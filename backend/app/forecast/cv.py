"""Purged walk-forward splits over dates, and the record of who looked at the holdout.

Train on everything before a test block, never after it, and drop ("purge") the training
rows whose targets reach into the test block: a 1-month target dated three days before
the block would otherwise leak the block's prices into training. An extra embargo covers
serial correlation in features. The final `holdout` span is never used by the walk-forward
folds; it is scored once, at the end, to confirm what the folds found.

The holdout starts on a fixed date (DECISIONS.md D-007), not a year before the newest
data: a moving start would turn last month's holdout into this month's training data. The
walk-forward test rows also stop `horizon_days` before it, so no walk-forward target is
measured on holdout prices (ISSUE-029).

Every look at the holdout is appended to `HOLDOUT_LOG` (committed, so a reviewer can
count them). `open_holdout` refuses a second final look with the same configuration and a
new configuration whose counter (`CONFIGS_TRIED`) was not raised.
"""

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pandas as pd

# First holdout date (D-007). It is the start of the year already scored twice in phase 1
# (ISSUE-005), so that year is contaminated and only reported for reference (D-015 ②).
HOLDOUT_START = "2025-10-19"
HOLDOUT_LOG = Path(__file__).resolve().parents[3] / "docs" / "dev" / "holdout_log.jsonl"

Scope = Literal["forecast", "strategy"]
# What makes two looks "the same final look". A forecast refit on newer data with an
# unchanged configuration scores a longer holdout, which is allowed (and recorded).
ONCE_PER: dict[str, tuple[str, ...]] = {
    "forecast": ("config_hash", "data_end"),
    "strategy": ("config_hash",),
}


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
    holdout_days: int = 365  # only used when fixed_holdout is None
    # ISO date the holdout starts on; None puts it holdout_days before the newest date
    # (synthetic tests, whose data ends long before HOLDOUT_START).
    fixed_holdout: str | None = HOLDOUT_START

    @property
    def gap(self) -> pd.Timedelta:
        return pd.Timedelta(days=self.horizon_days + self.embargo_days)

    def holdout_start(self, dates: pd.Series) -> pd.Timestamp:
        if self.fixed_holdout is not None:
            return pd.Timestamp(self.fixed_holdout)
        return pd.Timestamp(dates.max()) - pd.Timedelta(days=self.holdout_days)

    def walk_forward_end(self, dates: pd.Series) -> pd.Timestamp:
        """Exclusive end of the walk-forward test rows: a target dated on or after this
        could be measured on holdout prices. The full purge gap (horizon plus embargo) is
        used: around holidays 5 NYSE sessions span up to 11 days and 21 up to 35, more
        than horizon_days alone (9 and 32)."""
        return self.holdout_start(dates) - self.gap

    def folds(self, dates: pd.Series) -> Iterator[Fold]:
        """Expanding-window folds covering the span between warm-up and the holdout."""
        first = pd.Timestamp(dates.min())
        end = min(self.walk_forward_end(dates), pd.Timestamp(dates.max()) + pd.Timedelta(days=1))
        start = first + pd.Timedelta(days=self.min_train_days)
        step = pd.Timedelta(days=self.test_days)
        while start < end:
            stop = min(start + step, end)
            yield Fold(train_end=start - self.gap, test_start=start, test_end=stop)
            start = stop

    def holdout(self, dates: pd.Series) -> Fold:
        start = self.holdout_start(dates)
        last = pd.Timestamp(dates.max()) + pd.Timedelta(days=1)
        return Fold(train_end=start - self.gap, test_start=start, test_end=max(last, start))


class HoldoutViewError(RuntimeError):
    """A look at the holdout that the rules of D-007 forbid."""


def holdout_views(path: Path = HOLDOUT_LOG) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def open_holdout(
    scope: Scope,
    config_hash: str,
    *,
    holdout_start: str,
    data_end: str,
    configs_tried: int,
    note: str = "",
    path: Path = HOLDOUT_LOG,
    now: datetime | None = None,
) -> dict:
    """Record a look at the holdout before it happens, or refuse it.

    Refused: the same final look again (`ONCE_PER[scope]`), and a configuration not seen
    before whose `configs_tried` is not above every earlier one of the scope (the counter
    was not raised for it). Returns the appended entry.
    """
    if scope not in ONCE_PER:
        raise ValueError(f"unknown holdout scope {scope!r}")
    entry = {
        "viewed_at": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "scope": scope,
        "config_hash": config_hash,
        "holdout_start": str(holdout_start),
        "data_end": str(data_end),
        "configs_tried": int(configs_tried),
        "note": note,
    }
    earlier = [v for v in holdout_views(path) if v.get("scope") == scope]
    keys = ONCE_PER[scope]
    for v in earlier:
        if v.get("holdout_start") == entry["holdout_start"] and all(
            str(v.get(k)) == str(entry[k]) for k in keys
        ):
            raise HoldoutViewError(
                f"{scope} holdout from {holdout_start} was already scored for "
                f"{', '.join(f'{k}={entry[k]}' for k in keys)} at {v.get('viewed_at')}"
            )
    seen = {v.get("config_hash") for v in earlier}
    if earlier and config_hash not in seen:
        most = max(int(v.get("configs_tried", 0)) for v in earlier)
        if configs_tried <= most:
            raise HoldoutViewError(
                f"new {scope} configuration {config_hash} but the counter is still "
                f"{configs_tried} (already {most}); raise it before scoring the holdout"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry
