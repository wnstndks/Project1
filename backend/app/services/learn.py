"""The learn coach: evidence from the user's own trade log, what to check this week, and the
study material behind each concept (DECISIONS.md D-034).

It is neither a signal (D-027) nor a rule check nor a policy check (D-033): nothing here
places an order, grades the person or says which way a price goes. Lessons (`app/learn`) are
static content; this service only merges them with the reading and self-check state stored in
`lesson_progress`, and scores a self-check on the server so only the score and total are kept.

`skills()` reuses the coach's one pass over the last year of bars (`CoachService._habits`) and
the pure `strategy/skills` module, so its counts are the ones the coach page shows. `week()`
joins the rule check, the stored earnings/ex-dividend calendar (`services/events.py`), the
NYSE calendar, the pending corporate actions and the policy state through the pure
`build_watch`, which is the only place the week items are worded.
"""

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.data.calendar import Closure, upcoming_closures
from app.data.provider import UpcomingEvent
from app.db.models import ActionStatus, CorporateAction, LessonProgress, RuleSettingsRow
from app.learn.catalog import DEFAULT_FIRST_TOPICS, LESSON_LOAD_ERRORS, LESSONS
from app.learn.model import WATCH_KINDS, Lesson, to_dict
from app.services.coach import CoachService
from app.services.errors import DomainError, NotFoundError
from app.services.events import EventService
from app.services.rules import RuleService
from app.strategy import skills as sk
from app.strategy.coach import exposure
from app.strategy.risk import RiskLimits

log = logging.getLogger(__name__)

WEEK_DAYS = 7
NEAR_PCT = 5.0  # a stop or add level within this many percent of the price is "near"
NEAR_CAP_PT = 2.0  # weight room (percentage points) below which the cap is "near"
KST = timezone(timedelta(hours=9))

SEVERITY_ORDER: dict[str, int] = {"now": 0, "soon": 1, "setup": 2}
SEVERITY_LABELS_KO: dict[str, str] = {"now": "지금 확인", "soon": "이번 주", "setup": "준비"}

# --- week item wording (no direction, no advice words; src/lib/learn.ts carries the labels) ---
KILL_SWITCH_TITLE_KO = "킬스위치가 켜져 있어요"
KILL_SWITCH_DETAIL_KO = (
    "한도를 넘어 모의투자 주문이 멈춰 있어요. 코치 페이지에서 이유를 보고 해제할 수 있어요."
)
RULE_TRIGGERED_DETAIL_KO = (
    "내가 정한 규칙의 조건에 들어왔어요. 규칙 페이지에서 무엇이 걸렸는지와 발동가를 확인하기"
)
NEAR_CUT_TITLE_KO = "{sym} 손절선까지 {pct}%"
NEAR_CUT_DETAIL_KO = "내가 정한 손절선에 가까워요. 발동가와 그때의 손실액을 미리 봐 두기"
NEAR_ADD_TITLE_KO = "{sym} 추매선까지 {pct}%"
NEAR_ADD_DETAIL_KO = "내가 정한 추매선에 가까워요. 남은 횟수와 비중 상한을 미리 봐 두기"
NEAR_CAP_TITLE_KO = "{sym} 비중 상한까지 {pt}%p"
NEAR_CAP_DETAIL_KO = "종목 비중 상한에 가까워 추가 매수가 막힐 수 있어요."
SUSPICIOUS_TITLE_KO = "단가 확인이 필요한 거래 {n}건"
SUSPICIOUS_DETAIL_KO = (
    "스크린샷에서 단가를 잘못 읽었을 수 있어요. 고치기 전까지 손익과 습관 증거가 실제와 달라요."
)
PENDING_TITLE_KO = "확인이 필요한 배당·액면분할 {n}건"
PENDING_DETAIL_KO = "반영하기 전까지 보유 수량이나 손익이 실제와 다를 수 있어요."
EARNINGS_TITLE_KO = "{sym} 실적 발표 예정일"
EARNINGS_DETAIL_KO = "그 전에 내 손절선을 확인해 두기"
EX_DIVIDEND_TITLE_KO = "{sym} 배당락일"
EX_DIVIDEND_DETAIL_KO = (
    "전날까지 보유한 수량에 배당이 붙어요. 들어오면 거래 페이지의 배당·분할 확인에서 반영하기"
)
HOLIDAY_TITLE_KO = "미국 휴장"
HOLIDAY_DETAIL_KO = "이날은 미국 주식 봉이 없어요. 코인은 쉬지 않아요."
EARLY_CLOSE_TITLE_KO = "미국 조기 폐장 (한국 시각 {time})"
EARLY_CLOSE_DETAIL_KO = "미국 장이 평소보다 일찍 끝나요. 뉴스 마감 시각도 그만큼 당겨져요."
EVENTS_STALE_TITLE_KO = "{n}종목 일정을 최신으로 못 받았어요"
EVENTS_STALE_DETAIL_KO = "{syms} · 저장된 일정이 있으면 그대로 보여 드려요."
POLICY_UNSET_TITLE_KO = "투자 정책을 아직 적지 않았어요"
POLICY_UNSET_DETAIL_KO = (
    "허용 낙폭·비중 상한·자산군 목표를 적어야 자산군 비중과 규칙 점검이 내 기준으로 돌아가요."
)
CASH_MISSING_TITLE_KO = "현금 잔고를 적지 않았어요"
CASH_MISSING_DETAIL_KO = "현금이 없으면 자산군 비중과 리밸런싱이 투자금 기준으로만 계산돼요."
CASH_STALE_TITLE_KO = "현금 기준일이 30일 넘게 지났어요"
CASH_STALE_DETAIL_KO = "잔고를 다시 적어야 비중 계산이 지금 상태와 맞아요."

