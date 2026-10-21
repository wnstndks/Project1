"""Skill against baselines, significance, and the edge verdict.

An "edge" is claimed only when all of these hold, otherwise the UI says there is none:
- the walk-forward loss beats the baseline with a one-sided Diebold-Mariano p < 0.05
  after Holm correction across every comparison tried (and Bonferroni across configs),
- the advantage has the same sign in at least two thirds of (full-enough) calendar years,
- the untouched holdout agrees (mean improvement > 0 and p < 0.10).
Direction is judged by the Brier score against the base rate of up moves; the range by
the mean pinball loss against the EWMA Student-t volatility baseline; the ranking (what a
cross-sectional signal uses) by the daily within-class rank correlation (IC) against zero.

The unit is asset class x horizon (D-005): 3 horizons x 2 classes x 3 kinds = 18
comparisons in one Holm family. `compare_losses` takes any two per-date loss series.

Two edges are not read from the report:
- `PointInTimeEdge.edge_at` (backtests): the same tests on an expanding window of the
  walk-forward rows whose targets were known by the decision date, so a 2018 signal is
  never switched on by what happened in 2022 (D-005).
- `live_edge_at` (the live service): a rank edge stays False until a pre-registered
  forward paper test confirms it (`FORWARD_CONFIRMED`, D-006); its holdout was seen.
"""

import math
from collections.abc import Callable, Collection, Mapping
from dataclasses import asdict, dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from app.data.calendar import expected_dates
from app.forecast import metrics
from app.forecast.panel import HORIZON_DAYS, HORIZONS
from app.forecast.walkforward import COVERAGE

ALPHA = 0.05
# Model configurations evaluated on this data so far, the holdout included. Each attempt is
# another chance of a lucky result, so p-values are also multiplied by this (Bonferroni).
# Raise it whenever the model or its settings change after seeing results.
# 1: initial settings. 2: time-ordered early stopping, min_child_samples 500, lr 0.02.
# 3: HEAD code with the phase-2 panel fixes (calendar-based returns, context lags), edge per
#    asset class with the rank comparison, partial years left out (D-004, D-005, D-006).
# The old per-symbol LSTM (app/ml) is not counted: it forecast prices of single symbols on
# another target and never produced a pooled report (D-018).
CONFIGS_TRIED = 3
HOLDOUT_ALPHA = 0.10
MIN_YEAR_SHARE = 2 / 3
# Point-in-time edges need at least this many full-enough years of known outcomes.
MIN_EDGE_YEARS = 2
# A rank comparison needs this many assets of a class on a date (S1 trades with n >= 3).
MIN_RANK_ASSETS = 3

ASSET_CLASSES = ("stock", "crypto")
KINDS = ("direction", "range", "rank")
# Comparisons in one Holm family: every horizon, class and kind, whether computed or not.
FAMILY_SIZE = len(HORIZONS) * len(ASSET_CLASSES) * len(KINDS)
# (kind, candidate, baseline, metric)
COMPARISON_SPECS = (
    ("direction", "gbdt", "climatology", "brier"),
    ("range", "gbdt", "ewma_t", "interval"),
    ("rank", "gbdt", "zero", "ic"),
)
# (asset class, horizon) whose rank edge a pre-registered forward paper test has confirmed
# (D-006, D-015 ③). Empty: no live rank signal. Adding one needs a DECISIONS.md entry.
FORWARD_CONFIRMED: frozenset[tuple[str, str]] = frozenset()


@dataclass
class ModelScore:
    rows: int
    interval_loss: float
    coverage: float
    kupiec_p: float
    brier: float
    hit_rate: float
    ic: float
    ic_t: float
    pt_p: float


@dataclass
class Comparison:
    model: str
    baseline: str
    metric: str
    dm_stat: float
    p_value: float
    year_share: float  # share of full-enough calendar years where the model did better
    holdout_dm_stat: float
    holdout_p_value: float
    p_adjusted: float = 1.0
    edge: bool = False
    asset_class: str = "all"
    years: int = 0
    dates: int = 0
    mean_gain: float = 0.0  # mean per-date loss reduction (rank: mean IC)


