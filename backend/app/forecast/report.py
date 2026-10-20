"""Skill against baselines, significance, and the edge verdict.

An "edge" is claimed only when all of these hold, otherwise the UI says there is none:
- the walk-forward loss beats the baseline with a one-sided Diebold-Mariano p < 0.05
  after Holm correction across the horizons tried,
- the advantage has the same sign in at least two thirds of calendar years,
- the untouched holdout year agrees (mean improvement > 0 and p < 0.10).
Direction is judged by the Brier score against the base rate of up moves; the range by
the mean pinball loss against the EWMA Student-t volatility baseline.
"""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from app.forecast import metrics
from app.forecast.walkforward import COVERAGE

ALPHA = 0.05
# Model configurations evaluated on this data so far, the holdout included. Each attempt is
# another chance of a lucky result, so p-values are also multiplied by this (Bonferroni).
# Raise it whenever the model or its settings change after seeing results.
# 1: initial settings. 2: time-ordered early stopping, min_child_samples 500, lr 0.02.
CONFIGS_TRIED = 2
HOLDOUT_ALPHA = 0.10
MIN_YEAR_SHARE = 2 / 3


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
    year_share: float  # share of calendar years where the model did better
    holdout_dm_stat: float
    holdout_p_value: float
    p_adjusted: float = 1.0
    edge: bool = False


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


def compare(oos: pd.DataFrame, model: str, baseline: str, metric: str, lags: int) -> Comparison:
    wf = oos[oos["segment"] == "walk_forward"]
    hold = oos[oos["segment"] == "holdout"]
    d_base, d_model = _losses(wf, baseline, metric), _losses(wf, model, metric)
    stat, p = metrics.diebold_mariano(d_base.to_numpy(), d_model.to_numpy(), lags)
    diff = d_base - d_model
    yearly = diff.groupby(pd.DatetimeIndex(diff.index).year).mean()
    year_share = float((yearly > 0).mean()) if len(yearly) else 0.0
    if hold.empty:
        h_stat, h_p = 0.0, 1.0
    else:
        h_stat, h_p = metrics.diebold_mariano(
            _losses(hold, baseline, metric).to_numpy(),
            _losses(hold, model, metric).to_numpy(),
            lags,
        )
    return Comparison(model, baseline, metric, stat, p, year_share, h_stat, h_p)


def verdicts(comparisons: dict[str, Comparison]) -> dict[str, Comparison]:
    """Apply Holm across the comparisons and Bonferroni across configurations tried, then
    the full edge rule."""
    adjusted = metrics.holm({k: c.p_value for k, c in comparisons.items()})
    for k, c in comparisons.items():
        c.p_adjusted = min(1.0, adjusted[k] * CONFIGS_TRIED)
        c.edge = bool(
            c.p_adjusted < ALPHA
            and c.year_share >= MIN_YEAR_SHARE
            and c.holdout_dm_stat > 0
            and c.holdout_p_value < HOLDOUT_ALPHA
        )
    return comparisons


def to_dict(obj) -> dict:
    d = asdict(obj)
    return {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in d.items()}
