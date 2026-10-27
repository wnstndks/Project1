"""Portfolio coach pure module (app/strategy/coach.py, D-033): validation, fail-closed
behaviour, target construction, rebalance tolerance, patterns. Synthetic values only; the
hand-computed "answer" tests live in test_coach_math.py (written by someone else)."""

import math
import os
from dataclasses import asdict
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app.config import Settings, get_settings
from app.strategy import coach
from app.strategy.coach import (
    NO_PICK_NOTE_KO,
    PATTERN_LABELS_KO,
    VIOLATION_LABELS_KO,
    CashRecord,
    Exposure,
    HoldingView,
    MonthCount,
    Policy,
    TradeView,
    Weights,
    averaging_down_below_cut,
    beta,
    cap_class_weights,
    chasing_buys,
    choose_grid,
    concentration,
    construct_targets,
    correlation_table,
    exposure,
    krw_return_frame,
    monthly_trade_counts,
    overtrading,
    period_review,
    quick_rebuy_after_loss,
    rebalance_plan,
    required_annual_return_pct,
    risk_window,
    rule_lag,
    twr_index,
    violations,
    weights,
)
from app.strategy.risk import Book, RiskLimits

TODAY = date(2026, 10, 16)
# Wide limits isolate the target-construction rules from the symbol caps.
WIDE = RiskLimits(max_position_weight=1.0, max_order_fraction=1.0)
BANNED_WORDS = ("추천", "사세요", "파세요", "오를", "예상 수익")


