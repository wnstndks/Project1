from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.data.fake_provider import FakeProvider
from app.data.provider import MarketDataProvider
from app.db.session import get_db
from app.services.market_data import MarketDataService, QuoteCache


@lru_cache
def get_provider() -> MarketDataProvider:
    if get_settings().market_provider == "fake":
        return FakeProvider()
    from app.data.yfinance_provider import YFinanceProvider

    return YFinanceProvider()


@lru_cache
def get_quote_cache() -> QuoteCache:
    return QuoteCache()


def get_market_service(
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_provider),
    quote_cache: QuoteCache = Depends(get_quote_cache),
) -> MarketDataService:
    return MarketDataService(db, provider, quote_cache)
