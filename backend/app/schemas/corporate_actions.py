from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.db.models import ActionKind, ActionStatus
from app.schemas.common import Num


class CorporateActionOut(BaseModel):
    id: int
    symbol: str
    ex_date: date
    kind: ActionKind
    value: Num
    status: ActionStatus
    shares_before: Num
    # Split: shares after the split. Dividend: estimated USD after withholding.
    effect: Num
    # Dividends: tax withheld at source (0.15 for US companies).
    withholding: Num


class WithholdingIn(BaseModel):
    symbol: str
    rate: Decimal = Field(ge=0, lt=1)
