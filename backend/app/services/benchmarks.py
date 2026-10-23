"""'Same money on the same days' benchmarks.

Every trade in the ledger becomes a cash flow in won: a buy puts `quantity x price + fee` in, a
sell takes `quantity x price - fee` out, converted at the rate the ledger itself uses for that
trade (`fx_rate` recorded on the trade, else the market USD/KRW of the trade date). The flows
are then replayed into a benchmark (ARKK, SPY, BTC-USD, ...) bought and sold at that day's
close, so the curve answers "what if the same money had gone into X on the same days" and
stays fair when buys are spread over time.

Pure functions (`cash_flows`, `replay`) do the arithmetic; `BenchmarkService` wires them to
the ledger, the price cache and `PortfolioService.history`, which supplies my own curve on the
same daily grid (weekends and holidays forward-filled). Dividends are left out on both sides:
the portfolio history excludes them and Yahoo closes are split- but not dividend-adjusted.
"""

from bisect import bisect_right
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.assets import resolve_symbol
from app.db.models import Currency, Side, Transaction
from app.services.errors import DomainError
from app.services.ledger import ordered, trade_fx
from app.services.market_data import MarketDataService
from app.services.portfolio import HistoryPoint, PortfolioService

FxLookup = Callable[[date], Decimal]

DEFAULT_BENCHMARKS = "ARKK,BRK-B,SPY,QQQ,BTC-USD"
MAX_BENCHMARKS = 8
BENCHMARK_NAMES = {
    "ARKK": "ARK 이노베이션 ETF (캐시 우드)",
    "BRK-B": "버크셔 해서웨이 B (버핏)",
    "SPY": "S&P 500 ETF",
    "QQQ": "나스닥 100 ETF",
    "BTC-USD": "비트코인",
}
# Bars fetched before the first trade so that day has a previous close to forward-fill from.
LOOKBACK = timedelta(days=10)


@dataclass(frozen=True)
class CashFlow:
    date: date
    # Won put into the position (> 0, a buy) or taken out of it (< 0, a sell).
    amount_krw: Decimal


@dataclass(frozen=True)
class BenchmarkPoint:
    date: date
    value: float  # USD
    value_krw: float


@dataclass(frozen=True)
class BenchmarkSeries:
    symbol: str
    name_ko: str
    points: list[BenchmarkPoint]


@dataclass(frozen=True)
class BenchmarkComparison:
    mine: list[HistoryPoint]
    benchmarks: list[BenchmarkSeries]


def parse_symbols(raw: str | None, default: str = DEFAULT_BENCHMARKS) -> list[str]:
    """Comma-separated tickers -> canonical symbols, de-duplicated, in the given order."""
    out: list[str] = []
    for part in (raw if raw and raw.strip() else default).split(","):
        if not part.strip():
            continue
        symbol = resolve_symbol(part)
        if symbol not in out:
            out.append(symbol)
    if not out:
        raise DomainError("No benchmark symbols given")
    if len(out) > MAX_BENCHMARKS:
        raise DomainError(f"At most {MAX_BENCHMARKS} benchmarks at a time")
    return out


def benchmark_name(symbol: str) -> str:
    return BENCHMARK_NAMES.get(symbol, symbol)


def cash_flows(transactions: Iterable[Transaction], fx_on: FxLookup) -> list[CashFlow]:
    """One won-denominated flow per trade, in ledger order.

    Uses the same amounts and rate rule as the ledger's KRW cost basis (`Position.apply` with
    `trade_fx`), so a buy's flow equals the won the ledger records as invested that day.
    """
    flows = []
    for tx in ordered(transactions):
        currency = tx.currency or Currency.USD
        buy = tx.side == Side.BUY
        native = tx.quantity * tx.price + (tx.fee if buy else -tx.fee)
        krw = native if currency == Currency.KRW else native * trade_fx(tx, fx_on)
        flows.append(CashFlow(tx.trade_date, krw if buy else -krw))
    return flows


def replay(
    flows: list[CashFlow],
    closes: dict[date, float],
    fx_on: FxLookup,
    end: date,
    start: date | None = None,
) -> list[BenchmarkPoint]:
    """Daily value of a benchmark bought and sold with exactly these flows.

    `closes` are the benchmark's USD closes. Each day prices at the last close on or before it
    (forward-fill) times that day's USD/KRW. A buy adds `amount / price` units; a sell removes
    `amount / price` units, or everything if fewer are held. Flows dated before the first
    available close wait as cash and buy at the first close. Points run from the first flow
    (or `start`, if later) to `end`.
    """
    if not flows:
        return []
    flows = sorted(flows, key=lambda f: f.date)
    dates = sorted(closes)
    first = flows[0].date
    begin = first if start is None else max(start, first)

    units = 0.0
    cash = 0.0
    points: list[BenchmarkPoint] = []
    i = 0
    d = first
    while d <= end:
        k = bisect_right(dates, d)
        close = closes[dates[k - 1]] if k else None
        fx = float(fx_on(d))
        price_krw = close * fx if close is not None else None
        while i < len(flows) and flows[i].date <= d:
            amount = float(flows[i].amount_krw)
            if price_krw is None:
                cash = max(0.0, cash + amount)
            elif amount >= 0:
                units += amount / price_krw
            else:
                units = max(0.0, units - (-amount) / price_krw)
            i += 1
        if price_krw is not None and cash:
            units += cash / price_krw
            cash = 0.0
        if d >= begin:
            value_krw = units * price_krw + cash if price_krw is not None else cash
            value_usd = units * close if close is not None else cash / fx
            points.append(BenchmarkPoint(d, round(value_usd, 2), round(value_krw)))
        d += timedelta(days=1)
    return points


class BenchmarkService:
    def __init__(
        self,
        db: Session,
        market: MarketDataService,
        portfolio: PortfolioService,
        today: Callable[[], date] = date.today,
    ) -> None:
        self.db = db
        self.market = market
        self.portfolio = portfolio
        self.today = today

    def compare(self, symbols: list[str], start: date | None = None) -> BenchmarkComparison:
        """My history and each benchmark fed with my cash flows, on the same daily grid.

        Flows are always replayed from the first trade; `start` only trims the output, so the
        last point is the same whatever range is shown.
        """
        txs = ordered(self.db.scalars(select(Transaction)))
        if not txs:
            return BenchmarkComparison(
                [], [BenchmarkSeries(s, benchmark_name(s), []) for s in symbols]
            )
        today = self.today()
        fetch_from = txs[0].trade_date - LOOKBACK
        fx_on = self.market.usd_krw_lookup(fetch_from)
        flows = cash_flows(txs, fx_on)
        # Network (missing bars) finishes before anything is derived from the ledger.
        closes = {
            s: {b.date: b.close for b in self.market.get_history(s, fetch_from, today)}
            for s in symbols
        }
        series = [
            BenchmarkSeries(s, benchmark_name(s), replay(flows, closes[s], fx_on, today, start))
            for s in symbols
        ]
        return BenchmarkComparison(self.portfolio.history(start), series)
