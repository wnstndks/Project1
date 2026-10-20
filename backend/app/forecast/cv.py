"""Purged walk-forward splits over dates.

Train on everything before a test block, never after it, and drop ("purge") the training
rows whose targets reach into the test block: a 1-month target dated three days before
the block would otherwise leak the block's prices into training. An extra embargo covers
serial correlation in features. The final `holdout` span is never used by the walk-forward
folds; it is scored once, at the end, to confirm what the folds found.
"""

from collections.abc import Iterator
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Fold:
    train_end: pd.Timestamp  # exclusive
    test_start: pd.Timestamp  # inclusive
    test_end: pd.Timestamp  # exclusive


@dataclass(frozen=True)
class PurgedWalkForward:
    horizon_days: int  # calendar days the target may span
    test_days: int = 91  # about one quarter (63 sessions)
    min_train_days: int = 730
    embargo_days: int = 5
    holdout_days: int = 365

    @property
    def gap(self) -> pd.Timedelta:
        return pd.Timedelta(days=self.horizon_days + self.embargo_days)

    def holdout_start(self, dates: pd.Series) -> pd.Timestamp:
        return pd.Timestamp(dates.max()) - pd.Timedelta(days=self.holdout_days)

    def folds(self, dates: pd.Series) -> Iterator[Fold]:
        """Expanding-window folds covering the span between warm-up and the holdout."""
        first = pd.Timestamp(dates.min())
        end = self.holdout_start(dates)
        start = first + pd.Timedelta(days=self.min_train_days)
        step = pd.Timedelta(days=self.test_days)
        while start < end:
            stop = min(start + step, end)
            yield Fold(train_end=start - self.gap, test_start=start, test_end=stop)
            start = stop

    def holdout(self, dates: pd.Series) -> Fold:
        start = self.holdout_start(dates)
        last = pd.Timestamp(dates.max()) + pd.Timedelta(days=1)
        return Fold(train_end=start - self.gap, test_start=start, test_end=last)
