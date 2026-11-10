"""Content contract for the study-page lessons (D-034, `app/learn/`).

The dataclasses already refuse a lesson that breaks the contract; these tests state every rule
explicitly against the real catalog (parametrised over `LESSONS`) and against small synthetic
lessons for the boundaries. Catalog completeness (14 planned ids, one lesson per skill, every
watch kind explained) is asserted, and so is `LESSON_LOAD_ERRORS == {}`: the catalog serves
the lessons that load and reports the broken ones instead of failing the app's import
(ISSUE-050), so CI must be the place where a broken lesson fails.
"""

from __future__ import annotations

import inspect
import json
import logging
import re
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.learn.catalog as catalog_module
import app.learn.model as model_module
from app.learn.catalog import (
    DEFAULT_FIRST_TOPICS,
    LESSON_LOAD_ERRORS,
    LESSONS,
    PLANNED_LESSON_IDS,
    get_lesson,
)
from app.learn.model import (
    ACCESSED_PATTERN,
    BANNED_PATTERN,
    COST_WORD_PATTERN,
    FOOTNOTE_PATTERN,
    GRADE_PATTERN,
    LESSON_LEVELS,
    PERCENT_PATTERN,
    SECTION_KINDS,
    SKILL_CODES,
    TICKER_TOKEN_PATTERN,
    WATCH_KINDS,
    YEAR_PATTERN,
    Lesson,
    Question,
    Reference,
    Section,
    banned_words_in,
    body_chars,
    iter_strings,
    lesson_minutes,
    sentences,
    to_dict,
)

ID_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
ALL_LESSONS = list(LESSONS.values())
each_lesson = pytest.mark.parametrize("lesson", ALL_LESSONS, ids=[x.id for x in ALL_LESSONS])

EXPECTED_DICT_KEYS = {
    "id",
    "title_ko",
    "level",
    "skill_codes",
    "watch_kinds",
    "summary_ko",
    "sections",
    "general_example_ko",
    "references",
    "quiz",
    "takeaway_ko",
    "minutes",
    "body_chars",
}


# --- synthetic lesson builder -------------------------------------------------------------------

REFS = (
    Reference(
        title="예시 한국어 자료",
        url="https://example.org/ko",
        publisher="예시 기관",
        lang="ko",
        note_ko="2026년 기준으로 확인한 예시 자료입니다.",
        accessed="2026-11",
    ),
    Reference(
        title="Example English source",
        url="https://example.org/en",
        publisher="Example",
        lang="en",
        note_ko="영어 자료입니다.",
        accessed="2026-11",
    ),
)
QUIZ = (
    Question("개념 문항입니다?", ("하나", "둘", "셋"), 0, "첫 번째가 답인 이유입니다."),
    Question(
        "분산하면 손실이 사라진다?",
        ("그렇다", "아니다, 줄어들 뿐이다", "모른다"),
        1,
        "분산은 손실의 폭을 줄일 뿐 없애지 않습니다.",
    ),
    Question(
        "이 앱의 코치 페이지가 보여 주는 것은?",
        ("습관", "주문", "뉴스", "환율"),
        0,
        "앱 설명입니다.",
    ),
)


def make_sections(pad: int) -> tuple[Section, ...]:
    """Three minimal sections; `pad` extra body characters go into a second fact paragraph."""
    paragraphs = ("첫 단락입니다.",) + (("가" * pad,) if pad > 0 else ())
    fact = Section("사실", "fact", paragraphs)
    principle = Section("원칙", "principle", ("둘째 단락입니다.",))
    app = Section("앱", "app", ("셋째 단락입니다.",), route="/coach")
    return (fact, principle, app)


def make_lesson(body: int = 900, **over) -> Lesson:
    """A valid lesson whose body is exactly `body` characters unless `sections` is overridden."""
    base = sum(len(t) for s in make_sections(0) for t in s.texts())
    assert body > base
    kwargs = dict(
        id="sample-lesson",
        title_ko="예시 강의",
        level="basic",
        skill_codes=("chasing",),
        watch_kinds=(),
        summary_ko="예시 요약입니다.",
        sections=make_sections(body - base),
        general_example_ko="AAA를 100만원어치 사고 BBB를 50만원어치 샀습니다.",
        references=REFS,
        quiz=QUIZ,
        takeaway_ko="핵심 한 줄입니다.",
    )
    kwargs.update(over)
    return Lesson(**kwargs)


