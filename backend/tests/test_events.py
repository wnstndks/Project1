"""Upcoming earnings / ex-dividend dates and NYSE closures (learn page, D-034)."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import select

from app.data import yfinance_provider as yfp
from app.data.calendar import Closure, upcoming_closures
from app.data.fake_provider import FakeProvider
from app.data.provider import MarketDataError, UpcomingEvent
from app.data.upbit_provider import RoutingProvider, UpbitProvider
from app.db.models import EventSync, UpcomingEventRow
from app.services.events import (
    DEFAULT_ERROR_TTL,
    ERROR_MAX,
    EventService,
    has_calendar,
    join_error,
    split_error,
)
from tests.conftest import TODAY

NOW = datetime.combine(TODAY, datetime.min.time()) + timedelta(hours=10)
D = TODAY


def day(n: int) -> date:
    return TODAY + timedelta(days=n)


# --- FakeProvider -------------------------------------------------------------------------


def test_fake_events_are_deterministic_and_after_today():
    a = FakeProvider(today=TODAY).get_upcoming_events("AAA")
    b = FakeProvider(today=TODAY).get_upcoming_events("AAA")
    assert a == b and a
    assert all(e.symbol == "AAA" and e.date > TODAY for e in a)
    earnings = [e for e in a if e.kind == "earnings"]
    assert len(earnings) == 2
    assert (earnings[1].date - earnings[0].date).days == 91
    assert len([e for e in a if e.kind == "ex_dividend"]) <= 1
    assert a == sorted(a, key=lambda e: (e.date, e.kind))


def test_fake_moves_with_today():
    early = FakeProvider(today=TODAY).get_upcoming_events("AAA")
    later = FakeProvider(today=TODAY + timedelta(days=400)).get_upcoming_events("AAA")
    assert all(e.date > TODAY + timedelta(days=400) for e in later)
    assert early != later


def test_fake_override_wins_and_is_copied():
    ev = [UpcomingEvent("AAA", "earnings", day(3), True)]
    p = FakeProvider(today=TODAY, upcoming={"AAA": ev})
    assert p.get_upcoming_events("AAA") == ev
    assert p.get_upcoming_events("AAA") is not ev
    assert p.event_calls == ["AAA", "AAA"]


@pytest.mark.parametrize("symbol", ["BTC-USD", "ETH-USD", "KRW-BTC", "KRW-SOL"])
def test_fake_coins_have_no_events(symbol):
    assert FakeProvider(today=TODAY).get_upcoming_events(symbol) == []


def test_fake_unknown_symbol_has_no_events():
    assert FakeProvider(today=TODAY, unknown={"ZZZZ"}).get_upcoming_events("ZZZZ") == []


# --- Upbit / routing ------------------------------------------------------------------------


def test_upbit_has_no_events_and_routing_delegates():
    ev = [UpcomingEvent("AAA", "ex_dividend", day(2))]
    default = FakeProvider(today=TODAY, upcoming={"AAA": ev})
    upbit = UpbitProvider(http=object())  # never used: no request is made
    routed = RoutingProvider(default, upbit)
    assert upbit.get_upcoming_events("KRW-BTC") == []
    assert routed.get_upcoming_events("KRW-BTC") == []
    assert routed.get_upcoming_events("AAA") == ev
    assert default.event_calls == ["AAA"]


# --- NYSE closures ------------------------------------------------------------------------


def test_upcoming_closures_thanksgiving_week():
    out = upcoming_closures(date(2026, 11, 23), 7)
    assert out == [
        Closure(date(2026, 11, 26), "holiday", None),
        Closure(date(2026, 11, 27), "early_close", datetime(2026, 11, 27, 18, 0, tzinfo=UTC)),
    ]


def test_upcoming_closures_regular_week_is_empty():
    assert upcoming_closures(date(2026, 11, 2), 7) == []


def test_upcoming_closures_window_edges():
    # Christmas 2026: early close Thursday 12-24, holiday Friday 12-25.
    assert [c.kind for c in upcoming_closures(date(2026, 12, 24), 2)] == ["early_close", "holiday"]
    assert [c.date for c in upcoming_closures(date(2026, 12, 25), 1)] == [date(2026, 12, 25)]
    # Independence Day 2026 is a Saturday: observed Friday 07-03, and no early close on 07-02
    # because 07-03 is not a session.
    assert [(c.date, c.kind) for c in upcoming_closures(date(2026, 7, 2), 2)] == [
        (date(2026, 7, 3), "holiday")
    ]
    assert upcoming_closures(date(2026, 7, 4), 2) == []  # Saturday and Sunday only
    assert upcoming_closures(date(2026, 11, 26), 0) == []


# --- YFinanceProvider.get_upcoming_events -------------------------------------------------


def _patch_ticker(monkeypatch, calendar, calls: list[str]) -> None:
    class Ticker:
        def __init__(self, symbol: str) -> None:
            calls.append(symbol)

        @property
        def calendar(self):
            if isinstance(calendar, Exception):
                raise calendar
            return calendar

    monkeypatch.setattr(yfp, "yf", SimpleNamespace(Ticker=Ticker))


def test_yfinance_dict_range_is_estimated_and_ex_date_kept(monkeypatch):
    calls: list[str] = []
    cal = {
        "Earnings Date": [date(2026, 11, 5), date(2026, 11, 9)],
        "Ex-Dividend Date": date(2026, 8, 11),  # already past: not filtered here
        "Dividend Date": date(2026, 8, 14),
        "Earnings Average": 1.23,
    }
    _patch_ticker(monkeypatch, cal, calls)
    out = yfp.YFinanceProvider().get_upcoming_events("AAA")
    assert out == [
        UpcomingEvent("AAA", "earnings", date(2026, 11, 5), True),
        UpcomingEvent("AAA", "ex_dividend", date(2026, 8, 11), False),
    ]
    assert calls == ["AAA"]


def test_yfinance_dict_single_date_is_confirmed(monkeypatch):
    _patch_ticker(monkeypatch, {"Earnings Date": [date(2026, 11, 5)]}, [])
    assert yfp.YFinanceProvider().get_upcoming_events("AAA") == [
        UpcomingEvent("AAA", "earnings", date(2026, 11, 5), False)
    ]


def test_yfinance_dict_repeated_date_counts_as_one(monkeypatch):
    _patch_ticker(monkeypatch, {"Earnings Date": [date(2026, 11, 5), date(2026, 11, 5)]}, [])
    assert yfp.YFinanceProvider().get_upcoming_events("AAA") == [
        UpcomingEvent("AAA", "earnings", date(2026, 11, 5), False)
    ]


def test_yfinance_dict_with_timestamps_and_tz(monkeypatch):
    cal = {
        "Earnings Date": [pd.Timestamp("2026-11-05 16:30", tz="America/New_York"), pd.NaT],
        "Ex-Dividend Date": None,
    }
    _patch_ticker(monkeypatch, cal, [])
    assert yfp.YFinanceProvider().get_upcoming_events("AAA") == [
        UpcomingEvent("AAA", "earnings", date(2026, 11, 5), False)
    ]


@pytest.mark.parametrize(
    "calendar", [None, {}, pd.DataFrame(), {"Earnings Date": []}, {"Earnings Average": 1.0}]
)
def test_yfinance_empty_calendar_shapes(monkeypatch, calendar):
    _patch_ticker(monkeypatch, calendar, [])
    assert yfp.YFinanceProvider().get_upcoming_events("AAA") == []


def test_yfinance_old_dataframe_rows(monkeypatch):
    # yfinance < 0.2: labels as rows, one column per date, other rows are estimates.
    cal = pd.DataFrame(
        {0: [pd.Timestamp("2026-11-05"), 1.0], 1: [pd.Timestamp("2026-11-09"), 1.1]},
        index=["Earnings Date", "Earnings Average"],
    )
    _patch_ticker(monkeypatch, cal, [])
    assert yfp.YFinanceProvider().get_upcoming_events("AAA") == [
        UpcomingEvent("AAA", "earnings", date(2026, 11, 5), True)
    ]


def test_yfinance_old_dataframe_columns(monkeypatch):
    cal = pd.DataFrame(
        {
            "Earnings Date": [pd.Timestamp("2026-11-05"), pd.NaT],
            "Ex-Dividend Date": [pd.Timestamp("2026-11-20"), pd.NaT],
        }
    )
    _patch_ticker(monkeypatch, cal, [])
    assert yfp.YFinanceProvider().get_upcoming_events("AAA") == [
        UpcomingEvent("AAA", "earnings", date(2026, 11, 5), False),
        UpcomingEvent("AAA", "ex_dividend", date(2026, 11, 20), False),
    ]


def test_yfinance_failure_becomes_market_data_error(monkeypatch):
    _patch_ticker(monkeypatch, RuntimeError("rate limited"), [])
    with pytest.raises(MarketDataError, match="AAA"):
        yfp.YFinanceProvider().get_upcoming_events("AAA")


def test_yfinance_unexpected_shape_is_an_error(monkeypatch):
    _patch_ticker(monkeypatch, ["not", "a", "calendar"], [])
    with pytest.raises(MarketDataError):
        yfp.YFinanceProvider().get_upcoming_events("AAA")


@pytest.mark.parametrize("symbol", ["BTC-USD", "KRW-BTC"])
def test_yfinance_coins_skip_the_request(monkeypatch, symbol):
    calls: list[str] = []
    _patch_ticker(monkeypatch, RuntimeError("must not be called"), calls)
    assert yfp.YFinanceProvider().get_upcoming_events(symbol) == []
    assert calls == []


# --- EventService -------------------------------------------------------------------------

EVENTS = {
    "AAA": [
        UpcomingEvent("AAA", "earnings", day(3), True),
        UpcomingEvent("AAA", "ex_dividend", day(-2)),  # Yahoo's last ex-date, already past
        UpcomingEvent("AAA", "ex_dividend", day(30)),
    ],
    "BBB": [UpcomingEvent("BBB", "earnings", day(7))],
}


class Clock:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t


class FailingProvider(FakeProvider):
    """`get_upcoming_events` raises for the symbols in `fail`, like a scraper outage."""

    def __init__(self, fail: set[str], **kw) -> None:
        super().__init__(**kw)
        self.fail = fail

    def get_upcoming_events(self, symbol):
        if symbol in self.fail:
            self.event_calls.append(symbol)
            raise MarketDataError(f"calendar down for {symbol}")
        return super().get_upcoming_events(symbol)


@pytest.fixture
def clock() -> Clock:
    return Clock(NOW)


def make(db, provider, clock, **kw) -> EventService:
    return EventService(db, provider, today=lambda: TODAY, now=clock, **kw)


def test_has_calendar():
    assert has_calendar("AAA") and has_calendar("BRK-B")
    assert not has_calendar("BTC-USD") and not has_calendar("KRW-BTC")
    assert not has_calendar("KRW=X")


def test_refresh_fetches_once_per_ttl_and_skips_coins(db, clock):
    p = FakeProvider(today=TODAY, upcoming=EVENTS)
    svc = make(db, p, clock)
    svc.refresh(["BBB", "AAA", "AAA", "BTC-USD", "KRW-BTC"])
    assert p.event_calls == ["AAA", "BBB"]  # sorted, de-duplicated, coins skipped
    svc.refresh(["AAA", "BBB"])
    assert p.event_calls == ["AAA", "BBB"]  # inside the TTL: no request
    clock.t = NOW + timedelta(hours=23, minutes=59)
    svc.refresh(["AAA", "BBB"])
    assert p.event_calls == ["AAA", "BBB"]
    clock.t = NOW + timedelta(hours=25)
    svc.refresh(["AAA", "BBB"])
    assert p.event_calls == ["AAA", "BBB", "AAA", "BBB"]
    svc.refresh([])
    svc.refresh(["BTC-USD"])
    assert p.event_calls == ["AAA", "BBB", "AAA", "BBB"]


def test_refresh_stores_rows_and_sync(db, clock):
    svc = make(db, FakeProvider(today=TODAY, upcoming=EVENTS), clock)
    svc.refresh(["AAA", "BBB"])
    rows = db.scalars(select(UpcomingEventRow).order_by(UpcomingEventRow.event_date)).all()
    assert [(r.symbol, r.kind, r.event_date, r.estimated) for r in rows] == [
        ("AAA", "ex_dividend", day(-2), False),
        ("AAA", "earnings", day(3), True),
        ("BBB", "earnings", day(7), False),
        ("AAA", "ex_dividend", day(30), False),
    ]
    assert {r.source for r in rows} == {"yfinance"}
    assert {r.fetched_at for r in rows} == {NOW}
    sync = db.get(EventSync, "AAA")
    assert sync is not None and sync.fetched_at == NOW and sync.error is None


def test_upcoming_filters_window_and_past_dates(db, clock):
    svc = make(db, FakeProvider(today=TODAY, upcoming=EVENTS), clock)
    svc.refresh(["AAA", "BBB"])
    events, stale, errors = svc.upcoming(["BBB", "AAA", "BTC-USD"], 7)
    assert events == [
        UpcomingEvent("AAA", "earnings", day(3), True),
        UpcomingEvent("BBB", "earnings", day(7), False),  # day 7 is inside [today, today+7]
    ]
    assert stale == [] and errors == {}
    events, _, _ = svc.upcoming(["AAA"], 30)
    assert [(e.kind, e.date) for e in events] == [("earnings", day(3)), ("ex_dividend", day(30))]
    events, _, _ = svc.upcoming(["AAA"], 2)
    assert events == []
    assert svc.upcoming([], 7) == ([], [], {})
    assert svc.upcoming(["BTC-USD", "KRW-BTC"], 7) == ([], [], {})


def test_upcoming_orders_by_date_then_symbol(db, clock):
    upcoming = {
        "AAA": [UpcomingEvent("AAA", "earnings", day(5))],
        "BBB": [
            UpcomingEvent("BBB", "ex_dividend", day(1)),
            UpcomingEvent("BBB", "earnings", day(5)),
        ],
    }
    svc = make(db, FakeProvider(today=TODAY, upcoming=upcoming), clock)
    svc.refresh(["AAA", "BBB"])
    events, _, _ = svc.upcoming(["AAA", "BBB"], 7)
    assert [(e.date, e.symbol, e.kind) for e in events] == [
        (day(1), "BBB", "ex_dividend"),
        (day(5), "AAA", "earnings"),
        (day(5), "BBB", "earnings"),
    ]


def test_upcoming_without_refresh_is_stale(db, clock):
    svc = make(db, FakeProvider(today=TODAY, upcoming=EVENTS), clock)
    events, stale, errors = svc.upcoming(["BBB", "AAA", "BTC-USD"], 7)
    assert events == [] and stale == ["AAA", "BBB"] and errors == {}


def test_upcoming_marks_expired_sync_stale_but_keeps_events(db, clock):
    svc = make(db, FakeProvider(today=TODAY, upcoming=EVENTS), clock)
    svc.refresh(["AAA", "BBB"])
    clock.t = NOW + timedelta(hours=25)
    events, stale, errors = svc.upcoming(["AAA", "BBB"], 7)
    assert len(events) == 2 and stale == ["AAA", "BBB"] and errors == {}


def test_failed_fetch_keeps_rows_reports_error_and_retries(db, clock):
    p = FailingProvider(fail=set(), today=TODAY, upcoming=EVENTS)
    svc = make(db, p, clock)
    svc.refresh(["AAA", "BBB"])
    clock.t = NOW + timedelta(hours=25)
    p.fail = {"AAA"}
    svc.refresh(["AAA", "BBB"])

    events, stale, errors = svc.upcoming(["AAA", "BBB"], 7)
    assert [e.symbol for e in events] == ["AAA", "BBB"]  # AAA's old rows survive the failure
    assert stale == ["AAA"]
    assert errors == {"AAA": "calendar down for AAA"}  # message only, no attempt time
    aaa, bbb = db.get(EventSync, "AAA"), db.get(EventSync, "BBB")
    # The last success time is kept; the attempt time rides inside `error` (no new column).
    assert aaa.fetched_at == NOW
    assert split_error(aaa.error) == (NOW + timedelta(hours=25), "calendar down for AAA")
    assert bbb.fetched_at == NOW + timedelta(hours=25) and bbb.error is None

    # Neither symbol is asked again right away: BBB is fresh, AAA failed less than
    # `error_ttl` ago (it used to be retried on every request, ISSUE in D-034 verification).
    calls_before = list(p.event_calls)
    svc.refresh(["AAA", "BBB"])
    assert p.event_calls == calls_before

    # Once `error_ttl` has passed since the failed attempt, AAA alone is retried.
    clock.t = NOW + timedelta(hours=25) + DEFAULT_ERROR_TTL
    p.fail = set()
    svc.refresh(["AAA", "BBB"])
    assert p.event_calls == [*calls_before, "AAA"]
    events, stale, errors = svc.upcoming(["AAA", "BBB"], 7)
    assert stale == [] and errors == {}
    assert db.get(EventSync, "AAA").fetched_at == clock.t
    assert db.get(EventSync, "AAA").error is None


def test_first_fetch_failure_records_error_without_rows(db, clock):
    p = FailingProvider(fail={"AAA"}, today=TODAY, upcoming=EVENTS)
    svc = make(db, p, clock)
    svc.refresh(["AAA"])
    events, stale, errors = svc.upcoming(["AAA"], 7)
    assert events == [] and stale == ["AAA"] and errors == {"AAA": "calendar down for AAA"}
    assert db.get(EventSync, "AAA").fetched_at == NOW
    assert split_error(db.get(EventSync, "AAA").error) == (NOW, "calendar down for AAA")
    assert db.scalars(select(UpcomingEventRow)).all() == []
    # A symbol that never succeeded is held back by `error_ttl` too.
    svc.refresh(["AAA"])
    assert p.event_calls == ["AAA"]
    clock.t = NOW + DEFAULT_ERROR_TTL
    svc.refresh(["AAA"])
    assert p.event_calls == ["AAA", "AAA"]


def test_failed_symbol_waits_error_ttl_but_stays_stale_meanwhile(db, clock):
    """A delisted ticker must not hit the provider on every 5-minute poll of the learn card:
    inside `error_ttl` no request is made, yet `upcoming()` keeps reporting it as stale with
    its message; the retry happens on the first request at or after `error_ttl`."""
    p = FailingProvider(fail={"AAA"}, today=TODAY, upcoming=EVENTS)
    svc = make(db, p, clock, error_ttl=timedelta(minutes=30))
    svc.refresh(["AAA", "BBB"])
    assert p.event_calls == ["AAA", "BBB"]

    for minutes in (5, 10, 15, 20, 25, 29):
        clock.t = NOW + timedelta(minutes=minutes)
        svc.refresh(["AAA", "BBB"])
        assert p.event_calls == ["AAA", "BBB"], minutes
        events, stale, errors = svc.upcoming(["AAA", "BBB"], 7)
        assert [e.symbol for e in events] == ["BBB"]
        assert stale == ["AAA"] and errors == {"AAA": "calendar down for AAA"}

    clock.t = NOW + timedelta(minutes=30)
    svc.refresh(["AAA", "BBB"])
    assert p.event_calls == ["AAA", "BBB", "AAA"]  # retried, BBB still inside its 24h TTL
    # Still failing: the attempt time moves forward and the next hold-off starts from it.
    assert split_error(db.get(EventSync, "AAA").error) == (clock.t, "calendar down for AAA")
    clock.t = NOW + timedelta(minutes=59)
    svc.refresh(["AAA", "BBB"])
    assert p.event_calls == ["AAA", "BBB", "AAA"]
    clock.t = NOW + timedelta(minutes=60)
    p.fail = set()
    svc.refresh(["AAA", "BBB"])
    assert p.event_calls == ["AAA", "BBB", "AAA", "AAA"]
    events, stale, errors = svc.upcoming(["AAA", "BBB"], 7)
    assert [e.symbol for e in events] == ["AAA", "BBB"] and stale == [] and errors == {}


def test_error_row_without_attempt_time_is_retried_once(db, clock):
    """Rows written before the attempt time was stored in `error` (plain message) have no
    hold-off: they are retried on the next request and then carry the prefix. This is the
    upgrade path instead of a migration."""
    db.add(EventSync(symbol="AAA", fetched_at=NOW - timedelta(hours=30), error="old outage"))
    db.commit()
    p = FailingProvider(fail={"AAA"}, today=TODAY, upcoming=EVENTS)
    svc = make(db, p, clock)
    _, stale, errors = svc.upcoming(["AAA"], 7)
    assert stale == ["AAA"] and errors == {"AAA": "old outage"}

    svc.refresh(["AAA"])
    assert p.event_calls == ["AAA"]
    assert split_error(db.get(EventSync, "AAA").error) == (NOW, "calendar down for AAA")
    assert db.get(EventSync, "AAA").fetched_at == NOW - timedelta(hours=30)  # last success kept
    svc.refresh(["AAA"])
    assert p.event_calls == ["AAA"]  # now held back like any other failure


def test_error_prefix_round_trip_and_column_width():
    t = datetime(2026, 11, 5, 10, 0, 0)
    assert join_error(t, "boom") == "2026-11-05T10:00:00 boom"
    assert split_error("2026-11-05T10:00:00 boom") == (t, "boom")
    assert split_error("boom") == (None, "boom")
    assert split_error("2026-11-05T10:00:00") == (None, "2026-11-05T10:00:00")
    assert split_error("not-a-time-at-all!! boom") == (None, "not-a-time-at-all!! boom")
    # Microseconds and a tz-aware clock collapse to naive UTC seconds.
    assert split_error(join_error(t.replace(microsecond=123456), "x"))[0] == t
    assert split_error(join_error(t.replace(tzinfo=UTC), "x"))[0] == t
    # The stored value fits EventSync.error (String(300)); the message is what gets cut.
    long = join_error(t, "m" * 1000)
    assert len(long) == ERROR_MAX
    assert split_error(long) == (t, "m" * (ERROR_MAX - 20))


def test_long_provider_message_is_stored_within_column(db, clock):
    class Chatty(FakeProvider):
        def get_upcoming_events(self, symbol):
            self.event_calls.append(symbol)
            raise MarketDataError("x" * 1000)

    svc = make(db, Chatty(today=TODAY), clock)
    svc.refresh(["AAA"])
    stored = db.get(EventSync, "AAA").error
    assert len(stored) <= ERROR_MAX
    assert split_error(stored) == (NOW, "x" * (ERROR_MAX - 20))
    _, _, errors = svc.upcoming(["AAA"], 7)
    assert errors == {"AAA": "x" * (ERROR_MAX - 20)}


def test_refresh_replaces_rows_and_dedupes(db, clock):
    p = FakeProvider(today=TODAY, upcoming={"AAA": [UpcomingEvent("AAA", "earnings", day(3))]})
    svc = make(db, p, clock)
    svc.refresh(["AAA"])
    clock.t = NOW + timedelta(hours=25)
    dup = UpcomingEvent("AAA", "earnings", day(10), True)
    p.upcoming["AAA"] = [dup, dup, UpcomingEvent("AAA", "ex_dividend", day(4))]
    svc.refresh(["AAA"])
    rows = db.scalars(select(UpcomingEventRow).order_by(UpcomingEventRow.event_date)).all()
    assert [(r.kind, r.event_date, r.estimated) for r in rows] == [
        ("ex_dividend", day(4), False),
        ("earnings", day(10), True),
    ]
    # An empty calendar on a later success clears the old rows too.
    clock.t = NOW + timedelta(hours=50)
    p.upcoming["AAA"] = []
    svc.refresh(["AAA"])
    assert db.scalars(select(UpcomingEventRow)).all() == []
    assert svc.upcoming(["AAA"], 30) == ([], [], {})
