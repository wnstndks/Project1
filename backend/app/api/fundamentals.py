"""Published company figures of a stock (DECISIONS.md D-036): valuation multiples, margins,
growth and recent income statements, as the provider reports them.

Facts with a source and a date. Not a signal, not a rule check, not a policy check and not
advice: no figure is judged here, and nothing places an order. The service caches per symbol
(24 hours) and keeps the last successful figures when a refresh fails, so both routes may
make provider requests and run off the event loop.

A failed lookup is not an HTTP error: the answer is 200 with `stale`, `error` and whatever
figures were stored before (none, if it never succeeded). Only a ticker that does not exist
is a 404, and an invalid one a 422.
"""

from contextlib import suppress
from dataclasses import asdict, fields

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from app.config import get_settings
from app.data.assets import resolve_symbol
from app.data.provider import Fundamentals, MarketDataError, StatementRow
from app.db.models import AssetType
from app.deps import get_fundamentals_service, get_market_service, get_portfolio_service
from app.schemas.fundamentals import (
    DISCLAIMER_KO,
    SOURCE_FAKE_KO,
    SOURCE_KO,
    FundamentalsOut,
    HeldFundamentalsOut,
    NoteCode,
)
from app.services.fundamentals import FundamentalsService, FundamentalsView
from app.services.market_data import MarketDataService
from app.services.portfolio import PortfolioService

router = APIRouter(prefix="/fundamentals", tags=["fundamentals"])

_NO_FIGURES = {f.name: None for f in fields(Fundamentals)} | {"annual": (), "quarterly": ()}
# What the provider leaves out when the statement currency is not the quote currency (an ADR):
# Yahoo's values for these mix the two.
_MIXED_CURRENCY_FIELDS = (
    "market_cap",
    "pbr",
    "psr",
    "eps_trailing",
    "eps_forward",
    "book_value_per_share",
)


# Days between two consecutive quarter ends. Four rows that far apart are twelve months.
_QUARTER_GAP_DAYS = (80, 100)


def get_source() -> str:
    return SOURCE_FAKE_KO if get_settings().market_provider == "fake" else SOURCE_KO


def _four_quarter_sums(rows: tuple[StatementRow, ...]) -> tuple[float, float] | None:
    """Operating income and net income over the newest four quarters, or None unless those
    are four consecutive quarters that all report both lines (no partial year is summed)."""
    four = rows[:4]
    if len(four) < 4:
        return None
    low, high = _QUARTER_GAP_DAYS
    gaps = [(a.period_end - b.period_end).days for a, b in zip(four, four[1:], strict=False)]
    if not all(low <= gap <= high for gap in gaps):
        return None
    operating = [row.operating_income for row in four]
    net = [row.net_income for row in four]
    if any(value is None for value in (*operating, *net)):
        return None
    return sum(operating), sum(net)


