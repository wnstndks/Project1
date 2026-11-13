from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
from typing import Literal, Protocol


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


EventKind = Literal["earnings", "ex_dividend"]


@dataclass(frozen=True)
class UpcomingEvent:
    """A scheduled earnings release or ex-dividend date. `estimated` marks a date the
    provider gave as a range (the first day is kept) rather than a confirmed one."""

    symbol: str
    kind: EventKind
    date: date
    estimated: bool = False


@dataclass(frozen=True)
class StatementRow:
    """One period of the income statement, in the statement currency (whole units, not
    thousands). A line the provider does not report for that period is None."""

    period_end: date
    revenue: float | None
    operating_income: float | None
    net_income: float | None


@dataclass(frozen=True)
class Fundamentals:
    """Published company figures of one stock (DECISIONS.md D-036). Facts, not a signal.

    Units are fixed here so no consumer has to know the provider's: every `*_pct` field is a
    percentage on the 0-100 scale (1.5 means 1.5%), money is in whole units of `currency`
    (the statement currency), multiples (PER, PBR, PSR) are plain ratios. A figure the
    provider does not give, or one that failed the provider's own consistency check, is None
    rather than a guess.

    The periods differ per field, so a screen has to name them: the operating margin is the
    most recent quarter's, the net margin and ROE cover the last 12 months, both growth
    figures compare the most recent quarter with the same quarter a year before.

    Statement first: the operating margin, the net margin and the revenue growth are
    computed from `quarterly` (row 0; rows 0-3; row 0 against the row a year before), so
    they are the numbers the rows next to them give. Where the rows cannot give them, the
    net margin and the revenue growth fall back to the provider's own figure of the same
    definition; the operating margin does not (the provider's has no fixed period) and is
    None. The trailing EPS, the trailing PER and the PSR follow the same rule: the last four
    quarters of the income statement (diluted EPS summed, price over it, market cap over
    the summed revenue), and the provider's own figures, checked against each other, only
    where the statement cannot give them.

    When the quote currency is not known to be the statement currency (an ADR: statements
    in TWD, quoted in USD), the figures denominated in or mixing the quote currency
    (`market_cap`, both EPS, `book_value_per_share`, `pbr`, `psr`) are None; ratios within
    one currency and the statements themselves are still given.
    """

    symbol: str
    currency: str | None  # statement currency (Yahoo financialCurrency), e.g. "USD"
    name: str | None
    sector: str | None
    industry: str | None
    summary: str | None  # longBusinessSummary, original English text
    market_cap: float | None
    per_trailing: float | None  # price / eps_trailing; None when that EPS <= 0 or unknown
    per_forward: float | None  # price / analysts' estimated EPS (an estimate)
    pbr: float | None  # None when book value is zero or negative
    psr: float | None  # market cap / last-12-month revenue (quarterly[0:4] when complete)
    eps_trailing: float | None  # last 12 months, diluted (four quarters); negative = loss
    eps_forward: float | None  # analysts' estimate
    book_value_per_share: float | None
    dividend_yield_pct: float | None  # percent, indicated annual dividend / price; 0.0 = none
    operating_margin_pct: float | None  # percent, quarterly[0] operating income / revenue
    net_margin_pct: float | None  # percent, last 12 months (quarterly[0:4] when complete)
    roe_pct: float | None  # percent, last-12-month net income / average equity
    revenue_growth_pct: float | None  # percent, quarterly[0] revenue vs a year before
    earnings_growth_pct: float | None  # percent, latest quarter EPS, YoY; None from a loss
    debt_to_equity_pct: float | None  # total debt / shareholders' equity, percent
    annual: tuple[StatementRow, ...] = ()  # newest first, at most 4
    quarterly: tuple[StatementRow, ...] = ()  # newest first, at most 5


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

    def get_upcoming_events(self, symbol: str) -> list[UpcomingEvent]:
        """Scheduled earnings releases and ex-dividend dates; empty for coins. Past dates may
        be included (Yahoo keeps the last ex-dividend date), so consumers filter by today."""
        ...

    def get_fundamentals(self, symbol: str) -> Fundamentals | None:
        """Valuation multiples, margins and recent income statements of a stock.

        None for an asset that has no company statements: without a network request for
        coins such as `BTC-USD`, Upbit markets `KRW-*` and the FX rate `KRW=X` (see
        `assets.has_fundamentals`), and after the lookup for what the provider identifies as
        a fund (an ETF). A failed lookup or an unknown ticker raises MarketDataError; it
        never comes back as None or as made-up values."""
        ...
