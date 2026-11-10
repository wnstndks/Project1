"""Hand-computed answers for the learning coach evidence (app/strategy/skills.py, D-034).

Written by the evaluation engineer, apart from the module's author (CLAUDE.md: whoever
builds a module and whoever checks its numbers are different people). Every expected value
is derived by hand or from a one-line formula written next to the assertion, never by
running the module; the behavioural tests live in tests/test_skills.py. The contract is
plan J (`replay_trades` accumulates KRW cost on top of the ledger's split-adjusted
`qty_before`; a sell is judged in its trade currency against `avg_cost_before`, which the
ledger computes with buy fees included). All inputs are synthetic (AAA, BBB, CCC, U*, O*).

Where the module's figure differs from the hand value, the test is left failing and the
gap is reported to the lead instead of bending the expectation.
"""

from datetime import date, timedelta

import pytest

from app.strategy.coach import (
    Exposure,
    Flag,
    HoldingView,
    LagFlag,
    MonthCount,
    Policy,
    TradeView,
)
from app.strategy.skills import (
    CASH_NOT_COMPARED_KO,
    CHASE_LINE_KO,
    COST_BASIS_PROXY_KO,
    DEFAULT_THRESHOLDS,
    IMPORTED_NO_NOTE_KO,
    LAG_DETAIL_KO,
    LAG_LINE_KO,
    LAG_SINCE_START_KO,
    LEVEL_LABELS_KO,
    NO_FEES_RECORDED_KO,
    NO_POLICY_KO,
    NO_RULES_KO,
    REBUY_LINE_KO,
    REBUY_WINDOW_LINE_KO,
    SKILL_LABELS_KO,
    SKILL_LESSONS,
    SUSPICIOUS_EXCLUDED_LINE_KO,
    SkillEvidence,
    SkillThresholds,
    chasing_evidence,
    class_drift_evidence,
    concentration_evidence,
    cost_blindness_evidence,
    first_topics,
    loss_holding_evidence,
    no_journal_evidence,
    oversizing_evidence,
    rank_skills,
    replay_trades,
    rule_breaking_evidence,
    short_holding_evidence,
)

TODAY = date(2026, 10, 30)
D0 = date(2026, 1, 5)  # TODAY − D0 = 298 days, so every date below is on or before TODAY
WINDOW = TODAY - timedelta(days=365)
CAP20 = Policy(max_position_weight_pct=20.0)


def day(offset: int) -> date:
    return D0 + timedelta(days=offset)


# --- helpers (they only build inputs; no expected value comes from the module) ------------------


def trade(
    id: int,
    symbol: str,
    side: str,
    on: date,
    qty: float,
    price: float,
    qty_before: float,
    avg_before: float | None,
    *,
    fee: float = 0.0,
    fx: float | None = 1000.0,
    currency: str = "USD",
    asset_class: str = "stock",
    origin: str = "manual",
    note: str | None = None,
) -> TradeView:
    return TradeView(
        id=id,
        symbol=symbol,
        asset_class=asset_class,  # type: ignore[arg-type]
        side=side,
        date=on,
        quantity=qty,
        price=price,
        currency=currency,
        avg_cost_before=avg_before,
        qty_before=qty_before,
        fee=fee,
        fx_krw=fx,
        origin=origin,
        note=note,
    )


def krw_trade(id: int, on: date, notional: float, fee: float, symbol: str = "BBB") -> TradeView:
    """One KRW coin buy of `notional` won (quantity 1) with `fee` won; fx_krw is None, which
    the module must read as a rate of 1 for KRW."""
    return trade(
        id,
        symbol,
        "buy",
        on,
        1,
        notional,
        0,
        None,
        fee=fee,
        fx=None,
        currency="KRW",
        asset_class="crypto",
    )


def holding(symbol: str, value_krw: float, asset_class: str = "stock") -> HoldingView:
    return HoldingView(
        symbol=symbol,
        asset_class=asset_class,  # type: ignore[arg-type]
        currency="USD" if asset_class == "stock" else "KRW",
        quantity=1.0,
        price=value_krw,
        price_krw=value_krw,
        value_krw=value_krw,
        cost_basis_krw=value_krw,
    )


def flag(code: str, trade_id: int, symbol: str = "AAA", on: date = D0) -> Flag:
    return Flag(code, "x", trade_id, symbol, on, "detail", None)


def exposure_of(stock: float, crypto: float, cash: float | None) -> Exposure:
    return Exposure(100.0, 100.0, stock, crypto, cash, stock)


def evidence(code: str, level: str, severity: float = 0.0) -> SkillEvidence:
    return SkillEvidence(
        code=code,
        label_ko=SKILL_LABELS_KO[code],
        level=level,  # type: ignore[arg-type]
        level_ko=LEVEL_LABELS_KO[level],
        sample_n=5,
        min_sample=5,
        window_start=None,
        window_end=TODAY,
        lines=(),
        lesson_ids=SKILL_LESSONS[code],
        severity=severity,
    )


# --- 1. replay: the briefing record, derived by hand ----------------------------------------
#
# fx 1,000 on every trade, so KRW = USD × 1,000.
#   D0     buy  10 @ 100, fee 1  → cost 1,001 USD = 1,001,000 KRW; ledger avg 1,001/10 = 100.1
#   D0+5   buy  10 @ 80,  fee 1  → cost   801 USD =   801,000 KRW; ledger avg (1,001+801)/20 = 90.1
#   D0+20  sell  5 @ 95          → net 475; basis 90.1×5 = 450.5; 475 − 450.5 = +24.5 → gain
#                                  pnl_pct = (475/450.5 − 1)×100 = 49/901×100 = 5.4384 %
#                                  KRW: released 1,802,000 × 5/20 = 450,500;
#                                  proceeds 475,000 → +24,500
#   D0+40  sell 15 @ 85          → net 1,275; basis 90.1×15 = 1,351.5; → loss
#                                  pnl_pct = (1,275/1,351.5 − 1)×100 = −3/53×100 = −5.6604 %
#                                  KRW: released 1,351,500 (all); proceeds 1,275,000 → −76,500
#   D0+50  buy   3 @ 90          → qty_before 0 → second round trip (cost 270,000 KRW)
# Trip 1: invested 1,802,000; realized 24,500 − 76,500 = −52,000; closed D0+40.
#
# NOTE: the briefing quotes "475/450.25 ≈ 5.497" with avg (1,001+801)/20 = 90.1; those two
# do not agree (90.1 × 5 = 450.5, not 450.25). 450.25 is 90.05 × 5, i.e. (1,000+800+1)/20,
# one fee short; the same slip is in test_skills.py's fixture comment. The ledger
# (`Position.apply`: cost_basis += qty×price + fee) gives 90.1, so 450.5 is used here.
# `replay_trades` takes avg_cost_before from the caller, so this is a fixture question, not a
# module one; realized_krw does not depend on it.

AVG_AFTER_BUY1 = 1_001 / 10  # 100.1
AVG_AFTER_BUY2 = (1_001 + 801) / 20  # 90.1
BRIEFING_RECORD = [
    trade(1, "AAA", "buy", day(0), 10, 100, 0, None, fee=1),
    trade(2, "AAA", "buy", day(5), 10, 80, 10, AVG_AFTER_BUY1, fee=1),
    trade(3, "AAA", "sell", day(20), 5, 95, 20, AVG_AFTER_BUY2),
    trade(4, "AAA", "sell", day(40), 15, 85, 15, AVG_AFTER_BUY2),
    trade(5, "AAA", "buy", day(50), 3, 90, 0, None),
]


def test_replay_round_trips_by_hand():
    r = replay_trades(BRIEFING_RECORD, TODAY)
    assert len(r.round_trips) == 2
    first, second = r.round_trips
    assert (first.opened, first.closed) == (day(0), day(40))
    assert (first.buys, first.sells) == (2, 2)
    assert first.trade_ids == (1, 2, 3, 4)
    assert first.currency == "USD" and first.suspicious is False
    assert first.invested_krw == pytest.approx(1_001_000 + 801_000)
    assert first.realized_krw == pytest.approx(24_500 - 76_500)
    assert first.realized_krw == pytest.approx(-52_000)
    # re-entry after the liquidation: a fresh trip, still open, cost 3 × 90 × 1,000
    assert (second.opened, second.closed) == (day(50), None)
    assert second.trade_ids == (5,)
    assert second.invested_krw == pytest.approx(270_000)
    assert second.realized_krw == pytest.approx(0.0)
    assert r.open_since == {"AAA": day(50)}


def test_replay_sell_outcomes_by_hand():
    r = replay_trades(BRIEFING_RECORD, TODAY)
    gain, loss = r.sells
    assert (gain.trade_id, gain.outcome, gain.days_held) == (3, "gain", 20)
    assert gain.pnl_pct == pytest.approx(49 / 901 * 100, abs=1e-9)
    assert gain.pnl_pct == pytest.approx(5.4384, abs=1e-4)
    assert (loss.trade_id, loss.outcome, loss.days_held) == (4, "loss", 40)
    assert loss.pnl_pct == pytest.approx(-3 / 53 * 100, abs=1e-9)
    assert loss.pnl_pct == pytest.approx(-5.6604, abs=1e-4)
    assert not gain.excluded and not loss.excluded


def test_replay_buy_sizing_by_hand():
    r = replay_trades(BRIEFING_RECORD, TODAY)
    b1, b2, b3 = r.buys
    # first money in: nothing invested before → no share (left out of the sizing sample)
    assert (b1.invested_before_krw, b1.symbol_share_after_pct) == (0.0, None)
    assert b1.notional_krw == pytest.approx(1_000_000)
    # second buy: AAA cost after = 1,802,000; base = 1,001,000 before + 801,000 this buy's
    # cost (fee included on both sides, D-034 amendment a) → exactly 100%: a single-symbol
    # record can never exceed 100%. notional_krw itself stays ex-fee (largest-buy line).
    assert b2.invested_before_krw == pytest.approx(1_001_000)
    assert b2.notional_krw == pytest.approx(800_000)
    assert b2.symbol_share_after_pct == pytest.approx(1_802_000 / (1_001_000 + 801_000) * 100)
    assert b2.symbol_share_after_pct == pytest.approx(100.0)
    # re-entry after liquidation is the first money in again
    assert (b3.invested_before_krw, b3.symbol_share_after_pct) == (0.0, None)