@pytest.fixture
def clean_env(monkeypatch):
    """Settings built here never see backend/.env or the shell's AM_ variables (ISSUE-014)."""
    for key in list(os.environ):
        if key.upper().startswith("AM_"):
            monkeypatch.delenv(key)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def config(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def holding(
    symbol: str,
    asset_class: str = "stock",
    value: float = 100.0,
    target: float | None = None,
    currency: str = "USD",
    cost: float | None = None,
) -> HoldingView:
    return HoldingView(
        symbol=symbol,
        asset_class=asset_class,
        currency=currency,
        quantity=1.0,
        price=value,
        price_krw=value,
        value_krw=value,
        cost_basis_krw=value if cost is None else cost,
        target_pct=target,
    )


def trade(
    id: int,
    symbol: str,
    side: str,
    day: date,
    price: float,
    *,
    avg_before: float | None = None,
    qty_before: float = 0.0,
    quantity: float = 1.0,
    asset_class: str = "stock",
) -> TradeView:
    return TradeView(
        id=id,
        symbol=symbol,
        asset_class=asset_class,
        side=side,
        date=day,
        quantity=quantity,
        price=price,
        currency="USD",
        avg_cost_before=avg_before,
        qty_before=qty_before,
    )


def closes(values, start: date = date(2026, 1, 1), freq: str = "D") -> pd.Series:
    return pd.Series(
        [float(v) for v in values], index=pd.date_range(start, periods=len(values), freq=freq)
    )


def returns_frame(seed: int, rows: int, symbols: tuple[str, ...], scale: float = 0.01):
    rng = np.random.default_rng(seed)
    data = rng.normal(0.0, scale, size=(rows, len(symbols)))
    index = pd.bdate_range(date(2023, 1, 2), periods=rows)
    return pd.DataFrame(data, index=index, columns=list(symbols))


def policy(**kwargs) -> Policy:
    base = {"target_stock_pct": 80.0, "target_crypto_pct": 20.0, "target_cash_pct": 0.0}
    base.update(kwargs)
    return Policy(**base)


def text_of(obj) -> str:
    return " ".join(str(v) for v in asdict(obj).values())


# --- Policy --------------------------------------------------------------------------------


def test_policy_defaults_are_valid():
    p = Policy()
    assert p.target_stock_pct + p.target_crypto_pct + p.target_cash_pct == 100.0
    assert p.notes() == []


@pytest.mark.parametrize("stock,crypto,cash", [(80, 20, 5), (50, 20, 20), (0, 0, 0), (100, 1, 0)])
def test_policy_rejects_class_targets_not_summing_to_100(stock, crypto, cash):
    with pytest.raises(ValueError, match="add up to 100"):
        Policy(target_stock_pct=stock, target_crypto_pct=crypto, target_cash_pct=cash)


def test_policy_accepts_float_noise_in_the_sum():
    Policy(
        target_stock_pct=33.3333333,
        target_crypto_pct=33.3333333,
        target_cash_pct=33.3333334,
        max_crypto_weight_pct=40,
    )


def test_policy_rejects_crypto_target_above_crypto_cap():
    with pytest.raises(ValueError, match="max_crypto_weight_pct"):
        Policy(
            target_stock_pct=50, target_crypto_pct=40, target_cash_pct=10, max_crypto_weight_pct=30
        )


@pytest.mark.parametrize(
    "field",
    [
        "drawdown_tolerance_pct",
        "max_position_weight_pct",
        "max_crypto_weight_pct",
        "max_total_risk_pct",
        "rebalance_band_pt",
        "target_stock_pct",
        "monthly_contribution_krw",
        "goal_krw",
    ],
)
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_policy_rejects_non_finite_numbers(field, bad):
    with pytest.raises(ValueError):
        Policy(**{field: bad})


@pytest.mark.parametrize(
    "field",
    [
        "drawdown_tolerance_pct",
        "max_position_weight_pct",
        "max_crypto_weight_pct",
        "max_total_risk_pct",
    ],
)
@pytest.mark.parametrize("bad", [0, 100, -1, 150])
def test_policy_caps_must_be_strictly_between_0_and_100(field, bad):
    with pytest.raises(ValueError, match=r"\(0, 100\)"):
        Policy(**{field: bad})


def test_policy_crypto_cap_may_equal_the_crypto_target():
    p = Policy(
        target_stock_pct=70, target_crypto_pct=30, target_cash_pct=0, max_crypto_weight_pct=30
    )
    assert p.target_crypto_pct == p.max_crypto_weight_pct


@pytest.mark.parametrize("bad", [-1, 100, 250])
def test_policy_band_is_zero_or_more_and_below_100(bad):
    with pytest.raises(ValueError, match="rebalance_band_pt"):
        Policy(rebalance_band_pt=bad)
    assert Policy(rebalance_band_pt=0).rebalance_band_pt == 0.0


def test_policy_rejects_negative_contribution_and_non_positive_goal():
    with pytest.raises(ValueError, match="monthly_contribution_krw"):
        Policy(monthly_contribution_krw=-1)
    for bad in (0, -5):
        with pytest.raises(ValueError, match="goal_krw"):
            Policy(goal_krw=bad)


def test_policy_goal_date_checks_only_the_type():
    with pytest.raises(ValueError, match="goal_date"):
        Policy(goal_date="2030-01-01")
    assert Policy(goal_date=date(2020, 1, 1)).goal_date == date(2020, 1, 1)  # past: service's job


def test_policy_coerces_decimal_and_int_to_float():
    p = Policy(
        drawdown_tolerance_pct=Decimal("15"),
        target_stock_pct=Decimal("60"),
        target_crypto_pct=20,
        target_cash_pct=Decimal("20.0"),
        goal_krw=Decimal("5000000"),
    )
    assert isinstance(p.drawdown_tolerance_pct, float) and p.drawdown_tolerance_pct == 15.0
    assert isinstance(p.goal_krw, float)
    assert p.target_stock_pct + p.target_crypto_pct + p.target_cash_pct == 100.0


def test_policy_is_frozen():
    with pytest.raises(AttributeError):
        Policy().target_cash_pct = 5  # type: ignore[misc]


def test_from_config_maps_risk_limits_and_budgets(clean_env):
    p = Policy.from_config(config())
    assert p.max_position_weight_pct == 20.0
    assert p.drawdown_tolerance_pct == 20.0
    assert p.max_crypto_weight_pct == 30.0
    assert p.max_total_risk_pct == 8.0
    assert p.rebalance_band_pt == 5.0
    assert (p.target_stock_pct, p.target_crypto_pct, p.target_cash_pct) == (80.0, 20.0, 0.0)
    assert p.goal_krw is None and p.goal_date is None and p.monthly_contribution_krw == 0.0


def test_from_config_reads_coach_settings_and_leaves_cash_as_the_rest(clean_env):
    s = config(
        coach_max_crypto_weight_pct=Decimal("40"),
        coach_max_total_risk_pct=Decimal("5"),
        strategy_budget_stock=Decimal("0.5"),
        strategy_budget_crypto=Decimal("0.3"),
        rules_target_weight_gap_pt=Decimal("3"),
        risk_max_position_weight=Decimal("0.15"),
    )
    p = Policy.from_config(s)
    assert (p.max_crypto_weight_pct, p.max_total_risk_pct) == (40.0, 5.0)
    assert (p.target_stock_pct, p.target_crypto_pct) == (50.0, 30.0)
    assert p.target_cash_pct == pytest.approx(20.0)
    assert p.rebalance_band_pt == 3.0 and p.max_position_weight_pct == 15.0


def test_from_config_clamps_crypto_budget_to_the_crypto_cap(clean_env):
    # Limits bind, targets yield: a 50% crypto budget with a 30% cap gives a 30% target.
    s = config(strategy_budget_stock=Decimal("0.4"), strategy_budget_crypto=Decimal("0.5"))
    p = Policy.from_config(s)
    assert p.target_crypto_pct == 30.0
    assert p.target_cash_pct == pytest.approx(30.0)


def test_coach_settings_reject_out_of_range(clean_env):
    from pydantic import ValidationError

    for bad in ("0", "100", "-3"):
        with pytest.raises(ValidationError):
            config(coach_max_crypto_weight_pct=Decimal(bad))
        with pytest.raises(ValidationError):
            config(coach_max_total_risk_pct=Decimal(bad))


def test_limits_only_narrow_the_symbol_cap():
    base = RiskLimits(max_position_weight=0.20, max_index_fund_weight=0.80)
    narrow = policy(max_position_weight_pct=10).limits(base)
    assert narrow.max_position_weight == pytest.approx(0.10)
    assert narrow.max_index_fund_weight == 0.80  # SPY cap untouched (D-025)
    wide = policy(max_position_weight_pct=50).limits(base)
    assert wide.max_position_weight == 0.20  # never widened
    assert wide.max_drawdown == base.max_drawdown


def test_notes_flag_a_tolerance_looser_than_the_project_limit():
    assert policy(drawdown_tolerance_pct=20).notes() == []
    notes = policy(drawdown_tolerance_pct=35).notes()
    assert any("20%" in n and "느슨" in n for n in notes)


def test_notes_flag_a_goal_without_a_date_and_vice_versa():
    assert any("목표일" in n for n in policy(goal_krw=1_000_000).notes())
    assert any("목표일" in n for n in policy(goal_date=date(2030, 1, 1)).notes())
    assert policy(goal_krw=1_000_000, goal_date=date(2030, 1, 1)).notes() == []


# --- CashRecord ----------------------------------------------------------------------------


@pytest.mark.parametrize("krw,usd", [(-1, 0), (0, -1), (float("nan"), 0), (0, float("inf"))])
def test_cash_record_rejects_negative_or_non_finite(krw, usd):
    with pytest.raises(ValueError):
        CashRecord(krw=krw, usd=usd, as_of=TODAY)


def test_cash_record_total_and_staleness():
    c = CashRecord(krw=1_000, usd=2, as_of=TODAY - timedelta(days=31))
    assert c.total_krw(1_400) == 1_000 + 2 * 1_400
    with pytest.raises(ValueError):
        c.total_krw(0)
    assert c.stale(TODAY) is True
    assert CashRecord(krw=1, as_of=TODAY - timedelta(days=30)).stale(TODAY) is False
    assert CashRecord(krw=1).stale(TODAY) is False  # no date: "missing", not "stale"


# --- views fail closed -----------------------------------------------------------------------


def test_holding_view_rejects_nan_negative_and_bad_class():
    with pytest.raises(ValueError):
        holding("A", value=float("nan"))
    with pytest.raises(ValueError):
        holding("A", value=-1)
    with pytest.raises(ValueError, match="asset_class"):
        holding("A", asset_class="bond")
    with pytest.raises(ValueError, match="target_pct"):
        holding("A", target=120)


def test_trade_view_rejects_nan_negative_and_bad_side():
    with pytest.raises(ValueError):
        trade(1, "A", "buy", TODAY, 10.0, quantity=float("nan"))
    with pytest.raises(ValueError):
        trade(1, "A", "buy", TODAY, 10.0, quantity=-1)
    with pytest.raises(ValueError):
        trade(1, "A", "buy", TODAY, 10.0, qty_before=-1)
    with pytest.raises(ValueError, match="side"):
        trade(1, "A", "short", TODAY, 10.0)
    with pytest.raises(ValueError, match="date"):
        trade(1, "A", "buy", "2026-01-01", 10.0)  # type: ignore[arg-type]


# --- weights, concentration, exposure -----------------------------------------------------------


def test_weights_on_both_bases():
    hs = [holding("A", value=300), holding("B", "crypto", value=100, currency="KRW")]
    w = weights(hs, cash_krw=100)
    by = {x.symbol: x for x in w}
    assert by["A"].weight_pct == pytest.approx(60.0)
    assert by["A"].invested_weight_pct == pytest.approx(75.0)
    assert by["B"].weight_pct == pytest.approx(20.0)
    assert sum(x.weight_pct for x in w) == pytest.approx(80.0)  # the rest is cash
    assert sum(x.invested_weight_pct for x in w) == pytest.approx(100.0)


def test_weights_without_cash_use_the_invested_base():
    w = weights([holding("A", value=300), holding("B", value=100)], cash_krw=None)
    for x in w:
        assert x.weight_pct == x.invested_weight_pct


def test_weights_reject_duplicates_negative_cash_and_handle_empty():
    with pytest.raises(ValueError, match="twice"):
        weights([holding("A"), holding("A")], None)
    with pytest.raises(ValueError):
        weights([holding("A")], cash_krw=-1)
    assert weights([], cash_krw=None) == []
    assert weights([], cash_krw=100) == []


def test_concentration_structure():
    w = weights([holding("A", value=500), holding("B", value=300), holding("C", value=200)], None)
    c = concentration(w)
    assert c.count == 3 and c.top1_symbol == "A"
    assert c.top1_pct == pytest.approx(50.0) and c.top3_pct == pytest.approx(100.0)
    assert 1.0 <= c.effective_n <= c.count
    assert 1.0 / c.count <= c.hhi <= 1.0
    empty = concentration([])
    assert (empty.count, empty.top1_symbol, empty.hhi, empty.effective_n) == (0, None, 0.0, 0.0)


def test_concentration_of_one_holding_is_total():
    c = concentration(weights([holding("A", value=42)], None))
    assert c.hhi == pytest.approx(1.0) and c.effective_n == pytest.approx(1.0)


def test_exposure_shares_add_up_and_track_usd():
    hs = [
        holding("A", value=300),
        holding("B", "crypto", value=100, currency="KRW"),
        holding("C", "crypto", value=100, currency="USD"),
    ]
    e = exposure(hs, cash_krw=500)
    assert e.equity_krw == 1000 and e.invested_krw == 500
    assert e.stock_pct + e.crypto_pct + e.cash_pct == pytest.approx(100.0)
    assert e.usd_pct == pytest.approx(40.0)  # A and C
    no_cash = exposure(hs, cash_krw=None)
    assert no_cash.cash_pct is None
    assert no_cash.stock_pct + no_cash.crypto_pct == pytest.approx(100.0)


def test_exposure_of_nothing_is_zero():
    e = exposure([], cash_krw=None)
    assert (e.equity_krw, e.stock_pct, e.crypto_pct, e.usd_pct) == (0.0, 0.0, 0.0, 0.0)


# --- krw_return_frame --------------------------------------------------------------------------


def test_return_frame_fails_closed_on_empty_or_nan_input():
    fx = closes([1400.0] * 10)
    with pytest.raises(ValueError, match="empty"):
        krw_return_frame({}, fx, {}, "all")
    bad = closes([1, 2, float("nan"), 4])
    with pytest.raises(ValueError, match="missing"):
        krw_return_frame({"A": bad}, fx, {"A": "USD"}, "all")
    with pytest.raises(ValueError, match="fx"):
        krw_return_frame({"A": closes([1, 2, 3])}, pd.Series(dtype=float), {"A": "USD"}, "all")
    with pytest.raises(ValueError, match="currency"):
        krw_return_frame({"A": closes([1, 2, 3])}, fx, {}, "all")
    with pytest.raises(ValueError, match="asset_class"):
        krw_return_frame({"A": closes([1, 2, 3])}, fx, {"A": "USD"}, "stock")
    with pytest.raises(ValueError, match="no symbol is a stock"):
        krw_return_frame(
            {"A": closes([1, 2, 3])}, fx, {"A": "USD"}, "stock", asset_class={"A": "crypto"}
        )


def test_return_frame_converts_usd_with_the_rate_and_keeps_krw():
    days = pd.bdate_range(date(2026, 1, 5), periods=6)
    usd = pd.Series([10.0, 11.0, 11.0, 12.0, 12.0, 13.0], index=days)
    fx = pd.Series([1000.0, 1000.0, 1100.0, 1100.0, 1100.0, 1100.0], index=days)
    krw = pd.Series([100.0, 100.0, 90.0, 90.0, 99.0, 99.0], index=days)
    r = krw_return_frame({"A": usd, "K": krw}, fx, {"A": "USD", "K": "KRW"}, "all")
    assert list(r.columns) == ["A", "K"] and len(r) == 5  # first grid date dropped
    assert r["A"].iloc[0] == pytest.approx(0.10)  # price up, rate flat
    assert r["A"].iloc[1] == pytest.approx(0.10)  # price flat, rate up 10%
    assert r["K"].iloc[1] == pytest.approx(-0.10)  # KRW series used as it is


def test_return_frame_stock_grid_folds_the_weekend_into_monday():
    fri, sat, sun, mon = (date(2026, 1, 9) + timedelta(days=i) for i in range(4))
    stock = pd.Series([100.0, 101.0], index=pd.to_datetime([fri, mon]))
    coin = pd.Series([100.0, 110.0, 99.0, 120.0], index=pd.to_datetime([fri, sat, sun, mon]))
    fx = pd.Series([1000.0, 1000.0], index=pd.to_datetime([fri, mon]))
    r = krw_return_frame(
        {"S": stock, "C": coin},
        fx,
        {"S": "USD", "C": "USD"},
        "stock",
        asset_class={"S": "stock", "C": "crypto"},
    )
    assert [d.date() for d in r.index] == [mon]
    assert r.loc[pd.Timestamp(mon), "C"] == pytest.approx(0.20)
    everyday = krw_return_frame({"S": stock, "C": coin}, fx, {"S": "USD", "C": "USD"}, "all")
    assert len(everyday) == 3
    assert everyday["S"].isna().sum() == 0  # stock forward-filled over the weekend


def test_return_frame_short_history_is_nan_before_the_first_bar():
    days = pd.bdate_range(date(2026, 1, 5), periods=8)
    a = pd.Series(np.linspace(10, 17, 8), index=days)
    b = pd.Series([5.0, 6.0, 7.0], index=days[-3:])
    fx = pd.Series(1000.0, index=days)
    r = krw_return_frame({"A": a, "B": b}, fx, {"A": "USD", "B": "USD"}, "all")
    assert r["A"].notna().all()
    assert r["B"].isna().sum() == 5 and r["B"].notna().sum() == 2


def test_return_frame_accepts_date_indexes_and_explicit_grids():
    days = [date(2026, 1, 5) + timedelta(days=i) for i in range(5)]
    a = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], index=days)
    fx = pd.Series([1.0] * 5, index=days)
    r = krw_return_frame({"A": a}, fx, {"A": "KRW"}, days[::2])
    assert len(r) == 2 and r["A"].iloc[0] == pytest.approx(2.0)
    with pytest.raises(ValueError, match="fewer than two"):
        krw_return_frame({"A": a}, fx, {"A": "KRW"}, days[:1])


