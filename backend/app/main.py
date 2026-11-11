from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import (
    auth,
    coach,
    congress,
    corporate_actions,
    forecasts,
    frontend,
    gurus,
    health,
    imports,
    learn,
    market,
    news,
    portfolio,
    predictions,
    projection,
    rules,
    transactions,
)
from app.config import Settings, get_settings
from app.data.assets import UnsupportedSymbolError
from app.data.news_sources import NewsDataError
from app.data.provider import MarketDataError
from app.security.demo import demo_symbol_guard
from app.security.middleware import SecurityState, build_stack
from app.services.errors import DomainError
from app.services.market_data import SymbolNotFoundError


def create_app(settings: Settings | None = None) -> FastAPI:
    """`settings` is for tests; the server always runs on `get_settings()`."""
    if settings is None:
        settings = get_settings()
    production = settings.env == "production"
    app = FastAPI(
        title="Asset Manager API",
        version="0.1.0",
        # A public instance does not publish its API schema.
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
        # Demo mode: ticker routes only answer for the demo's own symbols (every route gets
        # the guard, so one added later is covered too).
        dependencies=[Depends(demo_symbol_guard)] if settings.demo_mode else [],
    )
    security = SecurityState.from_settings(settings)
    app.state.security = security
    # Access control (D-035). `build_stack` lists the layers outermost first; add_middleware
    # puts each new one outside the previous, hence the reversal.
    for layer in reversed(build_stack(settings, security)):
        app.add_middleware(layer.cls, *layer.args, **layer.kwargs)

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
        auth,
        market,
        transactions,
        portfolio,
        predictions,
        projection,
        imports,
        news,
        corporate_actions,
        forecasts,
        gurus,
        congress,
        rules,
        coach,
        learn,
    ):
        api.include_router(module.router)
    app.include_router(api)
    # The built frontend, when there is one (the container sets AM_STATIC_DIR): its files and
    # the single-page app's pages for whatever no route above answered. Neither a mount nor a
    # route, so /api and the middleware above behave the same with or without it.
    if settings.static_dir is not None:
        frontend.install(app, settings.static_dir)
    return app


app = create_app()
