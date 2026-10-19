from functools import lru_cache
from pathlib import Path

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.data.fake_provider import FakeProvider
from app.data.news_sources import FinnhubClient, GdeltClient
from app.data.provider import MarketDataProvider
from app.data.upbit_provider import RoutingProvider, UpbitProvider
from app.db.session import get_db
from app.ml.sentiment import FinBertScorer, SentimentScorer
from app.services.market_data import MarketDataService, QuoteCache
from app.services.news import NewsService
from app.services.portfolio import PortfolioService
from app.services.predictions import PredictionService, TrainingJobs
from app.services.projection import ProjectionService
from app.services.screenshot_extractor import (
    ClaudeExtractor,
    FakeExtractor,
    HoldingsExtractor,
    OllamaExtractor,
)
from app.services.statement_import import StatementImportService
from app.services.transactions import TransactionService


@lru_cache
def get_provider() -> MarketDataProvider:
    if get_settings().market_provider == "fake":
        return FakeProvider()
    from app.data.yfinance_provider import YFinanceProvider

    # Upbit KRW markets ("KRW-BTC") come from Upbit, everything else from yfinance.
    return RoutingProvider(YFinanceProvider(), UpbitProvider())


@lru_cache
def get_quote_cache() -> QuoteCache:
    return QuoteCache()


def get_market_service(
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_provider),
    quote_cache: QuoteCache = Depends(get_quote_cache),
) -> MarketDataService:
    return MarketDataService(db, provider, quote_cache)


def get_transaction_service(
    db: Session = Depends(get_db), market: MarketDataService = Depends(get_market_service)
) -> TransactionService:
    return TransactionService(db, market)


def get_portfolio_service(
    db: Session = Depends(get_db), market: MarketDataService = Depends(get_market_service)
) -> PortfolioService:
    return PortfolioService(db, market)


def get_artifacts_dir() -> Path:
    return get_settings().artifacts_dir


@lru_cache
def get_training_jobs() -> TrainingJobs:
    return TrainingJobs()


def get_prediction_service(
    market: MarketDataService = Depends(get_market_service),
    artifacts_dir: Path = Depends(get_artifacts_dir),
) -> PredictionService:
    return PredictionService(market, artifacts_dir)


def get_projection_service(
    market: MarketDataService = Depends(get_market_service),
    portfolio: PortfolioService = Depends(get_portfolio_service),
) -> ProjectionService:
    return ProjectionService(market, portfolio)


@lru_cache
def get_extractor() -> HoldingsExtractor:
    settings = get_settings()
    if settings.import_extractor == "fake":
        return FakeExtractor()
    if settings.import_extractor == "ollama":
        return OllamaExtractor(settings.ollama_model, settings.ollama_url)
    key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
    return ClaudeExtractor(settings.import_model, api_key=key)


def get_import_service(
    extractor: HoldingsExtractor = Depends(get_extractor),
    market: MarketDataService = Depends(get_market_service),
    portfolio: PortfolioService = Depends(get_portfolio_service),
    transactions: TransactionService = Depends(get_transaction_service),
) -> StatementImportService:
    return StatementImportService(extractor, market, portfolio, transactions)


@lru_cache
def get_gdelt() -> GdeltClient:
    return GdeltClient()


@lru_cache
def get_finnhub() -> FinnhubClient | None:
    key = get_settings().finnhub_api_key
    return FinnhubClient(key.get_secret_value()) if key else None


@lru_cache
def get_scorer() -> SentimentScorer:
    return FinBertScorer()


def get_news_service(
    db: Session = Depends(get_db),
    provider: MarketDataProvider = Depends(get_provider),
    gdelt: GdeltClient = Depends(get_gdelt),
    finnhub: FinnhubClient | None = Depends(get_finnhub),
    scorer: SentimentScorer = Depends(get_scorer),
) -> NewsService:
    return NewsService(db, provider, gdelt, finnhub, scorer)
