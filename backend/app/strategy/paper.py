"""Paper trading: the daily runner that turns the latest forecast into risk-checked virtual
orders, fills them at the next bar's open and scores every signal once its horizon passes.

    python -m app.strategy.paper run     # signals and orders on the newest final bars
    python -m app.strategy.paper fill    # fill pending orders once the next bar is final
    python -m app.strategy.paper score   # score signals whose target date has passed
    python -m app.strategy.paper gaps    # decision days the runner missed, per class

`--strategy s2` runs S2-1d (exposure by forecast volatility) instead of S1-1w; each
strategy keeps its own records (strategy_id) in the same paper tables.

Nothing here writes to `transactions`: the paper account starts from
AM_PAPER_INITIAL_CAPITAL_KRW and exists only as rows of `paper_signals` (D-009), so real
holdings never change and never appear in the records. Prices come from the strict loader
(`load_daily`, `load_usd_krw`), never from the forecast service (D-011). Every order passes
`execution.execute` with the paper broker; with AM_LIVE_TRADING false the live broker is never
built.

Each run first values the paper account and trips the kill switch when drawdown or a daily
loss since the last reset passed its limit, when the book shows leverage, or when the prices
needed to value it are missing (fail closed). While tripped, signals are still recorded, as
`halted`, and no order is sent.

The arithmetic (fills, account, equity curve, scores) is pure functions at the top of the
file; `PaperTrader` does the I/O.

Two kinds of strategy plug in: held/not-held signals sized by equal shares of the class
budget (S1, `SignalStrategy`), and exposure signals sized by budget times target exposure
(S2, `ExposureStrategy`). An exposure strategy keeps its class state (allowed and committed
exposure) in each record's rationale, so the next run reads it back without a schema change.
"""

import argparse
import logging
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.assets import trades_every_day
from app.data.calendar import last_final_date, next_trading_dates
from app.data.provider import DataUnavailableError
from app.db.models import PaperSignal
from app.forecast.panel import HORIZONS
from app.forecast.universe import CRYPTO_BENCHMARK, STOCK_BENCHMARK, strategy_symbols
from app.strategy.backtest import MIN_TRADE_SHARE, CostModel, instrument
from app.strategy.execution import (
    Broker,
    BrokerAck,
    ExecResult,
    KillSwitch,
    execute,
    live_broker_unavailable,
)
from app.strategy.risk import (
    Book,
    Order,
    RiskLimits,
    apply_decision,
    budgets_from_settings,
    exposure_weights,
    kill_switch_triggers,
    plan_rebalance,
    target_weights,
)

if TYPE_CHECKING:
    from app.config import Settings
    from app.services.market_data import MarketDataService

log = logging.getLogger(__name__)

BENCHMARKS: dict[str, str] = {"stock": STOCK_BENCHMARK, "crypto": CRYPTO_BENCHMARK}
# A pending order whose next bar is still unavailable this many days later is given up.
FILL_EXPIRY_DAYS = 7
# US withholding on dividends (D-008); scores use total return net of it.
DIVIDEND_WITHHOLDING = 0.15
# Extra history loaded before a date so a close is found across weekends and holidays.
LOOKBACK_DAYS = 10
# Inference history: the slowest features look back 252 sessions (about a year).
INFERENCE_LOOKBACK_DAYS = 800

KRW = Decimal("1")
QTY = Decimal("0.00000001")
PRICE = Decimal("0.000001")


@dataclass(frozen=True)
class Costs:
    """One-way costs of an order: fee as a share of the traded amount, slippage against the
    open in basis points (buys pay more, sells get less)."""

    fee_rate: float
    slippage_bps: float


def order_costs(model: CostModel, symbol: str, asset_class: str, side: str) -> Costs:
    """The backtest's cost model split into slippage (moves the fill price) and everything
    else (commission, FX spread, SEC fee: charged as a fee), so a paper fill pays what the
    backtest charges for the same order (D-003)."""
    inst = instrument(symbol, asset_class)
    slip = model.slippage(inst)
    return Costs(model.rate(inst, side) - slip, slip * 1e4)


# --- pure arithmetic ---------------------------------------------------------------------


def fill_price(side: str, open_: float, slippage_bps: float) -> float:
    s = slippage_bps / 1e4
    return open_ * (1 + s) if side == "buy" else open_ * (1 - s)


@dataclass(frozen=True)
class Trade:
    """A filled paper order. Price in the asset's currency (USD), fee in KRW."""

    symbol: str
    side: Literal["buy", "sell"]
    fill_date: date
    quantity: float
    price: float
    fx: float
    fee_krw: float

    @property
    def gross_krw(self) -> float:
        return self.quantity * self.price * self.fx


def _apply(cash: float, qty: dict[str, float], t: Trade) -> float:
    sign = 1.0 if t.side == "buy" else -1.0
    q = qty.get(t.symbol, 0.0) + sign * t.quantity
    if abs(q) > 1e-12:
        qty[t.symbol] = q
    else:
        qty.pop(t.symbol, None)
    return cash - sign * t.gross_krw - t.fee_krw


def account(initial_cash: float, trades: Iterable[Trade]) -> tuple[float, dict[str, float]]:
    """Cash (KRW) and quantity per symbol after the trades."""
    cash, qty = initial_cash, {}
    for t in trades:
        cash = _apply(cash, qty, t)
    return cash, qty


