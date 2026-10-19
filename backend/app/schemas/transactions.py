from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import AssetType, Currency, Side
from app.schemas.common import Num


class TransactionIn(BaseModel):
    asset_type: AssetType
    symbol: str = Field(min_length=1, max_length=20, examples=["AAPL", "BTC"])
    side: Side
    trade_date: date
    currency: Currency = Field(
        Currency.USD, description="USD for stocks; KRW for coins bought on Upbit/Bithumb"
    )
    quantity: Decimal = Field(gt=0, max_digits=20, decimal_places=8)
    price: Decimal = Field(
        gt=0, max_digits=20, decimal_places=8, description="Per unit, in currency"
    )
    fee: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=8)
    fx_rate: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=20,
        decimal_places=6,
        description="USD/KRW actually paid; defaults to the market rate on trade_date",
    )
    seq: int = Field(default=0, ge=0, le=1000, description="Order among same-day trades")
    note: str | None = Field(default=None, max_length=200)


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_type: AssetType
    symbol: str
    side: Side
    trade_date: date
    currency: Currency
    quantity: Num
    price: Num
    fee: Num
    fx_rate: Num | None
    seq: int
    note: str | None
    created_at: datetime
    usd_krw: Num | None = Field(None, description="USD/KRW rate on the trade date")


class ConvertCurrencyIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    currency: Currency
