"""Risk settings and the pure limit functions shared with the backtest (D-002, D-003)."""

import math
import random
from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.strategy.risk import (
    Book,
    Order,
    RiskLimits,
    adopt_strategy,
    apply_decision,
    cap_weights,
    check_order,
    kill_switch_triggers,
    max_drawdown,
    plan_rebalance,
    portfolio_breach,
    rebalance_orders,
)

LIMITS = RiskLimits()


@pytest.fixture
def clean_env(monkeypatch):
    """Settings built here never see backend/.env or the shell's AM_ variables (ISSUE-014)."""
    import os

    for key in list(os.environ):
        if key.upper().startswith("AM_"):
            monkeypatch.delenv(key)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


# --- settings ------------------------------------------------------------------------


def test_live_trading_is_off_by_default(clean_env):
    assert settings().live_trading is False


@pytest.mark.parametrize("value", ["1", "yes", "on", "y", "t", "tru", "enable", ""])
def test_live_trading_rejects_anything_but_the_exact_words(clean_env, value):
    clean_env.setenv("AM_LIVE_TRADING", value)
    with pytest.raises(ValidationError):
        settings()


@pytest.mark.parametrize("value", ["false", "FALSE", " False "])
def test_live_trading_accepts_false_spelled_loosely(clean_env, value):
    clean_env.setenv("AM_LIVE_TRADING", value)
    assert settings().live_trading is False


def test_risk_defaults_match_d002(clean_env):
    limits = RiskLimits.from_settings(settings())
    assert limits == RiskLimits(0.20, 0.03, 0.05, None, 0.20)
    # The dataclass defaults (used by pure-function callers) cannot drift from the settings.
    assert RiskLimits() == limits


def test_drawdown_limit_can_only_be_tightened(clean_env):
    clean_env.setenv("AM_RISK_MAX_DRAWDOWN", "0.15")
    assert RiskLimits.from_settings(settings()).max_drawdown == 0.15
    for loose in ("0.21", "0.5", "0", "-0.1"):
        clean_env.setenv("AM_RISK_MAX_DRAWDOWN", loose)
        with pytest.raises(ValidationError):
            settings()


def test_blank_absolute_order_cap_means_unset(clean_env):
    clean_env.setenv("AM_RISK_MAX_ORDER_KRW", "")
    assert settings().risk_max_order_krw is None
    clean_env.setenv("AM_RISK_MAX_ORDER_KRW", "500000")
    assert RiskLimits.from_settings(settings()).max_order_krw == 500000.0


# --- weights -------------------------------------------------------------------------


def test_cap_weights_clamps_shorts_and_symbol_cap():
    assert cap_weights({"A": -0.3, "B": 0.5, "C": 0.1}, LIMITS) == {"A": 0.0, "B": 0.2, "C": 0.1}


def test_cap_weights_scales_total_down_to_one():
    w = cap_weights({s: 0.2 for s in "ABCDEFG"}, LIMITS)  # 1.4 in total
    assert math.isclose(sum(w.values()), 1.0)
    assert all(math.isclose(v, 0.2 / 1.4) for v in w.values())


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), None])
def test_cap_weights_fails_closed_on_missing_values(bad):
    with pytest.raises(ValueError):
        cap_weights({"A": 0.1, "B": bad}, LIMITS)


# --- orders --------------------------------------------------------------------------


def book(cash=1_000_000.0, **positions) -> Book:
    return Book(cash, positions)


def test_buy_within_limits_is_accepted():
    d = check_order(Order("A", "buy", 40_000), book(), LIMITS)
    assert (d.status, d.notional, d.reasons) == ("accepted", 40_000, ())


def test_buy_is_clipped_to_the_per_order_cap():
    d = check_order(Order("A", "buy", 200_000), book(), LIMITS)
    assert d.status == "clipped"
    assert d.notional == pytest.approx(50_000)
    assert d.reasons == ("max_order_fraction",)


def test_absolute_order_cap_applies_when_smaller():
    limits = RiskLimits(max_order_krw=30_000)
    d = check_order(Order("A", "buy", 200_000), book(), limits)
    assert d.notional == pytest.approx(30_000)
    assert d.reasons == ("max_order_fraction", "max_order_krw")


def test_buy_is_clipped_to_the_symbol_weight_cap():
    b = book(cash=820_000.0, A=180_000.0)  # A at 18% of 1,000,000
    d = check_order(Order("A", "buy", 50_000), b, LIMITS)
    assert d.status == "clipped"
    assert d.notional == pytest.approx(20_000)
    assert d.reasons == ("max_position_weight",)


