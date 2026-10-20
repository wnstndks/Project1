"""Pure ledger math: derive positions from transactions using the moving-average cost method.

Each trade is in its own currency (USD for stocks, KRW for coins bought on Upbit). The other
currency is derived at that trade date's USD/KRW rate, which is how Korean brokers report:
the KRW cost basis is what was actually spent in won, so KRW P&L includes the currency
gain or loss. A position may not mix currencies.
"""

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.data.provider import split_fraction
from app.db.models import (
    ActionKind,
    AssetType,
    CorporateAction,
    Currency,
    Side,
    Transaction,
)
from app.services.errors import DomainError

ZERO = Decimal("0")
# US tax withheld from dividends paid to Korean residents (Korea-US tax treaty rate).
WITHHOLDING_TAX = Decimal("0.15")
# Quantities are entered with up to 8 decimals (schemas/transactions.py).
QTY_STEP = Decimal("1e-8")

# USD/KRW rate for a trade date.
FxLookup = Callable[[date], Decimal]


class OversellError(DomainError):
    def __init__(self, symbol: str, trade_date: date, held: Decimal, selling: Decimal) -> None:
        super().__init__(
            f"Cannot sell {selling} {symbol} on {trade_date}: only {held} held at that point"
        )
        self.symbol = symbol


class MixedCurrencyError(DomainError):
    pass


@dataclass
class Position:
    symbol: str
    asset_type: AssetType
    # Currency the position trades in; set by its first trade.
    currency: Currency | None = None
    quantity: Decimal = ZERO
    # Total cost of the shares still held, including buy fees.
    cost_basis: Decimal = ZERO
    realized_pnl: Decimal = ZERO
    # KRW figures. For KRW trades these are exact; for USD trades they use the trade date's
    # rate. The derived currency is only tracked when an FX lookup is given.
    cost_basis_krw: Decimal = ZERO
    realized_pnl_krw: Decimal = ZERO
    # Cash dividends after US withholding (confirmed events only).
    dividends: Decimal = ZERO
    dividends_krw: Decimal = ZERO
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
        currency = tx.currency or Currency.USD
        # A flat position can restart in another currency (e.g. sold on Binance in USD,
        # later bought on Upbit in KRW). An open one cannot mix.
        if self.currency is None or self.quantity == ZERO:
            self.currency = currency
        elif currency != self.currency:
            raise MixedCurrencyError(
                f"{tx.symbol} is currently held in {self.currency}, so a {currency} trade "
                "cannot be mixed in. Convert the existing trades on the asset page, "
                "or close the position first"
            )
        self.trades += 1
        self.fees_paid += tx.fee
        if self.first_trade is None:
            self.first_trade = tx.trade_date

        def in_usd_krw(native: Decimal) -> tuple[Decimal | None, Decimal | None]:
            if currency == Currency.KRW:
                return (native / fx if fx else None), native
            return native, (native * fx if fx is not None else None)

        if tx.side == Side.BUY:
            self.quantity += tx.quantity
            usd, krw = in_usd_krw(tx.quantity * tx.price + tx.fee)
            if usd is not None:
                self.cost_basis += usd
            if krw is not None:
                self.cost_basis_krw += krw
            return

        if tx.quantity > self.quantity:
            raise OversellError(tx.symbol, tx.trade_date, self.quantity, tx.quantity)
        share = tx.quantity / self.quantity
        released_usd = self.cost_basis * share
        released_krw = self.cost_basis_krw * share
        usd, krw = in_usd_krw(tx.quantity * tx.price - tx.fee)
        if usd is not None:
            self.realized_pnl += usd - released_usd
        if krw is not None:
            self.realized_pnl_krw += krw - released_krw
        self.quantity -= tx.quantity
        # Avoid leaving rounding dust once everything is sold.
        if self.quantity == ZERO:
            self.cost_basis = self.cost_basis_krw = ZERO
        else:
            self.cost_basis -= released_usd
            self.cost_basis_krw -= released_krw

    def apply_action(self, action: CorporateAction, fx: Decimal | None = None) -> None:
        """Apply a confirmed split or dividend at the start of its ex-date."""
        if self.quantity == ZERO:
            return
        if action.kind == ActionKind.SPLIT:
            # Same money invested, more shares: the average cost falls by the ratio.
            self.quantity = split_quantity(self.quantity, action.value)
            return
        net = net_dividend(self.quantity, action)
        self.dividends += net
        if fx is not None:
            self.dividends_krw += net * fx


def split_quantity(quantity: Decimal, ratio: Decimal) -> Decimal:
    """Shares after a split, exact to the 8 decimals quantities are entered with."""
    f = split_fraction(ratio)
    return (quantity * f.numerator / f.denominator).quantize(QTY_STEP)


def net_dividend(quantity: Decimal, action: CorporateAction) -> Decimal:
    rate = action.withholding if action.withholding is not None else WITHHOLDING_TAX
    return quantity * action.value * (1 - rate)


def trade_fx(tx: Transaction, fx_on: FxLookup) -> Decimal:
    """The rate actually paid if recorded on the trade, else the market rate that day."""
    return tx.fx_rate if tx.fx_rate is not None else fx_on(tx.trade_date)


def ordered(transactions: Iterable[Transaction]) -> list[Transaction]:
    """Chronological order. Same-day trades follow `seq`, then entry order (id).

    Unsaved trades (no id yet) sort after saved ones from the same day, in the given order.
    A same-day sell-then-buy round trip therefore realizes P&L against the earlier cost.
    """
    return sorted(
        transactions,
        key=lambda t: (t.trade_date, t.seq or 0, t.id if t.id is not None else math.inf),
    )


def timeline(
    transactions: Iterable[Transaction], events: Iterable[CorporateAction] = ()
) -> list[Transaction | CorporateAction]:
    """Trades and confirmed corporate actions in replay order.

    An action takes effect at the start of its ex-date, before that day's trades. A dividend
    sharing its ex-date with a split is paid on the pre-split shares.
    """
    trades = ordered(transactions)
    items: list[tuple[tuple, Transaction | CorporateAction]] = [
        ((e.ex_date, 0, e.kind != ActionKind.DIVIDEND, i), e) for i, e in enumerate(events)
    ]
    items += [((t.trade_date, 1, 0, i), t) for i, t in enumerate(trades)]
    return [item for _, item in sorted(items, key=lambda p: p[0])]


def build_positions(
    transactions: Iterable[Transaction],
    as_of: date | None = None,
    fx_on: FxLookup | None = None,
    events: Iterable[CorporateAction] = (),
) -> dict[str, Position]:
    """Replay the ledger. Raises OversellError if any sell exceeds the quantity held."""
    positions: dict[str, Position] = {}
    for item in timeline(transactions, events):
        if isinstance(item, CorporateAction):
            if as_of is not None and item.ex_date > as_of:
                break
            pos = positions.get(item.symbol)
            if pos is not None:
                pos.apply_action(item, fx_on(item.ex_date) if fx_on else None)
            continue
        if as_of is not None and item.trade_date > as_of:
            break
        pos = positions.setdefault(item.symbol, Position(item.symbol, item.asset_type))
        pos.apply(item, trade_fx(item, fx_on) if fx_on else None)
    return positions
