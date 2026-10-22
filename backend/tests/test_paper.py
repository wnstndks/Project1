"""Paper trading: sizing, fills, account, scoring and the daily runner (ISSUE-012).

The runner is driven end to end over FakeProvider prices with a stub strategy and
predictor, so these tests need no network and no trained model.
"""

import math
import os
import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pandas as pd
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.config import Settings, get_settings
from app.data.fake_provider import FakeProvider
from app.data.provider import DataUnavailableError
from app.db.models import KillSwitchEvent, PaperSignal, Transaction
from app.forecast.universe import strategy_symbols
from app.services.market_data import MarketDataService, QuoteCache
from app.strategy.backtest import CostModel
from app.strategy.paper import (
    Costs,
    ExposureStrategy,
    PaperTrader,
    PendingOrder,
    SignalStrategy,
    Trade,
    account,
    equity_curve,
    fill_orders,
    fill_price,
    format_gaps,
    no_live_edge,
    order_costs,
    period_return,
    trade_pnl_krw,
)
from app.strategy.risk import RiskLimits, budgets_from_settings, target_weights
from app.strategy.s1 import CLASS_BUDGETS, round_trip_costs

COSTS = {"stock": Costs(0.0005, 5.0), "crypto": Costs(0.001, 10.0)}
LIMITS = RiskLimits()


@pytest.fixture
def settings(monkeypatch) -> Settings:
    for key in list(os.environ):
        if key.upper().startswith("AM_"):
            monkeypatch.delenv(key)
    get_settings.cache_clear()
    yield Settings(_env_file=None)
    get_settings.cache_clear()


# --- sizing (risk.target_weights) ----------------------------------------------------------


@dataclass
class Sig:
    symbol: str
    asset_class: str
    action: str = "hold"
    held_after: bool = False
    confidence: str | None = None
    rationale: dict = field(default_factory=dict)


BUDGETS = {"stock": 0.80, "crypto": 0.20}


def test_budgets_default_to_the_registered_split(settings):
    # The settings' defaults and the S1 definition must not drift apart: the backtest reads
    # s1.CLASS_BUDGETS, paper trading reads the settings.
    assert budgets_from_settings(settings) == BUDGETS == dict(CLASS_BUDGETS)


def test_budgets_cannot_add_up_to_leverage(settings, monkeypatch):
    monkeypatch.setenv("AM_STRATEGY_BUDGET_STOCK", "0.9")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    monkeypatch.setenv("AM_STRATEGY_BUDGET_STOCK", "-0.1")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_class_budget_is_split_equally_among_held_symbols():
    signals = [Sig(s, "stock", held_after=True) for s in "ABCDE"] + [
        Sig("F", "stock"),
        Sig("BTC", "crypto", held_after=True),
        Sig("ETH", "crypto", held_after=True),
        Sig("XRP", "crypto"),
    ]
    w = target_weights(signals, BUDGETS, LIMITS)
    assert {s: round(v, 10) for s, v in w.items()} == {
        **{s: 0.16 for s in "ABCDE"},
        "F": 0.0,
        "BTC": 0.1,
        "ETH": 0.1,
        "XRP": 0.0,
    }


def test_symbol_cap_leaves_the_rest_in_cash():
    w = target_weights(
        [Sig("A", "stock", held_after=True), Sig("B", "stock", held_after=True)], BUDGETS, LIMITS
    )
    assert w == {"A": 0.2, "B": 0.2}  # 0.4 each asked, capped; 0.4 of the budget stays cash


def test_sizing_fails_closed():
    held = [Sig("A", "stock", held_after=True)]
    assert target_weights(held, {"crypto": 0.2}, LIMITS) == {"A": 0.0}  # no budget, no buy
    with pytest.raises(ValueError):
        target_weights(held, {"stock": 0.9, "crypto": 0.2}, LIMITS)
    with pytest.raises(ValueError):
        target_weights(held, {"stock": float("nan")}, LIMITS)
    with pytest.raises(ValueError):
        target_weights(held + held, BUDGETS, LIMITS)


def test_only_a_real_true_counts_as_held():
    w = target_weights([Sig("A", "stock", held_after="yes")], BUDGETS, LIMITS)  # type: ignore[arg-type]
    assert w == {"A": 0.0}


# --- fills ---------------------------------------------------------------------------------


def test_fill_price_pays_slippage_against_the_open():
    assert fill_price("buy", 100.0, 10) == pytest.approx(100.1)
    assert fill_price("sell", 100.0, 10) == pytest.approx(99.9)


def order(key, symbol, side, notional=0.0, quantity=None, costs=COSTS["stock"]):
    return PendingOrder(key, symbol, side, notional, quantity, costs)


def test_sells_fill_first_and_fund_the_buys():
    # 100 cash; selling 1 A at ~50 brings ~150, enough for a 140 buy.
    orders = [order(1, "B", "buy", notional=140.0), order(2, "A", "sell", quantity=1.0)]
    out = fill_orders(orders, {"A": 50.0, "B": 10.0}, fx=1.0, cash=100.0, held={"A": 1.0})
    assert [f.key for f in out] == [2, 1]
    sell, buy = out
    assert sell.price == pytest.approx(50 * (1 - 5e-4))
    assert buy.filled and buy.note == ""
    assert buy.quantity * buy.price + buy.fee_krw == pytest.approx(140 * 1.0005)


def test_buy_is_cut_to_the_cash_left_after_a_gap():
    out = fill_orders([order(1, "B", "buy", notional=500.0)], {"B": 10.0}, 1.0, 100.0, {})
    assert out[0].note == "cash"
    assert out[0].quantity * out[0].price + out[0].fee_krw == pytest.approx(100.0)
    out = fill_orders([order(1, "B", "buy", notional=500.0)], {"B": 10.0}, 1.0, 0.0, {})
    assert (out[0].filled, out[0].note) == (False, "cash")


