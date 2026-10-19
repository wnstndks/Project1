from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, status

from app.data.assets import resolve_symbol
from app.deps import (
    get_artifacts_dir,
    get_market_service,
    get_prediction_service,
    get_training_jobs,
)
from app.ml.artifacts import TrainConfig
from app.schemas.predictions import BacktestPoint, ForecastOut, TrainedModelOut, TrainingJobOut
from app.services.errors import NotFoundError
from app.services.market_data import MarketDataService
from app.services.predictions import PredictionService, TrainingJobs

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.get("", response_model=list[TrainedModelOut])
def trained_models(service: PredictionService = Depends(get_prediction_service)):
    return service.trained()


@router.get("/{symbol}", response_model=ForecastOut)
def forecast(symbol: str, service: PredictionService = Depends(get_prediction_service)):
    return service.forecast(resolve_symbol(symbol))


@router.get("/{symbol}/backtest", response_model=list[BacktestPoint])
def backtest(symbol: str, service: PredictionService = Depends(get_prediction_service)):
    return service.backtest(resolve_symbol(symbol))


@router.post("/{symbol}/train", response_model=TrainingJobOut, status_code=status.HTTP_202_ACCEPTED)
def start_training(
    symbol: str,
    market: MarketDataService = Depends(get_market_service),
    artifacts_dir: Path = Depends(get_artifacts_dir),
    jobs: TrainingJobs = Depends(get_training_jobs),
):
    job = jobs.start(resolve_symbol(symbol), market, artifacts_dir, TrainConfig())
    return asdict(job)


@router.get("/{symbol}/train", response_model=TrainingJobOut)
def training_status(symbol: str, jobs: TrainingJobs = Depends(get_training_jobs)):
    job = jobs.get(resolve_symbol(symbol))
    if job is None:
        raise NotFoundError(f"No training job for {symbol}")
    return asdict(job)
