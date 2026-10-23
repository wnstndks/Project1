"""Buy-more / stop-loss checks of the user's own rules (plan G, DECISIONS.md D-027).

This is not a trading signal. The forecaster has no verified directional edge (CLAUDE.md:
without `edge` a symbol shows '우위 없음'), so nothing here says *when* a price will move.
Instead the user's rules are evaluated against one position and its final daily bars, and
the result is the price at which each rule fires, how far away it is, and whether a buy
would even be allowed by the risk limits. The forecaster's calibrated range enters only
through `prob_below` / `prob_below_label`, a reference the UI labels as such.

Pure functions: no database, no network, no HTTP. `avg_cost`, `price`, `bars.close` and
`equity` must be in one currency (KRW coins: Upbit bars with a KRW average cost). Invalid
input fails closed with ValueError, as in `risk.py`.

Settings come in three layers, global → asset class (`crypto`) → symbol (`targets`), because
a coin moves three to four times as much as a stock and the same −15% stop would be noise.

Counting days: every rule that says "N days" counts final bars. A coin has one bar per
calendar day, so for coins this is calendar days; for a stock it is trading days, which is
what an N-candle chart shows. Bars also keep the module free of the market calendar.

Precedence: any stop-loss condition wins (`cut`); buy-more conditions are then not listed,
because a position under review for cutting is never also a buy candidate. A buy-more
condition that is met but blocked by a limit stays `hold`, with the condition listed and
the reason in `blocked_by`, so the UI can say "조건은 맞지만 한도로 보류".

Labels: `RuleCheck.label_ko` names the review by what fired, so a position in profit whose
trailing stop tripped reads "이익 보전 검토", never "손절 검토"; `chip_ko` is the short
form for the holdings list. `STATUS_LABELS` stays for compatibility only.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

from app.forecast.panel import AssetClass
from app.strategy.risk import EPS, INDEX_FUNDS, Book, Order, RiskLimits, check_order

if TYPE_CHECKING:
    from app.config import Settings

Status = Literal["cut", "add", "hold"]
TriggerKind = Literal["cut", "add", "info"]

# Compatibility only: the home chip uses `RuleCheck.chip_ko`, the detail `label_ko`, which
# distinguish a stop-loss from a trailing stop on a position in profit.
STATUS_LABELS: dict[Status, str] = {"cut": "손절 검토", "add": "추매 검토", "hold": "관망"}
# Why a buy would not be allowed right now; codes come from `check_order` plus the kill switch.
BLOCK_LABELS: dict[str, str] = {
    "kill_switch": "킬스위치 발동 중",
    "max_position_weight": "종목 비중 상한",
    "max_index_fund_weight": "지수 ETF 비중 상한",
    "max_order_fraction": "1회 주문 상한",
    "max_order_krw": "1회 주문 상한(원화)",
    "cash": "현금 부족",
    "invalid_book": "계좌 상태를 읽을 수 없음",
    "invalid_notional": "주문 금액을 계산할 수 없음",
}
# Clip for `prob_below`: three quantiles say nothing reliable about the far tails.
PROB_FLOOR, PROB_CEIL = 0.01, 0.99
# Shown next to every `prob_below` figure: the forecast is for the close at the horizon, and
# a level is touched on the way roughly twice as often as it is still breached at the end
# (reflection principle of a driftless walk).
PROB_CAVEAT_KO = "기간 끝에 그 아래일 확률이며, 도중에 한 번 닿을 확률은 대략 두 배입니다"
NO_CASH_NOTE_KO = "현금 기록이 없어 추매 가능 금액을 확인하지 못했습니다"


# --- settings -------------------------------------------------------------------------


@dataclass(frozen=True)
class SymbolRule:
    """Per-symbol overrides; None keeps the asset-class or global value. `target_weight_pct`
    has no global default: without it the target-weight rule is off for that symbol."""

    target_weight_pct: float | None = None
    cut_loss_pct: float | None = None
    trailing_drop_pct: float | None = None
    add_step_pct: float | None = None
    add_max_steps: int | None = None


@dataclass(frozen=True)
class AssetClassRule:
    """Asset-class overrides of the global values; None keeps the global one."""

    cut_loss_pct: float | None = None
    trailing_drop_pct: float | None = None
    add_step_pct: float | None = None


# Coins move several times as much as stocks (AM_RULES_CRYPTO_*).
CRYPTO_DEFAULTS = AssetClassRule(cut_loss_pct=25.0, trailing_drop_pct=30.0, add_step_pct=8.0)


def _check_pct(name: str, value: float, *, allow_zero: bool = False) -> None:
    lo_ok = value >= 0 if allow_zero else value > 0
    if not (math.isfinite(value) and lo_ok and value < 100):
        raise ValueError(f"{name} must be a percentage in {'[' if allow_zero else '('}0, 100)")


def _check_count(name: str, value: int, minimum: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _or(override: float | None, base: float) -> float:
    return override if override is not None else base


@dataclass(frozen=True)
class RuleSettings:
    """The user's rules. Percentages are of the average cost (or of the recent high), day
    counts are final bars (see module docstring). Defaults mirror `AM_RULES_*`."""

    # Stop-loss review
    cut_loss_pct: float = 15.0
    trailing_lookback_days: int = 60
    trailing_drop_pct: float = 20.0
    below_ma_days: int = 5
    ma_long: int = 60
    ma_short: int = 20
    # Buy-more review. Two steps of −5% keep every add price above the −15% stop-loss.
    add_step_pct: float = 5.0
    add_max_steps: int = 2
    add_requires_above_ma_short: bool = True
    target_weight_gap_pt: float = 5.0
    targets: Mapping[str, SymbolRule] = field(default_factory=dict)
    # Asset-class layer between the global values and `targets`.
    crypto: AssetClassRule = CRYPTO_DEFAULTS
    # Loss at the stop-loss price as a share of equity above which the check warns.
    max_risk_pct: float = 2.0

    def __post_init__(self) -> None:
        _check_pct("cut_loss_pct", self.cut_loss_pct)
        _check_pct("trailing_drop_pct", self.trailing_drop_pct)
        _check_pct("add_step_pct", self.add_step_pct)
        _check_pct("target_weight_gap_pt", self.target_weight_gap_pt, allow_zero=True)
        _check_pct("max_risk_pct", self.max_risk_pct)
        _check_count("trailing_lookback_days", self.trailing_lookback_days, 1)
        _check_count("below_ma_days", self.below_ma_days, 1)
        _check_count("ma_long", self.ma_long, 2)
        _check_count("ma_short", self.ma_short, 2)
        _check_count("add_max_steps", self.add_max_steps, 0)
        for name in ("cut_loss_pct", "trailing_drop_pct", "add_step_pct"):
            value = getattr(self.crypto, name)
            if value is not None:
                _check_pct(f"crypto.{name}", value)
        for symbol, rule in self.targets.items():
            for name in ("target_weight_pct", "cut_loss_pct", "trailing_drop_pct", "add_step_pct"):
                value = getattr(rule, name)
                if value is not None:
                    _check_pct(f"targets[{symbol}].{name}", value)
            if rule.add_max_steps is not None:
                _check_count(f"targets[{symbol}].add_max_steps", rule.add_max_steps, 0)

    @classmethod
    def from_config(
        cls, settings: "Settings", targets: Mapping[str, SymbolRule] | None = None
    ) -> "RuleSettings":
        """Global and asset-class values from `AM_RULES_*`; per-symbol rules are stored by
        the app and passed in, because `config.py` only holds defaults."""

        def opt(v: object) -> float | None:
            return float(v) if v is not None else None  # type: ignore[arg-type]

        return cls(
            cut_loss_pct=float(settings.rules_cut_loss_pct),
            trailing_lookback_days=int(settings.rules_trailing_lookback_days),
            trailing_drop_pct=float(settings.rules_trailing_drop_pct),
            below_ma_days=int(settings.rules_below_ma_days),
            ma_long=int(settings.rules_ma_long),
            ma_short=int(settings.rules_ma_short),
            add_step_pct=float(settings.rules_add_step_pct),
            add_max_steps=int(settings.rules_add_max_steps),
            add_requires_above_ma_short=bool(settings.rules_add_requires_above_ma_short),
            target_weight_gap_pt=float(settings.rules_target_weight_gap_pt),
            targets=dict(targets or {}),
            crypto=AssetClassRule(
                cut_loss_pct=opt(settings.rules_crypto_cut_loss_pct),
                trailing_drop_pct=opt(settings.rules_crypto_trailing_drop_pct),
                add_step_pct=opt(settings.rules_crypto_add_step_pct),
            ),
            max_risk_pct=float(settings.rules_max_risk_pct),
        )

    def resolve(self, symbol: str, asset_class: AssetClass | None = None) -> "ResolvedRule":
        """The values that apply to `symbol`: global → asset class (`crypto` when
        `asset_class == "crypto"`) → the symbol's own overrides. Without `asset_class` the
        asset-class layer is skipped (the original behaviour)."""
        c = self.crypto if asset_class == "crypto" else AssetClassRule()
        o = self.targets.get(symbol, SymbolRule())
        return ResolvedRule(
            cut_loss_pct=_or(o.cut_loss_pct, _or(c.cut_loss_pct, self.cut_loss_pct)),
            trailing_lookback_days=self.trailing_lookback_days,
            trailing_drop_pct=_or(
                o.trailing_drop_pct, _or(c.trailing_drop_pct, self.trailing_drop_pct)
            ),
            below_ma_days=self.below_ma_days,
            ma_long=self.ma_long,
            ma_short=self.ma_short,
            add_step_pct=_or(o.add_step_pct, _or(c.add_step_pct, self.add_step_pct)),
            add_max_steps=o.add_max_steps if o.add_max_steps is not None else self.add_max_steps,
            add_requires_above_ma_short=self.add_requires_above_ma_short,
            target_weight_gap_pt=self.target_weight_gap_pt,
            target_weight_pct=o.target_weight_pct,
        )

    def validate_notes(self) -> tuple[str, ...]:
        """Rule combinations that are legal but self-defeating, as notes for the settings
        screen, never exceptions: a last buy-more step below the stop-loss means the cut
        comes first. Checked for the global values, the crypto layer when it differs, and
        each symbol that overrides one of the three values involved."""
        notes: list[str] = []

        def check(scope: str, r: "ResolvedRule") -> None:
            last = r.add_step_pct * r.add_max_steps
            if r.add_max_steps > 0 and last > r.cut_loss_pct + EPS:
                notes.append(
                    f"{scope}: 분할매수 마지막 회차(−{last:g}%)가 손절(−{r.cut_loss_pct:g}%) "
                    "아래라 손절 검토가 먼저 옵니다"
                )

        check("전역", self.resolve(""))
        if self.crypto != AssetClassRule():
            check("코인", self.resolve("", "crypto"))
        for symbol in sorted(self.targets):
            o = self.targets[symbol]
            if (o.cut_loss_pct, o.add_step_pct, o.add_max_steps) != (None, None, None):
                check(symbol, self.resolve(symbol))
        return tuple(notes)

    @property
    def warnings(self) -> tuple[str, ...]:
        return self.validate_notes()


@dataclass(frozen=True)
class ResolvedRule:
    cut_loss_pct: float
    trailing_lookback_days: int
    trailing_drop_pct: float
    below_ma_days: int
    ma_long: int
    ma_short: int
    add_step_pct: float
    add_max_steps: int
    add_requires_above_ma_short: bool
    target_weight_gap_pt: float
    target_weight_pct: float | None


# --- inputs ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PositionView:
    """One held position as the caller (the service, from the ledger) sees it.

    `weight_pct` is the position's share of total equity in percent. `add_steps_done` is how
    many buys were added since the current position started (the ledger knows; this module
    does not), so the next step's price is `avg_cost × (1 − step% × (done + 1))`.
    """

    symbol: str
    asset_class: AssetClass
    quantity: float
    avg_cost: float
    price: float
    weight_pct: float
    add_steps_done: int = 0


@dataclass(frozen=True)
class LimitState:
    """What the risk layer knows at check time.

    `book` (cash and position values in KRW, the paper account or any account with a cash
    record) lets `risk.check_order` run the very pre-trade check paper trading applies.
    Without it (real holdings have no cash record) only the symbol weight cap and the kill
    switch are checked, and the result carries a note saying so. A tripped kill switch
    blocks buy-more reviews; stop-loss reviews are still reported because they reduce risk
    and this module never places orders.
    """

    limits: RiskLimits = RiskLimits()
    kill_switch_tripped: bool = False
    kill_switch_reason: str | None = None
    book: Book | None = None


# --- outputs --------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleTrigger:
    code: str
    label_ko: str
    detail: str
    kind: TriggerKind


@dataclass(frozen=True)
class Levels:
    """Prices at which the rules fire, in the position's currency."""

    cut_price: float  # max(cut_loss_price, trailing_stop_price)
    cut_loss_price: float
    trailing_high: float  # highest high of the lookback window, or the current price if higher
    trailing_stop_price: float
    add_price: float | None  # None once all steps are used
    next_add_step: int | None
    ma_short: float | None  # None when there are fewer bars than the window
    ma_long: float | None
    target_weight_pct: float | None
    # Loss if the stop-loss price is hit from here: (price − cut_price) × quantity, 0 when
    # the stop is already above the price (a review is then already open).
    risk_amount: float = 0.0


