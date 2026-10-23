from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, Query

from app.config import get_settings
from app.deps import get_benchmark_service, get_portfolio_service
from app.schemas.portfolio import (
    BenchmarkOut,
    HistoryPointOut,
    HoldingOut,
    SparklineOut,
    SummaryOut,
)
from app.services.benchmarks import BenchmarkService, parse_symbols
from app.services.portfolio import PortfolioService

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("/holdings", response_model=list[HoldingOut])
def holdings(service: PortfolioService = Depends(get_portfolio_service)):
    return [asdict(h) for h in service.holdings()]


@router.get("/summary", response_model=SummaryOut)
def summary(service: PortfolioService = Depends(get_portfolio_service)):
    return asdict(service.summary())


@router.get("/history", response_model=list[HistoryPointOut])
def history(start: date | None = None, service: PortfolioService = Depends(get_portfolio_service)):
    return [asdict(p) for p in service.history(start)]


@router.get("/sparklines", response_model=list[SparklineOut])
def sparklines(
    days: int = Query(30, ge=7, le=365),
    service: PortfolioService = Depends(get_portfolio_service),
):
    return [asdict(s) for s in service.sparklines(days)]


@router.get("/benchmark", response_model=BenchmarkOut)
def benchmark(
    symbols: str | None = Query(None, description="Comma-separated; default AM_BENCHMARKS"),
    start: date | None = None,
    service: BenchmarkService = Depends(get_benchmark_service),
):
    """My history beside benchmarks bought and sold with my own cash flows on the same days."""
    result = service.compare(parse_symbols(symbols, get_settings().benchmarks), start)
    return {
        "mine": [asdict(p) for p in result.mine],
        "benchmarks": [
            {"symbol": s.symbol, "name_ko": s.name_ko, "points": [asdict(p) for p in s.points]}
            for s in result.benchmarks
        ],
    }
