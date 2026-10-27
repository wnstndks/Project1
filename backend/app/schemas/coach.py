"""The portfolio coach over HTTP (DECISIONS.md D-033): the user's investment policy and the
checks built on it.

The coach checks the portfolio against the policy the user wrote down. It is not a forecast,
not a stock pick and not investment advice, and nothing here places an order. Past-data
figures (volatility, drawdown, correlation, beta) carry their window; the UI adds "past
results do not guarantee the future". Numbers may arrive as strings and are parsed as exact
decimals. Range constraints live here; the cross-field rules (asset-class targets sum to 100,
crypto target within its cap, goal date in the future) live in `services/coach.py`, which
answers 422 naming the problem.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import Num

# --- policy ---------------------------------------------------------------------------------


class PolicyFieldsIn(BaseModel):
    # The goal is optional; the required annual return needs both amount and date.
    goal_krw: Decimal | None = Field(None, ge=0)
    goal_date: date | None = None
    monthly_contribution_krw: Decimal = Field(ge=0)
    # The deepest loss the user says they can sit through, in percent of equity.
    drawdown_tolerance_pct: Decimal = Field(gt=0, lt=100)
    max_position_weight_pct: Decimal = Field(gt=0, le=100)
    # All coins together, in percent of equity.
    max_crypto_weight_pct: Decimal = Field(ge=0, le=100)
    # Loss if every stop-loss were hit at once, as a share of equity in percent.
    max_total_risk_pct: Decimal = Field(gt=0, lt=100)
    # Drift from a target weight the rebalancing plan leaves alone, in percentage points.
    rebalance_band_pt: Decimal = Field(ge=0, lt=100)
    # Asset-class targets; together exactly 100.
    target_stock_pct: Decimal = Field(ge=0, le=100)
    target_crypto_pct: Decimal = Field(ge=0, le=100)
    target_cash_pct: Decimal = Field(ge=0, le=100)


class CashIn(BaseModel):
    """Cash the app cannot see, typed in by the user with the date it was true."""

    krw: Decimal = Field(ge=0)
    usd: Decimal = Field(ge=0)
    as_of: date


class PolicyIn(BaseModel):
    policy: PolicyFieldsIn
    # None clears the stored cash record: the form sends exactly what it shows.
    cash: CashIn | None = None


class PolicyFieldsOut(BaseModel):
    goal_krw: Num | None
    goal_date: date | None
    monthly_contribution_krw: Num
    drawdown_tolerance_pct: Num
    max_position_weight_pct: Num
    max_crypto_weight_pct: Num
    max_total_risk_pct: Num
    rebalance_band_pt: Num
    target_stock_pct: Num
    target_crypto_pct: Num
    target_cash_pct: Num


class CashOut(BaseModel):
    krw: Num
    usd: Num
    as_of: date


class PolicyOut(BaseModel):
    policy: PolicyFieldsOut
    # None while the user has not entered cash.
    cash: CashOut | None
    # Derived from the AM_RISK_* / AM_RULES_* settings, for the reset button.
    defaults: PolicyFieldsOut
    # Legal but noteworthy choices (a tolerance looser than the project limit, a goal
    # without a date, a cash target without a cash record), as text for the screen.
    warnings: list[str]
    # None while no row is stored (the defaults apply).
    updated_at: datetime | None
    # The cash record's date is more than CASH_STALE_DAYS old.
    cash_stale: bool
    # False while no row is stored: the screen shows the defaults and says so.
    policy_set: bool


# --- diagnosis ---------------------------------------------------------------------------------


class WeightOut(BaseModel):
    symbol: str
    asset_class: str
    currency: str
    value_krw: float
    # Share of equity (cash included when a cash record exists) and of the invested amount.
    weight_pct: float
    invested_weight_pct: float
    # The user's per-symbol target from the rule settings, when set.
    target_pct: float | None
    # The symbol's cap under the policy (index funds keep their own cap, D-025).
    cap_pct: float


class ConcentrationOut(BaseModel):
    """Invested-basis concentration; `effective_n` = 1/HHI, how many equal holdings this is."""

    count: int
    top1_symbol: str | None
    top1_pct: float
    top3_pct: float
    hhi: float
    effective_n: float


class ExposureOut(BaseModel):
    equity_krw: float
    invested_krw: float
    stock_pct: float
    crypto_pct: float
    # None without a cash record; then every share is of the invested amount.
    cash_pct: float | None
    # USD-denominated holdings: currency risk sits inside the KRW figures, so it is shown.
    usd_pct: float


class ExcludedOut(BaseModel):
    symbol: str
    bars: int


class RiskWindowOut(BaseModel):
    """Volatility and fixed-weight drawdown of today's mix over one past window. Not a
    forecast: the window and `usable` say what the number rests on."""

    name: str
    grid: str
    periods_per_year: int
    rows: int
    start: date | None
    end: date | None
    annual_vol_pct: float
    # One standard deviation of a year's move in won, on the same base as the weights.
    swing_1sigma_krw: float
    max_drawdown_pct: float
    drawdown_peak: date | None
    drawdown_trough: date | None
    coverage_pct: float
    included: list[str]
    excluded: list[ExcludedOut]
    method: str
    usable: bool
    reason: str | None
    # True when the window's first bar was the peak the drawdown fell from (then
    # `drawdown_peak` is None and the UI says "from the start of the window").
    peak_at_window_start: bool


class ActualRiskOut(BaseModel):
    """The real value curve with deposits taken out (time-weighted index). Information only;
    it never trips the kill switch (D-027)."""

    since: date
    points: int
    twr_max_drawdown_pct: float
    current_drawdown_pct: float
    daily_loss_breaches_1y: int
    drawdown_breaches_1y: int
    limit_drawdown_pct: float
    limit_daily_loss_pct: float


class RiskOut(BaseModel):
    windows: list[RiskWindowOut]
    actual: ActualRiskOut | None
    actual_error: str | None


class CorrelationOut(BaseModel):
    symbols: list[str]
    matrix: list[list[float]]
    method: str
    rows: int
    excluded: list[str]


class BetaOut(BaseModel):
    """Slope of the symbol's returns on its benchmark's, both in the trade currency."""

    symbol: str
    benchmark: str
    window: str
    beta: float | None
    r2: float | None
    rows: int
    reason: str | None


class ViolationOut(BaseModel):
    code: str
    severity: str  # warn | info
    label_ko: str
    detail: str
    value: float | None
    limit: float | None
    subject: str | None


class DiagnosisOut(BaseModel):
    as_of: date
    # True with no open position: nothing to check.
    empty: bool
    policy_set: bool
    policy: PolicyFieldsOut
    equity_krw: float
    invested_krw: float
    cash_krw: float | None
    cash_as_of: date | None
    cash_stale: bool
    usd_krw: float
    weights: list[WeightOut]
    concentration: ConcentrationOut | None
    exposure: ExposureOut | None
    risk: RiskOut
    correlation: CorrelationOut | None
    betas: list[BetaOut]
    # Loss if every stop-loss were hit, as a share of equity (from the rule checks).
    total_risk_pct_equity: float | None
    violations: list[ViolationOut]
    # Arithmetic, not a forecast: the constant return that reaches the goal in time.
    required_annual_return_pct: float | None
    goal_years: float | None
    caveats: list[str]
    checked_at: datetime


# --- rebalancing --------------------------------------------------------------------------------


class TargetOut(BaseModel):
    symbol: str
    asset_class: str
    current_pct: float
    target_pct: float
    drift_pt: float
    # symbol | remainder | scaled | class_zero (strategy/coach.TargetPlan)
    source: str
    capped: bool


class RebalanceOrderOut(BaseModel):
    """One change the policy implies, checked against the limits. Never placed."""

    symbol: str
    side: str  # buy | sell
    requested_krw: float
    allowed_krw: float
    status: str  # accepted | clipped | rejected
    reasons: list[str]
    labels: list[str]
    approx_qty: float | None
    price: float
    currency: str
    price_krw: float
    # Reference only, sells: allowed × (1 − cost_basis / value). Fees and taxes left out.
    realized_pnl_krw_if_sold: float | None


class AfterWeightOut(BaseModel):
    symbol: str
    weight_pct: float


class AfterOut(BaseModel):
    weights: list[AfterWeightOut]
    cash_krw: float
    cash_pct: float | None


class RebalanceOut(BaseModel):
    empty: bool
    equity_krw: float
    cash_known: bool
    band_pt: float
    class_targets: dict[str, float | None]
    unallocated_pct: float
    targets: list[TargetOut]
    orders: list[RebalanceOrderOut]
    after: AfterOut | None
    notes: list[str]
    headline_ko: str
    disclaimer_ko: str


# --- habits in the trade log ---------------------------------------------------------------------


class FlagOut(BaseModel):
    code: str
    label_ko: str
    trade_id: int
    symbol: str
    date: date
    detail: str
    value: float | None


class PatternOut(BaseModel):
    code: str
    label_ko: str
    count: int
    detail: str
    trades: list[FlagOut]
    # For `overtrading`: the months flagged ("YYYY-MM").
    months: list[str]


class MonthCountOut(BaseModel):
    month: str
    buys: int
    sells: int
    total: int


class LagFlagOut(BaseModel):
    symbol: str
    # In the trade currency (USD, or Upbit won for KRW coins).
    currency: str
    cut_price: float
    days: int
    since: date
    last_close: float
    # True when every loaded bar was already at or below the stop: `since` is then the first
    # bar loaded, not the day the price crossed, and `days` is a lower bound (N-COACH-6).
    since_window_start: bool = False


class PatternsOut(BaseModel):
    empty: bool
    window_start: date
    window_end: date
    trades_considered: int
    trades_without_bars: int
    patterns: list[PatternOut]
    monthly: list[MonthCountOut]
    rule_lag: list[LagFlagOut]
    caveats: list[str]


# --- monthly review ------------------------------------------------------------------------------


class ReviewBenchmarkOut(BaseModel):
    """The same cash flows replayed into a benchmark over the month; `excess_krw` is my
    change minus its change (both include the same deposits, so they cancel)."""

    symbol: str
    name_ko: str
    start_value_krw: float
    end_value_krw: float
    change_krw: float
    excess_krw: float


class TradeCountOut(BaseModel):
    buys: int
    sells: int


class ReviewOut(BaseModel):
    empty: bool
    month: str
    start: date
    end: date
    start_point: date | None
    end_point: date | None
    start_value_krw: float
    end_value_krw: float
    change_krw: float
    # Net cash put in over the month (buys − sells, in won); change − contributions is the
    # market result.
    contributions_krw: float
    market_pnl_krw: float
    realized_pnl_krw: float
    dividends_krw: float
    benchmarks: list[ReviewBenchmarkOut]
    trades: TradeCountOut
    flagged_trades: list[FlagOut]
    # False when the month starts before the habit window (today − 1 year): the flags were not
    # counted and `flagged_trades` is empty, with a caveat saying so (N-COACH-2).
    flags_counted: bool
    # Trades up to the month's end whose unit price fails the 20x rule against the close of
    # their day; above 0 the deposit/market split is distorted and the first caveat says so.
    suspicious_trades: int
    # Warnings from the weight- and exposure-based checks alone (no bars), so it can differ
    # from the diagnosis count; the UI labels it as such (N-COACH-5).
    violations_now: int
    months_available: list[str]
    caveats: list[str]