def test_sell_never_exceeds_the_quantity_held():
    out = fill_orders([order(1, "A", "sell", quantity=5.0)], {"A": 10.0}, 1.0, 0.0, {"A": 2.0})
    assert (out[0].quantity, out[0].note) == (2.0, "nothing_held")
    out = fill_orders([order(1, "A", "sell", quantity=5.0)], {"A": 10.0}, 1.0, 0.0, {})
    assert out[0].filled is False


def test_fills_need_a_usable_open_and_rate():
    with pytest.raises(ValueError):
        fill_orders([order(1, "A", "buy", 10.0)], {"A": float("nan")}, 1.0, 100.0, {})
    with pytest.raises(ValueError):
        fill_orders([order(1, "A", "buy", 10.0)], {"A": 10.0}, 0.0, 100.0, {})


def test_no_sequence_of_fills_borrows_or_shorts():
    rng = random.Random(3)
    for _ in range(200):
        cash, held = rng.uniform(0, 1000), {"A": rng.uniform(0, 5), "B": rng.uniform(0, 5)}
        orders = [
            order(i, rng.choice("AB"), rng.choice(["buy", "sell"]), rng.uniform(0, 800),
                  rng.uniform(0, 8))
            for i in range(6)
        ]  # fmt: skip
        orders = [o if o.side == "sell" else PendingOrder(o.key, o.symbol, "buy",
                  o.notional_krw, None, o.costs) for o in orders]  # fmt: skip
        opens = {"A": rng.uniform(5, 200), "B": rng.uniform(5, 200)}
        trades = [
            Trade(o.symbol, o.side, date(2026, 1, 1), f.quantity, f.price, 1.0, f.fee_krw)
            for o, f in zip(
                sorted(orders, key=lambda o: (o.side != "sell", o.key)),
                fill_orders(orders, opens, 1.0, cash, held),
                strict=True,
            )
            if f.filled
        ]
        start = [Trade(s, "buy", date(2026, 1, 1), q, 0.0, 1.0, 0.0) for s, q in held.items()]
        c, q = account(cash, start + trades)
        assert c >= -1e-6
        assert all(v >= -1e-9 for v in q.values())


# --- account, equity, scores -------------------------------------------------------------------


def test_account_and_equity_curve_carry_prices_over_gaps():
    trades = [
        Trade("SPY", "buy", date(2026, 1, 2), 10.0, 100.0, 1000.0, 500.0),
        Trade("SPY", "sell", date(2026, 1, 5), 4.0, 110.0, 1000.0, 200.0),
    ]
    cash, qty = account(2_000_000.0, trades)
    assert cash == pytest.approx(2_000_000 - 1_000_000 - 500 + 440_000 - 200)
    assert qty == {"SPY": pytest.approx(6.0)}
    closes = pd.DataFrame(
        {"SPY": [100.0, 105.0, 110.0]},
        index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05"]),
    )
    fx = pd.Series([1000.0], index=pd.to_datetime(["2025-12-31"]))
    curve = equity_curve(2_000_000.0, trades, closes, fx, date(2026, 1, 1), date(2026, 1, 5))
    assert list(curve.index.date) == [date(2026, 1, d) for d in range(1, 6)]
    assert curve.iloc[0] == 2_000_000.0
    assert curve.iloc[1] == pytest.approx(2_000_000 - 1_000_500 + 10 * 105 * 1000)
    assert curve.iloc[3] == curve.iloc[1]  # weekend carries Friday's close
    assert curve.iloc[4] == pytest.approx(cash + 6 * 110 * 1000)


def test_equity_curve_refuses_to_value_a_symbol_without_price():
    trades = [Trade("QQQ", "buy", date(2026, 1, 2), 1.0, 100.0, 1000.0, 0.0)]
    closes = pd.DataFrame({"SPY": [1.0]}, index=pd.to_datetime(["2026-01-01"]))
    fx = pd.Series([1000.0], index=pd.to_datetime(["2026-01-01"]))
    with pytest.raises(DataUnavailableError):
        equity_curve(1e6, trades, closes, fx, date(2026, 1, 1), date(2026, 1, 3))


def test_trade_pnl_counts_the_fee_and_the_avoided_loss():
    buy = Trade("A", "buy", date(2026, 1, 2), 2.0, 100.0, 1000.0, 100.0)
    assert trade_pnl_krw(buy, 110.0, 1000.0) == pytest.approx(220_000 - 200_000 - 100)
    sell = Trade("A", "sell", date(2026, 1, 2), 2.0, 100.0, 1000.0, 100.0)
    assert trade_pnl_krw(sell, 90.0, 1000.0) == pytest.approx(200_000 - 100 - 180_000)


def test_period_return():
    s = pd.Series([100.0, 120.0], index=pd.to_datetime(["2026-01-01", "2026-01-08"]))
    assert period_return(s, date(2026, 1, 1), date(2026, 1, 8)) == pytest.approx(0.2)


# --- the runner, end to end ------------------------------------------------------------------


class Clock:
    def __init__(self, provider: FakeProvider) -> None:
        self.provider = provider
        self.utc = datetime(2026, 1, 1, tzinfo=UTC)

    def at(self, utc: datetime) -> None:
        self.utc = utc
        self.provider.today = utc.date()


class StubStrategy:
    """Wants `picks` held; buys them on the first decision day and holds after."""

    strategy_id = "test-s1"
    horizon = "1w"

    def __init__(self, picks, decides=lambda cls, day: True) -> None:
        self.picks = set(picks)
        self.decides = decides
        self.seen_held: list[dict] = []

    def is_decision_day(self, asset_class, day):
        return self.decides(asset_class, day)

    def signals(self, rows, as_of, held, last):
        self.seen_held.append(dict(held))
        out = []
        for r in rows.itertuples(index=False):
            want = r.symbol in self.picks
            action = ("hold" if held.get(r.symbol) else "buy") if want else "no_edge"
            out.append(Sig(r.symbol, r.asset_class, action, want, "low", {"p_up": r.gbdt_p_up}))
        return out