def test_replay_fails_closed_on_bad_input():
    # a sell with nothing held (qty_before 0)
    with pytest.raises(ValueError):
        replay_trades([trade(1, "AAA", "sell", day(0), 1, 10, 0, None)], TODAY)
    # a sell of a symbol the series never bought, even though the ledger says it is held
    with pytest.raises(ValueError):
        replay_trades([trade(1, "AAA", "sell", day(0), 1, 10, 5, 10.0)], TODAY)
    # a USD trade without its KRW rate: no silent substitute
    with pytest.raises(ValueError):
        replay_trades([trade(1, "AAA", "buy", day(0), 1, 10, 0, None, fx=None)], TODAY)
    # an add-on buy (qty_before > 0) of a symbol the series never bought
    with pytest.raises(ValueError):
        replay_trades([trade(1, "AAA", "buy", day(0), 1, 10, 5, 10.0)], TODAY)
    # dated after today
    with pytest.raises(ValueError):
        replay_trades([trade(1, "AAA", "buy", TODAY + timedelta(days=1), 1, 10, 0, None)], TODAY)
    # the same id twice
    with pytest.raises(ValueError):
        replay_trades(
            [
                trade(1, "AAA", "buy", day(0), 1, 10, 0, None),
                trade(1, "BBB", "buy", day(1), 1, 10, 0, None),
            ],
            TODAY,
        )


def test_replay_krw_trade_needs_no_rate():
    # KRW trade: fx_krw None must be read as 1, so 0.5 × 100,000,000 = 50,000,000 won
    t = trade(
        1,
        "BBB",
        "buy",
        day(0),
        0.5,
        100_000_000,
        0,
        None,
        fx=None,
        currency="KRW",
        asset_class="crypto",
    )
    r = replay_trades([t], TODAY)
    assert r.buys[0].notional_krw == pytest.approx(50_000_000)
    assert r.round_trips[0].invested_krw == pytest.approx(50_000_000)
    assert r.round_trips[0].currency == "KRW"


# --- 2. replay: a 4:1 split between the buy and the sell ------------------------------------
#
# fx 1 (so KRW = trade currency).  D0: buy 10 @ 100 → cost 1,000.  Then a 4:1 split: the
# ledger (which replays corporate actions) now reports qty_before = 40 and avg_cost_before =
# 1,000/40 = 25.  D0+30: sell 40 @ 30 → gross 1,200.
#   share of the position sold = min(40/40, 1) = 1 → released = 1,000 (all the KRW cost)
#   realized = 1,200 − 1,000 = +200;  the trip closes because 40 ≥ qty_before 40
#   outcome in trade currency: net 1,200 vs basis 25 × 40 = 1,000 → gain, pnl +20%
# The replay never sees the split itself: it trusts qty_before/avg_cost_before and only
# accumulates won. If the ledger had NOT applied the split (qty_before 10, avg 100) the sell
# of 40 would still release the whole 1,000 (share capped at 1) and realized would still be
# +200, but the sell would be judged against basis 100 × 40 = 4,000 → "loss", pnl −70%.
# So a split error shows up in outcome/pnl_pct, not in realized_krw.


def test_replay_split_adjusted_sell_closes_trip_on_full_cost():
    trades = [
        trade(1, "AAA", "buy", day(0), 10, 100, 0, None, fx=1.0),
        trade(2, "AAA", "sell", day(30), 40, 30, 40, 25.0, fx=1.0),
    ]
    r = replay_trades(trades, TODAY)
    (trip,) = r.round_trips
    assert (trip.opened, trip.closed) == (day(0), day(30))
    assert trip.invested_krw == pytest.approx(1_000)
    assert trip.realized_krw == pytest.approx(1_200 - 1_000)
    assert trip.trade_ids == (1, 2)
    assert r.open_since == {}
    (sell,) = r.sells
    assert (sell.outcome, sell.days_held) == ("gain", 30)
    assert sell.pnl_pct == pytest.approx((1_200 / 1_000 - 1) * 100)


def test_replay_split_adjusted_partial_sell_releases_pro_rata():
    # same split; sell 20 of the 40 at 30 (gross 600): share 20/40 = 0.5 → released 500,
    # realized +100, 500 of cost stays; then sell the remaining 20 (qty_before 20, avg 25):
    # released 500, +100 more → total +200 and the trip closes
    trades = [
        trade(1, "AAA", "buy", day(0), 10, 100, 0, None, fx=1.0),
        trade(2, "AAA", "sell", day(30), 20, 30, 40, 25.0, fx=1.0),
        trade(3, "AAA", "sell", day(60), 20, 30, 20, 25.0, fx=1.0),
    ]
    r = replay_trades(trades[:2], TODAY)
    (open_trip,) = r.round_trips
    assert open_trip.closed is None
    assert open_trip.realized_krw == pytest.approx(100)
    assert r.open_since == {"AAA": day(0)}
    r2 = replay_trades(trades, TODAY)
    (closed_trip,) = r2.round_trips
    assert closed_trip.closed == day(60)
    assert closed_trip.realized_krw == pytest.approx(200)
    assert [s.outcome for s in r2.sells] == ["gain", "gain"]
    assert [s.days_held for s in r2.sells] == [30, 60]


# --- 3. sizing: cost-basis share after a buy and the oversizing boundaries ------------------


def test_sizing_share_is_symbol_cost_over_total_cost_after_the_buy():
    # fx 1, no fees. BBB 3,000 first → share None (nothing before). AAA 1,000 next:
    # AAA cost 1,000 / (3,000 before + 1,000 notional) = 25%.
    r = replay_trades(
        [
            trade(1, "BBB", "buy", day(0), 1, 3_000, 0, None, fx=1.0),
            trade(2, "AAA", "buy", day(1), 1, 1_000, 0, None, fx=1.0),
        ],
        TODAY,
    )
    assert r.buys[0].symbol_share_after_pct is None
    assert r.buys[1].invested_before_krw == pytest.approx(3_000)
    assert r.buys[1].symbol_share_after_pct == pytest.approx(25.0)
    # same symbol: AAA 3,000 then AAA 1,000 (qty_before 1, ledger avg 3,000) → AAA cost 4,000
    # over (3,000 + 1,000) = 100%: the share is cumulative cost, not this buy alone
    r2 = replay_trades(
        [
            trade(1, "AAA", "buy", day(0), 1, 3_000, 0, None, fx=1.0),
            trade(2, "AAA", "buy", day(1), 1, 1_000, 1, 3_000.0, fx=1.0),
        ],
        TODAY,
    )
    assert r2.buys[1].symbol_share_after_pct == pytest.approx(100.0)
    # with a fee of 10 on the AAA buy: numerator 1,010, denominator 3,000 + 1,010 = 4,010
    # (the fee sits on both sides) → 25.187%
    r3 = replay_trades(
        [
            trade(1, "BBB", "buy", day(0), 1, 3_000, 0, None, fx=1.0),
            trade(2, "AAA", "buy", day(1), 1, 1_000, 0, None, fee=10, fx=1.0),
        ],
        TODAY,
    )
    assert r3.buys[1].symbol_share_after_pct == pytest.approx(1_010 / 4_010 * 100)


def sized_record(k_over: int, n: int) -> tuple[list[TradeView], list[int]]:
    """BBB 1,000 first (share None, not in the sample), then `n` buys of fresh symbols at fx 1
    with no fee: n − k_over buys of 1 won each (share 1/(1,000 + i) < 0.1%, under any cap),
    then k_over buys each equal to everything invested before it (share p/(p + p) = 50%,
    over a 20% cap). Returns the trades and the ids of the over-cap buys."""
    trades = [trade(100, "BBB", "buy", day(0), 1, 1_000, 0, None, fx=1.0)]
    before = 1_000.0
    over_ids: list[int] = []
    next_id = 101
    for i in range(n - k_over):
        trades.append(trade(next_id, f"U{i}", "buy", day(next_id - 100), 1, 1, 0, None, fx=1.0))
        before += 1
        next_id += 1
    for i in range(k_over):
        trades.append(
            trade(next_id, f"O{i}", "buy", day(next_id - 100), 1, before, 0, None, fx=1.0)
        )
        over_ids.append(next_id)
        before *= 2
        next_id += 1
    return trades, over_ids


@pytest.mark.parametrize(
    ("k_over", "n", "level"),
    [
        (3, 10, "strong"),  # 3/10 = 0.30 ≥ 0.30
        (2, 10, "some"),  # 0.20: below 0.30, at or above 0.10
        (1, 10, "some"),  # 0.10 ≥ 0.10, the some boundary itself
        (0, 10, "none"),  # 0/10
        (2, 4, "insufficient"),  # n = 4 < min_sample 5, whatever the share
    ],
)
def test_oversizing_boundaries_one_buy_apart(k_over, n, level):
    trades, over_ids = sized_record(k_over, n)
    e = oversizing_evidence(replay_trades(trades, TODAY), CAP20, None, D0, TODAY)
    assert (e.level, e.sample_n, e.min_sample) == (level, n, 5)
    assert e.caveat_ko == COST_BASIS_PROXY_KO
    assert e.lines[0].trade_ids == tuple(over_ids)
    assert e.lines[0].value == pytest.approx(k_over / n * 100)
    assert (
        e.lines[0].text_ko == f"{n}번 중 {k_over}번은 매수 뒤 그 종목이 투자원금의 20%를 넘었어요"
    )
    assert e.severity == pytest.approx(k_over / n)


def test_oversizing_largest_buy_line_by_hand():
    # k=3, n=10: notionals 1,000 + 7 × 1 + 1,007 + 2,014 + 4,028 = 8,056; the largest buy
    # doubled the total, so it is exactly half: 4,028 / 8,056 = 50.0% (n = all 11 clean buys)
    trades, over_ids = sized_record(3, 10)
    e = oversizing_evidence(replay_trades(trades, TODAY), CAP20, None, D0, TODAY)
    assert e.lines[1].value == pytest.approx(50.0)
    assert e.lines[1].n == 11 and e.lines[1].trade_ids == (over_ids[-1],)
    assert e.lines[1].text_ko == "가장 큰 한 번 매수가 이 기간 매수 총액의 50.0%"
    # k=0: largest is the 1,000 base over 1,000 + 10 = 1,010 → 99.0099%
    trades0, _ = sized_record(0, 10)
    e0 = oversizing_evidence(replay_trades(trades0, TODAY), CAP20, None, D0, TODAY)
    assert e0.lines[1].value == pytest.approx(1_000 / 1_010 * 100)


