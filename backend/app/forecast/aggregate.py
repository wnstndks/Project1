"""Portfolio-level forecast: from per-asset ranges to the range of the total in won.

Per-asset forecasts are quantiles of each asset's own return. Adding them up would ignore
that assets fall together, so paths are simulated instead:
- dependence: a Student-t copula (5 dof: joint crashes are more common than a normal
  copula allows) with a Ledoit-Wolf shrunk correlation of recent daily returns, USD/KRW
  included;
- marginals: a two-piece Student-t through each asset's 10/50/90% quantiles, so skewed
  forecasts stay skewed;
- won value: every holding is a dollar asset (coins on Upbit track the dollar price times
  the exchange rate), so its won return is its dollar return plus the USD/KRW return;
- the kimchi premium: coins held on Upbit also carry the change in their premium over the
  dollar price. The premium mean-reverts (a pooled AR(1) on the log premium), so a high
  premium is expected to shrink: a drift, not just extra noise. The four coins' premia
  move together, so one shared shock drives them.
"""

from collections.abc import Mapping
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


@dataclass(frozen=True)
class PremiumModel:
    """Daily AR(1) of the log kimchi premium: p[t+1] - mu = phi (p[t] - mu) + e."""

    mu: float
    phi: float
    sigma: float

    def horizon(self, current: float, days: int) -> tuple[float, float]:
        """Mean and standard deviation of the premium's change over `days`."""
        decay = self.phi**days
        mean = (self.mu - current) * (1 - decay)
        if self.phi >= 1:
            return mean, self.sigma * np.sqrt(days)
        sd = self.sigma * np.sqrt((1 - decay**2) / (1 - self.phi**2))
        return float(mean), float(sd)


def fit_premium(premia: Mapping[str, pd.Series], min_rows: int = 60) -> PremiumModel | None:
    """Pooled fit over the coins' daily log premia (common mean and persistence)."""
    series = [s.dropna() for s in premia.values() if len(s.dropna()) >= min_rows]
    if not series:
        return None
    mu = float(np.mean(np.concatenate([s.to_numpy() for s in series])))
    x = np.concatenate([s.to_numpy()[:-1] - mu for s in series])
    y = np.concatenate([s.to_numpy()[1:] - mu for s in series])
    phi = float(np.clip(x @ y / max(x @ x, 1e-12), 0.0, 0.999))
    sigma = float(np.std(y - phi * x))
    return PremiumModel(mu, phi, sigma)


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
    premium: Mapping[str, tuple[float, float]] | None = None,
) -> PortfolioForecast:
    """`corr` is ordered as `assets` followed by the exchange rate. `premium` maps the
    symbols held on Upbit to the (mean, sd) of their premium change over the horizon."""
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
    shock = rng.standard_normal(paths)  # one premium shock shared by every Upbit coin
    end = np.zeros(paths)
    for i, a in enumerate(assets):
        r = _marginal(u[:, i], a.q10, a.q50, a.q90) + fx_ret
        if premium and a.symbol in premium:
            mean, sd = premium[a.symbol]
            r = r + mean + sd * shock
        end += a.value_krw * np.exp(r)
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
