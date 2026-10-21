"""Data quality checks for daily bars: boundary validation and a report over the cache.

    py -m uv run python -m app.data.quality                  # every cached symbol
    py -m uv run python -m app.data.quality SPY KRW=X -v     # with the offending dates

Boundary rule (`validate_bars`, applied to every provider response before it is cached):
- A bar whose close or adjusted close is missing or not positive is dropped: no consumer can
  use it, and storing it would fail the NOT NULL columns or poison returns.
- A bar with a usable close but a broken open/high/low (missing, not positive, high < low)
  is kept and logged. Dropping it would punch a calendar hole into close-based series (the
  forecast panel, FX conversion), which is worse than an unusable intraday range. Missing
  open/high/low are stored as 0.0, the same "unknown" value Yahoo itself sends for some
  index bars; `ohlc_ok` marks such bars and the strict loader refuses them where the open is
  needed for execution.
- A close slightly outside [low, high] is kept and only counted: Yahoo FX bars do this
  routinely (KRW=X, median 0.07%), and their high/low must not be used for anything.
"""

import argparse
import logging
import math
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import date

import numpy as np
import pandas as pd

from app.data.calendar import CalendarKind, calendar_kind, expected_dates
from app.data.provider import Bar

log = logging.getLogger(__name__)

# |daily log return| above this is listed for review (not an error by itself).
EXTREME_LOG_RETURN: dict[CalendarKind, float] = {"xnys": 0.25, "daily": 0.40, "weekdays": 0.02}
# In 24/7 markets a bar opens at the previous close; a larger jump means a broken bar.
OPEN_GAP = 0.005
# Longest acceptable distance between two Yahoo FX bars (Easter 2025 left 5 days).
FX_MAX_GAP_DAYS = 5


def _bad(x: float) -> bool:
    return x is None or math.isnan(x) or x <= 0


def ohlc_ok(open_: float, high: float, low: float, close: float) -> bool:
    """True when the intraday range is usable (all positive, high >= low)."""
    return not (_bad(open_) or _bad(high) or _bad(low) or _bad(close)) and high >= low


def validate_bars(symbol: str, bars: Iterable[Bar]) -> list[Bar]:
    """Apply the boundary rule in the module docstring and log what was changed."""
    kept: list[Bar] = []
    dropped: list[date] = []
    broken: list[date] = []
    for b in bars:
        if _bad(b.close) or _bad(b.adj_close):
            dropped.append(b.date)
            continue
        fix = {
            k: 0.0
            for k in ("open", "high", "low", "volume")
            if getattr(b, k) is None or math.isnan(getattr(b, k))
        }
        if fix:
            b = replace(b, **fix)
        if not ohlc_ok(b.open, b.high, b.low, b.close):
            broken.append(b.date)
        kept.append(b)
    if dropped:
        log.warning(
            "%s: dropped %d bars without a usable close: %s", symbol, len(dropped), dropped[:5]
        )
    if broken:
        log.warning(
            "%s: kept %d bars with a broken open/high/low: %s", symbol, len(broken), broken[:5]
        )
    return kept


@dataclass
class QualityReport:
    symbol: str
    kind: CalendarKind
    bars: int
    first: date | None = None
    last: date | None = None
    missing: list[date] = field(default_factory=list)  # expected by the calendar, absent
    extra: list[date] = field(default_factory=list)  # present on a non-calendar date
    max_gap_days: int = 0  # longest distance between consecutive bars
    broken_ohlc: list[date] = field(default_factory=list)
    close_outside: int = 0  # close outside [low, high]
    close_outside_max: float = 0.0  # worst relative distance
    open_gaps: list[tuple[date, float]] = field(default_factory=list)  # 24/7 markets only
    extreme_returns: list[tuple[date, float]] = field(default_factory=list)
    flat_days: int = 0  # close equal to the previous close
    longest_flat_run: int = 0

    def summary(self) -> dict:
        return {
            "symbol": self.symbol,
            "kind": self.kind,
            "bars": self.bars,
            "first": self.first,
            "last": self.last,
            "missing": len(self.missing),
            "extra": len(self.extra),
            "max_gap": self.max_gap_days,
            "broken_ohlc": len(self.broken_ohlc),
            "close_out": self.close_outside,
            "open_gaps": len(self.open_gaps),
            "extreme": len(self.extreme_returns),
            "flat": self.flat_days,
            "flat_run": self.longest_flat_run,
        }


