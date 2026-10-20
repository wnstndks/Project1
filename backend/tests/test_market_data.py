from datetime import date, datetime, timedelta

import pytest

from app.data.assets import UnsupportedSymbolError, normalize_symbol
from app.db.models import AssetType
from app.services.market_data import MarketDataService, QuoteCache, SymbolNotFoundError
from tests.conftest import TODAY


class Clock:
    def __init__(self, start: datetime) -> None:
        self.t = start

    def __call__(self) -> datetime:
        return self.t


@pytest.fixture
def clock() -> Clock:
    return Clock(datetime.combine(TODAY, datetime.min.time()) + timedelta(hours=10))


@pytest.fixture
def service(db, provider, clock) -> MarketDataService:
    return MarketDataService(db, provider, QuoteCache(), now=clock)


@pytest.mark.parametrize(
    ("asset_type", "raw", "expected"),
    [
        (AssetType.CRYPTO, "btc", "BTC-USD"),
        (AssetType.CRYPTO, "SOL-USD", "SOL-USD"),
        (AssetType.STOCK, " aapl ", "AAPL"),
        (AssetType.STOCK, "brk.b", "BRK.B"),
    ],
)
def test_normalize_symbol(asset_type, raw, expected):
    assert normalize_symbol(asset_type, raw) == expected


@pytest.mark.parametrize(
    ("asset_type", "raw"),
    [(AssetType.CRYPTO, "DOGE"), (AssetType.STOCK, "BTC-USD"), (AssetType.STOCK, "not a ticker")],
)
def test_normalize_symbol_rejects(asset_type, raw):
    with pytest.raises(UnsupportedSymbolError):
        normalize_symbol(asset_type, raw)


def test_history_is_cached_after_first_fetch(service, provider):
    start = date(2026, 9, 1)
    first = service.get_history("AAPL", start)
    second = service.get_history("AAPL", start)

    assert len(provider.history_calls) == 1
    assert [b.date for b in first] == [b.date for b in second]
    assert all(b.date.weekday() < 5 for b in first)


def test_crypto_history_includes_weekends(service):
    bars = service.get_history("BTC-USD", date(2026, 10, 1))
    assert len(bars) == 16
    assert any(b.date.weekday() >= 5 for b in bars)


def test_earlier_start_fetches_only_the_missing_range(service, provider):
    service.get_history("AAPL", date(2026, 9, 1))
    service.get_history("AAPL", date(2026, 8, 1))

    assert provider.history_calls[-1] == ("AAPL", date(2026, 8, 1), date(2026, 8, 31))


def test_stale_cache_refreshes_from_last_bar(service, provider, clock):
    service.get_history("AAPL", date(2026, 9, 1))
    clock.t += timedelta(hours=1)
    service.get_history("AAPL", date(2026, 9, 1))

    # Re-downloads a short overlap before the newest bar to detect re-adjusted history.
    assert provider.history_calls[-1] == ("AAPL", TODAY - timedelta(days=10), TODAY)


def test_unknown_symbol_raises(service):
    with pytest.raises(SymbolNotFoundError):
        service.get_history("ZZZZ", date(2026, 9, 1))
    with pytest.raises(SymbolNotFoundError):
        service.get_quote("ZZZZ")


def test_quote_cache_expires():
    now = [0.0]
    cache = QuoteCache(ttl_seconds=60, clock=lambda: now[0])
    from app.data.provider import Quote

    cache.put(Quote("AAPL", 1.0, datetime(2026, 1, 1)))
    assert cache.get("AAPL") is not None
    now[0] = 61
    assert cache.get("AAPL") is None


def test_history_endpoint(client):
    res = client.get("/api/market/btc/history", params={"start": "2026-10-10"})
    assert res.status_code == 200
    body = res.json()
    assert body[0]["date"] == "2026-10-10"
    assert set(body[0]) == {"date", "open", "high", "low", "close", "adj_close", "volume"}


