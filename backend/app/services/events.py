"""Upcoming earnings releases and ex-dividend dates of held stocks (DECISIONS.md D-034 §5).

The provider's calendar is looked up per symbol at most once per TTL (24 hours). All network
requests finish before anything is written, then the symbols that succeeded get their rows
replaced and the ones that failed keep their last successful rows, carry the error and are
reported as stale. A failed symbol is not asked again before `error_ttl` (1 hour) has passed
since the last attempt: the home learn card polls `/api/learn/week` every 5 minutes, so a
delisted ticker would otherwise hit the provider on every poll. Coins, Upbit markets and the
FX rate are never looked up. The dates are facts, not signals: the learn page shows them next
to the user's own rules and never with a direction.

Where the last attempt time lives: `event_syncs` has only `fetched_at` (last success, kept
across failures so the TTL of the stored rows still means something) and `error`. Rather than
add a column (migration) or keep an in-memory map (the service is built per request in
`deps.get_learn_service`, so instance state would not survive to the next poll), the attempt
time is stored as a fixed-width ISO prefix inside `error` itself: `"2026-11-05T10:00:00 msg"`.
`split_error` takes it apart; `upcoming()` returns only the message. Rows written before this
scheme have no prefix, count as "attempt time unknown" and are retried once, after which they
carry the prefix.
"""

import logging
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.data.assets import FX_USDKRW, trades_every_day
from app.data.provider import MarketDataProvider, UpcomingEvent
from app.db.models import EventSync, UpcomingEventRow

log = logging.getLogger(__name__)

DEFAULT_TTL = timedelta(hours=24)
DEFAULT_ERROR_TTL = timedelta(hours=1)
MAX_WORKERS = 8
EVENT_KINDS = ("earnings", "ex_dividend")
ERROR_MAX = 300  # EventSync.error is String(300)
_ATTEMPT_WIDTH = 19  # len("2026-11-05T10:00:00")


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def has_calendar(symbol: str) -> bool:
    """Only stocks and ETFs have earnings or dividends: coins (`BTC-USD`), Upbit markets
    (`KRW-BTC`) and the FX rate are skipped without a request."""
    return not (trades_every_day(symbol) or symbol.startswith("KRW-") or symbol == FX_USDKRW)


def _stocks(symbols: Sequence[str]) -> list[str]:
    return sorted({s for s in symbols if has_calendar(s)})


def join_error(attempted_at: datetime, message: str) -> str:
    """`error` column value: last attempt time (UTC, seconds) + space + message, within the
    column width. The message is what the provider raised, trimmed to fit."""
    if attempted_at.tzinfo is not None:  # the service clock is naive UTC; be safe anyway
        attempted_at = attempted_at.astimezone(UTC).replace(tzinfo=None)
    prefix = attempted_at.replace(microsecond=0).isoformat(timespec="seconds")
    return f"{prefix} {message}"[:ERROR_MAX]


def split_error(error: str) -> tuple[datetime | None, str]:
    """Inverse of `join_error`. A value without the prefix (written before the attempt time
    was stored) comes back as `(None, error)`."""
    if len(error) > _ATTEMPT_WIDTH and error[_ATTEMPT_WIDTH] == " ":
        try:
            return datetime.fromisoformat(error[:_ATTEMPT_WIDTH]), error[_ATTEMPT_WIDTH + 1 :]
        except ValueError:
            pass
    return None, error


