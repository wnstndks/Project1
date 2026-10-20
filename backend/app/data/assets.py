"""Supported assets and symbol normalization.

Only four coins are supported by design. Stocks are any US ticker.
"""

import re

from app.db.models import AssetType

CRYPTO_ASSETS: dict[str, str] = {
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
    "XRP-USD": "XRP",
    "SOL-USD": "Solana",
}

# Upbit KRW market for each supported coin (prices include the "kimchi premium").
UPBIT_MARKETS: dict[str, str] = {
    "BTC-USD": "KRW-BTC",
    "ETH-USD": "KRW-ETH",
    "XRP-USD": "KRW-XRP",
    "SOL-USD": "KRW-SOL",
}

# yfinance symbol for the USD/KRW exchange rate (KRW per 1 USD).
FX_USDKRW = "KRW=X"

_STOCK_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


class UnsupportedSymbolError(ValueError):
    pass


def normalize_symbol(asset_type: AssetType, symbol: str) -> str:
    """Return the canonical provider symbol, e.g. "btc" -> "BTC-USD", " aapl " -> "AAPL"."""
    s = symbol.strip().upper()
    if asset_type == AssetType.CRYPTO:
        if not s.endswith("-USD"):
            s = f"{s}-USD"
        if s not in CRYPTO_ASSETS:
            supported = ", ".join(k.removesuffix("-USD") for k in CRYPTO_ASSETS)
            raise UnsupportedSymbolError(f"Unsupported coin '{symbol}'. Supported: {supported}")
        return s

    if s.endswith("-USD") or not _STOCK_SYMBOL.match(s):
        raise UnsupportedSymbolError(f"Invalid stock symbol '{symbol}'")
    return s


def resolve_symbol(raw: str) -> str:
    """Guess the asset type from user input ("AAPL", "btc", "SOL-USD") and normalize it."""
    s = raw.strip().upper()
    if s in UPBIT_MARKETS.values():
        return s  # an Upbit KRW market, e.g. "KRW-BTC"
    is_crypto = s.endswith("-USD") or f"{s}-USD" in CRYPTO_ASSETS
    return normalize_symbol(AssetType.CRYPTO if is_crypto else AssetType.STOCK, s)


def asset_type_of(symbol: str) -> AssetType:
    is_coin = symbol in CRYPTO_ASSETS or symbol in UPBIT_MARKETS.values()
    return AssetType.CRYPTO if is_coin else AssetType.STOCK


def base_symbol(symbol: str) -> str:
    """The canonical symbol for an Upbit market: "KRW-BTC" -> "BTC-USD"."""
    for base, market in UPBIT_MARKETS.items():
        if market == symbol:
            return base
    return symbol


def trades_every_day(symbol: str) -> bool:
    """Coins trade 24/7, so their daily bars include weekends; stocks do not.

    Any yfinance "-USD" pair counts: the forecaster trains on more coins than the four
    users can hold.
    """
    return symbol.endswith("-USD") or symbol in UPBIT_MARKETS.values()