def stub_predict(symbols, as_of):
    classes = strategy_symbols()
    return pd.DataFrame(
        {
            "symbol": list(symbols),
            "asset_class": [classes[s] for s in symbols],
            "date": [pd.Timestamp(as_of[classes[s]]) for s in symbols],
            "gbdt_p_up": 0.55,
            "scale": 0.02,
        }
    )


@pytest.fixture
def world(db, settings):
    provider = FakeProvider(today=date(2026, 10, 17))
    clock = Clock(provider)
    # Saturday 01:00 UTC: Friday 10-16 is final for stocks and coins alike.
    clock.at(datetime(2026, 10, 17, 1, 0, tzinfo=UTC))
    market = MarketDataService(
        db,
        provider,
        QuoteCache(),
        now=lambda: clock.utc.replace(tzinfo=None),
        utc_now=lambda: clock.utc,
    )
    live_factory = MagicMock()

    def trader(strategy, **kw):
        return PaperTrader(
            db,
            market,
            settings,
            strategy=strategy,
            predict=kw.pop("predict", stub_predict),
            costs=CostModel(),
            live_factory=live_factory,
            clock=lambda: clock.utc.replace(tzinfo=None),
            **kw,
        )

    return {"db": db, "provider": provider, "clock": clock, "trader": trader, "live": live_factory}


def _bar(provider, symbol, day):
    return next(b for b in provider.get_history(symbol, day, day))


def test_run_fill_score_end_to_end_without_real_orders(world):
    db, provider, clock = world["db"], world["provider"], world["clock"]
    trader = world["trader"](StubStrategy({"SPY", "QQQ", "BTC-USD"}))

    report = trader.run()
    assert report.decided == {"stock": date(2026, 10, 16), "crypto": date(2026, 10, 16)}
    assert report.recorded == len(strategy_symbols())
    assert (report.orders, report.tripped, report.skipped) == (3, None, None)
    rows = {r.symbol: r for r in db.scalars(select(PaperSignal))}
    spy, btc, iwm = rows["SPY"], rows["BTC-USD"], rows["IWM"]
    # SPY and QQQ share the stock budget (0.4 each asked). QQQ stops at the 20% symbol cap,
    # SPY as a broad index fund does not (D-025); BTC gets its 20% class budget. One order is
    # still capped at 5% of the 10,000,000 virtual capital.
    assert (spy.action, spy.side, spy.risk_status, spy.fill_status) == (
        "buy", "buy", "clipped", "pending",
    )  # fmt: skip
    # (5% of equity after the fees of the orders checked before it)
    assert float(spy.notional_krw) == pytest.approx(500_000, rel=1e-3)
    assert spy.target_weight == pytest.approx(0.4)
    assert rows["QQQ"].target_weight == pytest.approx(0.2)
    assert btc.target_weight == pytest.approx(0.2)
    assert spy.ref_price == pytest.approx(_bar(provider, "SPY", date(2026, 10, 16)).close)
    assert spy.target_date == date(2026, 10, 23)  # five sessions later
    assert btc.target_date == date(2026, 10, 23)  # seven coin days later
    assert (iwm.action, iwm.side, iwm.risk_status, iwm.fill_status) == (
        "no_edge", None, "none", "none",
    )  # fmt: skip
    # Signals made, orders approved, and the live broker was never even built.
    world["live"].assert_not_called()

    # Running again the same day records nothing new: the first record stands.
    again = trader.run()
    assert (again.decided, again.recorded) == ({}, 0)

    # Nothing fills before the next bar is final.
    assert trader.fill() == 0

    # Tuesday: the coin bar of Saturday and the stock bar of Monday are final.
    clock.at(datetime(2026, 10, 20, 1, 0, tzinfo=UTC))
    assert trader.fill() == 3
    db.expire_all()
    btc = db.get(PaperSignal, btc.id)
    spy = db.get(PaperSignal, spy.id)
    assert btc.fill_date == date(2026, 10, 17)  # the day after the signal, never the same bar
    assert spy.fill_date == date(2026, 10, 19)  # the next NYSE session
    btc_open = _bar(provider, "BTC-USD", date(2026, 10, 17)).open
    # BTC: 5 bp slippage on the price; commission 0.1% and FX spread 0.1% as the fee.
    assert float(btc.fill_price) == pytest.approx(btc_open * 1.0005, rel=1e-6)
    assert float(btc.fee_krw) == pytest.approx(float(btc.notional_krw) * 0.002, abs=1)
    # The open uses the previous day's USD/KRW, the newest known by then.
    fx_before = _bar(provider, "KRW=X", date(2026, 10, 16)).close
    assert float(btc.fill_fx) == pytest.approx(fx_before, rel=1e-6)
    spent = float(spy.quantity) * float(spy.fill_price) * float(spy.fill_fx)
    assert spent == pytest.approx(float(spy.notional_krw), rel=1e-6)
    # SPY: commission 0.25% + FX spread 0.1% as the fee.
    assert float(spy.fee_krw) == pytest.approx(float(spy.notional_krw) * 0.0035, abs=1)

    # Saturday after the target date: every signal is scored, filled or not.
    clock.at(datetime(2026, 10, 24, 1, 0, tzinfo=UTC))
    assert trader.score() == len(strategy_symbols())
    db.expire_all()
    spy = db.get(PaperSignal, spy.id)
    c16 = _bar(provider, "SPY", date(2026, 10, 16)).close
    c23 = _bar(provider, "SPY", date(2026, 10, 23)).close
    assert spy.exit_price == pytest.approx(c23)
    assert spy.signal_return == pytest.approx(c23 / c16 - 1)
    assert spy.benchmark_return == pytest.approx(spy.signal_return)  # SPY is the benchmark
    assert spy.trade_pnl_krw is not None
    iwm = db.get(PaperSignal, iwm.id)
    assert iwm.signal_return is not None and iwm.trade_pnl_krw is None
    assert trader.score() == 0  # scored once

    # The next decision day sees the strategy's own state from the last one.
    trader.run()
    assert trader.strategy.seen_held[-1]["SPY"] is True
    assert trader.strategy.seen_held[-1]["IWM"] is False

    # Real holdings are untouched: paper trading never writes a transaction.
    assert db.scalar(select(func.count()).select_from(Transaction)) == 0
    world["live"].assert_not_called()


