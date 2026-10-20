from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    corporate_actions,
    forecasts,
    health,
    imports,
    market,
    news,
    portfolio,
    predictions,
    projection,
    transactions,
)
from app.config import get_settings
from app.data.assets import UnsupportedSymbolError
from app.data.news_sources import NewsDataError
from app.data.provider import MarketDataError
from app.services.errors import DomainError
from app.services.market_data import SymbolNotFoundError


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Asset Manager API", version="0.1.0")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        content = {"detail": str(exc)}
        if getattr(exc, "code", None):
            content["code"] = exc.code
        return JSONResponse(status_code=exc.status_code, content=content)

    @app.exception_handler(UnsupportedSymbolError)
    async def _unsupported_symbol(_: Request, exc: UnsupportedSymbolError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(SymbolNotFoundError)
    async def _symbol_not_found(_: Request, exc: SymbolNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": f"Unknown symbol '{exc}'"})

    @app.exception_handler(NewsDataError)
    async def _news_data_error(_: Request, exc: NewsDataError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(MarketDataError)
    async def _market_data_error(_: Request, exc: MarketDataError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    api = APIRouter(prefix="/api")
    for module in (
        health,
        market,
        transactions,
        portfolio,
        predictions,
        projection,
        imports,
        news,
        corporate_actions,
        forecasts,
    ):
        api.include_router(module.router)
    app.include_router(api)
    return app


app = create_app()