def test_oversizing_total_risk_breach_floors_at_some_only_with_a_sample():
    # 0/10 over → none on its own; total risk 9% > cap 8% adds a line, floors to some
    # (n = 10 ≥ min_sample), and severity = max(0, 9/8 − 1) = 0.125
    trades, _ = sized_record(0, 10)
    r = replay_trades(trades, TODAY)
    e = oversizing_evidence(r, Policy(max_total_risk_pct=8.0), 9.0, D0, TODAY)
    assert (e.level, e.sample_n) == ("some", 10)
    assert e.lines[-1].text_ko == "손절선까지 손실 합 9.0% (한도 8%)"
    assert e.severity == pytest.approx(0.125)
    # exactly at the cap: no line, no floor
    at_cap = oversizing_evidence(r, Policy(max_total_risk_pct=8.0), 8.0, D0, TODAY)
    assert at_cap.level == "none" and len(at_cap.lines) == 2
    # below the sample the line is still added but nothing is floored (N-LEARN-3):
    # n = 0 (a single first buy has no share) and n = 4 both stay insufficient; severity
    # still carries 9/8 − 1
    single = replay_trades([trade(1, "AAA", "buy", day(0), 1, 100, 0, None)], TODAY)
    e0 = oversizing_evidence(single, Policy(max_total_risk_pct=8.0), 9.0, D0, TODAY)
    assert (e0.level, e0.sample_n) == ("insufficient", 0)
    assert e0.lines == (e0.lines[-1],)  # no sizing lines for one buy, only the risk line
    assert e0.lines[-1].text_ko == "손절선까지 손실 합 9.0% (한도 8%)"
    assert e0.severity == pytest.approx(0.125)
    four, _ = sized_record(0, 4)
    e4 = oversizing_evidence(
        replay_trades(four, TODAY), Policy(max_total_risk_pct=8.0), 9.0, D0, TODAY
    )
    assert (e4.level, e4.sample_n) == ("insufficient", 4)
    assert e4.lines[-1].text_ko == "손절선까지 손실 합 9.0% (한도 8%)"
    # and n = 5 is enough: 5 under-cap buys + the breach → some
    five, _ = sized_record(0, 5)
    e5 = oversizing_evidence(
        replay_trades(five, TODAY), Policy(max_total_risk_pct=8.0), 9.0, D0, TODAY
    )
    assert (e5.level, e5.sample_n) == ("some", 5)


def test_oversizing_window_drops_earlier_buys():
    # window starting at the first over-cap buy: the 7 under buys and the base fall out, so
    # the sample is the 3 over buys (3/3 → strong when min_sample allows) and the largest-buy
    # line is over those three: 4,028 / (1,007 + 2,014 + 4,028) = 57.14%
    trades, over_ids = sized_record(3, 10)
    start = day(over_ids[0] - 100)
    e = oversizing_evidence(replay_trades(trades, TODAY), CAP20, None, start, TODAY)
    assert e.sample_n == 3 and e.level == "insufficient" and e.window_start == start
    assert e.lines[1].value == pytest.approx(4_028 / 7_049 * 100)
    loose = oversizing_evidence(
        replay_trades(trades, TODAY), CAP20, None, start, TODAY, SkillThresholds(min_sample=3)
    )
    assert loose.level == "strong"


# --- 4. chasing -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("k", "n", "level"),
    [
        (2, 5, "strong"),  # 0.40 ≥ 0.30
        (6, 20, "strong"),  # 0.30 exactly
        (1, 6, "some"),  # 0.1667 ≥ 0.15
        (3, 20, "some"),  # 0.15 exactly
        (1, 10, "none"),  # 0.10 < 0.15
        (2, 3, "insufficient"),  # n = 3 < 5 even though 0.67
        (0, 0, "insufficient"),  # no buys with bars at all
    ],
)
def test_chasing_boundaries(k, n, level):
    flags = [flag("chasing_buy", i) for i in range(1, k + 1)]
    e = chasing_evidence(flags, n, WINDOW, TODAY)
    assert (e.level, e.sample_n, e.min_sample) == (level, n, 5)
    assert (e.window_start, e.window_end) == (WINDOW, TODAY)
    assert e.severity == pytest.approx(k / n if n else 0.0)
    if n:
        assert e.lines[0].value == pytest.approx(k / n * 100)
        # the wording is the module's constant (it changed once already: "움직인" → "오른");
        # only the numbers in it are the hand values
        assert e.lines[0].text_ko == CHASE_LINE_KO.format(n=n, k=k, lookback=20, pct=15)
        assert e.lines[0].trade_ids == tuple(range(1, k + 1))
    else:
        assert e.lines == ()


def test_chasing_more_flags_than_buys_is_an_error():
    with pytest.raises(ValueError):
        chasing_evidence([flag("chasing_buy", 1), flag("chasing_buy", 2)], 1, WINDOW, TODAY)


# --- 5. memo share --------------------------------------------------------------------------
#
# Rule (plan J.7): a memo share BELOW 0.20 is strong, BELOW 0.60 some; the boundary itself is
# not below. So 1/5 = 0.20 → some (not strong), 3/5 = 0.60 → none (not some). The briefing's
# "3/5 → some" contradicts the rule it quotes; the rule is followed here.


def memo_record(
    noted: int, total: int, origin: str = "manual", note: str = "why"
) -> list[TradeView]:
    return [
        trade(
            i,
            "AAA",
            "buy",
            day(i),
            1,
            10,
            0,
            None,
            origin=origin,
            note=note if i <= noted else None,
        )
        for i in range(1, total + 1)
    ]


@pytest.mark.parametrize(
    ("noted", "total", "level"),
    [
        (0, 5, "strong"),  # 0.00 < 0.20
        (1, 5, "some"),  # 0.20 is not < 0.20, is < 0.60
        (2, 5, "some"),  # 0.40
        (3, 5, "none"),  # 0.60 is not < 0.60
        (4, 5, "none"),  # 0.80
        (0, 4, "insufficient"),  # n = 4 < 5
    ],
)
def test_no_journal_boundaries(noted, total, level):
    e = no_journal_evidence(memo_record(noted, total), WINDOW, TODAY)
    assert (e.level, e.sample_n) == (level, total)
    assert e.lines[0].value == pytest.approx(noted / total * 100)
    assert e.lines[0].text_ko == f"{total}건 중 메모가 있는 거래 {noted}건"
    # the line points at the trades WITHOUT a memo
    assert e.lines[0].trade_ids == tuple(range(noted + 1, total + 1))
    assert e.severity == pytest.approx(1 - noted / total)
    assert len(e.lines) == 1  # no imported trades → no import line


def test_no_journal_imported_trades_never_count_as_noted():
    # five imported trades, every one with a note: the module requires origin == "manual",
    # so noted = 0/5 → strong, and the import line says 5 came in without a memo
    e = no_journal_evidence(memo_record(5, 5, origin="import"), WINDOW, TODAY)
    assert e.level == "strong" and e.lines[0].value == pytest.approx(0.0)
    assert e.lines[1].text_ko == IMPORTED_NO_NOTE_KO.format(n=5)
    assert e.lines[1].trade_ids == (1, 2, 3, 4, 5)
    # 4 manual noted + 1 imported noted: 4/5 = 0.80 → none; import line counts 1
    mixed = memo_record(4, 4) + [
        trade(5, "BBB", "buy", day(5), 1, 10, 0, None, origin="import", note="auto")
    ]
    e2 = no_journal_evidence(mixed, WINDOW, TODAY)
    assert e2.level == "none" and e2.lines[0].value == pytest.approx(80.0)
    assert e2.lines[0].trade_ids == (5,)
    assert e2.lines[1].text_ko == IMPORTED_NO_NOTE_KO.format(n=1) and e2.lines[1].trade_ids == (5,)
    # a demo trade with a note is neither noted nor imported (it only lowers the share)
    demo = memo_record(4, 4) + [
        trade(5, "BBB", "buy", day(5), 1, 10, 0, None, origin="demo", note="x")
    ]
    e3 = no_journal_evidence(demo, WINDOW, TODAY)
    assert e3.lines[0].value == pytest.approx(80.0) and len(e3.lines) == 1
    # a blank note is no memo
    blank = memo_record(4, 4) + [trade(5, "BBB", "buy", day(5), 1, 10, 0, None, note="   ")]
    assert no_journal_evidence(blank, WINDOW, TODAY).lines[0].value == pytest.approx(80.0)


def test_no_journal_window_excludes_earlier_trades():
    # trades on D0+1 … D0+5; a window starting D0+3 keeps 3 of them (2 of the 3 noted)
    e = no_journal_evidence(memo_record(4, 5), day(3), TODAY)
    assert e.sample_n == 3 and e.lines[0].value == pytest.approx(2 / 3 * 100)
    assert e.window_start == day(3)


# --- 6. costs: fee basis points over the window ---------------------------------------------
#
# fee_bps = Σ fee·fx / Σ qty·price·fx × 10,000 over the trades that have a rate; a trade
# counts as "recorded" when fee > 0, and fewer than half recorded (among n ≥ 5) makes the
# item insufficient with NO_FEES_RECORDED_KO. KRW trades take fx 1; USD trades need fx_krw.


def fee_record(fees: list[float], notional: float = 420_000) -> list[TradeView]:
    return [krw_trade(i, day(i), notional, f) for i, f in enumerate(fees, start=1)]


def test_cost_no_fees_recorded_is_insufficient_with_caveat():
    e = cost_blindness_evidence(fee_record([0, 0, 0, 0, 0]), [], WINDOW, TODAY)
    assert (e.level, e.sample_n, e.caveat_ko) == ("insufficient", 5, NO_FEES_RECORDED_KO)
    assert e.lines[0].text_ko == "거래 비용 합 0원 = 거래 금액의 0.00%"
    assert e.lines[1].text_ko == "수수료가 적힌 거래 0건 / 5건"
    assert e.severity == pytest.approx(0.0)
    # with no fees recorded the busy months alone set the level (D-034 amendment b):
    # 2 → strong, 1 → some, 0 → insufficient; the caveat stays on and severity = busy / 2
    busy = [MonthCount("2026-03", 4, 4, 8), MonthCount("2026-07", 5, 5, 10)]
    e2 = cost_blindness_evidence(fee_record([0, 0, 0, 0, 0]), busy, WINDOW, TODAY)
    assert (e2.level, e2.caveat_ko) == ("strong", NO_FEES_RECORDED_KO)
    assert e2.lines[-1].text_ko == "평소보다 2배 넘게 거래한 달 2개 (2026-03, 2026-07)"
    assert e2.severity == pytest.approx(1.0)
    e1 = cost_blindness_evidence(fee_record([0, 0, 0, 0, 0]), busy[:1], WINDOW, TODAY)
    assert (e1.level, e1.caveat_ko) == ("some", NO_FEES_RECORDED_KO)
    assert e1.severity == pytest.approx(0.5)


