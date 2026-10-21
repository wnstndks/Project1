"""Buy / sell / hold / no-edge signals from the forecaster's out-of-sample rows.

Pure functions: no database, no network. A signal reads only what the forecaster knew at
the row's date (`INPUT_COLUMNS`); realized outcomes (`y`, `fr`) are dropped on entry. The
edge is never computed here: the caller passes `edge_at(as_of, asset_class, horizon)`,
which must itself use only targets known by `as_of` (D-005). Without an edge every row of
that asset class is "no edge" (우위 없음), and a held position is closed.

Rule (S1, docs/dev/STRATEGIES.md): rank `gbdt_p_up - climatology_p_up` within an asset
class on a decision date. Enter in the top third when the median forecast clears the
round-trip cost, keep while in the top two thirds, sell below that. The held state only
depends on earlier decisions, so a backtest replays dates in order (`signal_frame`).
"""

import math
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Literal

import pandas as pd

from app.data import calendar as market_calendar
from app.forecast.panel import AssetClass

# The edge callback's type is owned by the evaluation code (the scorer, not the strategy
# author); it is re-exported here for strategy callers.
from app.forecast.report import EdgeLookup, EdgeStatus

Action = Literal["buy", "sell", "hold", "no_edge"]
Confidence = Literal["high", "medium", "low"]
ACTION_LABELS: dict[Action, str] = {
    "buy": "매수",
    "sell": "매도",
    "hold": "보유",
    "no_edge": "우위 없음",
}
CONFIDENCE_LABELS: dict[Confidence, str] = {"high": "높음", "medium": "중간", "low": "낮음"}

# The only columns a signal may read, all known at the row's date. Quantiles are
# standardized (multiply by `scale` for a log return).
INPUT_COLUMNS = [
    "date",
    "symbol",
    "asset_class",
    "scale",
    "gbdt_q10",
    "gbdt_q50",
    "gbdt_q90",
    "gbdt_p_up",
    "climatology_p_up",
]
Schedule = Literal["weekly", "monthly"]


@dataclass(frozen=True)
class SignalConfig:
    name: str
    horizon: str
    schedule: Schedule
    # Round-trip trading cost per asset class as a log return (fees + slippage), the same
    # values the backtest charges.
    round_trip_cost: Mapping[AssetClass, float]
    universe: Mapping[str, AssetClass]
    entry_fraction: float = 1 / 3
    keep_fraction: float = 2 / 3
    min_assets: int = 3
    hurdle_multiple: float = 1.0
    confidence_high: float = 0.55
    confidence_medium: float = 0.52


@dataclass(frozen=True)
class Signal:
    symbol: str
    asset_class: AssetClass
    as_of: date
    horizon: str
    action: Action
    held_before: bool
    held_after: bool
    confidence: Confidence
    confidence_value: float | None
    reasons: Mapping[str, object]

    @property
    def label(self) -> str:
        return ACTION_LABELS[self.action]


def _inputs(rows: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in INPUT_COLUMNS if c not in rows.columns]
    if missing:
        raise ValueError(f"signal input lacks columns: {missing}")
    out = rows[INPUT_COLUMNS].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    return out


def confidence_of(status: EdgeStatus, config: SignalConfig) -> tuple[Confidence, float | None]:
    v = status.hit_rate_lower
    if v is None or not math.isfinite(v):
        return "low", None
    if v >= config.confidence_high:
        return "high", v
    if v >= config.confidence_medium:
        return "medium", v
    return "low", v


