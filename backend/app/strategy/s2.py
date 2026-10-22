"""S2: forecast volatility sets the SPY / BTC exposure (registered in docs/dev/STRATEGIES.md).

Pure functions: no database, no network. S2 never forecasts direction. On each decision
date (every NYSE session for SPY, every UTC day for BTC) the 1d range width of the
forecaster gives an annual volatility, and the exposure follows a volatility target:

    sigma = (q90 - q10) * scale / (2 * 1.2816) * sqrt(bars per year)
    k*    = min(1, risk_budget / (budget * sigma))            (risk_budget 0.06, sigma* 0.12)
    e     = k* on the weekly decision date, else min(k*, previous e)   (cut daily, add weekly)
    R     = e when |e - R| >= band (0.25), else unchanged     (buy / sell / hold)

R, the committed exposure, is the strategy's state; the symbol's target weight is
budget * R. Without an edge (the point-in-time vol edge of the class, passed in as
`edge_at`) the class shows "no edge" (우위 없음) and e = R = 0: the position is closed.
Only the columns in `input_columns` are read; realized outcomes (`y`, `fr`) never are.

Every value here is fixed by the registration. Changing one after seeing results is a new
strategy configuration: raise STRATEGY_CONFIGS_TRIED and log it in STRATEGIES.md.
"""

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date

import pandas as pd

from app.data import calendar as market_calendar
from app.forecast.panel import AssetClass
from app.forecast.universe import CRYPTO_BENCHMARK, STOCK_BENCHMARK
from app.strategy.signals import (
    ACTION_LABELS,
    Action,
    Confidence,
    EdgeLookup,
    EdgeStatus,
    decision_dates,
)

# Turns the width of a normal 80% interval (q10..q90) into a standard deviation.
INTERVAL_WIDTH_IN_SIGMAS = 2 * 1.2816
# Float noise allowed at the band edge, so a change of exactly the band trades.
BAND_EPS = 1e-12


@dataclass(frozen=True)
class S2Config:
    name: str = "S2-1d"
    horizon: str = "1d"
    # One symbol per asset class, the same as baseline ①.
    symbols: Mapping[AssetClass, str] = field(
        default_factory=lambda: {"stock": STOCK_BENCHMARK, "crypto": CRYPTO_BENCHMARK}
    )
    # Volatility a sleeve may contribute per year: sigma* / 2 with sigma* = 0.12.
    risk_budget: float = 0.06
    # Committed exposure moves only by at least this much (in units of the class budget).
    band: float = 0.25
    # Trade tolerance as a share of equity (BacktestConfig.min_trade_share and the paper
    # trader's min_order_share); applied where orders are made, recorded here.
    min_trade_share: float = 0.02
    bars_per_year: Mapping[AssetClass, int] = field(
        default_factory=lambda: {"stock": 252, "crypto": 365}
    )
    # Quantile columns the volatility is read from. S2 uses the GBDT; the d2 diagnostic
    # (`ewma_variant`) swaps in the EWMA-t baseline and keeps everything else.
    quantiles: tuple[str, str] = ("gbdt_q10", "gbdt_q90")
    confidence_high: float = 0.55
    confidence_medium: float = 0.52

    @property
    def universe(self) -> dict[str, AssetClass]:
        return {symbol: cls for cls, symbol in self.symbols.items()}

    @property
    def input_columns(self) -> list[str]:
        return ["date", "symbol", "asset_class", "scale", *self.quantiles]


def s2_1d() -> S2Config:
    """The registered configuration; adoption is judged on it."""
    return S2Config()


def ewma_variant(config: S2Config) -> S2Config:
    """d2 (S2-ewma): the same rule and edge gate with the EWMA-t width. A diagnostic and
    the comparison of falsification 7, never a configuration to adopt."""
    return replace(config, name=f"{config.name}-ewma", quantiles=("ewma_t_q10", "ewma_t_q90"))


@dataclass(frozen=True)
class S2State:
    """Per asset class: the allowed exposure e (the ratchet) and the committed one R."""

    allowed: float = 0.0
    exposure: float = 0.0