def test_cost_unrecorded_fees_drop_the_bp_reading_but_not_the_line():
    # 2 of 5 recorded (0.4 < 0.5) at 5,000 won each: 10,000 / 2,000,000 = 50 bp would be
    # strong on a usable record; with too few fees recorded the bp reading is given up:
    # no busy month → insufficient and severity 0 (bp term zeroed), one → some, 0.5.
    # The fee line still prints the 50 bp it saw.
    fees = fee_record([5_000, 5_000, 0, 0, 0], 400_000)
    e = cost_blindness_evidence(fees, [], WINDOW, TODAY)
    assert (e.level, e.caveat_ko) == ("insufficient", NO_FEES_RECORDED_KO)
    assert e.lines[0].value == pytest.approx(50.0)
    assert e.lines[1].text_ko == "수수료가 적힌 거래 2건 / 5건"
    assert e.severity == pytest.approx(0.0)
    one_busy = cost_blindness_evidence(fees, [MonthCount("2026-03", 4, 4, 8)], WINDOW, TODAY)
    assert (one_busy.level, one_busy.caveat_ko) == ("some", NO_FEES_RECORDED_KO)
    assert one_busy.severity == pytest.approx(0.5)


def test_cost_hand_calculation_9_52bp_is_none():
    # 500 + 500 + 1,000 = 2,000 won over 5 × 420,000 = 2,100,000 won
    # → 2,000 / 2,100,000 × 10,000 = 9.5238 bp = 0.0952% → prints 0.10%; 3 of 5 recorded (0.6 ≥ 0.5)
    e = cost_blindness_evidence(fee_record([500, 500, 1_000, 0, 0]), [], WINDOW, TODAY)
    assert (e.level, e.sample_n, e.caveat_ko) == ("none", 5, None)
    assert e.lines[0].value == pytest.approx(2_000 / 2_100_000 * 1e4)
    assert e.lines[0].value == pytest.approx(9.5238, abs=1e-4)
    assert e.lines[0].text_ko == "거래 비용 합 2,000원 = 거래 금액의 0.10%"
    assert e.lines[1].text_ko == "수수료가 적힌 거래 3건 / 5건"
    assert e.lines[1].value == pytest.approx(60.0)
    assert e.severity == pytest.approx(9.5238 / 50, abs=1e-4)


@pytest.mark.parametrize(
    ("fee", "level"),
    [
        (2_000, "strong"),  # 10,000 / 2,000,000 = 50.0 bp, the strong boundary itself
        (1_999, "some"),  # 9,995 / 2,000,000 = 49.975 bp
        (1_000, "some"),  # 5,000 / 2,000,000 = 25.0 bp, the some boundary itself
        (999, "none"),  # 4,995 / 2,000,000 = 24.975 bp
    ],
)
def test_cost_bp_boundaries_are_inclusive(fee, level):
    # 5 KRW buys of 400,000 won each (2,000,000 won traded), the same fee on each
    e = cost_blindness_evidence(fee_record([fee] * 5, notional=400_000), [], WINDOW, TODAY)
    assert e.level == level
    assert e.lines[0].value == pytest.approx(fee * 5 / 2_000_000 * 1e4)
    assert len(e.lines) == 1  # every trade recorded → no "k건 / n건" line


def test_cost_recorded_share_boundary_is_inclusive():
    # 2 of 5 recorded = 0.4 < 0.5 → insufficient; 3 of 6 = 0.5 is not below → evaluated:
    # 3,000 / (6 × 400,000) × 10,000 = 12.5 bp → none
    two_of_five = cost_blindness_evidence(
        fee_record([1_000, 1_000, 0, 0, 0], 400_000), [], WINDOW, TODAY
    )
    assert two_of_five.level == "insufficient" and two_of_five.caveat_ko == NO_FEES_RECORDED_KO
    three_of_six = cost_blindness_evidence(
        fee_record([1_000, 1_000, 1_000, 0, 0, 0], 400_000), [], WINDOW, TODAY
    )
    assert (three_of_six.level, three_of_six.caveat_ko) == ("none", None)
    assert three_of_six.lines[0].value == pytest.approx(12.5)
    assert three_of_six.lines[1].text_ko == "수수료가 적힌 거래 3건 / 6건"


def test_cost_usd_fee_and_notional_are_converted_with_the_trade_rate():
    # 5 × (fee 1 USD, 100 @ 10 USD, fx 1,300): fee 1,300 won each → 6,500; notional
    # 1,300,000 won each → 6,500,000; 6,500 / 6,500,000 × 10,000 = 10 bp
    usd = [trade(i, "AAA", "buy", day(i), 100, 10, 0, None, fee=1, fx=1300.0) for i in range(1, 6)]
    e = cost_blindness_evidence(usd, [], WINDOW, TODAY)
    assert (e.level, e.sample_n) == ("none", 5)
    assert e.lines[0].value == pytest.approx(10.0)
    assert e.lines[0].text_ko == "거래 비용 합 6,500원 = 거래 금액의 0.10%"
    assert len(e.lines) == 1
    # one USD trade without a rate is left out of both sums and counted in its own line;
    # the recorded share is over priced trades only (5/5), so the level is unchanged
    e2 = cost_blindness_evidence(
        usd + [trade(9, "BBB", "buy", day(9), 1, 1_000_000, 0, None, fee=5_000, fx=None)],
        [],
        WINDOW,
        TODAY,
    )
    assert e2.sample_n == 6 and e2.level == "none"
    assert e2.lines[0].value == pytest.approx(10.0)
    assert e2.lines[-1].text_ko == "환율이 없어 비용 계산에서 뺀 거래 1건" and e2.lines[-1].n == 1


def test_cost_suspicious_trades_leave_the_sample_and_every_sum():
    # 5 KRW buys of 400,000 won with fee 1,000 each (25 bp → some) plus one suspicious buy
    # (id 9, 40,000,000 won — a 100× price slip — fee 1,000). Taken in, it swamps the
    # denominator: 6,000 / 42,000,000 × 10,000 = 1.43 bp → none, n = 6, 6/6 recorded.
    # Marked suspicious (N-LEARN-4): n = 5, 5,000 / 2,000,000 = 25 bp → some,
    # excluded_suspicious 1 and a line pointing at trade 9.
    clean = fee_record([1_000] * 5, 400_000)
    odd = krw_trade(9, day(9), 40_000_000, 1_000)
    included = cost_blindness_evidence(clean + [odd], [], WINDOW, TODAY)
    assert (included.level, included.sample_n, included.excluded_suspicious) == ("none", 6, 0)
    assert included.lines[0].value == pytest.approx(6_000 / 42_000_000 * 1e4)
    e = cost_blindness_evidence(clean + [odd], [], WINDOW, TODAY, suspicious_ids=frozenset({9}))
    assert (e.level, e.sample_n, e.excluded_suspicious) == ("some", 5, 1)
    assert e.lines[0].value == pytest.approx(25.0) and e.lines[0].n == 5
    assert e.lines[0].text_ko == "거래 비용 합 5,000원 = 거래 금액의 0.25%"
    assert e.lines[1].text_ko == SUSPICIOUS_EXCLUDED_LINE_KO.format(n=1)
    assert (e.lines[1].trade_ids, e.lines[1].symbols, e.lines[1].n) == ((9,), ("BBB",), 1)
    assert len(e.lines) == 2  # 5/5 recorded → no "k건 / n건" line
    assert e.severity == pytest.approx(25 / 50)
    # the recorded share ignores it too: 2 of 5 usable recorded = 0.4 even though the
    # suspicious trade carries a fee → still the no-fee caveat and insufficient
    sparse = fee_record([1_000, 1_000, 0, 0, 0], 400_000)
    s = cost_blindness_evidence(sparse + [odd], [], WINDOW, TODAY, suspicious_ids=frozenset({9}))
    assert (s.level, s.caveat_ko, s.sample_n) == ("insufficient", NO_FEES_RECORDED_KO, 5)
    assert s.lines[1].text_ko == "수수료가 적힌 거래 2건 / 5건"
    # and it does not help the sample reach min_sample: 4 clean + 1 suspicious → n = 4
    few = cost_blindness_evidence(
        clean[:4] + [odd], [], WINDOW, TODAY, suspicious_ids=frozenset({9})
    )
    assert (few.level, few.sample_n, few.excluded_suspicious) == ("insufficient", 4, 1)
    assert few.caveat_ko is None


def test_cost_busy_months_and_severity():
    base = fee_record([500, 500, 1_000, 0, 0])
    one = cost_blindness_evidence(base, [MonthCount("2026-03", 4, 4, 8)], WINDOW, TODAY)
    assert one.level == "some" and one.severity == pytest.approx(0.5)  # max(9.52/50, 1/2)
    two = cost_blindness_evidence(
        base, [MonthCount("2026-03", 4, 4, 8), MonthCount("2026-07", 5, 5, 10)], WINDOW, TODAY
    )
    assert two.level == "strong" and two.severity == pytest.approx(1.0)
    assert two.lines[-1].value == 2.0 and two.lines[-1].n == 2
    # n = 4 < 5: insufficient without the no-fee caveat, even with 2 busy months
    busy2 = [MonthCount("2026-03", 4, 4, 8), MonthCount("2026-07", 5, 5, 10)]
    few = cost_blindness_evidence(fee_record([0, 0, 0, 0]), busy2, WINDOW, TODAY)
    assert (few.level, few.caveat_ko) == ("insufficient", None)


# --- 7. holding period: closed round trips over the whole record ----------------------------


def closed_trip(id0: int, symbol: str, days_held: int, sell_price: float = 110) -> list[TradeView]:
    """Buy 1 @ 100 on D0, sell it `days_held` days later."""
    return [
        trade(id0, symbol, "buy", D0, 1, 100, 0, None),
        trade(id0 + 1, symbol, "sell", day(days_held), 1, sell_price, 1, 100.0),
    ]