# --- catalog ------------------------------------------------------------------------------------


def test_planned_ids_are_fourteen_unique_kebab_ids():
    assert len(PLANNED_LESSON_IDS) == 14
    assert len(set(PLANNED_LESSON_IDS)) == 14
    assert all(ID_RE.match(i) for i in PLANNED_LESSON_IDS)


def test_catalog_follows_planned_order_and_keys_match_ids():
    assert list(LESSONS) == [i for i in PLANNED_LESSON_IDS if i in LESSONS]
    for lesson_id, lesson in LESSONS.items():
        assert lesson.id == lesson_id


def test_default_first_topics_are_planned_lessons():
    assert len(DEFAULT_FIRST_TOPICS) == 3
    assert set(DEFAULT_FIRST_TOPICS) <= set(PLANNED_LESSON_IDS)


def test_get_lesson():
    assert get_lesson("no-such-lesson") is None
    for lesson_id, lesson in LESSONS.items():
        assert get_lesson(lesson_id) is lesson


def test_all_planned_lessons_exist():
    assert set(LESSONS) == set(PLANNED_LESSON_IDS)


def test_no_lesson_failed_to_load():
    """The catalog leaves a broken lesson out instead of failing the app's import; CI is
    where that must still fail (ISSUE-050)."""
    assert LESSON_LOAD_ERRORS == {}


def test_every_skill_code_has_a_lesson():
    covered = {c for x in ALL_LESSONS for c in x.skill_codes}
    assert covered == set(SKILL_CODES)


def test_every_watch_kind_is_explained_by_a_lesson():
    covered = {k for x in ALL_LESSONS for k in x.watch_kinds}
    assert covered == set(WATCH_KINDS)


def test_load_keeps_the_other_lessons_when_one_module_is_broken(monkeypatch, caplog):
    """A module that raises (here: the model's validation error) or exports the wrong object
    is recorded under its planned id with the error's first line, logged at ERROR, and left
    out; every other lesson still loads in planned order. A missing module stays a skip."""
    broken, wrong_type = PLANNED_LESSON_IDS[0], PLANNED_LESSON_IDS[1]
    real_import = catalog_module.import_module

    def fake_import(name: str):
        if name == catalog_module._module_name(broken):
            raise ValueError("body is 9 chars; must be 700-1800 (x)\n  second line is dropped")
        if name == catalog_module._module_name(wrong_type):
            return SimpleNamespace(LESSON=object())
        return real_import(name)

    monkeypatch.setattr(catalog_module, "import_module", fake_import)
    with caplog.at_level(logging.ERROR, logger="app.learn.catalog"):
        lessons, errors = catalog_module._load((*PLANNED_LESSON_IDS, "not-written-yet"))

    assert list(lessons) == [i for i in PLANNED_LESSON_IDS if i not in (broken, wrong_type)]
    assert errors == {
        broken: "ValueError: body is 9 chars; must be 700-1800 (x)",
        wrong_type: f"TypeError: {catalog_module._module_name(wrong_type)}.LESSON must be a "
        "Lesson, got object",
    }
    logged = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert any(broken in m for m in logged) and any(wrong_type in m for m in logged)


# --- cross-checks with the evidence module (`app/strategy/skills.py`, risk-engineer) and the
# --- week list (`app/services/learn.py`, app-engineer) -----------------------------------------


def test_watch_kinds_match_the_kinds_the_learn_service_emits():
    """`services/learn.py` builds week items with `add("<kind>", ...)` and rejects unknown
    kinds at runtime; this keeps `model.WATCH_KINDS` and that set identical in both directions
    without importing the service (the learn modules stay pure)."""
    source = Path(__file__).resolve().parents[1] / "app" / "services" / "learn.py"
    emitted = set(re.findall(r'\badd\(\s*"([a-z_]+)"', source.read_text(encoding="utf-8")))
    assert emitted == set(WATCH_KINDS)