def test_choose_grid():
    assert choose_grid({"A": "stock", "B": "crypto"}) == ("stock", 252)
    assert choose_grid({"B": "crypto"}) == ("all", 365)
    assert choose_grid({}) == ("all", 365)


# --- risk_window -----------------------------------------------------------------------------


def test_risk_window_fails_closed_on_empty_frame_and_bad_numbers():
    frame = returns_frame(1, 300, ("A", "B"))
    with pytest.raises(ValueError, match="empty"):
        risk_window(pd.DataFrame(), {"A": 50}, 1000, name="1y", periods_per_year=252)
    with pytest.raises(ValueError, match="infinite"):
        bad = frame.copy()
        bad.iloc[3, 0] = np.inf
        risk_window(bad, {"A": 50, "B": 50}, 1000, name="1y", periods_per_year=252)
    with pytest.raises(ValueError, match="weights_pct"):
        risk_window(frame, {"A": float("nan")}, 1000, name="1y", periods_per_year=252)
    with pytest.raises(ValueError, match="equity_krw"):
        risk_window(frame, {"A": 50}, -1, name="1y", periods_per_year=252)
    with pytest.raises(ValueError, match="duplicate"):
        dup = pd.concat([frame, frame["A"]], axis=1)
        risk_window(dup, {"A": 50}, 1000, name="1y", periods_per_year=252)


def test_risk_window_usable_with_two_full_columns():
    frame = returns_frame(2, 300, ("A", "B"))
    w = risk_window(frame, {"A": 60, "B": 40}, 1_000_000, name="1y", periods_per_year=252)
    assert w.usable and w.reason is None
    assert w.method == "ledoit_wolf" and w.rows == 300
    assert w.included == ("A", "B") and w.excluded == ()
    assert w.coverage_pct == pytest.approx(100.0)
    assert w.annual_vol_pct > 0
    assert w.swing_1sigma_krw == pytest.approx(w.annual_vol_pct / 100 * 1_000_000)
    assert 0 <= w.max_drawdown_pct <= 100
    if w.peak_at_window_start:
        assert w.drawdown_peak is None and w.drawdown_trough is not None
    else:
        assert w.drawdown_peak <= w.drawdown_trough
    assert w.start == frame.index[0].date() and w.end == frame.index[-1].date()
    assert w.grid == "stock" and w.periods_per_year == 252


def test_risk_window_excludes_short_history_and_renormalises():
    frame = returns_frame(3, 300, ("A", "B"))
    frame.iloc[:250, 1] = np.nan  # B has 50 finite rows
    w = risk_window(frame, {"A": 80, "B": 20}, 1000, name="3y", periods_per_year=252)
    assert w.included == ("A",)
    assert [asdict(e) for e in w.excluded] == [{"symbol": "B", "bars": 50}]
    assert w.coverage_pct == pytest.approx(80.0)
    assert w.usable is True and w.method == "single"
    assert w.rows == 300  # A alone, all its rows
    only_a = risk_window(frame[["A"]], {"A": 100}, 1000, name="3y", periods_per_year=252)
    # A stands in for the whole invested part: same volatility as holding A alone.
    assert w.annual_vol_pct == pytest.approx(only_a.annual_vol_pct)