# --- service caveats ----------------------------------------------------------------------------
LOAD_ERRORS_CAVEAT_KO = "강의 {n}편을 불러오지 못했어요. 목록에서 빠져 있습니다(개발 중 오류)."
NO_TRADES_KO = "거래 기록이 없어요."
SUSPICIOUS_EXCLUDED_KO = "단가 확인이 필요한 거래 {n}건은 크기·결과 증거에서 뺐어요."
REPLAY_SKIPPED_KO = "{habits} 증거는 계산하지 않았어요: {reason}"
FX_MISSING_REASON_KO = "환율을 받지 못한 달러 거래 {n}건"
BARS_MISSING_KO = "시세가 없어 급등 뒤 매수·손절선 점검에서 뺀 종목: {syms}"
RULES_SKIPPED_KO = "규칙을 점검하지 못한 종목: {syms}"
EVENTS_UNAVAILABLE_KO = "일정 공급자가 연결되지 않아 실적·배당락 일정은 비어 있어요."
WEEK_CAVEAT_KO = (
    "실적·배당락 날짜는 시세 공급자가 알려 준 일정이며 바뀔 수 있어요."
    " (추정)은 범위로 받은 날짜의 첫날이에요."
)
# The habits whose evidence needs the position replay (`strategy/skills.replay_trades`).
REPLAY_CODES: tuple[str, ...] = ("oversizing", "loss_holding", "short_holding")
TRADE_CODES: tuple[str, ...] = (
    "oversizing",
    "rule_breaking",
    "chasing",
    "cost_blindness",
    "no_journal",
    "loss_holding",
    "short_holding",
)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def progress_dict(row: LessonProgress | None, lesson_id: str) -> dict | None:
    if row is None:
        return None
    return {
        "lesson_id": lesson_id,
        "read_at": row.read_at,
        "quiz_score": row.quiz_score,
        "quiz_total": row.quiz_total,
        "quiz_at": row.quiz_at,
    }


def score_answers(lesson: Lesson, answers: Sequence[int]) -> int:
    """Correct answers in `answers` (one 0-based choice per question, in order). The length
    is checked by the caller."""
    return sum(1 for q, a in zip(lesson.quiz, answers, strict=True) if a == q.answer)


def lessons_for_kinds(lessons: Mapping[str, Lesson] = LESSONS) -> dict[str, str]:
    """Week-item kind → the first lesson in catalog order that explains it."""
    out: dict[str, str] = {}
    for lesson in lessons.values():
        for kind in lesson.watch_kinds:
            out.setdefault(kind, lesson.id)
    return out


# --- the week list (pure) -----------------------------------------------------------------------


