"""The (date, asset) panel: point-in-time features and forward targets.

Input bars are final daily bars (`get_history(final_only=True)`), one frame per asset with
columns open, high, low, close, adj_close, volume indexed by date.

Point-in-time rule: a row dated D may only use information published by that row's close.
A US stock's D bar closes 16:00 New York; a coin's D bar closes 00:00 UTC the next day,
which is after the US close. So coin rows may use that day's US market data, while stock
rows only see the previous day's coin data. Every context series declares the lag (in
calendar days) each asset class must apply; the join is then an as-of join.

Returns and targets are counted in calendar slots, not bars: every series is first laid
on its expected calendar (NYSE sessions for stocks, every day for coins), so a bar missing
from the data becomes a gap instead of silently turning a one-day return into two.
"""

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from app.data import calendar as market_calendar

AssetClass = Literal["stock", "crypto"]

# Horizons are named by calendar span so stocks and coins line up in a portfolio:
# a week is 5 NYSE sessions but 7 coin days.
HORIZONS: dict[str, dict[AssetClass, int]] = {
    "1d": {"stock": 1, "crypto": 1},
    "1w": {"stock": 5, "crypto": 7},
    "1m": {"stock": 21, "crypto": 30},
}
# Calendar days a horizon spans at most; used to purge training rows near a test block and
# to tell when a target is known. The longest spans in the NYSE calendar (unscheduled
# closures included, e.g. 2006-12-29 -> 2007-01-03 for one session); coins need 1/7/30.
# tests/test_panel.py checks these against app.data.calendar.
HORIZON_DAYS = {"1d": 5, "1w": 12, "1m": 35}

# Bump when features or targets are computed differently: it is part of the config hash.
# 2: calendar-based returns and targets, tolerant volatility scale, filled context gaps,
#    HORIZON_DAYS as true maximum spans (5/12/35).
PANEL_VERSION = 2
MIN_VOL = 1e-4
# Days of the 20-day window that must be present for the volatility used as a scale.
MIN_VOL_DAYS = 15
MIN_RANK_ASSETS = 5
# How many days a context series (index, rate) carries its last value over missing days.
CONTEXT_FILL_DAYS = 5
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


Calendar = Literal["xnys", "daily"]

# Market calendars live in app.data.calendar only, which answers per symbol; these symbols
# stand for each calendar (synthetic test symbols would not map to the right one).
_CALENDAR_SYMBOL: dict[Calendar, str] = {"xnys": "SPY", "daily": "BTC-USD"}
# Share of weekend bars above which a context series is taken to trade every day (coins
# have 2/7; an index or FX series has none or a stray few).
DAILY_WEEKEND_SHARE = 0.1


def xnys_sessions(start, end) -> pd.DatetimeIndex:
    """NYSE sessions from start to end inclusive (weekdays outside the known calendar)."""
    days = market_calendar.expected_dates(
        _CALENDAR_SYMBOL["xnys"], pd.Timestamp(start).date(), pd.Timestamp(end).date()
    )
    return _dates(days)


def expected_dates(index, calendar: Calendar) -> pd.DatetimeIndex:
    """Every date a series spanning `index` should have a bar on, plus the ones it has."""
    have = _dates(index)
    if have.empty:
        return have
    full = market_calendar.expected_dates(
        _CALENDAR_SYMBOL[calendar], have.min().date(), have.max().date()
    )
    return _dates(full).union(have)


def regularize(bars: pd.DataFrame, calendar: Calendar) -> pd.DataFrame:
    """Bars on their full calendar: dates without a bar become rows of NaN."""
    out = bars.copy()
    out.index = _dates(out.index)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out.reindex(expected_dates(out.index, calendar))


def asset_calendar(asset_class: AssetClass) -> Calendar:
    return "daily" if asset_class == "crypto" else "xnys"


def _log_ret(p: pd.Series, n: int) -> pd.Series:
    return np.log(p) - np.log(p.shift(n))


