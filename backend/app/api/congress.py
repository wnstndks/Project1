"""US House members' stock trades (STOCK Act disclosures) for my symbols.

Syncing downloads PDFs from the Clerk's site and takes tens of seconds, so like the investor
comparison it runs as a background task on its own session: the first `/trades` call and
`/sync` schedule it and return at once, and the screen polls while `syncing` is true.
"""

import logging
from collections.abc import Callable
from dataclasses import asdict
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.data.congress_provider import CongressProvider
from app.deps import (
    get_congress_max_batches,
    get_congress_provider,
    get_congress_service,
    get_session_factory,
)
from app.schemas.congress import (
    CongressStatusOut,
    CongressSyncOut,
    CongressTradeOut,
    CongressTradesOut,
)
from app.services.congress import CongressService, CongressStatus, Trade

log = logging.getLogger(__name__)

router = APIRouter(prefix="/congress", tags=["congress"])


def run_sync(session_factory: Callable, provider: CongressProvider, max_batches: int) -> None:
    """Background job: fetch what is due, batch after batch, on its own session."""
    try:
        with session_factory() as db:
            CongressService(db, provider, max_batches=max_batches).sync()
    except Exception:  # noqa: BLE001 - a background job has no response to fail
        log.exception("congress sync failed")


def get_sync_job(
    session_factory=Depends(get_session_factory),
    provider: CongressProvider = Depends(get_congress_provider),
    max_batches: int = Depends(get_congress_max_batches),
) -> Callable[[], None]:
    return lambda: run_sync(session_factory, provider, max_batches)


def _status_out(s: CongressStatus) -> CongressStatusOut:
    return CongressStatusOut(
        source=s.source,
        synced_at=s.synced_at,
        index_modified=s.index_modified,
        stale=s.stale,
        syncing=s.syncing,
        error=s.error,
        docs_total=s.docs_total,
        docs_parsed=s.docs_parsed,
        docs_no_text=s.docs_no_text,
        docs_failed=s.docs_failed,
        docs_pending=s.docs_pending,
        trades=s.trades,
    )


def _trade_out(t: Trade) -> CongressTradeOut:
    return CongressTradeOut(**asdict(t))


def _symbols(raw: str) -> list[str]:
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


@router.get("/trades", response_model=CongressTradesOut)
def trades(
    background: BackgroundTasks,
    symbols: str = Query("", description="Comma-separated tickers, e.g. my holdings"),
    days: int = Query(180, ge=1, le=730, description="Transactions in the last N days"),
    service: CongressService = Depends(get_congress_service),
    sync_job: Callable[[], None] = Depends(get_sync_job),
):
    current = service.status()
    scheduled = service.due()
    if scheduled:
        # Nothing stored yet, the daily TTL passed, or a backlog is pending: fetch in the
        # background; the screen polls while `syncing`.
        background.add_task(sync_job)
    syncing = current.syncing or scheduled
    since = service.now().date() - timedelta(days=days)
    rows = service.trades(_symbols(symbols), since=since)
    return CongressTradesOut(
        syncing=syncing, status=_status_out(current), trades=[_trade_out(t) for t in rows]
    )


@router.get("/status", response_model=CongressStatusOut)
def status_(service: CongressService = Depends(get_congress_service)):
    return _status_out(service.status())


@router.post("/sync", response_model=CongressSyncOut, status_code=status.HTTP_202_ACCEPTED)
def sync(
    background: BackgroundTasks,
    service: CongressService = Depends(get_congress_service),
    sync_job: Callable[[], None] = Depends(get_sync_job),
):
    """Manual "fetch now". Schedules a run only when one would do something (TTL passed or
    documents pending) and none is running; `syncing` says whether that happened."""
    current = service.status()
    scheduled = service.due()
    if scheduled:
        background.add_task(sync_job)
    return CongressSyncOut(syncing=current.syncing or scheduled, status=_status_out(current))
