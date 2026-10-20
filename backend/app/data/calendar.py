"""Trading calendars: when a daily bar is final, and which dates are trading days.

US stocks follow the NYSE calendar (holidays and 13:00 ET early closes). Coins trade 24/7
and their daily bars close at 00:00 UTC; the USD/KRW series is treated the same way.
"""

from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas as pd

from app.data.assets import FX_USDKRW, trades_every_day

NEW_YORK = ZoneInfo("America/New_York")
REGULAR_CLOSE = time(16, 0)
SETTLE_DELAY = timedelta(minutes=30)


@lru_cache
def _nyse():
    # Imported lazily: building the calendar takes about a second.
    import exchange_calendars as xc

    return xc.get_calendar("XNYS")


def is_24_7(symbol: str) -> bool:
    return trades_every_day(symbol) or symbol == FX_USDKRW


def _is_session(d: date) -> bool:
    cal = _nyse()
    ts = pd.Timestamp(d)
    if cal.first_session <= ts <= cal.last_session:
        return cal.is_session(ts)
    # Outside the calendar's ~20-year window (old news, far-off dates): weekdays only.
    return d.weekday() < 5


def nyse_close_utc(d: date) -> datetime | None:
    """Session close for a NYSE trading day (early closes included); None on holidays."""
    if not _is_session(d):
        return None
    cal = _nyse()
    ts = pd.Timestamp(d)
    if not cal.first_session <= ts <= cal.last_session:
        return datetime.combine(d, REGULAR_CLOSE, tzinfo=NEW_YORK).astimezone(UTC)
    return cal.session_close(ts).to_pydatetime()


def us_close_utc(d: date) -> datetime:
    """The close that news published on New York date `d` is measured against."""
    close = nyse_close_utc(d)
    if close is not None:
        return close
    return datetime.combine(d, REGULAR_CLOSE, tzinfo=NEW_YORK).astimezone(UTC)


def bar_is_final(symbol: str, bar_date: date, now_utc: datetime) -> bool:
    """True once the bar for `bar_date` can no longer change (its session has closed)."""
    if is_24_7(symbol):
        return now_utc >= datetime.combine(bar_date + timedelta(days=1), time.min, tzinfo=UTC)
    close = nyse_close_utc(bar_date)
    if close is None:
        return True  # no session that day, so nothing in progress
    # The closing auction print and final volume reach Yahoo a little after the bell.
    return now_utc >= close + SETTLE_DELAY


def next_trading_dates(symbol: str, after: date, n: int) -> list[date]:
    """The next n dates with a bar after `after` (NYSE sessions for stocks)."""
    if is_24_7(symbol):
        return [after + timedelta(days=i) for i in range(1, n + 1)]
    out: list[date] = []
    d = after
    while len(out) < n:
        d += timedelta(days=1)
        if _is_session(d):
            out.append(d)
    return out
