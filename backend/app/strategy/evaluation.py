"""Whether a backtested strategy beats its baselines: the pre-registered rule of D-015.

Gate ① (walk-forward, decides "candidate"):
  1. forecast edge: the signal's point-in-time edge held on enough decision dates,
  2. excess return over baselines ① and ② after costs and taxes: p = max(HAC t,
     stationary block bootstrap), Holm over the two baselines, x STRATEGY_CONFIGS_TRIED,
     below 0.05,
  3. net Sharpe above the volatility-matched baseline ① and Deflated Sharpe p < 0.05,
  4. excess over baseline ① with the same sign in two thirds of full-enough years,
  5. MDD <= 20% with the kill switch off (D-003),
  6. costs and taxes below half the profit before them.
Gate ② (the holdout, reference only) is opened once per strategy configuration through
`open_strategy_holdout`; only its MDD can reject. Gate ③ is the forward paper test.
"""

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from app.forecast import cv, metrics
from app.strategy.backtest import BacktestResult, cost_share
from app.strategy.risk import RiskLimits, adopt_strategy, max_drawdown

# Strategy configurations (signal rules and thresholds) tried on this data, the holdout
# included: the Bonferroni factor of the excess-return test and the N of the Deflated
# Sharpe (D-004). Raise it whenever a rule or threshold changes after seeing results and
# log the change in STRATEGIES.md.
# 2: S1-1w and S1-1m registered 2026-10-20 before any backtest.
STRATEGY_CONFIGS_TRIED = 2

ALPHA = 0.05
MIN_YEAR_SHARE = 2 / 3
MAX_COST_SHARE = 0.5
# S1 falsification 1: rejected when 50% or more of the decision dates have no edge, so the
# edge must be on for strictly more than half of them.
MIN_EDGE_SHARE = 0.5
BOOTSTRAP_BLOCK = 20
BOOTSTRAP_SAMPLES = 2000
# HAC lag for daily strategy returns (a week of overlap from weekly rebalancing).
RETURN_LAGS = 7


@dataclass
class ExcessTest:
    baseline: str
    days: int
    mean_daily: float
    hac_t: float
    hac_p: float
    bootstrap_p: float
    p_value: float  # the larger of the two
    p_adjusted: float = 1.0
    passed: bool = False


@dataclass
class SharpeTest:
    strategy_sharpe: float  # annualized
    baseline_sharpe: float
    stat: float
    p_value: float
    deflated_sr0: float  # benchmark daily Sharpe of the best of N unskilled trials
    deflated_p: float
    passed: bool = False


@dataclass
class GateVerdict:
    status: str  # "candidate" | "rejected"
    reasons: list[str]
    edge_share: float
    excess: dict[str, ExcessTest]
    sharpe: SharpeTest
    year_share: float
    years: int
    max_drawdown: float
    cost_share: float
    configs_tried: int
    checks: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return _finite(d)


