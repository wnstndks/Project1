from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class Bar:
    date: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    volume: float


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: float
    as_of: datetime


@dataclass(frozen=True)
class CorporateEvent:
    date: date  # ex-date
    kind: str  # "split" or "dividend"
    value: Decimal  # split ratio, or dividend per share in the quote currency


class MarketDataError(Exception):
    """The provider failed (network error, upstream change, rate limit)."""


class MarketDataProvider(Protocol):
    def get_history(self, symbol: str, start: date, end: date) -> list[Bar]:
        """Daily bars with start <= date <= end. Empty list when there is no data."""
        ...

    def get_quote(self, symbol: str) -> Quote | None:
        """Latest price, or None when the symbol is unknown."""
        ...

    def get_name(self, symbol: str) -> str | None:
        """Short company or fund name, e.g. "Apple Inc."; None when unavailable."""
        ...

    def get_actions(self, symbol: str) -> list[CorporateEvent]:
        """Past splits and cash dividends (empty for coins)."""
        ...