def test_short_holding_median_45_one_of_three_short_is_some():
    # trips of 10, 45 and 200 days: median 45; 1 of 3 closed within 30 days → 0.333 ≥ 0.25
    r = replay_trades(
        closed_trip(1, "AAA", 10) + closed_trip(3, "BBB", 45) + closed_trip(5, "CCC", 200), TODAY
    )
    e = short_holding_evidence(r, TODAY)
    assert (e.level, e.sample_n, e.min_sample) == ("some", 3, 3)
    assert (
        e.lines[0].text_ko == "닫힌 포지션 3개의 중간 보유 기간 45일" and e.lines[0].value == 45.0
    )
    assert e.lines[1].text_ko == "1개는 30일 안에 정리"
    assert e.lines[1].value == pytest.approx(1 / 3 * 100)
    assert e.lines[1].trade_ids == (1, 2) and e.lines[1].symbols == ("AAA",)
    assert len(e.lines) == 2  # nothing open → no open-position line
    assert (e.window_start, e.window_end) == (D0, TODAY)
    assert e.severity == pytest.approx(1 / 3)


def test_short_holding_two_of_three_is_strong_and_30_days_is_not_short():
    strong = short_holding_evidence(
        replay_trades(
            closed_trip(1, "AAA", 10) + closed_trip(3, "BBB", 20) + closed_trip(5, "CCC", 200),
            TODAY,
        ),
        TODAY,
    )
    assert strong.level == "strong" and strong.lines[0].value == 20.0  # median of 10, 20, 200
    assert strong.lines[1].value == pytest.approx(2 / 3 * 100)
    # a 30-day trip is not "within 30 days" (strictly less): 0 of 3 → none
    on_edge = short_holding_evidence(
        replay_trades(
            closed_trip(1, "AAA", 30) + closed_trip(3, "BBB", 45) + closed_trip(5, "CCC", 200),
            TODAY,
        ),
        TODAY,
    )
    assert on_edge.level == "none" and on_edge.lines[1].text_ko == "0개는 30일 안에 정리"
    # four trips 10, 20, 45, 200: even count → median (20 + 45) / 2 = 32.5; 2/4 = 0.5 → strong
    four = short_holding_evidence(
        replay_trades(
            closed_trip(1, "AAA", 10)
            + closed_trip(3, "BBB", 20)
            + closed_trip(5, "CCC", 45)
            + closed_trip(7, "DDD", 200),
            TODAY,
        ),
        TODAY,
    )
    assert four.level == "strong" and four.lines[0].value == 32.5
    assert four.lines[0].text_ko == "닫힌 포지션 4개의 중간 보유 기간 32.5일"


def test_short_holding_two_closed_is_insufficient_but_open_ages_are_listed():
    # two closed trips (10, 45 days) → n = 2 < 3. Two open positions: DDD bought D0+270
    # (2026-10-02 → 28 days to TODAY) and CCC bought D0+280 (2026-10-12 → 18 days);
    # oldest first, then symbol.
    trades = (
        closed_trip(1, "AAA", 10)
        + closed_trip(3, "BBB", 45)
        + [
            trade(5, "CCC", "buy", day(280), 1, 100, 0, None),
            trade(6, "DDD", "buy", day(270), 1, 100, 0, None),
        ]
    )
    r = replay_trades(trades, TODAY)
    assert r.open_since == {"CCC": day(280), "DDD": day(270)}
    e = short_holding_evidence(r, TODAY)
    assert (e.level, e.sample_n) == ("insufficient", 2)
    assert e.lines[0].value == pytest.approx(27.5)  # median of 10 and 45
    assert e.lines[-1].text_ko == "지금 들고 있는 DDD 28일째 · CCC 18일째"
    assert (
        e.lines[-1].value == 28.0 and e.lines[-1].n == 2 and e.lines[-1].symbols == ("DDD", "CCC")
    )
    # a suspicious trip is dropped from the sample and counted
    sus = short_holding_evidence(
        replay_trades(
            closed_trip(1, "AAA", 10) + closed_trip(3, "BBB", 45) + closed_trip(5, "CCC", 200),
            TODAY,
            frozenset({1}),
        ),
        TODAY,
    )
    assert (sus.level, sus.sample_n, sus.excluded_suspicious) == ("insufficient", 2, 1)
    assert sus.lines[0].value == pytest.approx((45 + 200) / 2)


# --- 8. handling losses: sell outcomes, quick rebuys, median holding gain vs loss -----------


def sell_pairs(spec: list[tuple[int, float]]) -> list[TradeView]:
    """One round trip per entry: buy 1 @ 100 on D0 under its own symbol, sell `days` later at
    `price` (110 gain, 90 loss, 100 flat). Separate symbols keep the trips independent."""
    out: list[TradeView] = []
    for i, (days, price) in enumerate(spec):
        out += [
            trade(2 * i + 1, f"S{i}", "buy", D0, 1, 100, 0, None),
            trade(2 * i + 2, f"S{i}", "sell", day(days), 1, price, 1, 100.0),
        ]
    return out


def test_loss_holding_rebuy_share_half_is_strong():
    # AAA: buy D0, sell D0+5 @ 90 (loss, 5 days); buy again D0+8 (the coach flags it as a rebuy
    # within 10 days); sell D0+30 @ 80 (loss, days_held 30 − 8 = 22). BBB: buy D0, sell D0+3
    # @ 120 (gain). Losses 2, gains 1; rebuys 1 → 1/2 = 0.5 ≥ 0.5 → strong once n ≥ min_sells.
    trades = [
        trade(1, "AAA", "buy", day(0), 1, 100, 0, None),
        trade(2, "AAA", "sell", day(5), 1, 90, 1, 100.0),
        trade(3, "AAA", "buy", day(8), 1, 90, 0, None),
        trade(4, "AAA", "sell", day(30), 1, 80, 1, 90.0),
        trade(5, "BBB", "buy", day(0), 1, 100, 0, None),
        trade(6, "BBB", "sell", day(3), 1, 120, 1, 100.0),
    ]
    r = replay_trades(trades, TODAY)
    assert [s.days_held for s in r.sells] == [3, 5, 22]  # ordered by (date, id)
    # the flag names the rebuy (AAA on D0+8); the module pairs it with the latest AAA loss
    # sold within 10 days before it: D0−2 ≤ D0+5 < D0+8 → sell id 2
    rebuys = [flag("quick_rebuy_after_loss", 3, "AAA", day(8))]
    e = loss_holding_evidence(r, rebuys, TODAY, SkillThresholds(min_sells=3))
    assert (e.level, e.sample_n, e.min_sample) == ("strong", 3, 3)
    assert e.lines[0].text_ko == "손실 매도 2건 · 이익 매도 1건"
    assert e.lines[0].value == pytest.approx(2 / 3 * 100) and e.lines[0].trade_ids == (2, 4)
    # whole-record wording (no rebuy window): the module's constant, our numbers
    assert e.lines[1].text_ko == REBUY_LINE_KO.format(n=2, k=1, days=10)
    assert (
        e.lines[1].value == pytest.approx(50.0)
        and e.lines[1].n == 2
        and e.lines[1].trade_ids == (3,)
    )
    assert len(e.lines) == 2  # fewer than 3 gains → no median line
    assert (e.window_start, e.window_end) == (D0, TODAY)
    assert e.severity == pytest.approx(0.5)
    # default min_sells 4: the same record is insufficient; without the flag: none
    assert loss_holding_evidence(r, rebuys, TODAY).level == "insufficient"
    assert loss_holding_evidence(r, [], TODAY, SkillThresholds(min_sells=3)).level == "none"
    # one rebuy out of 3 losses = 0.333: below 0.5 but ≥ 1 rebuy → some
    three_losses = trades + [
        trade(7, "CCC", "buy", day(0), 1, 100, 0, None),
        trade(8, "CCC", "sell", day(9), 1, 50, 1, 100.0),
    ]
    some = loss_holding_evidence(replay_trades(three_losses, TODAY), rebuys, TODAY)
    assert (some.level, some.sample_n) == ("some", 4)


def test_loss_holding_rebuy_window_narrows_the_denominator():
    # five loss sells over the whole record: S0..S2 sold on D0+10/20/30, S3 on D0+200, S4 on
    # D0+210 (ids 2, 4, 6, 8, 10). S3 is bought again on D0+205 (id 11) and the coach flags
    # that buy as a rebuy within 10 days. No gains, so no median line; n = 5 ≥ min_sells 4.
    #   whole record: 1 rebuy / 5 losses = 20% → some (a rebuy exists, share < 0.5)
    #   window from D0+150: losses on/after it = 2 (D0+200, D0+210) → 1/2 = 50% → strong;
    #   span = TODAY − (D0+150) = 298 − 150 = 148 days
    trades = sell_pairs([(10, 90), (20, 90), (30, 90), (200, 90), (210, 90)]) + [
        trade(11, "S3", "buy", day(205), 1, 90, 0, None)
    ]
    r = replay_trades(trades, TODAY)
    assert [s.date for s in r.sells] == [day(10), day(20), day(30), day(200), day(210)]
    rebuys = [flag("quick_rebuy_after_loss", 11, "S3", day(205))]
    whole = loss_holding_evidence(r, rebuys, TODAY)
    assert (whole.level, whole.sample_n) == ("some", 5)
    assert whole.lines[0].text_ko == "손실 매도 5건 · 이익 매도 0건"
    assert whole.lines[1].text_ko == REBUY_LINE_KO.format(n=5, k=1, days=10)
    assert (whole.lines[1].value, whole.lines[1].n) == (pytest.approx(20.0), 5)
    assert whole.severity == pytest.approx(0.2)
    windowed = loss_holding_evidence(r, rebuys, TODAY, rebuy_window_start=day(150))
    assert (windowed.level, windowed.sample_n) == ("strong", 5)  # sample is still all sells
    assert windowed.lines[0].text_ko == "손실 매도 5건 · 이익 매도 0건"  # counts: whole record
    assert windowed.lines[1].text_ko == REBUY_WINDOW_LINE_KO.format(span=148, n=2, k=1, days=10)
    assert (windowed.lines[1].value, windowed.lines[1].n) == (pytest.approx(50.0), 2)
    assert windowed.lines[1].trade_ids == (11,) and windowed.lines[1].symbols == ("S3",)
    assert windowed.severity == pytest.approx(0.5)
    assert (windowed.window_start, windowed.window_end) == (D0, TODAY)  # item window unchanged
    # the window start itself is inside (≥): starting on D0+200 keeps both late losses
    on_edge = loss_holding_evidence(r, rebuys, TODAY, rebuy_window_start=day(200))
    assert (on_edge.lines[1].n, on_edge.lines[1].value) == (2, pytest.approx(50.0))
    # one day later only D0+210 is in the denominator; the flag's own loss sell (D0+200,
    # paired as D0+195 ≤ D0+200 < D0+205) is not, so the flag is left out: 0/1, no
    # trade_ids, nothing paired → none
    past_edge = loss_holding_evidence(r, rebuys, TODAY, rebuy_window_start=day(201))
    assert (past_edge.level, past_edge.lines[1].n) == ("none", 1)
    assert past_edge.lines[1].value == pytest.approx(0.0) and past_edge.lines[1].trade_ids == ()
    assert past_edge.lines[1].text_ko == REBUY_WINDOW_LINE_KO.format(span=97, n=1, k=0, days=10)
    # None is the whole record (the default); a start after today is refused
    assert loss_holding_evidence(r, rebuys, TODAY, rebuy_window_start=None).lines[1].n == 5
    with pytest.raises(ValueError):
        loss_holding_evidence(r, rebuys, TODAY, rebuy_window_start=TODAY + timedelta(days=1))


