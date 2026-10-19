"""Portfolio valuation: combines ledger positions with market prices and the USD/KRW rate."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.assets import CRYPTO_ASSETS, FX_USDKRW
from app.data.provider import Quote
from app.db.models import AssetType, Side, Transaction
from app.services.ledger import ZERO, Position, build_positions, ordered
from app.services.market_data import MarketDataService

HUNDRED = Decimal("100")


def _dec(x: float) -> Decimal:
    return Decimal(str(x))


def _pct(part: Decimal, whole: Decimal) -> Decimal:
    return (part / whole * HUNDRED) if whole else ZERO


@dataclass
class Holding:
    symbol: str
    name: str
    asset_type: AssetType
    quantity: Decimal
    avg_cost: Decimal
    cost_basis: Decimal
    price: Decimal
    price_as_of: datetime
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pct: Decimal
    realized_pnl: Decimal
    weight: Decimal = ZERO


@dataclass
class Allocation:
    asset_type: AssetType
    market_value: Decimal
    weight: Decimal


@dataclass
class Summary:
    market_value: Decimal
    market_value_krw: Decimal
    cost_basis: Decimal
    unrealized_pnl: Decimal
    unrealized_pct: Decimal
    realized_pnl: Decimal
    total_pnl: Decimal
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
        return self._holdings(build_positions(self._transactions()))

    def _holdings(self, positions: dict[str, Position]) -> list[Holding]:
        open_positions = [p for p in positions.values() if p.quantity > ZERO]
        quotes = self.market.get_quotes([p.symbol for p in open_positions])
        holdings = [self._value(p, quotes[p.symbol]) for p in open_positions]
        total = sum((h.market_value for h in holdings), ZERO)
        for h in holdings:
            h.weight = _pct(h.market_value, total)
        return sorted(holdings, key=lambda h: h.market_value, reverse=True)

    def summary(self) -> Summary:
        positions = build_positions(self._transactions())
        holdings = self._holdings(positions)
        fx = _dec(self.market.usd_krw().price)

        market_value = sum((h.market_value for h in holdings), ZERO)
        cost_basis = sum((h.cost_basis for h in holdings), ZERO)
        unrealized = market_value - cost_basis
        # Realized P&L also counts positions that have been fully sold.
        realized = sum((p.realized_pnl for p in positions.values()), ZERO)

        allocation = []
        for asset_type in AssetType:
            value = sum((h.market_value for h in holdings if h.asset_type == asset_type), ZERO)
            allocation.append(Allocation(asset_type, value, _pct(value, market_value)))

        return Summary(
            market_value=market_value,
            market_value_krw=market_value * fx,
            cost_basis=cost_basis,
            unrealized_pnl=unrealized,
            unrealized_pct=_pct(unrealized, cost_basis),
            realized_pnl=realized,
            total_pnl=unrealized + realized,
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

        closes = {
            sym: {b.date: b.close for b in self.market.get_history(sym, fetch_from, today)}
            for sym in {t.symbol for t in txs}
        }
        fx_closes = {b.date: b.close for b in self.market.get_history(FX_USDKRW, fetch_from, today)}

        positions: dict[str, Position] = {}
        # KRW actually spent, converted at each buy date's rate (not today's), so the KRW
        # cost line stays flat between trades and FX gains show up as portfolio return.
        cost_krw: dict[str, float] = {}
        last_price: dict[str, float] = {}
        last_fx = next(iter(fx_closes.values()), None) or self.market.usd_krw().price
        points: list[HistoryPoint] = []
        i = 0
        d = fetch_from
        while d <= today:
            for sym, series in closes.items():
                if d in series:
                    last_price[sym] = series[d]
            last_fx = fx_closes.get(d, last_fx)

            while i < len(txs) and txs[i].trade_date <= d:
                tx = txs[i]
                pos = positions.setdefault(tx.symbol, Position(tx.symbol, tx.asset_type))
                held_before = pos.quantity
                pos.apply(tx)
                if tx.side == Side.BUY:
                    spent = float(tx.quantity * tx.price + tx.fee) * last_fx
                    cost_krw[tx.symbol] = cost_krw.get(tx.symbol, 0.0) + spent
                else:
                    cost_krw[tx.symbol] *= float(pos.quantity / held_before)
                i += 1

            if d >= start:
                value = 0.0
                cost = 0.0
                for sym, pos in positions.items():
                    if pos.quantity == ZERO:
                        continue
                    # Before the first bar arrives, value the position at its cost.
                    price = last_price.get(sym, float(pos.avg_cost))
                    value += float(pos.quantity) * price
                    cost += float(pos.cost_basis)
                points.append(
                    HistoryPoint(
                        date=d,
                        market_value=round(value, 2),
                        market_value_krw=round(value * last_fx),
                        cost_basis=round(cost, 2),
                        cost_basis_krw=round(sum(cost_krw.values())),
                    )
                )
            d += timedelta(days=1)
        return points

    def _value(self, p: Position, quote: Quote) -> Holding:
        price = _dec(quote.price)
        market_value = p.quantity * price
        unrealized = market_value - p.cost_basis
        return Holding(
            symbol=p.symbol,
            name=CRYPTO_ASSETS.get(p.symbol, p.symbol),
            asset_type=p.asset_type,
            quantity=p.quantity,
            avg_cost=p.avg_cost,
            cost_basis=p.cost_basis,
            price=price,
            price_as_of=quote.as_of,
            market_value=market_value,
            unrealized_pnl=unrealized,
            unrealized_pct=_pct(unrealized, p.cost_basis),
            realized_pnl=p.realized_pnl,
        )

    def _transactions(self) -> list[Transaction]:
        return list(self.db.scalars(select(Transaction)))
