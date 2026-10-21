from datetime import UTC, date, datetime, timedelta

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


# --- finality: a bar is final only if it was downloaded after its session closed ---------

D = date(2026, 10, 15)  # Thursday


class IntradayProvider:
    """Wraps FakeProvider: bar D comes back 10% lower until it has closed (00:00 UTC D+1
    for coins), like an in-progress session. `drop` lists dates the provider stops sending."""

    def __init__(self, clock) -> None:
        from app.data.fake_provider import FakeProvider

        self.inner = FakeProvider(today=D + timedelta(days=1))
        self.clock = clock
        self.calls = 0
        self.drop: set[date] = set()
        self.empty = False

    def get_history(self, symbol, start, end):
        from dataclasses import replace

        self.calls += 1
        if self.empty:
            return []
        final = self.clock() >= datetime.combine(D + timedelta(days=1), datetime.min.time(), UTC)
        out = []
        for b in self.inner.get_history(symbol, start, end):
            if b.date in self.drop:
                continue
            if b.date == D and not final:
                b = replace(b, close=b.close * 0.9, adj_close=b.adj_close * 0.9)
            out.append(b)
        return out

    def get_quote(self, symbol):
        return self.inner.get_quote(symbol)


def _true_close(symbol: str, d: date) -> float:
    from app.data.fake_provider import FakeProvider

    return FakeProvider(today=d).get_history(symbol, d, d)[0].close


def _intraday_service(db, at: datetime):
    t = {"now": at}
    provider = IntradayProvider(lambda: t["now"])
    svc = MarketDataService(
        db,
        provider,
        QuoteCache(),
        now=lambda: (t["now"] + timedelta(hours=9)).replace(tzinfo=None),  # local KST clock
        utc_now=lambda: t["now"],
    )
    return svc, provider, t


@pytest.mark.parametrize(
    ("synced", "read", "max_age"),
    [
        # Inside the 15-minute TTL, but the bar closed in between.
        (
            datetime(2026, 10, 15, 23, 55, tzinfo=UTC),
            datetime(2026, 10, 16, 0, 5, tzinfo=UTC),
            None,
        ),
        # The forecaster's reference path: max_age would otherwise skip the sync.
        (
            datetime(2026, 10, 15, 6, 0, tzinfo=UTC),
            datetime(2026, 10, 16, 0, 40, tzinfo=UTC),
            timedelta(hours=20),
        ),
    ],
)
def test_bar_cached_in_progress_is_refetched_once_it_closes(db, synced, read, max_age):
    svc, provider, t = _intraday_service(db, synced)
    assert svc.get_history("BTC-USD", date(2026, 9, 1), final_only=True)[-1].date < D
    t["now"] = read
    calls = provider.calls
    bars = svc.get_history("BTC-USD", date(2026, 9, 1), final_only=True, max_age=max_age)
    assert provider.calls > calls
    assert bars[-1].date == D
    assert bars[-1].close == pytest.approx(_true_close("BTC-USD", D))


def test_in_progress_bar_is_hidden_until_a_final_version_arrives(db):
    svc, provider, t = _intraday_service(db, datetime(2026, 10, 15, 12, 0, tzinfo=UTC))
    svc.get_history("BTC-USD", date(2026, 9, 1))
    # Closed now, but the refresh fails: the stale partial bar must not pass as final.
    t["now"] = datetime(2026, 10, 16, 1, 0, tzinfo=UTC)
    provider.empty = True
    assert svc.get_history("BTC-USD", date(2026, 9, 1), final_only=True)[-1].date < D
    # Not final_only (display): the cached value is still shown.
    assert svc.get_history("BTC-USD", date(2026, 9, 1))[-1].date == D


def test_empty_refresh_does_not_advance_synced_at(db):
    from app.db.models import SymbolSync

    svc, provider, t = _intraday_service(db, datetime(2026, 10, 15, 12, 0, tzinfo=UTC))
    svc.get_history("AAPL", date(2026, 9, 1))
    before = db.get(SymbolSync, "AAPL").synced_at
    assert before == datetime(2026, 10, 15, 12, 0)  # naive UTC, not the local clock
    provider.empty = True
    t["now"] += timedelta(hours=2)
    svc.get_history("AAPL", date(2026, 9, 1))
    db.expire_all()
    assert db.get(SymbolSync, "AAPL").synced_at == before