def asset_features(bars: pd.DataFrame, benchmark: pd.Series | None = None) -> pd.DataFrame:
    """Features for one asset. Row t uses bars up to and including t only.

    Returns are divided by the asset's own 20-day volatility so one pooled model can learn
    across a utility stock and a coin. Shifts count rows, so `bars` should already be on
    its calendar (`regularize`): a missing row would stretch every return across it.
    """
    p = bars["adj_close"]
    lr = np.log(p).diff()
    rv5 = lr.rolling(5).std()
    rv20 = lr.rolling(20).std()
    rv60 = lr.rolling(60).std()
    vol = _scale_vol(lr)
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
        b = pd.Series(benchmark.to_numpy(dtype=float), index=_dates(benchmark.index))
        b = b[~b.index.duplicated(keep="last")].reindex(_dates(bars.index))
        blr = pd.Series(np.log(b.to_numpy()), index=bars.index).diff()
        cov = lr.rolling(60, min_periods=40).cov(blr)
        beta = cov / blr.rolling(60, min_periods=40).var()
        out["beta60"] = beta
        resid = lr - beta * blr
        out["resid5"] = resid.rolling(5).sum() / (vol * np.sqrt(5))
    else:
        out["beta60"] = np.nan
        out["resid5"] = np.nan
    return out


def _scale_vol(lr: pd.Series) -> pd.Series:
    """20-day volatility used to standardize returns. A missing day or two in the window
    still gives an estimate, so one gap does not blank out the scale for 20 days."""
    return lr.rolling(20, min_periods=MIN_VOL_DAYS).std().clip(lower=MIN_VOL)


def asset_targets(bars: pd.DataFrame, asset_class: AssetClass) -> pd.DataFrame:
    """Forward targets. These look into the future by design and are never features.

    fr_{h}: log return from t to t+h bars. scale_{h}: the volatility used to standardize it
    (known at t). y_{h} = fr / scale is what the models learn.
    """
    p = bars["adj_close"]
    log_p = np.log(p)
    vol = _scale_vol(log_p.diff())
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
        # A series with weekend bars trades every day; everything else follows the NYSE.
        # Over a missing day the last value carries (briefly), so changes span dates.
        weekend_share = (_dates(c.bars.index).dayofweek >= 5).mean() if len(c.bars) else 0.0
        calendar = "daily" if weekend_share > DAILY_WEEKEND_SHARE else "xnys"
        bars = regularize(c.bars[["close"]], calendar).ffill(limit=CONTEXT_FILL_DAYS)
        p = bars["close"]
        f = pd.DataFrame(index=bars.index)
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
        bars = regularize(a.bars, asset_calendar(a.asset_class))
        has_bar = bars["adj_close"].notna().to_numpy()
        bench = (benchmarks or {}).get(a.asset_class)
        f = asset_features(bars, bench)
        t = asset_targets(bars, a.asset_class)
        # Calendar slots without a bar only served to keep returns aligned to dates.
        df = pd.concat([f, t], axis=1)[has_bar]
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


def latest_ranks(
    panel: pd.DataFrame,
    rows: pd.DataFrame,
    max_age_days: int = 4,
    peers: Collection[str] | None = None,
) -> pd.DataFrame:
    """Recompute rank features for served rows against every asset's newest row.

    At inference the newest date may only have rows for the held symbols (reference assets
    refresh less often), and ranking within that date alone would compare a stock with two
    or three others instead of the ~45 the model learned from. Peers here are each asset's
    latest row in the same class from the last few days.

    `peers` limits the comparison to the symbols the model was trained with (the run's
    `meta["universe"]`), so a reference list edited after training does not change the
    rank features the model sees.
    """
    latest = panel.sort_values("date").groupby("symbol").tail(1)
    if peers is not None:
        latest = latest[latest["symbol"].isin(set(peers))]
    out = rows.copy()
    for idx, r in rows.iterrows():
        group = latest[
            (latest["asset_class"] == r["asset_class"])
            & (latest["symbol"] != r["symbol"])
            & (latest["date"] <= r["date"])
            & (latest["date"] >= r["date"] - pd.Timedelta(days=max_age_days))
        ]
        for col in ("r5", "r20", "rv20", "drawdown252"):
            values = group[col].dropna().to_numpy()
            v = r[col]
            if pd.isna(v) or len(values) + 1 < MIN_RANK_ASSETS:
                out.at[idx, f"rank_{col}"] = np.nan
                continue
            # Same convention as pandas rank(pct=True): average rank of ties, over n.
            rank = (values < v).sum() + ((values == v).sum() + 2) / 2
            out.at[idx, f"rank_{col}"] = rank / (len(values) + 1)
    return out