def check_bars(symbol: str, df: pd.DataFrame) -> QualityReport:
    """Quality report for one symbol's bars (index: dates; columns open, high, low, close,
    adj_close). Pure: the caller supplies the bars."""
    kind = calendar_kind(symbol)
    rep = QualityReport(symbol, kind, len(df))
    if df.empty:
        return rep
    df = df.sort_index()
    dates = [d.date() if isinstance(d, pd.Timestamp) else d for d in df.index]
    df = df.set_axis(pd.DatetimeIndex(dates))
    rep.first, rep.last = dates[0], dates[-1]

    have = set(dates)
    expected = expected_dates(symbol, rep.first, rep.last)
    rep.missing = [d for d in expected if d not in have]
    rep.extra = sorted(have - set(expected))
    if len(dates) > 1:
        rep.max_gap_days = int(pd.Series(df.index).diff().dt.days.max())

    o, h, lo, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    broken = ~np.array([ohlc_ok(*x) for x in zip(o, h, lo, c, strict=True)])
    rep.broken_ohlc = [d for d, b in zip(dates, broken, strict=True) if b]
    with np.errstate(divide="ignore", invalid="ignore"):
        dev = np.maximum(c / h - 1, 1 - c / lo)
    dev = np.where(broken, np.nan, dev)
    outside = dev > 1e-4
    rep.close_outside = int(np.nansum(outside))
    rep.close_outside_max = float(np.nanmax(np.where(outside, dev, np.nan))) if outside.any() else 0

    if kind == "daily":
        prev = df["close"].shift(1)
        consecutive = pd.Series(df.index).diff().dt.days.to_numpy() == 1
        gap = (df["open"] / prev - 1).to_numpy()
        flag = consecutive & ~broken & (np.abs(gap) > OPEN_GAP)
        rep.open_gaps = [(d, float(g)) for d, g, f in zip(dates, gap, flag, strict=True) if f]

    lr = np.log(df["adj_close"]).diff()
    big = lr[lr.abs() > EXTREME_LOG_RETURN[kind]]
    rep.extreme_returns = [(d.date(), float(v)) for d, v in big.items()]

    flat = (df["close"].diff() == 0).to_numpy()
    rep.flat_days = int(flat.sum())
    run = best = 0
    for f in flat:
        run = run + 1 if f else 0
        best = max(best, run)
    rep.longest_flat_run = best
    return rep


def _load_cache(symbols: list[str] | None) -> dict[str, pd.DataFrame]:
    from sqlalchemy import select

    from app.db.models import PriceBar
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        stmt = select(PriceBar).order_by(PriceBar.symbol, PriceBar.date)
        if symbols:
            stmt = stmt.where(PriceBar.symbol.in_(symbols))
        rows = list(db.scalars(stmt))
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r.symbol, []).append(r)
    return {
        s: pd.DataFrame(
            [(r.open, r.high, r.low, r.close, r.adj_close, r.volume) for r in rs],
            columns=["open", "high", "low", "close", "adj_close", "volume"],
            index=[r.date for r in rs],
        )
        for s, rs in out.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Quality report for cached daily bars")
    parser.add_argument("symbols", nargs="*", help="default: every cached symbol")
    parser.add_argument("-v", "--verbose", action="store_true", help="list offending dates")
    args = parser.parse_args()

    frames = _load_cache(args.symbols or None)
    for s in args.symbols:
        if s not in frames:
            print(f"{s}: no cached bars")
    reports = [check_bars(s, df) for s, df in sorted(frames.items())]
    table = pd.DataFrame([r.summary() for r in reports])
    if not table.empty:
        print(table.to_string(index=False))
    if args.verbose:
        for r in reports:
            items = {
                "missing": r.missing[:20],
                "extra": r.extra[:20],
                "broken_ohlc": r.broken_ohlc[:20],
                "open_gaps": [(d, round(g, 4)) for d, g in r.open_gaps[:20]],
                "extreme": [(d, round(v, 3)) for d, v in r.extreme_returns[:20]],
            }
            items = {k: v for k, v in items.items() if v}
            if items or r.close_outside:
                print(f"\n{r.symbol}")
                for k, v in items.items():
                    print(f"  {k}: {[str(x) if isinstance(x, date) else x for x in v]}")
                if r.close_outside:
                    worst = f"{r.close_outside_max:.4f}"
                    print(f"  close outside [low, high]: {r.close_outside} (max {worst})")


if __name__ == "__main__":
    main()
