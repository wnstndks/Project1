from datetime import date, datetime

from pydantic import BaseModel

from app.db.models import AssetType, Currency
from app.schemas.common import Num


class HoldingOut(BaseModel):
    """USD fields plus *_krw fields: KRW cost uses each trade date's FX rate, KRW value today's."""

    symbol: str
    name: str
    asset_type: AssetType
    currency: Currency
    quantity: Num
    avg_cost: Num
    cost_basis: Num
    price: Num
    price_as_of: datetime
    # Close before the quote's session, in the pricing currency (USD; Upbit won for KRW coins).
    prev_close: Num
    # Today's move: quantity x (price - prev_close). USD, percent, and KRW at today's rate.
    day_change: Num
    day_change_pct: Num
    day_change_krw: Num
    market_value: Num
    unrealized_pnl: Num
    unrealized_pct: Num
    realized_pnl: Num
    dividends: Num
    avg_cost_krw: Num
    cost_basis_krw: Num
    price_krw: Num
    market_value_krw: Num
    unrealized_pnl_krw: Num
    unrealized_pct_krw: Num
    realized_pnl_krw: Num
    weight: Num


class AllocationOut(BaseModel):
    asset_type: AssetType
    market_value: Num
    market_value_krw: Num
    weight: Num


class SummaryOut(BaseModel):
    """Amounts in USD unless suffixed with _krw."""

    market_value: Num
    market_value_krw: Num
    # Sum of today's moves; pct against the value at the previous closes.
    day_change: Num
    day_change_krw: Num
    day_change_pct: Num
    cost_basis: Num
    unrealized_pnl: Num
    unrealized_pct: Num
    realized_pnl: Num
    dividends: Num
    dividends_krw: Num
    total_pnl: Num
    cost_basis_krw: Num
    unrealized_pnl_krw: Num
    unrealized_pct_krw: Num
    realized_pnl_krw: Num
    total_pnl_krw: Num
    fx_pnl_krw: Num
    usd_krw: Num
    allocation: list[AllocationOut]
    holdings_count: int


class HistoryPointOut(BaseModel):
    date: date
    market_value: float
    market_value_krw: float
    cost_basis: float
    cost_basis_krw: float


class SparklineOut(BaseModel):
    symbol: str
    # Closes oldest first, in the pricing currency (USD; Upbit won for KRW coins).
    closes: list[float]


class BenchmarkPointOut(BaseModel):
    date: date
    # The benchmark bought with my won flows, valued in USD and in KRW at that day's rate.
    value: float
    value_krw: float


class BenchmarkSeriesOut(BaseModel):
    symbol: str
    name_ko: str
    points: list[BenchmarkPointOut]


class BenchmarkOut(BaseModel):
    """My value history and benchmarks fed with the same cash flows, on the same daily grid."""

    mine: list[HistoryPointOut]
    benchmarks: list[BenchmarkSeriesOut]
