from datetime import date, datetime

from pydantic import BaseModel

from app.db.models import AssetType
from app.schemas.common import Num


class HoldingOut(BaseModel):
    symbol: str
    name: str
    asset_type: AssetType
    quantity: Num
    avg_cost: Num
    cost_basis: Num
    price: Num
    price_as_of: datetime
    market_value: Num
    unrealized_pnl: Num
    unrealized_pct: Num
    realized_pnl: Num
    weight: Num


class AllocationOut(BaseModel):
    asset_type: AssetType
    market_value: Num
    weight: Num


class SummaryOut(BaseModel):
    """All amounts in USD unless suffixed with _krw."""

    market_value: Num
    market_value_krw: Num
    cost_basis: Num
    unrealized_pnl: Num
    unrealized_pct: Num
    realized_pnl: Num
    total_pnl: Num
    usd_krw: Num
    allocation: list[AllocationOut]
    holdings_count: int


class HistoryPointOut(BaseModel):
    date: date
    market_value: float
    market_value_krw: float
    cost_basis: float
    cost_basis_krw: float
