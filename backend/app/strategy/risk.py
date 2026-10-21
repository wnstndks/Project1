"""Risk limits shared by the backtest and paper trading (DECISIONS.md D-002, D-003).

Pure functions on floats: amounts are in the base currency (KRW), weights are shares of
equity. The backtest imports these functions as they are, so the order-level rules it
simulates are exactly the ones paper trading (and, one day, real orders) obey:

- no leverage and no short selling (fixed rules, not settings),
- a cap on each buy order and on each symbol's weight,
- a drawdown limit for adopting a strategy, and drawdown/daily-loss triggers for the kill
  switch.

Invalid input (NaN, a negative cash balance) fails closed: weights raise, orders are rejected.
"""

import math
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Literal, Protocol

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from app.config import Settings

# Float noise allowed before a value counts as past a limit, so exactly 20% passes.
EPS = 1e-12
# Orders smaller than this share of equity are treated as nothing left to trade.
MIN_ORDER_SHARE = 1e-9

Side = Literal["buy", "sell"]
OrderStatus = Literal["accepted", "clipped", "rejected"]
BreachCode = Literal["max_drawdown", "daily_loss"]


@dataclass(frozen=True)
class RiskLimits:
    max_drawdown: float = 0.20
    daily_loss_limit: float = 0.03
    max_order_fraction: float = 0.05
    max_order_krw: float | None = None
    max_position_weight: float = 0.20

    @classmethod
    def from_settings(cls, settings: "Settings") -> "RiskLimits":
        cap = settings.risk_max_order_krw
        return cls(
            max_drawdown=float(settings.risk_max_drawdown),
            daily_loss_limit=float(settings.risk_daily_loss_limit),
            max_order_fraction=float(settings.risk_max_order_fraction),
            max_order_krw=float(cap) if cap is not None else None,
            max_position_weight=float(settings.risk_max_position_weight),
        )


@dataclass(frozen=True)
class Book:
    """Cash and the market value of each position, both in the base currency."""

    cash: float
    positions: Mapping[str, float] = field(default_factory=dict)

    @property
    def equity(self) -> float:
        return self.cash + sum(self.positions.values())


@dataclass(frozen=True)
class Order:
    symbol: str
    side: Side
    notional: float


@dataclass(frozen=True)
class OrderDecision:
    order: Order
    status: OrderStatus
    # What may be traded: the request, less if clipped, 0 if rejected.
    notional: float
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Verdict:
    adopted: bool
    reason: str
    max_drawdown: float
    limit: float


@dataclass(frozen=True)
class Trigger:
    date: date
    reason_code: BreachCode
    value: float


def _finite(x: float) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def cap_weights(target: Mapping[str, float], limits: RiskLimits) -> dict[str, float]:
    """Target weights within the limits: no shorts, each at most the symbol cap, total at
    most 1 (scaled down proportionally). Missing or infinite weights raise ValueError."""
    for symbol, w in target.items():
        if not _finite(w):
            raise ValueError(f"Target weight for {symbol} is not a finite number")
    out = {s: min(max(float(w), 0.0), limits.max_position_weight) for s, w in target.items()}
    total = sum(out.values())
    if total > 1.0:
        out = {s: w / total for s, w in out.items()}
    return out


def budgets_from_settings(settings: "Settings") -> dict[str, float]:
    return {
        "stock": float(settings.strategy_budget_stock),
        "crypto": float(settings.strategy_budget_crypto),
    }


class Sized(Protocol):
    """What sizing reads from a signal (a dataclass or a DataFrame row from itertuples)."""

    symbol: str
    asset_class: str
    held_after: bool


def target_weights(
    signals: Iterable[Sized], budgets: Mapping[str, float], limits: RiskLimits
) -> dict[str, float]:
    """Target weights from one decision day's signals (STRATEGIES.md S1, 비중).

    Each asset class's budget is split equally among its symbols held after the signal,
    then `cap_weights` applies the symbol cap and the no-short, no-leverage rules; whatever
    is left stays in cash. Symbols not held get weight 0, so they are sold. A class with no
    budget, or one missing from `budgets`, gets nothing (fail closed).
    """
    budgets = dict(budgets)
    for cls, b in budgets.items():
        if not _finite(b) or b < 0:
            raise ValueError(f"Budget for {cls} must be a non-negative number")
    if sum(budgets.values()) > 1.0 + EPS:
        raise ValueError("Asset class budgets add up to more than 1 (leverage)")
    held: dict[str, list[str]] = {}
    out: dict[str, float] = {}
    for s in signals:
        if s.symbol in out:
            raise ValueError(f"Two signals for {s.symbol} on one day")
        out[s.symbol] = 0.0
        if s.held_after is True:
            held.setdefault(s.asset_class, []).append(s.symbol)
    for cls, symbols in held.items():
        share = budgets.get(cls, 0.0) / len(symbols)
        for symbol in symbols:
            out[symbol] = share
    return cap_weights(out, limits)