def test_only_deciding_classes_get_signals(world):
    strategy = StubStrategy({"SPY"}, decides=lambda cls, day: cls == "crypto")
    report = world["trader"](strategy).run()
    assert set(report.decided) == {"crypto"}
    classes = {r.asset_class for r in world["db"].scalars(select(PaperSignal))}
    assert classes == {"crypto"}


def test_the_same_signal_key_is_stored_once(world):
    db = world["db"]
    world["trader"](StubStrategy(set())).run()
    first = db.scalars(select(PaperSignal).where(PaperSignal.symbol == "SPY")).one()
    dup = PaperSignal(
        created_at=datetime(2026, 10, 17), strategy_id=first.strategy_id, symbol="SPY",
        asset_class="stock", as_of=first.as_of, horizon="1w", action="buy", held_after=True,
        rationale={}, risk_status="none", fill_status="none",
    )  # fmt: skip
    db.add(dup)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_missing_inference_data_records_no_signal_and_sends_nothing(world):
    def broken(symbols, as_of):
        raise DataUnavailableError("SPY: newest final bar is 2026-10-15")

    report = world["trader"](StubStrategy({"SPY"}), predict=broken).run()
    assert report.recorded == 0
    assert report.skipped and "2026-10-15" not in report.skipped
    world["live"].assert_not_called()


# --- the runner and the kill switch ----------------------------------------------------------


def _filled(db, symbol, day, qty, price, fx, fee=0.0, side="buy"):
    db.add(
        PaperSignal(
            created_at=datetime(2026, 1, 1), strategy_id="test-s1", symbol=symbol,
            asset_class=strategy_symbols()[symbol], as_of=day, horizon="1w", action=side,
            held_after=side == "buy", rationale={}, risk_status="accepted", side=side,
            fill_status="filled", fill_date=day, quantity=Decimal(str(qty)),
            fill_price=Decimal(str(price)), fill_fx=Decimal(str(fx)), fee_krw=Decimal(str(fee)),
        )
    )  # fmt: skip
    db.commit()


def _synthetic_prices(trader, monkeypatch, closes):
    index = pd.date_range("2026-10-01", periods=len(closes), freq="D")
    monkeypatch.setattr(
        trader, "_closes", lambda symbols, start, end: pd.DataFrame({"SPY": closes}, index=index)
    )
    monkeypatch.setattr(trader, "_fx", lambda start, end: pd.Series(1000.0, index=index))


def test_drawdown_past_the_limit_trips_and_halts_every_signal(world, monkeypatch):
    db = world["db"]
    trader = world["trader"](StubStrategy({"SPY", "BTC-USD"}))
    # 10,000 shares bought at 100 x 1000 KRW would cost far more than the capital: use 90.
    _filled(db, "SPY", date(2026, 10, 1), 90.0, 100.0, 1000.0)
    # Cash 1,000,000 + 90 shares: equity 10,000,000 -> 7,750,000 is -22.5% (each day -2.5%).
    closes = [100.0 - 2.5 * i if i <= 10 else 75.0 for i in range(17)]
    _synthetic_prices(trader, monkeypatch, closes)
    paper_submit = MagicMock()
    monkeypatch.setattr("app.strategy.paper.PaperBroker.submit", paper_submit)

    report = trader.run()
    assert report.tripped == "max_drawdown"
    event = db.scalars(select(KillSwitchEvent)).one()
    assert (event.action, event.reason_code, event.actor) == ("trip", "max_drawdown", "system")
    assert "%" in event.detail and "KRW" not in event.detail
    rows = list(db.scalars(select(PaperSignal).where(PaperSignal.fill_status != "filled")))
    assert rows and {r.risk_status for r in rows} == {"halted"}
    assert all("max_drawdown" in r.risk_reason for r in rows)
    assert {r.fill_status for r in rows} == {"none"}
    paper_submit.assert_not_called()
    world["live"].assert_not_called()


def test_daily_loss_past_the_limit_trips(world, monkeypatch):
    trader = world["trader"](StubStrategy(set()))
    _filled(world["db"], "SPY", date(2026, 10, 1), 90.0, 100.0, 1000.0)
    # One -4% day on 90% invested is a -3.6% day for the account.
    _synthetic_prices(trader, monkeypatch, [100.0] * 8 + [96.0] * 9)
    assert trader.check_limits(date(2026, 10, 17)) == "daily_loss"


def test_reset_starts_a_new_watch_but_a_new_breach_trips_again(world, monkeypatch):
    db, clock = world["db"], world["clock"]
    trader = world["trader"](StubStrategy(set()))
    _filled(db, "SPY", date(2026, 10, 1), 90.0, 100.0, 1000.0)
    closes = [100.0 - 2.5 * i if i <= 10 else 75.0 for i in range(17)]
    _synthetic_prices(trader, monkeypatch, closes)
    assert trader.check_limits(date(2026, 10, 17)) == "max_drawdown"
    with pytest.raises(PermissionError):
        trader.kill.reset(actor="system")
    trader.kill.reset(actor="user")  # the clock says 2026-10-17
    assert trader.check_limits(date(2026, 10, 17)) is None
    # A fresh 20%+ fall after the reset trips again.
    _synthetic_prices(
        trader, monkeypatch, closes[:16] + [75.0, *[75.0 - 2 * i for i in range(1, 12)]]
    )
    clock.at(datetime(2026, 10, 29, 1, 0, tzinfo=UTC))
    assert trader.check_limits(date(2026, 10, 28)) == "max_drawdown"


