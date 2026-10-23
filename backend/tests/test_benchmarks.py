"""'Same money on the same days' benchmarks: cash flows, replay arithmetic, FX, API."""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from app.data.assets import UnsupportedSymbolError
from app.db.models import AssetType, Currency, Side, Transaction
from app.services.benchmarks import (
    DEFAULT_BENCHMARKS,
    BenchmarkService,
    CashFlow,
    cash_flows,
    parse_symbols,
    replay,
)
from app.services.errors import DomainError
from app.services.market_data import MarketDataService, QuoteCache
from app.services.portfolio import PortfolioService
from tests.conftest import TODAY

D = date


def tx(
    symbol: str,
    side: Side,
    day: date,
    qty: str,
    price: str,
    fee: str = "0",
    currency: Currency = Currency.USD,
    fx_rate: str | None = None,
    asset_type: AssetType = AssetType.STOCK,
) -> Transaction:
    return Transaction(
        asset_type=asset_type,
        symbol=symbol,
        side=side,
        trade_date=day,
        currency=currency,
        quantity=Decimal(qty),
        price=Decimal(price),
        fee=Decimal(fee),
        fx_rate=Decimal(fx_rate) if fx_rate else None,
    )


def const_fx(rate: str):
    return lambda _d: Decimal(rate)


def days(first: date, n: int) -> list[date]:
    return [first + timedelta(days=i) for i in range(n)]


# --- pure functions ----------------------------------------------------------------------------


def test_cash_flows_use_ledger_amounts_and_trade_date_rates():
    txs = [
        # Entered out of order; flows come back in ledger order.
        tx("AAPL", Side.SELL, D(2026, 1, 8), "4", "110", fee="1", fx_rate="1400"),
        tx("AAPL", Side.BUY, D(2026, 1, 5), "10", "100", fee="1"),
        tx(
            "BTC-USD",
            Side.BUY,
            D(2026, 1, 6),
            "0.01",
            "90000000",
            currency=Currency.KRW,
            asset_type=AssetType.CRYPTO,
        ),
    ]
    assert cash_flows(txs, const_fx("1300")) == [
        # (10 x 100 + 1 fee) x market rate 1300
        CashFlow(D(2026, 1, 5), Decimal("1301300")),
        # KRW trade: the won amount is exact, no rate involved
        CashFlow(D(2026, 1, 6), Decimal("900000")),
        # (4 x 110 - 1 fee) x the rate recorded on the trade, which beats the market rate
        CashFlow(D(2026, 1, 8), Decimal("-614600")),
    ]


def test_replay_buys_at_close_forward_fills_and_sells_units():
    closes = {
        D(2026, 1, 5): 100.0,
        D(2026, 1, 6): 100.0,
        D(2026, 1, 7): 110.0,
        D(2026, 1, 9): 120.0,
    }
    flows = [
        CashFlow(D(2026, 1, 5), Decimal("1000000")),
        CashFlow(D(2026, 1, 7), Decimal("-550000")),
    ]
    pts = replay(flows, closes, const_fx("1000"), end=D(2026, 1, 9))
    assert [p.date for p in pts] == days(D(2026, 1, 5), 5)
    # 10 units bought at 100,000 won; 550,000 won sold at 110,000 = 5 units; 1/8 has no bar and
    # keeps 1/7's close; 1/9 reprices the 5 units at 120.
    assert [p.value_krw for p in pts] == [1_000_000, 1_000_000, 550_000, 550_000, 600_000]
    assert [p.value for p in pts] == [1000.0, 1000.0, 550.0, 550.0, 600.0]


def test_replay_oversell_sells_everything_and_early_cash_waits_for_the_first_close():
    closes = {D(2026, 1, 7): 200.0}
    flows = [
        CashFlow(D(2026, 1, 5), Decimal("400000")),
        CashFlow(D(2026, 1, 8), Decimal("-999999999")),
    ]
    pts = replay(flows, closes, const_fx("1000"), end=D(2026, 1, 8))
    # Cash is held at face value until the benchmark has a price, then buys 2 units.
    assert [p.value_krw for p in pts] == [400_000, 400_000, 400_000, 0]


def test_replay_start_trims_output_but_replays_earlier_flows():
    closes = {d: 100.0 for d in days(D(2026, 1, 1), 10)}
    flows = [CashFlow(D(2026, 1, 2), Decimal("100000")), CashFlow(D(2026, 1, 4), Decimal("100000"))]
    full = replay(flows, closes, const_fx("1000"), end=D(2026, 1, 9))
    trimmed = replay(flows, closes, const_fx("1000"), end=D(2026, 1, 9), start=D(2026, 1, 6))
    assert trimmed == full[-4:]
    assert trimmed[0].value_krw == 200_000
    # A start before the first flow does not add zero-value days.
    assert replay(flows, closes, const_fx("1000"), end=D(2026, 1, 9), start=D(2025, 1, 1)) == full
    assert replay([], closes, const_fx("1000"), end=D(2026, 1, 9)) == []


