"""Hand-computed answers for the portfolio coach (app/strategy/coach.py, D-033).

Written by the evaluation engineer, apart from the module's author (CLAUDE.md: whoever
builds a module and whoever checks its numbers are different people). Every expected value
is worked out by hand or from a one-line formula written next to the assertion, never by
running the module; the module's behavioural tests live in test_coach.py. All inputs are
synthetic (AAA, BBB, XXX...); none is a real holding.

Where the module's figure differs from the hand value, the test stays as
`xfail(strict=True)` and the gap is reported instead of bending the expectation.
"""

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.strategy import coach
from app.strategy.coach import (
    NO_PICK_NOTE_KO,
    Excluded,
    HoldingView,
    MonthCount,
    Policy,
    TargetPlan,
    TradeView,
    averaging_down_below_cut,
    beta,
    cap_class_weights,
    chasing_buys,
    concentration,
    construct_targets,
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
    weights,
)
from app.strategy.risk import Book, RiskLimits, max_drawdown

SQRT252 = math.sqrt(252)
D0 = date(2024, 1, 1)
# Caps wide enough that only the rule under test binds.
WIDE = RiskLimits(max_position_weight=1.0, max_order_fraction=1.0)
NO_FX = pd.Series(dtype=float)
STOCK_80_CASH_20 = Policy(target_stock_pct=80, target_crypto_pct=0, target_cash_pct=20)


# --- helpers (they build inputs only; no expected value comes from the module) ------------------