def equity_curve(
    initial_cash: float,
    trades: Sequence[Trade],
    closes: pd.DataFrame,
    fx: pd.Series,
    start: date,
    end: date,
) -> pd.Series:
    """Daily KRW equity over [start, end]: cash plus each position at that day's close.

    `closes` has one column per symbol and `fx` is KRW per dollar; a day without a bar
    carries the last value. Trades count from their fill date. A held symbol without a
    price raises DataUnavailableError: an account that cannot be valued cannot be checked.
    """
    days = pd.date_range(start, end, freq="D")

    def daily(x):
        return x.reindex(x.index.union(days)).sort_index().ffill().reindex(days)

    closes, fx = daily(closes), daily(fx)
    ordered = sorted(trades, key=lambda t: t.fill_date)
    cash, qty, i = initial_cash, {}, 0
    values: list[float] = []
    for day in days:
        while i < len(ordered) and ordered[i].fill_date <= day.date():
            cash = _apply(cash, qty, ordered[i])
            i += 1
        value = cash
        for symbol, q in qty.items():
            price = float(closes[symbol].loc[day]) if symbol in closes else math.nan
            rate = float(fx.loc[day])
            if not (math.isfinite(price) and math.isfinite(rate)):
                raise DataUnavailableError(f"No price to value {symbol} on {day.date()}")
            value += q * price * rate
        values.append(value)
    return pd.Series(values, index=days, dtype=float)


@dataclass(frozen=True)
class PendingOrder:
    key: int
    symbol: str
    side: Literal["buy", "sell"]
    # Approved KRW amount at signal time; a buy spends at most this (fee on top).
    notional_krw: float
    # Sells only: the quantity decided at signal time.
    quantity: float | None
    costs: Costs


@dataclass(frozen=True)
class FillResult:
    key: int
    filled: bool
    quantity: float = 0.0
    price: float = 0.0
    fee_krw: float = 0.0
    # Why it was cut or skipped: cash | nothing_held | "".
    note: str = ""


def fill_orders(
    orders: Sequence[PendingOrder],
    opens: Mapping[str, float],
    fx: float,
    cash: float,
    held: Mapping[str, float],
) -> list[FillResult]:
    """Fill one day's pending orders at that day's open plus slippage.

    Sells go first so their proceeds fund the buys. A sell never exceeds the quantity held;
    a buy never spends more than the cash left (fee included), so the account cannot borrow
    even when the open gapped against the signal's close.
    """
    if not (math.isfinite(fx) and fx > 0):
        raise ValueError("fx must be a positive number")
    held = dict(held)
    out: list[FillResult] = []
    for o in sorted(orders, key=lambda o: (o.side != "sell", o.key)):
        open_ = opens.get(o.symbol, math.nan)
        if not (math.isfinite(open_) and open_ > 0):
            raise ValueError(f"No usable open for {o.symbol}")
        price = fill_price(o.side, open_, o.costs.slippage_bps)
        if o.side == "sell":
            wanted = o.quantity or 0.0
            q = min(wanted, held.get(o.symbol, 0.0))
            if q <= 0:
                out.append(FillResult(o.key, False, note="nothing_held"))
                continue
            gross = q * price * fx
            fee = gross * o.costs.fee_rate
            cash += gross - fee
            held[o.symbol] = held.get(o.symbol, 0.0) - q
            note = "nothing_held" if q < wanted - 1e-12 else ""
        else:
            spend = min(o.notional_krw, max(cash, 0.0) / (1 + o.costs.fee_rate))
            if spend <= 0:
                out.append(FillResult(o.key, False, note="cash"))
                continue
            q = spend / (price * fx)
            fee = spend * o.costs.fee_rate
            cash -= spend + fee
            held[o.symbol] = held.get(o.symbol, 0.0) + q
            note = "cash" if spend < o.notional_krw - 1e-9 else ""
        out.append(FillResult(o.key, True, q, price, fee, note))
    return out


def period_return(index: pd.Series, start: date, end: date) -> float:
    """Return of a price or total-return index from its value on `start` to `end`."""
    return float(index.loc[pd.Timestamp(end)] / index.loc[pd.Timestamp(start)] - 1)


def trade_pnl_krw(t: Trade, exit_price: float, exit_fx: float) -> float:
    """KRW result of a filled order at the target date, after its fee.

    A buy gains what the bought quantity is worth then minus what it cost; a sell gains what
    it fetched minus what the sold quantity would be worth then (the loss it avoided).
    """
    later = t.quantity * exit_price * exit_fx
    if t.side == "buy":
        return later - t.gross_krw - t.fee_krw
    return t.gross_krw - t.fee_krw - later


def _dec(x: float | None, step: Decimal) -> Decimal | None:
    if x is None or not math.isfinite(x):
        return None
    return Decimal(repr(float(x))).quantize(step, rounding=ROUND_HALF_EVEN)


def _float(x: Decimal | None) -> float:
    return float(x) if x is not None else math.nan


def _last_on(series: pd.Series | None, day: date) -> float:
    if series is None:
        return math.nan
    s = series.loc[: pd.Timestamp(day)].dropna()
    return float(s.iloc[-1]) if len(s) else math.nan


# --- strategy and inference interfaces ---------------------------------------------------


class Signal(Protocol):
    """What the paper runner records from a strategy signal (strategy/signals.py)."""

    symbol: str
    asset_class: str
    action: str  # buy | sell | hold | no_edge
    held_after: bool
    confidence: str | None
    rationale: Mapping[str, Any]
    # Exposure strategies only: the share of the class budget to hold, in [0, 1].
    target_exposure: float | None


Sizing = Literal["equal", "exposure"]


class PaperStrategy(Protocol):
    strategy_id: str
    horizon: str
    # Optional attributes, read with defaults: `universe` (symbol -> class, default the
    # S1 strategy universe), `sizing` ("equal") and `min_order_share` (the trader's).

    def is_decision_day(self, asset_class: str, day: date) -> bool: ...

    def signals(
        self,
        rows: pd.DataFrame,
        as_of: Mapping[str, date],
        held: Mapping[str, bool],
        last: Mapping[str, Mapping[str, Any]],
    ) -> Sequence[Signal]:
        """Signals of the classes in `as_of` (class -> decision day) from that day's
        inference rows, given each symbol's held state and its latest recorded rationale."""
        ...


