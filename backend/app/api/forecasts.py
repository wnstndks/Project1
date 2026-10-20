from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.data.assets import base_symbol, resolve_symbol
from app.deps import (
    get_artifacts_dir,
    get_forecast_service,
    get_forecast_training,
    get_provider,
    get_quote_cache,
    get_session_factory,
)
from app.schemas.forecasts import (
    ForecastBacktestPoint,
    ForecastJobOut,
    ForecastStatusOut,
    PortfolioForecastOut,
    SymbolForecastOut,
    TrackRecordOut,
)
from app.services.forecasts import ForecastService, ForecastTraining
from app.services.market_data import MarketDataService

router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.get("/status", response_model=ForecastStatusOut)
def forecast_status(
    service: ForecastService = Depends(get_forecast_service),
    training: ForecastTraining = Depends(get_forecast_training),
):
    out = service.status()
    if training.job is not None:
        out["job"] = asdict(training.job)
    return out


@router.post("/train", response_model=ForecastJobOut, status_code=status.HTTP_202_ACCEPTED)
def start_training(
    training: ForecastTraining = Depends(get_forecast_training),
    session_factory=Depends(get_session_factory),
    provider=Depends(get_provider),
    quote_cache=Depends(get_quote_cache),
    artifacts_dir: Path = Depends(get_artifacts_dir),
):
    def make_market(db: Session) -> MarketDataService:
        return MarketDataService(db, provider, quote_cache)

    return asdict(training.start(session_factory, make_market, artifacts_dir))


# Inference rebuilds the latest panel (tens of assets), so it runs off the event loop.
@router.get("/portfolio", response_model=PortfolioForecastOut)
async def portfolio_forecast(service: ForecastService = Depends(get_forecast_service)):
    return await run_in_threadpool(service.portfolio_forecast)


@router.get("/track-record", response_model=TrackRecordOut)
def track_record(
    symbol: str | None = None, service: ForecastService = Depends(get_forecast_service)
):
    return service.track_record(base_symbol(resolve_symbol(symbol)) if symbol else None)


@router.get("/{symbol}", response_model=SymbolForecastOut)
async def symbol_forecast(symbol: str, service: ForecastService = Depends(get_forecast_service)):
    return await run_in_threadpool(service.forecast, base_symbol(resolve_symbol(symbol)))


@router.get("/{symbol}/backtest", response_model=list[ForecastBacktestPoint])
def backtest(
    symbol: str,
    horizon: Literal["1d", "1w", "1m"] = "1w",
    service: ForecastService = Depends(get_forecast_service),
):
    return service.backtest(base_symbol(resolve_symbol(symbol)), horizon)
