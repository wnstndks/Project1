from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import AssetType


class BarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    volume: float


class QuoteOut(BaseModel):
    symbol: str
    price: float
    as_of: datetime


class KimchiPremiumOut(BaseModel):
    symbol: str
    upbit_krw: float
    global_usd: float
    usd_krw: float
    global_krw: float
    premium_pct: float


class AssetInfo(BaseModel):
    symbol: str
    name: str
    asset_type: AssetType
