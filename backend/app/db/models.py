import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
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


class KillSwitchEvent(Base):
    """Append-only log of the kill switch; the latest row is the current state.

    `action` is "trip" or "reset", `actor` is "system" or "user". Only the user resets.
    `detail` holds ratios only, never amounts, keys or account details.
    """

    __tablename__ = "kill_switch_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime)
    action: Mapped[str] = mapped_column(String(5))
    reason_code: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str] = mapped_column(String(200), default="")
    actor: Mapped[str] = mapped_column(String(6))


class PaperSignal(Base):
    """One strategy signal and what the paper account did with it, scored later.

    Paper trading never writes to `transactions`, so real holdings stay untouched. Only the
    first signal per (strategy, symbol, as_of) is kept. Prices are in the asset's currency
    (USD), amounts in KRW at the day's USD/KRW (DECISIONS.md D-014). Fills happen at the
    next bar's open, never on the signal's own bar.
    """

    __tablename__ = "paper_signals"
    __table_args__ = (Index("ix_paper_signals_key", "strategy_id", "symbol", "as_of", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    strategy_id: Mapped[str] = mapped_column(String(40))
    symbol: Mapped[str] = mapped_column(String(20))
    asset_class: Mapped[str] = mapped_column(String(6))
    as_of: Mapped[date] = mapped_column(Date)
    horizon: Mapped[str] = mapped_column(String(4))
    # buy | sell | hold | no_edge
    action: Mapped[str] = mapped_column(String(8))
    # The strategy's own state after this signal (S1: buy -> held, sell/no_edge -> not held,
    # hold -> unchanged); the next decision day reads it. Not the paper account's position.
    held_after: Mapped[bool] = mapped_column(Boolean)
    # high | medium | low (display only, never used by the trading rule)
    confidence: Mapped[str | None] = mapped_column(String(8))
    rationale: Mapped[dict] = mapped_column(JSON)
    # Close of the signal's bar and USD/KRW that day.
    ref_price: Mapped[float | None] = mapped_column(Float)
    ref_fx: Mapped[float | None] = mapped_column(Float)
    target_weight: Mapped[float | None] = mapped_column(Float)
    # Risk check: none (no order needed) | accepted | clipped | rejected | failed | halted
    risk_status: Mapped[str] = mapped_column(String(8))
    risk_reason: Mapped[str | None] = mapped_column(String(200))
    side: Mapped[str | None] = mapped_column(String(4))
    # Approved order size at signal time. A buy spends at most this at the fill; a sell's
    # quantity is fixed at signal time and never exceeds what the paper account holds.
    notional_krw: Mapped[Decimal | None] = mapped_column(DecimalText)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    # none | pending | filled | expired
    fill_status: Mapped[str] = mapped_column(String(8))
    fill_date: Mapped[date | None] = mapped_column(Date)
    # Why a fill was cut or skipped: cash (not enough after the open gapped) | nothing_held |
    # no_bar (next bar never arrived) | kill_switch (tripped between approval and fill)
    fill_note: Mapped[str | None] = mapped_column(String(20))
    quantity: Mapped[Decimal | None] = mapped_column(DecimalText)
    # Next bar's open with slippage, in `currency`.
    fill_price: Mapped[Decimal | None] = mapped_column(DecimalText)
    fill_fx: Mapped[Decimal | None] = mapped_column(DecimalText)
    fee_krw: Mapped[Decimal | None] = mapped_column(DecimalText)
    slippage_bps: Mapped[float | None] = mapped_column(Float)
    # Scoring once the horizon has passed: total return (dividends net of withholding) from
    # the close on as_of to the close on target_date, and the class benchmark's over the same
    # dates (SPY for stocks, BTC for coins).
    target_date: Mapped[date | None] = mapped_column(Date)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime)
    exit_price: Mapped[float | None] = mapped_column(Float)
    signal_return: Mapped[float | None] = mapped_column(Float)
    benchmark_return: Mapped[float | None] = mapped_column(Float)
    # Filled orders only: value change of the bought or sold quantity to target_date, in KRW,
    # after the fee.
    trade_pnl_krw: Mapped[Decimal | None] = mapped_column(DecimalText)


class GuruHoldingRecord(Base):
    """One position of a well-known investor's latest public snapshot (ARK CSV or 13F).

    Only the latest snapshot per investor is kept; `weight` is the share of the snapshot's
    total value. `symbol` is None for cash, private placements and CUSIPs not yet mapped.
    """

    __tablename__ = "guru_holdings"
    __table_args__ = (Index("ix_guru_holdings_guru_as_of", "guru_id", "as_of"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guru_id: Mapped[str] = mapped_column(String(40))
    as_of: Mapped[date] = mapped_column(Date)
    symbol: Mapped[str | None] = mapped_column(String(20))
    cusip: Mapped[str | None] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(String(200))
    shares: Mapped[float] = mapped_column(Float)
    value_usd: Mapped[float] = mapped_column(Float)
    weight: Mapped[float] = mapped_column(Float)


class GuruSync(Base):
    """Last sync attempt per investor. `error` is set when the attempt failed and the stored
    holdings (if any) are from an earlier success; `note` carries non-fatal caveats."""

    __tablename__ = "guru_syncs"

    guru_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime)  # UTC
    as_of: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(4))
    error: Mapped[str | None] = mapped_column(String(300))
    note: Mapped[str | None] = mapped_column(String(300))


class CusipTicker(Base):
    """Permanent CUSIP -> ticker cache from OpenFIGI. `symbol` None means the lookup found no
    US listing; those are retried after a while, successes never expire."""

    __tablename__ = "cusip_tickers"

    cusip: Mapped[str] = mapped_column(String(12), primary_key=True)
    symbol: Mapped[str | None] = mapped_column(String(20))
    name: Mapped[str | None] = mapped_column(String(200))
    resolved_at: Mapped[datetime] = mapped_column(DateTime)  # UTC


class RuleSettingsRow(Base):
    """The user's buy-more / stop-loss rules (app/strategy/rules.py, DECISIONS.md D-027).

    One row (id 1). `global_json` holds the `RuleSettings` fields except `targets`;
    `targets_json` maps a symbol to its `SymbolRule` overrides (None values left out).
    Without a row the `AM_RULES_*` defaults apply.
    """

    __tablename__ = "rule_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    global_json: Mapped[dict] = mapped_column(JSON)
    targets_json: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime)  # UTC