def test_skill_codes_match_strategy_skill_labels_in_order():
    from app.strategy.skills import SKILL_LABELS_KO

    assert tuple(SKILL_LABELS_KO) == SKILL_CODES


def test_strategy_skill_lessons_point_at_planned_ids():
    from app.strategy.skills import SKILL_LESSONS

    assert set(SKILL_LESSONS) == set(SKILL_CODES)
    for code, lesson_ids in SKILL_LESSONS.items():
        assert lesson_ids, code
        assert set(lesson_ids) <= set(PLANNED_LESSON_IDS), code


def test_written_lessons_are_listed_under_their_skill_codes():
    from app.strategy.skills import SKILL_LESSONS

    for lesson in ALL_LESSONS:
        for code in lesson.skill_codes:
            assert lesson.id in SKILL_LESSONS[code], (lesson.id, code)


def test_learn_modules_stay_pure():
    for module in (model_module, catalog_module):
        src = inspect.getsource(module)
        for heavy in ("pandas", "sqlalchemy", "fastapi", "httpx", "yfinance"):
            assert heavy not in src, f"{module.__name__} must not import {heavy}"


# --- every lesson in the catalog ----------------------------------------------------------------


@each_lesson
def test_id_and_level_and_codes(lesson: Lesson):
    assert ID_RE.match(lesson.id)
    assert lesson.id in PLANNED_LESSON_IDS
    assert lesson.level in LESSON_LEVELS
    assert set(lesson.skill_codes) <= set(SKILL_CODES)
    assert set(lesson.watch_kinds) <= set(WATCH_KINDS)
    assert len(set(lesson.skill_codes)) == len(lesson.skill_codes)
    assert len(set(lesson.watch_kinds)) == len(lesson.watch_kinds)


@each_lesson
def test_sections_shape(lesson: Lesson):
    assert 3 <= len(lesson.sections) <= 5
    kinds = [s.kind for s in lesson.sections]
    assert set(kinds) <= set(SECTION_KINDS)
    assert "fact" in kinds and "principle" in kinds and "app" in kinds
    for s in lesson.sections:
        assert s.heading_ko.strip()
        assert s.paragraphs and all(p.strip() for p in s.paragraphs)
        if s.kind == "app":
            assert s.route is not None and s.route.startswith("/")


@each_lesson
def test_length_limits(lesson: Lesson):
    assert 700 <= body_chars(lesson) <= 1800
    assert len(lesson.summary_ko) <= 120
    assert len(sentences(lesson.summary_ko)) <= 2
    assert len(lesson.takeaway_ko) <= 60
    assert lesson_minutes(lesson) >= 2


@each_lesson
def test_principle_sections_have_no_percent_figures(lesson: Lesson):
    for s in lesson.sections:
        if s.kind == "principle":
            assert all("%" not in t for t in s.texts()), s.heading_ko


@each_lesson
def test_tax_or_fee_figures_cite_a_dated_reference(lesson: Lesson):
    for text in lesson.prose():
        for sentence in sentences(text):
            if COST_WORD_PATTERN.search(sentence) and PERCENT_PATTERN.search(sentence):
                marks = [int(n) for n in FOOTNOTE_PATTERN.findall(sentence)]
                assert marks, sentence
                notes = [lesson.references[n - 1].note_ko for n in marks]
                assert any(YEAR_PATTERN.search(note) for note in notes), sentence


@each_lesson
def test_footnotes_resolve_and_every_reference_is_cited(lesson: Lesson):
    cited: set[int] = set()
    for text in lesson.prose():
        for n in FOOTNOTE_PATTERN.findall(text):
            assert 1 <= int(n) <= len(lesson.references), text
            cited.add(int(n))
    assert cited == set(range(1, len(lesson.references) + 1)), lesson.id


@each_lesson
def test_references(lesson: Lesson):
    assert len(lesson.references) >= 2
    for r in lesson.references:
        assert r.url.startswith("https://")
        assert r.title.strip() and r.publisher.strip() and r.note_ko.strip()
        assert r.lang in ("ko", "en")
        assert ACCESSED_PATTERN.match(r.accessed)
    has_ko = any(r.lang == "ko" for r in lesson.references)
    assert has_ko or any("영어" in r.note_ko for r in lesson.references)