# Inference rows for `symbols`, one per symbol dated at its class's decision day, with the
# forecast columns the strategy reads (OOS column names, see walkforward.py).
Predictor = Callable[[Sequence[str], Mapping[str, date]], pd.DataFrame]


class PaperBroker:
    """Accepts approved orders into the paper account. Nothing leaves the process."""

    def __init__(self) -> None:
        self.orders: list[Order] = []

    def submit(self, order: Order) -> BrokerAck:
        self.orders.append(order)
        return BrokerAck("paper", f"paper:{len(self.orders)}")


@dataclass
class RunReport:
    decided: dict[str, date] = field(default_factory=dict)
    recorded: int = 0
    orders: int = 0
    # Kill switch reason when tripped (now or before this run).
    tripped: str | None = None
    # Fixed text when no signals could be made (never an exception message).
    skipped: str | None = None
    # Per class: decision days between the last record and today's that the runner missed.
    missed: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionGaps:
    """One class's decision days from its first record through the newest final bar: which
    have a record and which the runner missed (a day it did not run, or one it skipped for
    missing data). A missed weekly day delays an exposure increase by a week, which the
    backtest (replaying every day) never sees (verifier N-13). `generated_share` is the
    forward test's success criterion 3 (signals made on at least half the decision days)."""

    asset_class: str
    first: date | None
    through: date | None
    expected: int
    recorded: int
    missed: tuple[date, ...] = ()
    weekly_missed: tuple[date, ...] = ()

    @property
    def generated_share(self) -> float | None:
        return self.recorded / self.expected if self.expected else None


def format_gaps(gaps: Mapping[str, DecisionGaps]) -> str:
    """One line per class for the CLI; dates only, never amounts."""
    if not gaps:
        return "no decision calendar for this strategy"
    lines = []
    for cls, g in sorted(gaps.items()):
        share = "n/a" if g.generated_share is None else f"{g.generated_share:.1%}"
        weekly = ",".join(d.isoformat() for d in g.weekly_missed) or "-"
        lines.append(
            f"{cls}: {g.first}..{g.through} expected={g.expected} recorded={g.recorded} "
            f"missed={len(g.missed)} weekly_missed={len(g.weekly_missed)} ({weekly}) "
            f"generated={share}"
        )
    return "\n".join(lines)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _risk_status(res: ExecResult) -> str:
    if res.status in ("halted", "rejected", "failed"):
        return res.status
    return res.decision.status if res.decision else "accepted"