def alternating(std: float, rows: int, start: date = D0) -> pd.Series:
    """A +c, −c, +c... sequence: its mean is exactly 0 and Σx² = rows·c², so the sample
    (ddof=1) standard deviation is c·√(rows/(rows−1)); c is chosen to make that `std`."""
    assert rows % 2 == 0
    c = std * math.sqrt((rows - 1) / rows)
    return pd.Series([c, -c] * (rows // 2), index=pd.bdate_range(start, periods=rows))


def daily(values, start: date) -> pd.Series:
    """Closes on consecutive calendar days from `start`."""
    index = pd.to_datetime([start + timedelta(days=i) for i in range(len(values))])
    return pd.Series([float(v) for v in values], index=index)


def krw_returns(**closes: pd.Series) -> pd.DataFrame:
    """Daily returns of KRW close series (no exchange rate enters) on the union of dates."""
    return krw_return_frame(closes, NO_FX, dict.fromkeys(closes, "KRW"), "all")


def holding(
    symbol: str,
    asset_class: str = "stock",
    value: float = 100.0,
    target: float | None = None,
    currency: str = "USD",
) -> HoldingView:
    return HoldingView(
        symbol=symbol,
        asset_class=asset_class,
        currency=currency,
        quantity=1.0,
        price=value,
        price_krw=value,
        value_krw=value,
        cost_basis_krw=value,
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
) -> TradeView:
    return TradeView(
        id=id,
        symbol=symbol,
        asset_class="stock",
        side=side,
        date=day,
        quantity=1.0,
        price=price,
        currency="USD",
        avg_cost_before=avg_before,
        qty_before=qty_before,
    )


def plan_of(**targets: float) -> TargetPlan:
    """A TargetPlan with the given fractions; rebalance_plan reads only `targets`."""
    return TargetPlan(
        targets=dict(targets),
        source=dict.fromkeys(targets, "symbol"),
        class_targets={"stock": 100.0, "crypto": 0.0, "cash": 0.0},
        unallocated_pct=0.0,
        capped=(),
    )


@pytest.fixture
def fixed_correlation(monkeypatch):
    """Swap the Ledoit-Wolf estimate for a given matrix so σ_p = √(wᵀ·D·C·D·w) can be
    checked against a closed form with a known ρ."""

    def install(matrix) -> None:
        m = np.asarray(matrix, dtype=float)
        monkeypatch.setattr(coach, "correlation", lambda returns, min_rows=120: m)

    return install


# --- 1. portfolio volatility ---------------------------------------------------------------------


class TestPortfolioVolatility:
    """σ_p² = w₁²σ₁² + w₂²σ₂² + 2·w₁·w₂·ρ·σ₁·σ₂ with w = (0.6, 0.4), σ = (0.20, 0.50) a year."""

    def two_assets(self, fixed_correlation, rho: float, equity: float = 1_000_000.0):
        fixed_correlation([[1.0, rho], [rho, 1.0]])
        a = alternating(0.20 / SQRT252, 300)
        b = alternating(0.50 / SQRT252, 300)
        return risk_window(
            pd.DataFrame({"A": a, "B": b}),
            {"A": 60, "B": 40},
            equity,
            name="1y",
            periods_per_year=252,
        )

    def test_rho_0_3_gives_26_2298_percent(self, fixed_correlation):
        w = self.two_assets(fixed_correlation, 0.3)
        # 0.36·0.04 + 0.16·0.25 + 2·0.6·0.4·0.3·0.2·0.5 = 0.0144 + 0.04 + 0.0144 = 0.0688
        assert w.annual_vol_pct == pytest.approx(26.2298, abs=1e-3)
        assert w.annual_vol_pct == pytest.approx(math.sqrt(0.0688) * 100, abs=1e-9)
        assert w.swing_1sigma_krw == pytest.approx(math.sqrt(0.0688) * 1_000_000, abs=1e-6)
        assert w.usable and w.rows == 300 and w.included == ("A", "B") and w.excluded == ()
        assert w.grid == "stock" and w.periods_per_year == 252

    @pytest.mark.parametrize(
        "rho,expected_pct",
        [
            (1.0, 32.0),  # 0.6·0.2 + 0.4·0.5
            (-1.0, 8.0),  # |0.6·0.2 − 0.4·0.5|
            (0.0, math.sqrt(0.0144 + 0.04) * 100),
        ],
    )
    def test_the_correlation_term_enters_as_in_the_formula(
        self, fixed_correlation, rho, expected_pct
    ):
        w = self.two_assets(fixed_correlation, rho)
        assert w.annual_vol_pct == pytest.approx(expected_pct, abs=1e-9)
        assert w.swing_1sigma_krw == pytest.approx(expected_pct / 100 * 1_000_000, abs=1e-6)

    def test_single_asset_is_its_sample_deviation_times_sqrt_252(self):
        a = alternating(0.20 / SQRT252, 300)
        w = risk_window(
            pd.DataFrame({"A": a}), {"A": 100}, 2_500_000, name="1y", periods_per_year=252
        )
        assert w.annual_vol_pct == pytest.approx(20.0, abs=1e-9)
        assert w.swing_1sigma_krw == pytest.approx(500_000.0, abs=1e-6)
        assert w.method == "single"

    def test_coin_only_grid_annualises_by_sqrt_365(self):
        a = alternating(0.20 / SQRT252, 300)
        w = risk_window(pd.DataFrame({"A": a}), {"A": 100}, 1000, name="1y", periods_per_year=365)
        assert w.annual_vol_pct == pytest.approx(20.0 * math.sqrt(365 / 252), abs=1e-9)
        assert w.grid == "all"

    def test_cash_half_of_the_base_halves_the_volatility(self):
        a = alternating(0.20 / SQRT252, 300)
        w = risk_window(
            pd.DataFrame({"A": a}), {"A": 50}, 1_000_000, name="1y", periods_per_year=252
        )
        assert w.annual_vol_pct == pytest.approx(10.0, abs=1e-9)
        assert w.swing_1sigma_krw == pytest.approx(100_000.0, abs=1e-6)


# --- 2. fixed-weight drawdown ---------------------------------------------------------------------


class TestFixedWeightDrawdown:
    """Index Π(1 + Σᵢ wᵢ rᵢₜ) from 1.0; drawdown = 1 − trough / running peak. The correlation
    does not enter, so it is pinned to the identity to keep sklearn out of the picture."""

    def test_closes_100_120_90_110_fall_25_percent_from_120_to_90(self, fixed_correlation):
        fixed_correlation(np.eye(1))
        d = [date(2026, 1, 1) + timedelta(days=i) for i in range(4)]
        r = krw_returns(A=daily([100, 120, 90, 110], d[0]))
        assert r["A"].tolist() == pytest.approx([0.2, -0.25, 110 / 90 - 1])
        w = risk_window(r, {"A": 100}, 1000, name="w", periods_per_year=252, min_rows=2)
        assert w.max_drawdown_pct == pytest.approx(25.0, abs=1e-9)  # 1.2 → 0.9
        assert w.drawdown_peak == d[1]  # the 120 close
        assert w.drawdown_trough == d[2]  # the 90 close
        assert w.peak_at_window_start is False  # the peak is inside the window, so it is dated
        assert w.usable and w.rows == 3 and w.start == d[1] and w.end == d[3]

    def test_half_half_mix_of_a_mover_and_a_flat_asset_falls_10_percent(self, fixed_correlation):
        fixed_correlation(np.eye(2))
        d0 = date(2026, 1, 1)
        r = krw_returns(A=daily([100, 110, 88], d0), B=daily([100, 100, 100], d0))
        assert r["A"].tolist() == pytest.approx([0.10, -0.20]) and r["B"].tolist() == [0.0, 0.0]
        w = risk_window(r, {"A": 50, "B": 50}, 1000, name="w", periods_per_year=252, min_rows=2)
        # portfolio returns (0.05, −0.10) → index 1.05 then 0.945 → 1 − 0.945/1.05 = 0.10
        assert w.max_drawdown_pct == pytest.approx(10.0, abs=1e-9)
        assert w.drawdown_peak == d0 + timedelta(days=1)
        assert w.drawdown_trough == d0 + timedelta(days=2)

    def test_half_cash_damps_the_fall_to_12_5_percent(self, fixed_correlation):
        fixed_correlation(np.eye(1))
        r = krw_returns(A=daily([100, 120, 90, 110], date(2026, 1, 1)))
        w = risk_window(r, {"A": 50}, 1000, name="w", periods_per_year=252, min_rows=2)
        # portfolio returns (0.10, −0.125, 0.111) → 1.10 then 0.9625 → 1 − 0.9625/1.10 = 0.125
        assert w.max_drawdown_pct == pytest.approx(12.5, abs=1e-9)

    def test_a_rising_series_has_no_drawdown_and_no_dates(self, fixed_correlation):
        fixed_correlation(np.eye(1))
        r = krw_returns(A=daily([100, 110, 121], date(2026, 1, 1)))
        w = risk_window(r, {"A": 100}, 1000, name="w", periods_per_year=252, min_rows=2)
        assert w.max_drawdown_pct == 0.0
        assert w.drawdown_peak is None and w.drawdown_trough is None

    def test_peak_at_the_window_start_has_no_date_and_sets_the_flag(self, fixed_correlation):
        # The frame holds returns only, so the bar before the first return (the 100 close, the
        # real peak) has no date: the module says so instead of dating the peak one bar late.
        fixed_correlation(np.eye(1))
        d0 = date(2026, 1, 1)
        r = krw_returns(A=daily([100, 90, 95], d0))
        w = risk_window(r, {"A": 100}, 1000, name="w", periods_per_year=252, min_rows=2)
        assert w.max_drawdown_pct == pytest.approx(10.0, abs=1e-9)  # 1.0 → 0.9
        assert w.drawdown_trough == d0 + timedelta(days=1)  # the 90 close
        assert w.drawdown_peak is None
        assert w.peak_at_window_start is True


# --- 3. concentration -----------------------------------------------------------------------------


class TestConcentration:
    """HHI = Σ wᵢ² over invested fractions; effective_n = 1/HHI."""

    def test_50_30_20(self):
        hs = [holding("AAA", value=500), holding("BBB", value=300), holding("CCC", value=200)]
        c = concentration(weights(hs, None))
        assert c.hhi == pytest.approx(0.38, abs=1e-12)  # 0.25 + 0.09 + 0.04
        assert c.effective_n == pytest.approx(1 / 0.38, abs=1e-9)
        assert c.effective_n == pytest.approx(2.6316, abs=1e-4)
        assert c.top1_pct == pytest.approx(50.0) and c.top3_pct == pytest.approx(100.0)
        assert c.top1_symbol == "AAA" and c.count == 3

    def test_four_equal_holdings(self):
        hs = [holding(s, value=250) for s in ("AAA", "BBB", "CCC", "DDD")]
        c = concentration(weights(hs, None))
        assert c.hhi == pytest.approx(0.25, abs=1e-12)
        assert c.effective_n == pytest.approx(4.0, abs=1e-9)
        assert c.top1_pct == pytest.approx(25.0) and c.top3_pct == pytest.approx(75.0)

    def test_five_holdings_40_20_20_10_10(self):
        values = {"AAA": 400, "BBB": 200, "CCC": 200, "DDD": 100, "EEE": 100}
        c = concentration(weights([holding(s, value=v) for s, v in values.items()], None))
        assert c.top3_pct == pytest.approx(80.0)
        assert c.top1_pct == pytest.approx(40.0) and c.top1_symbol == "AAA"
        assert c.hhi == pytest.approx(0.16 + 0.04 + 0.04 + 0.01 + 0.01, abs=1e-12)  # 0.26
        assert c.effective_n == pytest.approx(1 / 0.26, abs=1e-9)  # 3.846

    def test_cash_changes_weight_pct_but_not_the_invested_basis(self):
        hs = [holding("AAA", value=500), holding("BBB", value=300), holding("CCC", value=200)]
        with_cash = weights(hs, cash_krw=1000)
        assert [w.weight_pct for w in with_cash] == pytest.approx([25.0, 15.0, 10.0])
        assert [w.invested_weight_pct for w in with_cash] == pytest.approx([50.0, 30.0, 20.0])
        assert concentration(with_cash).hhi == pytest.approx(0.38, abs=1e-12)


# --- 4. beta --------------------------------------------------------------------------------------


class TestBeta:
    """β = cov(y, x) / var(x); r² = cov² / (var(x)·var(y)); both with ddof=1."""

    @pytest.fixture
    def x(self) -> pd.Series:
        return pd.Series(np.sin(np.arange(60)) * 0.01, index=pd.bdate_range(D0, periods=60))

    def test_y_equals_2x(self, x):
        b = beta(2 * x, x)
        assert b is not None
        assert b.beta == pytest.approx(2.0, abs=1e-12)
        assert b.r2 == pytest.approx(1.0, abs=1e-12)
        assert b.rows == 60

    def test_slope_half_with_an_intercept_and_a_negative_slope(self, x):
        half = beta(0.5 * x + 0.001, x)
        assert half is not None and half.beta == pytest.approx(0.5, abs=1e-12)
        assert half.r2 == pytest.approx(1.0, abs=1e-12)
        neg = beta(-x, x)
        assert neg is not None and neg.beta == pytest.approx(-1.0, abs=1e-12)
        assert neg.r2 == pytest.approx(1.0, abs=1e-12)

    def test_none_for_a_zero_benchmark_or_fewer_than_60_rows(self, x):
        assert beta(2 * x, pd.Series(0.0, index=x.index)) is None
        assert beta((2 * x).iloc[:59], x.iloc[:59]) is None
        assert beta((2 * x).iloc[:59], x.iloc[:59], min_rows=59) is not None

    @pytest.mark.parametrize("level", [0.01, 0.3, -0.007])
    def test_none_for_a_benchmark_flat_at_a_non_zero_level(self, x, level):
        # Mathematically var(x) = 0, but pandas var(ddof=1) of a constant 0.01 series is about
        # 3e-36 from rounding; the guard must treat that as flat rather than divide by it.
        assert beta(2 * x, pd.Series(level, index=x.index)) is None

    def test_rows_are_the_common_dates(self, x):
        b = beta(2 * x, x.iloc[:59], min_rows=10)
        assert b is not None and b.rows == 59 and b.beta == pytest.approx(2.0, abs=1e-12)

    def test_hand_values_for_four_points(self):
        # x = 1,2,3,4 (mean 2.5), y = 2,4,5,9 (mean 5):
        # cov = (4.5 + 0.5 + 0 + 6)/3 = 11/3, var x = 5/3, var y = 26/3
        index = pd.bdate_range(D0, periods=4)
        b = beta(
            pd.Series([2.0, 4.0, 5.0, 9.0], index=index),
            pd.Series([1.0, 2.0, 3.0, 4.0], index=index),
            min_rows=4,
        )
        assert b is not None
        assert b.beta == pytest.approx(11 / 5, abs=1e-12)  # 2.2
        assert b.r2 == pytest.approx(121 / 130, abs=1e-12)  # 0.930769...
        assert b.rows == 4


# --- 5. time-weighted index and period review -----------------------------------------------------


class TestTwrAndPeriodReview:
    DAYS = [date(2026, 3, 1), date(2026, 3, 2), date(2026, 3, 3)]

    def series(self, values, flows) -> tuple[pd.Series, pd.Series]:
        index = pd.to_datetime(self.DAYS)
        return pd.Series(values, index=index, dtype=float), pd.Series(
            flows, index=index, dtype=float
        )

    def test_twr_index_strips_the_deposit(self):
        values, flows = self.series([100, 210, 200], [0, 100, 0])
        idx = twr_index(values, flows)
        # r₁ = (210 − 100 − 100)/100 = 0.10; r₂ = (200 − 210 − 0)/210 = −1/21
        assert idx.tolist() == pytest.approx([1.0, 1.10, 1.10 * (1 - 1 / 21)], abs=1e-12)
        assert idx.iloc[-1] == pytest.approx(1.047619, abs=1e-6)
        assert max_drawdown(idx) == pytest.approx(1 / 21, abs=1e-6)  # 4.7619%
        assert max_drawdown(idx) * 100 == pytest.approx(4.7619, abs=1e-4)

    def test_period_review_from_the_first_point(self):
        values, flows = self.series([100, 210, 200], [0, 100, 0])
        r = period_review(values, flows, self.DAYS[0], self.DAYS[-1])
        assert r.start_point == self.DAYS[0] and r.end_point == self.DAYS[-1]
        assert r.start_value_krw == 100.0 and r.end_value_krw == 200.0
        assert r.change_krw == 100.0
        assert r.contributions_krw == 100.0  # the day-2 flow lies in (start, end]
        assert r.market_pnl_krw == 0.0  # (200 − 100) − 100

    def test_period_review_before_the_first_point_counts_the_first_buy(self):
        values, flows = self.series([100, 210, 200], [100, 100, 0])
        r = period_review(values, flows, self.DAYS[0] - timedelta(days=1), self.DAYS[-1])
        assert r.start_point is None and r.start_value_krw == 0.0
        assert r.contributions_krw == 200.0  # both flows are inside (start, end]
        assert r.change_krw == 200.0 and r.market_pnl_krw == 0.0

    def test_period_review_with_a_market_gain(self):
        values, flows = self.series([100, 210, 231], [0, 100, 0])
        r = period_review(values, flows, self.DAYS[0], self.DAYS[-1])
        assert r.change_krw == 131.0 and r.contributions_krw == 100.0
        assert r.market_pnl_krw == pytest.approx(31.0)


# --- 6. target construction -----------------------------------------------------------------------


class TestTargetConstruction:
    def test_a_explicit_15_and_the_remainder_65_add_up_to_the_class_80(self):
        hs = [holding("AAA", target=15), holding("BBB")]
        plan = construct_targets(hs, STOCK_80_CASH_20, WIDE, cash_known=True)
        assert plan.targets == pytest.approx({"AAA": 0.15, "BBB": 0.65})
        assert plan.source == {"AAA": "symbol", "BBB": "remainder"}
        assert sum(plan.targets.values()) == pytest.approx(0.80)
        assert plan.capped == () and plan.unallocated_pct == 0.0 and plan.notes == ()
        assert plan.class_targets == {"stock": 80.0, "crypto": 0.0, "cash": 20.0}

    def test_a_under_the_default_20_percent_cap_the_remainder_stops_at_20(self):
        hs = [holding("AAA", target=15), holding("BBB")]
        plan = construct_targets(hs, STOCK_80_CASH_20, RiskLimits(), cash_known=True)
        assert plan.targets == pytest.approx({"AAA": 0.15, "BBB": 0.20})
        assert plan.capped == ("BBB",)
        assert any("45.0%p" in n for n in plan.notes)  # 0.80 − 0.35 stays cash
        assert sum(plan.targets.values()) <= 1 + 1e-9

    def test_b_two_explicit_15s_with_no_free_symbol_scale_up_to_40_each(self):
        hs = [holding("AAA", target=15), holding("BBB", target=15)]
        plan = construct_targets(hs, STOCK_80_CASH_20, WIDE, cash_known=True)
        assert plan.targets == pytest.approx({"AAA": 0.40, "BBB": 0.40})  # ×(80/30)
        assert plan.source == {"AAA": "scaled", "BBB": "scaled"}
        assert any("30%" in n and "80%" in n and "못 미쳐" in n for n in plan.notes)
        assert sum(plan.targets.values()) == pytest.approx(0.80)

    def test_c_a_zero_crypto_target_closes_the_coins(self):
        hs = [holding("AAA", value=800), holding("XXX", "crypto", value=200, currency="KRW")]
        plan = construct_targets(hs, STOCK_80_CASH_20, WIDE, cash_known=True)
        assert plan.targets["XXX"] == 0.0 and plan.source["XXX"] == "class_zero"
        assert plan.targets["AAA"] == pytest.approx(0.80) and plan.source["AAA"] == "remainder"
        assert plan.unallocated_pct == 0.0

    def test_d_a_crypto_target_with_no_coin_held_is_unallocated(self):
        plan = construct_targets([holding("AAA")], Policy(), WIDE, cash_known=True)  # 80/20/0
        assert plan.unallocated_pct == pytest.approx(20.0)
        assert any(NO_PICK_NOTE_KO in n and "20%" in n for n in plan.notes)
        assert plan.targets == pytest.approx({"AAA": 0.80})  # no new symbol
        assert sum(plan.targets.values()) <= 1 + 1e-9

    def test_e_a_single_stock_with_an_80_percent_class_target_is_capped_at_20(self):
        plan = construct_targets([holding("AAA")], STOCK_80_CASH_20, RiskLimits(), cash_known=True)
        assert plan.targets == pytest.approx({"AAA": 0.20}) and plan.capped == ("AAA",)
        assert any("60.0%p" in n for n in plan.notes)

    def test_e_explicit_coin_targets_of_25_each_shrink_to_the_30_percent_class(self):
        pol = Policy(
            target_stock_pct=70, target_crypto_pct=30, target_cash_pct=0, max_crypto_weight_pct=30
        )
        hs = [
            holding("AAA", target=70),
            holding("XXX", "crypto", target=25, currency="KRW"),
            holding("YYY", "crypto", target=25, currency="KRW"),
        ]
        plan = construct_targets(hs, pol, WIDE, cash_known=True)
        assert plan.targets == pytest.approx({"AAA": 0.70, "XXX": 0.15, "YYY": 0.15})  # ×(30/50)
        assert plan.source["XXX"] == "scaled" and plan.source["YYY"] == "scaled"
        assert sum(plan.targets.values()) == pytest.approx(1.0)
        assert sum(plan.targets.values()) <= 1 + 1e-9

    def test_e_crypto_cap_binds_when_cash_unknown_renormalises_the_classes(self):
        pol = Policy(
            target_stock_pct=50, target_crypto_pct=25, target_cash_pct=25, max_crypto_weight_pct=30
        )
        hs = [
            holding("AAA", value=500),
            holding("XXX", "crypto", value=125, currency="KRW"),
            holding("YYY", "crypto", value=125, currency="KRW"),
        ]
        plan = construct_targets(hs, pol, RiskLimits(), cash_known=False)
        # 50/25 of the invested amount = 66.67/33.33; coins 16.67 each → class cap 30 → 15 each;
        # the stock 66.67 → symbol cap 20.
        assert plan.class_targets["stock"] == pytest.approx(200 / 3)
        assert plan.class_targets["crypto"] == pytest.approx(100 / 3)
        assert plan.class_targets["cash"] is None
        assert plan.targets == pytest.approx({"AAA": 0.20, "XXX": 0.15, "YYY": 0.15})
        assert set(plan.capped) == {"AAA", "XXX", "YYY"}
        assert any("50.0%p" in n for n in plan.notes)
        assert sum(plan.targets.values()) == pytest.approx(0.50)

    def test_cap_class_weights_scales_only_the_class_over_its_cap(self):
        out = cap_class_weights(
            {"XXX": 0.25, "YYY": 0.25, "AAA": 0.5},
            {"XXX": "crypto", "YYY": "crypto", "AAA": "stock"},
            {"crypto": 0.30},
        )
        assert out == pytest.approx({"XXX": 0.15, "YYY": 0.15, "AAA": 0.5})

    def test_spy_uses_the_80_percent_index_fund_cap(self):
        plan = construct_targets([holding("SPY")], STOCK_80_CASH_20, RiskLimits(), cash_known=True)
        assert plan.targets == pytest.approx({"SPY": 0.80}) and plan.capped == ()
        pol = Policy(target_stock_pct=90, target_crypto_pct=0, target_cash_pct=10)
        over = construct_targets([holding("SPY")], pol, RiskLimits(), cash_known=True)
        assert over.targets == pytest.approx({"SPY": 0.80}) and over.capped == ("SPY",)
        assert any("10.0%p" in n for n in over.notes)

    def test_policy_limits_narrow_the_symbol_cap_to_10_percent(self):
        pol = Policy(
            target_stock_pct=80, target_crypto_pct=0, target_cash_pct=20, max_position_weight_pct=10
        )
        plan = construct_targets([holding("AAA")], pol, pol.limits(RiskLimits()), cash_known=True)
        assert plan.targets == pytest.approx({"AAA": 0.10}) and plan.capped == ("AAA",)


# --- 7. rebalance band and cash -------------------------------------------------------------------


class TestRebalanceBand:
    """Equity 1,000,000, band 5 → min notional 50,000; a change of exactly 50,000 is skipped."""

    PLAN = plan_of(AAA=0.5, BBB=0.5)

    def test_four_points_of_drift_inside_a_five_point_band_means_no_orders(self):
        book = Book(0.0, {"AAA": 540_000.0, "BBB": 460_000.0})
        assert rebalance_plan(book, self.PLAN, WIDE, band_pt=5) == []

    def test_exactly_the_band_is_not_traded(self):
        book = Book(0.0, {"AAA": 550_000.0, "BBB": 450_000.0})
        assert rebalance_plan(book, self.PLAN, WIDE, band_pt=5) == []

    def test_six_points_of_drift_sells_60000_first_then_buys_60000(self):
        book = Book(0.0, {"AAA": 560_000.0, "BBB": 440_000.0})
        orders = rebalance_plan(book, self.PLAN, WIDE, band_pt=5)
        assert [(d.order.symbol, d.order.side, d.status) for d in orders] == [
            ("AAA", "sell", "accepted"),
            ("BBB", "buy", "accepted"),
        ]
        assert [d.notional for d in orders] == pytest.approx([60_000.0, 60_000.0])
        assert all(d.reasons == () for d in orders)

    def test_a_buy_beyond_the_sale_proceeds_is_clipped_to_cash(self):
        plan = plan_of(AAA=0.5, BBB=0.3, CCC=0.2)
        book = Book(0.0, {"AAA": 540_000.0, "BBB": 400_000.0, "CCC": 60_000.0})
        orders = rebalance_plan(book, plan, WIDE, band_pt=5)
        # AAA: −40,000 is inside the band; BBB: −100,000 sold; CCC: +140,000 wanted, 100,000 cash.
        assert [(d.order.symbol, d.order.side) for d in orders] == [("BBB", "sell"), ("CCC", "buy")]
        sell, buy = orders
        assert sell.status == "accepted" and sell.notional == pytest.approx(100_000.0)
        assert buy.order.notional == pytest.approx(140_000.0)
        assert buy.status == "clipped" and buy.notional == pytest.approx(100_000.0)
        assert buy.reasons == ("cash",)

    def test_a_buy_with_nothing_sold_and_no_cash_is_rejected(self):
        plan = plan_of(AAA=0.5, BBB=0.4, CCC=0.1)
        book = Book(0.0, {"AAA": 530_000.0, "BBB": 430_000.0, "CCC": 40_000.0})
        orders = rebalance_plan(book, plan, WIDE, band_pt=5)
        assert [(d.order.symbol, d.order.side, d.status, d.notional) for d in orders] == [
            ("CCC", "buy", "rejected", 0.0)
        ]
        assert orders[0].order.notional == pytest.approx(60_000.0)
        assert "cash" in orders[0].reasons

    def test_the_per_order_cap_clips_a_buy_to_5_percent_of_equity(self):
        limits = RiskLimits(max_position_weight=1.0, max_order_fraction=0.05)
        book = Book(0.0, {"AAA": 560_000.0, "BBB": 440_000.0})
        sell, buy = rebalance_plan(book, self.PLAN, limits, band_pt=5)
        assert sell.status == "accepted" and sell.notional == pytest.approx(60_000.0)
        assert buy.status == "clipped" and buy.notional == pytest.approx(50_000.0)
        assert buy.reasons == ("max_order_fraction",)


# --- 8. required annual return --------------------------------------------------------------------


class TestRequiredReturn:
    def test_doubling_in_ten_years_needs_7_1773_percent(self):
        r = required_annual_return_pct(1e7, 0, 2e7, 10)
        assert r == pytest.approx((2 ** (1 / 10) - 1) * 100, abs=1e-9)
        assert r == pytest.approx(7.1773, abs=1e-3)

    def test_contributions_that_reach_the_goal_at_zero_need_no_return(self):
        # 12 × 1,000,000 × 10 = 120,000,000 exactly → f(0) = 0 ≥ 0 → None
        assert required_annual_return_pct(0, 1_000_000, 120_000_000, 10) is None
        r = required_annual_return_pct(0, 1_000_000, 120_000_001, 10)
        assert r is not None and 0 < r < 1e-3

    def test_a_mixed_case_inverts_the_annuity_formula(self):
        # At 5% a year for 10 years: c·1.05¹⁰ + 12·m·(1.05¹⁰ − 1)/0.05
        growth = 1.05**10
        goal = 10_000_000 * growth + 12 * 1_000_000 * (growth - 1) / 0.05
        assert required_annual_return_pct(10_000_000, 1_000_000, goal, 10) == pytest.approx(
            5.0, abs=1e-9
        )

    def test_none_when_the_goal_is_below_the_current_value_or_there_is_no_time(self):
        assert required_annual_return_pct(2e7, 0, 1e7, 10) is None
        assert required_annual_return_pct(1e7, 0, 2e7, 0) is None


# --- 9. habits in the trade log -------------------------------------------------------------------


class TestChasingBuys:
    START = date(2026, 1, 1)

    def bars(self, last: float) -> pd.Series:
        # 30 daily bars; for a buy on day 31 the last close is bar 29 and the close 20 bars
        # earlier is bar 9, which stays at 100.
        values = [100.0] * 30
        values[29] = last
        return daily(values, self.START)

    def test_plus_20_percent_is_flagged_plus_10_and_exactly_15_are_not(self):
        buy_day = self.START + timedelta(days=30)
        trades = [
            trade(1, "UP", "buy", buy_day, 120.0),
            trade(2, "MILD", "buy", buy_day, 110.0),
            trade(3, "EDGE", "buy", buy_day, 115.0),
        ]
        closes = {"UP": self.bars(120), "MILD": self.bars(110), "EDGE": self.bars(115)}
        flags, skipped = chasing_buys(trades, closes, lookback=20, threshold_pct=15)
        assert [(f.trade_id, f.symbol) for f in flags] == [(1, "UP")]
        assert flags[0].value == pytest.approx(20.0, abs=1e-9)
        assert skipped == 0

    def test_buys_without_21_prior_bars_are_skipped_not_judged(self):
        trades = [
            trade(1, "UP", "buy", self.START, 100.0),  # first bar: nothing before it
            trade(2, "UP", "buy", self.START + timedelta(days=20), 100.0),  # 20 bars before
            trade(3, "UP", "buy", self.START + timedelta(days=21), 100.0),  # 21 bars: judged
        ]
        flags, skipped = chasing_buys(trades, {"UP": self.bars(120)})
        assert skipped == 2 and flags == []


class TestAveragingDownBelowCut:
    def test_84_and_85_are_at_or_below_the_15_percent_line_86_is_not(self):
        d = date(2026, 3, 2)
        trades = [
            trade(1, "AAA", "buy", d, 84.0, avg_before=100.0, qty_before=10),
            trade(2, "AAA", "buy", d, 86.0, avg_before=100.0, qty_before=10),
            trade(3, "AAA", "buy", d, 85.0, avg_before=100.0, qty_before=10),
            trade(4, "AAA", "buy", d, 84.0, avg_before=None, qty_before=0),  # first buy
            trade(5, "AAA", "buy", d, 84.0, avg_before=100.0, qty_before=0),  # nothing held
        ]
        flags = averaging_down_below_cut(trades, lambda symbol, cls: 15.0)
        assert [f.trade_id for f in flags] == [1, 3]
        assert flags[0].value == pytest.approx(-16.0, abs=1e-9)
        assert flags[1].value == pytest.approx(-15.0, abs=1e-9)


class TestRuleLag:
    START = date(2026, 4, 1)

    def test_five_trailing_closes_at_or_below_85(self):
        closes = daily([100, 100, 100, 85, 84, 83, 85, 80], self.START)
        flags = rule_lag([("AAA", 100.0, 15.0)], {"AAA": closes}, min_days=5)
        assert len(flags) == 1
        f = flags[0]
        assert f.symbol == "AAA" and f.days == 5
        assert f.cut_price == pytest.approx(85.0)
        assert f.since == self.START + timedelta(days=3) and f.last_close == 80.0

    def test_four_trailing_closes_are_under_the_five_day_minimum(self):
        closes = daily([80, 80, 100, 84, 84, 84, 84], self.START)  # the early dip does not count
        assert rule_lag([("AAA", 100.0, 15.0)], {"AAA": closes}) == []
        f = rule_lag([("AAA", 100.0, 15.0)], {"AAA": closes}, min_days=4)[0]
        assert f.days == 4 and f.since == self.START + timedelta(days=3)


class TestOvertrading:
    QUIET = [MonthCount(f"2025-{m:02d}", 2, 2, 4) for m in range(1, 13)]

    def test_14_trades_after_12_months_of_4_is_flagged(self):
        out = overtrading([*self.QUIET, MonthCount("2026-01", 7, 7, 14)])
        assert [(m.month, m.total) for m in out] == [("2026-01", 14)]

    def test_5_trades_is_under_min_trades_and_8_is_not_above_twice_the_average(self):
        assert overtrading([*self.QUIET, MonthCount("2026-01", 3, 2, 5)]) == []
        assert overtrading([*self.QUIET, MonthCount("2026-01", 4, 4, 8)]) == []
        assert [m.total for m in overtrading([*self.QUIET, MonthCount("2026-01", 5, 4, 9)])] == [9]

    def test_from_the_trade_log(self):
        trades, n = [], 0
        for m in range(1, 13):
            for k in range(4):
                n += 1
                side = "buy" if k < 2 else "sell"
                trades.append(trade(n, "AAA", side, date(2025, m, 1 + k), 10.0))
        for k in range(14):
            n += 1
            side = "buy" if k % 2 == 0 else "sell"
            trades.append(trade(n, "AAA", side, date(2026, 1, 1 + k), 10.0))
        counts = monthly_trade_counts(trades)
        assert len(counts) == 13 and counts[-1] == MonthCount("2026-01", 7, 7, 14)
        assert [m.month for m in overtrading(counts)] == ["2026-01"]


class TestQuickRebuyAfterLoss:
    def test_seven_and_ten_days_are_flagged_eleven_is_not(self):
        d = date(2026, 5, 1)
        trades = [
            trade(1, "AAA", "sell", d, 90.0, avg_before=100.0, qty_before=5),
            trade(2, "AAA", "buy", d + timedelta(days=7), 91.0),
            trade(3, "BBB", "sell", d, 90.0, avg_before=100.0, qty_before=5),
            trade(4, "BBB", "buy", d + timedelta(days=11), 91.0),
            trade(5, "CCC", "sell", d, 100.0, avg_before=100.0, qty_before=5),  # not a loss
            trade(6, "CCC", "buy", d + timedelta(days=1), 99.0),
            trade(7, "DDD", "sell", d, 90.0, avg_before=100.0, qty_before=5),
            trade(8, "DDD", "buy", d + timedelta(days=10), 91.0),  # on the window's edge
        ]
        flags = quick_rebuy_after_loss(trades, days=10)
        assert [(f.trade_id, f.symbol, f.value) for f in flags] == [
            (2, "AAA", 7.0),
            (8, "DDD", 10.0),
        ]
        assert "-10.0%" in flags[0].detail and "7일" in flags[0].detail


# --- 10. short history, coverage, grid ------------------------------------------------------------


class TestShortHistoryAndCoverage:
    def frame(self, c_bars: int = 50) -> pd.DataFrame:
        a = alternating(0.20 / SQRT252, 300)
        b = alternating(0.50 / SQRT252, 300)
        c = pd.Series(np.nan, index=a.index)
        c.iloc[-c_bars:] = alternating(0.30 / SQRT252, c_bars).to_numpy()
        return pd.DataFrame({"A": a, "B": b, "C": c})

    def test_the_short_symbol_is_excluded_and_the_rest_renormalised(self, fixed_correlation):
        fixed_correlation(np.ones((2, 2)))  # ρ = 1 makes σ_p = Σ wᵢσᵢ, so the weights show
        w = risk_window(
            self.frame(), {"A": 50, "B": 30, "C": 20}, 1_000_000, name="3y", periods_per_year=252
        )
        assert w.excluded == (Excluded("C", 50),) and w.included == ("A", "B")
        assert w.coverage_pct == pytest.approx(80.0)
        # 50/80 = 62.5% and 30/80 = 37.5% of the whole: 0.625·0.20 + 0.375·0.50 = 0.3125
        assert w.annual_vol_pct == pytest.approx(31.25, abs=1e-9)
        assert w.swing_1sigma_krw == pytest.approx(312_500.0, abs=1e-6)
        assert w.usable and w.rows == 300 and w.method == "ledoit_wolf"

    def test_70_percent_coverage_is_not_usable_but_the_figure_is_still_computed(
        self, fixed_correlation
    ):
        fixed_correlation(np.ones((2, 2)))
        w = risk_window(
            self.frame(), {"A": 40, "B": 30, "C": 30}, 1000, name="3y", periods_per_year=252
        )
        assert w.coverage_pct == pytest.approx(70.0)
        assert w.usable is False
        assert w.reason is not None and "C" in w.reason and "70%" in w.reason and "75%" in w.reason
        # 40/70·0.20 + 30/70·0.50 = 0.32857
        assert w.annual_vol_pct == pytest.approx((40 / 70 * 0.2 + 30 / 70 * 0.5) * 100, abs=1e-9)

    def test_fewer_than_120_common_rows_uses_the_identity_correlation(self):
        index = pd.bdate_range(D0, periods=300)
        a = pd.Series(np.nan, index=index)
        b = pd.Series(np.nan, index=index)
        # A has rows 0..149, B rows 100..299: 50 common rows (100..149). Each run is tiled from
        # a 50-row ±c block, so the block on the overlap has mean 0 and the exact deviation.
        a.iloc[:150] = np.tile(alternating(0.20 / SQRT252, 50).to_numpy(), 3)
        b.iloc[100:] = np.tile(alternating(0.50 / SQRT252, 50).to_numpy(), 4)
        w = risk_window(
            pd.DataFrame({"A": a, "B": b}),
            {"A": 50, "B": 50},
            1000,
            name="3y",
            periods_per_year=252,
        )
        assert w.included == ("A", "B") and w.excluded == ()
        assert w.rows == 50 and w.method == "identity"
        assert w.start == index[100].date() and w.end == index[149].date()
        # identity: √(0.25·0.04 + 0.25·0.25) = √0.0725 = 0.26926
        assert w.annual_vol_pct == pytest.approx(math.sqrt(0.0725) * 100, abs=1e-9)
        assert w.usable is False and w.reason is not None and "50일" in w.reason


class TestKrwReturnFrame:
    def test_usd_close_times_the_rate_of_the_day_and_krw_as_is(self):
        days = pd.to_datetime([date(2026, 2, 2), date(2026, 2, 3)])
        closes = {
            "AAA": pd.Series([100.0, 110.0], index=days),
            "XXX": pd.Series([50_000.0, 55_000.0], index=days),
        }
        fx = pd.Series([1300.0, 1400.0], index=days)
        r = krw_return_frame(closes, fx, {"AAA": "USD", "XXX": "KRW"}, "all")
        assert len(r) == 1 and r.index[0] == days[1]
        # 100 × 1300 = 130,000 → 110 × 1400 = 154,000
        assert r.iloc[0]["AAA"] == pytest.approx(154_000 / 130_000 - 1, abs=1e-12)
        assert r.iloc[0]["AAA"] == pytest.approx(0.1846154, abs=1e-7)
        assert r.iloc[0]["XXX"] == pytest.approx(0.10, abs=1e-12)

    def test_stock_grid_folds_the_coin_weekend_into_monday(self):
        fri = date(2026, 1, 9)
        assert fri.weekday() == 4
        sat, sun, mon = (fri + timedelta(days=i) for i in (1, 2, 3))
        coin = pd.Series([100.0, 105.0, 110.0, 115.0], index=pd.to_datetime([fri, sat, sun, mon]))
        stock = pd.Series([50.0, 52.0], index=pd.to_datetime([fri, mon]))
        fx = pd.Series([1000.0, 1100.0], index=pd.to_datetime([fri, mon]))
        currency = {"S": "USD", "C": "KRW"}
        on_stock = krw_return_frame(
            {"S": stock, "C": coin},
            fx,
            currency,
            "stock",
            asset_class={"S": "stock", "C": "crypto"},
        )
        assert [d.date() for d in on_stock.index] == [mon]
        assert on_stock.iloc[0]["C"] == pytest.approx(0.15, abs=1e-12)  # 100 → 115 over the weekend
        assert on_stock.iloc[0]["S"] == pytest.approx(57_200 / 50_000 - 1, abs=1e-12)  # 0.144
        every_day = krw_return_frame({"S": stock, "C": coin}, fx, currency, "all")
        assert [d.date() for d in every_day.index] == [sat, sun, mon]
        assert every_day["C"].tolist() == pytest.approx([0.05, 110 / 105 - 1, 115 / 110 - 1])
        assert every_day["S"].tolist() == pytest.approx([0.0, 0.0, 0.144])  # carried over Sat/Sun
