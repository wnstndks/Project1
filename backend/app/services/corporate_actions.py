"""Stock splits and dividends: detected from market data, applied once the user confirms.

Dividends are recorded when the user held shares the day before the ex-date. Splits are
recorded for any symbol traded before them: even when nothing was held on the ex-date,
history needs them to undo the provider's split adjustment for earlier holding periods, so
those are confirmed straight away (they cannot change the ledger). Confirmed events are
merged into the ledger replay (`ledger.build_positions(..., events=...)`); detected ones are
shown for review, because the provider's data is not always right (and some brokers handle
fractional split shares differently).
"""

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.data.provider import CorporateEvent, MarketDataError, MarketDataProvider
from app.db.models import ActionKind, ActionStatus, AssetType, CorporateAction, Transaction
from app.services.errors import DomainError, NotFoundError
from app.services.ledger import (
    WITHHOLDING_TAX,
    ZERO,
    build_positions,
    net_dividend,
    split_quantity,
)
from app.services.market_data import drop_cached_bars

log = logging.getLogger(__name__)

VALUE_TOLERANCE = Decimal("0.001")  # relative change in a provider amount that counts
CHECK_TTL = 6 * 3600.0  # seconds between provider look-ups per symbol
_last_checked: dict[str, float] = {}
_lock = threading.Lock()


def confirmed_events(db: Session, symbols: list[str] | None = None) -> list[CorporateAction]:
    stmt = select(CorporateAction).where(CorporateAction.status == ActionStatus.CONFIRMED)
    if symbols is not None:
        stmt = stmt.where(CorporateAction.symbol.in_(symbols))
    return list(db.scalars(stmt))


def split_events(db: Session, symbols: list[str]) -> list[CorporateAction]:
    """Splits the provider's prices are adjusted for and the user's trades are not.

    Pending ones count too: the provider has already adjusted for them. Ignored ones do not,
    because a user ignores a split whose trades were already entered in post-split shares
    and prices, which then match the adjusted series as they are.
    """
    return list(
        db.scalars(
            select(CorporateAction).where(
                CorporateAction.symbol.in_(symbols),
                CorporateAction.kind == ActionKind.SPLIT,
                CorporateAction.status != ActionStatus.IGNORED,
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
    # Split: shares after. Dividend: estimated cash after withholding, in USD.
    effect: Decimal
    withholding: Decimal


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
        """Look up actions for traded US stocks and record new ones.

        Each symbol is reserved under the lock before its look-up, so concurrent requests do
        not fetch it twice; a failed look-up releases it so the next request retries.
        """
        by_symbol = self._stock_trades()
        now = self.clock()
        due = []
        with _lock:
            for symbol in by_symbol:
                if force or now - _last_checked.get(symbol, -CHECK_TTL) >= CHECK_TTL:
                    _last_checked[symbol] = now
                    due.append(symbol)
        fetched: dict[str, list[CorporateEvent]] = {}
        if due:
            # Network before any write; one request per symbol, in parallel.
            with ThreadPoolExecutor(max_workers=min(8, len(due))) as pool:
                results = pool.map(self._fetch, due)
            for symbol, events in zip(due, results, strict=True):
                if events is None:
                    with _lock:
                        _last_checked.pop(symbol, None)
                else:
                    fetched[symbol] = events

        today = self.today()
        now_dt = datetime.now()
        for symbol, events in fetched.items():
            txs = by_symbol[symbol]
            known = {
                (a.ex_date, a.kind): a
                for a in self.db.scalars(
                    select(CorporateAction).where(CorporateAction.symbol == symbol)
                )
            }
            rate = self._withholding(known.values())
            first = min(t.trade_date for t in txs)
            new_split = False
            for ev in events:
                kind = ActionKind(ev.kind)
                existing = known.get((ev.date, kind))
                if existing is not None:
                    self._refresh(existing, ev.value)
                    continue
                if not (first < ev.date <= today):
                    continue
                held = self._shares_before(symbol, txs, ev.date) > ZERO
                if kind == ActionKind.DIVIDEND and not held:
                    continue
                # A concurrent forced detect may have inserted it already.
                self.db.execute(
                    sqlite_insert(CorporateAction)
                    .values(
                        symbol=symbol,
                        ex_date=ev.date,
                        kind=kind,
                        value=ev.value,
                        status=ActionStatus.DETECTED if held else ActionStatus.CONFIRMED,
                        detected_at=now_dt,
                        withholding=rate,
                    )
                    .on_conflict_do_nothing()
                )
                new_split |= kind == ActionKind.SPLIT
            if new_split:
                # Cached bars may predate the provider's re-adjustment for this split, and
                # history would then undo an adjustment that was never applied.
                drop_cached_bars(self.db, symbol)
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
                split_quantity(shares, a.value)
                if a.kind == ActionKind.SPLIT
                else net_dividend(shares, a)
            )
            rate = a.withholding if a.withholding is not None else WITHHOLDING_TAX
            out.append(
                ActionView(
                    a.id, a.symbol, a.ex_date, a.kind, a.value, a.status, shares, effect, rate
                )
            )
        return out

    def set_status(self, action_id: int, status: ActionStatus) -> CorporateAction:
        action = self.db.get(CorporateAction, action_id)
        if action is None:
            raise NotFoundError(f"Corporate action {action_id} not found")
        # Validate the ledger as it would be with the new status, before saving it: e.g.
        # ignoring a split after recording post-split sells would oversell.
        others = [e for e in confirmed_events(self.db, [action.symbol]) if e.id != action.id]
        events = others + [action] if status == ActionStatus.CONFIRMED else others
        build_positions(self._stock_trades().get(action.symbol, []), events=events)
        action.status = status
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

    def set_withholding(self, symbol: str, rate: Decimal) -> int:
        """Set the withholding rate for every dividend of a symbol, including future ones."""
        if not ZERO <= rate < 1:
            raise DomainError("Withholding rate must be between 0 and 1")
        actions = list(
            self.db.scalars(
                select(CorporateAction).where(
                    CorporateAction.symbol == symbol,
                    CorporateAction.kind == ActionKind.DIVIDEND,
                )
            )
        )
        if not actions:
            raise NotFoundError(f"No dividends recorded for {symbol}")
        for a in actions:
            a.withholding = rate
        self.db.commit()
        return len(actions)

    def _fetch(self, symbol: str) -> list[CorporateEvent] | None:
        try:
            return self.provider.get_actions(symbol)
        except MarketDataError as exc:
            log.warning("Corporate actions look-up failed for %s: %s", symbol, exc)
            return None

    @staticmethod
    def _withholding(actions) -> Decimal:
        """The rate the user chose for this symbol's dividends, else the treaty rate."""
        latest = max(
            (a for a in actions if a.kind == ActionKind.DIVIDEND),
            key=lambda a: a.ex_date,
            default=None,
        )
        return latest.withholding if latest is not None else WITHHOLDING_TAX

    @staticmethod
    def _refresh(action: CorporateAction, value: Decimal) -> None:
        """Follow a corrected provider amount. A confirmed dividend goes back to review;
        confirmed splits are left alone because changing them could break the ledger."""
        # Restated amounts come back rounded ($0.11 after a 3:1 split is 0.036667, which
        # restores to 0.110001): only a real change may unconfirm a dividend.
        if abs(action.value - value) <= max(abs(action.value), abs(value)) * VALUE_TOLERANCE:
            return
        if action.status == ActionStatus.DETECTED:
            action.value = value
        elif action.kind == ActionKind.DIVIDEND and action.status == ActionStatus.CONFIRMED:
            action.value = value
            action.status = ActionStatus.DETECTED

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
