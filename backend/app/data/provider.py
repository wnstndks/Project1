from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
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


def split_fraction(ratio: Decimal) -> Fraction:
    """A split ratio as new/old shares. Providers send floats, so a 1-for-30 reverse split
    arrives as 0.0333…; snapping to a small denominator makes 30 old shares exactly 1 new."""
    return Fraction(ratio).limit_denominator(1000)


def unadjust_dividends(events: list[CorporateEvent]) -> list[CorporateEvent]:
    """Yahoo restates past dividends on today's share count, like its prices: NVDA's $0.04
    from March 2024 is listed as $0.004 after the 10:1 split. Restore the amount actually
    paid per share held at the time by multiplying by every later split ratio."""
    splits = [(e.date, split_fraction(e.value)) for e in events if e.kind == "split"]
    out = []
    for e in events:
        if e.kind == "dividend":
            factor = Fraction(1)
            for d, ratio in splits:
                if d > e.date:
                    factor *= ratio
            if factor != 1:
                value = Decimal(factor.numerator) * e.value / Decimal(factor.denominator)
                e = CorporateEvent(e.date, e.kind, value.quantize(Decimal("1e-6")).normalize())
        out.append(e)
    return out


def split_adjusted_dividends(events: list[CorporateEvent]) -> list[CorporateEvent]:
    """The inverse of `unadjust_dividends`: dividends restated on today's share count, the
    scale of split-adjusted prices (divide by every later split ratio)."""
    splits = [(e.date, split_fraction(e.value)) for e in events if e.kind == "split"]
    out = []
    for e in events:
        if e.kind == "dividend":
            factor = Fraction(1)
            for d, ratio in splits:
                if d > e.date:
                    factor *= ratio
            if factor != 1:
                value = Decimal(factor.denominator) * e.value / Decimal(factor.numerator)
                e = CorporateEvent(e.date, e.kind, value)
        out.append(e)
    return out


class MarketDataError(Exception):
    """The provider failed (network error, upstream change, rate limit)."""


class DataUnavailableError(MarketDataError):
    """Data a strict consumer (backtest, signals, paper trading) needs is missing, stale or
    malformed. Raised instead of substituting other values."""


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