def score(oos: pd.DataFrame, model: str, lags: int) -> ModelScore:
    y = oos["y"].to_numpy()
    q10, q50, q90 = (oos[f"{model}_{c}"].to_numpy() for c in ("q10", "q50", "q90"))
    p_up = oos[f"{model}_p_up"].to_numpy()
    up = (y > 0).astype(float)
    misses = int(((y < q10) | (y > q90)).sum())
    ic, ic_t = metrics.information_coefficient(oos.assign(_s=p_up), "_s", "y", lags)
    _, pt_p = metrics.pesaran_timmermann((p_up > 0.5).astype(float), up)
    return ModelScore(
        rows=len(oos),
        interval_loss=float(metrics.interval_loss(y, q10, q50, q90).mean()),
        coverage=float(1 - misses / max(len(y), 1)),
        kupiec_p=metrics.kupiec(misses, len(y), 1 - COVERAGE),
        brier=float(metrics.brier(up, p_up).mean()),
        hit_rate=float(((p_up > 0.5) == (up > 0)).mean()),
        ic=ic,
        ic_t=ic_t,
        pt_p=pt_p,
    )


def _losses(oos: pd.DataFrame, model: str, metric: str) -> pd.Series:
    """Per-date mean loss: averaging across assets first removes their correlation."""
    y = oos["y"].to_numpy()
    if metric == "brier":
        loss = metrics.brier((y > 0).astype(float), oos[f"{model}_p_up"].to_numpy())
    else:
        loss = metrics.interval_loss(
            y, *(oos[f"{model}_{c}"].to_numpy() for c in ("q10", "q50", "q90"))
        )
    return pd.Series(loss, index=oos.index).groupby(oos["date"]).mean()


def rank_signal(oos: pd.DataFrame, model: str = "gbdt") -> pd.Series:
    """The score a rank strategy sorts by: the model's up probability over the base rate
    (S1). The base rate is one number per class and fold, so within a class and date the
    order is the model's."""
    s = oos[f"{model}_p_up"]
    if "climatology_p_up" in oos.columns:
        s = s - oos["climatology_p_up"].fillna(0.0)
    return s


def rank_gains(
    oos: pd.DataFrame, model: str = "gbdt", min_assets: int = MIN_RANK_ASSETS
) -> pd.Series:
    """Per-date within-class IC of the rank signal against the outcome (one class only)."""
    if oos.empty:
        return pd.Series(dtype=float)
    df = oos[["date", "y"]].assign(_s=rank_signal(oos, model).to_numpy())
    return metrics.daily_ic(df, "_s", "y", min_assets)


def compare_losses(
    loss_base: pd.Series,
    loss_model: pd.Series,
    lags: int,
    holdout_base: pd.Series | None = None,
    holdout_model: pd.Series | None = None,
    *,
    model: str = "model",
    baseline: str = "baseline",
    metric: str = "loss",
    asset_class: str = "all",
) -> Comparison:
    """Compare two date-indexed loss series (lower is better) on their common dates: HAC
    Diebold-Mariano, year-by-year consistency, and the same test on the holdout pair."""
    base, mod = loss_base.align(loss_model, join="inner")
    stat, p = metrics.diebold_mariano(base.to_numpy(), mod.to_numpy(), lags)
    diff = base - mod
    share, years = metrics.year_share(diff)
    h_stat, h_p = 0.0, 1.0
    if holdout_base is not None and holdout_model is not None:
        hb, hm = holdout_base.align(holdout_model, join="inner")
        if len(hb):
            h_stat, h_p = metrics.diebold_mariano(hb.to_numpy(), hm.to_numpy(), lags)
    return Comparison(
        model,
        baseline,
        metric,
        stat,
        p,
        share,
        h_stat,
        h_p,
        asset_class=asset_class,
        years=years,
        dates=len(diff),
        mean_gain=float(diff.mean()) if len(diff) else 0.0,
    )


def _pair(oos: pd.DataFrame, model: str, baseline: str, metric: str) -> tuple[pd.Series, ...]:
    if metric == "ic":
        gain = rank_gains(oos, model)
        return pd.Series(0.0, index=gain.index), -gain
    return _losses(oos, baseline, metric), _losses(oos, model, metric)


