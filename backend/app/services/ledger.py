"""Pure ledger math: derive positions from transactions using the moving-average cost method."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.db.models import AssetType, Side, Transaction
from app.services.errors import DomainError

ZERO = Decimal("0")


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
    fees_paid: Decimal = ZERO
    first_trade: date | None = None
    trades: int = field(default=0)

    @property
    def avg_cost(self) -> Decimal:
        return self.cost_basis / self.quantity if self.quantity else ZERO

    def apply(self, tx: Transaction) -> None:
        self.trades += 1
        self.fees_paid += tx.fee
        if self.first_trade is None:
            self.first_trade = tx.trade_date

        if tx.side == Side.BUY:
            self.quantity += tx.quantity
            self.cost_basis += tx.quantity * tx.price + tx.fee
            return

        if tx.quantity > self.quantity:
            raise OversellError(tx.symbol, tx.trade_date, self.quantity, tx.quantity)
        released_cost = self.avg_cost * tx.quantity
        self.realized_pnl += tx.quantity * tx.price - tx.fee - released_cost
        self.quantity -= tx.quantity
        # Avoid leaving rounding dust once everything is sold.
        self.cost_basis = ZERO if self.quantity == ZERO else self.cost_basis - released_cost


def ordered(transactions: Iterable[Transaction]) -> list[Transaction]:
    """Chronological order; same-day trades keep insertion order, with buys before sells."""
    return sorted(
        transactions, key=lambda t: (t.trade_date, 0 if t.side == Side.BUY else 1, t.id or 0)
    )


def build_positions(
    transactions: Iterable[Transaction], as_of: date | None = None
) -> dict[str, Position]:
    """Replay the ledger. Raises OversellError if any sell exceeds the quantity held."""
    positions: dict[str, Position] = {}
    for tx in ordered(transactions):
        if as_of is not None and tx.trade_date > as_of:
            break
        pos = positions.setdefault(tx.symbol, Position(tx.symbol, tx.asset_type))
        pos.apply(tx)
    return positions