def test_quote_and_fx_endpoints(client):
    assert client.get("/api/market/AAPL/quote").json()["symbol"] == "AAPL"
    fx = client.get("/api/market/fx/usdkrw").json()
    assert fx["symbol"] == "KRW=X"
    assert fx["price"] > 0


def test_endpoint_errors(client):
    assert client.get("/api/market/ZZZZ/quote").status_code == 404
    assert client.get("/api/market/DOGE-USD/quote").status_code == 422


def test_kimchi_premium(client, provider):
    rows = {r["symbol"]: r for r in client.get("/api/market/kimchi").json()}
    assert set(rows) == {"BTC-USD", "ETH-USD", "XRP-USD", "SOL-USD"}
    btc = rows["BTC-USD"]
    assert btc["global_krw"] == pytest.approx(btc["global_usd"] * btc["usd_krw"])
    assert btc["premium_pct"] == pytest.approx((btc["upbit_krw"] / btc["global_krw"] - 1) * 100)
    assert isinstance(btc["fx_stale"], bool)


def test_upbit_market_symbols_resolve(client):
    assert client.get("/api/market/krw-btc/quote").json()["symbol"] == "KRW-BTC"
    info = client.get("/api/market/KRW-BTC/info").json()
    assert info["asset_type"] == "crypto" and info["name"] == "Bitcoin"


def test_supported_crypto_list(client):
    symbols = [a["symbol"] for a in client.get("/api/market/crypto").json()]
    assert symbols == ["BTC-USD", "ETH-USD", "XRP-USD", "SOL-USD"]


def test_final_only_drops_bars_whose_session_is_still_open(db, provider):
    from datetime import UTC

    # Friday 2026-10-16 at 15:00 ET: the stock session is still open.
    during = datetime(2026, 10, 16, 19, 0, tzinfo=UTC)
    after = datetime(2026, 10, 16, 21, 0, tzinfo=UTC)
    now = lambda: datetime(2026, 10, 16, 22, 0)  # noqa: E731
    for utc_now, last in ((during, date(2026, 10, 15)), (after, date(2026, 10, 16))):
        svc = MarketDataService(db, provider, QuoteCache(), now=now, utc_now=lambda u=utc_now: u)
        bars = svc.get_history("AAPL", date(2026, 10, 1), final_only=True)
        assert bars[-1].date == last
    # The current UTC day of a coin is never final until 00:00 UTC.
    svc = MarketDataService(db, provider, QuoteCache(), now=now, utc_now=lambda: after)
    assert svc.get_history("BTC-USD", date(2026, 10, 1), final_only=True)[-1].date == date(
        2026, 10, 15
    )


def test_provider_readjustment_triggers_full_refetch(db, clock):
    from dataclasses import replace

    from app.data.fake_provider import FakeProvider

    class SplittingProvider(FakeProvider):
        """Simulates Yahoo after a 10:1 split: every past price is divided by 10."""

        factor = 1.0

        def get_history(self, symbol, start, end):
            return [
                replace(
                    b,
                    open=b.open * self.factor,
                    high=b.high * self.factor,
                    low=b.low * self.factor,
                    close=b.close * self.factor,
                    adj_close=b.adj_close * self.factor,
                )
                for b in super().get_history(symbol, start, end)
            ]

    provider = SplittingProvider(today=TODAY)
    service = MarketDataService(db, provider, QuoteCache(), now=clock)
    before = {b.date: b.close for b in service.get_history("NVDA", date(2026, 6, 1))}

    provider.factor = 0.1
    clock.t += timedelta(hours=1)  # cache is stale: the next read refreshes
    after = {b.date: b.close for b in service.get_history("NVDA", date(2026, 6, 1))}

    # Old dates far before the overlap window were rescaled too: no fake -90% seam.
    first = min(before)
    assert after[first] == pytest.approx(before[first] * 0.1)
    assert set(after) == set(before)


