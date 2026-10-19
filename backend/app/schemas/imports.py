from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.db.models import AssetType
from app.schemas.common import Num


class ImportStatusOut(BaseModel):
    configured: bool
    model: str


class PreviewRowOut(BaseModel):
    name: str
    symbol: str | None
    asset_type: AssetType
    quantity: Num | None
    avg_price_usd: Num | None
    cost_krw: Num | None
    implied_fx: Num | None
    price_estimated: bool
    confidence: str
    status: str
    message: str | None
    current_quantity: Num | None
    diff: str | None


class PreviewOut(BaseModel):
    broker: str | None
    rows: list[PreviewRowOut]


class CommitRowIn(BaseModel):
    asset_type: AssetType
    symbol: str = Field(min_length=1, max_length=20)
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=8)
    avg_price_usd: Decimal = Field(gt=0, max_digits=20, decimal_places=8)
    fx_rate: Decimal | None = Field(None, gt=0, max_digits=20, decimal_places=6)


class CommitIn(BaseModel):
    trade_date: date
    rows: list[CommitRowIn] = Field(min_length=1, max_length=100)


class CommitOut(BaseModel):
    created: int
