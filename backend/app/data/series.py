"""Pure helpers that turn final daily bars into series a backtest can use.

Total return follows Yahoo's adjusted-close convention, so with no withholding it reproduces
`adj_close`: on an ex-date t the return is close_t / (close_{t-1} - D), where D is the
split-adjusted cash dividend. A Korean resident receives D x (1 - withholding) on US
dividends (15% under the treaty), so backtests pass that rate instead of using `adj_close`.

Calendar alignment: one row per calendar day D, holding what is known at D+1 00:00 UTC.
By then the stock bar of D (NYSE close, at most 21:00 UTC), the coin bar of D (closes at
00:00 UTC D+1) and the Upbit candle of D (same boundary) are final. Yahoo's USD/KRW bar of D
is assumed final by then too, as `calendar.bar_is_final` does (unverified, ISSUE-023).
Weekends and holidays carry the last value forward, up to a limit, with its age in days.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd


def total_return_index(
    close: pd.Series, dividends: pd.Series, withholding: float = 0.0
) -> pd.Series:
    """Dividend-reinvested price index on the scale of `close` at its last date.

    `close` is split-adjusted and indexed by date; `dividends` maps ex-dates to split-adjusted
    gross cash per share. A dividend whose ex-date is not a bar date counts on the next bar;
    ones outside the bars' range are ignored.
    """
    if not 0 <= withholding < 1:
        raise ValueError(f"withholding must be in [0, 1): {withholding}")
    close = close.sort_index().astype(float)
    idx = pd.DatetimeIndex(close.index)
    net = pd.Series(0.0, index=idx)
    if len(dividends):
        div = dividends.astype(float)
        pos = idx.searchsorted(pd.DatetimeIndex(div.index))
        for p, amount in zip(pos, div.to_numpy(), strict=True):
            if 0 < p < len(idx):  # needs a previous close
                net.iloc[p] += amount * (1 - withholding)
    prev = close.shift(1).to_numpy()
    # Multiplier applied to every bar before an ex-date, as in Yahoo's adjustment.
    step = np.where(net.to_numpy() > 0, 1 - net.to_numpy() / prev, 1.0)
    if (step <= 0).any():
        raise ValueError("a dividend is not smaller than the previous close")
    # factor_t = product of steps of ex-dates after t.
    after = np.concatenate([np.cumprod(step[::-1])[::-1][1:], [1.0]])
    return pd.Series(close.to_numpy() * after, index=close.index, name=close.name)


@dataclass(frozen=True)
class Aligned:
    values: pd.DataFrame  # index: calendar days; columns: series names
    age_days: pd.DataFrame  # days between the row's date and the bar the value came from


def align_daily(
    series: Mapping[str, pd.Series], start: date, end: date, max_staleness_days: int
) -> Aligned:
    """Put final-bar series on one calendar-day grid (as of D+1 00:00 UTC, see module doc).

    A value older than `max_staleness_days` becomes NaN (its age stays visible), so callers
    decide whether a gap is acceptable instead of silently using a stale price.
    """
    days = pd.date_range(start, end, freq="D")
    values, ages = {}, {}
    for name, s in series.items():
        s = s.sort_index()
        idx = pd.DatetimeIndex(s.index)
        observed = pd.Series(idx, index=idx)
        grid = days.union(idx)
        v = pd.Series(s.to_numpy(dtype=float), index=idx).reindex(grid).ffill().reindex(days)
        seen = observed.reindex(grid).ffill().reindex(days)
        age = (days.to_series() - seen).dt.days
        values[name] = v.where(age <= max_staleness_days)
        ages[name] = age
    return Aligned(pd.DataFrame(values, index=days), pd.DataFrame(ages, index=days))
