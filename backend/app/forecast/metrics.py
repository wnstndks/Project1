"""Forecast scores and the tests that decide whether a model beats its baseline.

Rows of a panel are not independent: assets move together on a date, and multi-day
targets overlap. Tests therefore work on per-date averages and use Newey-West (HAC)
variances with a lag of at least the horizon length.
"""

import numpy as np
import pandas as pd
from scipy import stats


def pinball(y: np.ndarray, q: np.ndarray, alpha: float) -> np.ndarray:
    """Quantile (pinball) loss per row."""
    diff = y - q
    return np.maximum(alpha * diff, (alpha - 1) * diff)


def interval_loss(y: np.ndarray, q10: np.ndarray, q50: np.ndarray, q90: np.ndarray) -> np.ndarray:
    """Mean pinball loss over the three quantiles: a proper score for the whole range."""
    return (pinball(y, q10, 0.1) + pinball(y, q50, 0.5) + pinball(y, q90, 0.9)) / 3


def brier(up: np.ndarray, p_up: np.ndarray) -> np.ndarray:
    return (p_up - up) ** 2


def newey_west_var(x: np.ndarray, lags: int) -> float:
    """HAC long-run variance of a series' mean component (Bartlett kernel)."""
    x = np.asarray(x, dtype=float) - np.mean(x)
    n = len(x)
    var = float(x @ x) / n
    for k in range(1, min(lags, n - 1) + 1):
        w = 1 - k / (lags + 1)
        var += 2 * w * float(x[k:] @ x[:-k]) / n
    return max(var, 1e-300)


def diebold_mariano(
    loss_base: np.ndarray, loss_model: np.ndarray, lags: int
) -> tuple[float, float]:
    """One-sided DM test that the model's loss is lower. Returns (statistic, p-value)."""
    d = np.asarray(loss_base) - np.asarray(loss_model)
    n = len(d)
    if n < 10:
        return 0.0, 1.0
    stat = float(np.mean(d) / np.sqrt(newey_west_var(d, lags) / n))
    return stat, float(1 - stats.norm.cdf(stat))


def kupiec(misses: int, n: int, expected_rate: float) -> float:
    """p-value of Kupiec's proportion-of-failures test: does the interval miss as often as
    it should? (Overlapping targets make this optimistic; it is a sanity check.)"""
    if n == 0:
        return 1.0
    x, p = misses, expected_rate
    phat = min(max(x / n, 1e-12), 1 - 1e-12)
    ll_null = (n - x) * np.log(1 - p) + x * np.log(p)
    ll_alt = (n - x) * np.log(1 - phat) + x * np.log(phat)
    lr = -2 * (ll_null - ll_alt)
    return float(1 - stats.chi2.cdf(lr, df=1))


def pesaran_timmermann(pred_up: np.ndarray, actual_up: np.ndarray) -> tuple[float, float]:
    """Test of directional accuracy beyond what the two base rates imply. (stat, p)."""
    pred_up = np.asarray(pred_up, dtype=float)
    actual_up = np.asarray(actual_up, dtype=float)
    n = len(pred_up)
    if n < 10:
        return 0.0, 1.0
    p_hat = np.mean(pred_up == actual_up)
    py, px = actual_up.mean(), pred_up.mean()
    p_star = py * px + (1 - py) * (1 - px)
    var_p = p_star * (1 - p_star) / n
    var_star = (
        (2 * py - 1) ** 2 * px * (1 - px) / n
        + (2 * px - 1) ** 2 * py * (1 - py) / n
        + 4 * py * px * (1 - py) * (1 - px) / n**2
    )
    denom = var_p - var_star
    if denom <= 0:
        return 0.0, 1.0
    stat = float((p_hat - p_star) / np.sqrt(denom))
    return stat, float(1 - stats.norm.cdf(stat))


def information_coefficient(
    df: pd.DataFrame, signal: str, outcome: str, lags: int
) -> tuple[float, float]:
    """Mean cross-sectional Spearman correlation per date and asset class (groups with 5+
    assets), and its Newey-West t-statistic. Within a class: stocks and coins differ in
    level, and mixing them would credit even a constant per-class forecast with skill."""
    ics = []
    keys = ["date", "asset_class"] if "asset_class" in df.columns else ["date"]
    for _, g in df.groupby(keys):
        if len(g) >= 5 and g[signal].nunique() > 1:
            ics.append(stats.spearmanr(g[signal], g[outcome]).statistic)
    ics = np.array([x for x in ics if np.isfinite(x)])
    if len(ics) < 10:
        return float("nan"), 0.0
    t = float(np.mean(ics) / np.sqrt(newey_west_var(ics, lags) / len(ics)))
    return float(np.mean(ics)), t


def holm(p_values: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values (controls the chance of any false 'edge')."""
    items = sorted(p_values.items(), key=lambda kv: kv[1])
    m = len(items)
    adjusted: dict[str, float] = {}
    running = 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        adjusted[k] = running
    return adjusted