def test_buy_at_the_symbol_cap_is_rejected():
    d = check_order(Order("A", "buy", 10_000), book(cash=800_000.0, A=200_000.0), LIMITS)
    assert (d.status, d.notional) == ("rejected", 0.0)
    assert "max_position_weight" in d.reasons


def test_buy_never_borrows_fees_included():
    b = book(cash=10_000.0, A=190_000.0, B=200_000.0, C=200_000.0, D=200_000.0, E=200_000.0)
    d = check_order(Order("F", "buy", 40_000), b, LIMITS, fee_rate=0.01)
    assert d.status == "clipped"
    assert d.notional * 1.01 == pytest.approx(10_000)
    assert d.reasons == ("cash",)


def test_buy_without_cash_is_rejected():
    b = book(cash=0.0, A=200_000.0, B=200_000.0, C=200_000.0, D=200_000.0, E=200_000.0)
    d = check_order(Order("F", "buy", 10_000), b, LIMITS)
    assert d.status == "rejected"
    assert "cash" in d.reasons


def test_sell_more_than_held_is_rejected_as_short_sale():
    d = check_order(Order("A", "sell", 60_000), book(cash=950_000.0, A=50_000.0), LIMITS)
    assert (d.status, d.reasons) == ("rejected", ("short_sale",))
    d = check_order(Order("Z", "sell", 1.0), book(), LIMITS)
    assert d.status == "rejected"


def test_sells_ignore_the_order_cap():
    d = check_order(Order("A", "sell", 200_000), book(cash=800_000.0, A=200_000.0), LIMITS)
    assert (d.status, d.notional) == ("accepted", 200_000)


@pytest.mark.parametrize("notional", [0.0, -5.0, float("nan"), float("inf")])
def test_invalid_notional_is_rejected(notional):
    assert check_order(Order("A", "buy", notional), book(), LIMITS).status == "rejected"


@pytest.mark.parametrize("bad", [book(cash=-1.0), book(cash=float("nan")), book(cash=0.0)])
def test_invalid_or_leveraged_book_rejects_everything(bad):
    d = check_order(Order("A", "buy", 1_000), bad, LIMITS)
    assert (d.status, d.reasons) == ("rejected", ("invalid_book",))


def test_no_order_sequence_ever_leverages_the_book():
    rng = random.Random(7)
    symbols = list("ABCDEFGH")
    for _ in range(300):
        b = Book(rng.uniform(0, 1e6), {s: rng.uniform(0, 3e5) for s in rng.sample(symbols, 3)})
        fee = rng.choice([0.0, 0.001, 0.0025])
        for _ in range(10):
            side = rng.choice(["buy", "sell"])
            o = Order(rng.choice(symbols), side, rng.uniform(1, 5e5))
            d = check_order(o, b, LIMITS, fee_rate=fee)
            if d.status != "rejected":
                b = apply_decision(b, d, fee_rate=fee)
            assert b.cash >= -1e-6
            assert all(v >= -1e-6 for v in b.positions.values())
            if side == "buy" and d.status != "rejected":
                assert b.positions[o.symbol] <= LIMITS.max_position_weight * b.equity * 1.02


def test_rebalance_sells_first_and_respects_every_cap():
    b = book(cash=0.0, A=500_000.0, B=500_000.0)
    decisions = rebalance_orders(b, {"A": 0.2, "C": 0.2, "D": 0.6}, LIMITS)
    sides = [(d.order.symbol, d.order.side) for d in decisions]
    assert sides == [("A", "sell"), ("B", "sell"), ("C", "buy"), ("D", "buy")]
    assert decisions[0].notional == pytest.approx(300_000)  # A 50% -> 20%
    assert decisions[1].notional == pytest.approx(500_000)  # B not in target: sold in full
    # D asked for 60%: capped at the 20% weight and then at 5% per order.
    assert decisions[2].notional == pytest.approx(50_000)
    assert decisions[3].notional == pytest.approx(50_000)


def test_plan_rebalance_skips_small_changes_but_always_exits():
    b = book(cash=899_990.0, A=10.0, B=100_000.0)
    orders = plan_rebalance(b, {"B": 0.1005}, LIMITS, min_notional=1_000)
    assert orders == [Order("A", "sell", 10.0)]


# --- drawdown, adoption, kill switch triggers ---------------------------------------------


