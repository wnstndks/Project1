"""Load the training universe and context series through the price cache.

Only final bars are used (`final_only=True`): an unfinished session would leak an intraday
price into a row labelled as a close. The first load downloads full histories (about a
minute for the whole universe); later loads only fetch the missing days.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from app.data.provider import MarketDataError
from app.forecast import universe
from app.forecast.panel import AssetClass, AssetSeries, ContextSeries
from app.services.market_data import MarketDataService, SymbolNotFoundError

log = logging.getLogger(__name__)

# Long enough for two years of warm-up and several years of walk-forward folds.
DEFAULT_START = date(2015, 1, 1)


@dataclass
class Inputs:
    assets: dict[str, AssetSeries]
    context: list[ContextSeries]
    benchmarks: dict[AssetClass, pd.Series]
    missing: list[str] = field(default_factory=list)

    @property
    def data_end(self) -> date:
        return max(a.bars.index.max() for a in self.assets.values())

    def context_close(self, name: str) -> pd.Series | None:
        for c in self.context:
            if c.name == name:
                return c.bars["close"]
        return None


def bars_frame(bars) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "adj_close": [b.adj_close for b in bars],
            "volume": [b.volume for b in bars],
        },
        index=[b.date for b in bars],
    ).sort_index()


# How old reference assets may be at inference: they only feed cross-sectional ranks.
REFERENCE_MAX_AGE = timedelta(hours=20)


def _load(
    market: MarketDataService, symbol: str, start: date, max_age: timedelta | None = None
) -> pd.DataFrame | None:
    try:
        bars = market.get_history(symbol, start, final_only=True, max_age=max_age)
    except (SymbolNotFoundError, MarketDataError) as exc:
        log.warning("Skipping %s: %s", symbol, exc)
        return None
    return bars_frame(bars) if len(bars) >= 300 else None


def load_inputs(
    market: MarketDataService,
    held: Iterable[tuple[str, AssetClass]],
    start: date = DEFAULT_START,
    cached_reference: bool = False,
) -> Inputs:
    """Held symbols (in their USD form, e.g. BTC-USD) plus the reference universe.

    `cached_reference` refreshes reference assets at most every REFERENCE_MAX_AGE (for
    inference, where they only feed cross-sectional ranks). Held symbols and context series
    are always brought up to date.
    """
    held = dict(held)
    wanted = universe.reference_symbols()
    for symbol, cls in held.items():
        wanted.setdefault(symbol, cls)
    context_symbols = {symbol for symbol, _, _ in universe.CONTEXT.values()}

    assets: dict[str, AssetSeries] = {}
    missing: list[str] = []
    for symbol, cls in wanted.items():
        stale_ok = cached_reference and symbol not in held and symbol not in context_symbols
        df = _load(market, symbol, start, REFERENCE_MAX_AGE if stale_ok else None)
        if df is None:
            missing.append(symbol)
        else:
            assets[symbol] = AssetSeries(cls, df)

    context: list[ContextSeries] = []
    frames: dict[str, pd.DataFrame] = {}
    for name, (symbol, kind, lag) in universe.CONTEXT.items():
        df = assets[symbol].bars if symbol in assets else _load(market, symbol, start)
        if df is None:
            missing.append(symbol)
            continue
        frames[name] = df
        context.append(ContextSeries(name, df, lag, kind))
    if "vix" in frames and "vix3m" in frames:
        # Term structure: short-dated fear above long-dated marks stress.
        ratio = (frames["vix"]["close"] / frames["vix3m"]["close"]).dropna()
        context.append(
            ContextSeries(
                "vix_term", pd.DataFrame({"close": ratio}), universe.CONTEXT["vix"][2], "level"
            )
        )

    benchmarks: dict[AssetClass, pd.Series] = {}
    for cls, symbol in (("stock", universe.STOCK_BENCHMARK), ("crypto", universe.CRYPTO_BENCHMARK)):
        if symbol in assets:
            benchmarks[cls] = assets[symbol].bars["adj_close"]
    return Inputs(assets, context, benchmarks, missing)