@each_lesson
def test_quiz(lesson: Lesson):
    assert len(lesson.quiz) == 3
    for q in lesson.quiz:
        assert q.prompt_ko.strip() and q.why_ko.strip()
        assert 3 <= len(q.choices) <= 4
        assert len({c.strip() for c in q.choices}) == len(q.choices)
        assert 0 <= q.answer < len(q.choices)
    # One question must be about the app's own screen (the `app` section).
    assert any(any(k in q.prompt_ko for k in ("이 앱", "페이지", "화면")) for q in lesson.quiz)


@each_lesson
def test_no_banned_or_grading_words_anywhere(lesson: Lesson):
    assert banned_words_in(lesson) == []
    for text in iter_strings(lesson):
        assert not BANNED_PATTERN.search(text), text
        assert not GRADE_PATTERN.search(text), text


@each_lesson
def test_general_example_uses_only_synthetic_tickers(lesson: Lesson):
    tokens = set(TICKER_TOKEN_PATTERN.findall(lesson.general_example_ko))
    assert tokens <= {"AAA", "BBB"}, tokens
    assert tokens, "the general example should name AAA or BBB"


@each_lesson
def test_to_dict_is_json_serialisable_with_stable_keys(lesson: Lesson):
    d = to_dict(lesson)
    assert set(d) == EXPECTED_DICT_KEYS
    assert d["minutes"] == lesson_minutes(lesson)
    assert d["body_chars"] == body_chars(lesson)
    assert isinstance(d["sections"], list) and isinstance(d["skill_codes"], list)
    assert set(d["sections"][0]) == {
        "heading_ko",
        "kind",
        "paragraphs",
        "bullets",
        "callout_ko",
        "route",
    }
    assert set(d["references"][0]) == {"title", "url", "publisher", "lang", "note_ko", "accessed"}
    assert set(d["quiz"][0]) == {"prompt_ko", "choices", "answer", "why_ko"}
    dumped = json.dumps(d, ensure_ascii=False)
    assert json.loads(dumped) == d


# --- synthetic boundaries -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "minutes"), [(799, 2), (800, 2), (801, 3), (1200, 3), (1201, 4), (1500, 4), (1800, 5)]
)
def test_lesson_minutes_boundaries(body: int, minutes: int):
    lesson = make_lesson(body=body)
    assert body_chars(lesson) == body
    assert lesson_minutes(lesson) == minutes


@pytest.mark.parametrize("body", [699, 1801])
def test_body_length_out_of_range_is_rejected(body: int):
    with pytest.raises(ValueError):
        make_lesson(body=body)


def test_body_length_edges_are_accepted():
    assert body_chars(make_lesson(body=700)) == 700
    assert body_chars(make_lesson(body=1800)) == 1800


def test_question_answer_out_of_range():
    with pytest.raises(ValueError):
        Question("문항?", ("하나", "둘", "셋"), 3, "설명")
    with pytest.raises(ValueError):
        Question("문항?", ("하나", "둘", "셋"), -1, "설명")
    with pytest.raises(ValueError):
        Question("문항?", ("하나", "둘", "셋"), True, "설명")


def test_question_choices_distinct_and_counted():
    with pytest.raises(ValueError):
        Question("문항?", ("하나", "하나", "셋"), 0, "설명")
    with pytest.raises(ValueError):
        Question("문항?", ("하나", "둘"), 0, "설명")
    with pytest.raises(ValueError):
        Question("문항?", ("하나", "둘", "셋", "넷", "다섯"), 0, "설명")
    with pytest.raises(ValueError):
        Question("문항?", ("하나", "둘", "셋"), 0, "   ")


def test_principle_section_rejects_percent():
    with pytest.raises(ValueError):
        Section("원칙", "principle", ("비용은 1%입니다.",))
    with pytest.raises(ValueError):
        Section("원칙", "principle", ("비용 이야기.",), bullets=("수수료 0.1%",))