class PaperTrader:
    def __init__(
        self,
        db: Session,
        market: "MarketDataService",
        settings: "Settings",
        *,
        strategy: PaperStrategy,
        predict: Predictor,
        costs: CostModel,
        live_factory: Callable[[], Broker] = live_broker_unavailable,
        min_order_share: float = MIN_TRADE_SHARE,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.db = db
        self.market = market
        self.settings = settings
        self.strategy = strategy
        self.predict = predict
        self.costs = costs
        self.live_factory = live_factory
        # Rebalancing changes up to this share of equity are skipped (exits never are), as
        # in the backtest. A strategy that registered its own tolerance (S2) brings it.
        self.min_order_share = getattr(strategy, "min_order_share", min_order_share)
        self.clock = clock
        self.limits = RiskLimits.from_settings(settings)
        self.initial_cash = float(settings.paper_initial_capital_krw)
        self.kill = KillSwitch(db, clock=clock)
        self.universe = dict(getattr(strategy, "universe", None) or strategy_symbols())
        self.sizing: Sizing = getattr(strategy, "sizing", "equal")
        if self.sizing not in ("equal", "exposure"):
            raise ValueError(f"Unknown sizing '{self.sizing}'")

    # --- records -------------------------------------------------------------------------

    def _rows(self, *conditions) -> list[PaperSignal]:
        q = select(PaperSignal).where(PaperSignal.strategy_id == self.strategy.strategy_id)
        for c in conditions:
            q = q.where(c)
        return list(self.db.scalars(q.order_by(PaperSignal.as_of, PaperSignal.id)))

    def _trades(self) -> list[Trade]:
        return [
            Trade(
                r.symbol,
                r.side,
                r.fill_date,
                _float(r.quantity),
                _float(r.fill_price),
                _float(r.fill_fx),
                _float(r.fee_krw),
            )
            for r in self._rows(PaperSignal.fill_status == "filled")
        ]

    def held_state(self) -> dict[str, bool]:
        """Each symbol's held state after its latest signal (S1 state, not account state)."""
        return {r.symbol: r.held_after for r in self._rows()}

    def last_rationale(self) -> dict[str, dict]:
        """Each symbol's rationale as recorded with its latest signal (where an exposure
        strategy keeps its state)."""
        return {r.symbol: dict(r.rationale or {}) for r in self._rows()}

    # --- missed decision days (verifier N-13) ----------------------------------------------

    def _calendar(self) -> tuple[Callable, Callable] | None:
        dates = getattr(self.strategy, "decision_dates", None)
        weekly = getattr(self.strategy, "is_weekly_day", None)
        return (dates, weekly) if dates is not None and weekly is not None else None

    def _missed_between(self, asset_class: str, after: date, before: date) -> tuple[list, list]:
        """Decision days strictly between two dates, all of them missed, and the weekly ones."""
        calendar = self._calendar()
        start, end = after + timedelta(days=1), before - timedelta(days=1)
        if calendar is None or start > end:
            return [], []
        dates, weekly = calendar
        missed = list(dates(asset_class, start, end))
        return missed, [d for d in missed if weekly(asset_class, d)]

    def missed_decisions(self, today: date | None = None) -> dict[str, DecisionGaps]:
        """Each class's record coverage of its decision calendar (read only). Empty for a
        strategy without one (S1 decides weekly by definition)."""
        calendar = self._calendar()
        if calendar is None:
            return {}
        dates, weekly = calendar
        now = self.market.utc_now()
        today = today or self.market.now().date()
        out: dict[str, DecisionGaps] = {}
        for cls in sorted(set(self.universe.values())):
            recorded = {r.as_of for r in self._rows(PaperSignal.asset_class == cls)}
            through = last_final_date(BENCHMARKS[cls], today, now)
            if not recorded or through is None:
                out[cls] = DecisionGaps(cls, None, through, 0, 0)
                continue
            first = min(recorded)
            expected = list(dates(cls, first, through)) if first <= through else []
            missed = tuple(d for d in expected if d not in recorded)
            out[cls] = DecisionGaps(
                cls,
                first,
                through,
                len(expected),
                len(expected) - len(missed),
                missed,
                tuple(d for d in missed if weekly(cls, d)),
            )
        return out

    # --- prices --------------------------------------------------------------------------

    def _closes(self, symbols: Iterable[str], start: date, end: date) -> pd.DataFrame:
        from app.forecast.data import load_daily

        symbols = sorted(set(symbols))
        if not symbols:
            return pd.DataFrame()
        daily = load_daily(self.market, symbols, start, end, allow_late_start=True)
        return pd.DataFrame({s: d.bars["close"] for s, d in daily.items()})

    def _fx(self, start: date, end: date) -> pd.Series:
        from app.forecast.data import load_usd_krw

        fx = load_usd_krw(self.market, start, end)
        fx.index = pd.DatetimeIndex(fx.index)
        return fx

    # --- kill switch -----------------------------------------------------------------------

    def check_limits(self, today: date) -> str | None:
        """Trip the kill switch if the paper account broke a limit since the last reset (or
        since its first fill); returns the reason. Checking every day since then, not just
        today, means a day the runner did not run cannot hide a breach."""
        trades = self._trades()
        cash, qty = account(self.initial_cash, trades)
        if cash < -1e-6 or any(q < 0 for q in qty.values()):
            self.kill.trip("leverage", "현금 또는 수량이 음수")
            return "leverage"
        if not trades:
            return None
        start = min(t.fill_date for t in trades)
        since = self.kill.state().since
        if since is not None:
            start = max(start, since.date())
        if start > today:
            return None
        try:
            lookback = start - timedelta(days=LOOKBACK_DAYS)
            closes = self._closes({t.symbol for t in trades}, lookback, today)
            fx = self._fx(lookback, today)
            curve = equity_curve(self.initial_cash, trades, closes, fx, start, today)
            # No external flows: the paper account pays no taxes and takes no deposits or
            # withdrawals, so every change in its equity is a market result (ISSUE-034).
            triggers = kill_switch_triggers(curve, self.limits)
        except (DataUnavailableError, ValueError) as exc:
            log.warning("Paper account cannot be valued (%s)", type(exc).__name__)
            self.kill.trip("stale_data", "평가에 필요한 시세를 불러오지 못함")
            return "stale_data"
        if triggers:
            t = triggers[0]
            self.kill.trip(t.reason_code, f"{t.date} {t.reason_code} {t.value:.2%}")
            return t.reason_code
        return None

    # --- run -----------------------------------------------------------------------------

    def run(self) -> RunReport:
        report = RunReport()
        now = self.market.utc_now()
        today = self.market.now().date()
        state = self.kill.state()
        report.tripped = state.reason_code if state.tripped else self.check_limits(today)

        decided: dict[str, date] = {}
        for cls, bench in BENCHMARKS.items():
            d = last_final_date(bench, today, now)
            if d is None or not self.strategy.is_decision_day(cls, d):
                continue
            # A decision day already recorded is never redone (first record wins).
            if self._rows(PaperSignal.asset_class == cls, PaperSignal.as_of == d):
                continue
            decided[cls] = d
        report.decided = decided
        if not decided:
            return report

        # Days the runner missed since each class's last record: the rule is not changed
        # (a missed weekly day just delays an increase), but it is logged and recorded.
        notes: dict[str, dict] = {}
        for cls, day in decided.items():
            previous = [r.as_of for r in self._rows(PaperSignal.asset_class == cls)]
            if not previous:
                continue
            missed, weekly = self._missed_between(cls, max(previous), day)
            if missed:
                log.warning(
                    "%s %s: %d decision day(s) missed before %s, %d weekly",
                    self.strategy.strategy_id,
                    cls,
                    len(missed),
                    day,
                    len(weekly),
                )
                report.missed[cls] = len(missed)
                notes[cls] = {
                    "missed_decision_days": [d.isoformat() for d in missed],
                    "missed_weekly_days": [d.isoformat() for d in weekly],
                }

        symbols = sorted(s for s, cls in self.universe.items() if cls in decided)
        cash, qty = account(self.initial_cash, self._trades())
        first = min(decided.values()) - timedelta(days=LOOKBACK_DAYS)
        try:
            rows = self.predict(symbols, decided)
            closes = self._closes(set(symbols) | set(qty), first, today)
            fx = self._fx(first, today)
        except DataUnavailableError as exc:
            log.warning("No paper signals today (%s)", type(exc).__name__)
            report.skipped = "추론 또는 시세 데이터를 불러오지 못함"
            return report

        rows = rows[rows["symbol"].isin(symbols)]
        on_day = np.array(
            [
                pd.Timestamp(d).date() == decided.get(c)
                for d, c in zip(rows["date"], rows["asset_class"], strict=True)
            ],
            dtype=bool,
        )
        rows = rows[on_day]
        signals = [
            s
            for s in self.strategy.signals(rows, decided, self.held_state(), self.last_rationale())
            if s.asset_class in decided
        ]
        inputs = {r["symbol"]: _inputs_of(r) for r in rows.to_dict("records")}
        self._decide(signals, decided, cash, qty, closes, fx, inputs, report, notes)
        return report

    def _decide(
        self,
        signals: Sequence[Signal],
        decided: Mapping[str, date],
        cash: float,
        qty: Mapping[str, float],
        closes: pd.DataFrame,
        fx: pd.Series,
        inputs: Mapping[str, dict],
        report: RunReport,
        notes: Mapping[str, dict] | None = None,
    ) -> None:
        notes = notes or {}
        valued_on = max(decided.values())

        def krw(symbol: str, day: date) -> float:
            return _last_on(closes.get(symbol), day) * _last_on(fx, day)

        book = Book(cash, {s: q * krw(s, valued_on) for s, q in qty.items()})
        equity = book.equity
        if not all(math.isfinite(v) for v in book.positions.values()):
            raise DataUnavailableError("A paper position has no price")

        budgets = {c: b for c, b in budgets_from_settings(self.settings).items() if c in decided}
        if self.sizing == "exposure":
            target = exposure_weights(signals, budgets, self.limits)
        else:
            target = target_weights(signals, budgets, self.limits)
        # Classes not deciding today keep their positions as they drifted.
        others = {
            s: v / equity if equity > 0 else 0.0
            for s, v in book.positions.items()
            if self.universe.get(s) not in decided
        }
        plan = {
            o.symbol: o
            for o in plan_rebalance(
                book, {**others, **target}, self.limits, min_notional=self.min_order_share * equity
            )
            if o.symbol in target
        }

        paper = PaperBroker()
        results: dict[str, ExecResult] = {}
        # Sells first, so their proceeds count as cash when the buys are checked.
        for order in sorted(plan.values(), key=lambda o: (o.side != "sell", o.symbol)):
            # The full one-way rate, slippage included, as the backtest checks orders.
            fee = self.costs.rate(instrument(order.symbol, self.universe[order.symbol]), order.side)
            res = execute(
                order,
                book=book,
                settings=self.settings,
                kill_switch=self.kill,
                limits=self.limits,
                paper=paper,
                live_factory=self.live_factory,
                fee_rate=fee,
            )
            results[order.symbol] = res
            if res.status == "submitted":
                book = apply_decision(book, res.decision, fee_rate=fee)

        state = self.kill.state()
        created = self.clock()
        for s in signals:
            as_of = decided[s.asset_class]
            row = PaperSignal(
                created_at=created,
                strategy_id=self.strategy.strategy_id,
                symbol=s.symbol,
                asset_class=s.asset_class,
                as_of=as_of,
                horizon=self.strategy.horizon,
                action=s.action,
                held_after=bool(s.held_after),
                confidence=s.confidence,
                rationale={
                    **_jsonable(s.rationale),
                    **_provenance(inputs.get(s.symbol, {})),
                    **notes.get(s.asset_class, {}),
                },
                ref_price=_finite_or_none(_last_on(closes.get(s.symbol), as_of)),
                ref_fx=_finite_or_none(_last_on(fx, as_of)),
                target_weight=target.get(s.symbol),
                target_date=next_trading_dates(
                    s.symbol, as_of, HORIZONS[self.strategy.horizon][s.asset_class]
                )[-1],
                currency="USD",
                risk_status="halted" if state.tripped else "none",
                risk_reason=f"킬스위치 발동 중({state.reason_code})" if state.tripped else None,
                fill_status="none",
            )
            order, res = plan.get(s.symbol), results.get(s.symbol)
            if order is not None and res is not None:
                row.side = order.side
                row.risk_status = _risk_status(res)
                reasons = ", ".join(res.decision.reasons) if res.decision else ""
                row.risk_reason = res.reason or reasons or None
                if res.status == "submitted":
                    row.notional_krw = _dec(res.decision.notional, KRW)
                    row.slippage_bps = order_costs(
                        self.costs, s.symbol, s.asset_class, order.side
                    ).slippage_bps
                    row.fill_status = "pending"
                    if order.side == "sell":
                        row.quantity = _dec(
                            _sell_quantity(
                                qty.get(s.symbol, 0.0),
                                held_value=book_value(qty, s.symbol, krw, valued_on),
                                notional=res.decision.notional,
                                full_exit=target.get(s.symbol, 0.0) == 0.0,
                            ),
                            QTY,
                        )
                    report.orders += 1
            self.db.add(row)
            report.recorded += 1
        self.db.commit()

    # --- fill ----------------------------------------------------------------------------

    def fill(self) -> int:
        """Fill pending orders at their next bar's open once that bar is final, day by day so
        the cash each day's buys may spend is settled first.

        A kill switch trip cancels every order approved before it: while tripped nothing
        fills, and an order approved before a trip never fills even after the user resets
        (the reset resumes new decisions, not stale ones).
        """
        from app.forecast.data import load_daily, load_usd_krw

        now = self.market.utc_now()
        today = self.market.now().date()
        pending = self._rows(PaperSignal.fill_status == "pending")
        if not pending:
            return 0
        state = self.kill.state()
        last_trip = datetime.max if state.tripped else self.kill.last_trip_at()
        by_day: dict[date, list[PaperSignal]] = {}
        cancelled = False
        for r in pending:
            if last_trip is not None and r.created_at <= last_trip:
                r.fill_status, r.fill_note = "expired", "kill_switch"
                r.risk_status = "halted"
                r.risk_reason = f"체결 전 킬스위치 발동({state.reason_code or '해제됨'})"
                cancelled = True
                continue
            by_day.setdefault(next_trading_dates(r.symbol, r.as_of, 1)[0], []).append(r)
        if cancelled:
            self.db.commit()

        filled = 0
        for day in sorted(by_day):
            rows = by_day[day]
            symbols = sorted({r.symbol for r in rows})
            try:
                if any((last_final_date(s, today, now) or date.min) < day for s in symbols):
                    raise DataUnavailableError("next bar is not final yet")
                bars = load_daily(self.market, symbols, day, day)
                # At the open only the previous day's rate is known (as in the backtest).
                before = day - timedelta(days=1)
                fx = float(load_usd_krw(self.market, before, before).iloc[-1])
                opens = {s: float(b.bars["open"].loc[pd.Timestamp(day)]) for s, b in bars.items()}
            except (DataUnavailableError, KeyError):
                if (today - day).days <= FILL_EXPIRY_DAYS:
                    break  # later days wait too, cash must settle in date order
                for r in rows:
                    r.fill_status, r.fill_note = "expired", "no_bar"
                self.db.commit()
                continue
            cash, held = account(self.initial_cash, self._trades())
            orders = [
                PendingOrder(
                    r.id,
                    r.symbol,
                    r.side,
                    _float(r.notional_krw),
                    _float(r.quantity) if r.side == "sell" else None,
                    order_costs(self.costs, r.symbol, r.asset_class, r.side),
                )
                for r in rows
            ]
            results = {f.key: f for f in fill_orders(orders, opens, fx, cash, held)}
            for r in rows:
                f = results[r.id]
                r.fill_date = day
                r.fill_note = f.note or None
                if not f.filled:
                    r.fill_status = "expired"
                    continue
                r.fill_status = "filled"
                r.quantity = _dec(f.quantity, QTY)
                r.fill_price = _dec(f.price, PRICE)
                r.fill_fx = _dec(fx, PRICE)
                r.fee_krw = _dec(f.fee_krw, KRW)
                filled += 1
            self.db.commit()
        return filled

    # --- score ---------------------------------------------------------------------------

    def score(self) -> int:
        """Score signals whose target date has a final bar: total return (dividends net of
        withholding) from the signal's close to the target close, against the class
        benchmark over the same dates, and the KRW result of the filled order."""
        from app.forecast.data import load_daily, load_usd_krw

        now = self.market.utc_now()
        today = self.market.now().date()
        scored = 0
        for r in self._rows(PaperSignal.scored_at.is_(None), PaperSignal.fill_status != "pending"):
            last = last_final_date(r.symbol, today, now)
            if r.target_date is None or last is None or r.target_date > last:
                continue
            bench = BENCHMARKS[r.asset_class]
            try:
                daily = load_daily(
                    self.market,
                    sorted({r.symbol, bench}),
                    r.as_of - timedelta(days=LOOKBACK_DAYS),
                    r.target_date,
                    allow_late_start=True,
                )
                tr = {s: d.total_return(DIVIDEND_WITHHOLDING) for s, d in daily.items()}
                signal_return = period_return(tr[r.symbol], r.as_of, r.target_date)
                bench_return = period_return(tr[bench], r.as_of, r.target_date)
                exit_price = float(daily[r.symbol].bars["close"].loc[pd.Timestamp(r.target_date)])
                pnl = None
                if r.fill_status == "filled":
                    exit_fx = float(
                        load_usd_krw(self.market, r.target_date, r.target_date).iloc[-1]
                    )
                    pnl = trade_pnl_krw(_trade(r), exit_price, exit_fx)
            except (DataUnavailableError, KeyError) as exc:
                log.warning("Cannot score a paper signal yet (%s)", type(exc).__name__)
                continue
            r.exit_price = exit_price
            r.signal_return = signal_return
            r.benchmark_return = bench_return
            r.trade_pnl_krw = _dec(pnl, KRW)
            r.scored_at = self.clock()
            scored += 1
        self.db.commit()
        return scored


def _trade(r: PaperSignal) -> Trade:
    return Trade(
        r.symbol,
        r.side,
        r.fill_date,
        _float(r.quantity),
        _float(r.fill_price),
        _float(r.fill_fx),
        _float(r.fee_krw),
    )


def book_value(qty: Mapping[str, float], symbol: str, krw, day: date) -> float:
    return qty.get(symbol, 0.0) * krw(symbol, day) if symbol in qty else 0.0


def _sell_quantity(held: float, *, held_value: float, notional: float, full_exit: bool) -> float:
    """Quantity a sell order fixes at signal time: everything on an exit, otherwise the
    approved amount's share of the position's value, never more than held."""
    if full_exit or held_value <= 0:
        return held
    return held * min(1.0, notional / held_value)


def _finite_or_none(x: float) -> float | None:
    return x if math.isfinite(x) else None


# Forecast inputs recorded with each signal, so it can be audited and scored later.
RECORDED_INPUTS = (
    "scale",
    "gbdt_q10",
    "gbdt_q50",
    "gbdt_q90",
    "gbdt_p_up",
    "climatology_p_up",
    "ewma_t_q10",
    "ewma_t_q90",
)


def _inputs_of(row: Mapping[str, Any]) -> dict:
    out = {c: row[c] for c in RECORDED_INPUTS if c in row}
    if "run_id" in row:
        out["run_id"] = row["run_id"]
    return out


def _provenance(inputs: Mapping[str, Any]) -> dict:
    from app.forecast.report import CONFIGS_TRIED
    from app.strategy.evaluation import STRATEGY_CONFIGS_TRIED

    return {
        "inputs": _jsonable({k: v for k, v in inputs.items() if k != "run_id"}),
        "run_id": inputs.get("run_id"),
        "configs_tried": CONFIGS_TRIED,
        "strategy_configs_tried": STRATEGY_CONFIGS_TRIED,
    }


def _jsonable(x: Any) -> Any:
    """Plain JSON values: numpy scalars to Python, NaN to None, dates to ISO text."""
    if isinstance(x, Mapping):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, list | tuple | set):
        return [_jsonable(v) for v in x]
    if isinstance(x, np.generic):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    if isinstance(x, date | datetime | pd.Timestamp):
        return x.isoformat()
    return x


