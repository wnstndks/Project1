from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import AssetType, Side
from app.schemas.common import Num


class TransactionIn(BaseModel):
    asset_type: AssetType
    symbol: str = Field(min_length=1, max_length=20, examples=["AAPL", "BTC"])
    side: Side
    trade_date: date
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=8)
    price: Decimal = Field(gt=0, max_digits=20, decimal_places=8, description="USD per unit")
    fee: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=8)
    note: str | None = Field(default=None, max_length=200)


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_type: AssetType
    symbol: str
    side: Side
    trade_date: date
    quantity: Num
    price: Num
    fee: Num
    note: str | None
    created_at: datetime
