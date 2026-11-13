"""The only module allowed to import yfinance.

yfinance is an unofficial scraper of Yahoo Finance and can break or be rate limited,
so every failure is converted to MarketDataError at this boundary.
"""

import logging
import math
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
import yfinance as yf

from app.data.assets import has_fundamentals, trades_every_day
from app.data.provider import (
    Bar,
    CorporateEvent,
    Fundamentals,
    MarketDataError,
    Quote,
    StatementRow,
    UpcomingEvent,
    unadjust_dividends,
)

log = logging.getLogger(__name__)

# Keys of `Ticker.calendar` (a dict since yfinance 0.2.x; a DataFrame with these as row or
# column labels in older versions).
_EARNINGS_KEY = "Earnings Date"
_EX_DIVIDEND_KEY = "Ex-Dividend Date"

# --- Fundamentals (DECISIONS.md D-036) ------------------------------------------------------
# Units of `Ticker.info`, checked against real responses of yfinance 1.7.0 on 2026-11-11
# (AAPL, MSFT, AMZN, RIVN, SNAP, TSM; SPY for the fund case) by recomputing each figure from
# the price, the per-share values and the income statement / balance sheet:
#   trailingPE, forwardPE, priceToBook   = currentPrice / trailingEps, forwardEps, bookValue
#   priceToSalesTrailing12Months         = marketCap / totalRevenue (last 12 months)
#   dividendYield                        PERCENT already (0.31 = 0.31%) = dividendRate / price.
#                                        Older yfinance gave a fraction (0.0031), and
#                                        trailingAnnualDividendYield still is one, so the
#                                        scale is decided per response from dividendRate.
#   operatingMargins                     NOT USED. A fraction of no fixed period: the most
#                                        recent quarter for those six, the last four quarters
#                                        for a seventh name a day later (0.65214 against
#                                        0.66237 for the quarter), for an eighth no figure
#                                        of the statement at all
#   profitMargins                        fraction, of the last 12 months (all eight)
#   returnOnEquity                       fraction, 12-month net income / average equity
#   revenueGrowth, earningsGrowth        fraction, newest quarter against the same quarter a
#                                        year before (revenue: all eight; diluted EPS)
#   debtToEquity                         PERCENT already (84.286) = totalDebt / total equity
# For an ADR (TSM: statements in TWD, quote in USD) marketCap and the EPS values are in the
# quote currency, priceToSales divides USD by TWD and bookValue matched neither currency, so
# those are dropped when the two currencies differ or one is unknown.
#
# The three ratios the income statement can give (operating margin, net margin, revenue
# growth) are therefore computed from the statement rows that are returned with them, so a
# reader of the payload gets the number the rows give. `info` is the fallback of the net
# margin and the revenue growth only, whose definitions held for all eight tickers; the
# operating margin has no fallback and is None when the newest quarter cannot give it.
#
# The same goes for the trailing EPS, the trailing PER and the PSR. On 2026-11-12 Yahoo's
# trailingEps for AAPL was 9.16 where the statements give 8.98 (the day before it was 8.98):
# it had moved with the price (+2.0%) while trailingPE stood still, and for TSM likewise
# (+4.3%). trailingPE = price / trailingEps held throughout, so that check proves nothing.
# For a bank (JPM) totalRevenue was 4% below the sum of the four quarters. So: EPS = the four
# newest quarters' "Diluted EPS" (or the fiscal year's when it ends with the newest quarter),
# PER = price / that EPS, PSR = marketCap / the four newest quarters' revenue, each with
# Yahoo's own figure as the fallback when the statement cannot give it.
_ROW_REVENUE = "Total Revenue"
_ROW_OPERATING = "Operating Income"
_ROW_NET = "Net Income"
_ROW_EPS = "Diluted EPS"
_ANNUAL_ROWS = 4
_QUARTERLY_ROWS = 5
_MULTIPLE_TOL = 0.05  # a multiple vs its own numerator / denominator
_RATIO_DIGITS = 4  # computed EPS and multiples (a sum of two-decimal EPS has float noise)
_EPS_DIFF_ABS = 0.02  # Yahoo rounds EPS to cents; four rounded quarters can be 2 cents off
_DIFF_ABS = 0.5  # percentage points: when `info` is worth a warning next to the statement
_DIFF_REL = 0.05
_EXACT_ABS = 1.0  # percentage points: an `info` ratio vs the same ratio from `info` itself
_EXACT_REL = 0.10
_ROUGH_ABS = 5.0  # percentage points: a ratio vs a reference of a similar definition
_ROUGH_FACTOR = 2.5
_PCT_DIGITS = 4  # Yahoo's fractions carry float32 noise (0.41169998): 41.17, not 41.169998
_QUARTER_GAP = (80, 100)  # days between consecutive quarter ends
_YEAR_GAP = (350, 380)  # days between a quarter and the same quarter a year before


