"""Well-known investors' public holdings: cached snapshots, sync TTLs and overlap with mine.

Sync keeps the last successful snapshot when a source fails and records the failure in
`guru_syncs.error`, so the screen can show old data with a "stale" mark instead of nothing.
Network calls (ARK, EDGAR, OpenFIGI) finish before any row is written. 13F investors need
`AM_SEC_USER_AGENT`; without it they are listed with that reason and never fetched.
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.data.guru_provider import (
    CusipResolver,
    GuruDataError,
    GuruHolding,
    GuruProvider,
    GuruSnapshot,
)
from app.data.gurus import GURUS, Guru, find_guru
from app.db.models import CusipTicker, GuruHoldingRecord, GuruSync
from app.services.errors import NotFoundError

log = logging.getLogger(__name__)

SYNC_TTL = {"ark": timedelta(hours=24), "13f": timedelta(days=7)}
# After a failed attempt the source is tried again sooner than the TTL, but not on every
# request: a rejected User-Agent would otherwise hit EDGAR on each page load.
FAIL_RETRY = timedelta(hours=1)
# A snapshot older than this is stale even when the last sync succeeded: ARK publishes every
# trading day; a 13F covers a quarter and may be filed 45 days after it ends.
MAX_AGE = {"ark": timedelta(days=7), "13f": timedelta(days=140)}
# CUSIPs OpenFIGI could not map are asked again after this long; hits never expire.
UNRESOLVED_RETRY = timedelta(days=30)
SEC_UA_MISSING = "AM_SEC_USER_AGENT 미설정"
MAX_WORKERS = 4

_in_flight: set[str] = set()
_lock = threading.Lock()


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class GuruStatus:
    guru: Guru
    synced_at: datetime | None
    as_of: date | None
    error: str | None
    note: str | None
    stale: bool
    holdings_count: int


@dataclass(frozen=True)
class SyncResult:
    guru_id: str
    fetched: bool  # False when skipped (TTL, unconfigured, already running)
    as_of: date | None
    error: str | None


class GuruService:
    def __init__(
        self,
        db: Session,
        provider: GuruProvider,
        resolver: CusipResolver | None = None,
        now: Callable[[], datetime] = _utc_now,
        sec_configured: bool = True,
        max_resolve_per_sync: int = 150,
    ) -> None:
        self.db = db
        self.provider = provider
        self.resolver = resolver
        self.now = now
        self.sec_configured = sec_configured
        # OpenFIGI allows 25 requests/minute of 10 CUSIPs without a key, and Bridgewater
        # alone reports ~1,000 positions, so each sync maps this many and later syncs finish.
        self.max_resolve_per_sync = max_resolve_per_sync

    # --- reads ---------------------------------------------------------------------------

    def list_all(self) -> list[GuruStatus]:
        syncs = {s.guru_id: s for s in self.db.scalars(select(GuruSync))}
        counts = self._holding_counts()
        today = self.now().date()
        out = []
        for guru in GURUS:
            sync = syncs.get(guru.id)
            error = sync.error if sync else None
            if guru.source == "13f" and not self.sec_configured:
                error = SEC_UA_MISSING
            as_of = sync.as_of if sync else None
            stale = as_of is None or error is not None or today - as_of > MAX_AGE[guru.source]
            out.append(
                GuruStatus(
                    guru=guru,
                    synced_at=sync.synced_at if sync else None,
                    as_of=as_of,
                    error=error,
                    note=sync.note if sync else None,
                    stale=stale,
                    holdings_count=counts.get(guru.id, 0),
                )
            )
        return out

    def holdings(self, guru_id: str) -> list[GuruHolding]:
        """The stored snapshot, largest position first."""
        self._guru(guru_id)
        rows = self.db.scalars(
            select(GuruHoldingRecord)
            .where(GuruHoldingRecord.guru_id == guru_id)
            .order_by(GuruHoldingRecord.value_usd.desc())
        ).all()
        return [_to_holding(r) for r in rows]

    def overlap(self, my_symbols: list[str]) -> dict[str, list[GuruHolding]]:
        """Per investor, the stored positions whose ticker is one of mine (largest first).
        Investors with no match are left out."""
        wanted = {s.upper() for s in my_symbols if s}
        if not wanted:
            return {}
        rows = self.db.scalars(
            select(GuruHoldingRecord)
            .where(GuruHoldingRecord.symbol.in_(wanted))
            .order_by(GuruHoldingRecord.value_usd.desc())
        ).all()
        out: dict[str, list[GuruHolding]] = {}
        for r in rows:
            out.setdefault(r.guru_id, []).append(_to_holding(r))
        return out

    # --- sync ----------------------------------------------------------------------------

    def sync(self, guru_id: str, force: bool = False) -> SyncResult:
        guru = self._guru(guru_id)
        results = self._sync_many([guru], force)
        return results[guru.id]

    def sync_all(self, force: bool = False) -> dict[str, SyncResult]:
        """Fetches due investors in parallel (network only), then writes one by one."""
        return self._sync_many(list(GURUS), force)

    def _sync_many(self, gurus: list[Guru], force: bool) -> dict[str, SyncResult]:
        now = self.now()
        syncs = {s.guru_id: s for s in self.db.scalars(select(GuruSync))}
        results: dict[str, SyncResult] = {}
        due: list[Guru] = []
        for guru in gurus:
            sync = syncs.get(guru.id)
            if guru.source == "13f" and not self.sec_configured:
                results[guru.id] = SyncResult(guru.id, False, _as_of(sync), SEC_UA_MISSING)
            elif not force and sync and now - sync.synced_at < _interval(guru, sync):
                # Within the TTL. Tickers left unmapped by earlier syncs still get mapped.
                self._resolve_pending(guru, sync)
                results[guru.id] = SyncResult(guru.id, False, sync.as_of, sync.error)
            else:
                due.append(guru)

        # Reserve each investor so two concurrent requests do not fetch the same source.
        reserved: list[Guru] = []
        with _lock:
            for guru in due:
                if guru.id in _in_flight:
                    sync = syncs.get(guru.id)
                    results[guru.id] = SyncResult(guru.id, False, _as_of(sync), _error(sync))
                else:
                    _in_flight.add(guru.id)
                    reserved.append(guru)
        try:
            fetched: dict[str, GuruSnapshot | Exception] = {}
            if reserved:
                with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(reserved))) as pool:
                    outcomes = list(pool.map(self._fetch, reserved))
                fetched = dict(zip((g.id for g in reserved), outcomes, strict=True))
            for guru in reserved:
                results[guru.id] = self._apply(guru, fetched[guru.id], syncs.get(guru.id))
        finally:
            with _lock:
                _in_flight.difference_update(g.id for g in reserved)
        return results

    def _fetch(self, guru: Guru) -> GuruSnapshot | Exception:
        try:
            return self.provider.fetch(guru)
        except Exception as exc:  # noqa: BLE001 - every failure becomes a recorded error
            return exc

    def _apply(
        self, guru: Guru, outcome: GuruSnapshot | Exception, previous: GuruSync | None
    ) -> SyncResult:
        now = self.now()
        if isinstance(outcome, Exception):
            message = _short(outcome)
            log.warning("guru sync %s failed: %s", guru.id, message)
            self._upsert_sync(
                guru, synced_at=now, as_of=_as_of(previous), error=message, note=_note(previous)
            )
            self.db.commit()
            return SyncResult(guru.id, True, _as_of(previous), message)

        holdings = outcome.holdings
        resolved: dict[str, tuple[str | None, str | None]] = {}
        if outcome.source == "13f":
            # Network (OpenFIGI) before any write; a resolver failure leaves tickers None
            # for the next sync rather than failing the snapshot.
            holdings, resolved = self._resolve(holdings, now)

        self.db.execute(delete(GuruHoldingRecord).where(GuruHoldingRecord.guru_id == guru.id))
        self.db.add_all(
            GuruHoldingRecord(
                guru_id=guru.id,
                as_of=outcome.as_of,
                symbol=h.symbol,
                cusip=h.cusip,
                name=h.name,
                shares=h.shares,
                value_usd=h.value_usd,
                weight=h.weight,
            )
            for h in holdings
        )
        self._write_cusips(resolved, now)
        self._upsert_sync(guru, synced_at=now, as_of=outcome.as_of, error=None, note=outcome.note)
        self.db.commit()
        return SyncResult(guru.id, True, outcome.as_of, None)

    # --- CUSIP -> ticker -----------------------------------------------------------------

    def _resolve(
        self, holdings: list[GuruHolding], now: datetime
    ) -> tuple[list[GuruHolding], dict[str, tuple[str | None, str | None]]]:
        cusips = [h.cusip for h in holdings if h.cusip and h.symbol is None]
        cached = {
            c.cusip: c
            for c in self.db.scalars(select(CusipTicker).where(CusipTicker.cusip.in_(cusips)))
        }
        pending = [
            c
            for c in cusips
            if c not in cached
            or (cached[c].symbol is None and now - cached[c].resolved_at > UNRESOLVED_RETRY)
        ]
        fresh = self._lookup(pending[: self.max_resolve_per_sync])
        out = []
        for h in holdings:
            if h.symbol is not None or not h.cusip:
                out.append(h)
                continue
            if h.cusip in fresh:
                symbol = fresh[h.cusip][0]
            elif h.cusip in cached:
                symbol = cached[h.cusip].symbol
            else:
                symbol = None
            out.append(
                GuruHolding(symbol, h.cusip, h.name, h.shares, h.value_usd, h.weight)
                if symbol != h.symbol
                else h
            )
        return out, fresh

    def _resolve_pending(self, guru: Guru, sync: GuruSync) -> None:
        """Map tickers an earlier sync left None, within this sync's OpenFIGI budget."""
        if guru.source != "13f" or self.resolver is None or sync.error:
            return
        rows = self.db.scalars(
            select(GuruHoldingRecord)
            .where(GuruHoldingRecord.guru_id == guru.id, GuruHoldingRecord.symbol.is_(None))
            .order_by(GuruHoldingRecord.value_usd.desc())
        ).all()
        if not rows:
            return
        now = self.now()
        holdings, resolved = self._resolve([_to_holding(r) for r in rows], now)
        changed = False
        for row, h in zip(rows, holdings, strict=True):
            if h.symbol is not None:
                row.symbol = h.symbol
                changed = True
        if changed or resolved:
            self._write_cusips(resolved, now)
            self.db.commit()

    def _lookup(self, cusips: list[str]) -> dict[str, tuple[str | None, str | None]]:
        if not cusips or self.resolver is None:
            return {}
        try:
            return self.resolver.map_cusips(cusips)
        except GuruDataError as exc:
            log.warning("CUSIP lookup failed, tickers stay unmapped until the next sync: %s", exc)
            return {}

    def _write_cusips(
        self, resolved: dict[str, tuple[str | None, str | None]], now: datetime
    ) -> None:
        for cusip, (symbol, name) in resolved.items():
            row = self.db.get(CusipTicker, cusip)
            if row is None:
                self.db.add(CusipTicker(cusip=cusip, symbol=symbol, name=name, resolved_at=now))
            else:
                row.symbol, row.name, row.resolved_at = symbol, name, now

    # --- helpers -------------------------------------------------------------------------

    def _guru(self, guru_id: str) -> Guru:
        guru = find_guru(guru_id)
        if guru is None:
            raise NotFoundError(f"Unknown investor {guru_id}")
        return guru

    def _holding_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for guru_id in self.db.scalars(select(GuruHoldingRecord.guru_id)):
            counts[guru_id] = counts.get(guru_id, 0) + 1
        return counts

    def _upsert_sync(
        self,
        guru: Guru,
        synced_at: datetime,
        as_of: date | None,
        error: str | None,
        note: str | None,
    ) -> None:
        row = self.db.get(GuruSync, guru.id)
        if row is None:
            row = GuruSync(guru_id=guru.id, source=guru.source)
            self.db.add(row)
        row.synced_at, row.as_of, row.error, row.note = synced_at, as_of, error, note


def _to_holding(r: GuruHoldingRecord) -> GuruHolding:
    return GuruHolding(r.symbol, r.cusip, r.name, r.shares, r.value_usd, r.weight)


def _interval(guru: Guru, sync: GuruSync) -> timedelta:
    return FAIL_RETRY if sync.error else SYNC_TTL[guru.source]


def _as_of(sync: GuruSync | None) -> date | None:
    return sync.as_of if sync else None


def _error(sync: GuruSync | None) -> str | None:
    return sync.error if sync else None


def _note(sync: GuruSync | None) -> str | None:
    return sync.note if sync else None


def _short(exc: Exception) -> str:
    text = str(exc) or exc.__class__.__name__
    return text if len(text) <= 300 else text[:297] + "..."