class EventService:
    def __init__(
        self,
        db: Session,
        provider: MarketDataProvider,
        today: Callable[[], date] = date.today,
        now: Callable[[], datetime] = _utcnow,
        ttl: timedelta = DEFAULT_TTL,
        error_ttl: timedelta = DEFAULT_ERROR_TTL,
        source: str = "yfinance",
    ) -> None:
        self.db = db
        self.provider = provider
        self.today = today
        self.now = now
        self.ttl = ttl
        self.error_ttl = error_ttl
        self.source = source

    def refresh(self, symbols: Sequence[str]) -> None:
        """Fetch the calendar of every due stock symbol and store it in one transaction.

        Due means no sync row, a successful sync row older than the TTL, or a failed one
        whose last attempt is older than `error_ttl` (or unknown). Network first, in
        parallel; nothing is written until every request is back.
        """
        wanted = _stocks(symbols)
        if not wanted:
            return
        now = self.now()
        syncs = self._syncs(wanted)
        due = [s for s in wanted if self._due(syncs.get(s), now)]
        if not due:
            return
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(due))) as pool:
            results = list(pool.map(self._fetch, due))

        for symbol, (events, message) in zip(due, results, strict=True):
            existing = syncs.get(symbol)
            if message is None:
                self._replace_rows(symbol, events or [], now)
                fetched_at, error = now, None
            else:
                # Keep the last successful rows and their fetch time (the symbol stays
                # stale); the attempt time in `error` holds the retry back for `error_ttl`.
                fetched_at = existing.fetched_at if existing is not None else now
                error = join_error(now, message)
            stmt = sqlite_insert(EventSync).values(
                symbol=symbol, fetched_at=fetched_at, error=error
            )
            self.db.execute(
                stmt.on_conflict_do_update(
                    index_elements=["symbol"],
                    set_={"fetched_at": stmt.excluded.fetched_at, "error": stmt.excluded.error},
                )
            )
        self.db.commit()

    def upcoming(
        self, symbols: Sequence[str], days: int
    ) -> tuple[list[UpcomingEvent], list[str], dict[str, str]]:
        """Stored events in [today, today + days] for the stock symbols, ordered by date then
        symbol, plus the symbols whose data is stale (never fetched, past the TTL or failed,
        whether or not a retry is due yet) and the error message per failed symbol without
        the stored attempt time. No network."""
        wanted = _stocks(symbols)
        if not wanted:
            return [], [], {}
        today = self.today()
        end = today + timedelta(days=days)
        rows = self.db.scalars(
            select(UpcomingEventRow)
            .where(
                UpcomingEventRow.symbol.in_(wanted),
                UpcomingEventRow.event_date >= today,
                UpcomingEventRow.event_date <= end,
            )
            .order_by(UpcomingEventRow.event_date, UpcomingEventRow.symbol, UpcomingEventRow.kind)
            .execution_options(populate_existing=True)
        )
        events = [
            UpcomingEvent(r.symbol, r.kind, r.event_date, bool(r.estimated))  # type: ignore[arg-type]
            for r in rows
        ]
        now = self.now()
        syncs = self._syncs(wanted)
        stale = [s for s in wanted if self._stale(syncs.get(s), now)]
        errors = {
            s: split_error(syncs[s].error)[1] for s in wanted if s in syncs and syncs[s].error
        }
        return events, stale, errors

    def _fetch(self, symbol: str) -> tuple[list[UpcomingEvent] | None, str | None]:
        try:
            return self.provider.get_upcoming_events(symbol), None
        except Exception as exc:  # MarketDataError, or whatever the scraper lets through
            log.warning("upcoming events for %s failed: %s", symbol, exc)
            return None, str(exc) or type(exc).__name__

    def _replace_rows(self, symbol: str, events: list[UpcomingEvent], now: datetime) -> None:
        self.db.execute(delete(UpcomingEventRow).where(UpcomingEventRow.symbol == symbol))
        seen: set[tuple[str, date]] = set()
        values = []
        for e in events:
            if e.kind not in EVENT_KINDS or (e.kind, e.date) in seen:
                continue
            seen.add((e.kind, e.date))
            values.append(
                {
                    "symbol": symbol,
                    "kind": e.kind,
                    "event_date": e.date,
                    "estimated": bool(e.estimated),
                    "fetched_at": now,
                    "source": self.source,
                }
            )
        if not values:
            return
        # Upsert rather than plain insert: two concurrent requests may both refresh a symbol.
        stmt = sqlite_insert(UpcomingEventRow).values(values)
        self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=["symbol", "kind", "event_date"],
                set_={k: stmt.excluded[k] for k in ("estimated", "fetched_at", "source")},
            )
        )

    def _syncs(self, symbols: list[str]) -> dict[str, EventSync]:
        rows = self.db.scalars(
            select(EventSync)
            .where(EventSync.symbol.in_(symbols))
            .execution_options(populate_existing=True)
        )
        return {s.symbol: s for s in rows}

    def _stale(self, sync: EventSync | None, now: datetime) -> bool:
        """Reported to the caller: never fetched, last attempt failed, or past the TTL."""
        return sync is None or sync.error is not None or now - sync.fetched_at >= self.ttl

    def _due(self, sync: EventSync | None, now: datetime) -> bool:
        """Worth a request now: stale, and if the last attempt failed, `error_ttl` has passed
        since it (an error without a stored attempt time is retried right away)."""
        if sync is None:
            return True
        if sync.error is not None:
            attempted_at, _ = split_error(sync.error)
            return attempted_at is None or now - attempted_at >= self.error_ttl
        return now - sync.fetched_at >= self.ttl