def test_readjustment_with_ex_date_inside_the_overlap_is_detected(db, clock):
    from dataclasses import replace

    from app.data.fake_provider import FakeProvider

    ex = TODAY - timedelta(days=3)

    class SplitInsideWindow(FakeProvider):
        """Yahoo after a 2:1 split on `ex`: only bars before the ex-date are halved."""

        split = False

        def get_history(self, symbol, start, end):
            bars = super().get_history(symbol, start, end)
            if not self.split:
                return bars
            return [replace(b, close=b.close / 2) if b.date < ex else b for b in bars]

    provider = SplitInsideWindow(today=TODAY)
    service = MarketDataService(db, provider, QuoteCache(), now=clock)
    before = {b.date: b.close for b in service.get_history("NVDA", date(2026, 1, 1))}
    provider.split = True
    clock.t += timedelta(hours=1)
    after = {b.date: b.close for b in service.get_history("NVDA", date(2026, 1, 1))}

    first = min(before)
    assert after[first] == pytest.approx(before[first] / 2)  # old bars rescaled too


def test_cache_dropped_during_a_fetch_is_not_half_refilled(db, clock):
    from app.data.fake_provider import FakeProvider
    from app.services.market_data import drop_cached_bars

    class DroppingProvider(FakeProvider):
        drop = False

        def get_history(self, symbol, start, end):
            if self.drop:  # a split is recorded while this request is fetching
                drop_cached_bars(db, symbol)
                db.commit()
            return super().get_history(symbol, start, end)

    provider = DroppingProvider(today=TODAY)
    service = MarketDataService(db, provider, QuoteCache(), now=clock)
    service.get_history("NVDA", date(2026, 1, 1))
    provider.drop = True
    provider.history_calls.clear()
    clock.t += timedelta(hours=1)
    bars = service.get_history("NVDA", date(2026, 1, 1))
    # Instead of storing only the 10-day refresh window, it downloads the whole range again.
    assert [c[1] for c in provider.history_calls] == [TODAY - timedelta(days=10), date(2026, 1, 1)]
    assert min(b.date for b in bars) <= date(2026, 1, 5)


def test_single_corrected_bar_does_not_wipe_the_cache(db, clock):
    from dataclasses import replace

    from app.data.fake_provider import FakeProvider

    fixed = TODAY - timedelta(days=4)

    class CorrectingProvider(FakeProvider):
        """The provider corrects one bar in the overlap window; the rest are unchanged."""

        corrected = False

        def get_history(self, symbol, start, end):
            bars = super().get_history(symbol, start, end)
            if self.corrected:
                bars = [replace(b, close=b.close * 1.02) if b.date == fixed else b for b in bars]
            return bars

    provider = CorrectingProvider(today=TODAY)
    service = MarketDataService(db, provider, QuoteCache(), now=clock)
    service.get_history("NVDA", date(2026, 1, 1))
    provider.corrected = True
    provider.history_calls.clear()
    clock.t += timedelta(hours=1)
    after = {b.date: b.close for b in service.get_history("NVDA", date(2026, 1, 1))}

    # Only the overlap window was fetched, and the corrected bar was overwritten in place.
    assert [start for _, start, _ in provider.history_calls] == [TODAY - timedelta(days=10)]
    expected = {
        b.date: b.close for b in FakeProvider(today=TODAY).get_history("NVDA", fixed, fixed)
    }
    assert after[fixed] == pytest.approx(expected[fixed] * 1.02)


def test_unchanged_history_is_not_refetched(service, provider, clock):
    service.get_history("AAPL", date(2026, 6, 1))
    clock.t += timedelta(hours=1)
    service.get_history("AAPL", date(2026, 6, 1))
    # Second call only re-downloads the short overlap window, not the whole series.
    _, start, _ = provider.history_calls[-1]
    assert start >= TODAY - timedelta(days=15)