def test_risk_window_not_usable_below_min_coverage():
    frame = returns_frame(4, 300, ("A", "B"))
    frame.iloc[:250, 1] = np.nan
    w = risk_window(frame, {"A": 60, "B": 40}, 1000, name="3y", periods_per_year=252)
    assert w.coverage_pct == pytest.approx(60.0)
    assert w.usable is False
    assert w.reason is not None and "B" in w.reason and "75%" in w.reason
    assert w.annual_vol_pct > 0  # still reported, just flagged


def test_risk_window_identity_when_too_few_common_rows():
    frame = returns_frame(5, 300, ("A", "B"))
    frame.iloc[150:, 0] = np.nan  # A: rows 0..149
    frame.iloc[:100, 1] = np.nan  # B: rows 100..299, overlap 50
    w = risk_window(frame, {"A": 50, "B": 50}, 1000, name="3y", periods_per_year=252)
    assert w.included == ("A", "B") and w.excluded == ()
    assert w.rows == 50 and w.method == "identity"
    assert w.usable is False and "겹치는" in w.reason


def test_risk_window_without_weights_or_history():
    frame = returns_frame(6, 300, ("A",))
    none = risk_window(frame, {"A": 0}, 1000, name="1y", periods_per_year=252)
    assert none.usable is False and none.reason == "보유 종목이 없습니다"
    assert none.method == "none" and none.rows == 0
    unknown = risk_window(frame, {"Z": 100}, 1000, name="1y", periods_per_year=365)
    assert unknown.usable is False and unknown.excluded[0].bars == 0
    assert unknown.grid == "all"


def test_risk_window_cash_share_earns_zero():
    frame = returns_frame(7, 300, ("A",))
    full = risk_window(frame, {"A": 100}, 1000, name="1y", periods_per_year=252)
    half = risk_window(frame, {"A": 50}, 1000, name="1y", periods_per_year=252)
    assert half.annual_vol_pct == pytest.approx(full.annual_vol_pct / 2)
    assert half.max_drawdown_pct < full.max_drawdown_pct


def one_symbol_returns(prices: list[float]):
    days = pd.bdate_range(date(2026, 3, 2), periods=len(prices))
    series = pd.Series(prices, index=days, dtype=float)
    return (series / series.shift(1) - 1).iloc[1:].to_frame("A"), days


def test_risk_window_peak_at_window_start_has_a_flag_and_no_date():
    # The fall starts from the bar before the first return, which the frame does not hold.
    frame, days = one_symbol_returns([100.0, 80.0, 85.0])
    w = risk_window(frame, {"A": 100}, 1000, name="t", periods_per_year=252, min_rows=2)
    assert w.max_drawdown_pct > 0
    assert w.peak_at_window_start is True and w.drawdown_peak is None
    assert w.drawdown_trough == days[1].date() == w.start
    assert asdict(w)["peak_at_window_start"] is True


def test_risk_window_peak_inside_the_window_is_dated():
    frame, days = one_symbol_returns([100.0, 130.0, 91.0, 120.0])
    w = risk_window(frame, {"A": 100}, 1000, name="t", periods_per_year=252, min_rows=2)
    assert w.peak_at_window_start is False
    assert w.drawdown_peak == days[1].date() and w.drawdown_trough == days[2].date()
    assert w.drawdown_peak < w.drawdown_trough
    rising, _ = one_symbol_returns([100.0, 110.0, 120.0])
    flat = risk_window(rising, {"A": 100}, 1000, name="t", periods_per_year=252, min_rows=2)
    assert flat.max_drawdown_pct == 0.0
    assert (flat.drawdown_peak, flat.drawdown_trough, flat.peak_at_window_start) == (
        None,
        None,
        False,
    )


def test_risk_window_serialises_with_asdict():
    frame = returns_frame(8, 200, ("A", "B"))
    w = risk_window(frame, {"A": 50, "B": 50}, 1000, name="1y", periods_per_year=252)
    d = asdict(w)
    assert set(d) >= {"name", "annual_vol_pct", "max_drawdown_pct", "coverage_pct", "usable"}
    assert d["excluded"] == () and d["included"] == ("A", "B")  # asdict keeps tuples


# --- correlation_table, beta -------------------------------------------------------------------


def test_correlation_table_structure_and_exclusion():
    frame = returns_frame(9, 300, ("A", "B", "C"))
    frame.iloc[:250, 2] = np.nan
    t = correlation_table(frame)
    assert t.symbols == ("A", "B") and t.excluded == ("C",)
    assert t.method == "ledoit_wolf" and t.rows == 300
    m = np.array(t.matrix)
    assert m.shape == (2, 2)
    assert np.allclose(np.diag(m), 1.0) and np.allclose(m, m.T)
    assert correlation_table(frame[["C"]]).method == "none"
    assert correlation_table(frame[["A"]]).method == "single"


def test_beta_none_when_short_or_flat_and_structure_otherwise():
    x = returns_frame(10, 200, ("X",))["X"]
    y = 1.5 * x + returns_frame(11, 200, ("N",))["N"] * 0.1
    assert beta(y.iloc[:30], x.iloc[:30]) is None
    assert beta(y, pd.Series(0.0, index=x.index)) is None
    for level in (0.01, 0.3):
        # A constant benchmark: var(ddof=1) is ~1e-36, not exactly 0, and must still be "flat".
        assert beta(y, pd.Series(level, index=x.index)) is None
    b = beta(y, x)
    assert b is not None and b.rows == 200 and 0.0 <= b.r2 <= 1.0 and b.beta > 0
    shifted = beta(y, x.iloc[100:])
    assert shifted is not None and shifted.rows == 100  # common dates only
    with pytest.raises(ValueError):
        beta(y.replace(y.iloc[0], np.inf), x)


# --- twr_index, period_review -------------------------------------------------------------------


def test_twr_index_starts_at_one_and_ignores_deposits():
    days = pd.date_range(date(2026, 1, 1), periods=3)
    idx = twr_index(
        pd.Series([100.0, 200.0, 220.0], index=days), pd.Series([0, 100, 0], index=days)
    )
    assert idx.iloc[0] == 1.0
    assert idx.iloc[1] == pytest.approx(1.0)  # the day's change was all deposit
    assert idx.iloc[2] == pytest.approx(1.10)


def test_twr_index_aligns_flows_by_date_and_handles_zero_value():
    days = pd.date_range(date(2026, 1, 1), periods=3)
    flows = pd.Series([50.0], index=[date(2026, 1, 2)])  # plain dates, values by Timestamp
    idx = twr_index(pd.Series([0.0, 50.0, 55.0], index=days), flows)
    assert idx.iloc[1] == pytest.approx(1.0)  # previous value 0: return counted as 0
    assert idx.iloc[2] == pytest.approx(1.10)
    assert twr_index(pd.Series([100.0, 90.0], index=days[:2])).iloc[-1] == pytest.approx(0.9)


def test_twr_index_fails_closed():
    days = pd.date_range(date(2026, 1, 1), periods=2)
    with pytest.raises(ValueError):
        twr_index(pd.Series([100.0, np.nan], index=days))
    with pytest.raises(ValueError, match="empty"):
        twr_index(pd.Series(dtype=float))
    with pytest.raises(ValueError, match="flows"):
        twr_index(pd.Series([1.0, 2.0], index=days), pd.Series([np.nan, 0.0], index=days))


