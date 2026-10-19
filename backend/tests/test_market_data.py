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

    assert provider.history_calls[-1] == ("AAPL", TODAY, TODAY)


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


def test_upbit_market_symbols_resolve(client):
    assert client.get("/api/market/krw-btc/quote").json()["symbol"] == "KRW-BTC"


def test_supported_crypto_list(client):
    symbols = [a["symbol"] for a in client.get("/api/market/crypto").json()]
    assert symbols == ["BTC-USD", "ETH-USD", "XRP-USD", "SOL-USD"]