@dataclass(frozen=True)
class S2Signal:
    symbol: str
    asset_class: AssetClass
    as_of: date
    horizon: str
    action: Action
    held_before: bool
    held_after: bool
    # R after the decision, as a share of the class budget in [0, 1] (risk.py sizes it).
    target_exposure: float
    confidence: Confidence
    confidence_value: float | None
    reasons: Mapping[str, object]
    # The class's state after this decision: the `prev` of its next decision date.
    state: S2State = S2State()

    @property
    def label(self) -> str:
        return ACTION_LABELS[self.action]


def implied_vol(q10: float, q90: float, scale: float, bars_per_year: int) -> float:
    """Annual volatility from one bar's standardized 80% range; NaN if it is unusable."""
    try:
        width = (float(q90) - float(q10)) * float(scale)
    except (TypeError, ValueError):
        return math.nan
    if not math.isfinite(width) or width <= 0:
        return math.nan
    return width / INTERVAL_WIDTH_IN_SIGMAS * math.sqrt(bars_per_year)


def target_exposure(sigma: float, budget: float, risk_budget: float) -> float:
    """k* = min(1, risk_budget / (budget * sigma)), never above 1 (no leverage)."""
    if not math.isfinite(sigma) or sigma <= 0:
        raise ValueError("volatility must be a positive number")
    if budget <= 0:
        return 0.0
    return min(1.0, risk_budget / (budget * sigma))


def confidence_of(status: EdgeStatus, config: S2Config) -> tuple[Confidence, float | None]:
    v = status.hit_rate_lower
    if v is None or not math.isfinite(v):
        return "low", None
    if v >= config.confidence_high:
        return "high", v
    if v >= config.confidence_medium:
        return "medium", v
    return "low", v


def _finite_or_none(v) -> float | None:
    return float(v) if v is not None and math.isfinite(v) else None


