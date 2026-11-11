"""The read-only public demo (DECISIONS.md D-035).

Two closed-by-default rules for `AM_DEMO_MODE`:

1. Every non-read request under /api is refused unless its exact method and path are in
   `DEMO_WRITE_ALLOWLIST` (routes that only compute: no ledger or settings write, no paid API
   or LLM call). A write route added later is refused until someone lists it here.
2. Read routes that take a ticker only answer for symbols the demo already uses (its ledger,
   the benchmarks, the app's own proxies), so a visitor cannot grow the price cache or make
   the server hammer the market data provider with arbitrary tickers.
"""

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.assets import (
    CRYPTO_ASSETS,
    FX_USDKRW,
    UPBIT_MARKETS,
    UnsupportedSymbolError,
    resolve_symbol,
)
from app.db.models import Transaction
from app.db.session import get_db
from app.security.paths import is_api, route_path
from app.services.errors import DomainError

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# (method, exact path). Reviewed one by one; tests/test_demo_mode.py lists every write route.
DEMO_WRITE_ALLOWLIST = frozenset(
    {
        # Monte Carlo on the demo's own holdings: reads the same cached bars as
        # GET /api/projection/assumptions, bounded inputs, nothing stored.
        ("POST", "/api/projection/simulate"),
        # No data behind them: login answers "not configured" on a demo without a login,
        # logout only clears a cookie.
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/logout"),
    }
)

READ_ONLY_DETAIL = "데모에서는 저장·수정할 수 없어요"
READ_ONLY_CODE = "demo_read_only"
SYMBOL_DETAIL = "데모에서는 데모 장부에 있는 종목만 볼 수 있어요"
SYMBOL_CODE = "demo_symbol_not_allowed"

# Path or query parameters that carry tickers ("symbols" is a comma-separated list).
SYMBOL_PARAMS = ("symbol", "symbols")

# Symbols the app fetches on its own whatever the ledger holds: the four coins and their
# Upbit markets (kimchi premium, KRW valuation), USD/KRW, and SPY (proxy for an empty stock
# class in the projection, beta benchmark, monthly review).
INTERNAL_SYMBOLS = frozenset({"SPY", FX_USDKRW, *CRYPTO_ASSETS, *UPBIT_MARKETS.values()})


class DemoSymbolNotAllowedError(DomainError):
    status_code = 403

    def __init__(self) -> None:
        super().__init__(SYMBOL_DETAIL, code=SYMBOL_CODE)


def canonical(raw: str) -> str:
    """The symbol a route would end up using for this input ("btc" -> "BTC-USD")."""
    s = raw.strip().upper()
    try:
        return resolve_symbol(s)
    except UnsupportedSymbolError:
        return s


def allowed_symbols(db: Session, benchmarks: str) -> frozenset[str]:
    held = set(db.scalars(select(Transaction.symbol).distinct()))
    listed = {canonical(part) for part in benchmarks.split(",") if part.strip()}
    upbit = {UPBIT_MARKETS[s] for s in held if s in UPBIT_MARKETS}
    return frozenset(INTERNAL_SYMBOLS | held | listed | upbit)


def requested_symbols(request: Request) -> list[str]:
    out: list[str] = []
    for name in SYMBOL_PARAMS:
        if name in request.path_params:
            # A blank path segment stays in the list and is refused (closed).
            out.extend(str(request.path_params[name]).split(","))
        for value in request.query_params.getlist(name):
            # A blank query value means "not given": routes fall back to their default.
            out.extend(part for part in value.split(",") if part.strip())
    return out


def demo_symbol_guard(request: Request, db: Session = Depends(get_db)) -> None:
    """App-wide dependency in demo mode: runs for every route, before the route's own
    dependencies touch a provider. Routes without a symbol parameter pass untouched, and
    so does anything outside /api (a page route of the frontend may carry `?symbol=`)."""
    if not is_api(route_path(request.scope)):
        return
    symbols = requested_symbols(request)
    if not symbols:
        return
    allowed = allowed_symbols(db, request.app.state.security.settings.benchmarks)
    if any(canonical(s) not in allowed for s in symbols):
        raise DemoSymbolNotAllowedError