def _book_is_valid(book: Book) -> bool:
    values = [book.cash, *book.positions.values()]
    return all(_finite(v) and v >= 0 for v in values) and book.equity > 0


def check_order(
    order: Order, book: Book, limits: RiskLimits, *, fee_rate: float = 0.0
) -> OrderDecision:
    """Pre-trade check of one order against the book it would be applied to.

    Buys are clipped to the per-order cap, the symbol weight cap and the cash on hand
    (fees included), so no buy ever borrows. Sells larger than the position are rejected
    (short selling); the per-order cap does not apply to sells, which only reduce risk.
    """
    if not _finite(fee_rate) or fee_rate < 0:
        raise ValueError("fee_rate must be a non-negative number")

    def reject(*reasons: str) -> OrderDecision:
        return OrderDecision(order, "rejected", 0.0, reasons)

    if not _finite(order.notional) or order.notional <= 0:
        return reject("invalid_notional")
    if not _book_is_valid(book):
        return reject("invalid_book")
    equity = book.equity
    held = book.positions.get(order.symbol, 0.0)

    if order.side == "sell":
        if order.notional > held * (1 + 1e-9):
            return reject("short_sale")
        return OrderDecision(order, "accepted", order.notional)
    if order.side != "buy":
        return reject("invalid_side")

    caps = [(limits.max_order_fraction * equity, "max_order_fraction")]
    if limits.max_order_krw is not None:
        caps.append((limits.max_order_krw, "max_order_krw"))
    caps += [
        (limits.max_position_weight * equity - held, "max_position_weight"),
        (book.cash / (1 + fee_rate), "cash"),
    ]
    allowed, reasons = order.notional, []
    for cap, reason in caps:
        if cap < allowed:
            allowed = cap
            reasons.append(reason)
    if allowed <= MIN_ORDER_SHARE * equity:
        return reject(*reasons)
    return OrderDecision(order, "clipped" if reasons else "accepted", allowed, tuple(reasons))


def plan_rebalance(
    book: Book, target: Mapping[str, float], limits: RiskLimits, *, min_notional: float = 0.0
) -> list[Order]:
    """Unchecked orders from `book` to the capped `target` weights, sells first so their
    proceeds can fund the buys. A position whose target is 0 is sold in full, however small;
    other changes up to `min_notional` are skipped."""
    weights = cap_weights(target, limits)
    equity = book.equity
    symbols = sorted(set(book.positions) | set(weights))
    sells: list[Order] = []
    buys: list[Order] = []
    for s in symbols:
        held = book.positions.get(s, 0.0)
        delta = weights.get(s, 0.0) * equity - held
        if weights.get(s, 0.0) == 0.0 and held > 0:
            sells.append(Order(s, "sell", held))
        elif delta < -min_notional and delta < 0:
            sells.append(Order(s, "sell", -delta))
        elif delta > min_notional and delta > 0:
            buys.append(Order(s, "buy", delta))
    return sells + buys


def apply_decision(book: Book, decision: OrderDecision, *, fee_rate: float = 0.0) -> Book:
    """The book after the approved part of an order is filled at its notional, fee paid in
    cash. Fully sold positions disappear."""
    n = decision.notional
    if n <= 0:
        return book
    s = decision.order.symbol
    positions = dict(book.positions)
    if decision.order.side == "sell":
        cash = book.cash + n * (1 - fee_rate)
        left = positions.get(s, 0.0) - n
        if left <= MIN_ORDER_SHARE * max(book.equity, 1.0):
            positions.pop(s, None)
        else:
            positions[s] = left
    else:
        cash = book.cash - n * (1 + fee_rate)
        positions[s] = positions.get(s, 0.0) + n
    return Book(cash, positions)


