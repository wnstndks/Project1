"""Portfolio coach: checks of the user's own investment policy (DECISIONS.md D-033).

This is not a strategy and not a signal. The forecaster has no verified edge, so nothing here
says what will go up. The coach takes the policy the user wrote down (asset class targets,
caps, the drawdown they can bear, a goal) and reports where today's holdings stand against it:
weights, concentration, how much the current mix moved in the past, the orders a rebalance to
the targets would mean (sizes and what blocks them, never placed), and habits seen in the
trade log. Every past-data figure carries its window; the UI adds "past results do not
guarantee the future".

Pure functions: no database, no network, no HTTP. Amounts are KRW floats, weights are percent
of equity unless a name says `fraction`. Invalid input (NaN, negative quantities, an empty
frame) fails closed with ValueError, as in `risk.py`. No new symbol is ever introduced: targets
are built only over the holdings passed in, and an asset class the user wants but does not
hold is reported as `unallocated_pct`.

Korean labels live at the top of the module and are used as they are by the service and the
UI (`src/lib/coach.ts`); they avoid "추천·사세요·파세요·오를·예상 수익" by rule.
"""

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd

from app.forecast.aggregate import correlation
from app.forecast.panel import AssetClass
from app.strategy.risk import (
    EPS,
    Book,
    OrderDecision,
    RiskLimits,
    cap_weights,
    max_drawdown,
    rebalance_orders,
)

if TYPE_CHECKING:
    from app.config import Settings

Grid = Literal["stock", "all"]
Severity = Literal["warn", "info"]
TargetSource = Literal["symbol", "remainder", "scaled", "class_zero"]

# Trading days per year by return grid (D-033): stock sessions, or every calendar day when
# only coins are held.
PERIODS_PER_YEAR: dict[Grid, int] = {"stock": 252, "all": 365}
# The project's own strategy limit (D-002); a looser personal tolerance is allowed but noted.
PROJECT_MAX_DRAWDOWN_PCT = 20.0
CLASSES: tuple[str, ...] = ("stock", "crypto", "cash")

# --- Korean labels (single source for the service and src/lib/coach.ts) ----------------

VIOLATION_LABELS_KO: dict[str, str] = {
    "position_over_cap": "종목 비중 상한 초과",
    "crypto_over_cap": "코인 합산 상한 초과",
    "class_drift": "자산군 비중 이탈",
    "drawdown_over_tolerance": "허용 낙폭 초과",
    "total_risk_over_cap": "손절 합산 손실 상한 초과",
    "cash_missing": "현금 미입력",
    "cash_stale": "현금 기준일 오래됨",
    "targets_exceed_class": "종목 목표 합이 자산군 목표를 넘음",
    "kill_switch_tripped": "킬스위치 발동 중",
}
PATTERN_LABELS_KO: dict[str, str] = {
    "chasing_buy": "급등 뒤 매수",
    "averaging_down_below_cut": "손절선 아래 물타기",
    "rule_lag": "손절선 아래 보유 지속",
    "overtrading": "거래 횟수 급증",
    "quick_rebuy_after_loss": "손실 매도 뒤 재매수",
}
CLASS_LABELS_KO: dict[str, str] = {"stock": "주식", "crypto": "코인", "cash": "현금"}
NO_CASH_NOTE_KO = "현금 기록이 없어 매도 대금 범위에서만 매수를 계산했습니다"
CASH_UNKNOWN_TARGET_NOTE_KO = (
    "현금 기록이 없어 자산군 목표를 투자금 기준으로 다시 맞췄습니다(현금 목표는 확인 불가)"
)
NO_PICK_NOTE_KO = "어떤 종목을 살지는 제안하지 않습니다"
REBALANCE_HEADLINE_KO = "내 정책과 지금 비중의 차이예요. 예측이 아니고, 주문은 내지 않습니다."
DISCLAIMER_KO = "투자 조언이 아닙니다. 수수료·세금 미포함."
PAST_CAVEAT_KO = "과거 데이터로 추정한 값이며, 과거는 미래를 보장하지 않습니다."
LOOSER_THAN_PROJECT_KO = "허용 낙폭 {pct}%는 프로젝트 전략 한도(20%)보다 느슨합니다"
GOAL_INCOMPLETE_NOTE_KO = "목표 금액과 목표일을 둘 다 적어야 필요 수익률을 계산합니다"
NOT_A_FORECAST_KO = "산수이지 예측이 아닙니다"
# Risk window names as the UI shows them; `window_label_ko` falls back to the name itself.
WINDOW_LABELS_KO: dict[str, str] = {"1y": "1년", "3y": "3년"}
REMAINDER_ZERO_NOTE_KO = (
    "{cls}에서 목표를 적지 않은 종목 {n}개({symbols})는 종목 목표 합이 자산군 목표를 다 채워 "
    "목표 0%가 됩니다"
)
TWR_NEGATIVE_VALUE_KO = "{day}: 평가액이 음수라 시간가중 지수를 만들 수 없습니다"
TWR_RETURN_FLOOR_KO = (
    "{day}: 입금을 뺀 수익률이 -100% 이하라 시간가중 지수를 만들 수 없습니다"
    "(단가가 틀린 거래가 있는지 거래 페이지에서 확인하세요)"
)


# --- validation helpers -----------------------------------------------------------------


def _finite(x: object) -> bool:
    try:
        return math.isfinite(float(x))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _num(name: str, value: object, *, lo: float | None = None, hi: float | None = None) -> float:
    """`value` as a finite float within [lo, hi]; ValueError otherwise."""
    if isinstance(value, bool) or not _finite(value):
        raise ValueError(f"{name} must be a finite number")
    x = float(value)  # type: ignore[arg-type]
    if lo is not None and x < lo:
        raise ValueError(f"{name} must be >= {lo}")
    if hi is not None and x > hi:
        raise ValueError(f"{name} must be <= {hi}")
    return x


def _open_pct(name: str, value: object) -> float:
    x = _num(name, value)
    if not 0.0 < x < 100.0:
        raise ValueError(f"{name} must be a percentage in (0, 100)")
    return x


def _set(obj: object, name: str, value: object) -> None:
    object.__setattr__(obj, name, value)


