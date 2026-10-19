"""Pure ledger math: derive positions from transactions using the moving-average cost method.

USD figures come straight from the trades. KRW figures convert every trade at the USD/KRW
rate of its own trade date, which is how Korean brokers report won P&L: the KRW cost basis
is what was actually spent in won, so KRW P&L includes the currency gain or loss.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.db.models import AssetType, Side, Transaction
from app.services.errors import DomainError

ZERO = Decimal("0")

# USD/KRW rate for a trade date.
FxLookup = Callable[[date], Decimal]


class OversellError(DomainError):
    def __init__(self, symbol: str, trade_date: date, held: Decimal, selling: Decimal) -> None:
        super().__init__(
            f"Cannot sell {selling} {symbol} on {trade_date}: only {held} held at that point"
        )
        self.symbol = symbol


@dataclass
class Position:
    symbol: str
    asset_type: AssetType
    quantity: Decimal = ZERO
    # Total cost of the shares still held, including buy fees.
    cost_basis: Decimal = ZERO
    realized_pnl: Decimal = ZERO
    # Same figures in KRW at each trade date's rate; only tracked when an FX lookup is given.
    cost_basis_krw: Decimal = ZERO
    realized_pnl_krw: Decimal = ZERO
    fees_paid: Decimal = ZERO
    first_trade: date | None = None
    trades: int = field(default=0)

    @property
    def avg_cost(self) -> Decimal:
        return self.cost_basis / self.quantity if self.quantity else ZERO

    @property
    def avg_cost_krw(self) -> Decimal:
        return self.cost_basis_krw / self.quantity if self.quantity else ZERO

    def apply(self, tx: Transaction, fx: Decimal | None = None) -> None:
        self.trades += 1
        self.fees_paid += tx.fee
        if self.first_trade is None:
            self.first_trade = tx.trade_date

        if tx.side == Side.BUY:
            self.quantity += tx.quantity
            spent = tx.quantity * tx.price + tx.fee
            self.cost_basis += spent
            if fx is not None:
                self.cost_basis_krw += spent * fx
            return

        if tx.quantity > self.quantity:
            raise OversellError(tx.symbol, tx.trade_date, self.quantity, tx.quantity)
        share = tx.quantity / self.quantity
        released_cost = self.avg_cost * tx.quantity
        proceeds = tx.quantity * tx.price - tx.fee
        self.realized_pnl += proceeds - released_cost
        if fx is not None:
            released_krw = self.cost_basis_krw * share
            self.realized_pnl_krw += proceeds * fx - released_krw
            self.cost_basis_krw -= released_krw
        self.quantity -= tx.quantity
        # Avoid leaving rounding dust once everything is sold.
        if self.quantity == ZERO:
            self.cost_basis = self.cost_basis_krw = ZERO
        else:
            self.cost_basis -= released_cost


def ordered(transactions: Iterable[Transaction]) -> list[Transaction]:
    """Chronological order; same-day trades keep insertion order, with buys before sells."""
    return sorted(
        transactions, key=lambda t: (t.trade_date, 0 if t.side == Side.BUY else 1, t.id or 0)
    )


def build_positions(
    transactions: Iterable[Transaction],
    as_of: date | None = None,
    fx_on: FxLookup | None = None,
) -> dict[str, Position]:
    """Replay the ledger. Raises OversellError if any sell exceeds the quantity held."""
    positions: dict[str, Position] = {}
    for tx in ordered(transactions):
        if as_of is not None and tx.trade_date > as_of:
            break
        pos = positions.setdefault(tx.symbol, Position(tx.symbol, tx.asset_type))
        pos.apply(tx, fx_on(tx.trade_date) if fx_on else None)
    return positions