@dataclass(frozen=True)
class WatchItem:
    """One thing to check in the next days. `severity`: now (지금 확인) / soon (이번 주) /
    setup (준비). `estimated` marks a calendar date the provider gave as a range."""

    kind: str
    severity: str
    title_ko: str
    detail_ko: str
    route: str | None
    date: date | None
    symbol: str | None
    lesson_id: str | None
    estimated: bool = False


def _num(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be a number")
    return float(value)


def _within(value: object, near: float) -> bool:
    """`−near ≤ value ≤ 0`: the level sits at or below the price, within `near` percent."""
    if value is None:
        return False
    x = _num("distance", value)
    return -near - 1e-9 <= x <= 1e-9


def build_watch(
    *,
    today: date,
    days: int,
    events: Sequence[UpcomingEvent],
    checks: Sequence[Mapping[str, object]],
    closures: Sequence[Closure],
    pending_actions: int,
    suspicious_count: int,
    kill_tripped: bool,
    policy_set: bool,
    cash_missing: bool,
    cash_stale: bool,
    stale_symbols: Sequence[str],
    lesson_for: Mapping[str, str] | None = None,
    near_pct: float = NEAR_PCT,
    near_cap_pt: float = NEAR_CAP_PT,
) -> list[WatchItem]:
    """The week list from facts the service gathered; no database, no network.

    `checks` are the rule check rows (`RuleService.check_all()["checks"]`): a `cut`/`add`
    status is `rule_triggered` with the check's own `label_ko`; a `hold` whose stop (add)
    level is at or below the price within `near_pct` is `rule_near_cut` (`rule_near_add`);
    `weight_room_pt ≤ near_cap_pt` is `near_cap`. Calendar events and closures are kept only
    inside `[today, today + days]`. Items are sorted by severity, then date (undated items
    count as today), then symbol, then kind. `lesson_for` maps a kind to the lesson that
    explains it. Nothing here names a direction.
    """
    if not isinstance(today, date):
        raise ValueError("today must be a date")
    if isinstance(days, bool) or not isinstance(days, int) or days < 0:
        raise ValueError("days must be a non-negative integer")
    near = _num("near_pct", near_pct)
    near_cap = _num("near_cap_pt", near_cap_pt)
    if near < 0 or near_cap < 0:
        raise ValueError("near_pct and near_cap_pt must not be negative")
    end = today + timedelta(days=days)
    lessons = dict(lesson_for or {})
    items: list[WatchItem] = []

    def add(
        kind: str,
        severity: str,
        title: str,
        detail: str,
        route: str | None,
        *,
        when: date | None = None,
        symbol: str | None = None,
        estimated: bool = False,
    ) -> None:
        if kind not in WATCH_KINDS:
            raise ValueError(f"unknown watch kind {kind!r}")
        items.append(
            WatchItem(
                kind=kind,
                severity=severity,
                title_ko=title,
                detail_ko=detail,
                route=route,
                date=when,
                symbol=symbol,
                lesson_id=lessons.get(kind),
                estimated=estimated,
            )
        )

    if kill_tripped:
        add("kill_switch", "now", KILL_SWITCH_TITLE_KO, KILL_SWITCH_DETAIL_KO, "/coach")
    if suspicious_count > 0:
        add(
            "suspicious_trade",
            "now",
            SUSPICIOUS_TITLE_KO.format(n=suspicious_count),
            SUSPICIOUS_DETAIL_KO,
            "/transactions?check=1",
        )
    if pending_actions > 0:
        add(
            "pending_action",
            "now",
            PENDING_TITLE_KO.format(n=pending_actions),
            PENDING_DETAIL_KO,
            "/transactions",
        )

    for check in checks:
        symbol = str(check["symbol"])
        status = check.get("status")
        if status in ("cut", "add"):
            label = str(check.get("label_ko") or "")
            add(
                "rule_triggered",
                "now",
                f"{symbol} {label}".strip(),
                RULE_TRIGGERED_DETAIL_KO,
                "/rules",
                symbol=symbol,
            )
        else:
            cut = check.get("cut_distance_pct")
            if _within(cut, near):
                add(
                    "rule_near_cut",
                    "soon",
                    NEAR_CUT_TITLE_KO.format(sym=symbol, pct=f"{abs(_num('cut', cut)):.1f}"),
                    NEAR_CUT_DETAIL_KO,
                    "/rules",
                    symbol=symbol,
                )
            add_d = check.get("add_distance_pct")
            if _within(add_d, near):
                add(
                    "rule_near_add",
                    "soon",
                    NEAR_ADD_TITLE_KO.format(sym=symbol, pct=f"{abs(_num('add', add_d)):.1f}"),
                    NEAR_ADD_DETAIL_KO,
                    "/rules",
                    symbol=symbol,
                )
        room = check.get("weight_room_pt")
        if room is not None and _num("weight_room_pt", room) <= near_cap + 1e-9:
            add(
                "near_cap",
                "setup",
                NEAR_CAP_TITLE_KO.format(sym=symbol, pt=f"{_num('weight_room_pt', room):.1f}"),
                NEAR_CAP_DETAIL_KO,
                "/rules",
                symbol=symbol,
            )

    for e in events:
        if not (today <= e.date <= end):
            continue
        if e.kind == "earnings":
            add(
                "earnings",
                "soon",
                EARNINGS_TITLE_KO.format(sym=e.symbol),
                EARNINGS_DETAIL_KO,
                "/rules",
                when=e.date,
                symbol=e.symbol,
                estimated=bool(e.estimated),
            )
        elif e.kind == "ex_dividend":
            add(
                "ex_dividend",
                "soon",
                EX_DIVIDEND_TITLE_KO.format(sym=e.symbol),
                EX_DIVIDEND_DETAIL_KO,
                "/transactions",
                when=e.date,
                symbol=e.symbol,
                estimated=bool(e.estimated),
            )

    for c in closures:
        if not (today <= c.date <= end):
            continue
        if c.kind == "early_close" and c.close_utc is not None:
            when = c.close_utc.astimezone(KST).strftime("%H:%M")
            add(
                "market_closure",
                "setup",
                EARLY_CLOSE_TITLE_KO.format(time=when),
                EARLY_CLOSE_DETAIL_KO,
                None,
                when=c.date,
            )
        else:
            add("market_closure", "setup", HOLIDAY_TITLE_KO, HOLIDAY_DETAIL_KO, None, when=c.date)

    if stale_symbols:
        syms = sorted(dict.fromkeys(stale_symbols))
        add(
            "events_stale",
            "setup",
            EVENTS_STALE_TITLE_KO.format(n=len(syms)),
            EVENTS_STALE_DETAIL_KO.format(syms=", ".join(syms)),
            None,
        )
    if not policy_set:
        add("policy_unset", "setup", POLICY_UNSET_TITLE_KO, POLICY_UNSET_DETAIL_KO, "/coach")
    if cash_missing:
        add("cash_missing", "setup", CASH_MISSING_TITLE_KO, CASH_MISSING_DETAIL_KO, "/coach")
    elif cash_stale:
        add("cash_stale", "setup", CASH_STALE_TITLE_KO, CASH_STALE_DETAIL_KO, "/coach")

    # Stable: items that tie (same severity, date and symbol) keep the order above.
    items.sort(key=lambda i: (SEVERITY_ORDER[i.severity], i.date or today, i.symbol or ""))
    return items


# --- evidence serialisation -----------------------------------------------------------------------


def _skill_dict(e: sk.SkillEvidence) -> dict:
    """`SkillOut` fields; the engine's `severity` orders items and is never sent."""
    return {
        "code": e.code,
        "label_ko": e.label_ko,
        "level": e.level,
        "level_ko": e.level_ko,
        "sample_n": e.sample_n,
        "min_sample": e.min_sample,
        "window_start": e.window_start,
        "window_end": e.window_end,
        "lines": [
            {
                "text_ko": line.text_ko,
                "value": line.value,
                "n": line.n,
                "trade_ids": list(line.trade_ids),
                "symbols": list(line.symbols),
            }
            for line in e.lines
        ],
        "lesson_ids": list(e.lesson_ids),
        "caveat_ko": e.caveat_ko,
        "excluded_suspicious": e.excluded_suspicious,
    }


def _insufficient(
    code: str,
    *,
    min_sample: int,
    window_start: date | None,
    today: date,
    caveat_ko: str | None,
) -> sk.SkillEvidence:
    """An `insufficient` item the service builds itself when the engine cannot be asked
    (empty ledger, or a replay that failed closed)."""
    return sk.SkillEvidence(
        code=code,
        label_ko=sk.SKILL_LABELS_KO[code],
        level="insufficient",
        level_ko=sk.LEVEL_LABELS_KO["insufficient"],
        sample_n=0,
        min_sample=min_sample,
        window_start=window_start,
        window_end=today,
        lines=(),
        lesson_ids=sk.SKILL_LESSONS[code],
        caveat_ko=caveat_ko,
    )


def _min_sample(code: str, th: sk.SkillThresholds = sk.DEFAULT_THRESHOLDS) -> int:
    if code == "loss_holding":
        return th.min_sells
    if code == "short_holding":
        return th.min_round_trips
    return th.min_sample


def _window_for(code: str, window_start: date) -> date | None:
    """The window the engine would report: the whole record (None) for the two
    whole-record habits, the year window for the rest."""
    return None if code in ("loss_holding", "short_holding") else window_start


class LearnService:
    def __init__(
        self,
        db: Session,
        coach: CoachService,
        rules: RuleService,
        events: EventService | None = None,
        settings: Settings | None = None,
        today: Callable[[], date] = date.today,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.db = db
        self.coach = coach
        self.rules = rules
        # The earnings / ex-dividend calendar (services/events.py); None leaves `week()`
        # without calendar items and says so in its caveats.
        self.events = events
        self.settings = settings or get_settings()
        self.today = today
        self.now = now

    # --- lessons and progress -------------------------------------------------------------

    def _progress_rows(self) -> dict[str, LessonProgress]:
        return {r.lesson_id: r for r in self.db.scalars(select(LessonProgress))}

    @staticmethod
    def _lesson(lesson_id: str) -> Lesson:
        lesson = LESSONS.get(lesson_id)
        if lesson is None:
            raise NotFoundError(f"강의를 찾을 수 없습니다 ({lesson_id})", code="lesson_not_found")
        return lesson

    def lessons(self) -> dict:
        """Every lesson's summary in catalog order with its progress, how many are read, and
        the basics-first order for a reader without a trade record."""
        rows = self._progress_rows()
        lessons = []
        for lesson in LESSONS.values():
            d = to_dict(lesson)
            lessons.append(
                {
                    "id": d["id"],
                    "title_ko": d["title_ko"],
                    "level": d["level"],
                    "minutes": d["minutes"],
                    "skill_codes": d["skill_codes"],
                    "watch_kinds": d["watch_kinds"],
                    "summary_ko": d["summary_ko"],
                    "progress": progress_dict(rows.get(lesson.id), lesson.id),
                }
            )
        read_count = sum(1 for lid, r in rows.items() if lid in LESSONS and r.read_at is not None)
        # Lessons whose module failed the content contract are left out, not hidden (ISSUE-050).
        load_errors = [
            {"lesson_id": lid, "error": err} for lid, err in sorted(LESSON_LOAD_ERRORS.items())
        ]
        caveats = [LOAD_ERRORS_CAVEAT_KO.format(n=len(load_errors))] if load_errors else []
        return {
            "lessons": lessons,
            "read_count": read_count,
            "total": len(LESSONS),
            "default_first_topics": [t for t in DEFAULT_FIRST_TOPICS if t in LESSONS],
            "load_errors": load_errors,
            "caveats": caveats,
        }

    def lesson(self, lesson_id: str) -> dict:
        """One lesson in full (static content) with its progress. 404 when unknown."""
        lesson = self._lesson(lesson_id)
        d = to_dict(lesson)
        d["progress"] = progress_dict(self.db.get(LessonProgress, lesson_id), lesson_id)
        return d

    def set_progress(
        self, lesson_id: str, read: bool | None, answers: Sequence[int] | None
    ) -> dict:
        """Mark the lesson read (`read=True`) or unread (`False`), and/or score a self-check.
        Answers are one choice index per question in order; a wrong count is a 422. Only the
        score, total and time are stored, never the answers."""
        lesson = self._lesson(lesson_id)
        if read is None and answers is None:
            raise DomainError("저장할 내용이 없습니다 (read 또는 answers)", code="empty_progress")
        if answers is not None and len(answers) != len(lesson.quiz):
            raise DomainError(
                f"답은 문항 수({len(lesson.quiz)})만큼 보내야 합니다 (받은 수 {len(answers)})",
                code="answers_length",
            )
        now = self.now()
        row = self.db.get(LessonProgress, lesson_id)
        if row is None:
            row = LessonProgress(lesson_id=lesson_id, updated_at=now)
            self.db.add(row)
        if answers is not None:
            row.quiz_score = score_answers(lesson, answers)
            row.quiz_total = len(lesson.quiz)
            row.quiz_at = now
        if read is True:
            row.read_at = now
        elif read is False:
            row.read_at = None
        row.updated_at = now
        self.db.commit()
        out = progress_dict(row, lesson_id)
        assert out is not None
        return out

    # --- habits in my records ---------------------------------------------------------------

    def _policy_state(self) -> tuple:
        """The coach's policy object (defaults while none is saved), whether one is saved,
        whether rules are saved, and the cash record in won (None while none is entered)."""
        payload = self.coach.policy_payload()
        policy = self.coach._policy_obj(payload["policy"])
        cash = self.coach._cash_record(payload["cash"])
        cash_krw = cash.total_krw(self.coach._fx_now()) if cash is not None else None
        rules_set = self.db.get(RuleSettingsRow, 1) is not None
        return policy, bool(payload["policy_set"]), rules_set, cash_krw, payload

    def skills(self) -> dict:
        """Strength of evidence for the nine habits in the user's own records (D-034).

        Today's state (concentration, class drift) comes from the open positions; the
        year-window habits reuse the coach's `_habits` flags; the whole-record habits
        replay every trade with `strategy/skills.replay_trades`. The replay fails closed
        (a dollar trade without its rate): those three habits are then `insufficient` and
        the reason is in `caveats`, never a silent substitute. Trades that fail the 20x
        price check stay in the replay but are excluded from the size and outcome evidence.
        """
        today = self.today()
        h = self.coach._habits(today)
        policy, policy_set, rules_set, cash_krw, _ = self._policy_state()
        check = self.rules.check_all()
        limits = policy.limits(RiskLimits.from_settings(self.settings))
        suspicious = self.coach.suspicious_ids() if h.trades else frozenset()
        caveats: list[str] = []
        th = sk.DEFAULT_THRESHOLDS

        items: list[sk.SkillEvidence] = [
            sk.concentration_evidence(
                h.views, cash_krw, policy, lambda s: limits.symbol_cap(s) * 100, today
            ),
            sk.class_drift_evidence(
                exposure(h.views, cash_krw) if h.views else None,
                policy,
                policy_set,
                today,
                holdings_count=len(h.views),
            ),
        ]

        if not h.trades:
            for code in TRADE_CODES:
                items.append(
                    _insufficient(
                        code,
                        min_sample=_min_sample(code, th),
                        window_start=_window_for(code, h.window_start),
                        today=today,
                        caveat_ko=NO_TRADES_KO,
                    )
                )
        else:
            replay: sk.Replay | None
            try:
                replay = sk.replay_trades(h.trades, today, suspicious)
            except ValueError as exc:
                replay = None
                reason = FX_MISSING_REASON_KO.format(n=h.fx_missing) if h.fx_missing else str(exc)
                log.warning("learn skills: trade replay skipped: %s", exc)
                caveats.append(
                    REPLAY_SKIPPED_KO.format(
                        habits="·".join(sk.SKILL_LABELS_KO[c] for c in REPLAY_CODES),
                        reason=reason,
                    )
                )
            buys_in_window = sum(1 for t in h.recent if t.side == "buy")
            positions_checked = sum(1 for hld in h.holdings if hld.symbol in h.closes)
            items.append(
                sk.rule_breaking_evidence(
                    h.recent,
                    h.averaging,
                    h.lag,
                    positions_checked,
                    policy_set,
                    rules_set,
                    h.window_start,
                    today,
                )
            )
            items.append(
                sk.chasing_evidence(
                    h.chasing, max(buys_in_window - h.skipped, 0), h.window_start, today
                )
            )
            items.append(
                sk.cost_blindness_evidence(
                    h.recent, h.busy, h.window_start, today, suspicious_ids=suspicious
                )
            )
            items.append(sk.no_journal_evidence(h.recent, h.window_start, today))
            if replay is not None:
                items.append(
                    sk.oversizing_evidence(
                        replay, policy, check["total_risk_pct_equity"], h.window_start, today
                    )
                )
                # The rebuy flags come from the coach's one-year pattern window, so the
                # loss-sell denominator is taken over the same window.
                items.append(
                    sk.loss_holding_evidence(
                        replay, h.rebuys, today, rebuy_window_start=h.window_start
                    )
                )
                items.append(sk.short_holding_evidence(replay, today))
            else:
                for code in REPLAY_CODES:
                    items.append(
                        _insufficient(
                            code,
                            min_sample=_min_sample(code, th),
                            window_start=_window_for(code, h.window_start),
                            today=today,
                            caveat_ko=caveats[-1],
                        )
                    )
            if suspicious:
                caveats.append(SUSPICIOUS_EXCLUDED_KO.format(n=len(suspicious)))
            if h.missing:
                caveats.append(BARS_MISSING_KO.format(syms=", ".join(sorted(h.missing))))
        if check["skipped"]:
            caveats.append(
                RULES_SKIPPED_KO.format(
                    syms=", ".join(sorted(s["symbol"] for s in check["skipped"]))
                )
            )

        ranked = sk.rank_skills(items)
        first, source = sk.first_topics(ranked, DEFAULT_FIRST_TOPICS, set(LESSONS))
        return {
            "as_of": today,
            "empty": not h.trades,
            "trades_total": len(h.trades),
            "trades_in_window": len(h.recent),
            "suspicious_excluded": len(suspicious),
            "window_start": h.window_start,
            "window_end": today,
            "skills": [_skill_dict(e) for e in ranked],
            "first_topics": list(first),
            "first_topics_source": source,
            "disclaimer_ko": sk.LEARN_DISCLAIMER_KO,
            "caveats": caveats,
        }

    # --- this week ----------------------------------------------------------------------------

    def week(self, days: int = WEEK_DAYS) -> dict:
        """What to check in `[today, today + days]`: rule checks that fired or are near,
        the stored earnings / ex-dividend calendar of the held stocks (refreshed once per
        TTL), NYSE closures, pending corporate actions (stored `detected` rows only, no new
        detection), trades needing a price check, the kill switch and the policy state."""
        today = self.today()
        check = self.rules.check_all()
        checks = check["checks"]
        held = [c["symbol"] for c in checks] + [s["symbol"] for s in check["skipped"]]
        caveats = [WEEK_CAVEAT_KO]
        events: list[UpcomingEvent] = []
        stale: list[str] = []
        errors: dict[str, str] = {}
        if self.events is None:
            caveats.append(EVENTS_UNAVAILABLE_KO)
        elif held:
            self.events.refresh(held)
            events, stale, errors = self.events.upcoming(held, days)
        # `upcoming()` is end-inclusive; `upcoming_closures` is end-exclusive, hence `days + 1`.
        closures = upcoming_closures(today, days + 1)
        pending = (
            self.db.scalar(
                select(func.count())
                .select_from(CorporateAction)
                .where(CorporateAction.status == ActionStatus.DETECTED)
            )
            or 0
        )
        suspicious = len(self.coach.suspicious_ids())
        payload = self.coach.policy_payload()
        stale_symbols = sorted(set(stale) | set(errors))
        items = build_watch(
            today=today,
            days=days,
            events=events,
            checks=checks,
            closures=closures,
            pending_actions=int(pending),
            suspicious_count=suspicious,
            kill_tripped=bool(check["kill_switch"]["tripped"]),
            policy_set=bool(payload["policy_set"]),
            cash_missing=payload["cash"] is None,
            cash_stale=bool(payload["cash_stale"]),
            stale_symbols=stale_symbols,
            lesson_for=lessons_for_kinds(),
        )
        if check["skipped"]:
            caveats.append(
                RULES_SKIPPED_KO.format(
                    syms=", ".join(sorted(s["symbol"] for s in check["skipped"]))
                )
            )
        return {
            "start": today,
            "end": today + timedelta(days=days),
            "items": [asdict(i) for i in items],
            "stale_symbols": stale_symbols,
            "errors": [f"{s}: {m}" for s, m in sorted(errors.items())],
            "caveats": caveats,
            "disclaimer_ko": sk.LEARN_DISCLAIMER_KO,
        }