def _finite(obj):
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_finite(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def _aligned(a: pd.Series, b: pd.Series) -> tuple[pd.Series, pd.Series]:
    a, b = a.align(b, join="inner")
    keep = a.notna() & b.notna()
    return a[keep], b[keep]


def excess_return_test(
    strategy: pd.Series,
    baseline: pd.Series,
    name: str = "baseline",
    *,
    lags: int = RETURN_LAGS,
    block: float = BOOTSTRAP_BLOCK,
    n_boot: int = BOOTSTRAP_SAMPLES,
    seed: int = 0,
) -> ExcessTest:
    """One-sided tests that daily strategy returns exceed the baseline's on common days."""
    s, b = _aligned(strategy, baseline)
    diff = (s - b).to_numpy(dtype=float)
    t, p_hac = metrics.mean_test(diff, lags)
    p_boot = metrics.stationary_bootstrap_p(diff, block, n_boot, seed)
    return ExcessTest(
        name, len(diff), float(diff.mean()) if len(diff) else 0.0, t, p_hac, p_boot,
        max(p_hac, p_boot),
    )  # fmt: skip


def sharpe_test(
    strategy: pd.Series,
    baseline: pd.Series,
    *,
    n_trials: int = STRATEGY_CONFIGS_TRIED,
    lags: int = RETURN_LAGS,
) -> SharpeTest:
    s, b = _aligned(strategy, baseline)
    _, stat, p = metrics.sharpe_difference(s.to_numpy(), b.to_numpy(), lags)
    _, sr0, dp = metrics.deflated_sharpe(s.to_numpy(), n_trials)
    ann = np.sqrt(365)

    def sr(x: pd.Series) -> float:
        sd = x.std(ddof=0)
        return float(x.mean() / sd * ann) if sd > 0 else 0.0

    return SharpeTest(sr(s), sr(b), stat, p, sr0, dp)


def year_consistency(strategy: pd.Series, baseline: pd.Series) -> tuple[float, int]:
    s, b = _aligned(strategy, baseline)
    return metrics.year_share(s - b)


def volatility_scale(strategy: pd.Series, baseline: pd.Series) -> float:
    """Exposure k <= 1 that gives baseline weights x k (rest cash) the strategy's realized
    volatility. Capped at 1: no leverage, even for a benchmark."""
    s, b = _aligned(strategy, baseline)
    sb = float(b.std())
    if sb <= 0:
        return 1.0
    return float(min(1.0, float(s.std()) / sb))


def adoption_gate(
    strategy: BacktestResult,
    baseline_1: BacktestResult,
    baseline_2: BacktestResult,
    vol_matched_1: BacktestResult,
    *,
    edge_share: float,
    limits: RiskLimits,
    configs_tried: int = STRATEGY_CONFIGS_TRIED,
    seed: int = 0,
) -> GateVerdict:
    """D-015 gate ① on walk-forward backtests run over the same days with the same costs.

    `edge_share` is the share of decision dates on which the point-in-time edge was on.
    `limits` is required (`RiskLimits.from_settings(settings)`), never the defaults quietly.
    """
    r = strategy.returns
    excess = {
        "baseline_1": excess_return_test(r, baseline_1.returns, "baseline_1", seed=seed),
        "baseline_2": excess_return_test(r, baseline_2.returns, "baseline_2", seed=seed),
    }
    adjusted = metrics.holm({k: e.p_value for k, e in excess.items()})
    for k, e in excess.items():
        e.p_adjusted = min(1.0, adjusted[k] * configs_tried)
        e.passed = e.p_adjusted < ALPHA
    sh = sharpe_test(r, vol_matched_1.returns, n_trials=configs_tried)
    sh.passed = sh.strategy_sharpe > sh.baseline_sharpe and sh.deflated_p < ALPHA
    share, years = year_consistency(r, baseline_1.returns)
    mdd = max_drawdown(np.r_[strategy.initial_capital_krw, strategy.equity.to_numpy()])
    mdd_verdict = adopt_strategy(mdd, limits)
    costs = cost_share(strategy)
    checks = {
        "1_forecast_edge": edge_share > MIN_EDGE_SHARE,
        "2_excess_baseline_1": excess["baseline_1"].passed,
        "2_excess_baseline_2": excess["baseline_2"].passed,
        "3_risk_adjusted": sh.passed,
        "4_yearly_consistency": years > 0 and share >= MIN_YEAR_SHARE,
        "5_max_drawdown": mdd_verdict.adopted,
        "6_costs": costs < MAX_COST_SHARE,
    }
    reasons = [k for k, ok in checks.items() if not ok]
    return GateVerdict(
        status="candidate" if not reasons else "rejected",
        reasons=reasons,
        edge_share=edge_share,
        excess=excess,
        sharpe=sh,
        year_share=share,
        years=years,
        max_drawdown=mdd,
        cost_share=costs,
        configs_tried=configs_tried,
        checks=checks,
    )


def holdout_mdd_ok(holdout: BacktestResult, *, limits: RiskLimits) -> bool:
    """D-015 ②: the only holdout result that can reject (a stricter direction)."""
    mdd = max_drawdown(np.r_[holdout.initial_capital_krw, holdout.equity.to_numpy()])
    return adopt_strategy(mdd, limits).adopted


# --- segments and the holdout -----------------------------------------------------------


def strategy_config_hash(config: dict) -> str:
    raw = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


@dataclass(frozen=True)
class HoldoutAccess:
    """Proof that a strategy's holdout look was logged; needed to get holdout dates."""

    config_hash: str
    entry: dict


def walk_forward_window(first: date, data_end: date) -> tuple[date, date]:
    """Days a walk-forward backtest may cover: up to the day before the holdout."""
    last = min(data_end, pd.Timestamp(cv.HOLDOUT_START).date() - timedelta(days=1))
    if last < first:
        raise ValueError("no walk-forward days before the holdout")
    return first, last


def walk_forward_decision_end(oos: pd.DataFrame) -> date:
    """Last date a walk-forward decision may be taken: the newest walk-forward OOS row.

    Walk-forward rows stop `horizon_days` before the holdout (ISSUE-029). A decision date
    after the last row would find no rows and sell the class (S1's too_few_assets; the
    baseline ② rule does the same), so decisions of the strategy and of baseline ② are
    cut here; the simulation itself still runs to the day before the holdout
    (`walk_forward_window`), holding the last decision's positions.
    """
    wf = oos[oos["segment"] == "walk_forward"]
    if wf.empty:
        raise ValueError("no walk-forward rows")
    return pd.Timestamp(wf["date"].max()).date()


def holdout_window(access: HoldoutAccess, data_end: date) -> tuple[date, date]:
    if not isinstance(access, HoldoutAccess):
        raise cv.HoldoutViewError("the holdout needs an access from open_strategy_holdout")
    return pd.Timestamp(cv.HOLDOUT_START).date(), data_end


def open_strategy_holdout(
    config: dict,
    data_end: date,
    *,
    configs_tried: int = STRATEGY_CONFIGS_TRIED,
    note: str = "",
    path: Path = cv.HOLDOUT_LOG,
) -> HoldoutAccess:
    """Log the single holdout look of a strategy configuration (D-007) or refuse it."""
    h = strategy_config_hash(config)
    entry = cv.open_holdout(
        "strategy",
        h,
        holdout_start=cv.HOLDOUT_START,
        data_end=str(data_end),
        configs_tried=configs_tried,
        note=note,
        path=path,
    )
    return HoldoutAccess(h, entry)


def edge_share(statuses) -> float:
    """Share of edge lookups that were on. Pass one lookup per (decision date, asset class)
    in the walk-forward decision window, both classes together, the early dates that are
    structurally `insufficient_history` included (S1 falsification 1, read literally)."""
    statuses = list(statuses)
    if not statuses:
        return 0.0
    return sum(1 for s in statuses if s.edge) / len(statuses)