# --- live wiring (CLI) ----------------------------------------------------------------------


def make_predictor(market: "MarketDataService", artifacts_dir: Path, horizon: str) -> Predictor:
    """Inference rows from the current trained run, built only from strictly loaded bars.

    Same model inputs as the forecast service (panel, latest ranks against the run's trained
    universe, conformal offsets), but every symbol the panel needs comes from `load_daily`:
    a missing or stale one raises DataUnavailableError and the day gets no signals instead of
    signals computed on degraded inputs.
    """

    def predict(symbols: Sequence[str], as_of: Mapping[str, date]) -> pd.DataFrame:
        from app.forecast import store, universe
        from app.forecast.data import load_daily
        from app.forecast.panel import AssetSeries, ContextSeries, build_panel, latest_ranks
        from app.forecast.walkforward import apply_offsets

        path = store.resolve(artifacts_dir)
        if path is None:
            raise DataUnavailableError("No trained forecaster")
        run = store.load(path)
        trained = list(run.meta["universe"])
        context_symbols = {sym for sym, _, _ in universe.CONTEXT.values()}
        wanted = sorted(set(trained) | set(symbols))
        start = min(as_of.values()) - timedelta(days=INFERENCE_LOOKBACK_DAYS)
        end = max(as_of.values())
        daily = load_daily(
            market,
            sorted(set(wanted) | context_symbols),
            start,
            end,
            allow_late_start=True,
            require_open=False,
        )
        bars = {s: d.bars.drop(columns="ohlc_ok") for s, d in daily.items()}
        assets = {
            s: AssetSeries("crypto" if trades_every_day(s) else "stock", bars[s]) for s in wanted
        }
        context = [
            ContextSeries(name, bars[sym], lag, kind)
            for name, (sym, kind, lag) in universe.CONTEXT.items()
        ]
        if "vix" in universe.CONTEXT and "vix3m" in universe.CONTEXT:
            # Same derived series as load_inputs builds.
            vix = bars[universe.CONTEXT["vix"][0]]["close"]
            vix3m = bars[universe.CONTEXT["vix3m"][0]]["close"]
            ratio = pd.DataFrame({"close": (vix / vix3m).dropna()})
            context.append(ContextSeries("vix_term", ratio, universe.CONTEXT["vix"][2], "level"))
        benchmarks = {
            "stock": bars[universe.STOCK_BENCHMARK]["adj_close"],
            "crypto": bars[universe.CRYPTO_BENCHMARK]["adj_close"],
        }
        panel = build_panel(assets, context, benchmarks)
        on_day = [
            d.date() == as_of.get(c)
            for d, c in zip(panel["date"], panel["asset_class"], strict=True)
        ]
        keep = panel["symbol"].isin(symbols).to_numpy() & np.array(on_day, dtype=bool)
        rows = latest_ranks(panel, panel[keep], peers=trained).set_index("symbol")
        out = rows[["date", "asset_class"]].copy()
        out["scale"] = rows[f"scale_{horizon}"]
        for name, model in run.models[horizon].items():
            pred = model.predict(rows)
            pred = apply_offsets(pred, run.offsets[horizon].get(name, {}), rows["asset_class"])
            for col in pred.columns:
                out[f"{name}_{col}"] = pred[col].to_numpy()
        out["run_id"] = run.run_id
        return out.reset_index(names="symbol")

    return predict