def test_unpriced_account_trips_stale_data(world, monkeypatch):
    trader = world["trader"](StubStrategy({"SPY"}))
    _filled(world["db"], "SPY", date(2026, 10, 1), 1.0, 100.0, 1000.0)

    def no_prices(symbols, start, end):
        raise DataUnavailableError("SPY: provider failed (token=abc)")

    monkeypatch.setattr(trader, "_closes", no_prices)
    assert trader.run().tripped == "stale_data"
    event = world["db"].scalars(select(KillSwitchEvent)).one()
    assert event.reason_code == "stale_data" and "token" not in event.detail


def test_negative_cash_trips_leverage(world):
    trader = world["trader"](StubStrategy(set()))
    _filled(world["db"], "SPY", date(2026, 10, 1), 1000.0, 100.0, 1000.0)  # 100,000,000 KRW
    assert trader.check_limits(date(2026, 10, 17)) == "leverage"
    assert trader.kill.state().tripped


def test_unreadable_kill_switch_halts_the_run(world, monkeypatch):
    trader = world["trader"](StubStrategy({"SPY", "BTC-USD"}))
    real = trader.kill.db
    broken = MagicMock(wraps=real)
    broken.scalars.side_effect = RuntimeError("disk")
    paper_submit = MagicMock()
    monkeypatch.setattr("app.strategy.paper.PaperBroker.submit", paper_submit)
    monkeypatch.setattr(trader.kill, "db", broken)
    report = trader.run()
    assert report.tripped == "state_unreadable"
    statuses = {r.risk_status for r in real.scalars(select(PaperSignal))}
    assert statuses == {"halted"}
    paper_submit.assert_not_called()
    world["live"].assert_not_called()


def test_recorded_rationale_and_reasons_hold_no_amounts_or_secrets(world):
    world["trader"](StubStrategy({"SPY", "BTC-USD"})).run()
    for r in world["db"].scalars(select(PaperSignal)):
        text = f"{r.rationale} {r.risk_reason or ''}"
        assert "key" not in text.lower() and "account" not in text.lower()
        assert not math.isnan(r.ref_price)


# --- costs and the S1 adapter ------------------------------------------------------------------


def test_paper_costs_split_the_backtest_rate_without_changing_it():
    model = CostModel()
    for symbol, cls in (("SPY", "stock"), ("BTC-USD", "crypto"), ("SOL-USD", "crypto")):
        for side in ("buy", "sell"):
            from app.strategy.backtest import instrument

            c = order_costs(model, symbol, cls, side)
            assert c.fee_rate + c.slippage_bps / 1e4 == pytest.approx(
                model.rate(instrument(symbol, cls), side)
            )
    assert order_costs(model, "BTC-USD", "crypto", "buy").slippage_bps == 5.0
    assert order_costs(model, "SOL-USD", "crypto", "buy").slippage_bps == 10.0


def test_s1_adapter_decides_on_the_registered_calendar_and_has_no_live_edge():
    from app.strategy.s1 import s1_1w

    model = CostModel()
    strategy = SignalStrategy(s1_1w(round_trip_costs(model)))
    assert strategy.strategy_id == "S1-1w" and strategy.horizon == "1w"
    assert strategy.is_decision_day("stock", date(2026, 10, 16))  # last session of the week
    assert not strategy.is_decision_day("stock", date(2026, 10, 15))
    assert strategy.is_decision_day("crypto", date(2026, 10, 18))  # Sunday
    assert not strategy.is_decision_day("crypto", date(2026, 10, 16))

    day = date(2026, 10, 16)
    rows = stub_predict(sorted(strategy_symbols()), {"stock": day, "crypto": day}).assign(
        gbdt_q10=-1.0, gbdt_q50=2.0, gbdt_q90=3.0, climatology_p_up=0.5
    )
    signals = strategy.signals(rows, {"stock": day}, {"SPY": True})
    assert {s.asset_class for s in signals} == {"stock"}
    assert {s.action for s in signals} == {"no_edge"}
    assert not any(s.held_after for s in signals)  # the held SPY is closed without an edge
    spy = next(s for s in signals if s.symbol == "SPY")
    assert spy.rationale["edge_reason"] == "not_candidate"


class ConstantModel:
    """Stands in for a trained forecaster; records the rows it was asked about."""

    def __init__(self, p_up: float) -> None:
        self.p_up = p_up

    def predict(self, rows):
        return pd.DataFrame(
            {"q10": -1.0, "q50": 0.1, "q90": 1.0, "p_up": self.p_up}, index=rows.index
        )


def test_predictor_builds_rows_from_strict_bars_and_the_current_run(world, tmp_path):
    from app.forecast import store
    from app.strategy.paper import make_predictor

    universe = sorted(strategy_symbols())
    store.save(
        tmp_path,
        meta={"universe": universe},
        report={},
        models={"1w": {"gbdt": ConstantModel(0.6), "climatology": ConstantModel(0.5)}},
        offsets={"1w": {"gbdt": {"stock": 0.5}}},
        backtests={},
    )
    market = world["trader"](StubStrategy(set())).market
    predict = make_predictor(market, tmp_path, "1w")
    day = date(2026, 10, 16)
    rows = predict(["SPY", "BTC-USD"], {"stock": day, "crypto": day})
    assert sorted(rows["symbol"]) == ["BTC-USD", "SPY"]
    assert set(rows["date"].dt.date) == {day}
    spy = rows.set_index("symbol").loc["SPY"]
    assert (spy["gbdt_q10"], spy["gbdt_q90"], spy["gbdt_p_up"]) == (-1.5, 1.5, 0.6)
    assert spy["climatology_p_up"] == 0.5 and spy["scale"] > 0
    assert rows["run_id"].nunique() == 1


def test_predictor_without_a_trained_run_gives_no_rows(world, tmp_path):
    from app.strategy.paper import make_predictor

    market = world["trader"](StubStrategy(set())).market
    with pytest.raises(DataUnavailableError):
        make_predictor(market, tmp_path, "1w")(["SPY"], {"stock": date(2026, 10, 16)})


# --- a trip between approval and fill ---------------------------------------------------------


