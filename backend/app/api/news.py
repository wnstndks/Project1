from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool

from app.data.assets import resolve_symbol
from app.deps import get_news_service
from app.schemas.news import NewsOut
from app.services.news import NewsService

router = APIRouter(prefix="/news", tags=["news"])


@router.get("/{symbol}", response_model=NewsOut)
async def news(
    symbol: str,
    days: int = Query(30, ge=1, le=90),
    service: NewsService = Depends(get_news_service),
):
    resolved = resolve_symbol(symbol)
    # Network fetches (GDELT is throttled to one call per 6 s) and FinBERT scoring block.
    summary = await run_in_threadpool(service.summary, resolved, days)
    return NewsOut(
        symbol=resolved,
        articles=summary.articles,
        days=summary.days,
        finnhub_enabled=summary.finnhub_enabled,
        warnings=summary.warnings,
    )
