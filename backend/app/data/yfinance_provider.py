"""The only module allowed to import yfinance.

yfinance is an unofficial scraper of Yahoo Finance and can break or be rate limited,
so every failure is converted to MarketDataError at this boundary.
"""

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
import yfinance as yf

from app.data.assets import trades_every_day
from app.data.provider import (
    Bar,
    CorporateEvent,
    MarketDataError,
    Quote,
    UpcomingEvent,
    unadjust_dividends,
)

# Keys of `Ticker.calendar` (a dict since yfinance 0.2.x; a DataFrame with these as row or
# column labels in older versions).
_EARNINGS_KEY = "Earnings Date"
_EX_DIVIDEND_KEY = "Ex-Dividend Date"


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