def _notes(data: Fundamentals | None) -> list[NoteCode]:
    """What the response itself says about a figure that is missing or easy to misread.
    Codes only; the screen owns the wording. Each code restates the figures, never a cause
    and never a verdict."""
    if data is None:
        return []
    notes: list[NoteCode] = []
    # A PER needs a positive EPS. Where the EPS itself was left out (ADR), a 12-month net
    # loss says the same thing.
    lost_money = (
        data.eps_trailing <= 0
        if data.eps_trailing is not None
        else data.net_margin_pct is not None and data.net_margin_pct < 0
    )
    if data.per_trailing is None and lost_money:
        notes.append("per_negative_earnings")
    if data.per_forward is None and data.eps_forward is not None and data.eps_forward <= 0:
        notes.append("per_forward_negative_earnings")
    # A PER exists only when 12-month net income is positive. With the latest operating
    # income negative, that PER alone reads like a company earning from its business. The
    # newest quarter decides; the newest fiscal year only when the quarter is not reported.
    if data.per_trailing is not None and data.per_trailing > 0:
        quarter = data.quarterly[0].operating_income if data.quarterly else None
        year = data.annual[0].operating_income if data.annual else None
        if quarter is not None:
            if quarter < 0:
                notes.append("operating_loss_net_profit")
        elif year is not None and year < 0:
            notes.append("operating_loss_net_profit_annual")
    # The operating margin is the newest quarter's operating income over its revenue. Two
    # reasons for its absence can be read off the statements; any other stays unexplained.
    if data.operating_margin_pct is None:
        rows = (*data.quarterly, *data.annual)
        if rows and all(row.operating_income is None for row in rows):
            notes.append("operating_income_not_reported")
        elif data.quarterly and data.quarterly[0].revenue == 0:
            notes.append("zero_revenue_quarter")
    # Net income above a positive operating income: the net margin beside it is then larger
    # than the operating margin (it can pass 100%), which the plain reading "what is left of
    # the sales" does not prepare for. Twelve months when four consecutive quarters report
    # both lines, else the newest fiscal year. An operating loss is the notes above.
    if data.net_margin_pct is not None:
        twelve_months = _four_quarter_sums(data.quarterly)
        if twelve_months is not None:
            operating, net = twelve_months
            if net > operating > 0:
                notes.append("net_income_above_operating_income")
        elif data.annual:
            operating, net = data.annual[0].operating_income, data.annual[0].net_income
            if operating is not None and net is not None and net > operating > 0:
                notes.append("net_income_above_operating_income_annual")
    if data.currency not in (None, "USD") and all(
        getattr(data, name) is None for name in _MIXED_CURRENCY_FIELDS
    ):
        notes.append("currency_mismatch")
    return notes


def _out(view: FundamentalsView, source: str) -> FundamentalsOut:
    figures = asdict(view.data) if view.data is not None else _NO_FIGURES
    return FundamentalsOut.model_validate(
        {
            **figures,
            "symbol": view.symbol,
            "supported": view.supported,
            "as_of": view.fetched_at.date() if view.fetched_at is not None else None,
            "stale": view.stale,
            "error": view.error,
            "notes": _notes(view.data),
            "source_ko": source,
            "disclaimer_ko": DISCLAIMER_KO,
        }
    )


def _held(
    portfolio: PortfolioService, service: FundamentalsService, source: str
) -> HeldFundamentalsOut:
    # Largest position first, the order of the holdings list on the home page.
    symbols = [
        h.symbol for h in portfolio.holdings() if h.quantity > 0 and h.asset_type == AssetType.STOCK
    ]
    views = {v.symbol: v for v in service.get_many(symbols)} if symbols else {}
    ordered = [views[s] for s in symbols if s in views]
    dated = [v.fetched_at.date() for v in ordered if v.data is not None and v.fetched_at]
    return HeldFundamentalsOut(
        items=[_out(v, source) for v in ordered],
        as_of=min(dated, default=None),
        source_ko=source,
        disclaimer_ko=DISCLAIMER_KO,
    )


def _one(
    symbol: str, service: FundamentalsService, market: MarketDataService, source: str
) -> FundamentalsOut:
    view = service.get(symbol)
    if view.data is None and view.error:
        # The lookup failed and there are no earlier figures to show. A ticker the quote
        # source does not know is a 404 like on the market routes (SymbolNotFoundError passes
        # through). Any other failure is answered as it is: 200 with `error` and no figures,
        # so the screen can say they could not be fetched right now.
        with suppress(MarketDataError):
            market.get_quote(symbol)
    return _out(view, source)


# Registered before "/{symbol}", which would otherwise capture "held" as a ticker.
@router.get("/held", response_model=HeldFundamentalsOut)
async def held_fundamentals(
    portfolio: PortfolioService = Depends(get_portfolio_service),
    service: FundamentalsService = Depends(get_fundamentals_service),
    source: str = Depends(get_source),
):
    """Every held stock (coins have no statements and are left out)."""
    return await run_in_threadpool(_held, portfolio, service, source)


# The parameter must stay named `symbol`: the demo's ticker guard goes by that name.
@router.get("/{symbol}", response_model=FundamentalsOut)
async def symbol_fundamentals(
    symbol: str,
    service: FundamentalsService = Depends(get_fundamentals_service),
    market: MarketDataService = Depends(get_market_service),
    source: str = Depends(get_source),
):
    return await run_in_threadpool(_one, resolve_symbol(symbol), service, market, source)
