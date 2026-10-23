"""Well-known investors: list, holdings, overlap with mine, background sync.

Syncing (ARK CSVs, EDGAR, OpenFIGI) takes tens of seconds, so it never runs inside a
request: `/sync` and a first `/compare` schedule `sync_all` as a background task on a fresh
session and return at once. The service's in-flight set keeps two requests from fetching the
same investor twice.
"""

import logging
from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.data.guru_provider import CusipResolver, GuruProvider
from app.deps import (
    get_cusip_resolver,
    get_guru_compare_service,
    get_guru_provider,
    get_guru_service,
    get_sec_configured,
    get_session_factory,
)
from app.schemas.gurus import (
    CompareOut,
    GuruCompareOut,
    GuruHoldingOut,
    GuruHoldingsOut,
    GuruOut,
    MissingOut,
    OverlapOut,
    SyncOut,
)
from app.services.guru_compare import GuruCompareService, GuruComparison, needs_sync
from app.services.gurus import GuruService, GuruStatus

log = logging.getLogger(__name__)

router = APIRouter(prefix="/gurus", tags=["gurus"])


def run_sync_all(
    session_factory: Callable,
    provider: GuruProvider,
    resolver: CusipResolver | None,
    sec_configured: bool,
) -> None:
    """Background job: sync every investor that is due, on its own session."""
    try:
        with session_factory() as db:
            GuruService(db, provider, resolver, sec_configured=sec_configured).sync_all()
    except Exception:  # noqa: BLE001 - a background job has no response to fail
        log.exception("guru sync_all failed")


def get_sync_job(
    session_factory=Depends(get_session_factory),
    provider: GuruProvider = Depends(get_guru_provider),
    resolver: CusipResolver | None = Depends(get_cusip_resolver),
    sec_configured: bool = Depends(get_sec_configured),
) -> Callable[[], None]:
    return lambda: run_sync_all(session_factory, provider, resolver, sec_configured)


def _guru_out(s: GuruStatus) -> GuruOut:
    return GuruOut(
        id=s.guru.id,
        name_ko=s.guru.name_ko,
        name_en=s.guru.name_en,
        source=s.guru.source,
        note=s.guru.note,
        synced_at=s.synced_at,
        as_of=s.as_of,
        stale=s.stale,
        error=s.error,
        sync_note=s.note,
        holdings_count=s.holdings_count,
    )


def _compare_out(c: GuruComparison) -> GuruCompareOut:
    return GuruCompareOut(
        guru=_guru_out(c.status),
        overlaps=[
            OverlapOut(
                symbol=o.symbol,
                name=o.name,
                my_weight_pct=o.my_weight_pct,
                guru_weight_pct=o.guru_weight_pct,
            )
            for o in c.overlaps
        ],
        top_missing=[
            MissingOut(symbol=m.symbol, name=m.name, weight_pct=m.weight_pct) for m in c.top_missing
        ],
    )


@router.get("", response_model=list[GuruOut])
def list_gurus(service: GuruService = Depends(get_guru_service)):
    return [_guru_out(s) for s in service.list_all()]


@router.get("/compare", response_model=CompareOut)
def compare(
    background: BackgroundTasks,
    service: GuruCompareService = Depends(get_guru_compare_service),
    sync_job: Callable[[], None] = Depends(get_sync_job),
):
    statuses = service.statuses()
    syncing = needs_sync(statuses)
    if syncing:
        # First visit: nothing stored yet. Fetch in the background; the screen polls.
        background.add_task(sync_job)
    return CompareOut(syncing=syncing, gurus=[_compare_out(c) for c in service.compare(statuses)])


@router.post("/sync", response_model=SyncOut, status_code=status.HTTP_202_ACCEPTED)
def sync(
    background: BackgroundTasks,
    service: GuruService = Depends(get_guru_service),
    sync_job: Callable[[], None] = Depends(get_sync_job),
):
    background.add_task(sync_job)
    return SyncOut(syncing=True, gurus=[_guru_out(s) for s in service.list_all()])


@router.get("/{guru_id}/holdings", response_model=GuruHoldingsOut)
def holdings(
    guru_id: str,
    top: int = Query(20, ge=1, le=500),
    service: GuruService = Depends(get_guru_service),
):
    rows = service.holdings(guru_id)  # 404 for an unknown id
    status_ = next(s for s in service.list_all() if s.guru.id == guru_id)
    return GuruHoldingsOut(
        guru=_guru_out(status_),
        holdings=[
            GuruHoldingOut(
                symbol=h.symbol,
                cusip=h.cusip,
                name=h.name,
                shares=h.shares,
                value_usd=h.value_usd,
                weight_pct=round(h.weight * 100, 2),
            )
            for h in rows[:top]
        ],
        total=len(rows),
    )