def test_loss_holding_rebuy_pairing_boundaries():
    # four loss sells: S0 D0+10, S1 D0+20, S2 D0+149, S3 D0+200 (ids 2, 4, 6, 8); S2 is bought
    # again on D0+155 (id 21) and flagged. Pairing: D0+145 ≤ D0+149 < D0+155 → sell id 6.
    trades = sell_pairs([(10, 90), (20, 90), (149, 90), (200, 90)]) + [
        trade(21, "S2", "buy", day(155), 1, 90, 0, None)
    ]
    r = replay_trades(trades, TODAY)
    rebuy = [flag("quick_rebuy_after_loss", 21, "S2", day(155))]
    # whole record: 1 paired / 4 losses = 25% → some
    whole = loss_holding_evidence(r, rebuy, TODAY)
    assert (whole.level, whole.lines[1].value, whole.lines[1].n) == ("some", 25.0, 4)
    assert whole.lines[1].trade_ids == (21,)
    # window from D0+150: the denominator is {S3 sell D0+200}; the flag's sell D0+149 lies
    # before the window, so the flag does not count → 0/1 = 0%, no trade_ids, none
    cut = loss_holding_evidence(r, rebuy, TODAY, rebuy_window_start=day(150))
    assert (cut.level, cut.lines[1].n, cut.lines[1].trade_ids) == ("none", 1, ())
    assert cut.lines[1].value == pytest.approx(0.0)
    assert cut.lines[1].text_ko == REBUY_WINDOW_LINE_KO.format(span=148, n=1, k=0, days=10)
    # window from D0+149: the sell is inside → 1/2 = 50% → strong
    kept = loss_holding_evidence(r, rebuy, TODAY, rebuy_window_start=day(149))
    assert (kept.level, kept.lines[1].value, kept.lines[1].n) == ("strong", 50.0, 2)
    # a rebuy 11 days after the loss (D0+160: D0+150 ≤ ? < D0+160 holds no S2 sell) or on the
    # very day of the sell (sell date < flag date fails) is not paired; neither is a flag
    # on a symbol whose only sell is a gain (S9 never sold at a loss)
    late = [flag("quick_rebuy_after_loss", 22, "S2", day(160))]
    assert loss_holding_evidence(r, late, TODAY).lines[1].trade_ids == ()
    assert loss_holding_evidence(r, late, TODAY).level == "none"
    same_day = [flag("quick_rebuy_after_loss", 23, "S2", day(149))]
    assert loss_holding_evidence(r, same_day, TODAY).lines[1].value == pytest.approx(0.0)
    other = [flag("quick_rebuy_after_loss", 24, "S9", day(155))]
    assert loss_holding_evidence(r, other, TODAY).lines[1].trade_ids == ()
    # a window after every loss: denominator 0 → the rebuy line is omitted even with a flag
    empty = loss_holding_evidence(r, rebuy, TODAY, rebuy_window_start=day(250))
    assert len(empty.lines) == 1 and empty.level == "none"
    with pytest.raises(ValueError):
        loss_holding_evidence(r, rebuy, TODAY, rebuy_days=-1)


def test_loss_holding_two_flags_on_one_loss_count_once_and_pair_with_the_latest_sell():
    # S0 is sold at a loss twice: D0+100 (id 2) and D0+105 (id 4, a second trip); S1..S3 are
    # losses on D0+10/20/30 (ids 6, 8, 10) → 5 losses. S0 is bought again on D0+108 (id 31)
    # and D0+112 (id 32), both flagged.
    #   id 31 (D0+108): D0+98 ≤ sells on D0+100 and D0+105 < D0+108 → the latest, id 4
    #   id 32 (D0+112): D0+102 ≤ D0+105 < D0+112 → id 4 again
    # k counts distinct paired sells → 1; trade_ids carries both flags; 1/5 = 20% → some
    trades = [
        trade(1, "S0", "buy", day(90), 1, 100, 0, None),
        trade(2, "S0", "sell", day(100), 1, 90, 1, 100.0),
        trade(3, "S0", "buy", day(101), 1, 100, 0, None),
        trade(4, "S0", "sell", day(105), 1, 90, 1, 100.0),
        trade(5, "S1", "buy", day(0), 1, 100, 0, None),
        trade(6, "S1", "sell", day(10), 1, 90, 1, 100.0),
        trade(7, "S2", "buy", day(0), 1, 100, 0, None),
        trade(8, "S2", "sell", day(20), 1, 90, 1, 100.0),
        trade(9, "S3", "buy", day(0), 1, 100, 0, None),
        trade(10, "S3", "sell", day(30), 1, 90, 1, 100.0),
        trade(31, "S0", "buy", day(108), 1, 100, 0, None),
        trade(32, "S0", "buy", day(112), 1, 100, 1, 100.0),
    ]
    r = replay_trades(trades, TODAY)
    assert len([s for s in r.sells if s.outcome == "loss"]) == 5
    flags = [
        flag("quick_rebuy_after_loss", 31, "S0", day(108)),
        flag("quick_rebuy_after_loss", 32, "S0", day(112)),
    ]
    e = loss_holding_evidence(r, flags, TODAY)
    assert (e.level, e.lines[1].value, e.lines[1].n) == ("some", pytest.approx(20.0), 5)
    assert e.lines[1].text_ko == REBUY_LINE_KO.format(n=5, k=1, days=10)
    assert e.lines[1].trade_ids == (31, 32) and e.lines[1].symbols == ("S0",)
    assert e.severity == pytest.approx(0.2)
    # the pairing picks the LATEST sell (id 4, D0+105): a window from D0+101 keeps id 4 in
    # the denominator (ids 4 only → 1/1 = 100%, strong) although id 2 (D0+100) is outside;
    # had the pairing picked id 2, both flags would have been dropped
    latest = loss_holding_evidence(r, flags, TODAY, rebuy_window_start=day(101))
    assert (latest.level, latest.lines[1].value, latest.lines[1].n) == ("strong", 100.0, 1)
    assert latest.lines[1].trade_ids == (31, 32)
    # a window from D0+106 leaves no S0 loss in the denominator → both flags dropped, and
    # with no loss on or after it the line is omitted
    assert len(loss_holding_evidence(r, flags, TODAY, rebuy_window_start=day(106)).lines) == 1


def test_loss_holding_flat_suffix():
    e = loss_holding_evidence(
        replay_trades(sell_pairs([(10, 110), (20, 90), (30, 100)]), TODAY),
        [],
        TODAY,
        SkillThresholds(min_sells=3),
    )
    assert e.lines[0].text_ko == "손실 매도 1건 · 이익 매도 1건 · 본전 1건"
    assert e.lines[0].value == pytest.approx(1 / 3 * 100)
    assert e.level == "none"


@pytest.mark.parametrize(
    ("loss_days", "level", "ratio"),
    [
        (20, "strong", 2.0),  # 20 / 10 = 2.0 ≥ 2.0
        (19, "some", 1.9),
        (15, "some", 1.5),  # 1.5 ≥ 1.5
        (14, "none", 1.4),
    ],
)
def test_loss_holding_median_ratio_boundaries(loss_days, level, ratio):
    # three gains held 10 days each (median 10), three losses held `loss_days` (median = that)
    spec = [(10, 110)] * 3 + [(loss_days, 90)] * 3
    e = loss_holding_evidence(replay_trades(sell_pairs(spec), TODAY), [], TODAY)
    assert (e.level, e.sample_n) == (level, 6)
    assert e.lines[-1].text_ko == f"이익 매도까지 중간 보유 10일 vs 손실 매도까지 {loss_days}일"
    assert e.lines[-1].value == pytest.approx(ratio) and e.lines[-1].n == 6
    assert e.severity == pytest.approx(ratio)


def test_loss_holding_median_line_needs_three_on_each_side():
    # 3 gains of 10 days + 2 losses of 100 days: n = 5 ≥ 4 but only 2 losses → no median line,
    # and with no rebuys the level is none even though the losses were held 10× longer
    two_losses = loss_holding_evidence(
        replay_trades(sell_pairs([(10, 110)] * 3 + [(100, 90)] * 2), TODAY), [], TODAY
    )
    assert two_losses.level == "none" and len(two_losses.lines) == 2
    assert all("중간 보유" not in line.text_ko for line in two_losses.lines)
    # 2 gains + 3 losses: same, no median line
    two_gains = loss_holding_evidence(
        replay_trades(sell_pairs([(10, 110)] * 2 + [(100, 90)] * 3), TODAY), [], TODAY
    )
    assert two_gains.level == "none" and len(two_gains.lines) == 2
    # a third loss turns the line on: 100 / 10 = 10 → strong
    three = loss_holding_evidence(
        replay_trades(sell_pairs([(10, 110)] * 3 + [(100, 90)] * 3), TODAY), [], TODAY
    )
    assert three.level == "strong" and three.lines[-1].value == pytest.approx(10.0)


# --- 9. asset-class drift -------------------------------------------------------------------
#
# Policy 80/20/0 with band 5: the worst |actual − target| over stock, crypto (and cash when
# known) must be strictly greater than the band for some, than twice the band for strong.

DRIFT_POLICY = Policy(target_stock_pct=80, target_crypto_pct=20, rebalance_band_pt=5)


