from dataclasses import asdict

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from app.db.models import ActionStatus
from app.deps import get_corporate_action_service
from app.schemas.corporate_actions import CorporateActionOut
from app.services.corporate_actions import CorporateActionService

router = APIRouter(prefix="/corporate-actions", tags=["corporate-actions"])


@router.get("", response_model=list[CorporateActionOut])
async def list_actions(
    service: CorporateActionService = Depends(get_corporate_action_service),
):
    # Detection calls the market data provider (one request per held stock, cached 6 h).
    await run_in_threadpool(service.detect)
    return [asdict(a) for a in service.list_all()]


@router.post("/dividends/confirm-all", response_model=list[CorporateActionOut])
def confirm_all_dividends(
    service: CorporateActionService = Depends(get_corporate_action_service),
):
    service.confirm_all_dividends()
    return [asdict(a) for a in service.list_all()]


@router.post("/{action_id}/confirm", response_model=list[CorporateActionOut])
def confirm(
    action_id: int, service: CorporateActionService = Depends(get_corporate_action_service)
):
    service.set_status(action_id, ActionStatus.CONFIRMED)
    return [asdict(a) for a in service.list_all()]


@router.post("/{action_id}/ignore", response_model=list[CorporateActionOut])
def ignore(action_id: int, service: CorporateActionService = Depends(get_corporate_action_service)):
    service.set_status(action_id, ActionStatus.IGNORED)
    return [asdict(a) for a in service.list_all()]