def test_app_section_requires_route():
    with pytest.raises(ValueError):
        Section("앱", "app", ("이 앱에서는.",))
    with pytest.raises(ValueError):
        Section("앱", "app", ("이 앱에서는.",), route="coach")
    assert Section("앱", "app", ("이 앱에서는.",), route="/coach").route == "/coach"


def test_tax_figure_needs_footnote_with_dated_note():
    def with_fact(text: str) -> tuple[Section, ...]:
        fact, principle, app = make_sections(880)
        return (replace(fact, paragraphs=fact.paragraphs + (text,)), principle, app)

    with pytest.raises(ValueError):  # no footnote in that sentence
        make_lesson(sections=with_fact("배당 원천징수는 15%입니다."))
    with pytest.raises(ValueError):  # footnote present but its note_ko has no year
        make_lesson(sections=with_fact("배당 원천징수는 15%입니다[2]."))
    ok = make_lesson(sections=with_fact("배당 원천징수는 15%입니다[1]."))
    assert "15%" in ok.sections[0].paragraphs[-1]


def test_footnote_must_point_at_an_existing_reference():
    with pytest.raises(ValueError):
        make_lesson(takeaway_ko="핵심 한 줄입니다[3].")
    with pytest.raises(ValueError):
        make_lesson(takeaway_ko="핵심 한 줄입니다[0].")


def test_banned_words_are_rejected_in_any_field():
    with pytest.raises(ValueError):
        make_lesson(takeaway_ko="이 종목을 추천합니다.")
    with pytest.raises(ValueError):
        make_lesson(summary_ko="가격이 오를 때 삽니다.")
    with pytest.raises(ValueError):
        Reference("제목", "https://example.org", "기관", "ko", "레벨 1 자료", "2026-11")
    with pytest.raises(ValueError):
        Question("내 실력은?", ("하나", "둘", "셋"), 0, "설명")
    with pytest.raises(ValueError):
        make_lesson(takeaway_ko="수익을 보장합니다.")


def test_negated_guarantee_is_allowed():
    lesson = make_lesson(takeaway_ko="공부는 수익을 보장하지 않습니다.")
    assert banned_words_in(lesson) == []


def test_general_example_rejects_other_tickers():
    with pytest.raises(ValueError):
        make_lesson(general_example_ko="SPY를 100만원어치 샀습니다.")
    with pytest.raises(ValueError):
        make_lesson(general_example_ko="AAA를 USD로 샀습니다.")


def test_summary_and_takeaway_limits():
    with pytest.raises(ValueError):
        make_lesson(summary_ko="가" * 121)
    with pytest.raises(ValueError):
        make_lesson(summary_ko="첫 문장입니다. 둘째 문장입니다. 셋째 문장입니다.")
    with pytest.raises(ValueError):
        make_lesson(takeaway_ko="가" * 61)


def test_lesson_structure_limits():
    fact, principle, app = make_sections(880)
    with pytest.raises(ValueError):  # no app section
        make_lesson(sections=(fact, principle, replace(app, kind="fact", route=None)))
    with pytest.raises(ValueError):  # too few sections
        make_lesson(sections=(fact, app))
    with pytest.raises(ValueError):  # unknown codes
        make_lesson(skill_codes=("gambling",))
    with pytest.raises(ValueError):
        make_lesson(watch_kinds=("moon_phase",))
    with pytest.raises(ValueError):  # bad id
        make_lesson(id="Chasing_Buys")
    with pytest.raises(ValueError):  # quiz count
        make_lesson(quiz=QUIZ[:2])
    with pytest.raises(ValueError):  # references count
        make_lesson(references=REFS[:1])
    with pytest.raises(ValueError):  # English only without a stated reason
        en_a = replace(REFS[1], note_ko="자료입니다.")
        en_b = replace(REFS[1], url="https://example.org/en2", note_ko="둘째 자료입니다.")
        make_lesson(references=(en_a, en_b))
    assert make_lesson(references=(replace(REFS[1], note_ko="자료입니다."), REFS[1]))
    with pytest.raises(ValueError):  # http reference
        make_lesson(references=(replace(REFS[0], url="http://example.org"), REFS[1]))
