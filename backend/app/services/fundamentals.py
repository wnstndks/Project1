"""Cached company fundamentals per stock (DECISIONS.md D-036).

The provider is asked per symbol at most once per TTL (24 hours). All network requests finish
before anything is written; then every symbol's row is updated in one transaction. A symbol
that succeeded gets its payload replaced. One that failed keeps its last successful payload
and fetch time, carries the error and is reported as stale, and is not asked again before
`error_ttl` (1 hour) has passed since that attempt, so a delisted ticker on a polled screen
does not hit the provider on every request. A failure never turns into made-up figures.

Two kinds of asset have no figures and come back with `supported=False`: coins, Upbit markets
and the FX rate, which are answered without the provider or the cache, and what the provider
identifies as a fund (an ETF) after a lookup, which is cached like any other result (a row
with a fetch time and no payload).

The payload is the provider's `Fundamentals` as JSON. One written by an older shape of that
dataclass cannot be read back and counts as a cache miss, never as partial figures.

There is no in-process cache: the service is built per request and the table is the cache.

Requests that arrive together do not each ask the provider. A request that finds something
due takes a process-wide lock, decides again what is due (the request that held the lock
before it has usually just stored it, or just failed to, which holds the retry back all the
same) and only then fetches. So a burst on a polled screen costs one lookup per symbol and
one pool of worker threads, not one per request. A request whose symbols are all cached
never takes the lock. This relies on the app running as a single process (one uvicorn
worker, DECISIONS.md D-035); a second process would only repeat the lookup, not corrupt
anything, because the writes are upserts.
"""

import logging
import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, fields
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import null, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.data.assets import has_fundamentals
from app.data.provider import Fundamentals, MarketDataProvider, StatementRow
from app.db.models import FundamentalsRow

log = logging.getLogger(__name__)

DEFAULT_TTL = timedelta(hours=24)
DEFAULT_ERROR_TTL = timedelta(hours=1)
MAX_WORKERS = 8
ERROR_MAX = 300  # FundamentalsRow.error is String(300)

# One refresh at a time in this process. Module state, not an attribute: the service is
# built per request, so an instance lock would never be shared.
_REFRESH_LOCK = threading.Lock()

_TEXT_FIELDS = ("symbol", "currency", "name", "sector", "industry", "summary")
_STATEMENT_FIELDS = ("annual", "quarterly")
_FIELD_NAMES = tuple(f.name for f in fields(Fundamentals))
_NUMBER_FIELDS = tuple(
    name for name in _FIELD_NAMES if name not in _TEXT_FIELDS + _STATEMENT_FIELDS
)
_ROW_NUMBERS = ("revenue", "operating_income", "net_income")


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class FundamentalsView:
    """What a screen needs about one symbol.

    `data` is the last successful figures (None when there are none). `fetched_at` is when
    they were fetched (naive UTC). `stale` means they are not from a successful fetch inside
    the TTL: the last attempt failed (`error` says why) or nothing was ever fetched.
    `supported=False` means the asset has no company statements (a coin, an ETF), which is
    not an error.
    """

    symbol: str
    data: Fundamentals | None
    fetched_at: datetime | None
    stale: bool
    error: str | None
    supported: bool


def to_payload(data: Fundamentals) -> dict[str, Any]:
    """`dataclasses.asdict` with the statement rows as lists and their dates as ISO strings,
    so the result is plain JSON."""
    payload = asdict(data)
    for name in _STATEMENT_FIELDS:
        payload[name] = [
            {**row, "period_end": row["period_end"].isoformat()} for row in payload[name]
        ]
    return payload


def from_payload(payload: Any) -> Fundamentals | None:
    """Inverse of `to_payload`. None when the payload does not have exactly the fields of
    today's `Fundamentals` with values of the right kind (a row written before the dataclass
    changed, or damaged): the caller treats that as "not cached" instead of guessing."""
    if not isinstance(payload, dict) or set(payload) != set(_FIELD_NAMES):
        return None
    try:
        values: dict[str, Any] = {name: _text(payload[name]) for name in _TEXT_FIELDS}
        if values["symbol"] is None:
            return None
        values |= {name: _number(payload[name]) for name in _NUMBER_FIELDS}
        values |= {name: _rows(payload[name]) for name in _STATEMENT_FIELDS}
    except (TypeError, ValueError, KeyError):
        return None
    return Fundamentals(**values)


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise TypeError(f"not text: {value!r}")


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"not a number: {value!r}")
    return float(value)


def _rows(value: Any) -> tuple[StatementRow, ...]:
    if not isinstance(value, list | tuple):
        raise TypeError(f"not statement rows: {value!r}")
    rows = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"period_end", *_ROW_NUMBERS}:
            raise TypeError(f"not a statement row: {item!r}")
        rows.append(
            StatementRow(
                date.fromisoformat(item["period_end"]),
                *(_number(item[name]) for name in _ROW_NUMBERS),
            )
        )
    return tuple(rows)


@dataclass(frozen=True)
class _Fetched:
    """Outcome of one provider call: figures, "no statements" (`data` None) or a failure."""

    data: Fundamentals | None = None
    error: str | None = None


