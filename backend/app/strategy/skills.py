"""Learning coach evidence: what the user's own trade log shows, with sample sizes (D-034).

This is not a signal (D-027), not a rule check and not a policy check (D-033). It is a
third thing: evidence taken from the user's own records, each line resting on a stated
number of trades over a stated window, paired with the study material that explains the
concept. The ``level`` of each item is the strength of the evidence (``strong`` 뚜렷함 /
``some`` 조금 보임 / ``none`` 걸린 것 없음 / ``insufficient`` 기록 부족), never a grade of the
person: no score, no rank, no personality label. Nothing here says which way a price will
go, nothing places or blocks an order, and the live-trading flag is never read.

Pure functions over the coach's dataclasses: no database, no network, no HTTP, no pandas.
Invalid input fails closed with ValueError (a USD trade without its KRW rate, a sell before
any buy in the series, a trade dated after today) instead of being patched silently.

Wording rule, enforced by ``tests/test_skills.py`` on every ``*_KO`` constant and on every
generated line: none of 추천·사세요·파세요·오를·예상 수익·수익 보장·반드시·확실히·무조건·틀림없이
(``LEARN_DISCLAIMER_KO`` says 보장하지 않습니다, which the rule allows), and none of the grading
words 실력·점수·등급·레벨. Lines carry numbers only; the UI adds no gain/loss colour to them.
Thresholds live in ``SkillThresholds`` (no ``AM_LEARN_*`` settings); tests pass another instance.
"""

import statistics
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from app.strategy.coach import (
    EPS,
    Exposure,
    Flag,
    HoldingView,
    LagFlag,
    MonthCount,
    Policy,
    TradeView,
    _num,
    concentration,
    exposure,
    weights,
)

Level = Literal["strong", "some", "none", "insufficient"]
Outcome = Literal["gain", "loss", "flat"]
TopicsSource = Literal["ranking", "default"]

# Stronger evidence sorts first.
LEVEL_ORDER: dict[str, int] = {"strong": 0, "some": 1, "none": 2, "insufficient": 3}

# --- Korean labels (single source for the service and src/lib/learn.ts) ----------------

LEVEL_LABELS_KO: dict[str, str] = {
    "strong": "뚜렷함",
    "some": "조금 보임",
    "none": "걸린 것 없음",
    "insufficient": "기록 부족",
}
SKILL_LABELS_KO: dict[str, str] = {
    "concentration": "한 곳에 몰림",
    "oversizing": "한 번에 크게 걸기",
    "rule_breaking": "정한 규칙 어기기",
    "chasing": "급등 뒤 매수",
    "loss_holding": "손실은 오래, 이익은 빨리",
    "cost_blindness": "비용 무시",
    "no_journal": "메모 없는 거래",
    "short_holding": "짧은 보유·잦은 회전",
    "class_drift": "자산군 비중 벗어남",
}
SKILL_LESSONS: dict[str, tuple[str, ...]] = {
    "concentration": ("diversification-basics",),
    "oversizing": ("position-sizing",),
    "rule_breaking": ("stop-loss-and-rules",),
    "chasing": ("chasing-buys",),
    "loss_holding": ("handling-losses",),
    "cost_blindness": ("costs-fees-fx-tax", "holding-period-turnover"),
    "no_journal": ("trade-journal",),
    "short_holding": ("holding-period-turnover",),
    "class_drift": ("rebalancing-bands",),
}
LEARN_DISCLAIMER_KO = "공부는 판단의 질을 높이지만 수익을 보장하지 않습니다. 투자 조언이 아닙니다."
SAMPLE_KO = "표본 {n}건"

# Caveats attached to an evidence item.
COST_BASIS_PROXY_KO = "매수 당시 평가액이 아니라 투자원금 기준으로 계산했습니다."
NO_FEES_RECORDED_KO = "수수료가 기록되지 않았어요. 가져온 거래는 수수료가 비어 있습니다."
NO_RULES_KO = "규칙과 정책을 아직 적지 않았어요."
NO_POLICY_KO = "정책을 아직 적지 않았어요."
IMPORTED_NO_NOTE_KO = "가져온 거래 {n}건은 메모 없이 들어옵니다."
FX_MISSING_SKIPPED_KO = "환율이 없어 비용 계산에서 뺀 거래 {n}건"
CASH_NOT_COMPARED_KO = "현금은 적지 않아 비교에서 뺐어요(주식·코인은 투자금 기준)"

# Evidence line templates. Numbers only; the UI appends "표본 N건" from `EvidenceLine.n`.
TOP1_LINE_KO = "가장 큰 종목 {sym} 비중 {pct}% (상한 {cap}%)"
EFFECTIVE_N_LINE_KO = "실질 종목 수 {n}개 (보유 {count}개)"
CRYPTO_SHARE_LINE_KO = "코인 비중 {pct}% (상한 {cap}%)"
OVERSIZED_LINE_KO = "{n}번 중 {k}번은 매수 뒤 그 종목이 투자원금의 {cap}%를 넘었어요"
LARGEST_BUY_LINE_KO = "가장 큰 한 번 매수가 이 기간 매수 총액의 {pct}%"
TOTAL_RISK_LINE_KO = "손절선까지 손실 합 {x}% (한도 {y}%)"
AVG_DOWN_LINE_KO = "추가 매수 {n}번 중 손절선 아래 물타기 {k}번"
LAG_LINE_KO = "손절선 아래에 머문 채 들고 있는 종목 {k}개 ({detail})"
LAG_DETAIL_KO = "{sym} {days}봉{more}"
# `rule_lag` counts bars from the start of the range it was given; when every bar was below
# the stop, the run began earlier than that, so the count is a floor (same words as the coach).
LAG_SINCE_START_KO = " 이상(조회 범위 처음부터)"
SUSPICIOUS_EXCLUDED_LINE_KO = "단가 확인이 필요한 거래 {n}건은 비용 계산에서 뺐어요"
CHASE_LINE_KO = "{n}번 매수 중 {k}번이 {lookback}봉 동안 {pct}% 넘게 오른 뒤였어요"
SELL_COUNT_LINE_KO = "손실 매도 {a}건 · 이익 매도 {b}건"
FLAT_SUFFIX_KO = " · 본전 {c}건"
REBUY_LINE_KO = "손실 매도 {n}건 중 {k}건은 {days}일 안에 다시 샀어요"
# The rebuy flags come from the coach's one-year window, so the denominator is the loss sells
# of that same window and the line says so (the span in days, not an assumed "1년").
REBUY_WINDOW_LINE_KO = "최근 {span}일 손실 매도 {n}건 중 {k}건은 {days}일 안에 다시 샀어요"
HOLD_MEDIAN_LINE_KO = "이익 매도까지 중간 보유 {d1}일 vs 손실 매도까지 {d2}일"
FEE_LINE_KO = "거래 비용 합 {fee}원 = 거래 금액의 {pct}%"
FEE_RECORDED_LINE_KO = "수수료가 적힌 거래 {k}건 / {n}건"
BUSY_MONTHS_LINE_KO = "평소보다 2배 넘게 거래한 달 {k}개 ({months})"
NOTE_LINE_KO = "{n}건 중 메모가 있는 거래 {k}건"
TRIP_MEDIAN_LINE_KO = "닫힌 포지션 {n}개의 중간 보유 기간 {d}일"
SHORT_TRIPS_LINE_KO = "{k}개는 {days}일 안에 정리"
OPEN_POSITIONS_LINE_KO = "지금 들고 있는 {detail}"
OPEN_POSITION_DETAIL_KO = "{sym} {days}일째"
CLASS_LINE_KO = "주식 {a}% (목표 {b}%) · 코인 {c}% (목표 {d}%)"
CASH_CLASS_SUFFIX_KO = " · 현금 {e}% (목표 {f}%)"
CLASS_CURRENT_LINE_KO = "지금 주식 {a}% · 코인 {c}%"


