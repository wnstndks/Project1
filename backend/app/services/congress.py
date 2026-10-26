"""US House members' stock trades (STOCK Act periodic transaction reports): daily sync, cache
and per-symbol reads.

Sync reads the Clerk's yearly index for this year and last, picks the periodic transaction
reports filed in the last `LOOKBACK` days that are not stored yet, downloads and parses up to
`MAX_DOCS_PER_SYNC` of them (newest first), and only then writes everything in one
transaction. One trigger repeats that batch, with a short pause, while documents are pending
and the batch made progress, up to `max_batches` (AM_CONGRESS_MAX_BATCHES): a first visit's
year of backlog (several hundred PDFs) is fetched in one background run instead of one batch a
day. A failed index fetch writes nothing but the error and stops the run; a failed document is
recorded as `failed` and retried on a later sync, a scanned document as `no_text` and never
retried. The last good data stays in place either way, with `stale` on the status.

ORM rows (app.db.models, added with the F2 migration):
- CongressTrade / congress_trades: id, source, year, doc_id, row_no, member, chamber, state,
  district, party, owner, asset_name, asset_type, symbol, side, transaction_date,
  notification_date, filing_date, amount_low, amount_high, amount_label, cap_gains_over_200,
  fetched_at. Unique (source, doc_id, row_no).
- CongressDoc / congress_docs: source + doc_id (pk), year, member, filing_date, status
  ("parsed" | "no_text" | "failed"), rows, error, fetched_at.
- CongressSync / congress_syncs: source (pk), synced_at, index_modified, docs_total, error.

This is public-record data about elected officials, not a signal: the screen names the 45-day
filing delay, the amount ranges and the family accounts (DECISIONS.md D-030).
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.data.congress_provider import (
    CongressDataError,
    CongressProvider,
    IndexEntry,
    PtrDocument,
    normalize_symbol,
    ptr_url,
)
from app.db.models import CongressDoc, CongressSync, CongressTrade

log = logging.getLogger(__name__)

SOURCE = "house"
CHAMBER = "house"
# The Clerk updates the index about once a day; after a failure the source is tried again
# sooner, but not on every request. While documents are still waiting for their first
# download (a first visit's backlog) a new run may start after a short pause instead of the
# daily TTL, so the manual "fetch now" button keeps working; the index ZIP is still read at most
# once per run. Documents that failed wait for the daily TTL like before, so a PDF the Clerk's
# site cannot serve does not cause a run every ten minutes.
SYNC_TTL = timedelta(hours=24)
FAIL_RETRY = timedelta(hours=1)
BACKLOG_RETRY = timedelta(minutes=10)
# Data older than this is stale even when the last sync succeeded (weekends have no filings,
# so three days rather than one).
MAX_AGE = timedelta(days=3)
# Filings older than this are not fetched; the API shows the last few months anyway.
LOOKBACK = timedelta(days=365)
# Documents fetched per batch: each is a 60-130 KB PDF, and a first sync has a year's backlog.
MAX_DOCS_PER_SYNC = 60
# Batches one trigger runs back to back (the setting's default), and the pause between them so
# the Clerk's site is not hammered.
MAX_BATCHES_PER_SYNC = 10
BATCH_PAUSE = 1.5  # seconds
# Once this instant (UTC) has passed, documents parsed before it are downloaded and parsed
# again, once, after the new and the failed ones: the parser changed on 2026-10-23 (ISSUE-045:
# rows after an "S O" / "D" label were dropped or their asset name truncated). Move it forward
# when the parser changes again; `parsed` documents are otherwise never re-read.
REPARSE_BEFORE = datetime(2026, 10, 23, 10, 50)

DOC_PARSED = "parsed"
DOC_NO_TEXT = "no_text"
DOC_FAILED = "failed"

_in_flight: set[str] = set()
_lock = threading.Lock()


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class Trade:
    symbol: str | None
    asset_name: str
    asset_type: str | None
    member: str
    chamber: str
    state: str
    district: str
    party: str | None
    owner: str  # SELF | SP | DC | JT
    side: str  # buy | sell | sell_partial | exchange
    transaction_date: date
    notification_date: date | None
    filing_date: date
    amount_low: int
    amount_high: int | None
    amount_label: str
    cap_gains_over_200: bool | None
    doc_id: str
    doc_url: str


@dataclass(frozen=True)
class CongressStatus:
    source: str
    synced_at: datetime | None
    index_modified: datetime | None
    stale: bool
    syncing: bool  # a background run is working through batches right now
    error: str | None
    docs_total: int  # periodic transaction reports in the lookback window at the last sync
    docs_parsed: int
    docs_no_text: int  # scanned paper filings that cannot be read
    docs_failed: int
    docs_pending: int  # still to download (first sync works through a backlog in batches)
    trades: int


@dataclass(frozen=True)
class SyncResult:
    fetched: bool  # False when skipped (TTL or already running)
    batches: int
    docs_fetched: int
    docs_parsed: int
    docs_no_text: int
    docs_failed: int
    docs_pending: int  # after the last batch, including documents still to re-read
    error: str | None


class CongressService:
    def __init__(
        self,
        db: Session,
        provider: CongressProvider,
        now: Callable[[], datetime] = _utc_now,
        max_docs_per_sync: int = MAX_DOCS_PER_SYNC,
        lookback: timedelta = LOOKBACK,
        max_batches: int = MAX_BATCHES_PER_SYNC,
        pause: float = BATCH_PAUSE,
        sleep: Callable[[float], None] = time.sleep,
        reparse_before: datetime = REPARSE_BEFORE,
    ) -> None:
        self.db = db
        self.provider = provider
        self.now = now
        self.max_docs_per_sync = max_docs_per_sync
        self.lookback = lookback
        self.max_batches = max(1, max_batches)
        self.pause = pause
        self.sleep = sleep
        self.reparse_before = reparse_before

    # --- reads ---------------------------------------------------------------------------

    def status(self) -> CongressStatus:
        sync = self.db.get(CongressSync, SOURCE)
        counts = self._doc_counts()
        trades = self.db.scalar(
            select(func.count()).select_from(CongressTrade).where(CongressTrade.source == SOURCE)
        )
        now = self.now()
        stale = sync is None or sync.error is not None or now - sync.synced_at > MAX_AGE
        total = sync.docs_total if sync else 0
        with _lock:
            syncing = SOURCE in _in_flight
        return CongressStatus(
            source=SOURCE,
            synced_at=sync.synced_at if sync else None,
            index_modified=sync.index_modified if sync else None,
            stale=stale,
            syncing=syncing,
            error=sync.error if sync else None,
            docs_total=total,
            docs_parsed=counts.get(DOC_PARSED, 0),
            docs_no_text=counts.get(DOC_NO_TEXT, 0),
            docs_failed=counts.get(DOC_FAILED, 0),
            docs_pending=_pending(total, counts),
            trades=trades or 0,
        )

    def trades(
        self, symbols: list[str], since: date | None = None, limit: int = 500
    ) -> list[Trade]:
        """Stored trades in my symbols (any spelling: "brk.b" matches "BRK-B"), newest
        transaction first."""
        wanted = {normalize_symbol(s) for s in symbols if s and s.strip()}
        if not wanted:
            return []
        stmt = (
            select(CongressTrade)
            .where(CongressTrade.source == SOURCE, CongressTrade.symbol.in_(wanted))
            .order_by(
                CongressTrade.transaction_date.desc(),
                CongressTrade.filing_date.desc(),
                CongressTrade.id,
            )
            .limit(limit)
        )
        if since is not None:
            stmt = stmt.where(CongressTrade.transaction_date >= since)
        return [_to_trade(r) for r in self.db.scalars(stmt)]

    # --- sync ----------------------------------------------------------------------------

    def due(self) -> bool:
        """Whether `sync()` would fetch now: nothing stored yet, the TTL has passed (an hour
        after a failure), or documents never downloaded (or parsed before the parser changed)
        are waiting and the backlog pause has passed; and no run is in flight. The API
        schedules a background run only when this is true."""
        with _lock:
            if SOURCE in _in_flight:
                return False
        return self._is_due(self.db.get(CongressSync, SOURCE), self.now())

    def _is_due(self, sync: CongressSync | None, now: datetime) -> bool:
        if sync is None:
            return True
        wait = _interval(sync)
        if sync.error is None and (
            _unfetched(sync.docs_total, self._doc_counts()) > 0 or self._to_reparse(now) > 0
        ):
            wait = min(wait, BACKLOG_RETRY)
        return now - sync.synced_at >= wait

    def _to_reparse(self, now: datetime) -> int:
        """Stored documents parsed before the parser changed, within the lookback window."""
        if now < self.reparse_before:
            return 0
        return (
            self.db.scalar(
                select(func.count())
                .select_from(CongressDoc)
                .where(
                    CongressDoc.source == SOURCE,
                    CongressDoc.status == DOC_PARSED,
                    CongressDoc.fetched_at < self.reparse_before,
                    CongressDoc.filing_date >= now.date() - self.lookback,
                )
            )
            or 0
        )

    def sync(self, force: bool = False) -> SyncResult:
        now = self.now()
        sync = self.db.get(CongressSync, SOURCE)
        if not force and not self._is_due(sync, now):
            return self._skipped(sync)
        with _lock:
            if SOURCE in _in_flight:
                return self._skipped(sync)
            _in_flight.add(SOURCE)
        try:
            return self._loop(sync)
        finally:
            with _lock:
                _in_flight.discard(SOURCE)

    def _loop(self, previous: CongressSync | None) -> SyncResult:
        """Batches back to back while documents are pending and the last batch made progress
        (a batch of nothing but failures would otherwise retry the same documents forever)."""
        results: list[SyncResult] = []
        indexed: tuple[list[IndexEntry], datetime | None] | None = None
        for batch in range(self.max_batches):
            if batch:
                self.sleep(self.pause)
            result, indexed = self._run(self.now(), previous, indexed)
            results.append(result)
            progress = result.docs_parsed + result.docs_no_text
            if result.error or result.docs_pending == 0 or progress == 0:
                break
            previous = self.db.get(CongressSync, SOURCE)
        last = results[-1]
        return SyncResult(
            fetched=True,
            batches=len(results),
            docs_fetched=sum(r.docs_fetched for r in results),
            docs_parsed=sum(r.docs_parsed for r in results),
            docs_no_text=sum(r.docs_no_text for r in results),
            docs_failed=sum(r.docs_failed for r in results),
            docs_pending=last.docs_pending,
            error=last.error,
        )

    def _run(
        self,
        now: datetime,
        previous: CongressSync | None,
        indexed: tuple[list[IndexEntry], datetime | None] | None = None,
    ) -> tuple[SyncResult, tuple[list[IndexEntry], datetime | None] | None]:
        """One batch. `indexed` carries the index entries read by an earlier batch of the same
        run, so the index is fetched once per trigger."""
        # 1. Indexes: network only. Failure leaves the stored trades and documents alone.
        if indexed is None:
            try:
                indexed = self._indexes(now)
            except CongressDataError as exc:
                message = _short(exc)
                log.warning("congress sync failed: %s", message)
                self._upsert_sync(
                    now,
                    index_modified=previous.index_modified if previous else None,
                    docs_total=previous.docs_total if previous else 0,
                    error=message,
                )
                self.db.commit()
                counts = self._doc_counts()
                total = previous.docs_total if previous else 0
                failed = SyncResult(True, 1, 0, 0, 0, 0, _pending(total, counts), message)
                return failed, None
        entries, modified = indexed

        cutoff = now.date() - self.lookback
        due = [e for e in entries if e.is_ptr and e.filing_date and e.filing_date >= cutoff]
        due.sort(key=lambda e: (e.filing_date, e.doc_id), reverse=True)
        known = {
            d.doc_id: d
            for d in self.db.scalars(select(CongressDoc).where(CongressDoc.source == SOURCE))
        }
        # New documents first (newest filing first), failed ones retried after them, then the
        # ones parsed before the parser changed (once that instant has passed; a document read
        # in this run gets a `fetched_at` after it, so none is read twice).
        fresh = [e for e in due if e.doc_id not in known]
        retry = [e for e in due if e.doc_id in known and known[e.doc_id].status == DOC_FAILED]

        def stale(doc: CongressDoc) -> bool:
            return (
                now >= self.reparse_before
                and doc.status == DOC_PARSED
                and doc.fetched_at < self.reparse_before
            )

        reparse = [e for e in due if e.doc_id in known and stale(known[e.doc_id])]
        batch = (fresh + retry + reparse)[: self.max_docs_per_sync]
        taken = {e.doc_id for e in batch}
        reparse_left = sum(e.doc_id not in taken for e in reparse)
        # A stored document the Clerk no longer lists cannot be re-read: stop counting it as
        # waiting, or `due()` would ask for a run every ten minutes for nothing.
        listed = {e.doc_id for e in due}
        for doc in known.values():
            if stale(doc) and doc.doc_id not in listed and (doc.filing_date or cutoff) >= cutoff:
                log.info("congress: %s is no longer in the index; not re-read", doc.doc_id)
                doc.fetched_at = now

        # 2. Documents: network and parsing, all in memory.
        outcomes = [(entry, self._fetch_doc(entry)) for entry in batch]

        # 3. One transaction.
        parsed = no_text = failed = 0
        for entry, outcome in outcomes:
            status = self._store(entry, outcome, now)
            parsed += status == DOC_PARSED
            no_text += status == DOC_NO_TEXT
            failed += status == DOC_FAILED
        # Rows stored before tickers were normalised ("BRK.B", "BRK/B") get the app's spelling
        # too (the SQL mirror of congress_provider.normalize_symbol).
        self.db.execute(
            update(CongressTrade)
            .where(
                CongressTrade.source == SOURCE,
                or_(CongressTrade.symbol.like("%.%"), CongressTrade.symbol.like("%/%")),
            )
            .values(
                symbol=func.upper(
                    func.replace(func.replace(CongressTrade.symbol, ".", "-"), "/", "-")
                )
            )
        )
        self._upsert_sync(now, index_modified=modified, docs_total=len(due), error=None)
        self.db.commit()
        counts = self._doc_counts()
        result = SyncResult(
            fetched=True,
            batches=1,
            docs_fetched=len(batch),
            docs_parsed=parsed,
            docs_no_text=no_text,
            docs_failed=failed,
            docs_pending=_pending(len(due), counts) + reparse_left,
            error=None,
        )
        return result, indexed

    def _indexes(self, now: datetime) -> tuple[list[IndexEntry], datetime | None]:
        """This year's and last year's filings (a year's index also holds filings made the
        following January). This year's index may not exist yet in January, which is not an
        error; a missing earlier index is."""
        entries: list[IndexEntry] = []
        modified: datetime | None = None
        for year in (now.year, now.year - 1):
            try:
                result = self.provider.index(year)
            except CongressDataError as exc:
                if exc.status == 404 and year == now.year:
                    continue
                raise
            entries.extend(result.entries)
            if result.modified and (modified is None or result.modified > modified):
                modified = result.modified
        return entries, modified

    def _fetch_doc(self, entry: IndexEntry) -> PtrDocument | Exception:
        try:
            return self.provider.ptr(entry.year, entry.doc_id)
        except Exception as exc:  # noqa: BLE001 - every failure becomes a recorded document error
            return exc

    def _store(self, entry: IndexEntry, outcome: PtrDocument | Exception, now: datetime) -> str:
        if isinstance(outcome, Exception):
            self._upsert_doc(entry, DOC_FAILED, rows=0, error=_short(outcome), now=now)
            return DOC_FAILED
        if outcome.no_text:
            self._upsert_doc(entry, DOC_NO_TEXT, rows=0, error=None, now=now)
            return DOC_NO_TEXT
        self.db.execute(
            delete(CongressTrade).where(
                CongressTrade.source == SOURCE, CongressTrade.doc_id == entry.doc_id
            )
        )
        self.db.add_all(
            CongressTrade(
                source=SOURCE,
                year=entry.year,
                doc_id=entry.doc_id,
                row_no=i,
                member=entry.name,
                chamber=CHAMBER,
                state=entry.state,
                district=entry.state_district,
                party=None,
                owner=row.owner,
                asset_name=row.asset_name,
                asset_type=row.asset_type,
                symbol=row.symbol,
                side=row.side,
                transaction_date=row.transaction_date,
                notification_date=row.notification_date,
                filing_date=entry.filing_date,
                amount_low=row.amount_low,
                amount_high=row.amount_high,
                amount_label=row.amount_label,
                cap_gains_over_200=row.cap_gains_over_200,
                fetched_at=now,
            )
            for i, row in enumerate(outcome.rows)
        )
        note = f"{len(outcome.warnings)} row(s) unparsed" if outcome.warnings else None
        self._upsert_doc(entry, DOC_PARSED, rows=len(outcome.rows), error=note, now=now)
        return DOC_PARSED

    # --- helpers -------------------------------------------------------------------------

    def _skipped(self, sync: CongressSync | None) -> SyncResult:
        counts = self._doc_counts()
        total = sync.docs_total if sync else 0
        return SyncResult(
            fetched=False,
            batches=0,
            docs_fetched=0,
            docs_parsed=0,
            docs_no_text=0,
            docs_failed=0,
            docs_pending=_pending(total, counts),
            error=sync.error if sync else None,
        )

    def _doc_counts(self) -> dict[str, int]:
        rows = self.db.execute(
            select(CongressDoc.status, func.count())
            .where(CongressDoc.source == SOURCE)
            .group_by(CongressDoc.status)
        ).all()
        return {status: count for status, count in rows}

    def _upsert_doc(
        self, entry: IndexEntry, status: str, rows: int, error: str | None, now: datetime
    ) -> None:
        doc = self.db.get(CongressDoc, (SOURCE, entry.doc_id))
        if doc is None:
            doc = CongressDoc(source=SOURCE, doc_id=entry.doc_id)
            self.db.add(doc)
        doc.year = entry.year
        doc.member = entry.name
        doc.filing_date = entry.filing_date
        doc.status, doc.rows, doc.error, doc.fetched_at = status, rows, error, now

    def _upsert_sync(
        self,
        synced_at: datetime,
        index_modified: datetime | None,
        docs_total: int,
        error: str | None,
    ) -> None:
        row = self.db.get(CongressSync, SOURCE)
        if row is None:
            row = CongressSync(source=SOURCE)
            self.db.add(row)
        row.synced_at, row.index_modified, row.docs_total, row.error = (
            synced_at,
            index_modified,
            docs_total,
            error,
        )


def _to_trade(r: CongressTrade) -> Trade:
    return Trade(
        symbol=r.symbol,
        asset_name=r.asset_name,
        asset_type=r.asset_type,
        member=r.member,
        chamber=r.chamber,
        state=r.state,
        district=r.district,
        party=r.party,
        owner=r.owner,
        side=r.side,
        transaction_date=r.transaction_date,
        notification_date=r.notification_date,
        filing_date=r.filing_date,
        amount_low=r.amount_low,
        amount_high=r.amount_high,
        amount_label=r.amount_label,
        cap_gains_over_200=r.cap_gains_over_200,
        doc_id=r.doc_id,
        doc_url=ptr_url(r.year, r.doc_id),
    )


def _pending(total: int, counts: dict[str, int]) -> int:
    """Documents still to be read: never downloaded or failed (the status figure)."""
    done = counts.get(DOC_PARSED, 0) + counts.get(DOC_NO_TEXT, 0)
    return max(total - done, 0)


def _unfetched(total: int, counts: dict[str, int]) -> int:
    """Documents never downloaded; failed ones are excluded, since they are retried on the
    daily schedule rather than after the backlog pause."""
    return max(total - sum(counts.values()), 0)


def _interval(sync: CongressSync) -> timedelta:
    return FAIL_RETRY if sync.error else SYNC_TTL


def _short(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    return text if len(text) <= 300 else text[:297] + "..."