def rebalance_orders(
    book: Book,
    target: Mapping[str, float],
    limits: RiskLimits,
    *,
    fee_rate: float | Callable[[Order], float] = 0.0,
    min_notional: float = 0.0,
    trade_only: Collection[str] | None = None,
) -> list[OrderDecision]:
    """Checked orders that move `book` toward `target` weights under the limits.

    Each order of `plan_rebalance` goes through `check_order` against the book as updated by
    the orders before it, the same sequence paper trading follows through `execution`.
    `fee_rate` may be one rate or a function of the order (costs differ by symbol and side).
    With `trade_only`, orders for other symbols are dropped: positions outside a decision
    keep their drifted weight in `target` and are not traded.
    """
    decisions: list[OrderDecision] = []
    for order in plan_rebalance(book, target, limits, min_notional=min_notional):
        if trade_only is not None and order.symbol not in trade_only:
            continue
        rate = fee_rate(order) if callable(fee_rate) else fee_rate
        d = check_order(order, book, limits, fee_rate=rate)
        decisions.append(d)
        book = apply_decision(book, d, fee_rate=rate)
    return decisions


def max_drawdown(equity: Sequence[float] | pd.Series | np.ndarray) -> float:
    """Largest fall from a running peak, as a positive fraction (0.25 = -25%)."""
    values = np.asarray(equity, dtype=float)
    if values.size == 0:
        return 0.0
    if not np.isfinite(values).all():
        raise ValueError("Equity curve has missing or infinite values")
    peaks = np.maximum.accumulate(values)
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peaks > 0, 1 - values / peaks, 0.0)
    return float(dd.max())


def adopt_strategy(max_drawdown: float, limits: RiskLimits | None = None) -> Verdict:
    """Whether a strategy's drawdown (measured with the kill switch off, D-003) allows it.

    The sign is ignored, so -0.25 and 0.25 mean the same. Exactly the limit passes.
    """
    limit = (limits or RiskLimits()).max_drawdown
    if not _finite(max_drawdown):
        return Verdict(False, "MDD를 계산할 수 없음", float("nan"), limit)
    dd = abs(float(max_drawdown))
    if dd > limit + EPS:
        return Verdict(False, f"MDD {dd:.1%}가 한도 {limit:.0%}를 넘음", dd, limit)
    return Verdict(True, f"MDD {dd:.1%} ≤ 한도 {limit:.0%}", dd, limit)


def _daily_loss(prev: float, cur: float) -> float:
    return 1 - cur / prev if prev > 0 else 0.0


def kill_switch_triggers(equity_curve: pd.Series, limits: RiskLimits) -> list[Trigger]:
    """Dates on which the kill switch would have tripped, for backtest reports.

    Drawdown: the first day past the limit; watching resumes once equity is back at its
    peak. Daily loss: every day that lost more than the limit against the day before.
    """
    curve = equity_curve.astype(float)
    if not np.isfinite(curve.to_numpy()).all():
        raise ValueError("Equity curve has missing or infinite values")
    out: list[Trigger] = []
    peak, in_breach, prev = -math.inf, False, None
    for day, value in curve.items():
        when = day.date() if isinstance(day, pd.Timestamp) else day
        if value >= peak:
            peak, in_breach = value, False
        dd = 1 - value / peak if peak > 0 else 0.0
        if dd > limits.max_drawdown + EPS and not in_breach:
            out.append(Trigger(when, "max_drawdown", dd))
            in_breach = True
        if prev is not None:
            loss = _daily_loss(prev, value)
            if loss > limits.daily_loss_limit + EPS:
                out.append(Trigger(when, "daily_loss", loss))
        prev = value
    return out


def portfolio_breach(equity_curve: pd.Series, limits: RiskLimits) -> Trigger | None:
    """The limit the latest point breaks, if any; drawdown is checked first.

    In operation the curve starts at the last kill switch reset, so a drawdown the user has
    already acknowledged does not trip it again until equity falls further.
    """
    curve = equity_curve.astype(float)
    if curve.empty:
        return None
    if not np.isfinite(curve.to_numpy()).all():
        raise ValueError("Equity curve has missing or infinite values")
    last_day = curve.index[-1]
    when = last_day.date() if isinstance(last_day, pd.Timestamp) else last_day
    last, peak = curve.iloc[-1], curve.max()
    dd = 1 - last / peak if peak > 0 else 0.0
    if dd > limits.max_drawdown + EPS:
        return Trigger(when, "max_drawdown", dd)
    if len(curve) >= 2:
        loss = _daily_loss(curve.iloc[-2], last)
        if loss > limits.daily_loss_limit + EPS:
            return Trigger(when, "daily_loss", loss)
    return None