def _to_date(d: object) -> date:
    if isinstance(d, pd.Timestamp | datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return pd.Timestamp(d).date()  # type: ignore[arg-type]


def _fmt_pct(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}%"


def window_label_ko(name: str) -> str:
    """The Korean label of a risk window name ("1y" → "1년", "3y" → "3년"); a name without
    a label is returned as it is. Every sentence shown to the user goes through this."""
    return WINDOW_LABELS_KO.get(name, name)


# --- the user's policy -------------------------------------------------------------------


@dataclass(frozen=True)
class Policy:
    """What the user wrote down. Percentages are of total equity (cash included).

    `drawdown_tolerance_pct` is the fall from a peak the user says they can bear; it may be
    looser than the project's 20% strategy limit, which `notes()` points out without blocking
    the number. `max_total_risk_pct` is the loss, as a share of total assets, if every
    stop-loss fired at once. `rebalance_band_pt` is the drift (percentage points) below which
    no rebalance order is proposed. Class targets add up to 100.
    """

    goal_krw: float | None = None
    goal_date: date | None = None
    monthly_contribution_krw: float = 0.0
    drawdown_tolerance_pct: float = 20.0
    max_position_weight_pct: float = 20.0
    max_crypto_weight_pct: float = 30.0
    max_total_risk_pct: float = 8.0
    rebalance_band_pt: float = 5.0
    target_stock_pct: float = 80.0
    target_crypto_pct: float = 20.0
    target_cash_pct: float = 0.0

    def __post_init__(self) -> None:
        for name in (
            "drawdown_tolerance_pct",
            "max_position_weight_pct",
            "max_crypto_weight_pct",
            "max_total_risk_pct",
        ):
            _set(self, name, _open_pct(name, getattr(self, name)))
        band = _num("rebalance_band_pt", self.rebalance_band_pt, lo=0.0)
        if band >= 100.0:
            raise ValueError("rebalance_band_pt must be below 100")
        _set(self, "rebalance_band_pt", band)
        for name in ("target_stock_pct", "target_crypto_pct", "target_cash_pct"):
            _set(self, name, _num(name, getattr(self, name), lo=0.0, hi=100.0))
        total = self.target_stock_pct + self.target_crypto_pct + self.target_cash_pct
        if abs(total - 100.0) > 1e-6:
            raise ValueError(f"Asset class targets must add up to 100 (got {total:g})")
        if self.target_crypto_pct > self.max_crypto_weight_pct + 1e-9:
            raise ValueError("target_crypto_pct must not exceed max_crypto_weight_pct")
        _set(
            self,
            "monthly_contribution_krw",
            _num("monthly_contribution_krw", self.monthly_contribution_krw, lo=0.0),
        )
        if self.goal_krw is not None:
            goal = _num("goal_krw", self.goal_krw)
            if goal <= 0:
                raise ValueError("goal_krw must be positive")
            _set(self, "goal_krw", goal)
        if self.goal_date is not None and not isinstance(self.goal_date, date):
            raise ValueError("goal_date must be a date")

    @classmethod
    def from_config(cls, settings: "Settings") -> "Policy":
        """Defaults before the user saves a policy: the risk limits and strategy budgets.

        The crypto target comes from the strategy budget but never above the coach's crypto
        cap (limits bind, targets yield); whatever the two class budgets leave is cash.
        """
        crypto_cap = float(settings.coach_max_crypto_weight_pct)
        stock = float(settings.strategy_budget_stock) * 100.0
        crypto = min(float(settings.strategy_budget_crypto) * 100.0, crypto_cap)
        cash = max(100.0 - stock - crypto, 0.0)
        return cls(
            drawdown_tolerance_pct=float(settings.risk_max_drawdown) * 100.0,
            max_position_weight_pct=float(settings.risk_max_position_weight) * 100.0,
            max_crypto_weight_pct=crypto_cap,
            max_total_risk_pct=float(settings.coach_max_total_risk_pct),
            rebalance_band_pt=float(settings.rules_target_weight_gap_pt),
            target_stock_pct=stock,
            target_crypto_pct=crypto,
            target_cash_pct=cash,
        )

    def limits(self, base: RiskLimits) -> RiskLimits:
        """`base` with the symbol cap narrowed to the policy's; never widened. The index fund
        cap (SPY, D-025) is left alone."""
        return replace(
            base,
            max_position_weight=min(base.max_position_weight, self.max_position_weight_pct / 100),
        )

    def notes(self) -> list[str]:
        """Plain-language remarks about the policy itself (not about the holdings)."""
        out: list[str] = []
        if self.drawdown_tolerance_pct > PROJECT_MAX_DRAWDOWN_PCT + EPS:
            out.append(LOOSER_THAN_PROJECT_KO.format(pct=f"{self.drawdown_tolerance_pct:g}"))
        if (self.goal_krw is None) != (self.goal_date is None):
            out.append(GOAL_INCOMPLETE_NOTE_KO)
        return out


@dataclass(frozen=True)
class CashRecord:
    """Cash the user typed in (the app cannot see bank or broker balances)."""

    krw: float = 0.0
    usd: float = 0.0
    as_of: date | None = None

    def __post_init__(self) -> None:
        _set(self, "krw", _num("krw", self.krw, lo=0.0))
        _set(self, "usd", _num("usd", self.usd, lo=0.0))
        if self.as_of is not None and not isinstance(self.as_of, date):
            raise ValueError("as_of must be a date")

    def total_krw(self, fx: float) -> float:
        """KRW plus USD at `fx` (KRW per USD)."""
        rate = _num("fx", fx)
        if rate <= 0:
            raise ValueError("fx must be positive")
        return self.krw + self.usd * rate

    def stale(self, today: date, days: int = 30) -> bool:
        """True when the record is older than `days`; False without a date."""
        return self.as_of is not None and (today - self.as_of).days > days


# --- inputs -------------------------------------------------------------------------------


@dataclass(frozen=True)
class HoldingView:
    """One held position as the service builds it from the ledger. `price` is in `currency`,
    the KRW fields at today's rate; `target_pct` is the user's per-symbol target weight
    (percent of equity) from the rule settings, None when not set."""

    symbol: str
    asset_class: AssetClass
    currency: str
    quantity: float
    price: float
    price_krw: float
    value_krw: float
    cost_basis_krw: float
    target_pct: float | None = None

    def __post_init__(self) -> None:
        if self.asset_class not in ("stock", "crypto"):
            raise ValueError(f"{self.symbol}: asset_class must be stock or crypto")
        for name in ("quantity", "price", "price_krw", "value_krw", "cost_basis_krw"):
            _set(self, name, _num(f"{self.symbol}: {name}", getattr(self, name), lo=0.0))
        if self.target_pct is not None:
            _set(
                self,
                "target_pct",
                _num(f"{self.symbol}: target_pct", self.target_pct, lo=0.0, hi=100.0),
            )


@dataclass(frozen=True)
class TradeView:
    """One trade with the position state just before it (the ledger replay knows both)."""

    id: int
    symbol: str
    asset_class: AssetClass
    side: str
    date: date
    quantity: float
    price: float
    currency: str
    avg_cost_before: float | None
    qty_before: float

    def __post_init__(self) -> None:
        if self.side not in ("buy", "sell"):
            raise ValueError(f"trade {self.id}: side must be buy or sell")
        if not isinstance(self.date, date):
            raise ValueError(f"trade {self.id}: date must be a date")
        q = _num(f"trade {self.id}: quantity", self.quantity, lo=0.0)
        if q <= 0:
            raise ValueError(f"trade {self.id}: quantity must be positive")
        _set(self, "quantity", q)
        _set(self, "price", _num(f"trade {self.id}: price", self.price, lo=0.0))
        _set(self, "qty_before", _num(f"trade {self.id}: qty_before", self.qty_before, lo=0.0))
        if self.avg_cost_before is not None:
            _set(
                self,
                "avg_cost_before",
                _num(f"trade {self.id}: avg_cost_before", self.avg_cost_before, lo=0.0),
            )


# --- weights, concentration, exposure --------------------------------------------------------


@dataclass(frozen=True)
class Weights:
    """One holding's share of equity (`weight_pct`, cash included when known) and of the
    invested amount alone (`invested_weight_pct`, cash is not a bet)."""

    symbol: str
    asset_class: AssetClass
    currency: str
    value_krw: float
    weight_pct: float
    invested_weight_pct: float
    target_pct: float | None


@dataclass(frozen=True)
class Concentration:
    """Invested-basis concentration: largest holding, top three, HHI and 1/HHI."""

    count: int
    top1_symbol: str | None
    top1_pct: float
    top3_pct: float
    hhi: float
    effective_n: float


@dataclass(frozen=True)
class Exposure:
    """Share of equity by asset class and in USD-denominated holdings. `cash_pct` is None
    when no cash record exists; then every share is of the invested amount."""

    equity_krw: float
    invested_krw: float
    stock_pct: float
    crypto_pct: float
    cash_pct: float | None
    usd_pct: float


def _check_holdings(holdings: Sequence[HoldingView]) -> None:
    seen: set[str] = set()
    for h in holdings:
        if h.symbol in seen:
            raise ValueError(f"{h.symbol} appears twice in holdings")
        seen.add(h.symbol)


def _cash(cash_krw: float | None) -> float | None:
    return None if cash_krw is None else _num("cash_krw", cash_krw, lo=0.0)


def weights(holdings: Sequence[HoldingView], cash_krw: float | None) -> list[Weights]:
    """Each holding's weight on both bases, in the order given. With no cash record the
    equity base is the invested amount, so both weights agree."""
    _check_holdings(holdings)
    cash = _cash(cash_krw)
    invested = sum(h.value_krw for h in holdings)
    equity = invested + (cash or 0.0)
    out: list[Weights] = []
    for h in holdings:
        out.append(
            Weights(
                symbol=h.symbol,
                asset_class=h.asset_class,
                currency=h.currency,
                value_krw=h.value_krw,
                weight_pct=h.value_krw / equity * 100 if equity > 0 else 0.0,
                invested_weight_pct=h.value_krw / invested * 100 if invested > 0 else 0.0,
                target_pct=h.target_pct,
            )
        )
    return out


def concentration(invested: Sequence[Weights]) -> Concentration:
    """Concentration of the invested amount (HHI = Σ wᵢ² over fractions; 1/HHI is how many
    equal-sized holdings would be as concentrated)."""
    shares = sorted((w.invested_weight_pct / 100 for w in invested), reverse=True)
    for s in shares:
        if not _finite(s) or s < 0:
            raise ValueError("invested_weight_pct must be non-negative numbers")
    hhi = float(sum(s * s for s in shares))
    top = max(invested, key=lambda w: w.invested_weight_pct, default=None)
    return Concentration(
        count=len(shares),
        top1_symbol=top.symbol if top is not None else None,
        top1_pct=shares[0] * 100 if shares else 0.0,
        top3_pct=sum(shares[:3]) * 100,
        hhi=hhi,
        effective_n=1.0 / hhi if hhi > 0 else 0.0,
    )


def exposure(holdings: Sequence[HoldingView], cash_krw: float | None) -> Exposure:
    """Shares of equity by asset class, cash, and USD-denominated holdings (currency risk is
    inside the KRW figures, so it is shown separately). USD cash is not counted in `usd_pct`;
    the cash record is a KRW total here."""
    _check_holdings(holdings)
    cash = _cash(cash_krw)
    invested = sum(h.value_krw for h in holdings)
    equity = invested + (cash or 0.0)

    def share(amount: float) -> float:
        return amount / equity * 100 if equity > 0 else 0.0

    return Exposure(
        equity_krw=equity,
        invested_krw=invested,
        stock_pct=share(sum(h.value_krw for h in holdings if h.asset_class == "stock")),
        crypto_pct=share(sum(h.value_krw for h in holdings if h.asset_class == "crypto")),
        cash_pct=None if cash is None else share(cash),
        usd_pct=share(sum(h.value_krw for h in holdings if h.currency == "USD")),
    )


# --- returns in KRW -------------------------------------------------------------------------


def _as_series(name: str, s: pd.Series) -> pd.Series:
    """`s` as a float series on a normalized, sorted, duplicate-free DatetimeIndex. NaN or
    infinite values fail closed; an empty series is allowed (a symbol with no bars)."""
    if not isinstance(s, pd.Series):
        raise ValueError(f"{name}: expected a pandas Series")
    if s.empty:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    values = pd.to_numeric(s, errors="coerce").astype(float).to_numpy()
    if not np.isfinite(values).all():
        raise ValueError(f"{name}: closes have missing or infinite values")
    index = pd.DatetimeIndex(pd.to_datetime(s.index)).normalize()
    out = pd.Series(values, index=index).sort_index()
    return out[~out.index.duplicated(keep="last")]


def _on_grid(s: pd.Series, grid: pd.DatetimeIndex) -> pd.Series:
    """`s` at each grid date: the last value on or before it (NaN before the first bar)."""
    if s.empty:
        return pd.Series(np.nan, index=grid, dtype=float)
    return s.reindex(grid.union(s.index)).ffill().reindex(grid)


def choose_grid(asset_class: Mapping[str, AssetClass]) -> tuple[Grid, int]:
    """The return grid for these holdings and its periods per year: stock sessions when any
    stock is held (coins forward-filled, Monday carries the weekend), else every day."""
    grid: Grid = "stock" if any(c == "stock" for c in asset_class.values()) else "all"
    return grid, PERIODS_PER_YEAR[grid]


def krw_return_frame(
    closes: Mapping[str, pd.Series],
    fx: pd.Series,
    currency: Mapping[str, str],
    grid: Grid | pd.DatetimeIndex | Sequence[date],
    *,
    asset_class: Mapping[str, AssetClass] | None = None,
) -> pd.DataFrame:
    """Daily simple returns of each symbol in KRW (columns = symbols, index = grid dates).

    USD closes are multiplied by the USD/KRW rate of the same date (last known rate on or
    before it); KRW closes are used as they are. `grid` is "stock" (union of the dates with a
    stock bar; needs `asset_class`), "all" (union of every symbol's dates) or an explicit set
    of dates. Prices are forward-filled onto the grid so a coin's Monday return covers the
    weekend; before a symbol's first bar its returns are NaN (short history, reported by
    `risk_window`). The first grid date has no return and is dropped.
    """
    if not closes:
        raise ValueError("closes is empty")
    series = {sym: _as_series(sym, s) for sym, s in closes.items()}
    for sym in series:
        if sym not in currency:
            raise ValueError(f"{sym}: currency is unknown")
        if currency[sym] not in ("USD", "KRW"):
            raise ValueError(f"{sym}: currency must be USD or KRW")
    rate = _as_series("fx", fx)
    if not (rate.empty or (rate > 0).all()):
        raise ValueError("fx: rates must be positive")
    if rate.empty and any(currency[s] == "USD" for s in series):
        raise ValueError("fx is empty but a USD symbol needs it")

    if isinstance(grid, str):
        if grid == "stock":
            if asset_class is None:
                raise ValueError('grid="stock" needs asset_class')
            members = [s for s in series if asset_class.get(s) == "stock"]
            if not members:
                raise ValueError('grid="stock" but no symbol is a stock; use grid="all"')
        elif grid == "all":
            members = list(series)
        else:
            raise ValueError('grid must be "stock", "all" or dates')
        dates = pd.DatetimeIndex([])
        for s in members:
            dates = dates.union(series[s].index)
    else:
        dates = pd.DatetimeIndex(pd.to_datetime(list(grid))).normalize().unique().sort_values()
    if len(dates) < 2:
        raise ValueError("fewer than two grid dates: no returns can be computed")

    fx_on_grid = _on_grid(rate, dates) if not rate.empty else None
    prices = {}
    for sym, s in series.items():
        p = _on_grid(s, dates)
        if currency[sym] == "USD":
            p = p * fx_on_grid
        prices[sym] = p
    frame = pd.DataFrame(prices, index=dates)
    returns = frame / frame.shift(1) - 1.0
    return returns.iloc[1:]


# --- portfolio risk from past returns -----------------------------------------------------------


@dataclass(frozen=True)
class Excluded:
    """A symbol left out of a window for having fewer finite returns than `min_rows`."""

    symbol: str
    bars: int


@dataclass(frozen=True)
class RiskWindow:
    """Volatility and fixed-weight drawdown of the current mix over one past window.

    `weights_pct` and `equity_krw` share one base (equity with cash, or invested only): the
    cash share earns zero, so `annual_vol_pct` and `max_drawdown_pct` are of that base and
    `swing_1sigma_krw = annual_vol × equity_krw`. Symbols with too short a history are
    `excluded`; the others stand in for the whole invested part (renormalised), and
    `coverage_pct` says how much of the invested weight they cover.

    `start`/`end` are the first and last return dates. The index starts at 1.0 on the bar
    before `start`, which is not in the frame: when the deepest fall began there,
    `drawdown_peak` is None and `peak_at_window_start` is True ("창 시작부터").
    """

    name: str
    grid: str
    periods_per_year: int
    rows: int
    start: date | None
    end: date | None
    annual_vol_pct: float
    swing_1sigma_krw: float
    max_drawdown_pct: float
    drawdown_peak: date | None
    drawdown_trough: date | None
    coverage_pct: float
    included: tuple[str, ...]
    excluded: tuple[Excluded, ...]
    method: str
    usable: bool
    reason: str | None
    # Last, with a default, so callers that build a RiskWindow by hand keep working.
    peak_at_window_start: bool = False


def _check_returns(returns: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(returns, pd.DataFrame):
        raise ValueError("returns must be a DataFrame")
    if returns.empty:
        raise ValueError("returns is empty")
    if returns.columns.duplicated().any():
        raise ValueError("returns has duplicate columns")
    frame = returns.astype(float)
    if np.isinf(frame.to_numpy()).any():
        raise ValueError("returns have infinite values")
    return frame


def _drawdown_points(index: pd.Series) -> tuple[float, date | None, date | None, bool]:
    """Max drawdown of the fixed-weight index with the dates of its peak and trough. Row 0 is
    the 1.0 start, whose date is the first return's (the real bar is the one before, which
    the frame does not hold): a peak there has no date and sets the `at_start` flag."""
    values = index.to_numpy(dtype=float)
    dd = max_drawdown(values)
    if dd <= 0 or len(values) == 0:
        return dd, None, None, False
    peaks = np.maximum.accumulate(values)
    falls = np.where(peaks > 0, 1 - values / peaks, 0.0)
    trough = int(np.argmax(falls))
    peak = int(np.argmax(values[: trough + 1]))
    trough_date = _to_date(index.index[trough])
    if peak == 0:
        return dd, None, trough_date, True
    return dd, _to_date(index.index[peak]), trough_date, False


def risk_window(
    returns: pd.DataFrame,
    weights_pct: Mapping[str, float],
    equity_krw: float,
    *,
    name: str,
    periods_per_year: int,
    min_rows: int = 120,
    min_coverage: float = 0.75,
    grid: str | None = None,
) -> RiskWindow:
    """Risk of holding today's weights through the past returns in `returns` (already cut to
    the window).

    Σ = D·C·D with C the shrunk correlation (`aggregate.correlation`, identity when the
    window has fewer than `min_rows` common rows) and D the sample standard deviations;
    `annual_vol = √(wᵀΣw)·√periods_per_year`. The drawdown is that of the fixed-weight index
    `Π(1 + Σᵢ wᵢ rᵢₜ)` (rebalanced daily, costs ignored). Not usable when the included
    symbols cover less than `min_coverage` of the invested weight or fewer than `min_rows`
    rows remain; the reason is spelled out in Korean. Nothing is replaced by a proxy.
    """
    frame = _check_returns(returns)
    equity = _num("equity_krw", equity_krw, lo=0.0)
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    grid_name = grid or ("stock" if periods_per_year == PERIODS_PER_YEAR["stock"] else "all")
    w_all = {s: _num(f"weights_pct[{s}]", w, lo=0.0) for s, w in weights_pct.items()}
    held = {s: w for s, w in w_all.items() if w > 0}

    included: list[str] = []
    excluded: list[Excluded] = []
    for s in held:
        bars = int(np.isfinite(frame[s].to_numpy()).sum()) if s in frame.columns else 0
        if bars >= min_rows:
            included.append(s)
        else:
            excluded.append(Excluded(s, bars))
    total = sum(held.values())
    covered = sum(held[s] for s in included)
    coverage_pct = covered / total * 100 if total > 0 else 0.0

    def empty(reason: str) -> RiskWindow:
        return RiskWindow(
            name=name,
            grid=grid_name,
            periods_per_year=periods_per_year,
            rows=0,
            start=None,
            end=None,
            annual_vol_pct=0.0,
            swing_1sigma_krw=0.0,
            max_drawdown_pct=0.0,
            drawdown_peak=None,
            drawdown_trough=None,
            peak_at_window_start=False,
            coverage_pct=coverage_pct,
            included=tuple(included),
            excluded=tuple(excluded),
            method="none",
            usable=False,
            reason=reason,
        )

    if not held:
        return empty("보유 종목이 없습니다")
    if not included:
        short = ", ".join(e.symbol for e in excluded)
        return empty(f"모든 종목의 이력이 {min_rows}일보다 짧습니다({short})")

    data = frame[included].dropna()
    rows = len(data)
    if rows < 2:
        return empty(f"겹치는 날이 {rows}일로 계산할 수 없습니다")

    # The included symbols stand in for the whole invested part; cash (the rest of the base)
    # earns zero.
    w = np.array([held[s] / covered * (total / 100.0) for s in included])
    sigma = data.std(ddof=1).to_numpy(dtype=float)
    if len(included) == 1:
        method = "single"
        corr = np.eye(1)
    else:
        corr = correlation(data, min_rows)
        method = "ledoit_wolf" if rows >= min_rows else "identity"
    cov = np.outer(sigma, sigma) * corr
    variance = float(w @ cov @ w)
    annual_vol = math.sqrt(max(variance, 0.0)) * math.sqrt(periods_per_year)

    portfolio = data.to_numpy(dtype=float) @ w
    index = pd.Series(np.cumprod(1.0 + portfolio), index=data.index)
    index = pd.concat([pd.Series([1.0], index=[data.index[0]]), index])
    dd, peak, trough, peak_at_start = _drawdown_points(index)

    reasons: list[str] = []
    if coverage_pct < min_coverage * 100 - EPS:
        short = ", ".join(e.symbol for e in excluded)
        reasons.append(
            f"이력이 {min_rows}일보다 짧은 종목({short})을 빼면 비중의 "
            f"{coverage_pct:.0f}%만 남아 {min_coverage:.0%}에 못 미칩니다"
        )
    if rows < min_rows:
        reasons.append(f"겹치는 날이 {rows}일로 {min_rows}일보다 적습니다")
    return RiskWindow(
        name=name,
        grid=grid_name,
        periods_per_year=periods_per_year,
        rows=rows,
        start=_to_date(data.index[0]),
        end=_to_date(data.index[-1]),
        annual_vol_pct=annual_vol * 100,
        swing_1sigma_krw=annual_vol * equity,
        max_drawdown_pct=dd * 100,
        drawdown_peak=peak,
        drawdown_trough=trough,
        peak_at_window_start=peak_at_start,
        coverage_pct=coverage_pct,
        included=tuple(included),
        excluded=tuple(excluded),
        method=method,
        usable=not reasons,
        reason="; ".join(reasons) if reasons else None,
    )


@dataclass(frozen=True)
class CorrelationTable:
    """Shrunk correlation of the symbols with enough rows; `excluded` had fewer."""

    symbols: tuple[str, ...]
    matrix: tuple[tuple[float, ...], ...]
    method: str
    rows: int
    excluded: tuple[str, ...]


def correlation_table(returns: pd.DataFrame, min_rows: int = 120) -> CorrelationTable:
    """Pairwise correlation of daily returns for the UI heatmap (Ledoit-Wolf shrinkage; the
    identity when fewer than `min_rows` common rows remain)."""
    frame = _check_returns(returns)
    counts = {c: int(np.isfinite(frame[c].to_numpy()).sum()) for c in frame.columns}
    symbols = [c for c in frame.columns if counts[c] >= min_rows]
    excluded = tuple(c for c in frame.columns if counts[c] < min_rows)
    if not symbols:
        return CorrelationTable((), (), "none", 0, excluded)
    data = frame[symbols].dropna()
    rows = len(data)
    if len(symbols) == 1:
        corr, method = np.eye(1), "single"
    elif rows < min_rows:
        corr, method = np.eye(len(symbols)), "identity"
    else:
        corr, method = correlation(data, min_rows), "ledoit_wolf"
    matrix = tuple(tuple(float(x) for x in row) for row in corr)
    return CorrelationTable(tuple(symbols), matrix, method, rows, excluded)


@dataclass(frozen=True)
class Beta:
    """OLS slope of a symbol's returns on a benchmark's, with the fit's r² and row count."""

    beta: float
    r2: float
    rows: int


def beta(y: pd.Series, x: pd.Series, min_rows: int = 60) -> Beta | None:
    """`cov(y, x) / var(x)` on the dates both have; None with fewer than `min_rows` common
    rows or a flat benchmark. Pass returns in one currency so the rate does not enter."""
    ys, xs = y.astype(float), x.astype(float)
    if np.isinf(ys.to_numpy()).any() or np.isinf(xs.to_numpy()).any():
        raise ValueError("returns have infinite values")
    both = pd.concat([ys.rename("y"), xs.rename("x")], axis=1, join="inner").dropna()
    rows = len(both)
    if rows < max(min_rows, 2):
        return None
    var_x = float(both["x"].var(ddof=1))
    # A constant non-zero benchmark has a variance of about 1e-36, not 0, so "flat" is judged
    # relative to the size of x (mean of x²), not against exact zero.
    scale = float((both["x"] ** 2).mean())
    if not math.isfinite(var_x) or var_x <= 1e-12 * max(scale, 1e-300):
        return None
    cov = float(both["y"].cov(both["x"]))
    var_y = float(both["y"].var(ddof=1))
    r2 = cov * cov / (var_x * var_y) if var_y > 0 else 0.0
    return Beta(beta=cov / var_x, r2=r2, rows=rows)


# --- the actual value curve ---------------------------------------------------------------------


def _aligned(values: pd.Series, flows: pd.Series | None) -> tuple[pd.Series, np.ndarray]:
    """`values` on a normalized DatetimeIndex and the flow of each of its days (0 where
    none), whether the two were indexed by Timestamps or by dates."""
    if not isinstance(values, pd.Series):
        raise ValueError("values must be a Series")
    if values.empty:
        raise ValueError("values is empty")
    data = values.astype(float).to_numpy()
    if not np.isfinite(data).all():
        raise ValueError("values have missing or infinite values")
    index = pd.DatetimeIndex(pd.to_datetime(values.index)).normalize()
    if index.duplicated().any():
        raise ValueError("values has duplicate dates")
    v = pd.Series(data, index=index).sort_index()
    if flows is None or flows.empty:
        return v, np.zeros(len(v))
    f = flows.astype(float)
    if not np.isfinite(f.to_numpy()).all():
        raise ValueError("flows have missing or infinite values")
    f.index = pd.DatetimeIndex(pd.to_datetime(f.index)).normalize()
    f = f.groupby(level=0).sum().reindex(v.index).fillna(0.0)
    return v, f.to_numpy(dtype=float)


def twr_index(values: pd.Series, flows: pd.Series | None = None) -> pd.Series:
    """Time-weighted index of a value curve, 1.0 on the first date.

    `r_d = (V_d − V_{d−1} − f_d) / V_{d−1}` with `f_d` the net cash that entered that day
    (buys positive, sells negative), so deposits do not look like gains. A day after a zero
    value (nothing was held; the curve starts again) counts as 0. Drawdowns and kill-switch
    triggers are then read off this index (`risk.max_drawdown`, `risk.kill_switch_triggers`),
    for information only.

    Fails closed rather than producing an index at or below zero: a negative value, or a day
    with `V_{d−1} > 0` whose `1 + r_d = (V_d − f_d) / V_{d−1}` is not positive (the day's
    deposit alone is at least the value, as happens when an imported trade's price is off by
    orders of magnitude), raises ValueError naming the date, and the caller shows the reason
    instead of a drawdown figure.
    """
    v, f = _aligned(values, flows)
    vals = v.to_numpy(dtype=float)
    negative = np.flatnonzero(vals < 0)
    if len(negative):
        raise ValueError(TWR_NEGATIVE_VALUE_KO.format(day=_to_date(v.index[int(negative[0])])))
    prev = vals[:-1]
    after = vals[1:] - f[1:]  # V_d − f_d = V_{d−1} · (1 + r_d)
    floored = np.flatnonzero((prev > 0) & (after <= 0))
    if len(floored):
        day = _to_date(v.index[int(floored[0]) + 1])
        raise ValueError(TWR_RETURN_FLOOR_KO.format(day=day))
    r = np.zeros(len(vals))
    with np.errstate(divide="ignore", invalid="ignore"):
        r[1:] = np.where(prev > 0, after / prev - 1.0, 0.0)
    return pd.Series(np.cumprod(1.0 + r), index=v.index)


@dataclass(frozen=True)
class PeriodReview:
    """Change of the value curve over (start, end] split into cash put in and market result."""

    start: date
    end: date
    start_point: date | None
    end_point: date
    start_value_krw: float
    end_value_krw: float
    change_krw: float
    contributions_krw: float
    market_pnl_krw: float


def period_review(
    history: pd.Series, flows: pd.Series | None, start: date, end: date
) -> PeriodReview:
    """Value at the last point on or before `start` and on or before `end`, the net cash
    that entered in (start, end], and `market_pnl = change − contributions`. With no point on
    or before `start` the start value is 0 (nothing was held yet), so the first buy counts as
    a contribution and not as a market gain."""
    if end < start:
        raise ValueError("end must not be before start")
    h = history.astype(float)
    if h.empty:
        raise ValueError("history is empty")
    if not np.isfinite(h.to_numpy()).all():
        raise ValueError("history has missing or infinite values")
    dates = [_to_date(d) for d in h.index]
    h = pd.Series(h.to_numpy(dtype=float), index=dates).sort_index()
    before_start = h[[d <= start for d in h.index]]
    before_end = h[[d <= end for d in h.index]]
    if before_end.empty:
        raise ValueError("history has no point on or before end")
    start_point = _to_date(before_start.index[-1]) if not before_start.empty else None
    start_value = float(before_start.iloc[-1]) if not before_start.empty else 0.0
    end_value = float(before_end.iloc[-1])
    contributions = 0.0
    if flows is not None and not flows.empty:
        f = flows.astype(float)
        if not np.isfinite(f.to_numpy()).all():
            raise ValueError("flows have missing or infinite values")
        for d, amount in f.items():
            when = _to_date(d)
            if start < when <= end:
                contributions += float(amount)
    change = end_value - start_value
    return PeriodReview(
        start=start,
        end=end,
        start_point=start_point,
        end_point=_to_date(before_end.index[-1]),
        start_value_krw=start_value,
        end_value_krw=end_value,
        change_krw=change,
        contributions_krw=contributions,
        market_pnl_krw=change - contributions,
    )


# --- targets and rebalancing -----------------------------------------------------------------


@dataclass(frozen=True)
class TargetPlan:
    """Target weights over the current holdings only (fractions of equity, sum ≤ 1).

    `source[symbol]`: "symbol" (the user's own target), "remainder" (the class target left
    after explicit ones, split by current value), "scaled" (explicit targets scaled to fit
    the class), "class_zero" (the class target is 0, so the position is to be closed).
    `class_targets` are percent of equity as used (cash None when no cash record).
    `unallocated_pct` is class target with no holding behind it; it stays cash.
    """

    targets: dict[str, float]
    source: dict[str, TargetSource]
    class_targets: dict[str, float | None]
    unallocated_pct: float
    capped: tuple[str, ...]
    notes: tuple[str, ...] = ()


def cap_class_weights(
    target: Mapping[str, float], asset_class: Mapping[str, str], caps: Mapping[str, float]
) -> dict[str, float]:
    """Scale each asset class's weights down proportionally when their sum exceeds the
    class's cap (fractions). Classes without a cap are untouched."""
    out: dict[str, float] = {}
    for s, w in target.items():
        out[s] = _num(f"target[{s}]", w, lo=0.0)
        if s not in asset_class:
            raise ValueError(f"{s}: asset_class is unknown")
    for cls, cap in caps.items():
        limit = _num(f"caps[{cls}]", cap, lo=0.0)
        members = [s for s in out if asset_class[s] == cls]
        total = sum(out[s] for s in members)
        if total > limit + EPS and total > 0:
            scale = limit / total
            for s in members:
                out[s] *= scale
    return out


def _class_targets(policy: Policy, cash_known: bool) -> dict[str, float | None]:
    """Class targets in percent of the base: as written when cash is known; otherwise stock
    and crypto renormalised to the invested amount and cash unknown."""
    if cash_known:
        return {
            "stock": policy.target_stock_pct,
            "crypto": policy.target_crypto_pct,
            "cash": policy.target_cash_pct,
        }
    invested = policy.target_stock_pct + policy.target_crypto_pct
    if invested <= 0:
        return {"stock": 0.0, "crypto": 0.0, "cash": None}
    return {
        "stock": policy.target_stock_pct / invested * 100,
        "crypto": policy.target_crypto_pct / invested * 100,
        "cash": None,
    }


def _remainder_zero_note(label: str, rest: Sequence[HoldingView]) -> str:
    """Note for symbols without a target that end at 0% because the explicit targets of
    their class already fill the class target."""
    return REMAINDER_ZERO_NOTE_KO.format(
        cls=label, n=len(rest), symbols=", ".join(h.symbol for h in rest)
    )


def construct_targets(
    holdings: Sequence[HoldingView], policy: Policy, limits: RiskLimits, *, cash_known: bool
) -> TargetPlan:
    """Target weights from the policy's class targets and the user's per-symbol targets,
    over the holdings passed in and nothing else.

    Per class: explicit symbol targets (percent of equity) are kept; if they exceed the
    class target they are scaled down (note `targets_exceed_class`); what the class has left
    goes to the symbols without a target in proportion to their current value; if every
    symbol has a target and they fall short, they are scaled up (note). When the explicit
    targets already fill (or exceed) the class, the symbols without a target get 0, which a
    rebalance reads as closing them, so a note names them. A class target with no holding
    behind it becomes `unallocated_pct`. Then `cap_class_weights` applies the crypto cap and
    `risk.cap_weights` the symbol caps and the no-leverage rule.
    """
    _check_holdings(holdings)
    classes = _class_targets(policy, cash_known)
    pct: dict[str, float] = {}
    source: dict[str, TargetSource] = {}
    notes: list[str] = []
    unallocated = 0.0
    if not cash_known:
        notes.append(CASH_UNKNOWN_TARGET_NOTE_KO)

    for cls in ("stock", "crypto"):
        target = classes[cls] or 0.0
        members = [h for h in holdings if h.asset_class == cls]
        label = CLASS_LABELS_KO[cls]
        if not members:
            if target > EPS:
                unallocated += target
                notes.append(
                    f"{label} 목표 {target:g}%가 있지만 보유가 없습니다. {NO_PICK_NOTE_KO}"
                )
            continue
        if target <= EPS:
            for h in members:
                pct[h.symbol], source[h.symbol] = 0.0, "class_zero"
            continue
        explicit = {h.symbol: h.target_pct for h in members if h.target_pct is not None}
        rest = [h for h in members if h.target_pct is None]
        total_explicit = sum(explicit.values())
        if total_explicit > target + EPS:
            scale = target / total_explicit
            for s, t in explicit.items():
                pct[s], source[s] = t * scale, "scaled"
            for h in rest:
                pct[h.symbol], source[h.symbol] = 0.0, "remainder"
            notes.append(
                f"{label} 종목 목표의 합 {total_explicit:g}%가 자산군 목표 {target:g}%를 넘어 "
                f"비례로 줄였습니다"
            )
            if rest:
                notes.append(_remainder_zero_note(label, rest))
        elif rest:
            for s, t in explicit.items():
                pct[s], source[s] = t, "symbol"
            remainder = max(target - total_explicit, 0.0)
            value = sum(h.value_krw for h in rest)
            for h in rest:
                share = h.value_krw / value if value > 0 else 1.0 / len(rest)
                pct[h.symbol], source[h.symbol] = remainder * share, "remainder"
            if remainder <= EPS:
                notes.append(_remainder_zero_note(label, rest))
        elif total_explicit <= EPS:
            for s in explicit:
                pct[s], source[s] = 0.0, "symbol"
            unallocated += target
            notes.append(
                f"{label} 종목 목표가 모두 0%라 자산군 목표 {target:g}%를 배분하지 못했습니다"
            )
        elif total_explicit < target - EPS:
            scale = target / total_explicit
            for s, t in explicit.items():
                pct[s], source[s] = t * scale, "scaled"
            notes.append(
                f"{label} 종목 목표의 합 {total_explicit:g}%가 자산군 목표 {target:g}%에 못 미쳐 "
                f"비례로 늘렸습니다"
            )
        else:
            for s, t in explicit.items():
                pct[s], source[s] = t, "symbol"

    fractions = {s: v / 100 for s, v in pct.items()}
    asset_class = {h.symbol: h.asset_class for h in holdings}
    after_class = cap_class_weights(
        fractions, asset_class, {"crypto": policy.max_crypto_weight_pct / 100}
    )
    final = cap_weights(after_class, limits)
    capped = tuple(s for s in final if final[s] < fractions[s] - EPS)
    left = sum(fractions.values()) - sum(final.values())
    if left > EPS:
        notes.append(f"비중 상한으로 {left * 100:.1f}%p가 현금으로 남습니다")
    return TargetPlan(
        targets=final,
        source=source,
        class_targets=classes,
        unallocated_pct=unallocated,
        capped=capped,
        notes=tuple(notes),
    )


def rebalance_plan(
    book: Book, plan: TargetPlan, limits: RiskLimits, band_pt: float
) -> list[OrderDecision]:
    """Checked orders from `book` to `plan.targets` (sells first, each checked against the
    book as updated by the previous ones), skipping changes smaller than `band_pt` percent
    of equity. Positions whose target is 0 are sold in full. Fees are 0 here; the UI says so.
    Nothing is executed."""
    band = _num("band_pt", band_pt, lo=0.0)
    return rebalance_orders(book, plan.targets, limits, min_notional=band / 100 * book.equity)


# --- policy violations -------------------------------------------------------------------------


@dataclass(frozen=True)
class Violation:
    """One policy check that is not met. `subject` is the symbol or asset class concerned."""

    code: str
    severity: Severity
    label_ko: str
    detail: str
    value: float | None
    limit: float | None
    subject: str | None = None


def _violation(
    code: str,
    severity: Severity,
    detail: str,
    value: float | None,
    limit: float | None,
    subject: str | None = None,
) -> Violation:
    return Violation(code, severity, VIOLATION_LABELS_KO[code], detail, value, limit, subject)


def violations(
    policy: Policy,
    weights: Sequence[Weights],
    exposure: Exposure,
    risk3y: RiskWindow | None,
    total_risk_pct: float | None,
    cash: CashRecord | None,
    today: date,
    kill_tripped: bool,
    limits: RiskLimits,
) -> list[Violation]:
    """Everything in the current state that breaks the policy, warnings first.

    `limits` should already be `policy.limits(base)`. `total_risk_pct` is the loss if every
    stop-loss fired, as a share of total assets (from the rule checks); None skips the check.
    `risk3y` is checked only when usable. Cash remarks are informational.
    """
    out: list[Violation] = []
    for w in weights:
        cap = limits.symbol_cap(w.symbol) * 100
        if w.weight_pct > cap + EPS:
            out.append(
                _violation(
                    "position_over_cap",
                    "warn",
                    f"{w.symbol} 비중 {_fmt_pct(w.weight_pct)}가 상한 {_fmt_pct(cap, 0)}를 넘음",
                    w.weight_pct,
                    cap,
                    w.symbol,
                )
            )
    if exposure.crypto_pct > policy.max_crypto_weight_pct + EPS:
        out.append(
            _violation(
                "crypto_over_cap",
                "warn",
                f"코인 합산 비중 {_fmt_pct(exposure.crypto_pct)}가 상한 "
                f"{_fmt_pct(policy.max_crypto_weight_pct, 0)}를 넘습니다",
                exposure.crypto_pct,
                policy.max_crypto_weight_pct,
                "crypto",
            )
        )
    classes = _class_targets(policy, cash is not None)
    actual = {"stock": exposure.stock_pct, "crypto": exposure.crypto_pct, "cash": exposure.cash_pct}
    for cls in CLASSES:
        target, now = classes[cls], actual[cls]
        if target is None or now is None:
            continue
        drift = now - target
        if abs(drift) > policy.rebalance_band_pt + EPS:
            out.append(
                _violation(
                    "class_drift",
                    "warn",
                    f"{CLASS_LABELS_KO[cls]} 비중 {_fmt_pct(now)}가 목표 {_fmt_pct(target)}에서 "
                    f"{drift:+.1f}%p 벗어났습니다(허용 ±{policy.rebalance_band_pt:g}%p)",
                    now,
                    target,
                    cls,
                )
            )
    if (
        risk3y is not None
        and risk3y.usable
        and risk3y.max_drawdown_pct > policy.drawdown_tolerance_pct + EPS
    ):
        out.append(
            _violation(
                "drawdown_over_tolerance",
                "warn",
                f"지금 구성으로 지난 {window_label_ko(risk3y.name)}을 지났다면 가장 깊은 하락이 "
                f"{_fmt_pct(risk3y.max_drawdown_pct)}로, 적어 둔 허용 낙폭 "
                f"{_fmt_pct(policy.drawdown_tolerance_pct, 0)}를 넘습니다",
                risk3y.max_drawdown_pct,
                policy.drawdown_tolerance_pct,
                risk3y.name,
            )
        )
    if total_risk_pct is not None:
        risk = _num("total_risk_pct", total_risk_pct)
        if risk > policy.max_total_risk_pct + EPS:
            out.append(
                _violation(
                    "total_risk_over_cap",
                    "warn",
                    f"모든 손절선이 닿으면 총자산의 {_fmt_pct(risk)}를 잃어 상한 "
                    f"{_fmt_pct(policy.max_total_risk_pct, 0)}를 넘습니다",
                    risk,
                    policy.max_total_risk_pct,
                )
            )
    if cash is None:
        out.append(
            _violation(
                "cash_missing",
                "info",
                "현금을 적지 않아 비중과 자산군 목표를 투자금 기준으로 계산했습니다",
                None,
                None,
            )
        )
    elif cash.stale(today):
        age = (today - cash.as_of).days if cash.as_of is not None else None
        out.append(
            _violation(
                "cash_stale",
                "info",
                f"현금 기준일이 {age}일 지났습니다. 최신 잔고로 갱신해 주세요",
                float(age) if age is not None else None,
                30.0,
            )
        )
    for cls in ("stock", "crypto"):
        target = classes[cls]
        explicit = sum(w.target_pct for w in weights if w.asset_class == cls and w.target_pct)
        if target is not None and explicit > target + EPS:
            out.append(
                _violation(
                    "targets_exceed_class",
                    "info",
                    f"{CLASS_LABELS_KO[cls]} 종목 목표의 합 {explicit:g}%가 자산군 목표 "
                    f"{target:g}%를 넘어 비례로 줄여 적용했습니다",
                    explicit,
                    target,
                    cls,
                )
            )
    if kill_tripped:
        out.append(
            _violation(
                "kill_switch_tripped",
                "info",
                "킬스위치가 켜져 있어 모의투자의 신호와 주문이 멈춰 있습니다",
                None,
                None,
            )
        )
    return out


# --- goal arithmetic ------------------------------------------------------------------------------


def _goal_gap(current: float, monthly: float, goal: float, years: float, r: float) -> float:
    growth = (1.0 + r) ** years
    # r → 0: the annuity factor ((1+r)^n − 1)/r tends to n.
    factor = years if abs(r) < 1e-12 else (growth - 1.0) / r
    return current * growth + 12.0 * monthly * factor - goal


def required_annual_return_pct(
    current: float, monthly: float, goal: float, years: float
) -> float | None:
    """The constant annual return at which `current` plus `12 × monthly` a year reaches
    `goal` in `years` (arithmetic, not a forecast). None when the goal is reached at 0%
    already, when `years` is not positive, or when even +100% a year would not reach it.
    Bisection on (−99%, 100%]."""
    c = _num("current", current, lo=0.0)
    m = _num("monthly", monthly, lo=0.0)
    g = _num("goal", goal)
    y = _num("years", years)
    if g <= 0:
        raise ValueError("goal must be positive")
    if y <= 0 or _goal_gap(c, m, g, y, 0.0) >= 0:
        return None
    lo, hi = -0.99, 1.0
    if _goal_gap(c, m, g, y, hi) < 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if _goal_gap(c, m, g, y, mid) < 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12:
            break
    return hi * 100


# --- habits in the trade log ---------------------------------------------------------------------


@dataclass(frozen=True)
class Flag:
    """One trade that matches a pattern, with the figure that matched."""

    code: str
    label_ko: str
    trade_id: int
    symbol: str
    date: date
    detail: str
    value: float | None = None


@dataclass(frozen=True)
class LagFlag:
    """A position whose closes have stayed at or below its stop-loss price for `days` bars.

    `since` is the first bar of that run. When every bar passed in was already at or below
    the stop, the run began before the range looked at, so `since` and `days` are only the
    range start and its length: `since_window_start` is True and the UI says "N일 이상".
    """

    symbol: str
    cut_price: float
    days: int
    since: date
    last_close: float
    # Last, with a default, so callers that build a LagFlag by hand keep working.
    since_window_start: bool = False


@dataclass(frozen=True)
class MonthCount:
    """Trades in one calendar month ("YYYY-MM")."""

    month: str
    buys: int
    sells: int
    total: int


def _flag(code: str, t: TradeView, detail: str, value: float | None = None) -> Flag:
    return Flag(code, PATTERN_LABELS_KO[code], t.id, t.symbol, t.date, detail, value)


def _ordered(trades: Iterable[TradeView]) -> list[TradeView]:
    return sorted(trades, key=lambda t: (t.date, t.id))


def _closes_by_symbol(closes: Mapping[str, pd.Series]) -> dict[str, pd.Series]:
    return {s: _as_series(s, c) for s, c in closes.items()}


def chasing_buys(
    trades: Iterable[TradeView],
    closes: Mapping[str, pd.Series],
    lookback: int = 20,
    threshold_pct: float = 15.0,
) -> tuple[list[Flag], int]:
    """Buys made right after a run-up: the last close before the trade date is more than
    `threshold_pct` above the close `lookback` bars earlier. Returns the flags and how many
    buys were skipped for lack of bars (fewer than `lookback + 1` before the trade)."""
    if lookback < 1:
        raise ValueError("lookback must be at least 1")
    threshold = _num("threshold_pct", threshold_pct, lo=0.0)
    series = _closes_by_symbol(closes)
    flags: list[Flag] = []
    skipped = 0
    for t in _ordered(trades):
        if t.side != "buy":
            continue
        s = series.get(t.symbol)
        if s is None:
            skipped += 1
            continue
        before = s[s.index < pd.Timestamp(t.date)]
        if len(before) < lookback + 1:
            skipped += 1
            continue
        last, ref = float(before.iloc[-1]), float(before.iloc[-1 - lookback])
        if ref <= 0:
            skipped += 1
            continue
        run_up = (last / ref - 1.0) * 100
        if run_up > threshold + EPS:
            flags.append(
                _flag(
                    "chasing_buy",
                    t,
                    f"매수 전 {lookback}봉 동안 {run_up:+.1f}% 움직인 뒤 샀습니다",
                    run_up,
                )
            )
    return flags, skipped


def averaging_down_below_cut(
    trades: Iterable[TradeView], cut_pct_of: Callable[[str, str], float]
) -> list[Flag]:
    """Buys into an existing position at or below its stop-loss price (`avg_cost_before ×
    (1 − cut%)`, the cut percent from `cut_pct_of(symbol, asset_class)`)."""
    flags: list[Flag] = []
    for t in _ordered(trades):
        if t.side != "buy" or t.qty_before <= 0 or t.avg_cost_before is None:
            continue
        cut = _num(f"cut_pct_of({t.symbol})", cut_pct_of(t.symbol, t.asset_class), lo=0.0)
        level = t.avg_cost_before * (1.0 - cut / 100)
        if t.avg_cost_before > 0 and t.price <= level + EPS:
            drop = (t.price / t.avg_cost_before - 1.0) * 100
            flags.append(
                _flag(
                    "averaging_down_below_cut",
                    t,
                    f"평균단가보다 {drop:.1f}% 아래(손절선 −{cut:g}%)에서 추가 매수했습니다",
                    drop,
                )
            )
    return flags


def rule_lag(
    positions: Iterable[tuple[str, float, float]],
    closes: Mapping[str, pd.Series],
    min_days: int = 5,
) -> list[LagFlag]:
    """Positions still held after `min_days` consecutive closes at or below the stop-loss
    price. `positions` are `(symbol, avg_cost, cut_pct)`; symbols without bars are skipped."""
    if min_days < 1:
        raise ValueError("min_days must be at least 1")
    series = _closes_by_symbol(closes)
    out: list[LagFlag] = []
    for symbol, avg_cost, cut_pct in positions:
        cost = _num(f"{symbol}: avg_cost", avg_cost, lo=0.0)
        cut = _num(f"{symbol}: cut_pct", cut_pct, lo=0.0)
        s = series.get(symbol)
        if s is None or s.empty or cost <= 0:
            continue
        level = cost * (1.0 - cut / 100)
        values = s.to_numpy(dtype=float)
        days = 0
        for v in values[::-1]:
            if v <= level + EPS:
                days += 1
            else:
                break
        if days >= min_days:
            out.append(
                LagFlag(
                    symbol=symbol,
                    cut_price=level,
                    days=days,
                    since=_to_date(s.index[len(values) - days]),
                    last_close=float(values[-1]),
                    since_window_start=days == len(values),
                )
            )
    return out


def monthly_trade_counts(trades: Iterable[TradeView]) -> list[MonthCount]:
    """Buys and sells per calendar month from the first to the last trade, months without
    trades included as zeros (so averages count them)."""
    ordered = _ordered(trades)
    if not ordered:
        return []
    counts: dict[str, list[int]] = {}
    first, last = ordered[0].date, ordered[-1].date
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        counts[f"{year:04d}-{month:02d}"] = [0, 0]
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    for t in ordered:
        key = f"{t.date.year:04d}-{t.date.month:02d}"
        counts[key][0 if t.side == "buy" else 1] += 1
    return [MonthCount(m, b, s, b + s) for m, (b, s) in counts.items()]


def overtrading(
    counts: Sequence[MonthCount], factor: float = 2.0, min_trades: int = 6
) -> list[MonthCount]:
    """Months with more than `factor` times the average of the previous twelve months and
    at least `min_trades` trades. The first month has nothing to compare with."""
    k = _num("factor", factor, lo=0.0)
    out: list[MonthCount] = []
    for i, m in enumerate(counts):
        if i == 0 or m.total < min_trades:
            continue
        window = counts[max(0, i - 12) : i]
        mean = sum(c.total for c in window) / len(window)
        if m.total > k * mean + EPS:
            out.append(m)
    return out


def quick_rebuy_after_loss(trades: Iterable[TradeView], days: int = 10) -> list[Flag]:
    """Buys of a symbol within `days` after it was sold below its average cost."""
    if days < 0:
        raise ValueError("days must not be negative")
    ordered = _ordered(trades)
    flags: list[Flag] = []
    flagged: set[int] = set()
    for i, sell in enumerate(ordered):
        if sell.side != "sell" or sell.avg_cost_before is None:
            continue
        if sell.price >= sell.avg_cost_before - EPS:
            continue
        for buy in ordered[i + 1 :]:
            gap = (buy.date - sell.date).days
            if gap > days:
                break
            if buy.symbol == sell.symbol and buy.side == "buy" and buy.id not in flagged:
                flagged.add(buy.id)
                loss = (sell.price / sell.avg_cost_before - 1.0) * 100
                flags.append(
                    _flag(
                        "quick_rebuy_after_loss",
                        buy,
                        f"{loss:.1f}%로 손실 매도한 {gap}일 뒤 같은 종목을 다시 샀습니다",
                        float(gap),
                    )
                )
                break
    return flags


__all__ = [
    "CASH_UNKNOWN_TARGET_NOTE_KO",
    "CLASSES",
    "CLASS_LABELS_KO",
    "DISCLAIMER_KO",
    "GOAL_INCOMPLETE_NOTE_KO",
    "LOOSER_THAN_PROJECT_KO",
    "NOT_A_FORECAST_KO",
    "NO_CASH_NOTE_KO",
    "NO_PICK_NOTE_KO",
    "PAST_CAVEAT_KO",
    "PATTERN_LABELS_KO",
    "PERIODS_PER_YEAR",
    "PROJECT_MAX_DRAWDOWN_PCT",
    "REBALANCE_HEADLINE_KO",
    "REMAINDER_ZERO_NOTE_KO",
    "TWR_NEGATIVE_VALUE_KO",
    "TWR_RETURN_FLOOR_KO",
    "VIOLATION_LABELS_KO",
    "WINDOW_LABELS_KO",
    "Beta",
    "CashRecord",
    "Concentration",
    "CorrelationTable",
    "Excluded",
    "Exposure",
    "Flag",
    "HoldingView",
    "LagFlag",
    "MonthCount",
    "PeriodReview",
    "Policy",
    "RiskWindow",
    "TargetPlan",
    "TradeView",
    "Violation",
    "Weights",
    "averaging_down_below_cut",
    "beta",
    "cap_class_weights",
    "chasing_buys",
    "choose_grid",
    "concentration",
    "construct_targets",
    "correlation_table",
    "exposure",
    "krw_return_frame",
    "monthly_trade_counts",
    "overtrading",
    "period_review",
    "quick_rebuy_after_loss",
    "rebalance_plan",
    "required_annual_return_pct",
    "risk_window",
    "rule_lag",
    "twr_index",
    "violations",
    "weights",
    "window_label_ko",
]
