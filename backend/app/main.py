from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import health, market
from app.config import get_settings
from app.data.provider import MarketDataError
from app.services.market_data import SymbolNotFoundError


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Asset Manager API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(SymbolNotFoundError)
    async def _symbol_not_found(_: Request, exc: SymbolNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": f"Unknown symbol '{exc}'"})

    @app.exception_handler(MarketDataError)
    async def _market_data_error(_: Request, exc: MarketDataError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    api.include_router(market.router)
    app.include_router(api)
    return app


app = create_app()
