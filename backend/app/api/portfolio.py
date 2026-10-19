from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends

from app.deps import get_portfolio_service
from app.schemas.portfolio import HistoryPointOut, HoldingOut, SummaryOut
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