def no_live_edge(as_of: date, asset_class: str, horizon: str, *_metric):
    """Live edge stays off until the strategy is a candidate (D-006, D-015, D-024): every
    paper signal is 'no edge' and no position is opened. An extra argument (the compared
    metric, "vol" for S2) does not change that."""
    from app.strategy.signals import EdgeStatus

    return EdgeStatus(False, "not_candidate")


@dataclass(frozen=True)
class _Recorded:
    """A `signals.Signal` in the shape the runner records."""

    symbol: str
    asset_class: str
    action: str
    held_after: bool
    confidence: str | None
    rationale: Mapping[str, Any]
    target_exposure: float | None = None


class SignalStrategy:
    """A `signals.SignalConfig` (S1-1w for the CLI) as a paper strategy."""

    def __init__(self, config, edge_at=no_live_edge) -> None:
        self.config = config
        self.edge_at = edge_at
        self.strategy_id = config.name
        self.horizon = config.horizon

    def is_decision_day(self, asset_class: str, day: date) -> bool:
        from app.strategy.signals import decision_dates

        return day in decision_dates(self.config.schedule, asset_class, day, day)

    def signals(self, rows, as_of, held, last=None):
        from app.strategy.signals import decide

        held_set = {s for s, h in held.items() if h is True}
        out = []
        for cls, day in as_of.items():
            for s in decide(rows, day, held_set, self.edge_at, self.config, asset_classes=(cls,)):
                reasons = {**s.reasons, "confidence_value": s.confidence_value}
                out.append(
                    _Recorded(
                        s.symbol, s.asset_class, s.action, s.held_after, s.confidence, reasons
                    )
                )
        return out