@pytest.mark.parametrize(
    ("stock", "crypto", "cash", "level", "worst"),
    [
        (90, 10, 0.0, "some", 10.0),  # drifts 10, 10, 0 → 10 > 5, not > 10
        (95, 5, 0.0, "strong", 15.0),  # 15 > 10
        (85, 15, 0.0, "none", 5.0),  # 5 is not > 5: the band itself is inside
        (90, 0, 10.0, "strong", 20.0),  # crypto 0 vs 20 → 20
        (80, 20, 0.0, "none", 0.0),
    ],
)
def test_class_drift_boundaries(stock, crypto, cash, level, worst):
    e = class_drift_evidence(exposure_of(stock, crypto, cash), DRIFT_POLICY, True, TODAY)
    assert (e.level, e.sample_n) == (level, 3)
    assert e.lines[0].value == pytest.approx(worst)
    assert e.severity == pytest.approx(worst / 5)
    assert (e.window_start, e.window_end) == (None, TODAY)


def test_class_drift_line_text_with_cash():
    e = class_drift_evidence(exposure_of(90, 10, 0.0), DRIFT_POLICY, True, TODAY)
    assert (
        e.lines[0].text_ko
        == "주식 90.0% (목표 80.0%) · 코인 10.0% (목표 20.0%) · 현금 0.0% (목표 0.0%)"
    )


def test_class_drift_without_policy_is_insufficient():
    e = class_drift_evidence(exposure_of(90, 10, 0.0), DRIFT_POLICY, False, TODAY)
    assert (e.level, e.sample_n, e.caveat_ko) == ("insufficient", 0, NO_POLICY_KO)
    # without holdings_count the line carries no n (N-LEARN-5: no "표본 0건" in the UI)
    assert e.lines[0].text_ko == "지금 주식 90.0% · 코인 10.0%" and e.lines[0].n is None
    none = class_drift_evidence(None, DRIFT_POLICY, True, TODAY)
    assert (none.level, none.lines, none.caveat_ko) == ("insufficient", (), NO_POLICY_KO)
    # with holdings_count the sample and the current-state line carry the count
    counted = class_drift_evidence(
        exposure_of(90, 10, 0.0), DRIFT_POLICY, False, TODAY, holdings_count=3
    )
    assert (counted.level, counted.sample_n, counted.caveat_ko) == ("insufficient", 3, NO_POLICY_KO)
    assert counted.lines[0].n == 3


def test_class_drift_holdings_count_is_the_sample_not_the_class_count():
    # 90/10/0 vs 80/20/0 → worst 10 → some either way; with holdings_count=3 the sample and
    # the line's n are the 3 holdings
    e = class_drift_evidence(exposure_of(90, 10, 0.0), DRIFT_POLICY, True, TODAY, holdings_count=3)
    assert (e.level, e.sample_n, e.lines[0].n) == ("some", 3, 3)
    # no cash record: 2 classes compared, but the sample is still the 3 holdings (81/19 vs
    # renormalised 75/25 → drift 6 > 5 → some)
    policy = Policy(
        target_stock_pct=60, target_crypto_pct=20, target_cash_pct=20, rebalance_band_pt=5
    )
    e2 = class_drift_evidence(exposure_of(81, 19, None), policy, True, TODAY, holdings_count=3)
    assert (e2.level, e2.sample_n, e2.lines[0].n) == ("some", 3, 3)
    assert e2.lines[0].value == pytest.approx(6.0)
    # the same call without the count: sample_n = 2 classes, n None on the line
    e3 = class_drift_evidence(exposure_of(81, 19, None), policy, True, TODAY)
    assert (e3.sample_n, e3.lines[0].n) == (2, None)
    # nothing held → insufficient even though 0/0/100 vs 80/20/0 drifts by 100
    e0 = class_drift_evidence(exposure_of(0, 0, 100.0), DRIFT_POLICY, True, TODAY, holdings_count=0)
    assert (e0.level, e0.sample_n, e0.lines[0].n) == ("insufficient", 0, 0)
    assert e0.lines[0].value == pytest.approx(100.0)
    with pytest.raises(ValueError):
        class_drift_evidence(exposure_of(90, 10, 0.0), DRIFT_POLICY, True, TODAY, holdings_count=-1)


def test_class_drift_without_cash_renormalises_targets_to_invested():
    # policy 60/20/20, no cash record → targets 60/80 = 75% stock, 20/80 = 25% crypto; n = 2
    policy = Policy(
        target_stock_pct=60, target_crypto_pct=20, target_cash_pct=20, rebalance_band_pt=5
    )
    on_band = class_drift_evidence(exposure_of(80, 20, None), policy, True, TODAY)
    assert (on_band.level, on_band.sample_n) == ("none", 2)
    assert on_band.lines[0].value == pytest.approx(5.0)
    assert (
        on_band.lines[0].text_ko
        == "주식 80.0% (목표 75.0%) · 코인 20.0% (목표 25.0%) · " + CASH_NOT_COMPARED_KO
    )
    over = class_drift_evidence(exposure_of(81, 19, None), policy, True, TODAY)
    assert over.level == "some" and over.lines[0].value == pytest.approx(6.0)


def test_class_drift_factor_widens_the_band():
    # drift_pt_factor 2 → band 10: a drift of 10 is no longer outside it
    e = class_drift_evidence(
        exposure_of(90, 10, 0.0), DRIFT_POLICY, True, TODAY, SkillThresholds(drift_pt_factor=2.0)
    )
    assert e.level == "none" and e.severity == pytest.approx(1.0)


# --- 10. concentration today ----------------------------------------------------------------
#
# weight_pct is of equity (cash included when given); effective n = 1 / Σ(invested share)²
# over the invested amount only. strong: top1 > cap + 10 or (≥ 3 holdings and eff n < 2);
# some: top1 > cap, eff n < 3, or crypto share > policy cap.


def test_concentration_70_20_10_is_strong_both_ways():
    # top 70 > 20 + 10; HHI = 0.49 + 0.04 + 0.01 = 0.54 → 1/0.54 = 1.8519 < 2
    hs = [holding("AAA", 70), holding("BBB", 20), holding("CCC", 10)]
    e = concentration_evidence(hs, None, Policy(), lambda _s: 20.0, TODAY)
    assert (e.level, e.sample_n, e.min_sample) == ("strong", 3, 1)
    assert e.lines[0].text_ko == "가장 큰 종목 AAA 비중 70.0% (상한 20%)"
    assert e.lines[0].value == pytest.approx(70.0) and e.lines[0].symbols == ("AAA",)
    assert e.lines[1].text_ko == "실질 종목 수 1.9개 (보유 3개)"
    assert e.lines[1].value == pytest.approx(1 / 0.54)
    assert len(e.lines) == 2  # no crypto held → no crypto line
    # severity = max(70/20, 0/30, 3/1.8519) = 3.5
    assert e.severity == pytest.approx(3.5)
    assert (e.window_start, e.window_end) == (None, TODAY)


def test_concentration_40_35_25_is_some_at_cap_30_and_strong_at_cap_20():
    # HHI = 0.16 + 0.1225 + 0.0625 = 0.345 → 2.8986 (< 3, not < 2) in both cases.
    # cap 30: top 40 > 30 but ≤ 40 → some; severity = max(40/30, 0, 3/2.8986 = 1.035) = 1.333
    hs = [holding("AAA", 40), holding("BBB", 35), holding("CCC", 25)]
    e = concentration_evidence(hs, None, Policy(), lambda _s: 30.0, TODAY)
    assert e.level == "some"
    assert e.lines[1].value == pytest.approx(1 / 0.345)
    assert e.severity == pytest.approx(40 / 30)
    # cap 20: top 40 > 20 + 10 → strong. (The briefing's "top1 > cap but ≤ cap + 10 → some"
    # example needs a cap of 30; with the 20% default the hand answer is strong, as is the
    # module's.) severity = max(40/20, 0, 1.035) = 2.0
    e20 = concentration_evidence(hs, None, Policy(), lambda _s: 20.0, TODAY)
    assert e20.level == "strong" and e20.severity == pytest.approx(2.0)
    # top1 alone over the cap (28 > 20, ≤ 30) with four holdings whose effective count is
    # 1/(0.0784 + 3 × 0.0576) = 1/0.2512 = 3.98 ≥ 3: some from the top-1 rule only
    four = concentration_evidence(
        [holding("AAA", 28), holding("BBB", 24), holding("CCC", 24), holding("DDD", 24)],
        None,
        Policy(),
        lambda _s: 20.0,
        TODAY,
    )
    assert four.level == "some" and four.lines[1].value == pytest.approx(1 / 0.2512)


def test_concentration_effective_n_alone_can_make_it_strong_or_some():
    # 70/15/15 with cap 70: top1 is at the cap, not over; HHI = 0.49 + 2 × 0.0225 = 0.535
    # → 1.8692 < 2 → strong from the effective count alone
    eff_strong = concentration_evidence(
        [holding("AAA", 70), holding("BBB", 15), holding("CCC", 15)],
        None,
        Policy(),
        lambda _s: 70.0,
        TODAY,
    )
    assert eff_strong.level == "strong" and eff_strong.lines[1].value == pytest.approx(1 / 0.535)
    # 60/20/20 with cap 60: HHI = 0.36 + 0.04 + 0.04 = 0.44 → 2.2727: < 3 → some
    eff_some = concentration_evidence(
        [holding("AAA", 60), holding("BBB", 20), holding("CCC", 20)],
        None,
        Policy(),
        lambda _s: 60.0,
        TODAY,
    )
    assert eff_some.level == "some" and eff_some.lines[1].value == pytest.approx(1 / 0.44)
    # 70/30 with cap 70: HHI = 0.49 + 0.09 = 0.58 → 1.7241, but only 2 holdings (< 3) so the
    # effective count is not judged → none; severity = 70/70 = 1
    two = concentration_evidence(
        [holding("AAA", 70), holding("BBB", 30)], None, Policy(), lambda _s: 70.0, TODAY
    )
    assert two.level == "none" and two.lines[1].value == pytest.approx(1 / 0.58)
    assert two.severity == pytest.approx(1.0)
    # four equal holdings, cap 25: top1 = cap (not over), eff n = 4 → none
    even = concentration_evidence(
        [holding(s, 25) for s in ("AAA", "BBB", "CCC", "DDD")],
        None,
        Policy(),
        lambda _s: 25.0,
        TODAY,
    )
    assert even.level == "none" and even.lines[1].value == pytest.approx(4.0)


