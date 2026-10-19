from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from app.data.assets import CRYPTO_ASSETS, UnsupportedSymbolError, asset_type_of, normalize_symbol
from app.db.models import AssetType
from app.deps import get_market_service
from app.schemas.market import AssetInfo, BarOut, QuoteOut
from app.services.market_data import MarketDataService

router = APIRouter(prefix="/market", tags=["market"])


def _resolve(symbol: str) -> str:
    """Accept "AAPL", "btc" or "BTC-USD" and return the provider symbol."""
    s = symbol.strip().upper()
    is_crypto = s.endswith("-USD") or f"{s}-USD" in CRYPTO_ASSETS
    asset_type = AssetType.CRYPTO if is_crypto else AssetType.STOCK
    try:
        return normalize_symbol(asset_type, s)
    except UnsupportedSymbolError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/crypto", response_model=list[AssetInfo])
def list_supported_crypto() -> list[AssetInfo]:
    return [
        AssetInfo(symbol=s, name=n, asset_type=AssetType.CRYPTO) for s, n in CRYPTO_ASSETS.items()
    ]


@router.get("/fx/usdkrw", response_model=QuoteOut)
def usd_krw(market: MarketDataService = Depends(get_market_service)) -> QuoteOut:
    q = market.usd_krw()
    return QuoteOut(symbol=q.symbol, price=q.price, as_of=q.as_of)


@router.get("/{symbol}/history", response_model=list[BarOut])
def history(
    symbol: str,
    start: date | None = Query(None, description="Defaults to one year ago"),
    end: date | None = None,
    market: MarketDataService = Depends(get_market_service),
):
    resolved = _resolve(symbol)
    start = start or date.today() - timedelta(days=365)
    return market.get_history(resolved, start, end)


@router.get("/{symbol}/quote", response_model=QuoteOut)
def quote(symbol: str, market: MarketDataService = Depends(get_market_service)) -> QuoteOut:
    q = market.get_quote(_resolve(symbol))
    return QuoteOut(symbol=q.symbol, price=q.price, as_of=q.as_of)


@router.get("/{symbol}/info", response_model=AssetInfo)
def info(symbol: str, market: MarketDataService = Depends(get_market_service)) -> AssetInfo:
    resolved = _resolve(symbol)
    market.get_quote(resolved)  # 404 for unknown tickers
    name = CRYPTO_ASSETS.get(resolved, resolved)
    return AssetInfo(symbol=resolved, name=name, asset_type=asset_type_of(resolved))