# --- dataclasses ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceLine:
    """One sentence of evidence with the number behind it and the trades it points to."""

    text_ko: str
    value: float | None = None
    n: int | None = None
    trade_ids: tuple[int, ...] = ()
    symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillEvidence:
    """Evidence for one habit code. `level` is the strength of the evidence; `sample_n`
    below `min_sample` makes it `insufficient`. `window_start` None means "today's state".
    `severity` orders items within a level and is never shown."""

    code: str
    label_ko: str
    level: Level
    level_ko: str
    sample_n: int
    min_sample: int
    window_start: date | None
    window_end: date
    lines: tuple[EvidenceLine, ...]
    lesson_ids: tuple[str, ...]
    caveat_ko: str | None = None
    excluded_suspicious: int = 0
    severity: float = 0.0


@dataclass(frozen=True)
class SkillThresholds:
    """Boundaries of the evidence levels. Tuples are (some, strong) and inclusive (≥), except
    `note_share`, where a memo share *below* the value is the finding."""

    min_sample: int = 5
    min_sells: int = 4
    min_round_trips: int = 3
    chase_share: tuple[float, float] = (0.15, 0.30)
    oversized_share: tuple[float, float] = (0.10, 0.30)
    avg_down_share_strong: float = 0.20
    rebuy_share_strong: float = 0.50
    hold_ratio: tuple[float, float] = (1.5, 2.0)
    fee_bps: tuple[float, float] = (25.0, 50.0)
    fee_recorded_min_share: float = 0.5
    note_share: tuple[float, float] = (0.60, 0.20)
    short_trip_days: int = 30
    short_trip_share: tuple[float, float] = (0.25, 0.50)
    effective_n: tuple[float, float] = (3.0, 2.0)
    min_holdings_for_effective_n: int = 3
    drift_pt_factor: float = 1.0


DEFAULT_THRESHOLDS = SkillThresholds()


@dataclass(frozen=True)
class RoundTrip:
    """One position from its first buy to the sell that emptied it (`closed` None while it
    is still held). KRW amounts use the rate of each trade."""

    symbol: str
    currency: str
    opened: date
    closed: date | None
    buys: int
    sells: int
    invested_krw: float
    realized_krw: float
    trade_ids: tuple[int, ...]
    suspicious: bool


@dataclass(frozen=True)
class SellOutcome:
    """One sell judged in its trade currency against the ledger's average cost."""

    trade_id: int
    symbol: str
    date: date
    outcome: Outcome
    pnl_pct: float
    days_held: int
    excluded: bool


@dataclass(frozen=True)
class BuySizing:
    """One buy with the cost-basis share of the symbol right after it: the symbol's
    fee-inclusive KRW cost over everything invested (fee-inclusive) once this buy is in.
    None for the first money in, when nothing was invested before. `notional_krw` is the
    buy's quantity × price × rate without the fee."""

    trade_id: int
    symbol: str
    date: date
    notional_krw: float
    invested_before_krw: float
    symbol_share_after_pct: float | None
    excluded: bool


@dataclass(frozen=True)
class Replay:
    round_trips: tuple[RoundTrip, ...]
    sells: tuple[SellOutcome, ...]
    buys: tuple[BuySizing, ...]
    open_since: dict[str, date]


# --- helpers ---------------------------------------------------------------------------------


def _check_today(today: object) -> date:
    if not isinstance(today, date):
        raise ValueError("today must be a date")
    return today


def _check_window(window_start: object, today: date) -> date | None:
    if window_start is None:
        return None
    if not isinstance(window_start, date):
        raise ValueError("window_start must be a date or None")
    if window_start > today:
        raise ValueError("window_start must not be after today")
    return window_start


