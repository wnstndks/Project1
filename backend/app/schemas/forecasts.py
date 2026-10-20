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
    # True only when the walk-forward and holdout tests both show skill (see forecast.report).
    direction_edge: bool
    range_edge: bool


class ClosePoint(BaseModel):
    date: date
    close: float


class SymbolForecastOut(BaseModel):
    symbol: str
    trained_at: datetime
    data_end: date
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


class ForecastStatusOut(BaseModel):
    trained: bool
    meta: dict | None = None
    report: dict | None = None
    job: ForecastJobOut | None = None


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
