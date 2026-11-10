"""The learn coach over HTTP (DECISIONS.md D-034): habit evidence, the week list, lessons
and progress.

Demo numbers only (AAPL/MSFT/BTC come from the coach tests' `seed_mixed`; the synthetic
AAA/BBB tickers feed the pure `build_watch`). Every clock is pinned to the provider's `today`;
no forecast model; the calendar comes from `FakeProvider`.
"""

import json
import re
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.data.calendar import Closure
from app.data.fake_provider import FakeProvider
from app.data.provider import MarketDataProvider, UpcomingEvent
from app.db.models import LessonProgress
from app.db.session import get_db
from app.deps import get_artifacts_dir, get_learn_service, get_market_service, get_provider
from app.learn.catalog import DEFAULT_FIRST_TOPICS, LESSON_LOAD_ERRORS, LESSONS
from app.learn.model import BANNED_PATTERN, GRADE_PATTERN, SKILL_CODES, WATCH_KINDS
from app.services.benchmarks import BenchmarkService
from app.services.coach import CoachService
from app.services.events import EventService
from app.services.learn import (
    NO_TRADES_KO,
    SEVERITY_ORDER,
    LearnService,
    WatchItem,
    build_watch,
    lessons_for_kinds,
)
from app.services.market_data import MarketDataService
from app.services.portfolio import PortfolioService
from app.services.rules import RuleService
from app.strategy.skills import LEARN_DISCLAIMER_KO

from .conftest import TODAY
from .test_coach_api import close_on, put_policy, seed_mixed
from .test_portfolio_api import buy

FIRST_ID = next(iter(LESSONS))
TRADE_CODES = (
    "oversizing",
    "rule_breaking",
    "chasing",
    "cost_blindness",
    "no_journal",
    "loss_holding",
    "short_holding",
)


@pytest.fixture(autouse=True)
def _fixed_clock(client, tmp_path):
    client.app.dependency_overrides[get_artifacts_dir] = lambda: tmp_path

    def learn(
        db: Session = Depends(get_db),
        market: MarketDataService = Depends(get_market_service),
        provider: MarketDataProvider = Depends(get_provider),
    ) -> LearnService:
        settings = get_settings()
        clock = lambda: TODAY  # noqa: E731
        portfolio = PortfolioService(db, market, today=clock)
        rules = RuleService(db, market, portfolio, settings, forecasts=None, today=clock)
        benchmarks = BenchmarkService(db, market, portfolio, today=clock)
        coach = CoachService(db, market, portfolio, rules, benchmarks, settings, today=clock)
        events = EventService(db, provider, today=clock, source="fake")
        return LearnService(db, coach, rules, events=events, settings=settings, today=clock)

    client.app.dependency_overrides[get_learn_service] = learn


def assert_honest(body: object) -> None:
    """No advice words and no grading words anywhere in a response."""
    text = json.dumps(body, ensure_ascii=False)
    assert not BANNED_PATTERN.search(text), BANNED_PATTERN.search(text)
    assert not GRADE_PATTERN.search(text), GRADE_PATTERN.search(text)


# --- lessons ----------------------------------------------------------------------------------


def test_lessons_lists_the_catalog_in_order_with_no_progress(client):
    res = client.get("/api/learn/lessons")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == len(LESSONS) and body["read_count"] == 0
    assert [x["id"] for x in body["lessons"]] == list(LESSONS)
    for x in body["lessons"]:
        assert x["progress"] is None and x["minutes"] >= 2
        assert x["level"] in ("basic", "intermediate")
        assert x["title_ko"] and x["summary_ko"]
    # The basics-first order, limited to lessons that exist.
    assert body["default_first_topics"] == [t for t in DEFAULT_FIRST_TOPICS if t in LESSONS]
    assert body["load_errors"] == [] and body["caveats"] == []
    assert_honest(body)