def _number(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return math.nan


def decide(
    row: Mapping[str, object] | None,
    as_of: date,
    asset_class: AssetClass,
    state: S2State,
    *,
    weekly: bool,
    status: EdgeStatus,
    budget: float,
    config: S2Config,
) -> tuple[S2Signal, S2State]:
    """One asset class on one decision date. `row` is that date's forecast row for the
    class's symbol (None when there is none); `state` comes from earlier decisions only."""
    symbol = config.symbols[asset_class]
    level, value = confidence_of(status, config)
    reasons: dict[str, object] = {
        "edge_reason": status.reason,
        "edge_n": status.n,
        **{f"edge_{k}": _finite_or_none(v) for k, v in dict(status.details).items()},
        "weekly": weekly,
        "risk_budget": config.risk_budget,
        "band": config.band,
        "budget": budget,
        "sigma_source": config.quantiles[0].removesuffix("_q10"),
        "allowed_before": state.allowed,
        "exposure_before": state.exposure,
    }
    sigma = math.nan
    if row is not None:
        q10, q90 = (_number(row.get(c)) for c in config.quantiles)
        scale = _number(row.get("scale"))
        sigma = implied_vol(q10, q90, scale, config.bars_per_year[asset_class])
        reasons["range_low"] = _finite_or_none(q10 * scale)
        reasons["range_high"] = _finite_or_none(q90 * scale)
    reasons["sigma"] = _finite_or_none(sigma)

    if not status.edge:
        # No edge: no position. Cutting is allowed on any day, so this never fights the
        # ratchet; adding back waits for a weekly date because e restarts at 0.
        action: Action = "no_edge"
        reasons["code"] = status.reason
        new = S2State(0.0, 0.0)
    elif not math.isfinite(sigma):
        # No usable forecast today: keep the state (no automatic sale).
        action, reasons["code"] = "hold", "missing_row"
        new = state
    else:
        k_star = target_exposure(sigma, budget, config.risk_budget)
        allowed = k_star if weekly else min(k_star, state.allowed)
        reasons["k_star"] = k_star
        if abs(allowed - state.exposure) >= config.band - BAND_EPS:
            action = "buy" if allowed > state.exposure else "sell"
            reasons["code"] = "raise_exposure" if action == "buy" else "cut_exposure"
            new = S2State(allowed, allowed)
        else:
            action, reasons["code"] = "hold", "within_band"
            new = S2State(allowed, state.exposure)
    reasons["allowed"] = new.allowed
    reasons["exposure"] = new.exposure
    # The same state under the short names the paper trader stores and reads back.
    reasons["e"], reasons["R"], reasons["R_prev"] = new.allowed, new.exposure, state.exposure
    reasons["target_weight"] = budget * new.exposure
    signal = S2Signal(
        symbol=symbol,
        asset_class=asset_class,
        as_of=as_of,
        horizon=config.horizon,
        action=action,
        held_before=state.exposure > 0,
        held_after=new.exposure > 0,
        target_exposure=new.exposure,
        confidence=level,
        confidence_value=value,
        reasons=reasons,
        state=new,
    )
    return signal, new


def daily_dates(asset_class: AssetClass, start, end) -> list[date]:
    """S2's decision dates in [start, end]: every NYSE session for stocks, every UTC day
    for coins. Fixed by the calendar alone, never by which rows exist."""
    start, end = pd.Timestamp(start).date(), pd.Timestamp(end).date()
    symbol = STOCK_BENCHMARK if asset_class == "stock" else CRYPTO_BENCHMARK
    return market_calendar.expected_dates(symbol, start, end)


def is_decision_day(asset_class: AssetClass, day: date) -> bool:
    return day in daily_dates(asset_class, day, day)


def is_weekly_day(asset_class: AssetClass, day: date) -> bool:
    """Whether exposure may be raised on `day` (S1's weekly decision calendar)."""
    return day in decision_dates("weekly", asset_class, day, day)


def decide_day(
    rows: pd.DataFrame,
    as_of: date,
    prev: Mapping[AssetClass, S2State],
    edge_at: EdgeLookup,
    config: S2Config,
    budgets: Mapping[AssetClass, float],
    asset_classes: Iterable[AssetClass] = ("stock", "crypto"),
) -> list[S2Signal]:
    """Signals of one decision date (paper trading): the rows dated `as_of` (others are
    ignored) and each class's state after its previous decision (`prev`, zero if absent).
    Each signal carries the state to pass on as the next `prev`."""
    df = _inputs(rows, config)
    day = df[df["date"] == pd.Timestamp(as_of)]
    out: list[S2Signal] = []
    for cls in asset_classes:
        match = day[(day["asset_class"] == cls) & (day["symbol"] == config.symbols[cls])]
        row = match.iloc[0].to_dict() if len(match) else None
        signal, _ = decide(
            row,
            as_of,
            cls,
            prev.get(cls, S2State()),
            weekly=is_weekly_day(cls, as_of),
            status=edge_at(as_of, cls, config.horizon),
            budget=float(budgets.get(cls, 0.0)),
            config=config,
        )
        out.append(signal)
    return out


def state_from_record(prev: Mapping[str, object]) -> S2State:
    """The state stored by the paper trader ({"e": .., "R": ..}); {} starts from zero.
    Anything else that is not a pair of numbers in [0, 1] raises (fail closed)."""
    if not prev:
        return S2State()
    values = (_number(prev.get("e")), _number(prev.get("R")))
    if not all(math.isfinite(v) and 0.0 <= v <= 1.0 for v in values):
        raise ValueError(f"S2 state is not two exposures in [0, 1]: {dict(prev)}")
    return S2State(*values)


def paper_decider(budgets: Mapping[AssetClass, float]):
    """`decide` in the shape paper.ExposureStrategy calls, with the class budgets bound
    (`risk.budgets_from_settings(settings)`): one class, the stored state as a dict."""

    def decide_for_paper(
        rows: pd.DataFrame,
        as_of: date,
        prev: Mapping[str, object],
        edge_at: EdgeLookup,
        config: S2Config,
        asset_class: AssetClass,
    ) -> list[S2Signal]:
        state = {asset_class: state_from_record(prev)}
        return decide_day(rows, as_of, state, edge_at, config, budgets, (asset_class,))

    return decide_for_paper


def _inputs(rows: pd.DataFrame, config: S2Config) -> pd.DataFrame:
    cols = config.input_columns
    missing = [c for c in cols if c not in rows.columns]
    if missing:
        raise ValueError(f"S2 input lacks columns: {missing}")
    out = rows[cols].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    return out


FRAME_COLUMNS = [
    "as_of",
    "symbol",
    "asset_class",
    "horizon",
    "action",
    "held_before",
    "held_after",
    "weekly",
    "sigma",
    "k_star",
    "allowed",
    "exposure_before",
    "exposure",
    "target_weight",
    "confidence",
    "confidence_value",
    "reason",
    "edge_reason",
]


def signal_frame(
    oos: pd.DataFrame,
    edge_at: EdgeLookup,
    config: S2Config,
    budgets: Mapping[AssetClass, float],
    start=None,
    end=None,
    asset_classes: Iterable[AssetClass] = ("stock", "crypto"),
) -> pd.DataFrame:
    """Every decision date's signal, replayed in date order from zero exposure.

    Each row of `oos` is used only on its own date and `edge_at` is asked about that date
    only, so a decision never sees a later forecast. Each class has its own state.
    """
    df = _inputs(oos, config)
    wanted = {(cls, sym) for cls, sym in config.symbols.items()}
    df = df[[(c, s) in wanted for c, s in zip(df["asset_class"], df["symbol"], strict=True)]]
    if start is None or end is None:
        if df.empty:
            return pd.DataFrame(columns=FRAME_COLUMNS)
        start = df["date"].min() if start is None else start
        end = df["date"].max() if end is None else end
    rows = {(r["asset_class"], r["date"]): r for r in df.to_dict("records")}
    records: list[dict] = []
    for cls in asset_classes:
        budget = float(budgets.get(cls, 0.0))
        weekly = set(decision_dates("weekly", cls, start, end))
        state = S2State()
        for d in daily_dates(cls, start, end):
            status = edge_at(d, cls, config.horizon)
            row = rows.get((cls, pd.Timestamp(d)))
            signal, state = decide(
                row, d, cls, state, weekly=d in weekly, status=status, budget=budget,
                config=config,
            )  # fmt: skip
            records.append(_record(signal))
    if not records:
        return pd.DataFrame(columns=FRAME_COLUMNS)
    out = pd.DataFrame.from_records(records, columns=FRAME_COLUMNS)
    out["as_of"] = pd.to_datetime(out["as_of"])
    return out.sort_values(["as_of", "asset_class"], ignore_index=True)


def _record(s: S2Signal) -> dict:
    r = s.reasons
    return {
        "as_of": s.as_of,
        "symbol": s.symbol,
        "asset_class": s.asset_class,
        "horizon": s.horizon,
        "action": s.action,
        "held_before": s.held_before,
        "held_after": s.held_after,
        "weekly": r.get("weekly"),
        "sigma": r.get("sigma"),
        "k_star": r.get("k_star"),
        "allowed": r.get("allowed"),
        "exposure_before": r.get("exposure_before"),
        "exposure": r.get("exposure"),
        "target_weight": r.get("target_weight"),
        "confidence": s.confidence,
        "confidence_value": s.confidence_value,
        "reason": r.get("code"),
        "edge_reason": r.get("edge_reason"),
    }


def decisions(frame: pd.DataFrame) -> pd.DataFrame:
    """Backtest decisions [date, symbol, weight] from `signal_frame`: the target weight
    budget x R of both symbols on every decision date. Order-level caps (index fund and
    symbol caps, order size, no leverage) are applied by risk.py where orders are made."""
    if frame.empty:
        return pd.DataFrame(columns=["date", "symbol", "weight"])
    out = frame[["as_of", "symbol", "target_weight"]].rename(
        columns={"as_of": "date", "target_weight": "weight"}
    )
    w = out["weight"].astype(float)
    if not w.map(math.isfinite).all() or (w < 0).any():
        raise ValueError("S2 target weights must be finite and non-negative")
    if (w.groupby(out["date"]).sum() > 1 + 1e-9).any():
        raise ValueError("S2 target weights add up to more than 1 (leverage)")
    return out.reset_index(drop=True)