def compare(
    oos: pd.DataFrame,
    model: str,
    baseline: str,
    metric: str,
    lags: int,
    asset_class: str | None = None,
) -> Comparison:
    """`compare_losses` on the walk-forward and holdout segments of an OOS frame, for one
    asset class or (None) all rows pooled."""
    if asset_class is not None:
        oos = oos[oos["asset_class"] == asset_class]
    wf = oos[oos["segment"] == "walk_forward"]
    hold = oos[oos["segment"] == "holdout"]
    base, mod = _pair(wf, model, baseline, metric)
    h_base = h_mod = None
    if not hold.empty:
        h_base, h_mod = _pair(hold, model, baseline, metric)
    return compare_losses(
        base,
        mod,
        lags,
        h_base,
        h_mod,
        model=model,
        baseline=baseline,
        metric=metric,
        asset_class=asset_class or "all",
    )


def compare_all(
    oos: pd.DataFrame, lags: int, rank_symbols: Collection[str] | None = None
) -> dict[str, Comparison]:
    """The six comparisons of one horizon, keyed "{asset_class}:{kind}". Rank comparisons
    only use `rank_symbols` (the strategy universe, free of hindsight picks, ISSUE-020)."""
    out: dict[str, Comparison] = {}
    ranked = oos if rank_symbols is None else oos[oos["symbol"].isin(set(rank_symbols))]
    for cls in ASSET_CLASSES:
        for kind, model, baseline, metric in COMPARISON_SPECS:
            rows = ranked if kind == "rank" else oos
            out[f"{cls}:{kind}"] = compare(rows, model, baseline, metric, lags, cls)
    return out


def _passes(c: Comparison) -> bool:
    return c.p_adjusted < ALPHA and c.year_share >= MIN_YEAR_SHARE


def verdicts(
    comparisons: dict[str, Comparison],
    configs_tried: int = CONFIGS_TRIED,
    family_size: int = FAMILY_SIZE,
) -> dict[str, Comparison]:
    """Apply Holm across the comparisons and Bonferroni across configurations tried, then
    the full edge rule. `family_size` pads the family with p = 1 for comparisons that were
    not computed, so leaving a horizon out never makes the others easier to pass."""
    p = {k: c.p_value for k, c in comparisons.items()}
    for i in range(max(0, family_size - len(p))):
        p[f"_missing{i}"] = 1.0
    adjusted = metrics.holm(p)
    for k, c in comparisons.items():
        c.p_adjusted = min(1.0, adjusted[k] * configs_tried)
        c.edge = bool(_passes(c) and c.holdout_dm_stat > 0 and c.holdout_p_value < HOLDOUT_ALPHA)
    return comparisons


def edge_of(report_horizon: Mapping, asset_class: str, kind: str) -> bool:
    """The edge flag of one comparison in a saved report's horizon section."""
    comp = report_horizon.get("comparisons", {}).get(f"{asset_class}:{kind}", {})
    return bool(comp.get("edge", False))


def to_dict(obj) -> dict:
    d = asdict(obj)
    return {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in d.items()}


# --- point-in-time and live edges --------------------------------------------------------


@dataclass(frozen=True)
class EdgeStatus:
    """What `edge_at(as_of, asset_class, horizon)` says; the type signals.py receives."""

    edge: bool
    # edge | no_data | insufficient_history | not_significant | inconsistent_years |
    # forward_test_pending
    reason: str
    # Display only (S1 confidence): Wilson 95% lower bound of the share of top-third rows
    # whose return beat the same-date class mean, over rows with known outcomes.
    hit_rate_lower: float | None = None
    n: int = 0  # out-of-sample dates with a known outcome
    # ic (mean gain: IC for rank, loss reduction otherwise), t_stat, p_adjusted, year_share
    details: Mapping[str, float] = field(default_factory=dict)


EdgeLookup = Callable[[date, str, str], EdgeStatus]