def test_concentration_cash_enters_the_weight_but_not_the_effective_count():
    # 70/20/10 plus 100 cash: AAA weight 70/200 = 35% (> 20 + 10 → strong); HHI still 0.54
    hs = [holding("AAA", 70), holding("BBB", 20), holding("CCC", 10)]
    e = concentration_evidence(hs, 100.0, Policy(), lambda _s: 20.0, TODAY)
    assert e.level == "strong" and e.lines[0].value == pytest.approx(35.0)
    assert e.lines[1].value == pytest.approx(1 / 0.54)
    # 300 cash: AAA 70/400 = 17.5% ≤ cap, yet eff n 1.85 < 2 keeps it strong
    e2 = concentration_evidence(hs, 300.0, Policy(), lambda _s: 20.0, TODAY)
    assert e2.level == "strong" and e2.lines[0].value == pytest.approx(17.5)


def test_concentration_crypto_share_over_policy_cap_is_some():
    # AAA 60 stock, BBB 40 crypto, symbol cap 70 (nobody over), crypto cap 30: 40 > 30 → some
    hs = [holding("AAA", 60), holding("BBB", 40, "crypto")]
    e = concentration_evidence(hs, None, Policy(max_crypto_weight_pct=30.0), lambda _s: 70.0, TODAY)
    assert e.level == "some"
    assert e.lines[2].text_ko == "코인 비중 40.0% (상한 30%)" and e.lines[2].symbols == ("BBB",)
    # severity = max(60/70, 40/30, 0 (two holdings)) = 1.333
    assert e.severity == pytest.approx(40 / 30)
    # at the cap: not over → none
    at_cap = concentration_evidence(
        [holding("AAA", 70), holding("BBB", 30, "crypto")],
        None,
        Policy(max_crypto_weight_pct=30.0),
        lambda _s: 70.0,
        TODAY,
    )
    assert at_cap.level == "none"


def test_concentration_without_holdings_is_insufficient():
    e = concentration_evidence([], None, Policy(), lambda _s: 20.0, TODAY)
    assert (e.level, e.sample_n, e.lines) == ("insufficient", 0, ())


# --- bonus: rule breaking (not in the briefing list; the arithmetic is small) ---------------


def add_on_buys(n: int) -> list[TradeView]:
    """`n` add-on buys into an existing AAA position (qty_before 5, so none is a first buy)."""
    return [trade(i, "AAA", "buy", day(i), 1, 90, 5, 100.0) for i in range(1, n + 1)]


def test_rule_breaking_by_hand():
    lag = [LagFlag("AAA", 80.0, 7, D0, 75.0)]
    avg = [flag("averaging_down_below_cut", 1)]
    # 5 add-ons + 1 position checked → n 6; 1/5 = 0.20 ≥ 0.20 and a lag → strong;
    # severity = max(0.20, 1/1) = 1
    e = rule_breaking_evidence(add_on_buys(5), avg, lag, 1, True, True, D0, TODAY)
    assert (e.level, e.sample_n) == ("strong", 6)
    assert e.lines[0].text_ko == "추가 매수 5번 중 손절선 아래 물타기 1번"
    assert e.lines[0].value == pytest.approx(20.0)
    # the lag line is the module's wording (bars, not days — N-LEARN-2); the numbers are ours
    assert e.lines[1].text_ko == LAG_LINE_KO.format(
        k=1, detail=LAG_DETAIL_KO.format(sym="AAA", days=7, more="")
    )
    assert "AAA 7봉" in e.lines[1].text_ko and e.lines[1].n == 1
    assert e.lines[1].value == 7.0
    assert e.severity == pytest.approx(1.0)
    # a run that began before the range looked at carries the "since window start" suffix
    since = [LagFlag("BBB", 80.0, 30, D0, 75.0, since_window_start=True)]
    e_since = rule_breaking_evidence([], [], since, 1, True, True, D0, TODAY)
    assert e_since.lines[0].text_ko == LAG_LINE_KO.format(
        k=1, detail=LAG_DETAIL_KO.format(sym="BBB", days=30, more=LAG_SINCE_START_KO)
    )
    assert "BBB 30봉" + LAG_SINCE_START_KO in e_since.lines[0].text_ko
    # 1/10 = 0.10 < 0.20 with a lag → some; 2/5 = 0.40 without a lag → some
    assert (
        rule_breaking_evidence(add_on_buys(10), avg, lag, 1, True, True, D0, TODAY).level == "some"
    )
    assert (
        rule_breaking_evidence(
            add_on_buys(5),
            avg + [flag("averaging_down_below_cut", 2)],
            [],
            0,
            True,
            True,
            D0,
            TODAY,
        ).level
        == "some"
    )
    # clean: 5 add-ons, 0 checked → n 5 → none; 4 add-ons → insufficient
    assert rule_breaking_evidence(add_on_buys(5), [], [], 0, True, True, D0, TODAY).level == "none"
    assert (
        rule_breaking_evidence(add_on_buys(4), [], [], 0, True, True, D0, TODAY).level
        == "insufficient"
    )
    # first buys (qty_before 0) are not add-ons
    firsts = [trade(i, f"S{i}", "buy", day(i), 1, 90, 0, None) for i in range(1, 6)]
    assert rule_breaking_evidence(firsts, [], [], 0, True, True, D0, TODAY).sample_n == 0


def test_rule_breaking_without_policy_and_rules_floors_at_some_only_with_a_sample():
    # neither saved → the caveat always; the `some` floor only once n ≥ min_sample
    # (D-034 amendment c). n = 4: insufficient + caveat; n = 5: some + caveat; n = 0: same
    # as n = 4.
    short = rule_breaking_evidence(add_on_buys(4), [], [], 0, False, False, D0, TODAY)
    assert (short.level, short.sample_n, short.caveat_ko) == ("insufficient", 4, NO_RULES_KO)
    enough = rule_breaking_evidence(add_on_buys(5), [], [], 0, False, False, D0, TODAY)
    assert (enough.level, enough.sample_n, enough.caveat_ko) == ("some", 5, NO_RULES_KO)
    empty = rule_breaking_evidence([], [], [], 0, False, False, D0, TODAY)
    assert (empty.level, empty.sample_n, empty.caveat_ko) == ("insufficient", 0, NO_RULES_KO)
    # one of the two saved → no caveat and no floor; the record speaks for itself
    one = rule_breaking_evidence(add_on_buys(4), [], [], 0, True, False, D0, TODAY)
    assert (one.level, one.caveat_ko) == ("insufficient", None)
    other = rule_breaking_evidence(add_on_buys(5), [], [], 0, False, True, D0, TODAY)
    assert (other.level, other.caveat_ko) == ("none", None)


# --- 11. ordering and first topics ----------------------------------------------------------


def test_rank_skills_level_then_severity_then_code():
    ranked = rank_skills(
        [
            evidence("oversizing", "strong", 0.4),
            evidence("chasing", "strong", 0.4),  # ties with oversizing → code order
            evidence("no_journal", "some", 0.9),  # higher severity never crosses a level
            evidence("class_drift", "none", 5.0),
            evidence("concentration", "insufficient", 9.0),
            evidence("cost_blindness", "strong", 0.1),
        ]
    )
    assert [e.code for e in ranked] == [
        "chasing",
        "oversizing",
        "cost_blindness",
        "no_journal",
        "class_drift",
        "concentration",
    ]
    assert rank_skills([]) == []


CATALOG = {lesson for ids in SKILL_LESSONS.values() for lesson in ids}
DEFAULT = ("diversification-basics", "position-sizing", "stop-loss-and-rules")


def test_first_topics_single_ranked_item_is_not_padded():
    ids, source = first_topics([evidence("concentration", "strong", 1.0)], DEFAULT, CATALOG)
    assert (ids, source) == (("diversification-basics",), "ranking")
    # a lone `some` counts too; `none`/`insufficient` do not
    assert first_topics([evidence("chasing", "some")], DEFAULT, CATALOG) == (
        ("chasing-buys",),
        "ranking",
    )
    assert first_topics([evidence("chasing", "none", 9.0)], DEFAULT, CATALOG) == (
        DEFAULT,
        "default",
    )
    assert first_topics([evidence("chasing", "insufficient")], DEFAULT, CATALOG) == (
        DEFAULT,
        "default",
    )


def test_first_topics_dedupes_in_ranked_order_and_stops_at_three():
    ranked = [
        evidence("cost_blindness", "strong", 1.0),  # costs-fees-fx-tax, holding-period-turnover
        evidence("short_holding", "some", 0.5),  # holding-period-turnover again → skipped
        evidence("chasing", "some", 0.4),  # chasing-buys → third
        evidence("oversizing", "some", 0.3),  # position-sizing → fourth, cut off
    ]
    ids, source = first_topics(ranked, DEFAULT, CATALOG)
    assert (ids, source) == (
        ("costs-fees-fx-tax", "holding-period-turnover", "chasing-buys"),
        "ranking",
    )
    # a lesson missing from the catalog is skipped and the next ranked one moves up
    ids2, _ = first_topics(ranked, DEFAULT, CATALOG - {"chasing-buys"})
    assert ids2 == ("costs-fees-fx-tax", "holding-period-turnover", "position-sizing")


def test_first_topics_default_is_deduped_filtered_and_capped():
    nothing = [evidence("concentration", "none"), evidence("chasing", "insufficient")]
    assert first_topics(nothing, DEFAULT, CATALOG) == (DEFAULT, "default")
    long_default = (
        "position-sizing",
        "position-sizing",
        "not-in-catalog",
        "chasing-buys",
        "trade-journal",
        "handling-losses",
    )
    ids, source = first_topics(nothing, long_default, CATALOG)
    assert (ids, source) == (("position-sizing", "chasing-buys", "trade-journal"), "default")
    assert first_topics([], (), CATALOG) == ((), "default")
    assert first_topics([], DEFAULT, set()) == ((), "default")


def test_thresholds_in_this_file_match_the_contract_defaults():
    # the boundaries hand-checked above assume plan J's defaults
    assert (
        SkillThresholds(
            min_sample=5,
            min_sells=4,
            min_round_trips=3,
            chase_share=(0.15, 0.30),
            oversized_share=(0.10, 0.30),
            avg_down_share_strong=0.20,
            rebuy_share_strong=0.50,
            hold_ratio=(1.5, 2.0),
            fee_bps=(25.0, 50.0),
            fee_recorded_min_share=0.5,
            note_share=(0.60, 0.20),
            short_trip_days=30,
            short_trip_share=(0.25, 0.50),
            effective_n=(3.0, 2.0),
            min_holdings_for_effective_n=3,
            drift_pt_factor=1.0,
        )
        == DEFAULT_THRESHOLDS
    )