def _pending_then_tuesday(world, picks=("SPY", "BTC-USD")):
    trader = world["trader"](StubStrategy(set(picks)))
    assert trader.run().orders == len(picks)
    return trader


def _fill_states(db):
    db.expire_all()
    return {(r.fill_status, r.fill_note, r.risk_status) for r in db.scalars(
        select(PaperSignal).where(PaperSignal.side.is_not(None)))}  # fmt: skip


def test_a_trip_after_approval_cancels_pending_orders(world):
    trader = _pending_then_tuesday(world)
    trader.kill.trip("daily_loss", "2026-10-17 daily_loss 3.40%")
    world["clock"].at(datetime(2026, 10, 20, 1, 0, tzinfo=UTC))
    assert trader.fill() == 0
    assert _fill_states(world["db"]) == {("expired", "kill_switch", "halted")}
    world["live"].assert_not_called()


def test_a_reset_does_not_revive_orders_approved_before_the_trip(world):
    trader = _pending_then_tuesday(world)
    trader.kill.trip("max_drawdown", "2026-10-17 max_drawdown 21.00%")
    trader.kill.reset(actor="user")
    world["clock"].at(datetime(2026, 10, 20, 1, 0, tzinfo=UTC))
    assert trader.fill() == 0
    assert _fill_states(world["db"]) == {("expired", "kill_switch", "halted")}


def test_orders_approved_after_a_reset_fill_normally(world):
    clock = world["clock"]
    trader = world["trader"](StubStrategy({"SPY", "BTC-USD"}))
    clock.at(datetime(2026, 10, 16, 12, 0, tzinfo=UTC))
    trader.kill.trip("manual", "test", actor="user")
    trader.kill.reset(actor="user")
    clock.at(datetime(2026, 10, 17, 1, 0, tzinfo=UTC))
    assert trader.run().orders == 2
    clock.at(datetime(2026, 10, 20, 1, 0, tzinfo=UTC))
    assert trader.fill() == 2


def test_unreadable_trip_history_cancels_pending_orders(world, monkeypatch):
    trader = _pending_then_tuesday(world)
    monkeypatch.setattr(trader.kill, "last_trip_at", lambda: datetime.max)
    world["clock"].at(datetime(2026, 10, 20, 1, 0, tzinfo=UTC))
    assert trader.fill() == 0
    assert _fill_states(world["db"]) == {("expired", "kill_switch", "halted")}


# --- the S2 exposure adapter ------------------------------------------------------------------


@dataclass(frozen=True)
class S2Config:
    name: str = "test-s2"
    horizon: str = "1d"
    min_trade_share: float = 0.02
    universe: dict = field(default_factory=lambda: {"SPY": "stock", "BTC-USD": "crypto"})
    exposure: dict = field(default_factory=lambda: {"stock": 1.0, "crypto": 1.0})


@dataclass
class ExpSig:
    symbol: str
    asset_class: str
    action: str
    held_after: bool
    confidence: str | None
    reasons: dict
    target_exposure: float