def target_end_dates(dates: pd.DatetimeIndex, asset_class: str, horizon: str) -> pd.DatetimeIndex:
    """The bar each row's target ends on: HORIZONS[horizon] NYSE sessions after the row
    for stocks (holidays included, as the panel counts them), that many days for coins."""
    steps = HORIZONS[horizon][asset_class]
    dates = pd.DatetimeIndex(dates).as_unit("ns")
    if dates.empty:
        return dates
    if asset_class == "crypto":
        return dates + pd.Timedelta(days=steps)
    last = dates.max() + pd.Timedelta(days=3 * steps + 30)
    sessions = pd.DatetimeIndex(expected_dates("SPY", dates.min().date(), last.date()))
    sessions = sessions.as_unit("ns")
    pos = sessions.searchsorted(dates, side="right") - 1 + steps
    return pd.DatetimeIndex(sessions[np.clip(pos, 0, len(sessions) - 1)])


def _hits(oos: pd.DataFrame, model: str) -> pd.DataFrame:
    """Per date: how many top-third rows (by the rank signal) beat their class-date mean
    return, and how many top-third rows there were. Cumulated over dates."""
    if oos.empty:
        return pd.DataFrame(columns=["hits", "n"], index=pd.DatetimeIndex([]))
    df = oos[["date", "symbol", "fr"]].assign(_s=rank_signal(oos, model).to_numpy())
    rows = []
    for d, g in df.dropna(subset=["fr", "_s"]).groupby("date", sort=True):
        n = len(g)
        if n < MIN_RANK_ASSETS:
            continue
        top = g.sort_values(["_s", "symbol"], ascending=[False, True]).head(math.ceil(n / 3))
        rows.append((d, int((top["fr"] > g["fr"].mean()).sum()), len(top)))
    out = pd.DataFrame(rows, columns=["date", "hits", "n"]).set_index("date")
    return out.cumsum()


