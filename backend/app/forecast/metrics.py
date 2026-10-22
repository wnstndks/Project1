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


# A 10-90% range of a normal spans 2 x 1.2816 standard deviations.
RANGE_TO_SIGMA = float(2 * stats.norm.ppf(0.9))
MIN_SIGMA = 1e-3


def implied_sigma(q10: np.ndarray, q90: np.ndarray, floor: float = MIN_SIGMA) -> np.ndarray:
    """The volatility a 10-90% range implies: its width over 2.5631, at least `floor`.
    Every model goes through the same conversion, so only the widths are compared."""
    width = np.asarray(q90, dtype=float) - np.asarray(q10, dtype=float)
    return np.maximum(width / RANGE_TO_SIGMA, floor)


def qlike(y: np.ndarray, sigma: np.ndarray) -> np.ndarray:
    """QLIKE loss of a volatility forecast per row: y^2 / sigma^2 + log sigma^2. With the
    noisy proxy y^2 it still ranks variance forecasts correctly (Patton 2011), and it does
    not score the location (q50) at all."""
    var = np.asarray(sigma, dtype=float) ** 2
    return np.asarray(y, dtype=float) ** 2 / var + np.log(var)


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


def daily_ic(df: pd.DataFrame, signal: str, outcome: str, min_assets: int = 5) -> pd.Series:
    """Cross-sectional Spearman correlation per date (and asset class, if the column is
    there), for groups of at least `min_assets` with a non-constant signal. Indexed by date;
    a date appears once per class."""
    keys = ["date", "asset_class"] if "asset_class" in df.columns else ["date"]
    dates, ics = [], []
    for key, g in df.groupby(keys, sort=True):
        if len(g) >= min_assets and g[signal].nunique() > 1 and g[outcome].nunique() > 1:
            ic = stats.spearmanr(g[signal], g[outcome]).statistic
            if np.isfinite(ic):
                dates.append(key[0] if isinstance(key, tuple) else key)
                ics.append(float(ic))
    return pd.Series(ics, index=pd.DatetimeIndex(dates), dtype=float)


def information_coefficient(
    df: pd.DataFrame, signal: str, outcome: str, lags: int, min_assets: int = 5
) -> tuple[float, float]:
    """Mean cross-sectional Spearman correlation per date and asset class (groups with 5+
    assets), and its Newey-West t-statistic. Within a class: stocks and coins differ in
    level, and mixing them would credit even a constant per-class forecast with skill."""
    ics = daily_ic(df, signal, outcome, min_assets).to_numpy()
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


# A calendar year counts for year-by-year consistency only if its observations span at
# least this many days: a first year that starts in October would otherwise weigh as much
# as a full one (ISSUE-031).
MIN_YEAR_SPAN_DAYS = 182


def yearly_means(x: pd.Series, min_span_days: int = MIN_YEAR_SPAN_DAYS) -> pd.Series:
    """Mean of a date-indexed series per calendar year, full-enough years only."""
    if x.empty:
        return pd.Series(dtype=float)
    idx = pd.DatetimeIndex(x.index)
    years = idx.year
    span = pd.Series(idx, index=idx).groupby(years).agg(lambda d: (d.max() - d.min()).days + 1)
    means = pd.Series(x.to_numpy(dtype=float), index=idx).groupby(years).mean()
    return means[span.reindex(means.index) >= min_span_days]


def year_share(x: pd.Series, min_span_days: int = MIN_YEAR_SPAN_DAYS) -> tuple[float, int]:
    """Share of (full-enough) calendar years with a positive mean, and how many years."""
    yearly = yearly_means(x, min_span_days)
    if yearly.empty:
        return 0.0, 0
    return float((yearly > 0).mean()), len(yearly)


def mean_test(x: np.ndarray, lags: int) -> tuple[float, float]:
    """One-sided HAC t-test that the mean of `x` is above zero. (stat, p)."""
    x = np.asarray(x, dtype=float)
    return diebold_mariano(x, np.zeros_like(x), lags)


