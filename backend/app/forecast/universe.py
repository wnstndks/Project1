"""What the pooled model trains on: the user's holdings plus a fixed reference universe.

More assets mean more independent examples of the same patterns (a volatility spike looks
alike in XLE and NVDA), which is what lets a GBDT beat per-symbol models. Predictions are
only served for held symbols.

Survivorship bias: these are today's large, liquid names. Delisted stocks are missing, so
historical returns of the universe look better than a real investor would have seen. For
coins, where collapses are common, former top-15 coins that lost 80-99% are included as
training-only assets so the model does not learn that every dip recovers.
"""

from collections.abc import Mapping

from app.forecast.panel import AssetClass

INDEX_ETFS = ["SPY", "QQQ", "IWM", "DIA"]
SECTOR_ETFS = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
LARGE_CAPS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B", "JPM", "V",
    "UNH", "XOM", "JNJ", "PG", "MA", "HD", "COST", "AVGO", "LLY", "ABBV",
    "MRK", "PEP", "KO", "WMT", "BAC", "CVX", "ORCL", "ADBE", "AMD", "NFLX",
]  # fmt: skip
COINS = [
    "BTC-USD", "ETH-USD", "XRP-USD", "SOL-USD", "BNB-USD", "ADA-USD", "DOGE-USD",
    "TRX-USD", "LTC-USD", "LINK-USD", "AVAX-USD", "DOT-USD", "BCH-USD", "XLM-USD", "ETC-USD",
]  # fmt: skip
# Fallen former leaders (still quoted on Yahoo), for training only. XMR and ZEC were
# dropped: they trade within about a third of their highs, so they are not collapses.
FALLEN_COINS = [
    "EOS-USD", "NEO-USD", "DASH-USD", "XEM-USD", "BSV-USD", "FTT-USD", "LUNC-USD", "ICP-USD",
]  # fmt: skip

# What strategies trade (D-008): index and sector ETFs, whose membership does not depend
# on knowing today's winners, and the four supported coins. LARGE_CAPS is picked with
# hindsight, so results on it are reported separately and never used to adopt a strategy.
STRATEGY_STOCKS = INDEX_ETFS + SECTOR_ETFS
STRATEGY_COINS = ["BTC-USD", "ETH-USD", "XRP-USD", "SOL-USD"]

STOCK_BENCHMARK = "SPY"
CRYPTO_BENCHMARK = "BTC-USD"

# name -> (provider symbol, kind, lag in days for stock rows, lag for coin rows).
# Coin bars close at 00:00 UTC, after the US close: stock rows see them a day late. Yahoo's
# USD/KRW bar for a date can close after either, so both classes wait a day for it.
# VIX, VIX3M and the 10-year yield may settle after 16:00 New York (VIX at 16:15); until
# their close time is confirmed, stock rows wait a day for them too.
CONTEXT: Mapping[str, tuple[str, str, Mapping[AssetClass, int]]] = {
    "vix": ("^VIX", "level", {"stock": 1, "crypto": 0}),
    "vix3m": ("^VIX3M", "level", {"stock": 1, "crypto": 0}),
    "spy": ("SPY", "returns", {"stock": 0, "crypto": 0}),
    "btc": ("BTC-USD", "returns", {"stock": 1, "crypto": 0}),
    "usdkrw": ("KRW=X", "returns", {"stock": 1, "crypto": 1}),
    # The dollar index settles an hour after the US close: stock rows wait a day.
    "dxy": ("DX-Y.NYB", "returns", {"stock": 1, "crypto": 0}),
    "us10y": ("^TNX", "diff", {"stock": 1, "crypto": 0}),
}


def reference_symbols() -> dict[str, AssetClass]:
    out: dict[str, AssetClass] = {s: "stock" for s in INDEX_ETFS + SECTOR_ETFS + LARGE_CAPS}
    out |= {s: "crypto" for s in COINS + FALLEN_COINS}
    return out


def strategy_symbols() -> dict[str, AssetClass]:
    out: dict[str, AssetClass] = {s: "stock" for s in STRATEGY_STOCKS}
    out |= {s: "crypto" for s in STRATEGY_COINS}
    return out


def universe_groups() -> dict[str, str]:
    """Reference symbol -> what its results may be used for: `strategy` (adoption),
    `large_cap` (reported separately, ISSUE-020) or `training_only`."""
    out = {s: "training_only" for s in reference_symbols()}
    out |= {s: "large_cap" for s in LARGE_CAPS}
    out |= {s: "strategy" for s in strategy_symbols()}
    return out