def _count(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _ratio(k: int, n: int) -> float:
    return k / n if n > 0 else 0.0


def _pct(x: float, digits: int = 1) -> str:
    return f"{x:.{digits}f}"


def _g(x: float) -> str:
    return f"{x:g}"


def _level_for(sample_n: int, min_sample: int, *, strong: bool, some: bool) -> Level:
    if sample_n < min_sample:
        return "insufficient"
    if strong:
        return "strong"
    if some:
        return "some"
    return "none"


def _at_least(level: Level, floor: Level) -> Level:
    return level if LEVEL_ORDER[level] <= LEVEL_ORDER[floor] else floor


def _evidence(
    code: str,
    level: Level,
    *,
    sample_n: int,
    min_sample: int,
    window_start: date | None,
    window_end: date,
    lines: Sequence[EvidenceLine],
    caveat_ko: str | None = None,
    excluded_suspicious: int = 0,
    severity: float = 0.0,
) -> SkillEvidence:
    return SkillEvidence(
        code=code,
        label_ko=SKILL_LABELS_KO[code],
        level=level,
        level_ko=LEVEL_LABELS_KO[level],
        sample_n=sample_n,
        min_sample=min_sample,
        window_start=window_start,
        window_end=window_end,
        lines=tuple(lines),
        lesson_ids=SKILL_LESSONS[code],
        caveat_ko=caveat_ko,
        excluded_suspicious=excluded_suspicious,
        severity=float(severity),
    )


def sample_ko(n: int) -> str:
    """ "표본 N건" as the UI appends it to every line."""
    return SAMPLE_KO.format(n=_count("n", n))


# --- position replay -------------------------------------------------------------------------


@dataclass
class _Position:
    currency: str
    opened: date
    cost_krw: float = 0.0
    buys: int = 0
    sells: int = 0
    invested_krw: float = 0.0
    realized_krw: float = 0.0
    trade_ids: list[int] = field(default_factory=list)
    suspicious: bool = False
    last_date: date | None = None


def _fx_of(t: TradeView) -> float:
    if t.currency == "KRW":
        return 1.0
    if t.fx_krw is None:
        raise ValueError(f"trade {t.id}: fx_krw is required for a {t.currency} trade")
    return t.fx_krw


def _trip(symbol: str, p: _Position, closed: date | None) -> RoundTrip:
    return RoundTrip(
        symbol=symbol,
        currency=p.currency,
        opened=p.opened,
        closed=closed,
        buys=p.buys,
        sells=p.sells,
        invested_krw=p.invested_krw,
        realized_krw=p.realized_krw,
        trade_ids=tuple(p.trade_ids),
        suspicious=p.suspicious,
    )


def replay_trades(
    trades: Iterable[TradeView], today: date, suspicious_ids: frozenset[int] = frozenset()
) -> Replay:
    """Replay the trades in (date, id) order, accumulating KRW cost on top of the ledger's
    `qty_before` (already split-adjusted), without re-running the ledger.

    A buy with `qty_before ≤ EPS` opens a round trip (re-entry after a liquidation is a new
    trip). Each buy adds `(qty·price + fee)·fx` (fee-inclusive, as the ledger's cost basis)
    to the symbol's cost and reports its share of everything invested right after it,
    `cost_after / (invested_before + this buy's fee-inclusive cost)` (None for the first
    money in).
    Each sell releases a pro-rata share of the cost, adds `proceeds − released` to the
    realised KRW, and is judged in its trade currency: `qty·price − fee` against
    `avg_cost_before·qty` (the ledger's average cost includes buy fees), flat within
    `EPS·basis`. A sell of the whole quantity closes the trip.

    Trades in `suspicious_ids` (the coach's 20× price check) are replayed as they are, mark
    their trip `suspicious`, and that trade plus every later buy and sell of the same trip
    is `excluded` from the size and outcome evidence (their cost basis is contaminated).

    ValueError: a non-KRW trade without `fx_krw`, a sell with nothing held or without an
    average cost, a sell or an add-on buy of a symbol the series never bought, a duplicate
    id, or a trade dated after `today`.
    """
    day = _check_today(today)
    ordered = sorted(trades, key=lambda t: (t.date, t.id))
    seen: set[int] = set()
    positions: dict[str, _Position] = {}
    trips: list[RoundTrip] = []
    sells: list[SellOutcome] = []
    buys: list[BuySizing] = []

    for t in ordered:
        if t.id in seen:
            raise ValueError(f"trade {t.id} appears twice")
        seen.add(t.id)
        if t.date > day:
            raise ValueError(f"trade {t.id}: dated {t.date}, after today {day}")
        fx = _fx_of(t)
        gross = t.quantity * t.price
        pos = positions.get(t.symbol)

        if t.side == "buy":
            if t.qty_before <= EPS:
                if pos is not None:
                    # The ledger says nothing is held, so the earlier trip ended on its last
                    # trade; start a fresh one.
                    trips.append(_trip(t.symbol, pos, pos.last_date))
                pos = _Position(currency=t.currency, opened=t.date)
                positions[t.symbol] = pos
            elif pos is None:
                raise ValueError(
                    f"trade {t.id}: {t.symbol} is held before its first buy in the series"
                )
            invested_before = sum(p.cost_krw for p in positions.values())
            notional = gross * fx
            if t.id in suspicious_ids:
                pos.suspicious = True
            # Cost is fee-inclusive, like the ledger's cost basis; the share below puts the
            # same fee-inclusive cost in numerator and denominator (a single-symbol record
            # reads exactly 100%). `notional` (fees out) only sizes the "largest buy" line.
            cost = (gross + t.fee) * fx
            pos.cost_krw += cost
            pos.invested_krw += cost
            pos.buys += 1
            pos.trade_ids.append(t.id)
            pos.last_date = t.date
            base = invested_before + cost
            share = pos.cost_krw / base * 100 if invested_before > EPS and base > 0 else None
            buys.append(
                BuySizing(
                    trade_id=t.id,
                    symbol=t.symbol,
                    date=t.date,
                    notional_krw=notional,
                    invested_before_krw=invested_before,
                    symbol_share_after_pct=share,
                    excluded=pos.suspicious,
                )
            )
            continue

        # sell
        if t.qty_before <= EPS or t.avg_cost_before is None:
            raise ValueError(f"trade {t.id}: sell of {t.symbol} with nothing held")
        if pos is None:
            raise ValueError(f"trade {t.id}: sell of {t.symbol} before any buy in the series")
        if t.id in suspicious_ids:
            pos.suspicious = True
        basis = t.avg_cost_before * t.quantity
        if basis <= 0:
            raise ValueError(f"trade {t.id}: avg_cost_before must be positive to judge a sell")
        share = min(t.quantity / t.qty_before, 1.0)
        released = pos.cost_krw * share
        proceeds = (gross - t.fee) * fx
        pos.realized_krw += proceeds - released
        pos.cost_krw -= released
        net = gross - t.fee
        diff = net - basis
        outcome: Outcome = "flat" if abs(diff) <= EPS * basis else ("gain" if diff > 0 else "loss")
        pos.sells += 1
        pos.trade_ids.append(t.id)
        pos.last_date = t.date
        sells.append(
            SellOutcome(
                trade_id=t.id,
                symbol=t.symbol,
                date=t.date,
                outcome=outcome,
                pnl_pct=(net / basis - 1.0) * 100,
                days_held=(t.date - pos.opened).days,
                excluded=pos.suspicious,
            )
        )
        if t.quantity >= t.qty_before - 1e-8:
            pos.cost_krw = 0.0
            trips.append(_trip(t.symbol, pos, t.date))
            del positions[t.symbol]

    open_since: dict[str, date] = {}
    for symbol in sorted(positions):
        trips.append(_trip(symbol, positions[symbol], None))
        open_since[symbol] = positions[symbol].opened
    return Replay(tuple(trips), tuple(sells), tuple(buys), open_since)


# --- evidence: today's state ---------------------------------------------------------------------


def concentration_evidence(
    holdings: Sequence[HoldingView],
    cash_krw: float | None,
    policy: Policy,
    cap_pct_of: Callable[[str], float],
    today: date,
    th: SkillThresholds = DEFAULT_THRESHOLDS,
) -> SkillEvidence:
    """How much sits in one place today: largest weight against its cap (`cap_pct_of`, the
    service's `policy.limits(...)` symbol cap in percent, index-fund exception included),
    effective number of holdings (1/HHI), crypto share against the policy cap. n = holdings."""
    day = _check_today(today)
    code = "concentration"
    n = len(holdings)
    if n == 0:
        return _evidence(
            code,
            "insufficient",
            sample_n=0,
            min_sample=1,
            window_start=None,
            window_end=day,
            lines=[],
        )
    ws = weights(holdings, cash_krw)
    conc = concentration(ws)
    exp = exposure(holdings, cash_krw)
    top = max(ws, key=lambda w: w.weight_pct)
    cap = _num(f"cap_pct_of({top.symbol})", cap_pct_of(top.symbol), lo=0.0)
    lines = [
        EvidenceLine(
            TOP1_LINE_KO.format(sym=top.symbol, pct=_pct(top.weight_pct), cap=_g(cap)),
            value=top.weight_pct,
            n=n,
            symbols=(top.symbol,),
        ),
        EvidenceLine(
            EFFECTIVE_N_LINE_KO.format(n=_pct(conc.effective_n), count=n),
            value=conc.effective_n,
            n=n,
        ),
    ]
    if exp.crypto_pct > EPS:
        lines.append(
            EvidenceLine(
                CRYPTO_SHARE_LINE_KO.format(
                    pct=_pct(exp.crypto_pct), cap=_g(policy.max_crypto_weight_pct)
                ),
                value=exp.crypto_pct,
                n=n,
                symbols=tuple(h.symbol for h in holdings if h.asset_class == "crypto"),
            )
        )
    enough = n >= th.min_holdings_for_effective_n
    strong = top.weight_pct > cap + 10.0 + EPS or (enough and conc.effective_n < th.effective_n[1])
    some = (
        top.weight_pct > cap + EPS
        or (enough and conc.effective_n < th.effective_n[0])
        or exp.crypto_pct > policy.max_crypto_weight_pct + EPS
    )
    severity = max(
        top.weight_pct / cap if cap > 0 else 0.0,
        exp.crypto_pct / policy.max_crypto_weight_pct,
        (th.effective_n[0] / conc.effective_n) if enough and conc.effective_n > 0 else 0.0,
    )
    return _evidence(
        code,
        _level_for(n, 1, strong=strong, some=some),
        sample_n=n,
        min_sample=1,
        window_start=None,
        window_end=day,
        lines=lines,
        severity=severity,
    )


def class_drift_evidence(
    exposure: Exposure | None,
    policy: Policy,
    policy_set: bool,
    today: date,
    th: SkillThresholds = DEFAULT_THRESHOLDS,
    *,
    holdings_count: int | None = None,
) -> SkillEvidence:
    """Today's asset-class shares against the policy targets. Without a saved policy (or
    without exposure) the item is `insufficient` with `NO_POLICY_KO`. When no cash record
    exists the stock/crypto targets are renormalised to the invested amount, as the coach's
    own `class_drift` violation does, and cash is left out of the comparison. Drift beyond
    `rebalance_band_pt × drift_pt_factor` is `some`, beyond twice that `strong`.

    The sample of a today's-state item is the number of holdings: pass `holdings_count` and
    it becomes `sample_n` and the `n` of every line (nothing held → `insufficient`). Without
    it (`Exposure` carries no count) `sample_n` is the number of classes compared and the
    lines carry no `n`, so the UI shows no "표본 0건"."""
    day = _check_today(today)
    code = "class_drift"
    count = None if holdings_count is None else _count("holdings_count", holdings_count)
    if not policy_set or exposure is None:
        lines: list[EvidenceLine] = []
        if exposure is not None:
            lines.append(
                EvidenceLine(
                    CLASS_CURRENT_LINE_KO.format(
                        a=_pct(exposure.stock_pct), c=_pct(exposure.crypto_pct)
                    ),
                    n=count,
                )
            )
        return _evidence(
            code,
            "insufficient",
            sample_n=count or 0,
            min_sample=1,
            window_start=None,
            window_end=day,
            lines=lines,
            caveat_ko=NO_POLICY_KO,
        )
    cash_known = exposure.cash_pct is not None
    if cash_known:
        t_stock, t_crypto = policy.target_stock_pct, policy.target_crypto_pct
    else:
        invested = policy.target_stock_pct + policy.target_crypto_pct
        t_stock = policy.target_stock_pct / invested * 100 if invested > 0 else 0.0
        t_crypto = policy.target_crypto_pct / invested * 100 if invested > 0 else 0.0
    drifts = [abs(exposure.stock_pct - t_stock), abs(exposure.crypto_pct - t_crypto)]
    text = CLASS_LINE_KO.format(
        a=_pct(exposure.stock_pct), b=_pct(t_stock), c=_pct(exposure.crypto_pct), d=_pct(t_crypto)
    )
    if cash_known:
        drifts.append(abs((exposure.cash_pct or 0.0) - policy.target_cash_pct))
        text += CASH_CLASS_SUFFIX_KO.format(
            e=_pct(exposure.cash_pct or 0.0), f=_pct(policy.target_cash_pct)
        )
    else:
        text += " · " + CASH_NOT_COMPARED_KO
    n = len(drifts) if count is None else count
    worst = max(drifts)
    band = policy.rebalance_band_pt * _num("drift_pt_factor", th.drift_pt_factor, lo=0.0)
    return _evidence(
        code,
        _level_for(n, 1, strong=worst > 2 * band + EPS, some=worst > band + EPS),
        sample_n=n,
        min_sample=1,
        window_start=None,
        window_end=day,
        lines=[EvidenceLine(text, value=worst, n=count)],
        severity=worst / band if band > 0 else worst,
    )


# --- evidence: the past year of trades ----------------------------------------------------------


def oversizing_evidence(
    replay: Replay,
    policy: Policy,
    total_risk_pct: float | None,
    window_start: date,
    today: date,
    th: SkillThresholds = DEFAULT_THRESHOLDS,
) -> SkillEvidence:
    """Buys in the window after which the symbol's cost-basis share exceeded the policy's
    position cap. n = buys with a share (not the first money in) that are not excluded. A
    `total_risk_pct` above the policy cap always adds a line and, once the sample reaches
    `min_sample`, makes the item at least `some` (a thin record stays `insufficient`)."""
    day = _check_today(today)
    start = _check_window(window_start, day)
    code = "oversizing"
    in_window = [b for b in replay.buys if start is None or b.date >= start]
    excluded = sum(1 for b in in_window if b.excluded)
    clean = [b for b in in_window if not b.excluded]
    sized = [b for b in clean if b.symbol_share_after_pct is not None]
    n = len(sized)
    cap = policy.max_position_weight_pct
    over = [b for b in sized if (b.symbol_share_after_pct or 0.0) > cap + EPS]
    share = _ratio(len(over), n)
    lines: list[EvidenceLine] = []
    if n > 0:
        lines.append(
            EvidenceLine(
                OVERSIZED_LINE_KO.format(n=n, k=len(over), cap=_g(cap)),
                value=share * 100,
                n=n,
                trade_ids=tuple(b.trade_id for b in over),
                symbols=tuple(dict.fromkeys(b.symbol for b in over)),
            )
        )
    total = sum(b.notional_krw for b in clean)
    if len(clean) >= 2 and total > 0:
        largest = max(clean, key=lambda b: b.notional_krw)
        lines.append(
            EvidenceLine(
                LARGEST_BUY_LINE_KO.format(pct=_pct(largest.notional_krw / total * 100)),
                value=largest.notional_krw / total * 100,
                n=len(clean),
                trade_ids=(largest.trade_id,),
                symbols=(largest.symbol,),
            )
        )
    level = _level_for(
        n, th.min_sample, strong=share >= th.oversized_share[1], some=share >= th.oversized_share[0]
    )
    severity = share
    if total_risk_pct is not None:
        risk = _num("total_risk_pct", total_risk_pct)
        if risk > policy.max_total_risk_pct + EPS:
            lines.append(
                EvidenceLine(
                    TOTAL_RISK_LINE_KO.format(x=_pct(risk), y=_g(policy.max_total_risk_pct)),
                    value=risk,
                    n=n,
                )
            )
            if n >= th.min_sample:
                level = _at_least(level, "some")
            severity = max(severity, risk / policy.max_total_risk_pct - 1.0)
    return _evidence(
        code,
        level,
        sample_n=n,
        min_sample=th.min_sample,
        window_start=start,
        window_end=day,
        lines=lines,
        caveat_ko=COST_BASIS_PROXY_KO,
        excluded_suspicious=excluded,
        severity=severity,
    )


def rule_breaking_evidence(
    recent: Sequence[TradeView],
    averaging: Sequence[Flag],
    lag: Sequence[LagFlag],
    positions_checked: int,
    policy_set: bool,
    rules_set: bool,
    window_start: date,
    today: date,
    th: SkillThresholds = DEFAULT_THRESHOLDS,
) -> SkillEvidence:
    """Add-on buys below the stop line (`averaging`, from the coach) and positions still
    held below it (`lag`). n = add-on buys in the window + positions the lag check looked
    at. With neither a policy nor rules saved the item carries `NO_RULES_KO` and, once the
    sample reaches `min_sample`, is at least `some` (the checks then ran against the default
    rules); an empty record stays `insufficient`."""
    day = _check_today(today)
    start = _check_window(window_start, day)
    code = "rule_breaking"
    checked = _count("positions_checked", positions_checked)
    adds = [
        t
        for t in recent
        if t.side == "buy" and t.qty_before > EPS and (start is None or t.date >= start)
    ]
    n = len(adds) + checked
    avg_share = _ratio(len(averaging), len(adds))
    lines: list[EvidenceLine] = []
    if adds:
        lines.append(
            EvidenceLine(
                AVG_DOWN_LINE_KO.format(n=len(adds), k=len(averaging)),
                value=avg_share * 100,
                n=len(adds),
                trade_ids=tuple(f.trade_id for f in averaging),
                symbols=tuple(dict.fromkeys(f.symbol for f in averaging)),
            )
        )
    if lag:
        detail = " · ".join(
            LAG_DETAIL_KO.format(
                sym=f.symbol, days=f.days, more=LAG_SINCE_START_KO if f.since_window_start else ""
            )
            for f in lag
        )
        lines.append(
            EvidenceLine(
                LAG_LINE_KO.format(k=len(lag), detail=detail),
                value=float(max(f.days for f in lag)),
                n=checked,
                symbols=tuple(f.symbol for f in lag),
            )
        )
    strong = len(lag) >= 1 and avg_share >= th.avg_down_share_strong
    some = len(lag) >= 1 or len(averaging) >= 1
    level = _level_for(n, th.min_sample, strong=strong, some=some)
    caveat = None
    if not policy_set and not rules_set:
        # The caveat always; the `some` floor only once there is a sample to speak of, so an
        # empty record stays "기록 부족" rather than "조금 보임 · 표본 0건".
        caveat = NO_RULES_KO
        if n >= th.min_sample:
            level = _at_least(level, "some")
    return _evidence(
        code,
        level,
        sample_n=n,
        min_sample=th.min_sample,
        window_start=start,
        window_end=day,
        lines=lines,
        caveat_ko=caveat,
        severity=max(avg_share, _ratio(len(lag), checked)),
    )


def chasing_evidence(
    flags: Sequence[Flag],
    buys_with_bars: int,
    window_start: date,
    today: date,
    th: SkillThresholds = DEFAULT_THRESHOLDS,
    *,
    lookback: int = 20,
    threshold_pct: float = 15.0,
) -> SkillEvidence:
    """Share of buys (among those with enough bars) made right after a run-up, from the
    coach's `chasing_buys` flags. `lookback`/`threshold_pct` only word the line and must
    match what produced the flags (the coach defaults)."""
    day = _check_today(today)
    start = _check_window(window_start, day)
    code = "chasing"
    n = _count("buys_with_bars", buys_with_bars)
    k = len(flags)
    if k > n:
        raise ValueError("more chasing flags than buys with bars")
    share = _ratio(k, n)
    lines: list[EvidenceLine] = []
    if n > 0:
        lines.append(
            EvidenceLine(
                CHASE_LINE_KO.format(n=n, k=k, lookback=lookback, pct=_g(threshold_pct)),
                value=share * 100,
                n=n,
                trade_ids=tuple(f.trade_id for f in flags),
                symbols=tuple(dict.fromkeys(f.symbol for f in flags)),
            )
        )
    return _evidence(
        code,
        _level_for(
            n, th.min_sample, strong=share >= th.chase_share[1], some=share >= th.chase_share[0]
        ),
        sample_n=n,
        min_sample=th.min_sample,
        window_start=start,
        window_end=day,
        lines=lines,
        severity=share,
    )


def cost_blindness_evidence(
    trades: Sequence[TradeView],
    busy_months: Sequence[MonthCount],
    window_start: date,
    today: date,
    th: SkillThresholds = DEFAULT_THRESHOLDS,
    *,
    suspicious_ids: frozenset[int] = frozenset(),
) -> SkillEvidence:
    """Fees as basis points of traded value over the window, and months of unusually many
    trades (the coach's `overtrading`). Trades in `suspicious_ids` (the 20× price check) are
    left out of n, both sums and the recorded share — one wrong price would swamp the
    denominator — and reported in `excluded_suspicious` and a line. Trades without a KRW
    rate are left out of both sums and counted in a line. When fewer than
    `fee_recorded_min_share` of the priced trades carry a fee (imports carry none), the
    basis-point reading is given up — caveat
    `NO_FEES_RECORDED_KO`, no bps term in `severity` — and the level comes from the busy
    months alone (`strong` at two or more, `some` at one, else `insufficient`)."""
    day = _check_today(today)
    start = _check_window(window_start, day)
    code = "cost_blindness"
    in_window = [t for t in trades if start is None or t.date >= start]
    suspicious = [t for t in in_window if t.id in suspicious_ids]
    usable = [t for t in in_window if t.id not in suspicious_ids]
    n = len(usable)
    fee_sum = 0.0
    notional_sum = 0.0
    skipped = 0
    recorded = 0
    priced = 0
    for t in usable:
        fx = 1.0 if t.currency == "KRW" else t.fx_krw
        if fx is None:
            skipped += 1
            continue
        priced += 1
        fee_sum += t.fee * fx
        notional_sum += t.quantity * t.price * fx
        if t.fee > 0:
            recorded += 1
    bps = fee_sum / notional_sum * 1e4 if notional_sum > 0 else 0.0
    recorded_share = _ratio(recorded, priced)
    lines: list[EvidenceLine] = []
    if priced > 0:
        lines.append(
            EvidenceLine(
                FEE_LINE_KO.format(fee=f"{fee_sum:,.0f}", pct=_pct(bps / 100, 2)),
                value=bps,
                n=priced,
            )
        )
        if recorded < priced:
            lines.append(
                EvidenceLine(
                    FEE_RECORDED_LINE_KO.format(k=recorded, n=priced),
                    value=recorded_share * 100,
                    n=priced,
                )
            )
    if skipped:
        lines.append(EvidenceLine(FX_MISSING_SKIPPED_KO.format(n=skipped), n=skipped))
    if suspicious:
        lines.append(
            EvidenceLine(
                SUSPICIOUS_EXCLUDED_LINE_KO.format(n=len(suspicious)),
                n=len(suspicious),
                trade_ids=tuple(t.id for t in suspicious),
                symbols=tuple(dict.fromkeys(t.symbol for t in suspicious)),
            )
        )
    busy = len(busy_months)
    if busy:
        lines.append(
            EvidenceLine(
                BUSY_MONTHS_LINE_KO.format(k=busy, months=", ".join(m.month for m in busy_months)),
                value=float(busy),
                n=busy,
            )
        )
    caveat = None
    fees_usable = recorded_share >= th.fee_recorded_min_share
    if n >= th.min_sample and not fees_usable:
        # Too few fees recorded (imports carry none): give up the basis-point reading, keep
        # judging by the busy months alone.
        caveat = NO_FEES_RECORDED_KO
        level = _level_for(n, th.min_sample, strong=busy >= 2, some=busy >= 1)
        if level == "none":
            level = "insufficient"
    else:
        level = _level_for(
            n,
            th.min_sample,
            strong=bps >= th.fee_bps[1] or busy >= 2,
            some=bps >= th.fee_bps[0] or busy >= 1,
        )
    bps_term = bps / th.fee_bps[1] if fees_usable and th.fee_bps[1] > 0 else 0.0
    return _evidence(
        code,
        level,
        sample_n=n,
        min_sample=th.min_sample,
        window_start=start,
        window_end=day,
        lines=lines,
        caveat_ko=caveat,
        excluded_suspicious=len(suspicious),
        severity=max(bps_term, busy / 2.0),
    )


def no_journal_evidence(
    trades: Sequence[TradeView],
    window_start: date,
    today: date,
    th: SkillThresholds = DEFAULT_THRESHOLDS,
) -> SkillEvidence:
    """Share of trades in the window that carry the user's own memo (`origin == "manual"`
    and a non-blank `note`). A share *below* `note_share[1]` is `strong`, below
    `note_share[0]` `some` (the boundary itself is not below). Imported trades are counted
    in a line of their own because they never carry a memo."""
    day = _check_today(today)
    start = _check_window(window_start, day)
    code = "no_journal"
    in_window = [t for t in trades if start is None or t.date >= start]
    n = len(in_window)
    noted = [t for t in in_window if t.origin == "manual" and t.note and t.note.strip()]
    imported = [t for t in in_window if t.origin == "import"]
    share = _ratio(len(noted), n)
    lines: list[EvidenceLine] = []
    if n > 0:
        lines.append(
            EvidenceLine(
                NOTE_LINE_KO.format(n=n, k=len(noted)),
                value=share * 100,
                n=n,
                trade_ids=tuple(t.id for t in in_window if t not in noted),
            )
        )
    if imported:
        lines.append(
            EvidenceLine(
                IMPORTED_NO_NOTE_KO.format(n=len(imported)),
                value=float(len(imported)),
                n=len(imported),
                trade_ids=tuple(t.id for t in imported),
            )
        )
    return _evidence(
        code,
        _level_for(
            n, th.min_sample, strong=share < th.note_share[1], some=share < th.note_share[0]
        ),
        sample_n=n,
        min_sample=th.min_sample,
        window_start=start,
        window_end=day,
        lines=lines,
        severity=1.0 - share,
    )


# --- evidence: the whole record -----------------------------------------------------------------


def _first_opened(replay: Replay) -> date | None:
    return min((r.opened for r in replay.round_trips), default=None)


def loss_holding_evidence(
    replay: Replay,
    rebuys: Sequence[Flag],
    today: date,
    th: SkillThresholds = DEFAULT_THRESHOLDS,
    *,
    rebuy_days: int = 10,
    rebuy_window_start: date | None = None,
) -> SkillEvidence:
    """Over the whole record: sells that ended in a loss vs a gain, how often a loss sell
    was followed by a rebuy within `rebuy_days` (the coach's `quick_rebuy_after_loss`
    flags), and the median holding time before gain sells vs loss sells (each when at
    least three). n = sells not excluded; `min_sells` of them are needed.

    The rebuy flags are produced over the coach's pattern window, so `rebuy_window_start`
    (the same date) makes the rebuy share's denominator the loss sells dated on or after it
    — otherwise a long record would dilute a recent habit — and the line names the span.
    None keeps the whole record as the denominator. A flag names only the rebuy (symbol and
    date), so it is paired here with the most recent loss sell of that symbol dated within
    `rebuy_days` before it, and counted only when that sell is in the denominator; a flag
    without such a sell, or whose sell lies before the window, is left out of the share and
    of the line's `trade_ids`. The share counts distinct paired sells, so it never exceeds
    100%. The sell counts and the median holding times always use the whole record
    (samples are scarce there)."""
    day = _check_today(today)
    code = "loss_holding"
    start = _first_opened(replay)
    rebuy_start = _check_window(rebuy_window_start, day)
    if rebuy_days < 0:
        raise ValueError("rebuy_days must not be negative")
    usable = [s for s in replay.sells if not s.excluded]
    excluded = len(replay.sells) - len(usable)
    n = len(usable)
    losses = [s for s in usable if s.outcome == "loss"]
    gains = [s for s in usable if s.outcome == "gain"]
    flats = n - len(losses) - len(gains)
    recent_losses = [s for s in losses if rebuy_start is None or s.date >= rebuy_start]
    denominator = {s.trade_id for s in recent_losses}
    matched: list[Flag] = []
    paired_sells: set[int] = set()
    for f in rebuys:
        earliest = f.date - timedelta(days=rebuy_days)
        candidates = [s for s in losses if s.symbol == f.symbol and earliest <= s.date < f.date]
        if not candidates:
            continue
        sell = max(candidates, key=lambda s: (s.date, s.trade_id))
        if sell.trade_id in denominator:
            matched.append(f)
            paired_sells.add(sell.trade_id)
    rebuy_share = _ratio(len(paired_sells), len(recent_losses))
    lines: list[EvidenceLine] = []
    if n > 0:
        text = SELL_COUNT_LINE_KO.format(a=len(losses), b=len(gains))
        if flats:
            text += FLAT_SUFFIX_KO.format(c=flats)
        lines.append(
            EvidenceLine(
                text,
                value=_ratio(len(losses), n) * 100,
                n=n,
                trade_ids=tuple(s.trade_id for s in losses),
                symbols=tuple(dict.fromkeys(s.symbol for s in losses)),
            )
        )
    if recent_losses:
        k = len(paired_sells)
        if rebuy_start is None:
            text = REBUY_LINE_KO.format(n=len(recent_losses), k=k, days=rebuy_days)
        else:
            text = REBUY_WINDOW_LINE_KO.format(
                span=(day - rebuy_start).days, n=len(recent_losses), k=k, days=rebuy_days
            )
        lines.append(
            EvidenceLine(
                text,
                value=rebuy_share * 100,
                n=len(recent_losses),
                trade_ids=tuple(f.trade_id for f in matched),
                symbols=tuple(dict.fromkeys(f.symbol for f in matched)),
            )
        )
    hold_multiple = 0.0
    if len(gains) >= 3 and len(losses) >= 3:
        d_gain = float(statistics.median(s.days_held for s in gains))
        d_loss = float(statistics.median(s.days_held for s in losses))
        hold_multiple = d_loss / d_gain if d_gain > 0 else (float("inf") if d_loss > 0 else 1.0)
        lines.append(
            EvidenceLine(
                HOLD_MEDIAN_LINE_KO.format(d1=_g(d_gain), d2=_g(d_loss)),
                value=hold_multiple if hold_multiple != float("inf") else None,
                n=len(gains) + len(losses),
            )
        )
    strong = rebuy_share >= th.rebuy_share_strong or hold_multiple >= th.hold_ratio[1]
    some = len(paired_sells) >= 1 or hold_multiple >= th.hold_ratio[0]
    severity = max(rebuy_share, hold_multiple if hold_multiple != float("inf") else 10.0)
    return _evidence(
        code,
        _level_for(n, th.min_sells, strong=strong, some=some),
        sample_n=n,
        min_sample=th.min_sells,
        window_start=start,
        window_end=day,
        lines=lines,
        excluded_suspicious=excluded,
        severity=severity,
    )


def short_holding_evidence(
    replay: Replay, today: date, th: SkillThresholds = DEFAULT_THRESHOLDS
) -> SkillEvidence:
    """Over the whole record: median holding time of closed round trips and the share
    closed within `short_trip_days`. n = closed, non-suspicious trips; `min_round_trips`
    needed. Open positions are listed with their age even when the item is `insufficient`."""
    day = _check_today(today)
    code = "short_holding"
    start = _first_opened(replay)
    closed = [r for r in replay.round_trips if r.closed is not None]
    usable = [r for r in closed if not r.suspicious]
    n = len(usable)
    days = {r.trade_ids: (r.closed - r.opened).days for r in usable if r.closed is not None}
    short = [r for r in usable if days[r.trade_ids] < th.short_trip_days]
    share = _ratio(len(short), n)
    lines: list[EvidenceLine] = []
    if n > 0:
        median_days = float(statistics.median(days.values()))
        lines.append(
            EvidenceLine(TRIP_MEDIAN_LINE_KO.format(n=n, d=_g(median_days)), value=median_days, n=n)
        )
        lines.append(
            EvidenceLine(
                SHORT_TRIPS_LINE_KO.format(k=len(short), days=th.short_trip_days),
                value=share * 100,
                n=n,
                trade_ids=tuple(i for r in short for i in r.trade_ids),
                symbols=tuple(dict.fromkeys(r.symbol for r in short)),
            )
        )
    if replay.open_since:
        ages = sorted(
            ((sym, (day - since).days) for sym, since in replay.open_since.items()),
            key=lambda x: (-x[1], x[0]),
        )
        detail = " · ".join(OPEN_POSITION_DETAIL_KO.format(sym=s, days=d) for s, d in ages)
        lines.append(
            EvidenceLine(
                OPEN_POSITIONS_LINE_KO.format(detail=detail),
                value=float(ages[0][1]),
                n=len(ages),
                symbols=tuple(s for s, _ in ages),
            )
        )
    return _evidence(
        code,
        _level_for(
            n,
            th.min_round_trips,
            strong=share >= th.short_trip_share[1],
            some=share >= th.short_trip_share[0],
        ),
        sample_n=n,
        min_sample=th.min_round_trips,
        window_start=start,
        window_end=day,
        lines=lines,
        excluded_suspicious=len(closed) - n,
        severity=share,
    )


# --- ordering and first topics -------------------------------------------------------------------


def rank_skills(evidences: Iterable[SkillEvidence]) -> list[SkillEvidence]:
    """strong → some → none → insufficient; within a level by `severity` descending, then
    by code. This is the order the page shows; it is not a ranking of the person."""
    return sorted(evidences, key=lambda e: (LEVEL_ORDER[e.level], -e.severity, e.code))


def first_topics(
    ranked: Sequence[SkillEvidence], default: Sequence[str], catalog_ids: Collection[str]
) -> tuple[tuple[str, ...], TopicsSource]:
    """Up to three lesson ids to read first: those of the `strong`/`some` items in ranked
    order, deduplicated and limited to `catalog_ids` ("ranking"); when none, the first
    three of `default` ("default")."""
    picked: list[str] = []
    for e in ranked:
        if e.level not in ("strong", "some"):
            continue
        for lesson in e.lesson_ids:
            if lesson in catalog_ids and lesson not in picked:
                picked.append(lesson)
    if picked:
        return tuple(picked[:3]), "ranking"
    fallback = [d for d in dict.fromkeys(default) if d in catalog_ids]
    return tuple(fallback[:3]), "default"


__all__ = [
    "AVG_DOWN_LINE_KO",
    "BUSY_MONTHS_LINE_KO",
    "CASH_CLASS_SUFFIX_KO",
    "CASH_NOT_COMPARED_KO",
    "CHASE_LINE_KO",
    "CLASS_CURRENT_LINE_KO",
    "CLASS_LINE_KO",
    "COST_BASIS_PROXY_KO",
    "CRYPTO_SHARE_LINE_KO",
    "DEFAULT_THRESHOLDS",
    "EFFECTIVE_N_LINE_KO",
    "FEE_LINE_KO",
    "FEE_RECORDED_LINE_KO",
    "FLAT_SUFFIX_KO",
    "FX_MISSING_SKIPPED_KO",
    "HOLD_MEDIAN_LINE_KO",
    "IMPORTED_NO_NOTE_KO",
    "LAG_DETAIL_KO",
    "LAG_LINE_KO",
    "LAG_SINCE_START_KO",
    "LARGEST_BUY_LINE_KO",
    "LEARN_DISCLAIMER_KO",
    "LEVEL_LABELS_KO",
    "LEVEL_ORDER",
    "NOTE_LINE_KO",
    "NO_FEES_RECORDED_KO",
    "NO_POLICY_KO",
    "NO_RULES_KO",
    "OPEN_POSITIONS_LINE_KO",
    "OPEN_POSITION_DETAIL_KO",
    "OVERSIZED_LINE_KO",
    "REBUY_LINE_KO",
    "REBUY_WINDOW_LINE_KO",
    "SAMPLE_KO",
    "SELL_COUNT_LINE_KO",
    "SHORT_TRIPS_LINE_KO",
    "SKILL_LABELS_KO",
    "SKILL_LESSONS",
    "SUSPICIOUS_EXCLUDED_LINE_KO",
    "TOP1_LINE_KO",
    "TOTAL_RISK_LINE_KO",
    "TRIP_MEDIAN_LINE_KO",
    "BuySizing",
    "EvidenceLine",
    "Level",
    "Outcome",
    "Replay",
    "RoundTrip",
    "SellOutcome",
    "SkillEvidence",
    "SkillThresholds",
    "TopicsSource",
    "chasing_evidence",
    "class_drift_evidence",
    "concentration_evidence",
    "cost_blindness_evidence",
    "first_topics",
    "loss_holding_evidence",
    "no_journal_evidence",
    "oversizing_evidence",
    "rank_skills",
    "replay_trades",
    "rule_breaking_evidence",
    "sample_ko",
    "short_holding_evidence",
]
