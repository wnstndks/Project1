from datetime import date

from pydantic import BaseModel

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
    # Split: shares after the split. Dividend: estimated USD after 15% US withholding.
    effect: Num
