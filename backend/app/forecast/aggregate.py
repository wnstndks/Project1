"""Portfolio-level forecast: from per-asset ranges to the range of the total in won.

Per-asset forecasts are quantiles of each asset's own return. Adding them up would ignore
that assets fall together, so paths are simulated instead:
- dependence: a Student-t copula (5 dof: joint crashes are more common than a normal
  copula allows) with a Ledoit-Wolf shrunk correlation of recent daily returns, USD/KRW
  included;
- marginals: a two-piece Student-t through each asset's 10/50/90% quantiles, so skewed
  forecasts stay skewed;
- won value: every holding is a dollar asset (coins on Upbit track the dollar price times
  the exchange rate), so its won return is its dollar return plus the USD/KRW return.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.covariance import LedoitWolf

DOF = 5
T90 = stats.t.ppf(0.9, DOF)
FX = "__usdkrw__"


@dataclass(frozen=True)
class AssetForecast:
    symbol: str
    value_krw: float
    # Quantiles of the log return over the horizon, in dollars.
    q10: float
    q50: float
    q90: float


@dataclass(frozen=True)
class PortfolioForecast:
    value_krw: float
    p10: float
    p50: float
    p90: float
    mean: float
    var95: float  # loss not exceeded in 95% of paths (positive number, won)
    es95: float  # average loss in the worst 5% of paths
    paths: int


def correlation(returns: pd.DataFrame, min_rows: int = 120) -> np.ndarray:
    """Shrunk correlation of daily returns (columns = assets). Identity when too short."""
    data = returns.dropna()
    k = returns.shape[1]
    if len(data) < min_rows or k < 2:
        return np.eye(k)
    z = (data - data.mean()) / data.std(ddof=0).replace(0, np.nan)
    cov = LedoitWolf().fit(z.fillna(0).to_numpy()).covariance_
    d = np.sqrt(np.diag(cov))
    corr = cov / np.outer(d, d)
    np.fill_diagonal(corr, 1.0)
    return corr


def _marginal(u: np.ndarray, q10: float, q50: float, q90: float) -> np.ndarray:
    z = stats.t.ppf(u, DOF)
    lo = max(q50 - q10, 1e-9) / T90
    hi = max(q90 - q50, 1e-9) / T90
    return q50 + np.where(z < 0, z * lo, z * hi)


def simulate(
    assets: list[AssetForecast],
    fx: AssetForecast,
    corr: np.ndarray,
    paths: int = 10_000,
    seed: int = 0,
) -> PortfolioForecast:
    """`corr` is ordered as `assets` followed by the exchange rate."""
    total = sum(a.value_krw for a in assets)
    if not assets or total <= 0:
        return PortfolioForecast(total, total, total, total, total, 0.0, 0.0, 0)
    rng = np.random.default_rng(seed)
    k = len(assets) + 1
    chol = np.linalg.cholesky(corr + 1e-9 * np.eye(k))
    normal = rng.standard_normal((paths, k)) @ chol.T
    w = rng.chisquare(DOF, size=(paths, 1)) / DOF
    u = stats.t.cdf(normal / np.sqrt(w), DOF)
    u = np.clip(u, 1e-12, 1 - 1e-12)

    fx_ret = _marginal(u[:, -1], fx.q10, fx.q50, fx.q90)
    end = np.zeros(paths)
    for i, a in enumerate(assets):
        r = _marginal(u[:, i], a.q10, a.q50, a.q90)
        end += a.value_krw * np.exp(r + fx_ret)
    loss = total - end
    var95 = float(np.quantile(loss, 0.95))
    return PortfolioForecast(
        value_krw=total,
        p10=float(np.quantile(end, 0.1)),
        p50=float(np.quantile(end, 0.5)),
        p90=float(np.quantile(end, 0.9)),
        mean=float(end.mean()),
        var95=max(var95, 0.0),
        es95=max(float(loss[loss >= var95].mean()), 0.0),
        paths=paths,
    )


def fx_forecast(usdkrw: pd.Series, days: int) -> AssetForecast:
    """USD/KRW over the horizon: median unchanged, EWMA volatility, fat tails."""
    lr = np.log(usdkrw).diff().dropna()
    sigma = (
        float(np.sqrt((lr**2).ewm(alpha=0.06, adjust=False).mean().iloc[-1])) if len(lr) else 0.005
    )
    # Trading days in `days` calendar days, roughly.
    s = sigma * np.sqrt(max(1, round(days * 5 / 7))) * T90 * np.sqrt((DOF - 2) / DOF)
    return AssetForecast(FX, 0.0, -s, 0.0, s)
