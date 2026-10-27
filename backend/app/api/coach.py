"""The portfolio coach (DECISIONS.md D-033): the user's own policy and the checks built on it.

Not a forecast, not a stock pick and not advice; nothing here places an order. The policy
routes are cheap; the others load years of bars and the rule checks, so they run off the
event loop.
"""

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool

from app.deps import get_coach_service
from app.schemas.coach import (
    DiagnosisOut,
    PatternsOut,
    PolicyIn,
    PolicyOut,
    RebalanceOut,
    ReviewOut,
)
from app.services.coach import CoachService

router = APIRouter(prefix="/coach", tags=["coach"])


@router.get("/policy", response_model=PolicyOut)
def get_policy(service: CoachService = Depends(get_coach_service)):
    return service.policy_payload()


@router.put("/policy", response_model=PolicyOut)
def put_policy(body: PolicyIn, service: CoachService = Depends(get_coach_service)):
    return service.update_policy(
        body.policy.model_dump(), body.cash.model_dump() if body.cash is not None else None
    )


@router.get("/diagnosis", response_model=DiagnosisOut)
async def get_diagnosis(service: CoachService = Depends(get_coach_service)):
    return await run_in_threadpool(service.diagnosis)


@router.get("/rebalance", response_model=RebalanceOut)
async def get_rebalance(service: CoachService = Depends(get_coach_service)):
    return await run_in_threadpool(service.rebalance)


@router.get("/patterns", response_model=PatternsOut)
async def get_patterns(service: CoachService = Depends(get_coach_service)):
    return await run_in_threadpool(service.patterns)


@router.get("/review", response_model=ReviewOut)
async def get_review(
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$", description="YYYY-MM"),
    service: CoachService = Depends(get_coach_service),
):
    return await run_in_threadpool(service.review, month)