class YFinanceProvider:
    def get_history(self, symbol: str, start: date, end: date) -> list[Bar]:
        # yfinance treats `end` as exclusive.
        df = self._download(symbol, start=start, end=end + timedelta(days=1))
        return [
            Bar(
                date=ts.date(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                adj_close=float(row["Adj Close"]),
                volume=float(row["Volume"]),
            )
            for ts, row in df.iterrows()
            if start <= ts.date() <= end and not pd.isna(row["Close"])
        ]

    def get_quote(self, symbol: str) -> Quote | None:
        # The last daily bar is the in-progress session while the market is open.
        df = self._download(symbol, period="5d")
        df = df.dropna(subset=["Close"])
        if df.empty:
            return None
        ts = df.index[-1]
        return Quote(symbol=symbol, price=float(df["Close"].iloc[-1]), as_of=_to_datetime(ts))

    def get_name(self, symbol: str) -> str | None:
        try:
            info = yf.Ticker(symbol).info
        except Exception as exc:  # yfinance raises many unrelated exception types
            raise MarketDataError(f"yfinance info failed for {symbol}: {exc}") from exc
        return info.get("shortName") or info.get("longName")

    def get_actions(self, symbol: str) -> list[CorporateEvent]:
        try:
            df = yf.Ticker(symbol).actions
        except Exception as exc:  # yfinance raises many unrelated exception types
            raise MarketDataError(f"yfinance actions failed for {symbol}: {exc}") from exc
        out: list[CorporateEvent] = []
        if df is None or df.empty:
            return out
        for ts, row in df.iterrows():
            d = ts.date()
            if row.get("Stock Splits", 0) and row["Stock Splits"] > 0:
                out.append(CorporateEvent(d, "split", Decimal(str(row["Stock Splits"]))))
            if row.get("Dividends", 0) and row["Dividends"] > 0:
                out.append(CorporateEvent(d, "dividend", Decimal(str(row["Dividends"]))))
        return unadjust_dividends(out)

    def get_upcoming_events(self, symbol: str) -> list[UpcomingEvent]:
        if trades_every_day(symbol):
            return []  # no earnings or dividends; skip the request
        try:
            cal = yf.Ticker(symbol).calendar
        except Exception as exc:  # yfinance raises many unrelated exception types
            raise MarketDataError(f"yfinance calendar failed for {symbol}: {exc}") from exc
        return parse_calendar(symbol, cal)

    def get_fundamentals(self, symbol: str) -> Fundamentals | None:
        if not has_fundamentals(symbol):
            return None  # coins, Upbit markets, FX, indices: no request
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
        except Exception as exc:  # yfinance raises many unrelated exception types
            raise MarketDataError(f"yfinance info failed for {symbol}: {exc}") from exc
        if not isinstance(info, dict):
            info = {}
        quote_type = info.get("quoteType")
        if not quote_type:
            # An unknown ticker and a swallowed HTTP error both come back as a nearly empty
            # dict (`{"trailingPegRatio": None}`); neither is "this asset has no statements".
            raise MarketDataError(f"yfinance returned no quote data for {symbol}")
        if str(quote_type).upper() != "EQUITY":
            return None  # ETF, fund, index...: a price but no company statements
        try:
            annual = ticker.income_stmt
            quarterly = ticker.quarterly_income_stmt
        except Exception as exc:  # yfinance raises many unrelated exception types
            raise MarketDataError(f"yfinance income statement failed for {symbol}: {exc}") from exc
        return parse_fundamentals(symbol, info, annual, quarterly)

    @staticmethod
    def _download(symbol: str, **kwargs) -> pd.DataFrame:
        try:
            return yf.Ticker(symbol).history(interval="1d", auto_adjust=False, **kwargs)
        except Exception as exc:  # yfinance raises many unrelated exception types
            raise MarketDataError(f"yfinance request failed for {symbol}: {exc}") from exc


def _to_datetime(ts: pd.Timestamp) -> datetime:
    return ts.to_pydatetime().replace(tzinfo=None)


def parse_calendar(symbol: str, cal: Any) -> list[UpcomingEvent]:
    """Upcoming events from `Ticker.calendar`, whatever shape this yfinance version gives.

    Recent versions return a dict: `"Earnings Date"` is a list of one date (confirmed) or two
    (Yahoo's estimated window: keep the first day, mark it estimated) and `"Ex-Dividend Date"`
    one date, which is usually the last one that already passed. Old versions return a
    DataFrame with those labels as rows (one column per date) or columns. Dates are not
    filtered here; the consumer compares them with today.
    """
    if cal is None:
        return []
    if isinstance(cal, pd.DataFrame):
        if cal.empty:
            return []
        earnings = _frame_values(cal, _EARNINGS_KEY)
        ex_dividend = _frame_values(cal, _EX_DIVIDEND_KEY)
    elif isinstance(cal, dict):
        if not cal:
            return []
        earnings, ex_dividend = cal.get(_EARNINGS_KEY), cal.get(_EX_DIVIDEND_KEY)
    else:
        raise MarketDataError(f"yfinance calendar for {symbol} has unexpected type {type(cal)!r}")

    out: list[UpcomingEvent] = []
    earnings_dates = _dates(earnings)
    if earnings_dates:
        out.append(UpcomingEvent(symbol, "earnings", earnings_dates[0], len(earnings_dates) > 1))
    ex_dates = _dates(ex_dividend)
    if ex_dates:
        out.append(UpcomingEvent(symbol, "ex_dividend", ex_dates[0]))
    return out


def _frame_values(cal: pd.DataFrame, key: str) -> list[Any]:
    if key in cal.index:
        return list(cal.loc[key])
    if key in cal.columns:
        return list(cal[key])
    return []


def _dates(value: Any) -> list[date]:
    """Distinct dates in a scalar or sequence, sorted; None and NaT are skipped."""
    items: Iterable[Any]
    if value is None:
        return []
    if isinstance(value, str | date | datetime | pd.Timestamp):
        items = [value]
    else:
        try:
            items = list(value)
        except TypeError:
            items = [value]
    out: set[date] = set()
    for item in items:
        if item is None or (not isinstance(item, str) and pd.isna(item)):
            continue
        try:
            ts = pd.Timestamp(item)
        except (ValueError, TypeError):
            continue  # not a date at all; leave it out rather than guess
        if pd.isna(ts):
            continue
        out.add(ts.date())
    return sorted(out)


def parse_fundamentals(
    symbol: str, info: dict[str, Any], annual: Any, quarterly: Any
) -> Fundamentals:
    """`Ticker.info` plus the two income statements as a `Fundamentals` in fixed units.

    Statement first: the operating margin (newest quarter), the net margin (four newest
    quarters) and the revenue growth (newest quarter against the one a year before) are
    computed from the quarterly rows returned in the same object, so they are the numbers
    those rows give. For the net margin and the revenue growth `info` fills in when the
    rows cannot (a quarter is missing, the base is zero), and when it disagrees with the
    rows a warning is logged and the rows win. The operating margin is never taken from
    `info`, whose figure has no fixed period: without the newest quarter's operating income
    and a positive revenue it is None.

    Likewise the trailing EPS is the statements' (four newest quarters of diluted EPS, or
    the fiscal year that ends with the newest quarter), the trailing PER is the price over
    that EPS and the PSR is the market cap over the four newest quarters' revenue. Without
    those rows, or when the statements are in another currency than the quote (an ADR),
    Yahoo's own pair stands in, checked as before.

    Everything else comes from `info` and is checked against a figure recomputed from the
    same response (the price and per-share values, the income statement). One that
    disagrees is dropped (None) with a warning rather than passed on; one that cannot be
    checked is converted with the scale documented at the top of this module. Nothing is
    filled in by guessing.
    """
    annual_rows = statement_rows(annual, _ANNUAL_ROWS)
    quarterly_rows = statement_rows(quarterly, _QUARTERLY_ROWS)
    revenue_info = _num(info.get("totalRevenue"))
    if not annual_rows and not quarterly_rows and revenue_info is not None:
        # yfinance turns a failed statement request into an empty frame. A company that
        # reports revenue has an income statement, so this is a failed fetch, not a fact.
        raise MarketDataError(f"yfinance returned no income statement for {symbol}")

    price = _first_positive(info, "currentPrice", "regularMarketPrice")
    statement_ccy = _text(info.get("financialCurrency"))
    quote_ccy = _text(info.get("currency"))
    # Per-share values and the market cap are in the quote currency. They are only passed on
    # when that is known to be the statement currency (`Fundamentals.currency`).
    same_ccy = bool(statement_ccy and quote_ccy and statement_ccy.upper() == quote_ccy.upper())

    eps_trailing = _first(info, "trailingEps", "epsTrailingTwelveMonths")
    eps_forward = _first(info, "forwardEps", "epsForward")
    book = _num(info.get("bookValue"))
    market_cap = _first_positive(info, "marketCap")
    shares = _first_positive(info, "impliedSharesOutstanding", "sharesOutstanding")
    equity = book * shares if same_ccy and book is not None and book > 0 and shares else None

    newest = quarterly_rows[0] if quarterly_rows else None
    year_before = _year_before(quarterly_rows)
    revenue_ttm = _ttm(quarterly_rows, "revenue")
    net_ttm = _ttm(quarterly_rows, "net_income")
    # `info` values are only compared with the statement when its newest quarter is the one
    # `info` describes (right after a release the two can be a quarter apart).
    aligned = newest is not None and _same_quarter(info.get("mostRecentQuarter"), newest.period_end)

    # Trailing EPS and PER, statement first. Yahoo was seen moving `trailingEps` with the
    # price for some tickers while holding `trailingPE` (8.98 -> 9.16 overnight with the same
    # statements), and the two agree with each other either way, so the pair cannot vouch
    # for itself. The statement's EPS is per share in the statement currency, hence only
    # when that is the quote currency.
    eps_statement = _eps_ttm(quarterly, quarterly_rows, annual, annual_rows) if same_ccy else None
    if eps_statement is not None:
        _warn_if_far(symbol, "trailingEps", eps_trailing, eps_statement, _EPS_DIFF_ABS, 0.01)
        eps_trailing = round(eps_statement, _RATIO_DIGITS)
        if eps_trailing <= 0:
            per_trailing = None
        elif price is not None:
            per_trailing = round(price / eps_trailing, _RATIO_DIGITS)
        else:  # no price to divide: Yahoo's multiple, unchecked
            per_trailing = _multiple(symbol, "trailingPE", _num(info.get("trailingPE")), None, None)
    else:
        # No trailing PER for a loss: judged by EPS, or by the statements without one.
        earned = eps_trailing if eps_trailing is not None else net_ttm
        loss = earned is not None and earned <= 0
        per_trailing = (
            None
            if loss
            else _multiple(symbol, "trailingPE", _num(info.get("trailingPE")), price, eps_trailing)
        )

    # PSR on the revenue of the rows that are returned (a bank's `totalRevenue` in `info`
    # was 4% off the sum of its four quarters); Yahoo's own multiple otherwise.
    psr_yahoo = _num(info.get("priceToSalesTrailing12Months"))
    if not same_ccy:
        psr = None
    elif market_cap is not None and revenue_ttm is not None and revenue_ttm > 0:
        psr = round(market_cap / revenue_ttm, _RATIO_DIGITS)
        _warn_if_far(symbol, "priceToSalesTrailing12Months", psr_yahoo, psr, 0.0, _MULTIPLE_TOL)
    else:
        psr = _multiple(symbol, "priceToSalesTrailing12Months", psr_yahoo, market_cap, revenue_info)

    debt_to_equity = _num(info.get("debtToEquity"))
    if debt_to_equity is not None and debt_to_equity < 0:
        debt_to_equity = None  # negative equity: the ratio has no meaning

    def percent(
        field: str, *, exact: float | None = None, rough: float | None = None
    ) -> float | None:
        return _percent(symbol, field, _num(info.get(field)), 100.0, exact=exact, rough=rough)

    def statement_first(
        field: str, computed: float | None, *, exact: float | None = None
    ) -> float | None:
        return _statement_first(symbol, field, computed, _num(info.get(field)), exact=exact)

    def multiple(field: str, numerator: float | None, denominator: float | None) -> float | None:
        return _multiple(symbol, field, _num(info.get(field)), numerator, denominator)

    return Fundamentals(
        symbol=symbol,
        currency=statement_ccy,
        name=_text(info.get("longName")) or _text(info.get("shortName")),
        sector=_text(info.get("sector")),
        industry=_text(info.get("industry")),
        summary=_text(info.get("longBusinessSummary")),
        market_cap=market_cap if same_ccy else None,
        per_trailing=per_trailing,
        per_forward=multiple("forwardPE", price, eps_forward),
        pbr=multiple("priceToBook", price, book) if same_ccy else None,
        psr=psr,
        eps_trailing=eps_trailing if same_ccy else None,
        eps_forward=eps_forward if same_ccy else None,
        book_value_per_share=book if same_ccy else None,
        dividend_yield_pct=_dividend_yield_pct(
            symbol,
            _num(info.get("dividendYield")),
            _num(info.get("dividendRate")),
            _num(info.get("trailingAnnualDividendRate")),
            price,
        ),
        # Statement only: `info["operatingMargins"]` has no fixed period (see the top of this
        # module), so it can neither stand in for the newest quarter nor be compared with it.
        operating_margin_pct=_rounded(
            _ratio_pct(newest.operating_income, newest.revenue) if newest else None
        ),
        net_margin_pct=statement_first(
            "profitMargins",
            _ratio_pct(net_ttm, revenue_ttm),
            # Without four full quarters `info` stands in, checked against `info` itself.
            exact=_ratio_pct(_num(info.get("netIncomeToCommon")), revenue_info),
        ),
        roe_pct=percent(
            "returnOnEquity", rough=_ratio_pct(_num(info.get("netIncomeToCommon")), equity)
        ),
        revenue_growth_pct=statement_first(
            "revenueGrowth",
            _growth_pct(newest.revenue, year_before.revenue) if newest and year_before else None,
        ),
        earnings_growth_pct=percent(
            "earningsGrowth",
            rough=(
                _growth_pct(newest.net_income, year_before.net_income)
                if aligned and newest and year_before
                else None
            ),
        ),
        debt_to_equity_pct=_percent(
            symbol,
            "debtToEquity",
            debt_to_equity,
            1.0,
            rough=_ratio_pct(_num(info.get("totalDebt")), equity),
        ),
        annual=annual_rows,
        quarterly=quarterly_rows,
    )


def statement_rows(frame: Any, limit: int) -> tuple[StatementRow, ...]:
    """Revenue, operating income and net income per period of a yfinance income statement
    (rows = line items, columns = period ends), newest first, at most `limit`.

    A line the statement does not have (banks have no "Operating Income") or a NaN cell is
    None for that value only. Yahoo pads the table with periods that are empty for these
    lines, usually the oldest and sometimes one in the middle: empty periods at either end
    are dropped, one between two reported periods is kept as a row of None so the gap shows.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return ()
    periods: dict[date, Any] = {}
    for column in frame.columns:
        period_end = _period(column)
        if period_end is not None:
            periods.setdefault(period_end, column)
    rows = [
        StatementRow(
            period_end,
            _cell(frame, _ROW_REVENUE, periods[period_end]),
            _cell(frame, _ROW_OPERATING, periods[period_end]),
            _cell(frame, _ROW_NET, periods[period_end]),
        )
        for period_end in sorted(periods, reverse=True)
    ]
    return tuple(_strip_empty(_strip_empty(rows)[:limit]))


def _strip_empty(rows: list[StatementRow]) -> list[StatementRow]:
    def empty(row: StatementRow) -> bool:
        return row.revenue is None and row.operating_income is None and row.net_income is None

    start, end = 0, len(rows)
    while start < end and empty(rows[start]):
        start += 1
    while end > start and empty(rows[end - 1]):
        end -= 1
    return rows[start:end]


def _period(column: Any) -> date | None:
    """A statement column label as a date; anything that is not a date (a positional integer
    label, "TTM") is skipped rather than read as one."""
    if not isinstance(column, str | date | datetime | pd.Timestamp):
        return None
    try:
        ts = pd.Timestamp(column)
    except (ValueError, TypeError):
        return None
    return None if pd.isna(ts) else ts.date()


def _cell(frame: pd.DataFrame, row: str, column: Any) -> float | None:
    if row not in frame.index:
        return None
    value = frame.loc[row, column]
    if isinstance(value, pd.DataFrame):  # duplicated row and column labels
        value = value.iloc[0, 0]
    elif isinstance(value, pd.Series):  # duplicated row or column label: take the first
        value = value.iloc[0]
    return _num(value)


def _num(value: Any) -> float | None:
    """A finite float, or None for None, NaN, inf, booleans and anything not numeric (Yahoo
    sends the string "Infinity" for some ratios)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _text(value: Any) -> str | None:
    return (value.strip() or None) if isinstance(value, str) else None


def _first(info: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        number = _num(info.get(key))
        if number is not None:
            return number
    return None


def _first_positive(info: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        number = _num(info.get(key))
        if number is not None and number > 0:
            return number
    return None


def _ratio_pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator * 100.0


def _rounded(percent: float | None) -> float | None:
    return None if percent is None else round(percent, _PCT_DIGITS)


def _growth_pct(new: float | None, old: float | None) -> float | None:
    """Change against a positive base; growth from zero or from a loss is not a number."""
    if new is None or old is None or old <= 0:
        return None
    return (new / old - 1.0) * 100.0


def _last_four(rows: tuple[StatementRow, ...]) -> tuple[StatementRow, ...] | None:
    """The newest four quarters when they are four consecutive quarters (twelve months)."""
    head = rows[:4]
    if len(head) < 4:
        return None
    for newer, older in zip(head, head[1:], strict=False):
        if not _QUARTER_GAP[0] <= (newer.period_end - older.period_end).days <= _QUARTER_GAP[1]:
            return None
    return head


def _ttm(rows: tuple[StatementRow, ...], field: str) -> float | None:
    """Sum of the newest four quarters, only when all four are reported and consecutive."""
    head = _last_four(rows)
    if head is None:
        return None
    values = [getattr(row, field) for row in head]
    return None if any(v is None for v in values) else sum(values)


def _line(frame: Any, row: str) -> dict[date, float | None]:
    """One line item of a statement by period end (empty when the line is not there)."""
    if not isinstance(frame, pd.DataFrame) or row not in frame.index:
        return {}
    out: dict[date, float | None] = {}
    for column in frame.columns:
        period_end = _period(column)
        if period_end is not None and period_end not in out:
            out[period_end] = _cell(frame, row, column)
    return out


def _eps_ttm(
    quarterly: Any,
    quarterly_rows: tuple[StatementRow, ...],
    annual: Any,
    annual_rows: tuple[StatementRow, ...],
) -> float | None:
    """Diluted EPS of the last twelve months from the statements, in the statement currency:
    the sum of the four newest quarters when all four report it and are consecutive; or the
    fiscal year's, when the year ends with the newest quarter (Yahoo leaves the fourth
    quarter's EPS empty, the annual column is those same twelve months). None otherwise.
    Basic EPS is not a substitute."""
    head = _last_four(quarterly_rows)
    if head is not None:
        by_period = _line(quarterly, _ROW_EPS)
        values = [by_period.get(row.period_end) for row in head]
        if all(v is not None for v in values):
            return sum(values)
    if quarterly_rows and annual_rows:
        year_end = annual_rows[0].period_end
        if year_end == quarterly_rows[0].period_end:
            return _line(annual, _ROW_EPS).get(year_end)
    return None


def _warn_if_far(
    symbol: str,
    field: str,
    value: float | None,
    computed: float,
    absolute: float,
    relative: float,
) -> None:
    """Log when Yahoo's `value` is not the figure computed from the statement. The computed
    one is used either way; the log is what shows how often and how far Yahoo is off."""
    if value is not None and abs(value - computed) > max(absolute, relative * abs(computed)):
        log.warning(
            "%s: %s=%r is not the %.6g computed from the income statement; the statement is used",
            symbol,
            field,
            value,
            computed,
        )


def _year_before(rows: tuple[StatementRow, ...]) -> StatementRow | None:
    """The quarter one year before the newest one, matched by date rather than position
    (the table can have a gap)."""
    for row in rows[1:]:
        if _YEAR_GAP[0] <= (rows[0].period_end - row.period_end).days <= _YEAR_GAP[1]:
            return row
    return None


def _same_quarter(most_recent_quarter: Any, period_end: date) -> bool:
    """Whether `info["mostRecentQuarter"]` (epoch seconds) is the statement's newest period.
    Yahoo labels statement columns with the month end while the info field has the exact
    fiscal date (2026-09-26 vs 2026-09-30), so a few weeks of slack. Unknown counts as same.
    """
    seconds = _num(most_recent_quarter)
    if seconds is None:
        return True
    try:
        quarter = (datetime(1970, 1, 1) + timedelta(seconds=seconds)).date()
    except (OverflowError, ValueError):
        return True
    return abs((quarter - period_end).days) <= 20


def _multiple(
    symbol: str,
    field: str,
    value: float | None,
    numerator: float | None,
    denominator: float | None,
) -> float | None:
    """A price multiple as Yahoo gave it: None when it or its denominator (EPS, book value,
    revenue) is zero or negative, and None when it is not numerator / denominator."""
    if value is None or value <= 0:
        return None
    if denominator is not None and denominator <= 0:
        return None
    if numerator is not None and numerator > 0 and denominator is not None:
        reference = numerator / denominator
        if abs(value - reference) > _MULTIPLE_TOL * reference:
            log.warning(
                "%s: %s=%r is not %.6g (recomputed); dropped", symbol, field, value, reference
            )
            return None
    return value


def _roughly(candidate: float, reference: float) -> bool:
    if abs(candidate - reference) <= _ROUGH_ABS:
        return True
    if candidate * reference <= 0:
        return False
    return 1.0 / _ROUGH_FACTOR <= candidate / reference <= _ROUGH_FACTOR


def _percent(
    symbol: str,
    field: str,
    value: float | None,
    scale: float,
    *,
    exact: float | None = None,
    rough: float | None = None,
) -> float | None:
    """`value` as a percentage. `scale` is what this yfinance version needs (100 for a
    fraction, 1 for a value that is already a percentage). With a reference in percent, the
    documented scale is used when it agrees, the other scale when only that one does (the
    unit changed upstream), and None when neither does. `exact` is the same ratio recomputed
    (tight), `rough` one of a similar definition (within a factor). Without a reference the
    documented scale stands."""
    if value is None:
        return None
    candidates = (value * scale, value * (1.0 if scale == 100.0 else 100.0))
    if exact is not None:
        tolerance = max(_EXACT_ABS, _EXACT_REL * abs(exact))
        passing = [c for c in candidates if abs(c - exact) <= tolerance]
        reference = exact
    elif rough is not None:
        passing = [c for c in candidates if _roughly(c, rough)]
        reference = rough
    else:
        return round(candidates[0], _PCT_DIGITS)
    if not passing:
        log.warning(
            "%s: %s=%r does not match %.6g%% recomputed from the same response; dropped",
            symbol,
            field,
            value,
            reference,
        )
        return None
    return round(passing[0], _PCT_DIGITS)


def _statement_first(
    symbol: str,
    field: str,
    computed: float | None,
    value: float | None,
    *,
    exact: float | None = None,
) -> float | None:
    """A ratio the income statement gives, in percent: `computed` (from the statement rows)
    when there is one, else `info`'s `value` (a fraction, checked against `exact` when that
    is known). When both exist and `info` is not the computed figure in either scale, a
    warning is logged and the computed figure is used all the same: the rows are returned
    next to the ratio, and the ratio has to be the one they give."""
    if computed is None:
        return _percent(symbol, field, value, 100.0, exact=exact)
    if value is not None:
        tolerance = max(_DIFF_ABS, _DIFF_REL * abs(computed))
        if all(abs(candidate - computed) > tolerance for candidate in (value * 100.0, value)):
            log.warning(
                "%s: %s=%r is not the %.4f%% computed from the income statement; "
                "the statement is used",
                symbol,
                field,
                value,
                computed,
            )
    return round(computed, _PCT_DIGITS)


def _dividend_yield_pct(
    symbol: str,
    dividend_yield: float | None,
    rate: float | None,
    trailing_rate: float | None,
    price: float | None,
) -> float | None:
    """Forward dividend yield in percent. `dividendYield` is a percentage in this yfinance
    version and was a fraction in older ones, so its scale is settled by `dividendRate /
    price` (or, failing that, loosely by the trailing rate). 0.0 for a company that pays
    nothing; `dividendRate / price` itself when only the rate is given; None when Yahoo
    gives neither, or the scale cannot be settled."""
    forward = rate / price * 100.0 if rate and rate > 0 and price else None
    if dividend_yield is None:
        return round(forward, _PCT_DIGITS) if forward is not None else None
    if dividend_yield < 0:
        return None
    if dividend_yield == 0:
        return 0.0 if forward is None else None
    candidates = (dividend_yield, dividend_yield * 100.0)  # percent first: verified on 1.7.0
    if forward is not None:
        reference = forward
        tolerance = max(0.03, _EXACT_REL * forward)
        passing = [c for c in candidates if abs(c - forward) <= tolerance]
    elif trailing_rate and trailing_rate > 0 and price:
        reference = trailing_rate / price * 100.0
        passing = [c for c in candidates if 0.5 <= c / reference <= 2.0]
    else:
        log.warning(
            "%s: dividendYield=%r has no dividend rate to settle its unit; dropped",
            symbol,
            dividend_yield,
        )
        return None
    if not passing:
        log.warning(
            "%s: dividendYield=%r does not match %.6g%% (dividend / price); dropped",
            symbol,
            dividend_yield,
            reference,
        )
        return None
    return round(passing[0], _PCT_DIGITS)
