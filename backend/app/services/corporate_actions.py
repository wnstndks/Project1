"""Stock splits and dividends: detected from market data, applied once the user confirms.

Only events on symbols the user held on the ex-date are recorded. Confirmed events are
merged into the ledger replay (`ledger.build_positions(..., events=...)`); detected ones are
shown for review, because the provider's data is not always right (and some brokers handle
fractional split shares differently).
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.provider import MarketDataProvider
from app.db.models import ActionKind, ActionStatus, AssetType, CorporateAction, Transaction
from app.services.errors import DomainError, NotFoundError
from app.services.ledger import WITHHOLDING_TAX, ZERO, build_positions

CHECK_TTL = 6 * 3600.0  # seconds between provider look-ups per symbol
_last_checked: dict[str, float] = {}
_lock = threading.Lock()


def confirmed_events(db: Session, symbols: list[str] | None = None) -> list[CorporateAction]:
    stmt = select(CorporateAction).where(CorporateAction.status == ActionStatus.CONFIRMED)
    if symbols is not None:
        stmt = stmt.where(CorporateAction.symbol.in_(symbols))
    return list(db.scalars(stmt))


def split_events(db: Session, symbols: list[str]) -> list[CorporateAction]:
    """Every known split, whatever its status: the provider's prices are adjusted for all."""
    return list(
        db.scalars(
            select(CorporateAction).where(
                CorporateAction.symbol.in_(symbols), CorporateAction.kind == ActionKind.SPLIT
            )
        )
    )


@dataclass
class ActionView:
    id: int
    symbol: str
    ex_date: date
    kind: ActionKind
    value: Decimal
    status: ActionStatus
    shares_before: Decimal
    # Split: shares after. Dividend: estimated cash after 15% US withholding, in USD.
    effect: Decimal


class CorporateActionService:
    def __init__(
        self,
        db: Session,
        provider: MarketDataProvider,
        today: Callable[[], date] = date.today,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.db = db
        self.provider = provider
        self.today = today
        self.clock = clock

    def detect(self, force: bool = False) -> None:
        """Look up actions for held US stocks and record new ones as detected."""
        by_symbol = self._stock_trades()
        fetched = {}
        now = self.clock()
        for symbol in by_symbol:
            with _lock:
                fresh = now - _last_checked.get(symbol, -CHECK_TTL) < CHECK_TTL
            if fresh and not force:
                continue
            fetched[symbol] = self.provider.get_actions(symbol)  # network: before any write
            with _lock:
                _last_checked[symbol] = now

        today = self.today()
        for symbol, events in fetched.items():
            txs = by_symbol[symbol]
            known = {
                (a.ex_date, a.kind)
                for a in self.db.scalars(
                    select(CorporateAction).where(CorporateAction.symbol == symbol)
                )
            }
            first = min(t.trade_date for t in txs)
            for ev in events:
                if not (first < ev.date <= today) or (ev.date, ev.kind) in known:
                    continue
                if self._shares_before(symbol, txs, ev.date) == ZERO:
                    continue
                self.db.add(
                    CorporateAction(
                        symbol=symbol,
                        ex_date=ev.date,
                        kind=ActionKind(ev.kind),
                        value=ev.value,
                        status=ActionStatus.DETECTED,
                        detected_at=datetime.now(),
                    )
                )
                known.add((ev.date, ev.kind))
        self.db.commit()

    def list_all(self) -> list[ActionView]:
        actions = self.db.scalars(
            select(CorporateAction).order_by(CorporateAction.ex_date.desc())
        ).all()
        trades = self._stock_trades()
        out = []
        for a in actions:
            shares = self._shares_before(a.symbol, trades.get(a.symbol, []), a.ex_date)
            effect = (
                shares * a.value
                if a.kind == ActionKind.SPLIT
                else shares * a.value * (1 - WITHHOLDING_TAX)
            )
            out.append(
                ActionView(a.id, a.symbol, a.ex_date, a.kind, a.value, a.status, shares, effect)
            )
        return out

    def set_status(self, action_id: int, status: ActionStatus) -> CorporateAction:
        action = self.db.get(CorporateAction, action_id)
        if action is None:
            raise NotFoundError(f"Corporate action {action_id} not found")
        previous = action.status
        action.status = status
        txs = self._stock_trades().get(action.symbol, [])
        try:
            # e.g. ignoring a split after recording post-split sells would oversell.
            build_positions(txs, events=confirmed_events(self.db, [action.symbol]))
        except DomainError:
            action.status = previous
            self.db.rollback()
            raise
        self.db.commit()
        return action

    def confirm_all_dividends(self) -> int:
        """Confirm every detected dividend. Dividends never change quantities, so this cannot
        break the ledger; splits are always confirmed one at a time."""
        pending = list(
            self.db.scalars(
                select(CorporateAction).where(
                    CorporateAction.kind == ActionKind.DIVIDEND,
                    CorporateAction.status == ActionStatus.DETECTED,
                )
            )
        )
        for a in pending:
            a.status = ActionStatus.CONFIRMED
        self.db.commit()
        return len(pending)

    def _shares_before(self, symbol: str, txs: list[Transaction], ex_date: date) -> Decimal:
        events = [e for e in confirmed_events(self.db, [symbol]) if e.ex_date < ex_date]
        pos = build_positions(txs, as_of=ex_date - timedelta(days=1), events=events).get(symbol)
        return pos.quantity if pos else ZERO

    def _stock_trades(self) -> dict[str, list[Transaction]]:
        out: dict[str, list[Transaction]] = {}
        for t in self.db.scalars(
            select(Transaction).where(Transaction.asset_type == AssetType.STOCK)
        ):
            out.setdefault(t.symbol, []).append(t)
        return out
