"""Monte Carlo projection of future net worth for the financial portfolio.

Model
- Two asset classes (US stocks, crypto), simulated monthly with correlated lognormal returns.
- Volatility and correlation come from the holdings' own monthly history (value-weighted per
  class). Classes with no holdings use a proxy (SPY / BTC-USD).
- Expected returns default to conservative long-run assumptions instead of the historical mean:
  a few years of crypto history implies absurd growth, and means are far noisier to estimate
  than volatility. The historical mean is still reported so the user can compare and override.
- Monthly contributions (KRW) are split by contribution weights; no rebalancing.
- Everything is in KRW at today's USD/KRW rate (currency risk is not simulated).
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.db.models import AssetType
from app.services.market_data import MarketDataService
from app.services.portfolio import PortfolioService

CLASSES = (AssetType.STOCK, AssetType.CRYPTO)
PROXY = {AssetType.STOCK: "SPY", AssetType.CRYPTO: "BTC-USD"}
DEFAULT_RETURN_PCT = {AssetType.STOCK: 7.0, AssetType.CRYPTO: 10.0}
LOOKBACK_YEARS = 5
# Volatility from fewer monthly returns than this is too noisy (or NaN): use the proxy.
MIN_MONTHS = 12


@dataclass
class ClassStats:
    value_krw: float
    weight_pct: float
    hist_return_pct: float  # annualized arithmetic mean of monthly returns
    vol_pct: float  # annualized volatility
    default_return_pct: float
    proxy: str | None  # set when the class has no holdings


@dataclass
class Assumptions:
    start_value_krw: float
    usd_krw: float
    classes: dict[AssetType, ClassStats]
    correlation: float
    lookback_years: int = LOOKBACK_YEARS


@dataclass
class ProjectionParams:
    years: int = 10
    monthly_contribution_krw: float = 0.0
    inflation_pct: float = 2.5
    simulations: int = 5000
    seed: int = 42
    return_pct: dict[AssetType, float] = field(default_factory=dict)
    vol_pct: dict[AssetType, float] = field(default_factory=dict)
    # Share of each monthly contribution going to stocks; defaults to the current weight.
    contribution_stock_pct: float | None = None
    target_krw: float | None = None


@dataclass
class YearPoint:
    year: int
    contributed_krw: float
    p10: float
    p50: float
    p90: float
    p10_real: float
    p50_real: float
    p90_real: float


@dataclass
class ProjectionResult:
    years: list[YearPoint]
    final_mean: float
    prob_target: float | None
    prob_loss: float  # final value below total money put in
    used_return_pct: dict[AssetType, float]
    used_vol_pct: dict[AssetType, float]
    correlation: float


def simulate(
    start_values: np.ndarray,
    annual_return: np.ndarray,
    annual_vol: np.ndarray,
    correlation: float,
    params: ProjectionParams,
    contribution_weights: np.ndarray,
) -> ProjectionResult:
    """Pure simulation; all money in KRW. Arrays are ordered like CLASSES."""
    months = params.years * 12
    n = params.simulations
    rng = np.random.default_rng(params.seed)

    sigma_m = annual_vol / np.sqrt(12)
    # Lognormal drift chosen so the *expected* annual growth equals 1 + annual_return.
    mu_m = np.log1p(annual_return) / 12 - sigma_m**2 / 2
    corr = np.array([[1.0, correlation], [correlation, 1.0]])
    chol = np.linalg.cholesky(corr + np.eye(2) * 1e-12)

    values = np.tile(start_values.astype(float), (n, 1))
    contribution = params.monthly_contribution_krw * contribution_weights
    contributed = float(start_values.sum())
    inflation_m = (1 + params.inflation_pct / 100) ** (1 / 12)

    def point(year: int, totals: np.ndarray) -> YearPoint:
        p10, p50, p90 = np.percentile(totals, [10, 50, 90])
        deflator = inflation_m ** (year * 12)
        return YearPoint(
            year=year,
            contributed_krw=round(contributed),
            p10=round(p10),
            p50=round(p50),
            p90=round(p90),
            p10_real=round(p10 / deflator),
            p50_real=round(p50 / deflator),
            p90_real=round(p90 / deflator),
        )

    points = [point(0, values.sum(axis=1))]
    for m in range(1, months + 1):
        z = rng.standard_normal((n, 2)) @ chol.T
        values *= np.exp(mu_m + sigma_m * z)
        values += contribution
        contributed += params.monthly_contribution_krw
        if m % 12 == 0:
            points.append(point(m // 12, values.sum(axis=1)))

    final = values.sum(axis=1)
    prob_target = None
    if params.target_krw:
        prob_target = float(np.mean(final >= params.target_krw) * 100)
    return ProjectionResult(
        years=points,
        final_mean=round(float(final.mean())),
        prob_target=prob_target,
        prob_loss=float(np.mean(final < contributed) * 100),
        used_return_pct=dict(zip(CLASSES, (annual_return * 100).round(4).tolist(), strict=True)),
        used_vol_pct=dict(zip(CLASSES, (annual_vol * 100).round(4).tolist(), strict=True)),
        correlation=correlation,
    )


class ProjectionService:
    def __init__(self, market: MarketDataService, portfolio: PortfolioService) -> None:
        self.market = market
        self.portfolio = portfolio

    def assumptions(self) -> Assumptions:
        holdings = self.portfolio.holdings()
        usd_krw = self.market.usd_krw().price
        start = date.today() - timedelta(days=365 * LOOKBACK_YEARS)

        class_returns: dict[AssetType, pd.Series] = {}
        stats: dict[AssetType, ClassStats] = {}
        total = sum(float(h.market_value_krw) for h in holdings)
        for cls in CLASSES:
            mine = [h for h in holdings if h.asset_type == cls]
            weights = {h.symbol: float(h.market_value) for h in mine} or {PROXY[cls]: 1.0}
            series = self._class_monthly_returns(weights, start)
            proxied = not mine
            if len(series) < MIN_MONTHS:
                series = self._class_monthly_returns({PROXY[cls]: 1.0}, start)
                proxied = True
            class_returns[cls] = series
            value = sum(float(h.market_value_krw) for h in mine)
            stats[cls] = ClassStats(
                value_krw=value,
                weight_pct=value / total * 100
                if total
                else (100.0 if cls == AssetType.STOCK else 0),
                hist_return_pct=float(series.mean() * 12 * 100),
                vol_pct=float(series.std() * np.sqrt(12) * 100),
                default_return_pct=DEFAULT_RETURN_PCT[cls],
                proxy=PROXY[cls] if proxied else None,
            )

        joined = pd.concat(class_returns.values(), axis=1, join="inner").dropna()
        corr = float(joined.corr().iloc[0, 1]) if len(joined) > 12 else 0.0
        return Assumptions(
            start_value_krw=total,
            usd_krw=usd_krw,
            classes=stats,
            correlation=0.0 if np.isnan(corr) else corr,
        )

    def run(self, params: ProjectionParams) -> ProjectionResult:
        a = self.assumptions()
        start_values = np.array([a.classes[c].value_krw for c in CLASSES])
        annual_return = np.array(
            [params.return_pct.get(c, a.classes[c].default_return_pct) / 100 for c in CLASSES]
        )
        annual_vol = np.array([params.vol_pct.get(c, a.classes[c].vol_pct) / 100 for c in CLASSES])
        stock_share = (
            params.contribution_stock_pct
            if params.contribution_stock_pct is not None
            else a.classes[AssetType.STOCK].weight_pct
        ) / 100
        weights = np.array([stock_share, 1 - stock_share])
        return simulate(start_values, annual_return, annual_vol, a.correlation, params, weights)

    def _class_monthly_returns(self, weights: dict[str, float], start: date) -> pd.Series:
        """Value-weighted monthly simple returns of a basket, renormalized over available data."""
        closes = {}
        for symbol in weights:
            bars = self.market.get_history(symbol, start)
            s = pd.Series([b.adj_close for b in bars], index=pd.to_datetime([b.date for b in bars]))
            closes[symbol] = s.resample("ME").last()
        returns = pd.DataFrame(closes).pct_change(fill_method=None).iloc[1:]
        w = pd.Series(weights)
        available = returns.notna()
        weighted = (returns.fillna(0) * w).sum(axis=1)
        norm = (available * w).sum(axis=1)
        return (weighted / norm.replace(0, np.nan)).dropna()