class CongressTrade(Base):
    """One transaction from a US House member's periodic transaction report (STOCK Act),
    as parsed from the Clerk's PDF (services/congress.py, DECISIONS.md D-030).

    `symbol` is None for assets without a ticker (funds, bonds); `amount_high` is None for
    "Over $X"; `party` is not in the Clerk's data and stays None until another source adds it.
    """

    __tablename__ = "congress_trades"
    __table_args__ = (
        UniqueConstraint("source", "doc_id", "row_no"),
        Index("ix_congress_trades_symbol_date", "symbol", "transaction_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(8))  # "house"
    year: Mapped[int] = mapped_column(Integer)  # index year, part of the document URL
    doc_id: Mapped[str] = mapped_column(String(16))
    row_no: Mapped[int] = mapped_column(Integer)
    member: Mapped[str] = mapped_column(String(120))
    chamber: Mapped[str] = mapped_column(String(6))
    state: Mapped[str] = mapped_column(String(2))
    district: Mapped[str] = mapped_column(String(6))  # "MD06"
    party: Mapped[str | None] = mapped_column(String(1))
    owner: Mapped[str] = mapped_column(String(4))  # SELF | SP | DC | JT
    asset_name: Mapped[str] = mapped_column(String(300))
    asset_type: Mapped[str | None] = mapped_column(String(4))  # Clerk code, e.g. ST
    symbol: Mapped[str | None] = mapped_column(String(20))
    side: Mapped[str] = mapped_column(String(12))  # buy | sell | sell_partial | exchange
    transaction_date: Mapped[date] = mapped_column(Date)
    notification_date: Mapped[date | None] = mapped_column(Date)
    filing_date: Mapped[date] = mapped_column(Date)
    amount_low: Mapped[int] = mapped_column(Integer)  # USD
    amount_high: Mapped[int | None] = mapped_column(Integer)
    amount_label: Mapped[str] = mapped_column(String(40))  # "$1,001 - $15,000"
    cap_gains_over_200: Mapped[bool | None] = mapped_column(Boolean)
    fetched_at: Mapped[datetime] = mapped_column(DateTime)  # UTC


class CongressDoc(Base):
    """Processing state of one House filing: parsed, scanned without a text layer
    (`no_text`, never retried) or failed (retried on a later sync)."""

    __tablename__ = "congress_docs"

    source: Mapped[str] = mapped_column(String(8), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    year: Mapped[int] = mapped_column(Integer)
    member: Mapped[str] = mapped_column(String(120))
    filing_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(10))  # parsed | no_text | failed
    rows: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(300))
    fetched_at: Mapped[datetime] = mapped_column(DateTime)  # UTC


class CongressSync(Base):
    """Last sync attempt per source. `error` set means the stored trades are from an earlier
    success; `docs_total` is the number of reports in the lookback window at that sync."""

    __tablename__ = "congress_syncs"

    source: Mapped[str] = mapped_column(String(8), primary_key=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime)  # UTC
    index_modified: Mapped[datetime | None] = mapped_column(DateTime)  # Clerk's Last-Modified
    docs_total: Mapped[int] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(String(300))
