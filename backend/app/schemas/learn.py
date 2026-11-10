"""The learn coach over HTTP (DECISIONS.md D-034): evidence from my own trade log, what to
check this week, and the study material behind each concept.

It is not a signal, not a rule check and not a policy check: the habit figures are the
strength of evidence in the user's own records (`strong`/`some`/`none`/`insufficient`), every
line carries its sample size and window, and nothing here grades the person. Lessons are
static content; the "from my records" examples are joined on the client from `skills` and
`week`. Self-check answers are scored on the server, which stores the score and total only.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Level = Literal["strong", "some", "none", "insufficient"]
Severity = Literal["now", "soon", "setup"]
TopicsSource = Literal["ranking", "default"]

# --- lessons -----------------------------------------------------------------------------------


class ReferenceOut(BaseModel):
    """One outside source. Free, authoritative sources first; the author checked the link."""

    title: str
    url: str
    publisher: str
    lang: str  # ko | en
    note_ko: str
    accessed: str  # YYYY-MM


class SectionOut(BaseModel):
    """A lesson section. `kind` is shown as a chip: fact (사실), principle (일반 원칙) or app
    (이 앱에서는, with `route` pointing at the screen it talks about)."""

    heading_ko: str
    kind: str  # fact | principle | app
    paragraphs: list[str]
    bullets: list[str] | None = None
    callout_ko: str | None = None
    route: str | None = None


class QuestionOut(BaseModel):
    """A self-check question. `answer` (0-based) and `why_ko` are sent so the screen can
    explain right after each choice; the server still scores what is saved."""

    prompt_ko: str
    choices: list[str]
    answer: int
    why_ko: str


class ProgressOut(BaseModel):
    lesson_id: str
    read_at: datetime | None
    quiz_score: int | None
    quiz_total: int | None
    quiz_at: datetime | None


class ProgressIn(BaseModel):
    """`read` marks or unmarks the lesson as read; `answers` (one 0-based choice per
    question, in order) is scored on the server. Either or both."""

    read: bool | None = None
    answers: list[int] | None = Field(None, max_length=20)


class LessonSummaryOut(BaseModel):
    id: str
    title_ko: str
    level: str  # basic | intermediate
    minutes: int
    # Habit codes (strategy/skills.SKILL_LABELS_KO) and week-item kinds this lesson explains.
    skill_codes: list[str]
    watch_kinds: list[str]
    summary_ko: str
    progress: ProgressOut | None


class LessonOut(LessonSummaryOut):
    body_chars: int
    sections: list[SectionOut]
    # Synthetic tickers only (AAA/BBB); shown when my own records have nothing to show.
    general_example_ko: str
    references: list[ReferenceOut]
    quiz: list[QuestionOut]
    takeaway_ko: str


class LoadErrorOut(BaseModel):
    """A lesson module that failed the content contract at import; it is left out of the
    list instead of taking the whole app down (fail-closed per lesson)."""

    lesson_id: str
    error: str


class LessonsOut(BaseModel):
    lessons: list[LessonSummaryOut]
    read_count: int
    total: int
    # The basics-first order used when the trade log is empty (`first_topics_source="default"`).
    default_first_topics: list[str]
    load_errors: list[LoadErrorOut]
    caveats: list[str]


# --- habits in my records (skills) -------------------------------------------------------------


class EvidenceLineOut(BaseModel):
    """One sentence of evidence with the figure behind it and the trades it rests on. `n` is
    the sample the sentence is about; the screen always prints it."""

    text_ko: str
    value: float | None
    n: int | None
    trade_ids: list[int]
    symbols: list[str]


class SkillOut(BaseModel):
    """Strength of evidence for one habit, never a grade: strong (뚜렷함), some (조금 보임),
    none (걸린 것 없음), insufficient (기록 부족, fewer than `min_sample`)."""

    code: str
    label_ko: str
    level: Level
    level_ko: str
    sample_n: int
    min_sample: int
    # The window the evidence was taken from; None start means "as of today".
    window_start: date | None
    window_end: date
    lines: list[EvidenceLineOut]
    lesson_ids: list[str]
    caveat_ko: str | None
    # Trades left out because their unit price fails the 20x rule (단가 확인).
    excluded_suspicious: int


class SkillsOut(BaseModel):
    as_of: date
    # True with no trades at all: every trade-based habit is `insufficient`.
    empty: bool
    trades_total: int
    trades_in_window: int
    suspicious_excluded: int
    window_start: date
    window_end: date
    # Server order: strong, some, none, insufficient; the screen keeps it.
    skills: list[SkillOut]
    first_topics: list[str]
    first_topics_source: TopicsSource
    disclaimer_ko: str
    caveats: list[str]


# --- this week ---------------------------------------------------------------------------------


class WatchItemOut(BaseModel):
    """Something to check in the next days, tied to my own rules and policy, never to a
    direction. `severity`: now (지금 확인), soon (이번 주), setup (준비)."""

    kind: str
    severity: Severity
    title_ko: str
    detail_ko: str
    route: str | None
    date: date | None
    symbol: str | None
    lesson_id: str | None
    # Calendar dates the provider gave as a range (first day kept).
    estimated: bool = False


class WeekOut(BaseModel):
    start: date
    end: date
    items: list[WatchItemOut]
    # Symbols whose calendar could not be refreshed; their stored dates (if any) are shown.
    stale_symbols: list[str]
    errors: list[str]
    caveats: list[str]
    disclaimer_ko: str
