from dataclasses import asdict

from fastapi import APIRouter, Depends

from app.db.models import AssetType
from app.deps import get_projection_service
from app.schemas.projection import AssumptionsOut, ProjectionIn, ProjectionOut
from app.services.projection import ProjectionParams, ProjectionService

router = APIRouter(prefix="/projection", tags=["projection"])


@router.get("/assumptions", response_model=AssumptionsOut)
def assumptions(service: ProjectionService = Depends(get_projection_service)):
    return asdict(service.assumptions())


@router.post("/simulate", response_model=ProjectionOut)
def simulate(body: ProjectionIn, service: ProjectionService = Depends(get_projection_service)):
    def per_class(stock: float | None, crypto: float | None) -> dict[AssetType, float]:
        pairs = {AssetType.STOCK: stock, AssetType.CRYPTO: crypto}
        return {k: v for k, v in pairs.items() if v is not None}

    params = ProjectionParams(
        years=body.years,
        monthly_contribution_krw=body.monthly_contribution_krw,
        inflation_pct=body.inflation_pct,
        simulations=body.simulations,
        seed=body.seed,
        return_pct=per_class(body.stock_return_pct, body.crypto_return_pct),
        vol_pct=per_class(body.stock_vol_pct, body.crypto_vol_pct),
        contribution_stock_pct=body.contribution_stock_pct,
        target_krw=body.target_krw,
    )
    return asdict(service.run(params))