def test_twr_index_fails_closed_when_a_day_would_take_the_index_to_or_below_zero():
    # N-COACH-1: a deposit larger than the day's value (an imported trade priced orders of
    # magnitude too high) used to give a negative index and a drawdown of many thousand %.
    days = pd.date_range(date(2026, 1, 1), periods=3)
    with pytest.raises(ValueError, match="2026-01-02") as info:
        twr_index(pd.Series([100.0, 50.0, 60.0], index=days), pd.Series([0, 200, 0], index=days))
    message = str(info.value)
    assert message.startswith("2026-01-02: ")
    assert "-100%" in message and "거래 페이지" in message
    # Exactly −100% (the value equals the deposit) is refused as well ...
    with pytest.raises(ValueError, match="2026-01-02"):
        twr_index(pd.Series([100.0, 200.0, 60.0], index=days), pd.Series([0, 200, 0], index=days))
    # ... while a hair above it is a (terrible but finite) return, and the date is the first
    # offending day, not the last.
    idx = twr_index(pd.Series([100.0, 201.0, 60.0], index=days), pd.Series([0, 200, 0], index=days))
    assert idx.iloc[1] == pytest.approx(0.01) and idx.iloc[2] == pytest.approx(0.01 * 60 / 201)
    with pytest.raises(ValueError, match="2026-01-03"):
        twr_index(pd.Series([100.0, 90.0, 10.0], index=days), pd.Series([0, 0, 20], index=days))
    # A negative value cannot come from the ledger: refused with its date.
    with pytest.raises(ValueError, match="2026-01-01") as neg:
        twr_index(pd.Series([-1.0, 90.0], index=days[:2]))
    assert "음수" in str(neg.value)
    # A zero value means nothing was held: the curve starts again and the day counts as 0.
    idx = twr_index(
        pd.Series([100.0, 0.0, 50.0, 55.0], index=pd.date_range(date(2026, 1, 1), periods=4)),
        pd.Series([0, -100, 50, 0], index=pd.date_range(date(2026, 1, 1), periods=4)),
    )
    assert idx.tolist() == pytest.approx([1.0, 1.0, 1.0, 1.1])


def test_period_review_splits_change_into_contributions_and_market():
    days = [date(2026, 2, 27), date(2026, 3, 5), date(2026, 3, 20), date(2026, 3, 31)]
    history = pd.Series([1000.0, 1500.0, 1450.0, 1600.0], index=days)
    flows = pd.Series([1000.0, 500.0, 0.0, 0.0], index=days)
    r = period_review(history, flows, date(2026, 2, 28), date(2026, 3, 31))
    assert r.start_point == date(2026, 2, 27) and r.end_point == date(2026, 3, 31)
    assert r.start_value_krw == 1000.0 and r.end_value_krw == 1600.0
    assert r.contributions_krw == 500.0  # the 2/27 flow is before (start, end]
    assert r.change_krw == 600.0 and r.market_pnl_krw == 100.0


def test_period_review_first_month_counts_the_first_buy_as_contribution():
    days = [date(2026, 3, 5), date(2026, 3, 31)]
    history = pd.Series([1000.0, 1100.0], index=pd.to_datetime(days))
    flows = pd.Series([1000.0, 0.0], index=days)
    r = period_review(history, flows, date(2026, 2, 28), date(2026, 3, 31))
    assert r.start_point is None and r.start_value_krw == 0.0
    assert r.contributions_krw == 1000.0 and r.market_pnl_krw == pytest.approx(100.0)


def test_period_review_fails_closed():
    history = pd.Series([1.0], index=[date(2026, 3, 5)])
    with pytest.raises(ValueError, match="empty"):
        period_review(pd.Series(dtype=float), None, date(2026, 1, 1), date(2026, 1, 31))
    with pytest.raises(ValueError, match="before"):
        period_review(history, None, date(2026, 3, 31), date(2026, 3, 1))
    with pytest.raises(ValueError, match="no point"):
        period_review(history, None, date(2026, 1, 1), date(2026, 1, 31))
    with pytest.raises(ValueError):
        period_review(
            pd.Series([np.nan], index=[date(2026, 3, 5)]), None, date(2026, 3, 1), date(2026, 3, 31)
        )


# --- cap_class_weights, construct_targets -------------------------------------------------------


def test_cap_class_weights_scales_only_the_class_over_its_cap():
    target = {"A": 0.5, "B": 0.3, "C": 0.2}
    cls = {"A": "stock", "B": "crypto", "C": "crypto"}
    out = cap_class_weights(target, cls, {"crypto": 0.3})
    assert out["A"] == 0.5
    assert out["B"] + out["C"] == pytest.approx(0.3)
    assert out["B"] / out["C"] == pytest.approx(1.5)  # proportions kept
    assert cap_class_weights(target, cls, {"crypto": 0.6}) == target
    assert cap_class_weights(target, cls, {}) == target


def test_cap_class_weights_fails_closed():
    with pytest.raises(ValueError, match="asset_class"):
        cap_class_weights({"A": 0.5}, {}, {"crypto": 0.3})
    with pytest.raises(ValueError):
        cap_class_weights({"A": float("nan")}, {"A": "stock"}, {})
    with pytest.raises(ValueError):
        cap_class_weights({"A": 0.5}, {"A": "crypto"}, {"crypto": -0.1})


def test_targets_explicit_plus_remainder_split_by_current_value():
    hs = [holding("A", value=100, target=15), holding("B", value=300), holding("C", value=100)]
    plan = construct_targets(
        hs,
        policy(target_stock_pct=80, target_crypto_pct=0, target_cash_pct=20),
        WIDE,
        cash_known=True,
    )
    assert plan.targets["A"] == pytest.approx(0.15)
    assert plan.targets["B"] + plan.targets["C"] == pytest.approx(0.65)
    assert plan.targets["B"] == pytest.approx(0.65 * 0.75)
    assert plan.source == {"A": "symbol", "B": "remainder", "C": "remainder"}
    assert plan.unallocated_pct == 0.0 and plan.capped == ()
    assert plan.class_targets == {"stock": 80.0, "crypto": 0.0, "cash": 20.0}


def test_targets_explicit_over_class_are_scaled_down_with_a_note():
    hs = [holding("A", target=50), holding("B", target=50), holding("C")]
    plan = construct_targets(
        hs,
        policy(target_stock_pct=80, target_crypto_pct=0, target_cash_pct=20),
        WIDE,
        cash_known=True,
    )
    assert plan.targets["A"] == pytest.approx(0.40) and plan.targets["B"] == pytest.approx(0.40)
    assert plan.targets["C"] == 0.0
    assert plan.source == {"A": "scaled", "B": "scaled", "C": "remainder"}
    assert any("넘어" in n for n in plan.notes)
    # N-COACH-9: C ends at 0% (a rebalance would close it), and the note says which symbols.
    note = next(n for n in plan.notes if "목표 0%" in n)
    assert "주식" in note and "1개(C)" in note


def test_targets_remainder_zero_when_explicit_targets_fill_the_class_is_noted():
    # Explicit targets add up to exactly the class target: the symbol without one gets 0.
    hs = [holding("A", target=50), holding("B", target=30), holding("C", value=400)]
    pol = policy(target_stock_pct=80, target_crypto_pct=0, target_cash_pct=20)
    plan = construct_targets(hs, pol, WIDE, cash_known=True)
    assert plan.targets == pytest.approx({"A": 0.5, "B": 0.3, "C": 0.0})
    assert plan.source == {"A": "symbol", "B": "symbol", "C": "remainder"}
    note = next(n for n in plan.notes if "목표 0%" in n)
    assert "주식" in note and "1개(C)" in note
    assert set(plan.targets) == {"A", "B", "C"}  # still no new symbol
    # Several symbols are listed together; a positive remainder gets no such note.
    many = construct_targets(
        [holding("A", target=60), holding("B", target=30), holding("C"), holding("D")],
        pol,
        WIDE,
        cash_known=True,
    )
    assert "2개(C, D)" in next(n for n in many.notes if "목표 0%" in n)
    some = construct_targets([holding("A", target=50), holding("C")], pol, WIDE, cash_known=True)
    assert some.targets["C"] == pytest.approx(0.30)
    assert not any("목표 0%" in n for n in some.notes)


def test_targets_explicit_under_class_without_remainder_are_scaled_up_with_a_note():
    hs = [holding("A", target=15), holding("B", target=15)]
    plan = construct_targets(
        hs,
        policy(target_stock_pct=80, target_crypto_pct=0, target_cash_pct=20),
        WIDE,
        cash_known=True,
    )
    assert plan.targets == pytest.approx({"A": 0.40, "B": 0.40})
    assert plan.source == {"A": "scaled", "B": "scaled"}
    assert any("못 미쳐" in n for n in plan.notes)


