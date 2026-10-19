from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from app.data.assets import (
    CRYPTO_ASSETS,
    UPBIT_MARKETS,
    asset_type_of,
    base_symbol,
    resolve_symbol,
)
from app.db.models import AssetType
from app.deps import get_market_service
from app.schemas.market import AssetInfo, BarOut, KimchiPremiumOut, QuoteOut
from app.services.market_data import MarketDataService

router = APIRouter(prefix="/market", tags=["market"])

# KRW=X stops updating over the weekend; a Monday-morning premium can be off by ~1%.
FX_STALE_AFTER = timedelta(hours=36)


@router.get("/crypto", response_model=list[AssetInfo])
def list_supported_crypto() -> list[AssetInfo]:
    return [
        AssetInfo(symbol=s, name=n, asset_type=AssetType.CRYPTO) for s, n in CRYPTO_ASSETS.items()
    ]


@router.get("/kimchi", response_model=list[KimchiPremiumOut])
def kimchi_premium(market: MarketDataService = Depends(get_market_service)):
    """Upbit KRW price vs the global USD price converted at today's USD/KRW rate."""
    fx_quote = market.usd_krw()
    fx = fx_quote.price
    fx_stale = (datetime.now() - fx_quote.as_of) > FX_STALE_AFTER
    quotes = market.get_quotes([*UPBIT_MARKETS, *UPBIT_MARKETS.values()])
    out = []
    for symbol, upbit in UPBIT_MARKETS.items():
        global_krw = quotes[symbol].price * fx
        out.append(
            KimchiPremiumOut(
                symbol=symbol,
                upbit_krw=quotes[upbit].price,
                global_usd=quotes[symbol].price,
                usd_krw=fx,
                global_krw=global_krw,
                premium_pct=(quotes[upbit].price / global_krw - 1) * 100,
                upbit_as_of=quotes[upbit].as_of,
                global_as_of=quotes[symbol].as_of,
                fx_as_of=fx_quote.as_of,
                fx_stale=fx_stale,
            )
        )
    return out


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
    resolved = resolve_symbol(symbol)
    start = start or date.today() - timedelta(days=365)
    return market.get_history(resolved, start, end)


@router.get("/{symbol}/quote", response_model=QuoteOut)
def quote(symbol: str, market: MarketDataService = Depends(get_market_service)) -> QuoteOut:
    q = market.get_quote(resolve_symbol(symbol))
    return QuoteOut(symbol=q.symbol, price=q.price, as_of=q.as_of)


@router.get("/{symbol}/info", response_model=AssetInfo)
def info(symbol: str, market: MarketDataService = Depends(get_market_service)) -> AssetInfo:
    resolved = resolve_symbol(symbol)
    market.get_quote(resolved)  # 404 for unknown tickers
    name = CRYPTO_ASSETS.get(base_symbol(resolved), resolved)
    return AssetInfo(symbol=resolved, name=name, asset_type=asset_type_of(resolved))
