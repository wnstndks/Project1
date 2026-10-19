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
    upbit_as_of: datetime
    global_as_of: datetime
    fx_as_of: datetime
    # The FX leg is old (weekends, holidays): the premium may be off by about as much as
    # the premium itself.
    fx_stale: bool


class AssetInfo(BaseModel):
    symbol: str
    name: str
    asset_type: AssetType