class PointInTimeEdge:
    """Edges as they would have been judged on each date, from walk-forward rows only.

    On `as_of` a row counts if its target was known: the bar its target ends on (h NYSE
    sessions later for stocks, h days for coins, `target_end_dates`) is on or before
    `as_of`. A calendar-day bound would not do: 5 sessions span up to 11 days. All
    18 comparisons are re-tested on that expanding window, Holm-adjusted together (missing
    ones count as p = 1) and multiplied by `configs_tried`; an edge also needs two thirds
    of at least `min_years` full-enough years to agree. There is no holdout check: on a
    past date the holdout lies in the future (D-006 reports it separately).
    """

    def __init__(
        self,
        oos: Mapping[str, pd.DataFrame],
        rank_symbols: Collection[str] | None = None,
        *,
        configs_tried: int = CONFIGS_TRIED,
        min_years: int = MIN_EDGE_YEARS,
        lags: Mapping[str, int] | None = None,
    ) -> None:
        self.configs_tried = configs_tried
        self.min_years = min_years
        self.lags = dict(lags or HORIZON_DAYS)
        self._gains: dict[tuple[str, str, str], pd.Series] = {}
        self._hit_counts: dict[tuple[str, str], pd.DataFrame] = {}
        self._ends: dict[tuple[str, str], pd.Series] = {}
        symbols = None if rank_symbols is None else set(rank_symbols)
        for h, frame in oos.items():
            wf = frame[frame["segment"] == "walk_forward"]
            for cls in ASSET_CLASSES:
                rows = wf[wf["asset_class"] == cls]
                ranked = rows if symbols is None else rows[rows["symbol"].isin(symbols)]
                dates = pd.DatetimeIndex(sorted(set(rows["date"]))).as_unit("ns")
                self._ends[(h, cls)] = pd.Series(target_end_dates(dates, cls, h), index=dates)
                for kind, model, baseline, metric in COMPARISON_SPECS:
                    base, mod = _pair(ranked if kind == "rank" else rows, model, baseline, metric)
                    base, mod = base.align(mod, join="inner")
                    self._gains[(h, cls, kind)] = (base - mod).sort_index()
                self._hit_counts[(h, cls)] = _hits(ranked, "gbdt")
        self._cache: dict[date, dict[tuple[str, str, str], EdgeStatus]] = {}

    def _known(self, s: pd.Series | pd.DataFrame, horizon: str, cls: str, as_of: date):
        if len(s) == 0:
            return s.iloc[0:0]
        ends = self._ends[(horizon, cls)].reindex(pd.DatetimeIndex(s.index))
        return s[(ends <= pd.Timestamp(as_of)).to_numpy()]

    def _evaluate(self, as_of: date) -> dict[tuple[str, str, str], EdgeStatus]:
        stats_: dict[tuple[str, str, str], tuple] = {}
        for key, gains in self._gains.items():
            h, cls = key[0], key[1]
            g = self._known(gains, h, cls, as_of)
            t, p = metrics.diebold_mariano(g.to_numpy(), np.zeros(len(g)), self.lags.get(h, 1))
            share, years = metrics.year_share(g)
            stats_[key] = (g, t, p, share, years)
        p_values = {key: s[2] for key, s in stats_.items()}
        for i in range(max(0, FAMILY_SIZE - len(p_values))):
            p_values[("_missing", str(i), "")] = 1.0
        adjusted = metrics.holm(p_values)
        out = {}
        for key, (g, t, _p, share, years) in stats_.items():
            h, cls, kind = key
            p_adj = min(1.0, adjusted[key] * self.configs_tried)
            if g.empty:
                reason = "no_data"
            elif len(g) < 10 or years < self.min_years:
                reason = "insufficient_history"
            elif p_adj >= ALPHA:
                reason = "not_significant"
            elif share < MIN_YEAR_SHARE:
                reason = "inconsistent_years"
            else:
                reason = "edge"
            hit_lower = None
            counts = self._known(self._hit_counts.get((h, cls), pd.DataFrame()), h, cls, as_of)
            if kind == "rank" and len(counts):
                last = counts.iloc[-1]
                hit_lower = metrics.wilson_lower(int(last["hits"]), int(last["n"]))
            out[key] = EdgeStatus(
                edge=reason == "edge",
                reason=reason,
                hit_rate_lower=hit_lower,
                n=len(g),
                details={
                    "ic": float(g.mean()) if len(g) else math.nan,
                    "t_stat": float(t),
                    "p_adjusted": float(p_adj),
                    "year_share": float(share),
                },
            )
        return out

    def status(self, as_of: date, asset_class: str, horizon: str, kind: str) -> EdgeStatus:
        as_of = pd.Timestamp(as_of).date()
        if as_of not in self._cache:
            self._cache[as_of] = self._evaluate(as_of)
        found = self._cache[as_of].get((horizon, asset_class, kind))
        if found is None:
            return EdgeStatus(False, "no_data")
        return found

    def edge_at(self, as_of: date, asset_class: str, horizon: str) -> EdgeStatus:
        """The rank edge (what S1 trades on); the callback signals.py receives."""
        return self.status(as_of, asset_class, horizon, "rank")


def live_edge_at(report: Mapping, kind: str = "rank") -> EdgeLookup:
    """Edge callback for the live service, read from a saved report.

    A rank edge is withheld until FORWARD_CONFIRMED lists the class and horizon: its
    walk-forward IC was looked at before the hypothesis was written down (D-006).
    """

    def lookup(as_of: date, asset_class: str, horizon: str) -> EdgeStatus:
        section = report.get("horizons", {}).get(horizon, {})
        comp = section.get("comparisons", {}).get(f"{asset_class}:{kind}", {})
        if not comp:
            return EdgeStatus(False, "no_data")
        common = dict(
            n=int(comp.get("dates") or 0),
            details={
                "ic": float(comp["mean_gain"]) if comp.get("mean_gain") is not None else math.nan,
                "t_stat": float(comp.get("dm_stat") or 0.0),
                "p_adjusted": float(comp.get("p_adjusted") or 1.0),
                "year_share": float(comp.get("year_share") or 0.0),
            },
        )
        if kind == "rank" and (asset_class, horizon) not in FORWARD_CONFIRMED:
            return EdgeStatus(False, "forward_test_pending", **common)
        if comp.get("edge"):
            return EdgeStatus(True, "edge", **common)
        return EdgeStatus(False, "not_significant", **common)

    return lookup
