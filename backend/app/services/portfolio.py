"""Portfolio valuation: combines ledger positions with market prices and the USD/KRW rate."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.assets import CRYPTO_ASSETS
from app.data.provider import Quote
from app.db.models import AssetType, Transaction
from app.services.ledger import ZERO, Position, build_positions, ordered, trade_fx
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
        return build_positions(txs, fx_on=fx_on)

    def _holdings(self, positions: dict[str, Position]) -> list[Holding]:
        open_positions = [p for p in positions.values() if p.quantity > ZERO]
        if not open_positions:
            return []
        quotes = self.market.get_quotes([p.symbol for p in open_positions])
        fx = _dec(self.market.usd_krw().price)
        holdings = [self._value(p, quotes[p.symbol], fx) for p in open_positions]
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
            total_pnl=unrealized + realized,
            cost_basis_krw=cost_krw,
            unrealized_pnl_krw=unrealized_krw,
            unrealized_pct_krw=_pct(unrealized_krw, cost_krw),
            realized_pnl_krw=realized_krw,
            total_pnl_krw=unrealized_krw + realized_krw,
            fx_pnl_krw=unrealized_krw - unrealized * fx,
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
        fx_on = self.market.usd_krw_lookup(fetch_from)

        positions: dict[str, Position] = {}
        last_price: dict[str, float] = {}
        points: list[HistoryPoint] = []
        i = 0
        d = fetch_from
        while d <= today:
            for sym, series in closes.items():
                if d in series:
                    last_price[sym] = series[d]
            while i < len(txs) and txs[i].trade_date <= d:
                tx = txs[i]
                pos = positions.setdefault(tx.symbol, Position(tx.symbol, tx.asset_type))
                pos.apply(tx, trade_fx(tx, fx_on))
                i += 1

            if d >= start:
                fx = float(fx_on(d))
                value = 0.0
                for sym, pos in positions.items():
                    if pos.quantity == ZERO:
                        continue
                    # Before the first bar arrives, value the position at its cost.
                    price = last_price.get(sym, float(pos.avg_cost))
                    value += float(pos.quantity) * price
                held = positions.values()
                points.append(
                    HistoryPoint(
                        date=d,
                        market_value=round(value, 2),
                        market_value_krw=round(value * fx),
                        cost_basis=round(float(sum(p.cost_basis for p in held)), 2),
                        # Fixed at each buy date's rate, so it only moves on trade days.
                        cost_basis_krw=round(float(sum(p.cost_basis_krw for p in held))),
                    )
                )
            d += timedelta(days=1)
        return points

    def _value(self, p: Position, quote: Quote, fx: Decimal) -> Holding:
        price = _dec(quote.price)
        market_value = p.quantity * price
        unrealized = market_value - p.cost_basis
        unrealized_krw = market_value * fx - p.cost_basis_krw
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
            avg_cost_krw=p.avg_cost_krw,
            cost_basis_krw=p.cost_basis_krw,
            price_krw=price * fx,
            market_value_krw=market_value * fx,
            unrealized_pnl_krw=unrealized_krw,
            unrealized_pct_krw=_pct(unrealized_krw, p.cost_basis_krw),
            realized_pnl_krw=p.realized_pnl_krw,
        )

    def _transactions(self) -> list[Transaction]:
        return list(self.db.scalars(select(Transaction)))