@dataclass(frozen=True)
class RuleCheck:
    symbol: str
    status: Status
    triggers: tuple[RuleTrigger, ...]
    levels: Levels
    # Move from the current price to the level, in percent (negative = below the price).
    cut_distance_pct: float
    add_distance_pct: float | None
    # Why a buy would not be allowed now (BLOCK_LABELS keys); checked whatever the status.
    blocked_by: tuple[str, ...]
    # Largest single buy the limits allow, when `LimitState.book` is given.
    add_cap_krw: float | None
    # Date of the last final bar the bar-based conditions were evaluated on.
    as_of: date
    # What the review is, by what fired: 손절 검토 / 이익 보전 검토 / 추세 이탈 · 매도 검토 /
    # 추매 검토 / 관망. `chip_ko` is the short form for the holdings list.
    label_ko: str = ""
    chip_ko: str = ""
    # `levels.risk_amount` as a share of `equity`, when the caller gave one.
    risk_pct_equity: float | None = None
    # Weight the symbol may still add before its cap, in percentage points (0 when over).
    weight_room_pt: float | None = None
    # Plain-language caveats about what could not be checked.
    notes: tuple[str, ...] = ()


# --- helpers --------------------------------------------------------------------------


def _finite(x: object) -> bool:
    try:
        return math.isfinite(float(x))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _positive(x: object) -> bool:
    return _finite(x) and float(x) > 0  # type: ignore[arg-type]


