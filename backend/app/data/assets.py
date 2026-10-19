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
    is_crypto = s.endswith("-USD") or f"{s}-USD" in CRYPTO_ASSETS
    return normalize_symbol(AssetType.CRYPTO if is_crypto else AssetType.STOCK, s)


def asset_type_of(symbol: str) -> AssetType:
    return AssetType.CRYPTO if symbol in CRYPTO_ASSETS else AssetType.STOCK


def trades_every_day(symbol: str) -> bool:
    """Coins trade 24/7, so their daily bars include weekends; stocks do not."""
    return symbol in CRYPTO_ASSETS