# Rationale keys where an exposure strategy keeps its class state between runs.
STATE_KEYS = ("e", "R")
# Rationale flag of a decision that started from zero because the stored state was unreadable.
STATE_RESET = "state_reset"


class ExposureDecide(Protocol):
    """The exposure rule (quant's signal code) for one class on `as_of`, from that day's rows
    and the class's previous state ({"e": ..., "R": ...}, empty at the start). Each signal
    carries `target_exposure` (the new committed exposure) and, in `reasons`, the "e" and
    "R" the next decision starts from."""

    def __call__(
        self,
        rows: pd.DataFrame,
        as_of: date,
        prev: Mapping[str, float],
        edge_at: Callable[..., Any],
        config: Any,
        asset_class: str,
    ) -> Sequence[Any]: ...


class ExposureStrategy:
    """An exposure rule (S2-1d) as a paper strategy: decides on every final bar, sizes with
    `risk.exposure_weights` and trades only changes above the registered tolerance
    (`config.min_trade_share` of equity, the same value the backtest uses).

    The class state comes back from the latest record of the class's symbols, so a day the
    runner missed leaves it where it was. A malformed state starts from zero exposure (fail
    closed: the rule then needs a weekly decision day to raise it again); that is logged
    and marked `state_reset` in the day's records, never silent.
    """

    sizing: Sizing = "exposure"

    def __init__(self, config, decide: ExposureDecide, edge_at=no_live_edge) -> None:
        self.config = config
        self.decide = decide
        self.edge_at = edge_at
        self.strategy_id = config.name
        self.horizon = config.horizon
        self.universe = dict(config.universe)
        tolerance = config.min_trade_share
        if not (isinstance(tolerance, int | float) and 0.0 <= tolerance < 1.0):
            raise ValueError("min_trade_share must be a share of equity in [0, 1)")
        # The single registered value (s2.S2Config), read rather than copied (verifier N-10).
        self.min_order_share = float(tolerance)

    def is_decision_day(self, asset_class: str, day: date) -> bool:
        # The runner offers only final bars: every XNYS session for stocks, every day for
        # coins, which is S2's calendar.
        return asset_class in set(self.universe.values())

    def decision_dates(self, asset_class: str, start: date, end: date) -> list[date]:
        """The calendar a missed day is counted against (s2.daily_dates)."""
        from app.strategy.s2 import daily_dates

        return daily_dates(asset_class, start, end)

    def is_weekly_day(self, asset_class: str, day: date) -> bool:
        """Whether `day` may raise exposure; missing one delays an increase by a week."""
        from app.strategy.s2 import is_weekly_day

        return is_weekly_day(asset_class, day)

    def state(
        self, asset_class: str, last: Mapping[str, Mapping[str, Any]]
    ) -> tuple[dict[str, float], bool]:
        """The class's stored state and whether it had to be reset: ({}, False) before the
        first decision, ({}, True) when the latest record holds no usable state."""
        for symbol in sorted(s for s, c in self.universe.items() if c == asset_class):
            r = last.get(symbol)
            if r is None:
                continue
            values = [r.get(k) for k in STATE_KEYS]
            if all(
                isinstance(v, int | float)
                and not isinstance(v, bool)
                and math.isfinite(v)
                and 0.0 <= v <= 1.0
                for v in values
            ):
                return {k: float(v) for k, v in zip(STATE_KEYS, values, strict=True)}, False
            log.warning(
                "Unreadable %s state for %s; starting from zero exposure",
                self.strategy_id,
                asset_class,
            )
            return {}, True
        return {}, False

    def signals(self, rows, as_of, held, last=None):
        last = last or {}
        out = []
        for cls, day in as_of.items():
            prev, reset = self.state(cls, last)
            for s in self.decide(rows, day, prev, self.edge_at, self.config, cls):
                reasons = {**s.reasons, "confidence_value": getattr(s, "confidence_value", None)}
                if reset:
                    reasons[STATE_RESET] = True
                missing = [k for k in STATE_KEYS if k not in reasons]
                if missing:
                    raise ValueError(f"{s.symbol}: exposure signal without state {missing}")
                out.append(
                    _Recorded(
                        s.symbol,
                        s.asset_class,
                        s.action,
                        bool(s.held_after),
                        s.confidence,
                        reasons,
                        float(s.target_exposure),
                    )
                )
        return out