def _check_position(p: PositionView) -> None:
    if not _positive(p.quantity):
        raise ValueError(f"{p.symbol}: quantity must be positive (no position to check)")
    if not _positive(p.avg_cost) or not _positive(p.price):
        raise ValueError(f"{p.symbol}: avg_cost and price must be positive numbers")
    if not _finite(p.weight_pct) or p.weight_pct < 0:
        raise ValueError(f"{p.symbol}: weight_pct must be a non-negative number")
    if not isinstance(p.add_steps_done, int) or p.add_steps_done < 0:
        raise ValueError(f"{p.symbol}: add_steps_done must be a non-negative integer")


def _prepare_bars(bars: pd.DataFrame | None) -> pd.DataFrame:
    """Final bars sorted by date with a finite close; `high` kept when present."""
    if bars is None or bars.empty:
        return pd.DataFrame({"date": pd.Series(dtype="object"), "close": pd.Series(dtype=float)})
    missing = {"date", "close"} - set(bars.columns)
    if missing:
        raise ValueError(f"bars is missing columns: {sorted(missing)}")
    cols = [c for c in ("date", "close", "high") if c in bars.columns]
    df = bars.loc[:, cols].copy()
    df["close"] = pd.to_numeric(df["close"], errors="coerce").astype(float)
    df = df[np.isfinite(df["close"])]
    if "high" in df.columns:
        df["high"] = pd.to_numeric(df["high"], errors="coerce").astype(float)
    return df.sort_values("date", kind="stable").reset_index(drop=True)


