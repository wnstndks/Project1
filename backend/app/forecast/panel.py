"""The (date, asset) panel: point-in-time features and forward targets.

Input bars are final daily bars (`get_history(final_only=True)`), one frame per asset with
columns open, high, low, close, adj_close, volume indexed by date.

Point-in-time rule: a row dated D may only use information published by that row's close.
A US stock's D bar closes 16:00 New York; a coin's D bar closes 00:00 UTC the next day,
which is after the US close. So coin rows may use that day's US market data, while stock
rows only see the previous day's coin data. Every context series declares the lag (in
calendar days) each asset class must apply; the join is then an as-of join.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

AssetClass = Literal["stock", "crypto"]

# Horizons are named by calendar span so stocks and coins line up in a portfolio:
# a week is 5 NYSE sessions but 7 coin days.
HORIZONS: dict[str, dict[AssetClass, int]] = {
    "1d": {"stock": 1, "crypto": 1},
    "1w": {"stock": 5, "crypto": 7},
    "1m": {"stock": 21, "crypto": 30},
}
# Calendar days a horizon spans at most; used to purge training rows near a test block.
HORIZON_DAYS = {"1d": 4, "1w": 9, "1m": 32}

MIN_VOL = 1e-4
MIN_RANK_ASSETS = 5
ASSET_FEATURES = [
    "r1",
    "r5",
    "r20",
    "r60",
    "rv5",
    "rv20",
    "rv60",
    "vol_ratio",
    "ewma_ratio",
    "parkinson20",
    "garman_klass20",
    "drawdown252",
    "ma_gap50",
    "volume_z",
    "beta60",
    "resid5",
]
RANK_FEATURES = ["rank_r5", "rank_r20", "rank_rv20", "rank_drawdown252"]


@dataclass(frozen=True)
class ContextSeries:
    """A market-wide series joined onto every asset row (index level, FX rate, ...)."""

    name: str
    bars: pd.DataFrame
    # Calendar days each asset class must wait before this series' bar D is known.
    lag: Mapping[AssetClass, int]
    # "level" adds the value itself; "returns" adds 5/20-day log changes; "diff" for yields.
    kind: Literal["level", "returns", "diff"] = "returns"


@dataclass(frozen=True)
class AssetSeries:
    asset_class: AssetClass
    bars: pd.DataFrame


def _dates(index) -> pd.DatetimeIndex:
    """Bars are indexed by `date`; joins need one datetime resolution on both sides."""
    return pd.DatetimeIndex(pd.to_datetime(index)).as_unit("ns")


def _log_ret(p: pd.Series, n: int) -> pd.Series:
    return np.log(p) - np.log(p.shift(n))


def asset_features(bars: pd.DataFrame, benchmark: pd.Series | None = None) -> pd.DataFrame:
    """Features for one asset. Row t uses bars up to and including t only.

    Returns are divided by the asset's own 20-day volatility so one pooled model can learn
    across a utility stock and a coin.
    """
    p = bars["adj_close"]
    lr = np.log(p).diff()
    rv5 = lr.rolling(5).std()
    rv20 = lr.rolling(20).std()
    rv60 = lr.rolling(60).std()
    vol = rv20.clip(lower=MIN_VOL)
    # RiskMetrics EWMA (lambda 0.94): reacts faster than the 20-day window.
    ewma = np.sqrt((lr**2).ewm(alpha=0.06, adjust=False).mean())

    out = pd.DataFrame(index=bars.index)
    out["r1"] = lr / vol
    for n in (5, 20, 60):
        out[f"r{n}"] = _log_ret(p, n) / (vol * np.sqrt(n))
    out["rv5"], out["rv20"], out["rv60"] = rv5, rv20, rv60
    out["vol_ratio"] = rv5 / rv60.clip(lower=MIN_VOL)
    out["ewma_ratio"] = ewma / vol

    # Range-based volatility: high/low/open are raw prices, but their ratios within a
    # day are unaffected by adjustment.
    hl = np.log(bars["high"] / bars["low"]).replace([np.inf, -np.inf], np.nan)
    co = np.log(bars["close"] / bars["open"]).replace([np.inf, -np.inf], np.nan)
    out["parkinson20"] = np.sqrt((hl**2).rolling(20).mean() / (4 * np.log(2)))
    gk = 0.5 * hl**2 - (2 * np.log(2) - 1) * co**2
    out["garman_klass20"] = np.sqrt(gk.rolling(20).mean().clip(lower=0))

    log_p = np.log(p)
    out["drawdown252"] = log_p - log_p.rolling(252, min_periods=60).max()
    out["ma_gap50"] = (log_p - log_p.rolling(50).mean()) / vol
    lv = np.log1p(bars["volume"].clip(lower=0))
    out["volume_z"] = (lv - lv.rolling(60).mean()) / lv.rolling(60).std().replace(0, np.nan)

    if benchmark is not None:
        b = benchmark.reindex(bars.index)
        blr = np.log(b).diff()
        cov = lr.rolling(60, min_periods=40).cov(blr)
        beta = cov / blr.rolling(60, min_periods=40).var()
        out["beta60"] = beta
        resid = lr - beta * blr
        out["resid5"] = resid.rolling(5).sum() / (vol * np.sqrt(5))
    else:
        out["beta60"] = np.nan
        out["resid5"] = np.nan
    return out


def asset_targets(bars: pd.DataFrame, asset_class: AssetClass) -> pd.DataFrame:
    """Forward targets. These look into the future by design and are never features.

    fr_{h}: log return from t to t+h bars. scale_{h}: the volatility used to standardize it
    (known at t). y_{h} = fr / scale is what the models learn.
    """
    p = bars["adj_close"]
    log_p = np.log(p)
    vol = np.log(p).diff().rolling(20).std().clip(lower=MIN_VOL)
    out = pd.DataFrame(index=bars.index)
    for name, steps in HORIZONS.items():
        h = steps[asset_class]
        fr = log_p.shift(-h) - log_p
        scale = vol * np.sqrt(h)
        out[f"fr_{name}"] = fr
        out[f"scale_{name}"] = scale
        out[f"y_{name}"] = fr / scale
    return out


def context_features(context: list[ContextSeries]) -> dict[AssetClass, pd.DataFrame]:
    """Context columns per asset class, already lagged so an as-of join on D is safe."""
    out: dict[AssetClass, list[pd.DataFrame]] = {"stock": [], "crypto": []}
    for c in context:
        p = c.bars["close"]
        f = pd.DataFrame(index=c.bars.index)
        if c.kind == "level":
            f[c.name] = p
            f[f"{c.name}_chg5"] = np.log(p) - np.log(p.shift(5))
        elif c.kind == "diff":
            f[f"{c.name}_chg20"] = p - p.shift(20)
        else:
            f[f"{c.name}_r5"] = _log_ret(p, 5)
            f[f"{c.name}_r20"] = _log_ret(p, 20)
            f[f"{c.name}_rv20"] = np.log(p).diff().rolling(20).std()
        for cls in ("stock", "crypto"):
            lagged = f.copy()
            lagged.index = _dates(lagged.index) + pd.Timedelta(days=c.lag[cls])
            out[cls].append(lagged)
    return {
        cls: (pd.concat(frames, axis=1, sort=True) if frames else pd.DataFrame())
        for cls, frames in out.items()
    }


def _asof_join(rows: pd.DataFrame, ctx: pd.DataFrame) -> pd.DataFrame:
    if ctx.empty:
        return rows
    # Each context column is forward-filled on its own: series have different calendars.
    ctx = ctx.ffill()
    ctx = ctx.reset_index(names="date").sort_values("date")
    merged = pd.merge_asof(rows.sort_values("date"), ctx, on="date", direction="backward")
    return merged


def build_panel(
    assets: Mapping[str, AssetSeries],
    context: list[ContextSeries] = (),
    benchmarks: Mapping[AssetClass, pd.Series] | None = None,
) -> pd.DataFrame:
    """Long panel with one row per (date, symbol): features, context and targets.

    `benchmarks` gives the series each class's beta and residual return are measured
    against (SPY for stocks, BTC for coins).
    """
    ctx = context_features(list(context))
    frames = []
    for symbol, a in assets.items():
        bars = a.bars.sort_index()
        bench = (benchmarks or {}).get(a.asset_class)
        f = asset_features(bars, bench)
        t = asset_targets(bars, a.asset_class)
        df = pd.concat([f, t], axis=1)
        df.index = _dates(df.index)
        df = df.reset_index(names="date")
        df["symbol"] = symbol
        df["asset_class"] = a.asset_class
        frames.append(_asof_join(df, ctx[a.asset_class]))
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.sort_values(["date", "symbol"], ignore_index=True)

    # Cross-sectional ranks within each asset class on each date: comparisons between
    # assets carry information a single series does not.
    # Too few assets make ranks meaningless (BTC alone in 2016 always ranks 1.0).
    grouped = panel.groupby(["date", "asset_class"])
    enough = grouped["symbol"].transform("size") >= MIN_RANK_ASSETS
    for col in ("r5", "r20", "rv20", "drawdown252"):
        panel[f"rank_{col}"] = grouped[col].rank(pct=True).where(enough)
    panel["is_crypto"] = (panel["asset_class"] == "crypto").astype(float)
    return panel


def feature_columns(panel: pd.DataFrame) -> list[str]:
    """Every model input: asset, rank and context features (never targets)."""
    excluded = {"date", "symbol", "asset_class"}
    return [
        c for c in panel.columns if c not in excluded and not c.startswith(("fr_", "scale_", "y_"))
    ]


def latest_ranks(panel: pd.DataFrame, rows: pd.DataFrame, max_age_days: int = 4) -> pd.DataFrame:
    """Recompute rank features for served rows against every asset's newest row.

    At inference the newest date may only have rows for the held symbols (reference assets
    refresh less often), and ranking within that date alone would compare a stock with two
    or three others instead of the ~45 the model learned from. Peers here are each asset's
    latest row in the same class from the last few days.
    """
    latest = panel.sort_values("date").groupby("symbol").tail(1)
    out = rows.copy()
    for idx, r in rows.iterrows():
        peers = latest[
            (latest["asset_class"] == r["asset_class"])
            & (latest["symbol"] != r["symbol"])
            & (latest["date"] <= r["date"])
            & (latest["date"] >= r["date"] - pd.Timedelta(days=max_age_days))
        ]
        for col in ("r5", "r20", "rv20", "drawdown252"):
            values = peers[col].dropna().to_numpy()
            v = r[col]
            if pd.isna(v) or len(values) + 1 < MIN_RANK_ASSETS:
                out.at[idx, f"rank_{col}"] = np.nan
                continue
            # Same convention as pandas rank(pct=True): average rank of ties, over n.
            rank = (values < v).sum() + ((values == v).sum() + 2) / 2
            out.at[idx, f"rank_{col}"] = rank / (len(values) + 1)
    return out