def test_a_lesson_that_failed_to_load_is_reported_not_hidden(client, monkeypatch):
    # The catalog leaves a broken lesson out of `LESSONS` and records why (ISSUE-050); the
    # list says so instead of silently showing fewer lessons.
    # A made-up id: the real catalog is complete, so no real lesson is missing here.
    monkeypatch.setitem(LESSON_LOAD_ERRORS, "zz-broken-lesson", "ValueError: body too long")
    body = client.get("/api/learn/lessons").json()
    assert body["load_errors"] == [
        {"lesson_id": "zz-broken-lesson", "error": "ValueError: body too long"}
    ]
    assert body["caveats"] == [
        "강의 1편을 불러오지 못했어요. 목록에서 빠져 있습니다(개발 중 오류)."
    ]
    assert "zz-broken-lesson" not in [x["id"] for x in body["lessons"]]
    assert body["total"] == len(LESSONS)
    assert client.get("/api/learn/lessons/zz-broken-lesson").status_code == 404
    assert_honest(body)


def test_lesson_detail_carries_sections_references_quiz_and_minutes(client):
    res = client.get(f"/api/learn/lessons/{FIRST_ID}")
    assert res.status_code == 200, res.text
    body = res.json()
    lesson = LESSONS[FIRST_ID]
    assert body["id"] == FIRST_ID and body["progress"] is None
    assert body["minutes"] == max(2, -(-body["body_chars"] // 400))
    assert len(body["sections"]) == len(lesson.sections)
    assert any(s["kind"] == "app" and s["route"] for s in body["sections"])
    assert len(body["references"]) >= 2
    for r in body["references"]:
        assert r["url"].startswith("https://") and r["publisher"] and r["accessed"]
    assert len(body["quiz"]) == 3
    for q in body["quiz"]:
        assert 0 <= q["answer"] < len(q["choices"]) and q["why_ko"]
    assert body["takeaway_ko"] and body["general_example_ko"]
    # Synthetic tickers only; a particle may follow ("AAA를"), so no `\b`.
    assert re.search(r"(?<![A-Za-z])(AAA|BBB)(?![A-Za-z])", body["general_example_ko"])
    assert_honest(body)


def test_unknown_lesson_is_404(client):
    res = client.get("/api/learn/lessons/no-such-lesson")
    assert res.status_code == 404
    assert res.json()["code"] == "lesson_not_found"


# --- progress ---------------------------------------------------------------------------------


def test_marking_read_shows_in_the_list_and_counts(client, db):
    res = client.put(f"/api/learn/progress/{FIRST_ID}", json={"read": True})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["lesson_id"] == FIRST_ID and out["read_at"] is not None
    assert out["quiz_score"] is None and out["quiz_total"] is None and out["quiz_at"] is None

    body = client.get("/api/learn/lessons").json()
    assert body["read_count"] == 1
    mine = next(x for x in body["lessons"] if x["id"] == FIRST_ID)
    assert mine["progress"]["read_at"] == out["read_at"]
    detail = client.get(f"/api/learn/lessons/{FIRST_ID}").json()
    assert detail["progress"]["read_at"] == out["read_at"]

    # Unmarking clears the time but keeps the row.
    again = client.put(f"/api/learn/progress/{FIRST_ID}", json={"read": False}).json()
    assert again["read_at"] is None
    assert client.get("/api/learn/lessons").json()["read_count"] == 0
    assert db.get(LessonProgress, FIRST_ID) is not None


def test_answers_are_scored_on_the_server_and_only_the_score_is_stored(client, db):
    lesson = LESSONS[FIRST_ID]
    right = [q.answer for q in lesson.quiz]
    res = client.put(f"/api/learn/progress/{FIRST_ID}", json={"answers": right})
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["quiz_score"] == 3 and out["quiz_total"] == 3 and out["quiz_at"] is not None
    assert out["read_at"] is None  # answering is not reading

    # One wrong answer (a choice index that is not the answer) scores 2.
    wrong = list(right)
    wrong[0] = (right[0] + 1) % len(lesson.quiz[0].choices)
    out = client.put(f"/api/learn/progress/{FIRST_ID}", json={"answers": wrong}).json()
    assert out["quiz_score"] == 2 and out["quiz_total"] == 3

    row = db.get(LessonProgress, FIRST_ID)
    assert row.quiz_score == 2 and row.quiz_total == 3
    assert not any(hasattr(row, name) for name in ("answers", "answers_json"))

    # Read and answers in one call.
    out = client.put(
        f"/api/learn/progress/{FIRST_ID}", json={"read": True, "answers": right}
    ).json()
    assert out["read_at"] is not None and out["quiz_score"] == 3
    assert_honest(out)


@pytest.mark.parametrize("answers", [[0, 1], [0, 1, 2, 0], []])
def test_answers_of_the_wrong_length_are_422(client, answers):
    res = client.put(f"/api/learn/progress/{FIRST_ID}", json={"answers": answers})
    assert res.status_code == 422, res.text
    assert res.json()["code"] == "answers_length"


def test_progress_without_anything_to_save_is_422(client):
    res = client.put(f"/api/learn/progress/{FIRST_ID}", json={})
    assert res.status_code == 422
    assert res.json()["code"] == "empty_progress"


def test_progress_for_an_unknown_lesson_is_404(client):
    res = client.put("/api/learn/progress/no-such-lesson", json={"read": True})
    assert res.status_code == 404


def test_every_lesson_detail_is_honest(client):
    for lesson_id in LESSONS:
        res = client.get(f"/api/learn/lessons/{lesson_id}")
        assert res.status_code == 200, res.text
        assert_honest(res.json())


# --- habits in my records (skills) ------------------------------------------------------------


def by_code(body: dict) -> dict[str, dict]:
    return {s["code"]: s for s in body["skills"]}


def test_skills_with_no_trades_is_insufficient_everywhere_and_still_200(client):
    res = client.get("/api/learn/skills")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["empty"] is True
    assert body["trades_total"] == 0 and body["trades_in_window"] == 0
    assert body["suspicious_excluded"] == 0
    assert body["as_of"] == TODAY.isoformat() and body["window_end"] == TODAY.isoformat()
    assert body["window_start"] == (TODAY - timedelta(days=365)).isoformat()
    skills = by_code(body)
    assert sorted(skills) == sorted(SKILL_CODES)
    for s in body["skills"]:
        assert s["level"] == "insufficient" and s["level_ko"] == "기록 부족"
        assert s["sample_n"] == 0 and s["lines"] == []
        assert s["window_end"] == TODAY.isoformat()
    for code in TRADE_CODES:
        assert skills[code]["caveat_ko"] == NO_TRADES_KO
    # Nothing held, no policy: today's-state habits are insufficient too, with their reasons.
    assert skills["concentration"]["caveat_ko"] is None
    assert skills["class_drift"]["caveat_ko"]
    # Whole-record habits report no window start; the others the year window.
    assert skills["loss_holding"]["window_start"] is None
    assert skills["oversizing"]["window_start"] == body["window_start"]
    # Basics first, limited to the lessons that exist.
    assert body["first_topics_source"] == "default"
    assert body["first_topics"] == [t for t in DEFAULT_FIRST_TOPICS if t in LESSONS][:3]
    assert body["disclaimer_ko"] == LEARN_DISCLAIMER_KO
    assert_honest(body)


def test_skills_after_three_trades_counts_them_and_names_the_window(client):
    seed_mixed(client)
    res = client.get("/api/learn/skills")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["empty"] is False
    assert body["trades_total"] == 3 and body["trades_in_window"] == 3
    skills = by_code(body)
    assert sorted(skills) == sorted(SKILL_CODES)

    journal = skills["no_journal"]
    assert journal["sample_n"] == 3 and journal["level"] == "insufficient"
    assert journal["lines"][0]["text_ko"] == "3건 중 메모가 있는 거래 0건"
    assert journal["lines"][0]["n"] == 3 and len(journal["lines"][0]["trade_ids"]) == 3
    assert journal["window_start"] == body["window_start"]

    conc = skills["concentration"]
    assert conc["sample_n"] == 3 and conc["window_start"] is None
    assert conc["level"] in ("strong", "some", "none")
    assert any(line["text_ko"].startswith("가장 큰 종목 ") for line in conc["lines"])
    assert any(line["text_ko"].startswith("코인 비중 ") for line in conc["lines"])
    for line in conc["lines"]:
        assert line["n"] == 3

    # Three open positions, nothing closed: the holding-period habit lists their ages only.
    short = skills["short_holding"]
    assert short["sample_n"] == 0 and short["level"] == "insufficient"
    assert short["lines"] and short["lines"][0]["text_ko"].startswith("지금 들고 있는 ")
    assert sorted(short["lines"][0]["symbols"]) == ["AAPL", "BTC-USD", "MSFT"]
    # Two sized buys (the first money in has no share) and no stop-loss breaches.
    assert skills["oversizing"]["sample_n"] == 2
    assert skills["loss_holding"]["sample_n"] == 0

    # Server order: stronger evidence first, `insufficient` last.
    levels = [s["level"] for s in body["skills"]]
    order = {"strong": 0, "some": 1, "none": 2, "insufficient": 3}
    assert levels == sorted(levels, key=order.__getitem__)
    # Every item names at least one lesson id and every line carries its sample.
    for s in body["skills"]:
        assert s["lesson_ids"]
        for line in s["lines"]:
            assert line["n"] is None or line["n"] >= 0
    assert body["caveats"] == []
    assert_honest(body)


def test_skills_class_drift_sample_is_the_holdings_count_even_without_a_policy(client):
    # N-LEARN-4: a today's-state item samples the holdings, so the screen never says
    # "표본 0건" next to a line about three positions.
    seed_mixed(client)
    body = client.get("/api/learn/skills").json()
    drift = by_code(body)["class_drift"]
    assert drift["level"] == "insufficient" and drift["caveat_ko"] == "정책을 아직 적지 않았어요."
    assert drift["sample_n"] == 3 and drift["window_start"] is None
    assert len(drift["lines"]) == 1 and drift["lines"][0]["n"] == 3
    assert drift["lines"][0]["text_ko"].startswith("지금 주식 ")


def test_skills_leaves_a_suspicious_trade_out_of_the_cost_figures(client, provider):
    # A sell at 1/40 of the close fails the 20x price check: it stays in the record but is
    # excluded from the size, outcome and cost evidence, and every response says so.
    assert buy(client, "AAPL", 10, 100).status_code == 201
    low = round(close_on(provider, "AAPL", "2026-10-02") / 40, 2)
    assert buy(client, "AAPL", 1, low, day="2026-10-02", side="sell").status_code == 201
    body = client.get("/api/learn/skills").json()
    assert body["suspicious_excluded"] == 1
    assert any(c.startswith("단가 확인이 필요한 거래 1건") for c in body["caveats"])
    cost = by_code(body)["cost_blindness"]
    assert cost["excluded_suspicious"] >= 1
    assert cost["sample_n"] == 1  # the suspicious sell is not in n either
    excluded_line = [line for line in cost["lines"] if "비용 계산에서 뺐어요" in line["text_ko"]]
    assert len(excluded_line) == 1 and excluded_line[0]["n"] == 1
    assert excluded_line[0]["text_ko"].startswith("단가 확인이 필요한 거래 1건")
    assert by_code(body)["loss_holding"]["excluded_suspicious"] == 1
    assert_honest(body)


def test_skills_counts_loss_sells_for_rebuys_over_the_pattern_window(client, provider):
    # One honest loss sell (10% under the buy, well inside the 20x check): the rebuy line
    # names the coach's one-year window so its denominator matches the flags' window.
    close = round(close_on(provider, "AAPL", "2026-10-01"), 2)
    assert buy(client, "AAPL", 10, close).status_code == 201
    assert (
        buy(client, "AAPL", 5, round(close * 0.9, 2), day="2026-10-02", side="sell").status_code
        == 201
    )
    body = client.get("/api/learn/skills").json()
    assert body["suspicious_excluded"] == 0
    loss = by_code(body)["loss_holding"]
    assert loss["sample_n"] == 1 and loss["level"] == "insufficient"
    assert loss["lines"][0]["text_ko"] == "손실 매도 1건 · 이익 매도 0건"
    rebuy = loss["lines"][1]
    assert rebuy["text_ko"] == "최근 365일 손실 매도 1건 중 0건은 10일 안에 다시 샀어요"
    assert rebuy["n"] == 1 and rebuy["trade_ids"] == []
    assert_honest(body)


def test_skills_sees_the_saved_policy_and_rules(client):
    seed_mixed(client)
    put_policy(client, cash={"krw": "1000000", "usd": "0", "as_of": TODAY.isoformat()})
    body = client.get("/api/learn/skills").json()
    skills = by_code(body)
    # With a policy saved the class-drift item compares against the targets (cash included).
    drift = skills["class_drift"]
    assert drift["level"] in ("strong", "some", "none")
    assert drift["sample_n"] == 3 and drift["caveat_ko"] is None
    assert drift["lines"][0]["text_ko"].startswith("주식 ")
    assert "현금" in drift["lines"][0]["text_ko"]
    assert_honest(body)


# --- this week ----------------------------------------------------------------------------------


def kinds(body: dict) -> list[str]:
    return [i["kind"] for i in body["items"]]


def test_week_without_trades_lists_the_setup_items_only(client):
    res = client.get("/api/learn/week")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["start"] == TODAY.isoformat()
    assert body["end"] == (TODAY + timedelta(days=7)).isoformat()
    got = kinds(body)
    assert "policy_unset" in got and "cash_missing" in got
    # Nothing held: no rule items, no calendar items, no stale symbols.
    assert not {"rule_triggered", "rule_near_cut", "rule_near_add", "near_cap"} & set(got)
    assert not {"earnings", "ex_dividend", "events_stale"} & set(got)
    assert body["stale_symbols"] == [] and body["errors"] == []
    for item in body["items"]:
        assert item["kind"] in WATCH_KINDS
        assert item["severity"] in SEVERITY_ORDER
        assert item["title_ko"]
        assert item["date"] is None or item["date"] >= TODAY.isoformat()
        if item["kind"] in ("policy_unset", "cash_missing"):
            assert item["route"] == "/coach" and item["severity"] == "setup"
    assert body["disclaimer_ko"] == LEARN_DISCLAIMER_KO
    assert body["caveats"]
    assert_honest(body)


def test_week_lists_a_fake_earnings_date_with_its_estimate_flag(client):
    # Pin the calendar: AAPL reports in three days (a range, so estimated), MSFT has nothing.
    provider = FakeProvider(
        today=TODAY,
        unknown={"ZZZZ"},
        upcoming={
            "AAPL": [UpcomingEvent("AAPL", "earnings", TODAY + timedelta(days=3), True)],
            "MSFT": [UpcomingEvent("MSFT", "ex_dividend", TODAY + timedelta(days=9))],
        },
    )
    client.app.dependency_overrides[get_provider] = lambda: provider
    seed_mixed(client)
    res = client.get("/api/learn/week")
    assert res.status_code == 200, res.text
    body = res.json()
    earnings = [i for i in body["items"] if i["kind"] == "earnings"]
    assert len(earnings) == 1
    item = earnings[0]
    assert item["symbol"] == "AAPL" and item["estimated"] is True
    assert item["date"] == (TODAY + timedelta(days=3)).isoformat()
    assert item["severity"] == "soon" and item["title_ko"] == "AAPL 실적 발표 예정일"
    assert item["detail_ko"] == "그 전에 내 손절선을 확인해 두기"
    assert item["lesson_id"] == lessons_for_kinds().get("earnings")
    # The MSFT ex-dividend date is past the window; the coin was never asked.
    assert not [i for i in body["items"] if i["kind"] == "ex_dividend"]
    assert sorted(provider.event_calls) == ["AAPL", "MSFT"]
    assert body["stale_symbols"] == [] and "events_stale" not in kinds(body)
    # Items are sorted by severity, then date, then symbol.
    keys = [
        (SEVERITY_ORDER[i["severity"]], i["date"] or TODAY.isoformat(), i["symbol"] or "")
        for i in body["items"]
    ]
    assert keys == sorted(keys)
    assert_honest(body)

    # The calendar is fetched once per TTL: a second request asks the provider nothing new.
    client.get("/api/learn/week")
    assert sorted(provider.event_calls) == ["AAPL", "MSFT"]


# --- build_watch (pure) ---------------------------------------------------------------------------


def check(symbol: str, status: str = "hold", **over) -> dict:
    row = {
        "symbol": symbol,
        "status": status,
        "label_ko": {"cut": "손절 검토", "add": "추매 검토", "hold": "관망"}[status],
        "cut_distance_pct": -20.0,
        "add_distance_pct": None,
        "weight_room_pt": 10.0,
    }
    row.update(over)
    return row


def test_build_watch_orders_by_severity_date_symbol_and_applies_the_boundaries():
    d = TODAY
    items = build_watch(
        today=d,
        days=7,
        events=[
            UpcomingEvent("AAA", "earnings", d + timedelta(days=2), True),
            UpcomingEvent("BBB", "ex_dividend", d + timedelta(days=8)),  # past the window
        ],
        checks=[
            check("AAA", cut_distance_pct=-5.0, weight_room_pt=1.5),  # on the boundary: in
            check("BBB", cut_distance_pct=-5.1, add_distance_pct=-2.0),  # just out; add near
        ],
        closures=[
            Closure(d + timedelta(days=5), "holiday", None),
            Closure(d + timedelta(days=9), "holiday", None),  # past the window
        ],
        pending_actions=2,
        suspicious_count=0,
        kill_tripped=True,
        policy_set=True,
        cash_missing=False,
        cash_stale=False,
        stale_symbols=[],
        lesson_for={"earnings": "earnings-week"},
    )
    assert [i.kind for i in items] == [
        "kill_switch",
        "pending_action",
        "rule_near_cut",
        "rule_near_add",
        "earnings",
        "near_cap",
        "market_closure",
    ]
    assert all(isinstance(i, WatchItem) for i in items)
    near_cut = items[2]
    assert near_cut.symbol == "AAA" and near_cut.title_ko == "AAA 손절선까지 5.0%"
    assert near_cut.severity == "soon" and near_cut.route == "/rules"
    assert items[3].title_ko == "BBB 추매선까지 2.0%"
    earnings = items[4]
    assert earnings.date == d + timedelta(days=2) and earnings.estimated is True
    assert earnings.lesson_id == "earnings-week" and earnings.symbol == "AAA"
    assert items[5].title_ko == "AAA 비중 상한까지 1.5%p" and items[5].severity == "setup"
    assert items[6].date == d + timedelta(days=5) and items[6].route is None
    assert items[1].title_ko == "확인이 필요한 배당·액면분할 2건"


def test_build_watch_reuses_the_rule_label_and_skips_near_items_for_a_fired_rule():
    items = build_watch(
        today=TODAY,
        days=7,
        events=[],
        checks=[
            check("AAA", "cut", cut_distance_pct=3.0),
            check("BBB", "add", cut_distance_pct=-1.0, add_distance_pct=0.5),
        ],
        closures=[],
        pending_actions=0,
        suspicious_count=3,
        kill_tripped=False,
        policy_set=False,
        cash_missing=True,
        cash_stale=True,
        stale_symbols=["BBB", "AAA", "BBB"],
    )
    got = [(i.kind, i.symbol) for i in items]
    # Within a severity, undated items sort as today and an empty symbol first; ties keep
    # the building order (policy before cash).
    assert got == [
        ("suspicious_trade", None),
        ("rule_triggered", "AAA"),
        ("rule_triggered", "BBB"),
        ("events_stale", None),
        ("policy_unset", None),
        ("cash_missing", None),
    ]
    assert items[1].title_ko == "AAA 손절 검토" and items[2].title_ko == "BBB 추매 검토"
    assert items[0].title_ko == "단가 확인이 필요한 거래 3건"
    assert items[0].route == "/transactions?check=1"
    stale = items[3]
    assert stale.title_ko == "2종목 일정을 최신으로 못 받았어요"
    assert stale.detail_ko.startswith("AAA, BBB")
    # `cash_stale` is not reported on top of `cash_missing`.
    assert "cash_stale" not in {i.kind for i in items}


def empty_watch(**over) -> list[WatchItem]:
    args: dict = dict(
        today=TODAY,
        days=7,
        events=[],
        checks=[],
        closures=[],
        pending_actions=0,
        suspicious_count=0,
        kill_tripped=False,
        policy_set=True,
        cash_missing=False,
        cash_stale=False,
        stale_symbols=[],
    )
    args.update(over)
    return build_watch(**args)


def test_build_watch_rejects_bad_input_and_every_item_is_honest():
    with pytest.raises(ValueError):
        empty_watch(days=-1)
    with pytest.raises(ValueError):
        empty_watch(near_pct=-1.0)
    assert empty_watch() == []
    close = datetime(2026, 11, 27, 18, 0, tzinfo=UTC)
    items = build_watch(
        today=TODAY,
        days=60,
        events=[
            UpcomingEvent("AAA", "earnings", TODAY + timedelta(days=1)),
            UpcomingEvent("BBB", "ex_dividend", TODAY + timedelta(days=2), True),
        ],
        checks=[
            check("AAA", "cut"),
            check("BBB", cut_distance_pct=-4.0, add_distance_pct=-4.0, weight_room_pt=0.0),
        ],
        closures=[
            Closure(TODAY + timedelta(days=10), "holiday", None),
            Closure(TODAY + timedelta(days=42), "early_close", close),
        ],
        pending_actions=1,
        suspicious_count=1,
        kill_tripped=True,
        policy_set=False,
        cash_missing=False,
        cash_stale=True,
        stale_symbols=["AAA"],
    )
    assert {i.kind for i in items} == set(WATCH_KINDS) - {"cash_missing"}
    early = next(i for i in items if i.title_ko.startswith("미국 조기 폐장"))
    assert early.title_ko == "미국 조기 폐장 (한국 시각 03:00)"
    text = json.dumps([i.__dict__ for i in items], ensure_ascii=False, default=str)
    assert not BANNED_PATTERN.search(text), BANNED_PATTERN.search(text)
    assert not GRADE_PATTERN.search(text), GRADE_PATTERN.search(text)
    # Every item of a kind a lesson explains links to that lesson (catalog order, first wins).
    for i in items:
        assert i.lesson_id is None  # no `lesson_for` given
    linked = empty_watch(policy_set=False, cash_missing=True, lesson_for=lessons_for_kinds())
    assert [i.kind for i in linked] == ["policy_unset", "cash_missing"]
    for i in linked:
        assert i.lesson_id == lessons_for_kinds().get(i.kind)
