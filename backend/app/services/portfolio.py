"""Portfolio valuation: combines ledger positions with market prices and the USD/KRW rate."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.assets import CRYPTO_ASSETS, UPBIT_MARKETS
from app.data.provider import Quote
from app.db.models import AssetType, CorporateAction, Currency, Transaction
from app.services.corporate_actions import confirmed_events, split_events
from app.services.ledger import ZERO, Position, build_positions, ordered, timeline, trade_fx
from app.services.market_data import MarketDataService

HUNDRED = Decimal("100")


def _dec(x: float) -> Decimal:
    return Decimal(str(x))


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    return (part / whole * HUNDRED) if whole else ZERO


def quote_symbol(symbol: str, currency: Currency | None) -> str:
    """Where a position is priced: coins held in KRW use their Upbit KRW market."""
    if currency == Currency.KRW and symbol in UPBIT_MARKETS:
        return UPBIT_MARKETS[symbol]
    return symbol


@dataclass
class Holding:
    symbol: str
    name: str
    asset_type: AssetType
    currency: Currency
    quantity: Decimal
    avg_cost: Decimal
    cost_basis: Decimal
    price: Decimal
    price_as_of: datetime
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pct: Decimal
    realized_pnl: Decimal
    dividends: Decimal
    # KRW: cost at each trade date's rate, value at today's rate (includes FX gain/loss).
    avg_cost_krw: Decimal
    cost_basis_krw: Decimal
    price_krw: Decimal
    market_value_krw: Decimal
    unrealized_pnl_krw: Decimal
    unrealized_pct_krw: Decimal
    realized_pnl_krw: Decimal
    weight: Decimal = ZERO


@dataclass
class Allocation:
    asset_type: AssetType
    market_value: Decimal
    market_value_krw: Decimal
    weight: Decimal


@dataclass
class Summary:
    market_value: Decimal
    market_value_krw: Decimal
    cost_basis: Decimal
    unrealized_pnl: Decimal
    unrealized_pct: Decimal
    realized_pnl: Decimal
    # Dividends after withholding; included in total_pnl.
    dividends: Decimal
    dividends_krw: Decimal
    total_pnl: Decimal
    cost_basis_krw: Decimal
    unrealized_pnl_krw: Decimal
    unrealized_pct_krw: Decimal
    realized_pnl_krw: Decimal
    total_pnl_krw: Decimal
    # Part of the KRW unrealized P&L caused by USD/KRW moving since purchase.
    fx_pnl_krw: Decimal
    usd_krw: Decimal
    allocation: list[Allocation]
    holdings_count: int


@dataclass
class HistoryPoint:
    date: date
    market_value: float
    market_value_krw: float
    cost_basis: float
    cost_basis_krw: float


class PortfolioService:
    def __init__(
        self, db: Session, market: MarketDataService, today: Callable[[], date] = date.today
    ) -> None:
        self.db = db
        self.market = market
        self.today = today

    def holdings(self) -> list[Holding]:
        return self._holdings(self._positions())

    def _positions(self) -> dict[str, Position]:
        txs = self._transactions()
        if not txs:
            return {}
        fx_on = self.market.usd_krw_lookup(min(t.trade_date for t in txs))
        return build_positions(txs, fx_on=fx_on, events=confirmed_events(self.db))

    def _holdings(self, positions: dict[str, Position]) -> list[Holding]:
        open_positions = [p for p in positions.values() if p.quantity > ZERO]
        if not open_positions:
            return []
        qsyms = {p.symbol: quote_symbol(p.symbol, p.currency) for p in open_positions}
        quotes = self.market.get_quotes(list(qsyms.values()))
        fx = _dec(self.market.usd_krw().price)
        holdings = [self._value(p, quotes[qsyms[p.symbol]], fx) for p in open_positions]
        total = sum((h.market_value for h in holdings), ZERO)
        for h in holdings:
            h.weight = _pct(h.market_value, total)
        return sorted(holdings, key=lambda h: h.market_value, reverse=True)

    def summary(self) -> Summary:
        positions = self._positions()
        holdings = self._holdings(positions)
        fx = _dec(self.market.usd_krw().price)

        def total(attr: str) -> Decimal:
            return sum((getattr(h, attr) for h in holdings), ZERO)

        market_value, cost_basis = total("market_value"), total("cost_basis")
        value_krw, cost_krw = total("market_value_krw"), total("cost_basis_krw")
        unrealized = market_value - cost_basis
        unrealized_krw = value_krw - cost_krw
        # Realized P&L also counts positions that have been fully sold.
        realized = sum((p.realized_pnl for p in positions.values()), ZERO)
        realized_krw = sum((p.realized_pnl_krw for p in positions.values()), ZERO)
        dividends = sum((p.dividends for p in positions.values()), ZERO)
        dividends_krw = sum((p.dividends_krw for p in positions.values()), ZERO)

        allocation = []
        for asset_type in AssetType:
            mine = [h for h in holdings if h.asset_type == asset_type]
            value = sum((h.market_value for h in mine), ZERO)
            value_krw_t = sum((h.market_value_krw for h in mine), ZERO)
            allocation.append(Allocation(asset_type, value, value_krw_t, _pct(value, market_value)))

        return Summary(
            market_value=market_value,
            market_value_krw=value_krw,
            cost_basis=cost_basis,
            unrealized_pnl=unrealized,
            unrealized_pct=_pct(unrealized, cost_basis),
            realized_pnl=realized,
            dividends=dividends,
            dividends_krw=dividends_krw,
            total_pnl=unrealized + realized + dividends,
            cost_basis_krw=cost_krw,
            unrealized_pnl_krw=unrealized_krw,
            unrealized_pct_krw=_pct(unrealized_krw, cost_krw),
            realized_pnl_krw=realized_krw,
            total_pnl_krw=unrealized_krw + realized_krw + dividends_krw,
            fx_pnl_krw=self._fx_pnl_krw(holdings, fx),
            usd_krw=fx,
            allocation=allocation,
            holdings_count=len(holdings),
        )

    def history(self, start: date | None = None) -> list[HistoryPoint]:
        """Daily portfolio value. Prices and FX are forward-filled over non-trading days."""
        txs = ordered(self._transactions())
        if not txs:
            return []
        today = self.today()
        first = txs[0].trade_date
        start = max(start or first, first)
        # Look back a little so the first day has a previous close to forward-fill from.
        fetch_from = first - timedelta(days=7)

        currency = {}
        for t in txs:
            currency.setdefault(t.symbol, t.currency or Currency.USD)
        # KRW coins are valued at Upbit KRW closes, everything else at USD closes.
        closes = {
            sym: {
                b.date: b.close
                for b in self.market.get_history(quote_symbol(sym, cur), fetch_from, today)
            }
            for sym, cur in currency.items()
        }
        fx_on = self.market.usd_krw_lookup(fetch_from)

        events = timeline(txs, confirmed_events(self.db))
        # The provider's closes are split-adjusted back in time; restore the price actually
        # traded on each day so pre-split quantities are valued correctly.
        splits: dict[str, list[tuple[date, Decimal]]] = {}
        for e in split_events(self.db, list(currency)):
            splits.setdefault(e.symbol, []).append((e.ex_date, e.value))

        def unadjust(sym: str, d: date) -> float:
            factor = Decimal("1")
            for ex_date, ratio in splits.get(sym, ()):
                if ex_date > d:
                    factor *= ratio
            return float(factor)

        positions: dict[str, Position] = {}
        last_price: dict[str, float] = {}
        points: list[HistoryPoint] = []
        i = 0
        d = fetch_from
        while d <= today:
            for sym, series in closes.items():
                if d in series:
                    last_price[sym] = series[d] * unadjust(sym, d)
            while i < len(events):
                item = events[i]
                when = item.ex_date if isinstance(item, CorporateAction) else item.trade_date
                if when > d:
                    break
                if isinstance(item, CorporateAction):
                    if item.symbol in positions:
                        positions[item.symbol].apply_action(item, fx_on(item.ex_date))
                else:
                    pos = positions.setdefault(item.symbol, Position(item.symbol, item.asset_type))
                    pos.apply(item, trade_fx(item, fx_on))
                i += 1

            if d >= start:
                fx = float(fx_on(d))
                value = value_krw = 0.0
                for sym, pos in positions.items():
                    if pos.quantity == ZERO:
                        continue
                    krw = pos.currency == Currency.KRW
                    # Before the first bar arrives, value the position at its cost.
                    fallback = pos.avg_cost_krw if krw else pos.avg_cost
                    native = float(pos.quantity) * last_price.get(sym, float(fallback))
                    value += native / fx if krw else native
                    value_krw += native if krw else native * fx
                held = positions.values()
                points.append(
                    HistoryPoint(
                        date=d,
                        market_value=round(value, 2),
                        market_value_krw=round(value_krw),
                        cost_basis=round(float(sum(p.cost_basis for p in held)), 2),
                        # Fixed at each buy date's rate, so it only moves on trade days.
                        cost_basis_krw=round(float(sum(p.cost_basis_krw for p in held))),
                    )
                )
            d += timedelta(days=1)
        return points

    def _value(self, p: Position, quote: Quote, fx: Decimal) -> Holding:
        if p.currency == Currency.KRW:
            price_krw = _dec(quote.price)
            price = price_krw / fx
        else:
            price = _dec(quote.price)
            price_krw = price * fx
        market_value = p.quantity * price
        market_value_krw = p.quantity * price_krw
        unrealized = market_value - p.cost_basis
        unrealized_krw = market_value_krw - p.cost_basis_krw
        return Holding(
            symbol=p.symbol,
            name=CRYPTO_ASSETS.get(p.symbol, p.symbol),
            asset_type=p.asset_type,
            currency=p.currency or Currency.USD,
            quantity=p.quantity,
            avg_cost=p.avg_cost,
            cost_basis=p.cost_basis,
            price=price,
            price_as_of=quote.as_of,
            market_value=market_value,
            unrealized_pnl=unrealized,
            unrealized_pct=_pct(unrealized, p.cost_basis),
            realized_pnl=p.realized_pnl,
            dividends=p.dividends,
            avg_cost_krw=p.avg_cost_krw,
            cost_basis_krw=p.cost_basis_krw,
            price_krw=price_krw,
            market_value_krw=market_value_krw,
            unrealized_pnl_krw=unrealized_krw,
            unrealized_pct_krw=_pct(unrealized_krw, p.cost_basis_krw),
            realized_pnl_krw=p.realized_pnl_krw,
        )

    @staticmethod
    def _fx_pnl_krw(holdings: list[Holding], fx: Decimal) -> Decimal:
        """Part of the KRW P&L caused by USD/KRW moving since purchase.

        Only USD positions carry currency risk; a coin bought in won has none.
        """
        usd = [h for h in holdings if h.currency == Currency.USD]
        unrealized_krw = sum((h.unrealized_pnl_krw for h in usd), ZERO)
        unrealized_usd = sum((h.unrealized_pnl for h in usd), ZERO)
        return unrealized_krw - unrealized_usd * fx

    def _transactions(self) -> list[Transaction]:
        return list(self.db.scalars(select(Transaction)))
