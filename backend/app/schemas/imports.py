from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.db.models import AssetType, Currency
from app.schemas.common import Num


class ImportStatusOut(BaseModel):
    configured: bool
    engine: str  # "ollama" | "claude" | "fake"
    model: str
    problem: str | None


class PreviewRowOut(BaseModel):
    name: str
    symbol: str | None
    asset_type: AssetType
    quantity: Num | None
    currency: Currency
    avg_price: Num | None
    cost_krw: Num | None
    implied_fx: Num | None
    price_estimated: bool
    ticker_guessed: bool
    confidence: str
    status: str
    message: str | None
    current_quantity: Num | None
    diff: str | None
    delta_quantity: Num | None
    delta_price: Num | None


class PreviewOut(BaseModel):
    broker: str | None
    rows: list[PreviewRowOut]


class CommitRowIn(BaseModel):
    asset_type: AssetType
    symbol: str = Field(min_length=1, max_length=20)
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=8)
    currency: Currency = Currency.USD
    price: Decimal = Field(gt=0, max_digits=20, decimal_places=8, description="In currency")
    fx_rate: Decimal | None = Field(None, gt=0, max_digits=20, decimal_places=6)


class CommitIn(BaseModel):
    trade_date: date
    rows: list[CommitRowIn] = Field(min_length=1, max_length=100)


class CommitOut(BaseModel):
    created: int
