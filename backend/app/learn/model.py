"""Lesson data model for the study page (D-034).

Frozen dataclasses whose `__post_init__` enforces the content contract with `ValueError`, so a
lesson that breaks a rule cannot be constructed (and the catalog cannot import it):

- structure: kebab id, 3-5 sections with at least one `app` section that names a route,
  exactly 3 self-check questions with 3-4 distinct choices, at least 2 references;
- honesty: no banned advice words or grading words in any string, no `%` figures inside a
  `principle` (opinion) section, and a tax/fee figure (`세율|수수료|…` next to `12%`) only in a
  sentence that cites a `[n]` reference whose `note_ko` names the year it was checked;
- size: 700-1,500 body characters, summary <= 120 chars / 2 sentences, takeaway <= 60.

`lesson_minutes` is derived (`max(2, ceil(body_chars / 400))`), never stored. `to_dict` is the
JSON shape the API's `LessonOut` schema mirrors; keep its key names stable.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterator
from dataclasses import dataclass, fields, is_dataclass
from typing import Any, Literal

SKILL_CODES: tuple[str, ...] = (
    "concentration",
    "oversizing",
    "rule_breaking",
    "chasing",
    "loss_holding",
    "cost_blindness",
    "no_journal",
    "short_holding",
    "class_drift",
)
WATCH_KINDS: tuple[str, ...] = (
    "kill_switch",
    "rule_triggered",
    "suspicious_trade",
    "pending_action",
    "earnings",
    "ex_dividend",
    "rule_near_cut",
    "rule_near_add",
    "near_cap",
    "market_closure",
    "events_stale",
    "policy_unset",
    "cash_missing",
    "cash_stale",
)
LESSON_LEVELS: tuple[str, ...] = ("basic", "intermediate")
SECTION_KINDS: tuple[str, ...] = ("fact", "principle", "app")

Level = Literal["basic", "intermediate"]
SectionKind = Literal["fact", "principle", "app"]
Lang = Literal["ko", "en"]

# Same regex as the coach/learn front-end tests (D-034 §2). "수익을 보장하지 않" is allowed.
BANNED_PATTERN = re.compile(
    r"추천|사세요|파세요|오를|예상 수익|수익(을|이)?\s?보장(?!하지 않)"
    r"|반드시|확실히|무조건|틀림없이"
)
# The study page describes evidence strength, never the reader (D-034 §2).
GRADE_PATTERN = re.compile(r"실력|점수|등급|레벨")

ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
ACCESSED_PATTERN = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
FOOTNOTE_PATTERN = re.compile(r"\[(\d+)\]")
COST_WORD_PATTERN = re.compile(r"세율|수수료|양도세|원천징수|거래세")
PERCENT_PATTERN = re.compile(r"\d+(?:\.\d+)?%")
YEAR_PATTERN = re.compile(r"\d{4}년")
# Upper-case tokens not glued to other Latin letters ("AAA를" still yields "AAA").
TICKER_TOKEN_PATTERN = re.compile(r"(?<![A-Za-z])[A-Z]{2,5}(?![A-Za-z])")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

ALLOWED_EXAMPLE_TICKERS: frozenset[str] = frozenset({"AAA", "BBB"})
SUMMARY_MAX_CHARS = 120
SUMMARY_MAX_SENTENCES = 2
TAKEAWAY_MAX_CHARS = 60
BODY_CHARS_MIN = 700
BODY_CHARS_MAX = 1800
SECTIONS_MIN = 3
SECTIONS_MAX = 5
CHOICES_MIN = 3
CHOICES_MAX = 4
QUIZ_COUNT = 3
MIN_REFERENCES = 2
CHARS_PER_MINUTE = 400
MIN_MINUTES = 2


# --- helpers -----------------------------------------------------------------------------------


def _require_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_texts(name: str, values: object, *, allow_empty: bool = False) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{name} must be a tuple of strings")
    if not values and not allow_empty:
        raise ValueError(f"{name} must not be empty")
    for i, v in enumerate(values):
        _require_text(f"{name}[{i}]", v)


def sentences(text: str) -> list[str]:
    """Split on sentence punctuation followed by whitespace, or on line breaks."""
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def iter_strings(obj: Any) -> Iterator[str]:
    """Every string reachable from a dataclass / tuple / list / dict (recursively)."""
    if isinstance(obj, str):
        yield obj
    elif is_dataclass(obj) and not isinstance(obj, type):
        for f in fields(obj):
            yield from iter_strings(getattr(obj, f.name))
    elif isinstance(obj, (tuple, list)):
        for item in obj:
            yield from iter_strings(item)
    elif isinstance(obj, dict):
        for item in obj.values():
            yield from iter_strings(item)


def banned_words_in(obj: Any) -> list[str]:
    """Advice words and grading words found in any string field (for tests and validation)."""
    found: list[str] = []
    for text in iter_strings(obj):
        found.extend(m.group(0) for m in BANNED_PATTERN.finditer(text))
        found.extend(m.group(0) for m in GRADE_PATTERN.finditer(text))
    return found


def _check_wording(name: str, obj: Any) -> None:
    hits = banned_words_in(obj)
    if hits:
        raise ValueError(f"{name} contains banned wording: {sorted(set(hits))}")


# --- dataclasses -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Reference:
    title: str
    url: str
    publisher: str
    lang: Lang
    note_ko: str
    accessed: str  # "YYYY-MM", when the author last opened the page

    def __post_init__(self) -> None:
        _require_text("title", self.title)
        _require_text("url", self.url)
        if not self.url.startswith("https://"):
            raise ValueError(f"url must start with https://: {self.url}")
        _require_text("publisher", self.publisher)
        if self.lang not in ("ko", "en"):
            raise ValueError(f"lang must be 'ko' or 'en', got {self.lang!r}")
        _require_text("note_ko", self.note_ko)
        if not isinstance(self.accessed, str) or not ACCESSED_PATTERN.match(self.accessed):
            raise ValueError(f"accessed must be 'YYYY-MM', got {self.accessed!r}")
        _check_wording("reference", self)


@dataclass(frozen=True)
class Section:
    heading_ko: str
    kind: SectionKind
    paragraphs: tuple[str, ...]
    bullets: tuple[str, ...] | None = None
    callout_ko: str | None = None
    route: str | None = None  # app route such as "/coach"; required for kind == "app"

    def __post_init__(self) -> None:
        _require_text("heading_ko", self.heading_ko)
        if self.kind not in SECTION_KINDS:
            raise ValueError(f"kind must be one of {SECTION_KINDS}, got {self.kind!r}")
        _require_texts("paragraphs", self.paragraphs)
        if self.bullets is not None:
            _require_texts("bullets", self.bullets)
        if self.callout_ko is not None:
            _require_text("callout_ko", self.callout_ko)
        if self.kind == "app" and self.route is None:
            raise ValueError(f"app section {self.heading_ko!r} must name a route")
        if self.route is not None and not self.route.startswith("/"):
            raise ValueError(f"route must start with '/', got {self.route!r}")
        if self.kind == "principle":
            for text in self.texts():
                if "%" in text:
                    raise ValueError(
                        f"principle section {self.heading_ko!r} must not contain '%': {text!r}"
                    )
        _check_wording(f"section {self.heading_ko!r}", self)

    def texts(self) -> tuple[str, ...]:
        """Body texts in reading order: paragraphs, bullets, callout."""
        out = list(self.paragraphs)
        if self.bullets:
            out.extend(self.bullets)
        if self.callout_ko:
            out.append(self.callout_ko)
        return tuple(out)


@dataclass(frozen=True)
class Question:
    prompt_ko: str
    choices: tuple[str, ...]
    answer: int  # index into choices
    why_ko: str  # shown right after answering, whether right or wrong

    def __post_init__(self) -> None:
        _require_text("prompt_ko", self.prompt_ko)
        _require_texts("choices", self.choices)
        n = len(self.choices)
        if not CHOICES_MIN <= n <= CHOICES_MAX:
            raise ValueError(f"choices must have {CHOICES_MIN}-{CHOICES_MAX} items, got {n}")
        if len({c.strip() for c in self.choices}) != n:
            raise ValueError("choices must be distinct")
        if isinstance(self.answer, bool) or not isinstance(self.answer, int):
            raise ValueError("answer must be an int index")
        if not 0 <= self.answer < n:
            raise ValueError(f"answer {self.answer} out of range for {n} choices")
        _require_text("why_ko", self.why_ko)
        _check_wording("question", self)


@dataclass(frozen=True)
class Lesson:
    id: str
    title_ko: str
    level: Level
    skill_codes: tuple[str, ...]
    watch_kinds: tuple[str, ...]
    summary_ko: str
    sections: tuple[Section, ...]
    general_example_ko: str  # synthetic AAA/BBB example shown when the reader has no record
    references: tuple[Reference, ...]
    quiz: tuple[Question, ...]  # exactly 3: one concept, one limit of the concept, one app
    takeaway_ko: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not ID_PATTERN.match(self.id):
            raise ValueError(f"id must be kebab-case ascii, got {self.id!r}")
        _require_text("title_ko", self.title_ko)
        if self.level not in LESSON_LEVELS:
            raise ValueError(f"level must be one of {LESSON_LEVELS}, got {self.level!r}")
        _check_codes("skill_codes", self.skill_codes, SKILL_CODES)
        _check_codes("watch_kinds", self.watch_kinds, WATCH_KINDS)

        _require_text("summary_ko", self.summary_ko)
        if len(self.summary_ko) > SUMMARY_MAX_CHARS:
            raise ValueError(
                f"summary_ko is {len(self.summary_ko)} chars (max {SUMMARY_MAX_CHARS})"
            )
        if len(sentences(self.summary_ko)) > SUMMARY_MAX_SENTENCES:
            raise ValueError(f"summary_ko must be at most {SUMMARY_MAX_SENTENCES} sentences")

        if not isinstance(self.sections, tuple) or not all(
            isinstance(s, Section) for s in self.sections
        ):
            raise ValueError("sections must be a tuple of Section")
        if not SECTIONS_MIN <= len(self.sections) <= SECTIONS_MAX:
            raise ValueError(
                f"sections must have {SECTIONS_MIN}-{SECTIONS_MAX} items, got {len(self.sections)}"
            )
        if not any(s.kind == "app" for s in self.sections):
            raise ValueError("at least one section must be kind='app'")

        _require_text("general_example_ko", self.general_example_ko)
        bad = sorted(
            t
            for t in TICKER_TOKEN_PATTERN.findall(self.general_example_ko)
            if t not in ALLOWED_EXAMPLE_TICKERS
        )
        if bad:
            raise ValueError(f"general_example_ko may only name AAA/BBB, found {bad}")

        if not isinstance(self.references, tuple) or not all(
            isinstance(r, Reference) for r in self.references
        ):
            raise ValueError("references must be a tuple of Reference")
        if len(self.references) < MIN_REFERENCES:
            raise ValueError(f"at least {MIN_REFERENCES} references are required")
        if not any(r.lang == "ko" for r in self.references) and not any(
            "영어" in r.note_ko for r in self.references
        ):
            raise ValueError(
                "references need a Korean source or a note_ko explaining why only English"
            )

        if not isinstance(self.quiz, tuple) or not all(isinstance(q, Question) for q in self.quiz):
            raise ValueError("quiz must be a tuple of Question")
        if len(self.quiz) != QUIZ_COUNT:
            raise ValueError(f"quiz must have exactly {QUIZ_COUNT} questions, got {len(self.quiz)}")

        _require_text("takeaway_ko", self.takeaway_ko)
        if len(self.takeaway_ko) > TAKEAWAY_MAX_CHARS:
            raise ValueError(
                f"takeaway_ko is {len(self.takeaway_ko)} chars (max {TAKEAWAY_MAX_CHARS})"
            )

        chars = body_chars(self)
        if not BODY_CHARS_MIN <= chars <= BODY_CHARS_MAX:
            raise ValueError(
                f"body is {chars} chars; must be {BODY_CHARS_MIN}-{BODY_CHARS_MAX} ({self.id})"
            )

        self._check_footnotes()
        _check_wording(f"lesson {self.id!r}", self)

    # Texts a reader sees in the lesson body or around it (footnotes may appear in any of them).
    def prose(self) -> tuple[str, ...]:
        out = [self.summary_ko]
        for s in self.sections:
            out.extend(s.texts())
        out.append(self.general_example_ko)
        out.append(self.takeaway_ko)
        for q in self.quiz:
            out.append(q.why_ko)
        return tuple(out)

    def _check_footnotes(self) -> None:
        n_refs = len(self.references)
        for text in self.prose():
            for m in FOOTNOTE_PATTERN.finditer(text):
                n = int(m.group(1))
                if not 1 <= n <= n_refs:
                    raise ValueError(f"footnote [{n}] has no reference (have {n_refs}): {text!r}")
            for sentence in sentences(text):
                if COST_WORD_PATTERN.search(sentence) and PERCENT_PATTERN.search(sentence):
                    marks = [int(x) for x in FOOTNOTE_PATTERN.findall(sentence)]
                    if not marks:
                        raise ValueError(
                            f"a tax/fee figure needs a [n] footnote in its sentence: {sentence!r}"
                        )
                    if not any(YEAR_PATTERN.search(self.references[k - 1].note_ko) for k in marks):
                        raise ValueError(
                            "a tax/fee figure's reference note_ko must state the year "
                            f"(e.g. '2026년 기준'): {sentence!r}"
                        )


def _check_codes(name: str, codes: object, allowed: tuple[str, ...]) -> None:
    if not isinstance(codes, tuple):
        raise ValueError(f"{name} must be a tuple")
    for c in codes:
        if c not in allowed:
            raise ValueError(f"{name} has unknown code {c!r}")
    if len(set(codes)) != len(codes):
        raise ValueError(f"{name} has duplicates: {codes}")


# --- derived values ----------------------------------------------------------------------------


def body_chars(lesson: Lesson) -> int:
    """Characters (spaces included) in paragraphs + bullets + callouts of all sections."""
    return sum(len(t) for s in lesson.sections for t in s.texts())


def lesson_minutes(lesson: Lesson) -> int:
    """Reading time: at least 2 minutes, 400 characters per minute, rounded up."""
    return max(MIN_MINUTES, math.ceil(body_chars(lesson) / CHARS_PER_MINUTE))


def _plain(obj: Any) -> Any:
    """Dataclasses → dicts, tuples → lists (JSON-friendly), everything else as is."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _plain(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, (tuple, list)):
        return [_plain(x) for x in obj]
    return obj


def to_dict(lesson: Lesson) -> dict[str, Any]:
    """JSON shape served by the API (`LessonOut`). Keys: id, title_ko, level, skill_codes,
    watch_kinds, summary_ko, sections[], general_example_ko, references[], quiz[],
    takeaway_ko, minutes, body_chars."""
    out = _plain(lesson)
    out["minutes"] = lesson_minutes(lesson)
    out["body_chars"] = body_chars(lesson)
    return out
