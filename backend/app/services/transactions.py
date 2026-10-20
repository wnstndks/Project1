from collections.abc import Callable, Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.data.assets import normalize_symbol
from app.db.models import AssetType, CorporateAction, Currency, Transaction
from app.schemas.transactions import TransactionIn
from app.services.corporate_actions import confirmed_events
from app.services.errors import DomainError, NotFoundError
from app.services.ledger import build_positions, trade_fx
from app.services.market_data import MarketDataService, SymbolNotFoundError
from app.services.portfolio import quote_symbol

# Note on transactions created by the screenshot import (lets them be removed together).
IMPORT_NOTE = "스크린샷 가져오기"


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
        """Replace the fields the client sent; fields it omitted (e.g. fx_rate) are kept."""
        tx = self._get(tx_id)
        sent = self._clean(data)
        values = {k: v for k, v in sent.items() if k in data.model_fields_set or k == "symbol"}
        current = {c: getattr(tx, c) for c in sent}
        updated = Transaction(id=tx.id, **(current | values))
        # The edit can break the ledger of the new symbol and, if renamed, the old one.
        self._check_ledger(updated.symbol, adds=[updated], remove=tx)
        if tx.symbol != updated.symbol:
            self._check_ledger(tx.symbol, remove=tx)

        for key, value in values.items():
            setattr(tx, key, value)
        self.db.commit()
        return tx

    def convert_currency(self, symbol: str, to: Currency) -> list[Transaction]:
        """Re-express every trade of a coin in another currency at each trade date's rate.

        For moving a coin recorded in USD (before KRW support) to KRW. Converting to KRW uses
        the recorded fx_rate when there is one, else the market rate, then drops fx_rate (a
        won trade is exact). Converting to USD keeps the KRW cost exact by recording the rate.
        """
        txs = list(self.db.scalars(select(Transaction).where(Transaction.symbol == symbol)))
        if not txs:
            raise NotFoundError(f"No transactions for {symbol}")
        if any(t.asset_type != AssetType.CRYPTO for t in txs) and to == Currency.KRW:
            raise DomainError("Only coins can be held in KRW")
        fx_on = self.market.usd_krw_lookup(min(t.trade_date for t in txs))
        for t in txs:
            current = t.currency or Currency.USD
            if current == to:
                continue
            rate = trade_fx(t, fx_on)
            if to == Currency.KRW:
                t.price = (t.price * rate).quantize(Decimal("0.01"))
                t.fee = (t.fee * rate).quantize(Decimal("0.01"))
                t.fx_rate = None
            else:
                t.price = (t.price / rate).quantize(Decimal("0.00000001"))
                t.fee = (t.fee / rate).quantize(Decimal("0.00000001"))
                t.fx_rate = rate
            t.currency = to
        build_positions(txs, events=confirmed_events(self.db, [symbol]))  # still valid
        self.db.commit()
        return txs

    def delete(self, tx_id: int) -> None:
        tx = self._get(tx_id)
        self._check_ledger(tx.symbol, remove=tx)
        self.db.delete(tx)
        self.db.commit()

    def delete_all(self, only_imported: bool = False) -> int:
        """Delete every transaction (or only screenshot imports). Returns how many.

        Deleting whole symbols keeps every remaining ledger valid, so no per-trade check is
        needed; when everything goes, the derived dividend/split records go too.
        """
        stmt = select(Transaction)
        if only_imported:
            stmt = stmt.where(Transaction.note == IMPORT_NOTE)
        txs = list(self.db.scalars(stmt))
        if only_imported:
            # Removing imported buys must not leave later manual sells overselling.
            for symbol in {t.symbol for t in txs}:
                self._check_ledger(symbol, removes=[t for t in txs if t.symbol == symbol])
        for t in txs:
            self.db.delete(t)
        if not only_imported:
            self.db.execute(delete(CorporateAction))
        self.db.commit()
        return len(txs)

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
        if data.currency == Currency.KRW and data.asset_type != AssetType.CRYPTO:
            raise DomainError("US stocks are recorded in USD; KRW is for coins on Korean exchanges")
        try:
            self.market.get_quote(quote_symbol(symbol, data.currency))
        except SymbolNotFoundError as exc:
            raise DomainError(f"Unknown symbol '{symbol}'") from exc
        return data.model_dump() | {"symbol": symbol}

    def _check_ledger(
        self,
        symbol: str,
        adds: Sequence[Transaction] = (),
        remove: Transaction | None = None,
        removes: Sequence[Transaction] = (),
    ) -> None:
        gone = {t.id for t in removes} | ({remove.id} if remove is not None else set())
        txs = [
            t
            for t in self.db.scalars(select(Transaction).where(Transaction.symbol == symbol))
            if t.id not in gone
        ]
        txs += [t for t in adds if t.symbol == symbol]
        # Confirmed splits count: a post-split sell of 100 shares bought as 10 is valid.
        build_positions(txs, events=confirmed_events(self.db, [symbol]))  # raises OversellError
