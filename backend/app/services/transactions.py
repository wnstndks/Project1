from collections.abc import Callable, Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.assets import normalize_symbol
from app.db.models import AssetType, Transaction
from app.schemas.transactions import TransactionIn
from app.services.errors import DomainError, NotFoundError
from app.services.ledger import build_positions, trade_fx
from app.services.market_data import MarketDataService, SymbolNotFoundError


class TransactionService:
    def __init__(
        self, db: Session, market: MarketDataService, today: Callable[[], date] = date.today
    ) -> None:
        self.db = db
        self.market = market
        self.today = today

    def list_all(
        self, symbol: str | None = None, asset_type: AssetType | None = None
    ) -> list[Transaction]:
        stmt = select(Transaction).order_by(Transaction.trade_date.desc(), Transaction.id.desc())
        if symbol:
            stmt = stmt.where(Transaction.symbol == symbol.strip().upper())
        if asset_type:
            stmt = stmt.where(Transaction.asset_type == asset_type)
        return list(self.db.scalars(stmt))

    def trade_date_fx(self, txs: list[Transaction]) -> dict[int, Decimal]:
        """USD/KRW on each transaction's trade date, keyed by transaction id."""
        if not txs:
            return {}
        fx_on = self.market.usd_krw_lookup(min(t.trade_date for t in txs))
        return {t.id: trade_fx(t, fx_on) for t in txs}

    def create(self, data: TransactionIn) -> Transaction:
        return self.create_many([data])[0]

    def create_many(self, items: list[TransactionIn]) -> list[Transaction]:
        """Validate every item first, then insert all of them in one commit (all or nothing)."""
        txs = [Transaction(**self._clean(d)) for d in items]
        for symbol in {t.symbol for t in txs}:
            self._check_ledger(symbol, adds=[t for t in txs if t.symbol == symbol])
        self.db.add_all(txs)
        self.db.commit()
        return txs

    def update(self, tx_id: int, data: TransactionIn) -> Transaction:
        tx = self._get(tx_id)
        values = self._clean(data)
        updated = Transaction(id=tx.id, **values)
        # The edit can break the ledger of the new symbol and, if renamed, the old one.
        self._check_ledger(updated.symbol, adds=[updated], remove=tx)
        if tx.symbol != updated.symbol:
            self._check_ledger(tx.symbol, remove=tx)

        for key, value in values.items():
            setattr(tx, key, value)
        self.db.commit()
        return tx

    def delete(self, tx_id: int) -> None:
        tx = self._get(tx_id)
        self._check_ledger(tx.symbol, remove=tx)
        self.db.delete(tx)
        self.db.commit()

    def _get(self, tx_id: int) -> Transaction:
        tx = self.db.get(Transaction, tx_id)
        if tx is None:
            raise NotFoundError(f"Transaction {tx_id} not found")
        return tx

    def _clean(self, data: TransactionIn) -> dict:
        try:
            symbol = normalize_symbol(data.asset_type, data.symbol)
        except ValueError as exc:
            raise DomainError(str(exc)) from exc
        if data.trade_date > self.today():
            raise DomainError("trade_date cannot be in the future")
        try:
            self.market.get_quote(symbol)
        except SymbolNotFoundError as exc:
            raise DomainError(f"Unknown symbol '{symbol}'") from exc
        return data.model_dump() | {"symbol": symbol}

    def _check_ledger(
        self, symbol: str, adds: Sequence[Transaction] = (), remove: Transaction | None = None
    ) -> None:
        txs = [
            t
            for t in self.db.scalars(select(Transaction).where(Transaction.symbol == symbol))
            if remove is None or t.id != remove.id
        ]
        txs += [t for t in adds if t.symbol == symbol]
        build_positions(txs)  # raises OversellError
