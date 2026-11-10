"""Ordered lesson catalog for the study page (D-034).

`LESSONS` keeps the order of `PLANNED_LESSON_IDS` (the plan's 14-lesson table). Lessons are
written one file at a time under `content/<id with underscores>.py`, each exporting `LESSON`.
A planned id whose module does not exist yet is simply not listed (not an error). A module
that exists but fails — validation `ValueError`, `ImportError`, `TypeError`, anything raised
while importing it — is left out of `LESSONS` and recorded in `LESSON_LOAD_ERRORS`
(id → first line of the error) and in the log. That keeps one broken lesson from taking the
whole app down (ISSUE-050) without degrading silently: the content tests assert the dict is
empty, and the service puts it in its response so the screen can say a lesson is missing.
"""

from __future__ import annotations

import logging
from importlib import import_module
from importlib.util import find_spec

from app.learn.model import Lesson, lesson_minutes

log = logging.getLogger(__name__)

PLANNED_LESSON_IDS: tuple[str, ...] = (
    "diversification-basics",
    "position-sizing",
    "stop-loss-and-rules",
    "chasing-buys",
    "handling-losses",
    "costs-fees-fx-tax",
    "trade-journal",
    "holding-period-turnover",
    "earnings-week",
    "ex-dividend-date",
    "rebalancing-bands",
    "reading-forecasts",
    "crypto-specifics",
    "fx-and-dollar-assets",
)

# Reading order when the reader has no trade record (`first_topics_source="default"`).
DEFAULT_FIRST_TOPICS: tuple[str, ...] = (
    "diversification-basics",
    "position-sizing",
    "stop-loss-and-rules",
)


def _module_name(lesson_id: str) -> str:
    return "app.learn.content." + lesson_id.replace("-", "_")


def _first_line(exc: BaseException) -> str:
    lines = [ln.strip() for ln in str(exc).splitlines() if ln.strip()]
    return f"{type(exc).__name__}: {lines[0]}" if lines else type(exc).__name__


def _load(
    planned: tuple[str, ...] = PLANNED_LESSON_IDS,
) -> tuple[dict[str, Lesson], dict[str, str]]:
    """Import each planned lesson module on its own.

    Returns `(lessons, errors)`: lessons that loaded, in planned order, and the planned ids
    whose module exists but could not be imported or does not export a `Lesson` with the
    planned id. A missing module is skipped without an error.
    """
    lessons: dict[str, Lesson] = {}
    errors: dict[str, str] = {}
    for lesson_id in planned:
        name = _module_name(lesson_id)
        try:
            if find_spec(name) is None:
                continue  # not written yet
            lesson = import_module(name).LESSON
            if not isinstance(lesson, Lesson):
                raise TypeError(f"{name}.LESSON must be a Lesson, got {type(lesson).__name__}")
            if lesson.id != lesson_id:
                raise ValueError(f"{name}.LESSON.id is {lesson.id!r}, expected {lesson_id!r}")
        except Exception as exc:
            # One bad lesson must not stop the others; it is reported, not served.
            errors[lesson_id] = _first_line(exc)
            log.error(
                "lesson %s failed to load and is not served: %s", lesson_id, errors[lesson_id]
            )
            continue
        lessons[lesson_id] = lesson
    return lessons, errors


LESSONS: dict[str, Lesson]
LESSON_LOAD_ERRORS: dict[str, str]
LESSONS, LESSON_LOAD_ERRORS = _load()


def get_lesson(lesson_id: str) -> Lesson | None:
    return LESSONS.get(lesson_id)


__all__ = [
    "DEFAULT_FIRST_TOPICS",
    "LESSON_LOAD_ERRORS",
    "LESSONS",
    "PLANNED_LESSON_IDS",
    "Lesson",
    "get_lesson",
    "lesson_minutes",
]