def test_targets_matching_explicit_are_taken_as_written():
    hs = [holding("A", target=50), holding("B", target=30)]
    plan = construct_targets(
        hs,
        policy(target_stock_pct=80, target_crypto_pct=0, target_cash_pct=20),
        WIDE,
        cash_known=True,
    )
    assert plan.targets == pytest.approx({"A": 0.5, "B": 0.3})
    assert plan.source == {"A": "symbol", "B": "symbol"} and plan.notes == ()


def test_targets_class_zero_closes_the_class_and_rebalance_sells_it_all():
    hs = [holding("A", value=800), holding("X", "crypto", value=200, currency="KRW")]
    pol = policy(target_stock_pct=80, target_crypto_pct=0, target_cash_pct=20)
    plan = construct_targets(hs, pol, WIDE, cash_known=True)
    assert plan.targets["X"] == 0.0 and plan.source["X"] == "class_zero"
    book = Book(cash=0.0, positions={"A": 800.0, "X": 200.0})
    orders = rebalance_plan(book, plan, WIDE, band_pt=5)
    sells = [d for d in orders if d.order.side == "sell"]
    assert [(d.order.symbol, d.notional, d.status) for d in sells] == [("X", 200.0, "accepted")]


def test_targets_class_without_holdings_is_unallocated_and_names_no_symbol():
    hs = [holding("X", "crypto", value=100, currency="KRW")]
    plan = construct_targets(
        hs,
        policy(target_stock_pct=70, target_crypto_pct=30, target_cash_pct=0),
        WIDE,
        cash_known=True,
    )
    assert plan.unallocated_pct == pytest.approx(70.0)
    assert plan.targets == pytest.approx({"X": 0.30})
    assert any(NO_PICK_NOTE_KO in n for n in plan.notes)
    assert set(plan.targets) == {"X"}  # no new symbol


def test_targets_apply_symbol_and_crypto_caps_and_sum_to_at_most_one():
    hs = [
        holding("A", value=500),
        holding("X", "crypto", value=125, currency="KRW"),
        holding("Y", "crypto", value=125, currency="KRW"),
    ]
    pol = policy(
        target_stock_pct=50, target_crypto_pct=25, target_cash_pct=25, max_crypto_weight_pct=30
    )
    # Cash unknown: 50/25 renormalise to 66.7/33.3 of the invested amount, so the crypto cap
    # (30%) binds on the class and the symbol cap (20%) on the single stock.
    plan = construct_targets(hs, pol, RiskLimits(max_position_weight=0.20), cash_known=False)
    assert plan.class_targets["cash"] is None
    assert plan.class_targets["crypto"] == pytest.approx(100 / 3)
    assert plan.targets["X"] == pytest.approx(0.15) and plan.targets["Y"] == pytest.approx(0.15)
    assert plan.targets["A"] == pytest.approx(0.20)
    assert set(plan.capped) == {"A", "X", "Y"}
    assert sum(plan.targets.values()) == pytest.approx(0.50)
    assert any("50.0%p가 현금으로 남습니다" in n for n in plan.notes)
    assert coach.CASH_UNKNOWN_TARGET_NOTE_KO in plan.notes


def test_targets_all_explicit_zero_leaves_class_unallocated():
    hs = [holding("A", target=0), holding("B", target=0)]
    plan = construct_targets(
        hs,
        policy(target_stock_pct=80, target_crypto_pct=0, target_cash_pct=20),
        WIDE,
        cash_known=True,
    )
    assert plan.targets == {"A": 0.0, "B": 0.0}
    assert plan.unallocated_pct == pytest.approx(80.0)


@pytest.mark.parametrize("seed", range(6))
def test_targets_never_exceed_one_or_a_cap(seed):
    rng = np.random.default_rng(seed)
    hs = []
    for i in range(int(rng.integers(1, 7))):
        cls = "stock" if rng.random() < 0.6 else "crypto"
        target = float(rng.integers(0, 60)) if rng.random() < 0.5 else None
        hs.append(holding(f"S{i}", cls, value=float(rng.integers(1, 1000)), target=target))
    crypto = float(rng.integers(0, 31))
    stock = float(rng.integers(0, int(100 - crypto) + 1))
    pol = policy(
        target_stock_pct=stock, target_crypto_pct=crypto, target_cash_pct=100 - stock - crypto
    )
    limits = RiskLimits(max_position_weight=0.20)
    plan = construct_targets(hs, pol, limits, cash_known=bool(rng.integers(0, 2)))
    assert sum(plan.targets.values()) <= 1.0 + 1e-9
    assert all(w <= 0.20 + 1e-9 for w in plan.targets.values())
    crypto_total = sum(
        w
        for s, w in plan.targets.items()
        if s in {h.symbol for h in hs if h.asset_class == "crypto"}
    )
    assert crypto_total <= pol.max_crypto_weight_pct / 100 + 1e-9
    assert set(plan.targets) == {h.symbol for h in hs}
    assert set(plan.source.values()) <= {"symbol", "remainder", "scaled", "class_zero"}


def test_targets_reject_duplicate_holdings():
    with pytest.raises(ValueError, match="twice"):
        construct_targets([holding("A"), holding("A")], policy(), WIDE, cash_known=True)


# --- rebalance_plan ------------------------------------------------------------------------------


def two_stock_plan():
    hs = [holding("A", target=50), holding("B", target=50)]
    return construct_targets(
        hs,
        policy(target_stock_pct=100, target_crypto_pct=0, target_cash_pct=0),
        WIDE,
        cash_known=True,
    )


def test_rebalance_drift_inside_the_band_means_no_orders():
    plan = two_stock_plan()
    assert rebalance_plan(Book(0.0, {"A": 54.0, "B": 46.0}), plan, WIDE, band_pt=5) == []


def test_rebalance_drift_beyond_the_band_sells_first_then_buys():
    plan = two_stock_plan()
    orders = rebalance_plan(Book(0.0, {"A": 56.0, "B": 44.0}), plan, WIDE, band_pt=5)
    assert [(d.order.symbol, d.order.side) for d in orders] == [("A", "sell"), ("B", "buy")]
    assert orders[0].notional == pytest.approx(6.0) and orders[1].notional == pytest.approx(6.0)
    assert all(d.status == "accepted" for d in orders)


def test_rebalance_without_cash_funds_buys_from_sales_only():
    hs = [holding("A", target=40), holding("B", target=40), holding("C", target=20)]
    plan = construct_targets(
        hs,
        policy(target_stock_pct=100, target_crypto_pct=0, target_cash_pct=0),
        WIDE,
        cash_known=False,
    )
    # The two small overweights sit inside the band, so nothing is sold and the buy has no cash.
    orders = rebalance_plan(Book(0.0, {"A": 44.0, "B": 44.0, "C": 12.0}), plan, WIDE, band_pt=5)
    assert [(d.order.symbol, d.order.side, d.status) for d in orders] == [("C", "buy", "rejected")]
    assert "cash" in orders[0].reasons
    funded = rebalance_plan(Book(10.0, {"A": 44.0, "B": 44.0, "C": 12.0}), plan, WIDE, band_pt=5)
    assert funded[0].status == "accepted" and funded[0].notional == pytest.approx(10.0)


def test_rebalance_band_zero_trades_every_difference_and_rejects_bad_band():
    plan = two_stock_plan()
    orders = rebalance_plan(Book(0.0, {"A": 50.5, "B": 49.5}), plan, WIDE, band_pt=0)
    assert len(orders) == 2
    with pytest.raises(ValueError):
        rebalance_plan(Book(0.0, {"A": 50.0, "B": 50.0}), plan, WIDE, band_pt=-1)


# --- violations ----------------------------------------------------------------------------------


def w_of(
    symbol: str, pct: float, asset_class: str = "stock", target: float | None = None
) -> Weights:
    return Weights(symbol, asset_class, "USD", pct, pct, pct, target)


def expo(stock: float, crypto: float, cash: float | None, usd: float = 0.0) -> Exposure:
    return Exposure(100.0, stock + crypto, stock, crypto, cash, usd)


def codes(found) -> list[str]:
    return [v.code for v in found]


def check(**overrides):
    args = {
        "policy": policy(target_stock_pct=70, target_crypto_pct=20, target_cash_pct=10),
        "weights": [w_of("A", 20), w_of("B", 20), w_of("X", 20, "crypto")],
        "exposure": expo(70, 20, 10),  # exactly on target: no class drift by default
        "risk3y": None,
        "total_risk_pct": None,
        "cash": CashRecord(krw=400, as_of=TODAY),
        "today": TODAY,
        "kill_tripped": False,
        "limits": RiskLimits(max_position_weight=0.20),
    }
    args.update(overrides)
    return violations(**args)


def test_violations_position_over_cap_only_above_the_cap():
    found = check(weights=[w_of("A", 20), w_of("B", 20.5)])
    assert codes(found) == ["position_over_cap"]  # A sits exactly on the cap
    over = found[0]
    assert over.subject == "B" and over.severity == "warn"
    assert over.value == 20.5 and over.limit == 20.0
    assert over.label_ko == VIOLATION_LABELS_KO["position_over_cap"] and "B" in over.detail


def test_violations_index_fund_uses_its_own_cap():
    found = check(weights=[w_of("SPY", 60)], exposure=expo(60, 0, 40))
    assert "position_over_cap" not in codes(found)


def test_violations_crypto_over_cap_and_class_drift():
    found = check(exposure=expo(40, 35, 25))
    assert "crypto_over_cap" in codes(found)
    drift = [v for v in found if v.code == "class_drift"]
    assert {v.subject for v in drift} == {"stock", "crypto", "cash"}
    assert all(v.value is not None and v.limit is not None for v in drift)
    quiet = check(exposure=expo(72, 18, 10))
    assert codes(quiet) == []


def test_violations_class_drift_without_cash_uses_the_invested_base():
    # Targets 70/20/10 become 77.8/22.2 of the invested amount; 78/22 is inside the band.
    found = check(cash=None, exposure=expo(78, 22, None))
    assert codes(found) == ["cash_missing"]
    assert found[0].severity == "info"


def test_violations_drawdown_only_when_usable():
    frame = returns_frame(12, 300, ("A",))
    window = risk_window(frame, {"A": 100}, 1000, name="3y", periods_per_year=252)
    deep = coach.RiskWindow(**{**asdict(window), "max_drawdown_pct": 33.0, "excluded": ()})
    found = check(risk3y=deep)
    assert "drawdown_over_tolerance" in codes(found)
    v = next(x for x in found if x.code == "drawdown_over_tolerance")
    assert v.value == 33.0 and v.limit == 20.0
    # N-COACH-7: the sentence carries the Korean label, the subject keeps the window code.
    assert "지난 3년을" in v.detail and "3y" not in v.detail and v.subject == "3y"
    unusable = coach.RiskWindow(**{**asdict(deep), "usable": False})
    assert "drawdown_over_tolerance" not in codes(check(risk3y=unusable))


def test_window_label_ko_maps_known_names_and_keeps_the_rest():
    assert coach.window_label_ko("1y") == "1년" and coach.window_label_ko("3y") == "3년"
    assert coach.window_label_ko("6m") == "6m"
    assert coach.WINDOW_LABELS_KO == {"1y": "1년", "3y": "3년"}


def test_violations_total_risk_cash_stale_targets_and_kill_switch():
    found = check(
        total_risk_pct=9.5,
        cash=CashRecord(krw=1, as_of=TODAY - timedelta(days=45)),
        kill_tripped=True,
        weights=[w_of("A", 20, target=50), w_of("B", 20, target=30), w_of("X", 20, "crypto")],
    )
    assert codes(found) == [
        "total_risk_over_cap",
        "cash_stale",
        "targets_exceed_class",
        "kill_switch_tripped",
    ]
    by = {v.code: v for v in found}
    assert by["total_risk_over_cap"].severity == "warn" and by["total_risk_over_cap"].limit == 8.0
    assert by["cash_stale"].value == 45.0 and by["cash_stale"].severity == "info"
    assert by["targets_exceed_class"].value == 80.0 and by["targets_exceed_class"].limit == 70.0
    assert by["kill_switch_tripped"].severity == "info"
    assert "total_risk_over_cap" not in codes(check(total_risk_pct=8.0))


def test_violations_wording_avoids_advice_words():
    found = check(
        exposure=expo(40, 35, 25),
        total_risk_pct=9.5,
        kill_tripped=True,
        weights=[w_of("B", 30, target=90)],
    )
    text = " ".join(text_of(v) for v in found) + " ".join(VIOLATION_LABELS_KO.values())
    for word in BANNED_WORDS:
        assert word not in text
    assert all(v.severity in ("warn", "info") for v in found)
    assert set(VIOLATION_LABELS_KO) >= set(codes(found))


def test_violations_fail_closed_on_bad_total_risk():
    with pytest.raises(ValueError):
        check(total_risk_pct=float("nan"))


# --- required_annual_return_pct -----------------------------------------------------------------


def test_required_return_none_when_not_needed_or_impossible():
    assert required_annual_return_pct(2_000, 0, 1_000, 10) is None  # already there
    assert required_annual_return_pct(1_000, 100, 2_000, 1) is None  # contributions alone do it
    assert required_annual_return_pct(1_000, 0, 2_000, 0) is None  # no time
    assert required_annual_return_pct(1_000, 0, 1e12, 3) is None  # not even at +100%/yr


def test_required_return_solves_the_equation_and_falls_with_contributions():
    r = required_annual_return_pct(1_000, 0, 3_000, 5)
    assert r is not None and 0 < r < 100
    assert 1_000 * (1 + r / 100) ** 5 == pytest.approx(3_000, rel=1e-9)
    with_saving = required_annual_return_pct(1_000, 10, 3_000, 5)
    assert with_saving is not None and with_saving < r
    n, m = 5, 10.0
    growth = (1 + with_saving / 100) ** n
    annuity = 12 * m * (growth - 1) / (with_saving / 100)
    assert 1_000 * growth + annuity == pytest.approx(3_000, rel=1e-9)


def test_required_return_fails_closed():
    for args in [
        (float("nan"), 0, 1, 1),
        (-1, 0, 1, 1),
        (1, -1, 1, 1),
        (1, 0, 0, 1),
        (1, 0, 1, float("nan")),
    ]:
        with pytest.raises(ValueError):
            required_annual_return_pct(*args)


# --- patterns -----------------------------------------------------------------------------------


def test_chasing_buys_flags_run_ups_and_counts_skips():
    start = date(2026, 1, 1)
    rising = closes(np.linspace(100, 125, 30), start)  # +25% over the window
    flat = closes([100.0] * 30, start)
    buy_day = start + timedelta(days=30)
    trades = [
        trade(1, "UP", "buy", buy_day, 125.0),
        trade(2, "FLAT", "buy", buy_day, 100.0),
        trade(3, "NOBARS", "buy", buy_day, 1.0),
        trade(4, "UP", "sell", buy_day, 125.0),
        trade(5, "UP", "buy", start + timedelta(days=5), 100.0),  # too few bars before it
    ]
    flags, skipped = chasing_buys(
        trades, {"UP": rising, "FLAT": flat}, lookback=20, threshold_pct=15
    )
    assert [f.trade_id for f in flags] == [1]
    assert flags[0].code == "chasing_buy" and flags[0].label_ko == PATTERN_LABELS_KO["chasing_buy"]
    assert flags[0].value is not None and flags[0].value > 15
    assert skipped == 2
    assert chasing_buys(trades, {"UP": rising, "FLAT": flat}, threshold_pct=40)[0] == []


