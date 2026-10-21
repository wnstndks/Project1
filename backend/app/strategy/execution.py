"""The single gate every order passes: kill switch, risk check, then paper or live broker.

Real orders go out only when `AM_LIVE_TRADING` is true, which only the user sets. Until
then every order lands in the paper account, and the live broker is never even built: the
factory is called lazily, after the flag check. No live broker exists yet, so the default
factory raises NotImplementedError.

Broker failures are reported with fixed messages and the exception type only, so a key,
token or account number inside an exception never reaches records, results or logs.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import KillSwitchEvent
from app.strategy.risk import Book, Order, OrderDecision, RiskLimits, check_order

if TYPE_CHECKING:
    from app.config import Settings

log = logging.getLogger(__name__)

REASON_CODES = frozenset(
    {"max_drawdown", "daily_loss", "leverage", "stale_data", "state_unreadable", "manual"}
)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class KillState:
    tripped: bool
    reason_code: str | None = None
    detail: str = ""
    # When the current state began (trip or last reset); None if never touched.
    since: datetime | None = None


class KillSwitch:
    """Kill switch state kept as append-only events in `kill_switch_events`.

    Fail-closed: if the state cannot be read it counts as tripped. Once tripped it stays so
    until the user resets it; the system can trip but never reset.
    """

    def __init__(self, db: Session, clock: Callable[[], datetime] = _utcnow) -> None:
        self.db = db
        self.clock = clock

    def state(self) -> KillState:
        try:
            row = self.db.scalars(
                select(KillSwitchEvent).order_by(KillSwitchEvent.id.desc()).limit(1)
            ).first()
        except Exception as exc:  # noqa: BLE001 - any failure must stop trading
            log.warning(
                "Kill switch state unreadable (%s); treating as tripped", type(exc).__name__
            )
            return KillState(True, "state_unreadable", "상태를 읽을 수 없음")
        if row is None:
            return KillState(False)
        if row.action == "reset":
            return KillState(False, since=row.at)
        return KillState(True, row.reason_code, row.detail, row.at)

    def last_trip_at(self) -> datetime | None:
        """When the switch last tripped (even if reset since); datetime.max if unreadable,
        so anything approved earlier counts as overtaken by a trip (fail closed)."""
        try:
            return self.db.scalar(
                select(func.max(KillSwitchEvent.at)).where(KillSwitchEvent.action == "trip")
            )
        except Exception as exc:  # noqa: BLE001 - any failure must stop trading
            log.warning("Kill switch history unreadable (%s)", type(exc).__name__)
            return datetime.max

    def trip(self, reason_code: str, detail: str = "", actor: str = "system") -> None:
        if reason_code not in REASON_CODES:
            raise ValueError(f"Unknown kill switch reason '{reason_code}'")
        if actor not in ("system", "user"):
            raise ValueError("actor must be 'system' or 'user'")
        self._append("trip", reason_code, detail, actor)
        log.warning("Kill switch tripped: %s %s", reason_code, detail)

    def reset(self, actor: str, detail: str = "") -> None:
        """Resume trading. Only the user may do this (from the app, never automatically)."""
        if actor != "user":
            raise PermissionError("Only the user can reset the kill switch")
        self._append("reset", "manual", detail, actor)

    def _append(self, action: str, reason_code: str, detail: str, actor: str) -> None:
        self.db.add(
            KillSwitchEvent(
                at=self.clock(),
                action=action,
                reason_code=reason_code,
                detail=detail[:200],
                actor=actor,
            )
        )
        self.db.commit()


@dataclass(frozen=True)
class BrokerAck:
    venue: Literal["paper", "live"]
    ref: str


class Broker(Protocol):
    def submit(self, order: Order) -> BrokerAck: ...


def live_broker_unavailable() -> Broker:
    raise NotImplementedError("No live broker is implemented")


@dataclass(frozen=True)
class ExecResult:
    status: Literal["halted", "rejected", "submitted", "failed"]
    # Fixed text for records and the UI; never an exception message.
    reason: str
    decision: OrderDecision | None = None
    ack: BrokerAck | None = None


def execute(
    order: Order,
    *,
    book: Book,
    settings: "Settings",
    kill_switch: KillSwitch,
    limits: RiskLimits,
    paper: Broker,
    live_factory: Callable[[], Broker] = live_broker_unavailable,
    fee_rate: float = 0.0,
) -> ExecResult:
    state = kill_switch.state()
    if state.tripped:
        return ExecResult("halted", f"킬스위치 발동 중({state.reason_code})")

    decision = check_order(order, book, limits, fee_rate=fee_rate)
    if decision.status == "rejected":
        return ExecResult("rejected", "한도 위반: " + ", ".join(decision.reasons), decision)
    approved = Order(order.symbol, order.side, decision.notional)

    # Identity check: only a real boolean True set by the user opens the live path.
    live = settings.live_trading is True
    venue = "live" if live else "paper"
    try:
        broker = live_factory() if live else paper
        ack = broker.submit(approved)
    except NotImplementedError:
        return ExecResult("failed", "실매매 브로커가 없음", decision)
    except Exception as exc:  # noqa: BLE001 - reported without its message, which may hold secrets
        log.warning("Order submission to %s broker failed (%s)", venue, type(exc).__name__)
        return ExecResult("failed", "주문 전송 실패", decision)
    return ExecResult("submitted", "", decision, ack)