class FundamentalsService:
    def __init__(
        self,
        db: Session,
        provider: MarketDataProvider,
        now: Callable[[], datetime] = _utcnow,
        ttl: timedelta = DEFAULT_TTL,
        error_ttl: timedelta = DEFAULT_ERROR_TTL,
    ) -> None:
        self.db = db
        self.provider = provider
        self.now = now
        self.ttl = ttl
        self.error_ttl = error_ttl

    def get(self, symbol: str) -> FundamentalsView:
        return self.get_many([symbol])[0]

    def get_many(self, symbols: Sequence[str]) -> list[FundamentalsView]:
        """One view per distinct symbol, in the order given.

        Symbols that are due (no row, a success older than the TTL, an unreadable payload, or
        a failure whose attempt is older than `error_ttl`) are fetched first: network in
        parallel, nothing written until every request is back, then one transaction. When
        nothing is due this is a read of the cache and takes no lock.
        """
        wanted = list(dict.fromkeys(symbols))
        stocks = [s for s in wanted if has_fundamentals(s)]
        now = self.now()
        rows = self._load(stocks)
        if any(self._due(rows.get(s), now) for s in stocks):
            rows, now = self._refresh(stocks)
        return [
            self._view(s, rows.get(s), now)
            if has_fundamentals(s)
            else FundamentalsView(s, None, None, False, None, False)
            for s in wanted
        ]

    def _refresh(self, stocks: list[str]) -> tuple[dict[str, FundamentalsRow], datetime]:
        """Fetch and store what is due, one request at a time in the process. Returns the
        rows as they are afterwards and the time the decision was made at.

        What is due is decided again under the lock, from a fresh read: while this request
        waited, the one holding the lock may have fetched the same symbols. The lock is held
        across the network on purpose, so that the waiting requests find the result instead
        of starting their own lookups.
        """
        with _REFRESH_LOCK:
            now = self.now()
            rows = self._load(stocks)
            due = [s for s in stocks if self._due(rows.get(s), now)]
            if due:
                with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(due))) as pool:
                    fetched = list(pool.map(self._fetch, due))
                for symbol, result in zip(due, fetched, strict=True):
                    self._store(symbol, result, now)
                self.db.commit()
                rows = self._load(stocks)
        return rows, now

    def _fetch(self, symbol: str) -> _Fetched:
        try:
            return _Fetched(data=self.provider.get_fundamentals(symbol))
        except Exception as exc:  # MarketDataError, or whatever the scraper lets through
            log.warning("fundamentals for %s failed: %s", symbol, exc)
            return _Fetched(error=(str(exc) or type(exc).__name__)[:ERROR_MAX])

    def _store(self, symbol: str, result: _Fetched, now: datetime) -> None:
        if result.error is None:
            payload = to_payload(result.data) if result.data is not None else null()
            values = {"fetched_at": now, "attempted_at": now, "payload": payload, "error": None}
            keep: tuple[str, ...] = ()
        else:
            # Keep the last successful payload and its fetch time; only the attempt moves.
            values = {"fetched_at": None, "attempted_at": now, "payload": null()}
            values["error"] = result.error
            keep = ("fetched_at", "payload")
        stmt = sqlite_insert(FundamentalsRow).values(symbol=symbol, **values)
        self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=["symbol"],
                set_={k: stmt.excluded[k] for k in values if k not in keep},
            )
        )

    def _load(self, symbols: list[str]) -> dict[str, FundamentalsRow]:
        if not symbols:
            return {}
        found = self.db.scalars(
            select(FundamentalsRow)
            .where(FundamentalsRow.symbol.in_(symbols))
            .execution_options(populate_existing=True)
        )
        return {row.symbol: row for row in found}

    def _due(self, row: FundamentalsRow | None, now: datetime) -> bool:
        """Worth a request now. After a failure the hold-off runs from that attempt, whatever
        is stored; otherwise from the last success, unless its payload cannot be read."""
        if row is None:
            return True
        if row.error is not None:
            return row.attempted_at is None or now - row.attempted_at >= self.error_ttl
        if row.fetched_at is None:
            return True
        if row.payload is not None and from_payload(row.payload) is None:
            return True
        return now - row.fetched_at >= self.ttl

    def _view(self, symbol: str, row: FundamentalsRow | None, now: datetime) -> FundamentalsView:
        if row is None:  # not reachable through get_many, which always leaves a row
            return FundamentalsView(symbol, None, None, True, None, True)
        data = from_payload(row.payload) if row.payload is not None else None
        # A success without a payload is the provider saying "no statements" (an ETF). A
        # payload that cannot be read is not that, and its fetch time dates nothing usable.
        unreadable = row.payload is not None and data is None
        fetched_at = None if unreadable else row.fetched_at
        return FundamentalsView(
            symbol=symbol,
            data=data,
            fetched_at=fetched_at,
            stale=row.error is not None or fetched_at is None or now - fetched_at >= self.ttl,
            error=row.error,
            supported=not (row.payload is None and row.fetched_at is not None),
        )
