from pydantic import BaseModel, Field

from app.db.models import AssetType


class ClassStatsOut(BaseModel):
    value_krw: float
    weight_pct: float
    hist_return_pct: float
    vol_pct: float
    default_return_pct: float
    proxy: str | None


class AssumptionsOut(BaseModel):
    start_value_krw: float
    usd_krw: float
    classes: dict[AssetType, ClassStatsOut]
    correlation: float
    lookback_years: int


class ProjectionIn(BaseModel):
    years: int = Field(10, ge=1, le=40)
    monthly_contribution_krw: float = Field(0, ge=0, le=1e10)
    inflation_pct: float = Field(2.5, ge=0, le=20)
    simulations: int = Field(5000, ge=500, le=20000)
    seed: int = 42
    stock_return_pct: float | None = Field(None, ge=-50, le=100)
    crypto_return_pct: float | None = Field(None, ge=-50, le=100)
    stock_vol_pct: float | None = Field(None, ge=0, le=300)
    crypto_vol_pct: float | None = Field(None, ge=0, le=300)
    contribution_stock_pct: float | None = Field(None, ge=0, le=100)
    target_krw: float | None = Field(None, gt=0)


class YearPointOut(BaseModel):
    year: int
    contributed_krw: float
    p10: float
    p50: float
    p90: float
    p10_real: float
    p50_real: float
    p90_real: float


class ProjectionOut(BaseModel):
    years: list[YearPointOut]
    final_mean: float
    prob_target: float | None
    prob_loss: float
    used_return_pct: dict[AssetType, float]
    used_vol_pct: dict[AssetType, float]
    correlation: float