def _decide_class(
    rows: pd.DataFrame,
    as_of: date,
    asset_class: AssetClass,
    symbols: Collection[str],
    held: Collection[str],
    status: EdgeStatus,
    config: SignalConfig,
) -> list[Signal]:
    """One decision date, one asset class. `rows` are that date's rows of the class."""
    rows = rows.assign(score=rows["gbdt_p_up"] - rows["climatology_p_up"])
    rows = rows[rows["score"].notna() & rows["symbol"].isin(symbols)]
    # Highest score first; ties go to the alphabetically first symbol.
    rows = rows.sort_values(["score", "symbol"], ascending=[False, True], kind="mergesort")
    n = len(rows)
    entry = math.ceil(n * config.entry_fraction)
    keep = math.ceil(n * config.keep_fraction)
    cost = float(config.round_trip_cost[asset_class])
    hurdle = config.hurdle_multiple * cost
    level, value = confidence_of(status, config)
    common = {"edge_reason": status.reason, "edge_n": status.n}
    for k, v in dict(status.details).items():
        # Saved as JSON: an uncomputed statistic is None, not NaN.
        common[f"edge_{k}"] = float(v) if v is not None and math.isfinite(v) else None

    if n < config.min_assets:
        blocked = "too_few_assets"
    elif not status.edge:
        blocked = status.reason
    else:
        blocked = None

    out: list[Signal] = []
    seen: set[str] = set()
    for rank, r in enumerate(rows.itertuples(index=False), start=1):
        seen.add(r.symbol)
        was_held = r.symbol in held
        expected = r.gbdt_q50 * r.scale
        reasons = {
            **common,
            "rank": rank,
            "n": n,
            "score": float(r.score),
            "p_up": float(r.gbdt_p_up),
            "base_p_up": float(r.climatology_p_up),
            "expected_return": float(expected),
            "range_low": float(r.gbdt_q10 * r.scale),
            "range_high": float(r.gbdt_q90 * r.scale),
            "hurdle": hurdle,
        }
        if blocked is not None:
            action: Action = "no_edge"
            reasons["code"] = blocked
        elif not was_held and rank <= entry and expected > hurdle:
            action, reasons["code"] = "buy", "entry_band"
        elif was_held and rank > keep:
            action, reasons["code"] = "sell", "left_keep_band"
        else:
            action = "hold"
            if was_held:
                reasons["code"] = "in_keep_band"
            elif rank <= entry:
                reasons["code"] = "below_hurdle"
            else:
                reasons["code"] = "outside_entry_band"
        out.append(
            _signal(r.symbol, asset_class, as_of, config, action, was_held, level, value, reasons)
        )

    # Held positions without a usable row today: no rank, so nothing changes, unless the
    # class has no edge, which closes every position.
    for symbol in sorted(set(held) - seen):
        reasons = {**common, "rank": None, "n": n, "hurdle": hurdle}
        if blocked is not None:
            action, reasons["code"] = "no_edge", blocked
        else:
            action, reasons["code"] = "hold", "missing_row"
        out.append(_signal(symbol, asset_class, as_of, config, action, True, level, value, reasons))
    return out


def _signal(
    symbol: str,
    asset_class: AssetClass,
    as_of: date,
    config: SignalConfig,
    action: Action,
    held_before: bool,
    confidence: Confidence,
    confidence_value: float | None,
    reasons: dict,
) -> Signal:
    if action == "buy":
        held_after = True
    elif action in ("sell", "no_edge"):
        held_after = False
    else:
        held_after = held_before
    return Signal(
        symbol=symbol,
        asset_class=asset_class,
        as_of=as_of,
        horizon=config.horizon,
        action=action,
        held_before=held_before,
        held_after=held_after,
        confidence=confidence,
        confidence_value=confidence_value,
        reasons=reasons,
    )


def decide(
    rows: pd.DataFrame,
    as_of: date,
    held: Collection[str],
    edge_at: EdgeLookup,
    config: SignalConfig,
    asset_classes: Iterable[AssetClass] = ("stock", "crypto"),
) -> list[Signal]:
    """Signals for one decision date from the rows dated `as_of` (others are ignored).

    `held` is the strategy's own position set after the previous decision, not the
    user's portfolio. Rows of symbols outside `config.universe` are ignored.
    """
    df = _inputs(rows)
    day = df[df["date"] == pd.Timestamp(as_of)]
    out: list[Signal] = []
    for cls in asset_classes:
        symbols = {s for s, c in config.universe.items() if c == cls}
        held_cls = {s for s in held if s in symbols}
        rows_cls = day[day["asset_class"] == cls]
        if rows_cls.empty and not held_cls:
            continue
        status = edge_at(as_of, cls, config.horizon)
        out += _decide_class(rows_cls, as_of, cls, symbols, held_cls, status, config)
    return out