def test_in_progress_bar_the_provider_no_longer_returns_is_deleted(db):
    svc, provider, t = _intraday_service(db, datetime(2026, 10, 15, 12, 0, tzinfo=UTC))
    svc.get_history("BTC-USD", date(2026, 9, 1))
    t["now"] = datetime(2026, 10, 16, 1, 0, tzinfo=UTC)
    # The provider skips D (in progress when cached) and D-2 (final when cached).
    provider.drop = {D, D - timedelta(days=2)}
    dates = {b.date for b in svc.get_history("BTC-USD", date(2026, 9, 1))}
    assert D not in dates
    assert D - timedelta(days=2) in dates  # a final bar survives a provider hiccup


def test_synced_at_in_the_future_is_not_trusted(db):
    from app.db.models import SymbolSync

    svc, provider, t = _intraday_service(db, datetime(2026, 10, 15, 12, 0, tzinfo=UTC))
    svc.get_history("BTC-USD", date(2026, 9, 1))
    # A legacy row written in local time (KST, 9 hours ahead) after D had closed in KST.
    db.get(SymbolSync, "BTC-USD").synced_at = datetime(2026, 10, 16, 9, 30)
    db.commit()
    t["now"] = datetime(2026, 10, 15, 12, 5, tzinfo=UTC)
    calls = provider.calls
    bars = svc.get_history("BTC-USD", date(2026, 9, 1), final_only=True)
    assert provider.calls > calls  # refreshed instead of trusting the future timestamp
    assert bars[-1].date < D
    db.expire_all()
    assert db.get(SymbolSync, "BTC-USD").synced_at == datetime(2026, 10, 15, 12, 5)


def test_refill_gaps_requests_dates_missing_inside_the_cache(db):
    svc, provider, t = _intraday_service(db, datetime(2026, 10, 16, 12, 0, tzinfo=UTC))
    hole = {date(2026, 9, 10), date(2026, 9, 11)}
    provider.drop = set(hole)
    svc.get_history("BTC-USD", date(2026, 9, 1))
    provider.drop = {date(2026, 9, 11)}  # one day comes back, the other is still absent
    assert svc.refill_gaps("BTC-USD") == [date(2026, 9, 11)]
    dates = {b.date for b in svc.get_history("BTC-USD", date(2026, 9, 1))}
    assert date(2026, 9, 10) in dates and date(2026, 9, 11) not in dates


def test_provider_bars_are_validated_before_caching(db):
    from dataclasses import replace

    svc, provider, t = _intraday_service(db, datetime(2026, 10, 16, 12, 0, tzinfo=UTC))
    real = provider.inner.get_history

    def broken(symbol, start, end):
        out = []
        for b in real(symbol, start, end):
            if b.date == date(2026, 9, 2):
                b = replace(b, close=0.0)
            if b.date == date(2026, 9, 3):
                b = replace(b, open=float("nan"), high=0.0, low=0.0)
            out.append(b)
        return out

    provider.inner.get_history = broken
    bars = {b.date: b for b in svc.get_history("^VIX", date(2026, 9, 1))}
    assert date(2026, 9, 2) not in bars  # no usable close: dropped
    kept = bars[date(2026, 9, 3)]  # usable close, broken range: kept, open stored as 0
    assert kept.open == 0.0 and kept.close > 0


def test_strict_usd_krw_lookup_raises_instead_of_substituting(db, provider, clock):
    from app.data.provider import DataUnavailableError

    svc = MarketDataService(db, provider, QuoteCache(), now=clock)
    lookup = svc.usd_krw_lookup(date(2026, 9, 1), strict=True)
    assert lookup(date(2026, 9, 5)) > 0
    with pytest.raises(DataUnavailableError):
        lookup(date(2026, 8, 1))  # before the loaded history
    with pytest.raises(DataUnavailableError):
        lookup(TODAY + timedelta(days=30))  # last known rate is too old
    # The display lookup keeps falling back.
    assert svc.usd_krw_lookup(date(2026, 9, 1))(date(2026, 8, 1)) > 0
