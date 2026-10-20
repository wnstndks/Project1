import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Enum, Float, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, DecimalText


class AssetType(enum.StrEnum):
    STOCK = "stock"
    CRYPTO = "crypto"


class Currency(enum.StrEnum):
    USD = "USD"
    KRW = "KRW"


class ActionKind(enum.StrEnum):
    SPLIT = "split"
    DIVIDEND = "dividend"


class ActionStatus(enum.StrEnum):
    DETECTED = "detected"
    CONFIRMED = "confirmed"
    IGNORED = "ignored"


class Side(enum.StrEnum):
    BUY = "buy"
    SELL = "sell"


def _str_enum(enum_cls: type[enum.StrEnum], length: int) -> Enum:
    # Persist the lowercase value ("buy"), not the member name ("BUY").
    return Enum(
        enum_cls, native_enum=False, length=length, values_callable=lambda e: [m.value for m in e]
    )


class Transaction(Base):
    """A buy or sell of a stock or coin. Price and fee are in `currency`.

    Stocks trade in USD. Coins bought on a Korean exchange (Upbit, Bithumb) trade in KRW.

    Holdings are never stored; they are derived from this ledger.
    """

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_type: Mapped[AssetType] = mapped_column(_str_enum(AssetType, 10))
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    side: Mapped[Side] = mapped_column(_str_enum(Side, 4))
    trade_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[Currency] = mapped_column(
        _str_enum(Currency, 3), default=Currency.USD, server_default="USD"
    )
    quantity: Mapped[Decimal] = mapped_column(DecimalText)
    price: Mapped[Decimal] = mapped_column(DecimalText)
    fee: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    # Actual USD/KRW rate paid, when known (e.g. read from a broker screenshot).
    # Overrides the market rate on the trade date for KRW cost basis.
    fx_rate: Mapped[Decimal | None] = mapped_column(DecimalText)
    # Order among trades on the same date (lower first). Ties fall back to entry order.
    seq: Mapped[int] = mapped_column(default=0, server_default="0")
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
    # Split- and dividend-adjusted close; use for return calculations and ML.
    adj_close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)


class CorporateAction(Base):
    """A split or cash dividend on a held stock. Only confirmed ones change the ledger."""

    __tablename__ = "corporate_actions"
    __table_args__ = (
        Index("ix_corporate_actions_symbol_date_kind", "symbol", "ex_date", "kind", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    ex_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[ActionKind] = mapped_column(_str_enum(ActionKind, 10))
    # Split: new shares per old share (10 for a 10:1 split). Dividend: USD per share.
    value: Mapped[Decimal] = mapped_column(DecimalText)
    status: Mapped[ActionStatus] = mapped_column(_str_enum(ActionStatus, 10))
    detected_at: Mapped[datetime] = mapped_column(DateTime)
    # Dividends only: tax withheld at source. 15% for US companies under the Korea-US
    # treaty; foreign ADRs and partnerships differ, so the user can change it per symbol.
    withholding: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0.15"))


class ForecastLog(Base):
    """Every live forecast as first served, scored later against what happened.

    Only the first forecast per (symbol, horizon, as_of) is kept, so a later retrain cannot
    quietly replace a forecast that turned out wrong. Returns are log returns.
    """

    __tablename__ = "forecast_log"
    __table_args__ = (Index("ix_forecast_log_key", "symbol", "horizon", "as_of", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    horizon: Mapped[str] = mapped_column(String(4))
    as_of: Mapped[date] = mapped_column(Date)
    target_date: Mapped[date] = mapped_column(Date)
    run_id: Mapped[str] = mapped_column(String(40))
    base_price: Mapped[float] = mapped_column(Float)
    q10: Mapped[float] = mapped_column(Float)
    q50: Mapped[float] = mapped_column(Float)
    q90: Mapped[float] = mapped_column(Float)
    p_up: Mapped[float] = mapped_column(Float)
    baseline_p_up: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class NewsArticle(Base):
    """A headline with its FinBERT sentiment. published_at is UTC (stored naive)."""

    __tablename__ = "news_articles"
    __table_args__ = (Index("ix_news_articles_symbol_url", "symbol", "url", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    source: Mapped[str] = mapped_column(String(100))
    headline: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(1000))
    positive: Mapped[float] = mapped_column(Float)
    negative: Mapped[float] = mapped_column(Float)
    neutral: Mapped[float] = mapped_column(Float)


class GdeltDaily(Base):
    """GDELT daily news tone and article volume for a symbol's query (UTC calendar days)."""

    __tablename__ = "gdelt_daily"
    __table_args__ = (Index("ix_gdelt_daily_symbol_date", "symbol", "date", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    date: Mapped[date] = mapped_column(Date)
    tone: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[int | None] = mapped_column()
    volume_norm: Mapped[int | None] = mapped_column()
    # The query that produced the row; rows from an older query are purged when it changes.
    query: Mapped[str | None] = mapped_column(String(200))
    # When the value was first fetched. GDELT revises recent days, so a backtest can tell
    # what was known at the time from the settled value.
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime)


class NewsCoverage(Base):
    """A date range a headline source was successfully collected for (inclusive)."""

    __tablename__ = "news_coverage"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    source: Mapped[str] = mapped_column(String(20))
    start: Mapped[date] = mapped_column(Date)
    end: Mapped[date] = mapped_column(Date)


class NewsSync(Base):
    """What news range has been fetched per symbol, so syncs are incremental."""

    __tablename__ = "news_syncs"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(200))
    query: Mapped[str] = mapped_column(String(200))
    gdelt_from: Mapped[date | None] = mapped_column(Date)
    gdelt_synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    finnhub_from: Mapped[date | None] = mapped_column(Date)
    finnhub_synced_at: Mapped[datetime | None] = mapped_column(DateTime)


class SymbolSync(Base):
    """Tracks which date range of a symbol has been fetched, so the cache is filled only once."""

    __tablename__ = "symbol_syncs"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    fetched_from: Mapped[date] = mapped_column(Date)
    synced_at: Mapped[datetime] = mapped_column(DateTime)