def decision_dates(schedule: Schedule, asset_class: AssetClass, start, end) -> list[date]:
    """Decision dates in [start, end], fixed by the calendar alone, never by which rows
    exist.

    Stocks decide on the last NYSE session of each week (or month); coins on each Sunday
    (or the last day of each month), their daily bar being the UTC day.
    """
    start, end = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if asset_class == "crypto":
        days = pd.date_range(start, end, freq="D")
        keep = days.dayofweek == 6 if schedule == "weekly" else days.is_month_end
        return [d.date() for d in days[keep]]
    # Look past `end`, so a week still in progress at `end` is not cut at its last day.
    ahead = end + pd.Timedelta(days=40)
    sessions = pd.DatetimeIndex(
        pd.to_datetime(market_calendar.expected_dates("SPY", start.date(), ahead.date()))
    )
    period = sessions.to_period("W-SUN" if schedule == "weekly" else "M")
    last = pd.Series(sessions, index=sessions).groupby(period).max()
    return [d.date() for d in last if d <= end]


SIGNAL_COLUMNS = [
    "as_of",
    "symbol",
    "asset_class",
    "horizon",
    "action",
    "held_before",
    "held_after",
    "rank",
    "n",
    "score",
    "expected_return",
    "hurdle",
    "confidence",
    "confidence_value",
    "reason",
    "edge_reason",
]


def signal_frame(
    oos: pd.DataFrame,
    edge_at: EdgeLookup,
    config: SignalConfig,
    start=None,
    end=None,
) -> pd.DataFrame:
    """Every decision date's signals, replayed in date order from an empty book.

    Each row of `oos` is used only on its own date; the held state on a date comes from
    earlier decisions alone. Coins and stocks keep separate books and calendars.
    """
    df = _inputs(oos)
    df = df[df["symbol"].isin(config.universe)]
    if df.empty:
        return pd.DataFrame(columns=SIGNAL_COLUMNS)
    start = pd.Timestamp(start) if start is not None else df["date"].min()
    end = pd.Timestamp(end) if end is not None else df["date"].max()
    by_date = dict(tuple(df.groupby("date")))
    empty = df.iloc[0:0]
    records: list[dict] = []
    for cls in ("stock", "crypto"):
        held: set[str] = set()
        for d in decision_dates(config.schedule, cls, start, end):
            rows = by_date.get(pd.Timestamp(d), empty)
            for s in decide(rows, d, held, edge_at, config, asset_classes=(cls,)):
                records.append(_record(s))
                if s.held_after:
                    held.add(s.symbol)
                else:
                    held.discard(s.symbol)
    if not records:
        return pd.DataFrame(columns=SIGNAL_COLUMNS)
    out = pd.DataFrame.from_records(records, columns=SIGNAL_COLUMNS)
    out["as_of"] = pd.to_datetime(out["as_of"])
    return out.sort_values(["as_of", "asset_class", "symbol"], ignore_index=True)


def _record(s: Signal) -> dict:
    r = s.reasons
    return {
        "as_of": s.as_of,
        "symbol": s.symbol,
        "asset_class": s.asset_class,
        "horizon": s.horizon,
        "action": s.action,
        "held_before": s.held_before,
        "held_after": s.held_after,
        "rank": r.get("rank"),
        "n": r.get("n"),
        "score": r.get("score"),
        "expected_return": r.get("expected_return"),
        "hurdle": r.get("hurdle"),
        "confidence": s.confidence,
        "confidence_value": s.confidence_value,
        "reason": r.get("code"),
        "edge_reason": r.get("edge_reason"),
    }