class FakeDecide:
    """Stands in for the S2 rule: sets the configured exposure, remembers what it saw."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def __call__(self, rows, as_of, prev, edge_at, config, asset_class):
        self.calls.append(
            (asset_class, as_of, dict(prev), edge_at(as_of, asset_class, "1d", "vol"))
        )
        k = config.exposure[asset_class]
        out = []
        for r in rows[rows["asset_class"] == asset_class].itertuples(index=False):
            action = "buy" if k > prev.get("R", 0.0) else "hold"
            reasons = {"sigma_hat": 0.16, "sigma_source": "gbdt", "e": k, "R": k, "scale": r.scale}
            out.append(ExpSig(r.symbol, asset_class, action, k > 0, "low", reasons, k))
        return out


def test_s2_adapter_sizes_by_exposure_with_the_index_cap_and_never_goes_live(world):
    db = world["db"]
    decide = FakeDecide()
    trader = world["trader"](ExposureStrategy(S2Config(), decide))
    assert trader.min_order_share == 0.02  # the config's registered tolerance

    report = trader.run()
    assert report.decided == {"stock": date(2026, 10, 16), "crypto": date(2026, 10, 16)}
    assert report.recorded == 2 and report.orders == 2
    rows = {r.symbol: r for r in db.scalars(select(PaperSignal))}
    assert set(rows) == {"SPY", "BTC-USD"}  # only the strategy's own universe
    spy, btc = rows["SPY"], rows["BTC-USD"]
    # Budget x exposure: SPY may reach the whole stock budget under the index fund cap.
    assert spy.target_weight == pytest.approx(0.8)
    assert btc.target_weight == pytest.approx(0.2)
    # Each buy is still cut to one order's 5% of equity: exposure is built over days.
    assert spy.risk_status == btc.risk_status == "clipped"
    assert float(spy.notional_krw) == pytest.approx(500_000, rel=1e-2)
    # The state the next decision starts from, and the 1d horizon's target date.
    assert (spy.rationale["e"], spy.rationale["R"]) == (1.0, 1.0)
    assert spy.target_date == date(2026, 10, 19) and btc.target_date == date(2026, 10, 17)
    assert decide.calls[0][2] == {}  # first decision starts from no state
    world["live"].assert_not_called()

    # Sunday: only the coin bar of Saturday is new; the coin class reads its own state back.
    world["clock"].at(datetime(2026, 10, 18, 1, 0, tzinfo=UTC))
    again = trader.run()
    assert again.decided == {"crypto": date(2026, 10, 17)}
    assert decide.calls[-1][:3] == ("crypto", date(2026, 10, 17), {"e": 1.0, "R": 1.0})
    world["live"].assert_not_called()
    assert db.scalar(select(func.count()).select_from(Transaction)) == 0


def test_s2_changes_within_the_tolerance_are_not_traded(world):
    # Coin exposure 0.05 -> weight 0.01 of equity, inside the 2% tolerance: no order.
    config = S2Config(exposure={"stock": 0.0, "crypto": 0.05})
    world["trader"](ExposureStrategy(config, FakeDecide())).run()
    rows = {r.symbol: r for r in world["db"].scalars(select(PaperSignal))}
    assert rows["BTC-USD"].target_weight == pytest.approx(0.01)
    assert (rows["BTC-USD"].side, rows["BTC-USD"].risk_status) == (None, "none")
    assert (rows["SPY"].side, rows["SPY"].target_weight) == (None, 0.0)


def test_s2_state_that_cannot_be_read_starts_from_zero_and_says_so(caplog):
    strategy = ExposureStrategy(S2Config(), FakeDecide())
    ok = {"SPY": {"e": 0.6, "R": 0.5}}
    assert strategy.state("stock", ok) == ({"e": 0.6, "R": 0.5}, False)
    assert strategy.state("stock", {}) == ({}, False)  # first decision: nothing to reset
    assert strategy.state("crypto", ok) == ({}, False)  # another class's state is never used
    bad_states = (
        {"e": 0.6},
        {"e": "0.6", "R": 0.5},
        {"e": 1.5, "R": 0.5},
        {"e": True, "R": 0.5},
        {"e": float("nan"), "R": 0.5},
    )
    for bad in bad_states:
        caplog.clear()
        assert strategy.state("stock", {"SPY": bad}) == ({}, True)
        assert "starting from zero" in caplog.text

    # The reset reaches the records: every signal of that class carries the flag.
    day = date(2026, 10, 16)
    rows = stub_predict(["SPY", "BTC-USD"], {"stock": day, "crypto": day})
    last = {"SPY": {"e": None, "R": 0.5}, "BTC-USD": {"e": 0.2, "R": 0.2}}
    signals = {s.symbol: s for s in strategy.signals(rows, {"stock": day, "crypto": day}, {}, last)}
    assert signals["SPY"].rationale["state_reset"] is True
    assert "state_reset" not in signals["BTC-USD"].rationale


def test_s2_reset_is_recorded_in_the_paper_signals(world, caplog):
    db = world["db"]
    trader = world["trader"](ExposureStrategy(S2Config(), FakeDecide()))
    trader.run()
    # Corrupt the stored coin state, then decide the next coin day.
    btc = db.scalars(select(PaperSignal).where(PaperSignal.symbol == "BTC-USD")).one()
    btc.rationale = {**btc.rationale, "R": "broken"}
    db.commit()
    world["clock"].at(datetime(2026, 10, 18, 1, 0, tzinfo=UTC))
    trader.run()
    new = db.scalars(
        select(PaperSignal).where(
            PaperSignal.symbol == "BTC-USD", PaperSignal.as_of == date(2026, 10, 17)
        )
    ).one()
    assert new.rationale["state_reset"] is True
    assert "starting from zero" in caplog.text
    world["live"].assert_not_called()


def test_s2_signal_without_state_is_refused():
    def stateless(rows, as_of, prev, edge_at, config, asset_class):
        return [ExpSig("SPY", "stock", "buy", True, None, {"sigma_hat": 0.1}, 1.0)]

    strategy = ExposureStrategy(S2Config(), stateless)
    day = date(2026, 10, 16)
    with pytest.raises(ValueError):
        strategy.signals(
            stub_predict(["SPY"], {"stock": day, "crypto": day}), {"stock": day}, {}, {}
        )


def test_s2_paper_edge_is_off_until_the_forward_test():
    status = no_live_edge(date(2026, 10, 16), "stock", "1d", "vol")
    assert (status.edge, status.reason) == (False, "not_candidate")
    strategy = ExposureStrategy(S2Config(), FakeDecide())
    assert strategy.edge_at is no_live_edge
    assert strategy.is_decision_day("stock", date(2026, 10, 15))  # every final session
    assert strategy.is_decision_day("crypto", date(2026, 10, 15))


# --- S2 with the real rule (s2.py) ----------------------------------------------------------


def _always_edge(as_of, asset_class, horizon, *_):
    from app.forecast.report import EdgeStatus

    return EdgeStatus(True, "edge", 0.6, 500)


def s2_predict(symbols, as_of):
    rows = stub_predict(symbols, as_of)
    # Standardized 80% range of width 2.5632 x 0.01 per day: sigma 0.01 a bar.
    return rows.assign(
        scale=0.01, gbdt_q10=-1.2816, gbdt_q90=1.2816, ewma_t_q10=-2.0, ewma_t_q90=2.0
    )


def test_s2_cli_strategy_is_the_registered_rule_with_the_live_edge_off(settings):
    from app.strategy.paper import make_strategy

    strategy = make_strategy("s2", settings, CostModel())
    assert (strategy.strategy_id, strategy.horizon) == ("S2-1d", "1d")
    assert strategy.universe == {"SPY": "stock", "BTC-USD": "crypto"}
    assert strategy.edge_at is no_live_edge
    from app.strategy.s2 import s2_1d

    # One registered tolerance (s2.S2Config), read by paper trading (verifier N-10).
    assert strategy.min_order_share == s2_1d().min_trade_share == 0.02
    assert make_strategy("s1", settings, CostModel()).strategy_id == "S1-1w"
    with pytest.raises(ValueError):
        make_strategy("s3", settings, CostModel())


def test_s2_rule_without_live_edge_records_no_edge_and_trades_nothing(world, settings):
    from app.strategy.paper import make_strategy

    trader = world["trader"](make_strategy("s2", settings, CostModel()), predict=s2_predict)
    report = trader.run()
    assert (report.recorded, report.orders) == (2, 0)
    for r in world["db"].scalars(select(PaperSignal)):
        assert (r.action, r.held_after, r.target_weight, r.side) == ("no_edge", False, 0.0, None)
        assert (r.rationale["e"], r.rationale["R"]) == (0.0, 0.0)
    world["live"].assert_not_called()


def test_s2_rule_end_to_end_ratchets_state_through_the_records(world):
    from app.strategy.s2 import paper_decider, s2_1d

    db, clock = world["db"], world["clock"]
    strategy = ExposureStrategy(s2_1d(), paper_decider(BUDGETS), edge_at=_always_edge)
    trader = world["trader"](strategy, predict=s2_predict)

    # Friday 10-16: the stock week's last session (a weekly date), not the coin's.
    trader.run()
    rows = {r.symbol: r for r in db.scalars(select(PaperSignal))}
    spy, btc = rows["SPY"], rows["BTC-USD"]
    sigma = spy.rationale["sigma"]
    assert sigma == pytest.approx(0.01 * math.sqrt(252), rel=1e-3)
    k = min(1.0, 0.06 / (0.8 * sigma))
    assert (spy.action, spy.rationale["R"]) == ("buy", pytest.approx(k))
    assert spy.target_weight == pytest.approx(0.8 * k)  # above 0.20: the index fund cap
    assert (spy.side, spy.risk_status) == ("buy", "clipped")  # 5% of equity per order
    # The coin's allowed exposure starts at 0 and only a Sunday may raise it.
    assert (btc.action, btc.rationale["R"], btc.side) == ("hold", 0.0, None)

    # Monday 10-19 01:00 UTC: Sunday's coin bar is final, a weekly coin date.
    clock.at(datetime(2026, 10, 19, 1, 0, tzinfo=UTC))
    assert trader.run().decided == {"crypto": date(2026, 10, 18)}
    btc = db.scalars(
        select(PaperSignal).where(
            PaperSignal.symbol == "BTC-USD", PaperSignal.as_of == date(2026, 10, 18)
        )
    ).one()
    sigma_c = 0.01 * math.sqrt(365)
    k_c = min(1.0, 0.06 / (0.2 * sigma_c))
    assert (btc.action, btc.rationale["R"]) == ("buy", pytest.approx(k_c, rel=1e-3))
    assert btc.target_weight == pytest.approx(0.2 * k_c, rel=1e-3)
    assert btc.rationale["exposure_before"] == 0.0  # state read back from Friday's record
    world["live"].assert_not_called()
    assert db.scalar(select(func.count()).select_from(Transaction)) == 0


@pytest.mark.parametrize("bad", [-0.01, 1.0, float("nan"), "0.02", None])
def test_s2_tolerance_outside_a_share_of_equity_is_refused(bad):
    with pytest.raises(ValueError):
        ExposureStrategy(S2Config(min_trade_share=bad), FakeDecide())


# --- missed decision days (verifier N-13) ----------------------------------------------------


def test_missed_decision_days_are_logged_recorded_and_counted(world, caplog):
    db, clock = world["db"], world["clock"]
    decide = FakeDecide()
    trader = world["trader"](ExposureStrategy(S2Config(), decide))
    trader.run()  # Friday 10-16 for both classes (the stock week's weekly day)
    assert trader.run().missed == {}  # nothing new, nothing missed

    # The runner next runs on Wednesday 10-21: Tuesday's bars are final for both classes.
    clock.at(datetime(2026, 10, 21, 1, 0, tzinfo=UTC))
    report = trader.run()
    assert report.decided == {"stock": date(2026, 10, 20), "crypto": date(2026, 10, 20)}
    # Stocks missed Monday; coins missed Saturday to Monday, Sunday being a weekly day.
    assert report.missed == {"stock": 1, "crypto": 3}
    assert "decision day(s) missed" in caplog.text
    new = {
        r.symbol: r
        for r in db.scalars(select(PaperSignal).where(PaperSignal.as_of == date(2026, 10, 20)))
    }
    assert new["SPY"].rationale["missed_decision_days"] == ["2026-10-19"]
    assert new["SPY"].rationale["missed_weekly_days"] == []
    assert new["BTC-USD"].rationale["missed_decision_days"] == [
        "2026-10-17",
        "2026-10-18",
        "2026-10-19",
    ]
    assert new["BTC-USD"].rationale["missed_weekly_days"] == ["2026-10-18"]
    # The rule itself is unchanged: the coin state carried over from Friday's record.
    assert decide.calls[-1][2] == {"e": 1.0, "R": 1.0}

    gaps = trader.missed_decisions()
    stock, coin = gaps["stock"], gaps["crypto"]
    assert (stock.first, stock.through) == (date(2026, 10, 16), date(2026, 10, 20))
    assert (stock.expected, stock.recorded, stock.missed) == (3, 2, (date(2026, 10, 19),))
    assert stock.weekly_missed == () and stock.generated_share == pytest.approx(2 / 3)
    assert (coin.expected, coin.recorded, len(coin.missed)) == (5, 2, 3)
    assert coin.weekly_missed == (date(2026, 10, 18),)
    assert coin.generated_share == pytest.approx(0.4)  # below half: criterion 3 would fail
    text = format_gaps(gaps)
    assert "crypto: 2026-10-16..2026-10-20 expected=5 recorded=2 missed=3" in text
    assert "weekly_missed=1 (2026-10-18)" in text
    world["live"].assert_not_called()


def test_a_skipped_day_counts_as_missed(world):
    trader = world["trader"](ExposureStrategy(S2Config(), FakeDecide()))
    trader.run()
    world["clock"].at(datetime(2026, 10, 18, 1, 0, tzinfo=UTC))

    def no_data(symbols, as_of):
        raise DataUnavailableError("down")

    trader.predict = no_data
    assert trader.run().skipped  # Saturday's coin decision could not be made
    coin = trader.missed_decisions()["crypto"]
    assert coin.missed == (date(2026, 10, 17),) and coin.recorded == 1


def test_strategies_without_a_daily_calendar_report_no_gaps(world):
    trader = world["trader"](StubStrategy({"SPY"}))
    trader.run()
    assert trader.missed_decisions() == {}
    assert format_gaps({}) == "no decision calendar for this strategy"
    assert ExposureStrategy(S2Config(), FakeDecide()).is_weekly_day("crypto", date(2026, 10, 18))
