from datetime import date, datetime

from pydantic import BaseModel


class ErrorMetrics(BaseModel):
    mae: float
    rmse: float
    mape: float
    direction_acc: float


class HorizonMetrics(BaseModel):
    day: int
    model: ErrorMetrics
    baseline: ErrorMetrics


class Metrics(BaseModel):
    samples: int
    by_horizon: list[HorizonMetrics]
    best_epoch: int
    train_seconds: float


class ForecastPoint(BaseModel):
    date: date
    price: float
    return_pct: float


class ClosePoint(BaseModel):
    date: date
    close: float


class ForecastOut(BaseModel):
    symbol: str
    as_of: date
    base_price: float
    forecast: list[ForecastPoint]
    metrics: Metrics
    trained_at: datetime
    train_range: list[date]
    test_range: list[date]
    recent: list[ClosePoint]


class BacktestPoint(BaseModel):
    date: date
    actual: float
    predicted: float
    naive: float


class TrainedModelOut(BaseModel):
    symbol: str
    trained_at: datetime
    mape_model: float
    mape_baseline: float


class TrainingJobOut(BaseModel):
    symbol: str
    state: str
    started_at: datetime
    finished_at: datetime | None
    error: str | None
    log: list[str]
