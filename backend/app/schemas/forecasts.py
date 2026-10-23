from datetime import date, datetime

from pydantic import BaseModel


class HorizonForecastOut(BaseModel):
    horizon: str  # "1d" | "1w" | "1m"
    as_of: date
    target_date: date
    base_price: float
    p10: float
    p50: float
    p90: float
    p_up: float
    # The same quantities from the baselines the model must beat.
    baseline_p_up: float
    baseline_p10: float
    baseline_p90: float
    # The live verdict (forecast.report.live_edge_at): True only when the walk-forward and
    # holdout tests show skill and, for the range, a forward paper test has confirmed it.
    direction_edge: bool
    range_edge: bool
    # Why: edge | forward_test_pending | not_significant | no_data
    direction_reason: str
    range_reason: str


class ClosePoint(BaseModel):
    date: date
    close: float


class SymbolForecastOut(BaseModel):
    symbol: str
    trained_at: datetime
    data_end: date
    # Won per dollar of this asset as the user values it (Upbit coins: premium included).
    krw_rate: float | None = None
    horizons: list[HorizonForecastOut]
    recent: list[ClosePoint]


class PortfolioHorizonOut(BaseModel):
    horizon: str
    value_krw: float
    p10: float
    p50: float
    p90: float
    mean: float
    var95: float
    es95: float
    paths: int


class PortfolioForecastOut(BaseModel):
    trained_at: datetime
    horizons: list[PortfolioHorizonOut]
    excluded: list[str]
    # Current premium of Upbit-held coins over the dollar price (0.01 = 1%).
    kimchi_premium: dict[str, float] = {}


class ForecastBacktestPoint(BaseModel):
    date: date
    actual: float  # realized log return
    q10: float
    q50: float
    q90: float
    p_up: float
    segment: str


class ForecastJobOut(BaseModel):
    state: str
    started_at: datetime
    finished_at: datetime | None
    error: str | None
    log: list[str]


class HeldHorizonOut(BaseModel):
    """One horizon of a held symbol, as price ratios so the client can scale any base
    (the dollar close or the won value) without recomputing the forecast."""

    horizon: str
    as_of: date
    target_date: date
    low_ratio: float  # p10 / base price
    mid_ratio: float  # p50 / base price
    high_ratio: float  # p90 / base price
    p_up: float
    baseline_p_up: float
    direction_edge: bool
    range_edge: bool
    direction_reason: str
    range_reason: str


class HeldForecastOut(BaseModel):
    """GET /forecasts/held: every symbol GET /forecasts/{symbol} would answer for (symbols
    ever traded), sorted by symbol; symbols without a forecast are left out."""

    symbol: str
    asset_class: str  # stock | crypto
    horizons: list[HeldHorizonOut]


class LiveVerdictOut(BaseModel):
    """Why a kind of forecast is or is not trusted live (forecast.report.live_edge_at):
    edge | forward_test_pending | not_significant | no_data."""

    direction: str
    range: str


class ForecastStatusOut(BaseModel):
    trained: bool
    meta: dict | None = None
    report: dict | None = None
    job: ForecastJobOut | None = None
    # The live verdict per asset class ("stock" | "crypto") and horizon ("1d" | "1w" | "1m"),
    # the same lookup the symbol forecasts show (D-026). The report's raw `edge` flags are
    # not it: a range edge stays withheld until its forward test. Empty before training.
    live: dict[str, dict[str, LiveVerdictOut]] = {}


class TrackSummaryOut(BaseModel):
    horizon: str
    scored: int
    coverage: float
    hit_rate: float
    baseline_hit_rate: float
    brier: float
    baseline_brier: float


class TrackRowOut(BaseModel):
    symbol: str
    horizon: str
    as_of: date
    target_date: date
    q10: float
    q50: float
    q90: float
    p_up: float
    realized: float


class TrackRecordOut(BaseModel):
    pending: int
    summary: list[TrackSummaryOut]
    recent: list[TrackRowOut]