def test_chasing_buys_uses_only_bars_before_the_trade_date():
    start = date(2026, 1, 1)
    # Flat until the buy date, then a jump: nothing before the buy says "run-up".
    series = closes([100.0] * 25 + [200.0] * 5, start)
    buy_day = start + timedelta(days=25)
    flags, skipped = chasing_buys([trade(1, "A", "buy", buy_day, 200.0)], {"A": series})
    assert flags == [] and skipped == 0


def test_chasing_buys_fails_closed_on_nan_closes_and_bad_lookback():
    series = closes([100.0, float("nan"), 101.0])
    with pytest.raises(ValueError):
        chasing_buys([trade(1, "A", "buy", TODAY, 1.0)], {"A": series})
    with pytest.raises(ValueError):
        chasing_buys([], {}, lookback=0)


def test_averaging_down_below_cut():
    cut = {"stock": 15.0, "crypto": 25.0}
    trades = [
        trade(1, "A", "buy", TODAY, 80.0, avg_before=100.0, qty_before=10),  # 85 is the line
        trade(2, "A", "buy", TODAY, 90.0, avg_before=100.0, qty_before=10),
        trade(3, "A", "buy", TODAY, 80.0, avg_before=None, qty_before=0),  # first buy
        trade(4, "X", "buy", TODAY, 76.0, avg_before=100.0, qty_before=1, asset_class="crypto"),
        trade(5, "X", "buy", TODAY, 75.0, avg_before=100.0, qty_before=1, asset_class="crypto"),
        trade(6, "A", "sell", TODAY, 50.0, avg_before=100.0, qty_before=10),
    ]
    flags = averaging_down_below_cut(trades, lambda symbol, cls: cut[cls])
    assert [f.trade_id for f in flags] == [1, 5]
    assert flags[0].value == pytest.approx(-20.0) and "−15%" in flags[0].detail
    with pytest.raises(ValueError):
        averaging_down_below_cut(trades, lambda s, c: float("nan"))


def test_rule_lag_counts_consecutive_closes_at_or_below_the_stop():
    start = date(2026, 1, 1)
    below = closes([100.0] * 10 + [84.0] * 6, start)  # stop at 85 with cut 15
    brief = closes([100.0] * 13 + [84.0] * 3, start)
    flags = rule_lag(
        [("A", 100.0, 15.0), ("B", 100.0, 15.0), ("Z", 100.0, 15.0)], {"A": below, "B": brief}
    )
    assert len(flags) == 1
    f = flags[0]
    assert f.symbol == "A" and f.days == 6 and f.cut_price == pytest.approx(85.0)
    assert f.since == start + timedelta(days=10) and f.last_close == 84.0
    assert f.since_window_start is False  # the run started inside the bars passed in
    assert rule_lag([("B", 100.0, 15.0)], {"B": brief}, min_days=3)[0].days == 3
    with pytest.raises(ValueError):
        rule_lag([("A", float("nan"), 15.0)], {"A": below})


def test_rule_lag_marks_a_run_that_was_already_under_way_at_the_first_bar():
    # N-COACH-6: when every bar is at or below the stop, `since`/`days` are only the start
    # and length of the range looked at, and the flag says so (the UI shows "N일 이상").
    start = date(2026, 1, 1)
    all_below = closes([84.0] * 6, start)
    from_middle = closes([100.0] * 3 + [84.0] * 6, start)
    flags = rule_lag([("A", 100.0, 15.0), ("B", 100.0, 15.0)], {"A": all_below, "B": from_middle})
    by = {f.symbol: f for f in flags}
    assert by["A"].since_window_start is True
    assert by["A"].since == start and by["A"].days == 6
    assert by["B"].since_window_start is False
    assert by["B"].since == start + timedelta(days=3) and by["B"].days == 6
    # The field is last and defaults to False, so existing field order and callers hold.
    assert list(asdict(by["A"])) == [
        "symbol",
        "cut_price",
        "days",
        "since",
        "last_close",
        "since_window_start",
    ]
    assert coach.LagFlag("A", 85.0, 5, start, 80.0).since_window_start is False


def test_monthly_trade_counts_fill_gaps():
    trades = [
        trade(1, "A", "buy", date(2026, 1, 5), 1.0),
        trade(2, "A", "sell", date(2026, 1, 20), 1.0),
        trade(3, "A", "buy", date(2026, 3, 2), 1.0),
    ]
    counts = monthly_trade_counts(trades)
    assert [asdict(c) for c in counts] == [
        {"month": "2026-01", "buys": 1, "sells": 1, "total": 2},
        {"month": "2026-02", "buys": 0, "sells": 0, "total": 0},
        {"month": "2026-03", "buys": 1, "sells": 0, "total": 1},
    ]
    assert monthly_trade_counts([]) == []


def test_overtrading_compares_a_month_with_its_trailing_average():
    quiet = [MonthCount(f"2025-{m:02d}", 1, 1, 2) for m in range(1, 13)]
    burst = quiet + [MonthCount("2026-01", 6, 2, 8)]
    assert [m.month for m in overtrading(burst)] == ["2026-01"]
    small = quiet + [MonthCount("2026-01", 3, 2, 5)]  # above 2x but under min_trades
    assert overtrading(small) == []
    assert overtrading(quiet) == []
    assert overtrading([MonthCount("2026-01", 10, 10, 20)]) == []  # nothing to compare with
    assert [m.month for m in overtrading(burst, factor=3.0)] == ["2026-01"]
    assert overtrading(burst, factor=4.0) == []


def test_quick_rebuy_after_loss():
    d = date(2026, 3, 1)
    trades = [
        trade(1, "A", "sell", d, 90.0, avg_before=100.0, qty_before=5),
        trade(2, "A", "buy", d + timedelta(days=4), 92.0),
        trade(3, "A", "buy", d + timedelta(days=6), 93.0),  # only the first rebuy is flagged
        trade(4, "B", "sell", d, 110.0, avg_before=100.0, qty_before=5),  # sold at a gain
        trade(5, "B", "buy", d + timedelta(days=1), 111.0),
        trade(6, "C", "sell", d, 90.0, avg_before=100.0, qty_before=5),
        trade(7, "C", "buy", d + timedelta(days=15), 80.0),  # too late
    ]
    flags = quick_rebuy_after_loss(trades, days=10)
    assert [f.trade_id for f in flags] == [2]
    assert flags[0].value == 4.0 and flags[0].code == "quick_rebuy_after_loss"
    assert quick_rebuy_after_loss(trades, days=20)[0].trade_id == 2
    assert [f.trade_id for f in quick_rebuy_after_loss(trades, days=20)] == [2, 7]
    with pytest.raises(ValueError):
        quick_rebuy_after_loss(trades, days=-1)


def test_pattern_labels_cover_every_code_and_avoid_advice_words():
    assert set(PATTERN_LABELS_KO) == {
        "chasing_buy",
        "averaging_down_below_cut",
        "rule_lag",
        "overtrading",
        "quick_rebuy_after_loss",
    }
    text = " ".join(PATTERN_LABELS_KO.values()) + " ".join(
        getattr(coach, name)
        for name in dir(coach)
        if name.endswith("_KO") and isinstance(getattr(coach, name), str)
    )
    for word in BANNED_WORDS:
        assert word not in text


def test_module_imports_no_database_or_http():
    import inspect

    source = inspect.getsource(coach)
    for forbidden in (
        "sqlalchemy",
        "httpx",
        "requests",
        "fastapi",
        "app.db.session",
        "app.services",
    ):
        assert forbidden not in source
    for forbidden in ("execute(", "Broker", "KillSwitch.trip", "AM_LIVE_TRADING"):
        assert forbidden not in source
    assert math.isfinite(coach.PROJECT_MAX_DRAWDOWN_PCT)