def stationary_bootstrap_p(
    x: np.ndarray, block: float = 20.0, n_boot: int = 2000, seed: int = 0
) -> float:
    """One-sided p-value that the mean of `x` is above zero, by the stationary bootstrap
    (Politis and Romano 1994: blocks of geometric length with mean `block`).

    The series is centred to impose the null, resampled, and the observed mean is compared
    with the resampled means. Serial dependence within blocks is kept.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 10:
        return 1.0
    observed = x.mean()
    centred = x - observed
    rng = np.random.default_rng(seed)
    p_new = 1.0 / block
    idx = np.empty((n_boot, n), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, n_boot)
    starts = rng.integers(0, n, (n_boot, n))
    jump = rng.random((n_boot, n)) < p_new
    for t in range(1, n):
        idx[:, t] = np.where(jump[:, t], starts[:, t], (idx[:, t - 1] + 1) % n)
    means = centred[idx].mean(axis=1)
    return float((1 + (means >= observed).sum()) / (n_boot + 1))


def sharpe_difference(r1: np.ndarray, r2: np.ndarray, lags: int) -> tuple[float, float, float]:
    """Test that the Sharpe ratio of `r1` exceeds that of `r2` (same dates), with the HAC
    delta-method standard error of Ledoit and Wolf (2008). Returns (difference per period,
    statistic, one-sided p)."""
    r1, r2 = np.asarray(r1, dtype=float), np.asarray(r2, dtype=float)
    n = len(r1)
    if n < 10 or len(r2) != n:
        return 0.0, 0.0, 1.0
    mu1, mu2 = r1.mean(), r2.mean()
    g1, g2 = (r1**2).mean(), (r2**2).mean()
    s1, s2 = g1 - mu1**2, g2 - mu2**2
    if s1 <= 0 or s2 <= 0:
        return 0.0, 0.0, 1.0
    diff = mu1 / np.sqrt(s1) - mu2 / np.sqrt(s2)
    grad = np.array([g1 / s1**1.5, -g2 / s2**1.5, -0.5 * mu1 / s1**1.5, 0.5 * mu2 / s2**1.5])
    y = np.column_stack([r1 - mu1, r2 - mu2, r1**2 - g1, r2**2 - g2])
    psi = y.T @ y / n
    for k in range(1, min(lags, n - 1) + 1):
        w = 1 - k / (lags + 1)
        gamma = y[k:].T @ y[:-k] / n
        psi += w * (gamma + gamma.T)
    var = float(grad @ psi @ grad) / n
    if var <= 0:
        return float(diff), 0.0, 1.0
    stat = float(diff / np.sqrt(var))
    return float(diff), stat, float(1 - stats.norm.cdf(stat))


def deflated_sharpe(
    r: np.ndarray, n_trials: int, trial_sharpe_var: float | None = None
) -> tuple[float, float, float]:
    """Deflated Sharpe ratio (Bailey and Lopez de Prado 2014) of per-period returns `r`.

    The benchmark Sharpe is the expected maximum of `n_trials` unskilled trials. Without
    the Sharpe ratios of the other trials, their variance is taken as the sampling variance
    of this one's estimate. Returns (Sharpe per period, benchmark Sharpe, p-value =
    1 - DSR: the chance an unskilled best-of-n would look at least this good).
    """
    r = np.asarray(r, dtype=float)
    n = len(r)
    if n < 10 or r.std() == 0:
        return 0.0, 0.0, 1.0
    sr = float(r.mean() / r.std())
    skew = float(stats.skew(r))
    kurt = float(stats.kurtosis(r, fisher=False))
    denom = 1 - skew * sr + (kurt - 1) / 4 * sr**2
    if denom <= 0:
        return sr, 0.0, 1.0
    var = trial_sharpe_var if trial_sharpe_var is not None else denom / (n - 1)
    if n_trials <= 1:
        sr0 = 0.0
    else:
        gamma = 0.5772156649015329
        sr0 = float(
            np.sqrt(var)
            * (
                (1 - gamma) * stats.norm.ppf(1 - 1 / n_trials)
                + gamma * stats.norm.ppf(1 - 1 / (n_trials * np.e))
            )
        )
    z = (sr - sr0) * np.sqrt(n - 1) / np.sqrt(denom)
    return sr, sr0, float(1 - stats.norm.cdf(z))


def wilson_lower(hits: int, n: int, z: float = 1.959963984540054) -> float | None:
    """Lower end of the Wilson score interval for a hit rate; None without observations."""
    if n <= 0:
        return None
    p = hits / n
    centre = p + z * z / (2 * n)
    margin = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return float((centre - margin) / (1 + z * z / n))
