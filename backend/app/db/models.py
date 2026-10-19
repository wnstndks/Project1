import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, Float, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, DecimalText


class AssetType(enum.StrEnum):
    STOCK = "stock"
    CRYPTO = "crypto"


class Side(enum.StrEnum):
    BUY = "buy"
    SELL = "sell"


def _str_enum(enum_cls: type[enum.StrEnum], length: int) -> Enum:
    # Persist the lowercase value ("buy"), not the member name ("BUY").
    return Enum(
        enum_cls, native_enum=False, length=length, values_callable=lambda e: [m.value for m in e]
    )


class Transaction(Base):
    """A buy or sell of a stock or coin. Prices and fees are in USD.

    Holdings are never stored; they are derived from this ledger.
    """

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_type: Mapped[AssetType] = mapped_column(_str_enum(AssetType, 10))
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    side: Mapped[Side] = mapped_column(_str_enum(Side, 4))
    trade_date: Mapped[date] = mapped_column(Date)
    quantity: Mapped[Decimal] = mapped_column(DecimalText)
    price: Mapped[Decimal] = mapped_column(DecimalText)
    fee: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    note: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PriceBar(Base):
    """Cached daily OHLCV bar from the market data provider.

    Also stores FX history (e.g. symbol "KRW=X" for USD/KRW).
    Market data is kept as float; only ledger values need exact decimals.
    """

    __tablename__ = "price_bars"
    __table_args__ = (Index("ix_price_bars_symbol_date", "symbol", "date", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    date: Mapped[date] = mapped_column(Date)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
