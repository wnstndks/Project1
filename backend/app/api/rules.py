"""Buy-more / stop-loss rule checks and settings (plan G, DECISIONS.md D-027).

These are the user's own rules checked against their holdings, not trading signals, and
nothing here places an order.
"""

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from app.deps import get_rule_service
from app.schemas.rules import (
    KillSwitchOut,
    KillSwitchResetIn,
    RuleCheckAllOut,
    RuleSettingsIn,
    RuleSettingsOut,
)
from app.services.rules import RuleService, kill_switch_payload

router = APIRouter(prefix="/rules", tags=["rules"])


# Loads a year of bars per holding and may run forecast inference: off the event loop.
@router.get("/check", response_model=RuleCheckAllOut)
async def check_rules(service: RuleService = Depends(get_rule_service)):
    return await run_in_threadpool(service.check_all)


@router.get("/settings", response_model=RuleSettingsOut)
def get_rule_settings(service: RuleService = Depends(get_rule_service)):
    return service.settings_payload()


@router.put("/settings", response_model=RuleSettingsOut)
def put_rule_settings(body: RuleSettingsIn, service: RuleService = Depends(get_rule_service)):
    return service.update_settings(
        body.global_.model_dump(),
        body.crypto.model_dump() if body.crypto is not None else None,
        {symbol: rule.model_dump() for symbol, rule in body.targets.items()},
    )


# The user resets the kill switch from the app; the actor is fixed server-side (D-033 §7).
# Answers the current state even when the switch was not tripped.
@router.post("/kill-switch/reset", response_model=KillSwitchOut)
def reset_kill_switch(
    body: KillSwitchResetIn | None = None, service: RuleService = Depends(get_rule_service)
):
    detail = body.detail if body is not None else ""
    return kill_switch_payload(service.reset_kill_switch(detail))