def test_max_drawdown():
    assert max_drawdown([100, 120, 90, 130, 104]) == pytest.approx(0.25)
    assert max_drawdown([]) == 0.0
    with pytest.raises(ValueError):
        max_drawdown([100, float("nan")])


@pytest.mark.parametrize(
    ("mdd", "adopted"),
    [(0.0, True), (0.19, True), (0.20, True), (-0.20, True), (0.2000001, False), (-0.25, False)],
)
def test_adopt_strategy_boundary(mdd, adopted):
    assert adopt_strategy(mdd).adopted is adopted


def test_adopt_strategy_uses_the_tightened_limit_and_rejects_nan():
    assert adopt_strategy(0.18, RiskLimits(max_drawdown=0.15)).adopted is False
    assert adopt_strategy(float("nan")).adopted is False


def test_exactly_twenty_percent_drawdown_does_not_trigger():
    curve = pd.Series([100.0, 80.0], index=pd.to_datetime(["2026-01-01", "2026-01-02"]))
    assert max_drawdown(curve) == pytest.approx(0.20)
    limits = RiskLimits(daily_loss_limit=0.5)
    assert kill_switch_triggers(curve, limits) == []
    assert portfolio_breach(curve, limits) is None
    nudged = curve.copy()
    nudged.iloc[-1] = 79.999
    assert portfolio_breach(nudged, limits).reason_code == "max_drawdown"


def test_kill_switch_triggers_on_a_synthetic_curve():
    days = pd.date_range("2026-01-01", periods=9, freq="D")
    # Two 2% steps down, a 4% day, recovery to a new peak, then a slide past 20%.
    values = [100, 98, 96.04, 92.2, 101, 95, 85, 80.5, 80]
    triggers = kill_switch_triggers(pd.Series(values, index=days, dtype=float), LIMITS)
    got = [(t.date, t.reason_code) for t in triggers]
    assert got == [
        (date(2026, 1, 4), "daily_loss"),  # 96.04 -> 92.2 is -4.0%
        (date(2026, 1, 6), "daily_loss"),  # 101 -> 95 is -5.9%
        (date(2026, 1, 7), "daily_loss"),  # 95 -> 85 is -10.5%
        (date(2026, 1, 8), "max_drawdown"),  # 80.5 is -20.3% from the 101 peak
        (date(2026, 1, 8), "daily_loss"),  # 85 -> 80.5 is -5.3%
    ]


def test_drawdown_trigger_rearms_only_after_a_new_peak():
    days = pd.date_range("2026-01-01", periods=6, freq="D")
    values = [100, 79, 85, 79, 100, 79]
    limits = RiskLimits(daily_loss_limit=0.99)
    got = [t.date for t in kill_switch_triggers(pd.Series(values, index=days, dtype=float), limits)]
    assert got == [date(2026, 1, 2), date(2026, 1, 6)]


def test_portfolio_breach_checks_the_latest_day():
    days = pd.date_range("2026-01-01", periods=3, freq="D")
    assert portfolio_breach(pd.Series([100.0, 99.0, 98.0], index=days), LIMITS) is None
    breach = portfolio_breach(pd.Series([100.0, 99.0, 95.0], index=days), LIMITS)
    assert (breach.reason_code, breach.date) == ("daily_loss", date(2026, 1, 3))
    with pytest.raises(ValueError):
        portfolio_breach(pd.Series([100.0, float("nan")], index=days[:2]), LIMITS)


def test_rebalance_takes_a_cost_per_order_and_trades_only_the_decision():
    b = book(cash=900_000.0, A=50_000.0, BTC=50_000.0)
    rates = {("A", "sell"): 0.01, ("C", "buy"): 0.02}
    decisions = rebalance_orders(
        b,
        {"A": 0.0, "C": 0.05, "BTC": 0.30},  # BTC is outside today's decision
        LIMITS,
        fee_rate=lambda o: rates[(o.symbol, o.side)],
        trade_only={"A", "C"},
    )
    assert [(d.order.symbol, d.order.side) for d in decisions] == [("A", "sell"), ("C", "buy")]
    # C is capped at 5% of equity after A's 1% fee (500); its own rate is 2%.
    assert decisions[1].notional == pytest.approx(0.05 * (1_000_000 - 500))
    end = b
    for d in decisions:
        end = apply_decision(end, d, fee_rate=rates[(d.order.symbol, d.order.side)])
    assert end.positions["BTC"] == 50_000.0
    assert end.cash == pytest.approx(900_000 + 50_000 * 0.99 - decisions[1].notional * 1.02)