def test_replay_applies_each_days_fx_rate():
    closes = {d: 100.0 for d in days(D(2026, 1, 1), 5)}
    fx = {
        D(2026, 1, 1): Decimal("1000"),
        D(2026, 1, 2): Decimal("1000"),
        D(2026, 1, 3): Decimal("1200"),
    }
    pts = replay(
        [CashFlow(D(2026, 1, 1), Decimal("500000"))], closes, lambda d: fx[d], end=D(2026, 1, 3)
    )
    # 5 units; the USD value is flat while the won value follows the rate.
    assert [p.value for p in pts] == [500.0, 500.0, 500.0]
    assert [p.value_krw for p in pts] == [500_000, 500_000, 600_000]


def test_parse_symbols_normalises_dedupes_and_limits():
    assert parse_symbols(None) == DEFAULT_BENCHMARKS.split(",")
    assert parse_symbols(" spy, btc ,SPY,,brk-b") == ["SPY", "BTC-USD", "BRK-B"]
    assert parse_symbols("", "QQQ") == ["QQQ"]
    with pytest.raises(UnsupportedSymbolError):
        parse_symbols("SP$Y")
    with pytest.raises(DomainError):
        parse_symbols(",".join(f"S{i}" for i in range(9)))


# --- service and API ---------------------------------------------------------------------------


def test_benchmark_curve_equals_my_history_when_i_hold_the_benchmark(db, provider):
    """Buying SPY at its close and benchmarking against SPY must reproduce my own curve: the
    flows, the daily grid, the forward-fill and the FX rule are then all aligned."""
    market = MarketDataService(db, provider, QuoteCache(), now=lambda: datetime(2026, 10, 16, 12))
    buy_day = D(2026, 9, 1)  # a Tuesday
    sell_day = D(2026, 9, 15)  # also a Tuesday
    close = provider.get_history("SPY", buy_day, buy_day)[0].close
    sell_close = provider.get_history("SPY", sell_day, sell_day)[0].close
    db.add(tx("SPY", Side.BUY, buy_day, "3", str(close)))
    db.add(tx("SPY", Side.SELL, sell_day, "1", str(sell_close)))
    db.commit()
    portfolio = PortfolioService(db, market, today=lambda: TODAY)
    service = BenchmarkService(db, market, portfolio, today=lambda: TODAY)

    result = service.compare(["SPY", "BTC-USD"], start=None)
    spy, btc = result.benchmarks
    assert spy.symbol == "SPY" and spy.name_ko == "S&P 500 ETF" and btc.symbol == "BTC-USD"
    assert [p.date for p in spy.points] == [p.date for p in result.mine] == days(buy_day, 46)
    for mine, point in zip(result.mine, spy.points, strict=True):
        assert point.value_krw == pytest.approx(mine.market_value_krw, abs=1)
        assert point.value == pytest.approx(mine.market_value, abs=0.01)
    # A different asset with the same flows gives a different curve.
    assert btc.points[-1].value_krw != spy.points[-1].value_krw

    trimmed = service.compare(["SPY"], start=D(2026, 10, 1))
    assert [p.date for p in trimmed.benchmarks[0].points] == days(D(2026, 10, 1), 16)
    assert trimmed.benchmarks[0].points[-1] == spy.points[-1]


def test_benchmark_api_shape_and_errors(client):
    empty = client.get("/api/portfolio/benchmark").json()
    assert empty["mine"] == []
    assert [b["symbol"] for b in empty["benchmarks"]] == DEFAULT_BENCHMARKS.split(",")
    assert all(b["points"] == [] for b in empty["benchmarks"])

    res = client.post(
        "/api/transactions",
        json={
            "asset_type": "stock",
            "symbol": "AAPL",
            "side": "buy",
            "trade_date": "2026-10-01",
            "quantity": "2",
            "price": "100",
        },
    )
    assert res.status_code == 201

    body = client.get("/api/portfolio/benchmark?symbols=spy,QQQ&start=2026-10-10").json()
    assert [b["symbol"] for b in body["benchmarks"]] == ["SPY", "QQQ"]
    assert body["benchmarks"][1]["name_ko"] == "나스닥 100 ETF"
    dates = [p["date"] for p in body["mine"]]
    assert dates[0] == "2026-10-10"
    assert [p["date"] for p in body["benchmarks"][0]["points"]] == dates
    assert set(body["mine"][0]) == {
        "date",
        "market_value",
        "market_value_krw",
        "cost_basis",
        "cost_basis_krw",
    }
    assert set(body["benchmarks"][0]["points"][0]) == {"date", "value", "value_krw"}
    assert body["benchmarks"][0]["points"][0]["value_krw"] > 0

    assert client.get("/api/portfolio/benchmark?symbols=SP$Y").status_code == 422
    assert client.get("/api/portfolio/benchmark?symbols=ZZZZ").status_code == 404