def _to_date(d: object) -> date:
    if isinstance(d, pd.Timestamp | datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return pd.Timestamp(d).date()  # type: ignore[arg-type]


def sma(closes: np.ndarray, window: int) -> float | None:
    """Simple moving average of the last `window` closes; None with fewer bars."""
    if window < 1 or len(closes) < window:
        return None
    return float(np.mean(closes[-window:]))


def bars_below_ma(closes: np.ndarray, window: int) -> int | None:
    """How many of the latest bars, counting back from the last, closed below their own
    `window`-bar SMA until one did not. None when no SMA can be computed."""
    if window < 1 or len(closes) < window:
        return None
    ma = pd.Series(closes).rolling(window).mean().to_numpy()
    count = 0
    for i in range(len(closes) - 1, window - 2, -1):
        if closes[i] < ma[i]:
            count += 1
        else:
            break
    return count


def trailing_high(bars: pd.DataFrame, lookback: int, price: float) -> float:
    """Highest high (close where no high is recorded) of the last `lookback` bars, or the
    current price when that is higher, so the stop rises with a new high."""
    window = bars.tail(lookback)
    if window.empty:
        return price
    highs = window["close"].to_numpy()
    if "high" in window.columns:
        h = window["high"].to_numpy()
        highs = np.where(np.isfinite(h), np.maximum(h, highs), highs)
    return max(float(np.max(highs)), price)


def _pct(num: float, den: float) -> float:
    return (num / den - 1.0) * 100.0


def _fmt(x: float) -> str:
    """A price for detail text: no currency, no thousands separator, two decimals at most."""
    if x >= 100:
        return f"{x:,.0f}"
    return f"{x:,.2f}".rstrip("0").rstrip(".")


# --- the check ------------------------------------------------------------------------


def blocked_reasons(
    position: PositionView, limits: LimitState
) -> tuple[tuple[str, ...], float | None]:
    """Why one buy of `position.symbol` would not pass the limits now, and the largest buy
    allowed (KRW) when a book is known.

    The weight test asks whether one more order of the per-order cap would take the symbol
    past its cap, not whether it is at the cap already; otherwise a position at 19.9% would
    still read as a buy candidate. With a book, `risk.check_order` runs with the per-order
    cap as the requested size, so the reasons are exactly those paper trading would give.
    """
    risk = limits.limits
    out: list[str] = []
    if limits.kill_switch_tripped:
        out.append("kill_switch")
    cap_code = "max_index_fund_weight" if position.symbol in INDEX_FUNDS else "max_position_weight"
    order_weight = risk.max_order_fraction
    if limits.book is not None and risk.max_order_krw is not None and limits.book.equity > 0:
        order_weight = min(order_weight, risk.max_order_krw / limits.book.equity)
    if position.weight_pct / 100.0 + order_weight > risk.symbol_cap(position.symbol) + EPS:
        out.append(cap_code)
    add_cap: float | None = None
    if limits.book is not None:
        equity = limits.book.equity
        notional = risk.max_order_fraction * equity
        if risk.max_order_krw is not None:
            notional = min(notional, risk.max_order_krw)
        decision = check_order(Order(position.symbol, "buy", notional), limits.book, risk)
        if decision.status == "rejected":
            out.extend(r for r in decision.reasons if r not in out)
        else:
            add_cap = decision.notional
    return tuple(out), add_cap


def weight_room_pt(position: PositionView, limits: LimitState) -> float:
    """Percentage points the symbol may still add before its weight cap; 0 when over."""
    cap = limits.limits.symbol_cap(position.symbol) * 100.0
    return max(cap - position.weight_pct, 0.0)


def evaluate(
    position: PositionView,
    bars: pd.DataFrame | None,
    settings: RuleSettings,
    limits: LimitState,
    *,
    as_of: date | None = None,
    equity: float | None = None,
) -> RuleCheck:
    """Check one position against the user's rules.

    `bars` are final daily bars (`date`, `close`, optionally `high`), any order; the current
    `position.price` is compared with levels, while "closes below the moving average" uses
    bars only (a live quote is not a close). `as_of` defaults to the last bar's date and is
    required when there are no bars. `equity` (total assets, in the position's currency)
    turns the loss at the stop-loss price into a share of equity and warns past
    `settings.max_risk_pct`.

    Stop-loss (any one → `cut`): price ≤ avg_cost × (1 − cut_loss%); price ≤ trailing high ×
    (1 − trailing_drop%); the last `below_ma_days` bars all closed below their `ma_long` SMA.
    Buy-more (any one, not blocked → `add`): price ≤ avg_cost × (1 − add_step% × (done + 1))
    while steps remain and, if required, price > `ma_short` SMA; or weight ≤ target weight −
    gap (the target rule is a rebalance and ignores the moving average). Otherwise `hold`.
    """
    _check_position(position)
    if equity is not None and not _positive(equity):
        raise ValueError(f"{position.symbol}: equity must be a positive number")
    rule = settings.resolve(position.symbol, position.asset_class)
    frame = _prepare_bars(bars)
    if frame.empty:
        if as_of is None:
            raise ValueError(f"{position.symbol}: no bars and no as_of date")
        when = as_of
    else:
        when = as_of if as_of is not None else _to_date(frame["date"].iloc[-1])
    closes = frame["close"].to_numpy(dtype=float)
    price, cost = float(position.price), float(position.avg_cost)

    # Levels
    ma_short = sma(closes, rule.ma_short)
    ma_long = sma(closes, rule.ma_long)
    high = trailing_high(frame, rule.trailing_lookback_days, price)
    cut_loss_price = cost * (1 - rule.cut_loss_pct / 100)
    trailing_stop_price = high * (1 - rule.trailing_drop_pct / 100)
    cut_price = max(cut_loss_price, trailing_stop_price)
    risk_amount = max(price - cut_price, 0.0) * float(position.quantity)
    next_step: int | None = None
    add_price: float | None = None
    if position.add_steps_done < rule.add_max_steps:
        next_step = position.add_steps_done + 1
        add_price = cost * (1 - rule.add_step_pct / 100 * next_step)
        if add_price <= 0:
            next_step, add_price = None, None

    cut: list[RuleTrigger] = []
    add: list[RuleTrigger] = []
    info: list[RuleTrigger] = []

    # Stop-loss conditions
    if price <= cut_loss_price * (1 + EPS):
        cut.append(
            RuleTrigger(
                "cut_loss",
                "손절 기준 도달",
                f"평균단가 대비 {_pct(price, cost):+.1f}% (기준 −{rule.cut_loss_pct:g}%)",
                "cut",
            )
        )
    if price <= trailing_stop_price * (1 + EPS):
        cut.append(
            RuleTrigger(
                "trailing_stop",
                "고점 대비 하락",
                f"최근 {rule.trailing_lookback_days}봉 고점 {_fmt(high)} 대비 "
                f"{_pct(price, high):+.1f}% (기준 −{rule.trailing_drop_pct:g}%)",
                "cut",
            )
        )
    skipped: list[str] = []
    need = rule.ma_long + rule.below_ma_days - 1
    if len(closes) < need:
        skipped.append(
            f"{rule.ma_long}일선 아래 {rule.below_ma_days}일 연속 조건"
            f"(봉 {need}개 필요, {len(closes)}개 있음)"
        )
    else:
        below = bars_below_ma(closes, rule.ma_long) or 0
        if below >= rule.below_ma_days:
            cut.append(
                RuleTrigger(
                    "below_ma",
                    f"{rule.ma_long}일선 아래 지속",
                    f"종가가 {rule.ma_long}일 이동평균 아래 {below}일 연속 "
                    f"(기준 {rule.below_ma_days}일)",
                    "cut",
                )
            )

    # Buy-more conditions (listed only when nothing says cut)
    if not cut:
        if add_price is not None and next_step is not None and price <= add_price * (1 + EPS):
            if not rule.add_requires_above_ma_short:
                add.append(_add_step_trigger(next_step, rule, price, cost, None))
            elif ma_short is None:
                skipped.append(f"{rule.ma_short}일선 위 조건(분할매수 {next_step}회차 가격은 도달)")
            elif price > ma_short:
                add.append(_add_step_trigger(next_step, rule, price, cost, ma_short))
            else:
                info.append(
                    RuleTrigger(
                        "add_below_ma_short",
                        f"추매가 도달, {rule.ma_short}일선 아래라 보류",
                        f"분할매수 {next_step}회차 가격 {_fmt(add_price)} 이하이지만 "
                        f"현재가가 {rule.ma_short}일 이동평균 {_fmt(ma_short)} 아래",
                        "info",
                    )
                )
        target = rule.target_weight_pct
        if target is not None and position.weight_pct <= target - rule.target_weight_gap_pt + EPS:
            add.append(
                RuleTrigger(
                    "below_target",
                    "목표 비중 미달",
                    f"비중 {position.weight_pct:.1f}% ≤ 목표 {target:g}% "
                    f"− {rule.target_weight_gap_pt:g}%p",
                    "add",
                )
            )
        # The user's rules can contradict each other (a step below the stop-loss, see
        # `RuleSettings.validate_notes`); the cut would come first. Say so.
        if add_price is not None and add_price <= cut_price * (1 + EPS):
            info.append(
                RuleTrigger(
                    "add_below_cut",
                    "다음 추매가가 손절가 아래",
                    f"분할매수 {next_step}회차 가격 {_fmt(add_price)}이 손절가 "
                    f"{_fmt(cut_price)} 아래라 지금 규칙으로는 손절 검토가 먼저 옴",
                    "info",
                )
            )
    if ma_long is None:
        skipped.insert(
            0, f"{rule.ma_long}일 이동평균(봉 {rule.ma_long}개 필요, {len(closes)}개 있음)"
        )
    if skipped:
        info.append(
            RuleTrigger(
                "insufficient_history",
                "이력 부족",
                "확정 봉이 부족해 건너뜀: " + "; ".join(skipped),
                "info",
            )
        )

    # Risk at the stop as a share of equity
    risk_pct: float | None = None
    if equity is not None:
        risk_pct = risk_amount / float(equity) * 100.0
        if risk_pct > settings.max_risk_pct + EPS:
            info.append(
                RuleTrigger(
                    "risk_over_limit",
                    "손절 시 손실이 한도 초과",
                    f"손절 시 손실이 총자산의 {risk_pct:.1f}%로 한도 "
                    f"{settings.max_risk_pct:g}%를 넘습니다",
                    "info",
                )
            )

    blocked, add_cap = blocked_reasons(position, limits)
    notes: list[str] = []
    if limits.book is None:
        notes.append(NO_CASH_NOTE_KO)

    if cut:
        status: Status = "cut"
        chip = "매도 검토"
        if any(t.code == "cut_loss" for t in cut):
            label = "손절 검토"
        elif price > cost:
            label = "이익 보전 검토"
        else:
            label = "추세 이탈 · 매도 검토"
    elif add and not blocked:
        status, label, chip = "add", "추매 검토", "추매 검토"
    else:
        status, label, chip = "hold", "관망", "관망"

    return RuleCheck(
        symbol=position.symbol,
        status=status,
        triggers=tuple(cut + add + info),
        levels=Levels(
            cut_price=cut_price,
            cut_loss_price=cut_loss_price,
            trailing_high=high,
            trailing_stop_price=trailing_stop_price,
            add_price=add_price,
            next_add_step=next_step,
            ma_short=ma_short,
            ma_long=ma_long,
            target_weight_pct=rule.target_weight_pct,
            risk_amount=risk_amount,
        ),
        cut_distance_pct=_pct(cut_price, price),
        add_distance_pct=_pct(add_price, price) if add_price is not None else None,
        blocked_by=blocked,
        add_cap_krw=add_cap,
        as_of=when,
        label_ko=label,
        chip_ko=chip,
        risk_pct_equity=risk_pct,
        weight_room_pt=weight_room_pt(position, limits),
        notes=tuple(notes),
    )


def _add_step_trigger(
    step: int, rule: ResolvedRule, price: float, cost: float, ma_short: float | None
) -> RuleTrigger:
    detail = f"평균단가 대비 {_pct(price, cost):+.1f}% (기준 −{rule.add_step_pct * step:g}%)"
    if ma_short is not None:
        detail += f", {rule.ma_short}일 이동평균 {_fmt(ma_short)} 위"
    return RuleTrigger("add_step", f"분할매수 {step}회차 가격 도달", detail, "add")


# --- forecast range as a reference ---------------------------------------------------


def prob_below(level: float, base_price: float, p10: float, p50: float, p90: float) -> float | None:
    """Approximate probability that the horizon's close ends below `level`, from the three
    forecast quantiles as prices (`services/forecasts.py` reports p10/p50/p90 this way).

    The quantiles become log returns against `base_price` and the CDF is interpolated
    linearly between them at 0.1, 0.5 and 0.9. Beyond q10 or q90 the neighbouring segment's
    slope is extended, and the result is clipped to [PROB_FLOOR, PROB_CEIL]. This is an
    approximation of a distribution known at three points only. The forecaster's range is
    calibrated but its direction has no verified edge (D-018, D-026), so the number is a
    reference for the UI, never a signal, and it is about the close at the end of the
    horizon: the level is touched on the way about twice as often (PROB_CAVEAT_KO). Use
    `prob_below_label` for display; it does not show extrapolated values as numbers. None
    if an input is not a positive finite number or the quantiles are out of order.
    """
    values = (level, base_price, p10, p50, p90)
    if not all(_positive(v) for v in values):
        return None
    level, base_price, p10, p50, p90 = (float(v) for v in values)
    if not p10 <= p50 <= p90:
        return None
    x = math.log(level / base_price)
    q10, q50, q90 = (math.log(p / base_price) for p in (p10, p50, p90))
    if x <= q50:
        lo, hi, p_lo, p_hi = q10, q50, 0.1, 0.5
    else:
        lo, hi, p_lo, p_hi = q50, q90, 0.5, 0.9
    if hi - lo <= 0:  # two equal quantiles: a step at the shared value
        return _clip_prob(p_lo if x < hi else p_hi)
    return _clip_prob(p_lo + (p_hi - p_lo) * (x - lo) / (hi - lo))


def _clip_prob(p: float) -> float:
    return min(max(p, PROB_FLOOR), PROB_CEIL)


def prob_below_label(
    level: float, base_price: float, p10: float, p50: float, p90: float
) -> str | None:
    """`prob_below` as display text. Inside the forecast range (p10 ≤ level ≤ p90) the
    probability is rounded to 5%: "약 N%". Outside it the extrapolated value is not shown as
    a number but as a bucket: "10% 미만" / "90% 초과", or "5% 미만" / "95% 초과" when the
    extrapolation ran into the clip. Show PROB_CAVEAT_KO next to it. None when `prob_below`
    is None."""
    p = prob_below(level, base_price, p10, p50, p90)
    if p is None:
        return None
    if level < p10:
        return "5% 미만" if p <= PROB_FLOOR else "10% 미만"
    if level > p90:
        return "95% 초과" if p >= PROB_CEIL else "90% 초과"
    return f"약 {5 * round(p * 20)}%"