def make_strategy(name: str, settings: "Settings", costs: CostModel) -> PaperStrategy:
    """The registered paper strategies, with the live edge off (D-006, D-024)."""
    if name == "s1":
        from app.strategy.s1 import round_trip_costs, s1_1w

        return SignalStrategy(s1_1w(round_trip_costs(costs)))
    if name == "s2":
        from app.strategy.s2 import paper_decider, s2_1d

        return ExposureStrategy(s2_1d(), paper_decider(budgets_from_settings(settings)))
    raise ValueError(f"Unknown strategy '{name}'")


def main(argv: Sequence[str] | None = None) -> None:
    from app.config import get_settings
    from app.db.session import SessionLocal
    from app.deps import get_provider, get_quote_cache
    from app.services.market_data import MarketDataService

    parser = argparse.ArgumentParser(description="Paper trading (never sends real orders)")
    parser.add_argument("command", choices=["run", "fill", "score", "gaps"])
    parser.add_argument("--strategy", choices=["s1", "s2"], default="s1")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    settings = get_settings()
    costs = CostModel()
    strategy = make_strategy(args.strategy, settings, costs)
    with SessionLocal() as db:
        market = MarketDataService(db, get_provider(), get_quote_cache())
        trader = PaperTrader(
            db,
            market,
            settings,
            strategy=strategy,
            predict=make_predictor(market, settings.artifacts_dir, strategy.horizon),
            costs=costs,
        )
        if args.command == "run":
            r = trader.run()
            decided = {c: str(d) for c, d in r.decided.items()}
            print(
                f"decided={decided} recorded={r.recorded} orders={r.orders} "
                f"tripped={r.tripped} skipped={r.skipped} missed={r.missed}"
            )
        elif args.command == "fill":
            print(f"filled={trader.fill()}")
        elif args.command == "gaps":
            print(format_gaps(trader.missed_decisions()))
        else:
            print(f"scored={trader.score()}")


if __name__ == "__main__":
    main()
