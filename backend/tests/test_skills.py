"""Learning coach evidence (`app/strategy/skills.py`, D-034): position replay by hand,
each evidence function's boundaries, ordering, first topics, wording rules and purity.
Synthetic tickers AAA/BBB only."""

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

import app.strategy.skills as skills
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
    COST_BASIS_PROXY_KO,
    DEFAULT_THRESHOLDS,
    IMPORTED_NO_NOTE_KO,
    LEARN_DISCLAIMER_KO,
    LEVEL_LABELS_KO,
    NO_FEES_RECORDED_KO,
    NO_POLICY_KO,
    NO_RULES_KO,
    SKILL_LABELS_KO,
    SKILL_LESSONS,
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
D0 = date(2026, 1, 5)
WINDOW = TODAY - timedelta(days=365)
# D-034 wording rule (same regex as the frontend tests). "보장하지 않" is allowed.
BANNED = re.compile(
    r"추천|사세요|파세요|오를|예상 수익|수익(을|이)?\s?보장(?!하지 않)"
    r"|반드시|확실히|무조건|틀림없이"
)
GRADE = re.compile(r"실력|점수|등급|레벨")


def trade(
    id: int,
    symbol: str,
    side: str,
    day: date,
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
        date=day,
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


def flag(code: str, trade_id: int, symbol: str = "AAA", day: date = D0) -> Flag:
    return Flag(code, "x", trade_id, symbol, day, "detail", None)


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


def texts(e: SkillEvidence) -> list[str]:
    out = [line.text_ko for line in e.lines]
    if e.caveat_ko:
        out.append(e.caveat_ko)
    return out


# --- the hand-calculated AAA record (fx 1000, KRW figures) ---------------------------------------
# D0: buy 10 @ 100 fee 1 → cost 1,001,000; D0+5: buy 10 @ 80 fee 1 → cost 1,802,000. The ledger's
# `Position.apply` adds `qty × price + fee` to the cost basis, so its average is
# (1,001 + 801) / 20 = 90.1; D0+20: sell 5 @ 95 → gain (475 vs 450.5); D0+40: sell 15 @ 85 → loss
# (1,275 vs 1,351.5), flat position; D0+50: buy again → second round trip.
AAA_RECORD = [
    trade(1, "AAA", "buy", D0, 10, 100, 0, None, fee=1),
    trade(2, "AAA", "buy", D0 + timedelta(days=5), 10, 80, 10, 100.1, fee=1),
    trade(3, "AAA", "sell", D0 + timedelta(days=20), 5, 95, 20, 90.1),
    trade(4, "AAA", "sell", D0 + timedelta(days=40), 15, 85, 15, 90.1),
    trade(5, "AAA", "buy", D0 + timedelta(days=50), 3, 90, 0, None),
]


# --- TradeView extension ------------------------------------------------------------------------


def test_tradeview_defaults_keep_old_calls_working():
    t = TradeView(
        id=1,
        symbol="AAA",
        asset_class="stock",
        side="buy",
        date=D0,
        quantity=1.0,
        price=10.0,
        currency="USD",
        avg_cost_before=None,
        qty_before=0.0,
    )
    assert t.fee == 0.0
    assert t.fx_krw is None
    assert t.origin == "manual"
    assert t.note is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fee": -1},
        {"fee": float("nan")},
        {"fx": 0},
        {"fx": -5},
        {"origin": "x"},
        {"note": 123},
    ],
)
def test_tradeview_rejects_bad_new_fields(kwargs):
    with pytest.raises(ValueError):
        trade(1, "AAA", "buy", D0, 1, 10, 0, None, **kwargs)


def test_tradeview_accepts_each_origin_and_krw_fx():
    for origin in ("manual", "import", "demo"):
        assert trade(1, "AAA", "buy", D0, 1, 10, 0, None, origin=origin).origin == origin
    t = trade(2, "BBB", "buy", D0, 1, 10, 0, None, currency="KRW", fx=1.0, note=" why ")
    assert t.fx_krw == 1.0 and t.note == " why "


# --- replay_trades ------------------------------------------------------------------------------


def test_replay_hand_calculation():
    r = replay_trades(AAA_RECORD, TODAY)
    assert len(r.round_trips) == 2
    first, second = r.round_trips
    assert first.symbol == "AAA" and first.currency == "USD"
    assert first.opened == D0 and first.closed == D0 + timedelta(days=40)
    assert first.buys == 2 and first.sells == 2
    assert first.trade_ids == (1, 2, 3, 4)
    assert first.invested_krw == pytest.approx(1_802_000)
    assert first.realized_krw == pytest.approx(24_500 - 76_500)
    assert first.suspicious is False
    assert second.opened == D0 + timedelta(days=50) and second.closed is None
    assert second.trade_ids == (5,)
    assert r.open_since == {"AAA": D0 + timedelta(days=50)}

    gain, loss = r.sells
    assert gain.trade_id == 3 and gain.outcome == "gain"
    assert gain.pnl_pct == pytest.approx((475 / 450.5 - 1) * 100, abs=1e-9)
    assert gain.pnl_pct == pytest.approx(5.4384, abs=1e-4)
    assert gain.days_held == 20 and gain.excluded is False
    assert loss.trade_id == 4 and loss.outcome == "loss" and loss.days_held == 40
    assert loss.pnl_pct == pytest.approx((1275 / 1351.5 - 1) * 100, abs=1e-9)
    assert loss.pnl_pct == pytest.approx(-3 / 53 * 100, abs=1e-9)  # −5.6604


def test_replay_buy_sizing_shares():
    r = replay_trades(AAA_RECORD, TODAY)
    b1, b2, b3 = r.buys
    assert b1.symbol_share_after_pct is None and b1.invested_before_krw == 0.0
    assert b1.notional_krw == pytest.approx(1_000_000)
    # second buy: cost after 1,802,000 over (1,001,000 before + 800,000 notional)
    assert b2.invested_before_krw == pytest.approx(1_001_000)
    # fee-inclusive cost over fee-inclusive base: a single-symbol record is exactly 100%
    assert b2.symbol_share_after_pct == pytest.approx(100.0)
    assert b2.notional_krw == pytest.approx(800_000)  # the fee stays out of the notional
    # re-entry after liquidation is the first money in again
    assert b3.invested_before_krw == 0.0 and b3.symbol_share_after_pct is None


def test_replay_partial_sell_then_hold_keeps_position_open():
    trades = [
        trade(1, "AAA", "buy", D0, 10, 100, 0, None),
        trade(2, "AAA", "sell", D0 + timedelta(days=3), 4, 100, 10, 100.0),
    ]
    r = replay_trades(trades, TODAY)
    assert r.sells[0].outcome == "flat"
    assert len(r.round_trips) == 1 and r.round_trips[0].closed is None
    assert r.round_trips[0].realized_krw == pytest.approx(0.0)
    assert r.open_since == {"AAA": D0}


def test_replay_sell_fee_turns_breakeven_into_loss():
    trades = [
        trade(1, "AAA", "buy", D0, 10, 100, 0, None),
        trade(2, "AAA", "sell", D0 + timedelta(days=3), 10, 100, 10, 100.0, fee=2),
    ]
    r = replay_trades(trades, TODAY)
    assert r.sells[0].outcome == "loss"
    assert r.sells[0].pnl_pct == pytest.approx(-0.2)
    assert r.round_trips[0].realized_krw == pytest.approx(-2_000)


def test_replay_krw_trade_uses_rate_one():
    trades = [
        trade(
            1,
            "BBB",
            "buy",
            D0,
            0.5,
            100_000_000,
            0,
            None,
            currency="KRW",
            fx=None,
            asset_class="crypto",
        ),
    ]
    r = replay_trades(trades, TODAY)
    assert r.buys[0].notional_krw == pytest.approx(50_000_000)
    assert r.round_trips[0].currency == "KRW"


def test_replay_sell_with_nothing_held_fails():
    with pytest.raises(ValueError):
        replay_trades([trade(1, "AAA", "sell", D0, 1, 10, 0, None)], TODAY)


def test_replay_sell_before_any_buy_in_series_fails():
    with pytest.raises(ValueError):
        replay_trades([trade(1, "AAA", "sell", D0, 1, 10, 5, 10.0)], TODAY)


def test_replay_usd_without_fx_fails_instead_of_substituting():
    with pytest.raises(ValueError):
        replay_trades([trade(1, "AAA", "buy", D0, 1, 10, 0, None, fx=None)], TODAY)


def test_replay_rejects_duplicate_ids_and_future_dates():
    twice = [trade(1, "AAA", "buy", D0, 1, 10, 0, None), trade(1, "BBB", "buy", D0, 1, 10, 0, None)]
    with pytest.raises(ValueError):
        replay_trades(twice, TODAY)
    with pytest.raises(ValueError):
        replay_trades([trade(1, "AAA", "buy", TODAY + timedelta(days=1), 1, 10, 0, None)], TODAY)


def test_replay_marks_suspicious_trip_and_excludes_later_outcomes():
    r = replay_trades(AAA_RECORD, TODAY, suspicious_ids=frozenset({2}))
    first, second = r.round_trips
    assert first.suspicious is True and second.suspicious is False
    b1, b2, b3 = r.buys
    assert b1.excluded is False  # before the suspicious trade: clean
    assert b2.excluded is True
    assert b3.excluded is False  # the next round trip starts clean
    assert all(s.excluded for s in r.sells)
    # the replay itself is unchanged
    assert first.realized_krw == pytest.approx(-52_000)


# --- concentration -------------------------------------------------------------------------------


def test_concentration_levels():
    policy = Policy()
    cap = dict.fromkeys(("AAA", "BBB", "CCC"), 20.0)
    empty = concentration_evidence([], None, policy, cap.__getitem__, TODAY)
    assert empty.level == "insufficient" and empty.sample_n == 0 and empty.lines == ()
    assert empty.window_start is None and empty.window_end == TODAY

    one = concentration_evidence([holding("AAA", 100)], None, policy, cap.__getitem__, TODAY)
    assert one.level == "strong" and one.sample_n == 1
    assert "AAA" in one.lines[0].text_ko and one.lines[0].symbols == ("AAA",)

    over = concentration_evidence(
        [holding("AAA", 28), holding("BBB", 24), holding("CCC", 24), holding("DDD", 24)],
        None,
        policy,
        lambda _s: 20.0,
        TODAY,
    )
    assert over.level == "some"  # AAA 28 > 20 but not > 30; effective n ≈ 3.98
    assert over.lines[0].value == pytest.approx(28.0)
    assert over.lines[1].value == pytest.approx(1 / (0.28**2 + 3 * 0.24**2))

    strong = concentration_evidence(
        [holding("AAA", 45), holding("BBB", 30), holding("CCC", 25)],
        None,
        policy,
        lambda _s: 20.0,
        TODAY,
    )
    assert strong.level == "strong"  # 45 > 20 + 10
    two = concentration_evidence(
        [holding("AAA", 90), holding("BBB", 5), holding("CCC", 5)],
        None,
        policy,
        lambda _s: 95.0,
        TODAY,
    )
    assert two.level == "strong"  # effective n 1.23 < 2 with three holdings
    even = concentration_evidence(
        [holding(s, 25) for s in ("AAA", "BBB", "CCC", "DDD")], None, policy, lambda _s: 40.0, TODAY
    )
    assert even.level == "none" and even.lines[1].value == pytest.approx(4.0)


def test_concentration_crypto_over_cap_is_some():
    policy = Policy(max_crypto_weight_pct=30.0)
    hs = [holding("AAA", 60), holding("BBB", 40, "crypto")]
    e = concentration_evidence(hs, None, policy, lambda _s: 70.0, TODAY)
    assert e.level == "some"
    assert any("코인 비중" in t for t in texts(e))


# --- oversizing -----------------------------------------------------------------------------------


def test_oversizing_share_proxy_and_sample_rule():
    trades = [
        trade(1, "AAA", "buy", D0, 10, 100, 0, None, fx=1.0),
        trade(2, "BBB", "buy", D0 + timedelta(days=1), 30, 100, 0, None, fx=1.0),
    ]
    r = replay_trades(trades, TODAY)
    assert r.buys[0].symbol_share_after_pct is None
    assert r.buys[1].symbol_share_after_pct == pytest.approx(75.0)

    policy = Policy(max_position_weight_pct=20.0)
    e = oversizing_evidence(r, policy, None, D0, TODAY)
    assert e.level == "insufficient" and e.sample_n == 1 and e.min_sample == 5
    assert e.caveat_ko == COST_BASIS_PROXY_KO
    assert e.lines[0].trade_ids == (2,) and "1번 중 1번" in e.lines[0].text_ko

    strong = oversizing_evidence(r, policy, None, D0, TODAY, SkillThresholds(min_sample=1))
    assert strong.level == "strong" and strong.severity == pytest.approx(1.0)
    assert strong.lines[1].value == pytest.approx(75.0)  # largest buy 3,000 of 4,000


def test_oversizing_total_risk_breach_adds_line_and_floor():
    r = replay_trades([trade(1, "AAA", "buy", D0, 1, 100, 0, None)], TODAY)
    e = oversizing_evidence(r, Policy(max_total_risk_pct=8.0), 10.0, D0, TODAY)
    # the line is a fact about today, but a thin sample stays "기록 부족" (N-LEARN-3)
    assert e.level == "insufficient" and e.sample_n == 0
    assert any("손절선까지 손실 합 10.0% (한도 8%)" in t for t in texts(e))
    ok = oversizing_evidence(r, Policy(max_total_risk_pct=8.0), 5.0, D0, TODAY)
    assert ok.level == "insufficient" and not any("손절선까지" in t for t in texts(ok))
    # with a full sample the breach lifts "none" to "some"
    many = [trade(1, "AAA", "buy", D0, 1, 100, 0, None, fx=1.0)] + [
        trade(
            i + 2,
            "BBB",
            "buy",
            D0 + timedelta(days=i + 1),
            1,
            1,
            float(i),
            1.0 if i else None,
            fx=1.0,
        )
        for i in range(5)
    ]
    full = replay_trades(many, TODAY)
    assert oversizing_evidence(full, Policy(), None, D0, TODAY).level == "none"
    lifted = oversizing_evidence(full, Policy(max_total_risk_pct=8.0), 10.0, D0, TODAY)
    assert lifted.level == "some" and lifted.sample_n == 5


def test_oversizing_excludes_suspicious_and_respects_window():
    trades = [
        trade(1, "AAA", "buy", D0, 10, 100, 0, None, fx=1.0),
        trade(2, "BBB", "buy", D0 + timedelta(days=1), 30, 100, 0, None, fx=1.0),
        trade(3, "BBB", "buy", D0 + timedelta(days=2), 30, 100, 30, 100.0, fx=1.0),
    ]
    r = replay_trades(trades, TODAY, suspicious_ids=frozenset({2}))
    e = oversizing_evidence(r, Policy(), None, D0, TODAY, SkillThresholds(min_sample=1))
    assert e.excluded_suspicious == 2 and e.sample_n == 0
    later = oversizing_evidence(r, Policy(), None, D0 + timedelta(days=3), TODAY)
    assert later.sample_n == 0 and later.excluded_suspicious == 0


# --- chasing --------------------------------------------------------------------------------------


def test_chasing_levels_and_boundaries():
    flags = [flag("chasing_buy", 1), flag("chasing_buy", 2, "BBB")]
    strong = chasing_evidence(flags, 5, WINDOW, TODAY)
    assert strong.level == "strong" and strong.sample_n == 5
    assert strong.lines[0].trade_ids == (1, 2) and strong.lines[0].symbols == ("AAA", "BBB")
    assert "5번 매수 중 2번" in strong.lines[0].text_ko
    assert chasing_evidence(flags[:1], 10, WINDOW, TODAY).level == "none"
    assert chasing_evidence(flags[:1], 6, WINDOW, TODAY).level == "some"  # 1/6 ≥ 0.15
    short = chasing_evidence(flags, 3, WINDOW, TODAY)
    assert short.level == "insufficient" and short.window_start == WINDOW
    with pytest.raises(ValueError):
        chasing_evidence(flags, 1, WINDOW, TODAY)
    with pytest.raises(ValueError):
        chasing_evidence(flags, 5, TODAY + timedelta(days=1), TODAY)


# --- rule breaking -------------------------------------------------------------------------------


def _adds(n: int) -> list[TradeView]:
    """`n` add-on buys into an existing AAA position."""
    return [
        trade(i, "AAA", "buy", D0 + timedelta(days=i), 1, 90, 5, 100.0) for i in range(1, n + 1)
    ]


def test_rule_breaking_levels():
    lag = [LagFlag("AAA", 80.0, 7, D0, 75.0)]
    avg = [flag("averaging_down_below_cut", 1)]
    strong = rule_breaking_evidence(_adds(5), avg, lag, 1, True, True, D0, TODAY)
    assert strong.level == "strong" and strong.sample_n == 6
    assert strong.lines[0].trade_ids == (1,) and strong.lines[1].symbols == ("AAA",)
    assert "AAA 7봉" in strong.lines[1].text_ko and "이상" not in strong.lines[1].text_ko

    some = rule_breaking_evidence(_adds(5), [], lag, 1, True, True, D0, TODAY)
    assert some.level == "some"
    weak = rule_breaking_evidence(_adds(10), avg, [], 2, True, True, D0, TODAY)
    assert weak.level == "some"  # 1/10 below 0.20 and no lag
    clean = rule_breaking_evidence(_adds(5), [], [], 2, True, True, D0, TODAY)
    assert clean.level == "none" and clean.caveat_ko is None
    few = rule_breaking_evidence(_adds(2), [], [], 1, True, True, D0, TODAY)
    assert few.level == "insufficient"


def test_rule_breaking_without_rules_or_policy_is_at_least_some():
    e = rule_breaking_evidence(_adds(5), [], [], 2, False, False, D0, TODAY)
    assert e.level == "some" and e.caveat_ko == NO_RULES_KO
    # an empty or thin record stays "기록 부족" (the caveat still says why),
    # never "조금 보임 · 표본 0건"
    empty = rule_breaking_evidence([], [], [], 0, False, False, D0, TODAY)
    assert empty.level == "insufficient" and empty.sample_n == 0 and empty.caveat_ko == NO_RULES_KO
    thin = rule_breaking_evidence(_adds(2), [], [], 1, False, False, D0, TODAY)
    assert thin.level == "insufficient" and thin.caveat_ko == NO_RULES_KO
    one_set = rule_breaking_evidence(_adds(5), [], [], 2, True, False, D0, TODAY)
    assert one_set.level == "none" and one_set.caveat_ko is None
    lag_since_start = [LagFlag("BBB", 80.0, 30, D0, 75.0, since_window_start=True)]
    e2 = rule_breaking_evidence([], [], lag_since_start, 1, True, True, D0, TODAY)
    # the lag check counted from the start of its range: a floor, worded as the coach does
    assert "BBB 30봉 이상(조회 범위 처음부터)" in e2.lines[0].text_ko
    assert "일" not in e2.lines[0].text_ko  # the unit is 봉, never 일


# --- no_journal -----------------------------------------------------------------------------------


def _noted(n_noted: int, n_total: int, origin: str = "manual") -> list[TradeView]:
    out = []
    for i in range(1, n_total + 1):
        note = "이유" if i <= n_noted else None
        out.append(
            trade(i, "AAA", "buy", D0 + timedelta(days=i), 1, 10, 0, None, origin=origin, note=note)
        )
    return out


def test_no_journal_boundaries_are_strict_below():
    e = no_journal_evidence(_noted(1, 5), WINDOW, TODAY)
    assert e.level == "some" and e.lines[0].value == pytest.approx(20.0)  # 0.20 is not < 0.20
    assert e.lines[0].trade_ids == (2, 3, 4, 5)
    assert no_journal_evidence(_noted(0, 5), WINDOW, TODAY).level == "strong"
    assert no_journal_evidence(_noted(3, 5), WINDOW, TODAY).level == "none"  # 0.60 not < 0.60
    assert no_journal_evidence(_noted(2, 5), WINDOW, TODAY).level == "some"
    assert no_journal_evidence(_noted(4, 4), WINDOW, TODAY).level == "insufficient"


def test_no_journal_import_line_and_blank_notes():
    trades = _noted(2, 3) + [
        trade(10, "BBB", "buy", D0, 1, 10, 0, None, origin="import", note="auto"),
        trade(11, "BBB", "buy", D0, 1, 10, 1, 10.0, note="   "),
    ]
    e = no_journal_evidence(trades, WINDOW, TODAY)
    assert e.sample_n == 5 and e.lines[0].value == pytest.approx(40.0)
    assert e.lines[1].text_ko == IMPORTED_NO_NOTE_KO.format(n=1)
    assert e.lines[1].trade_ids == (10,)
    out_of_window = no_journal_evidence(trades, D0 + timedelta(days=2), TODAY)
    assert out_of_window.sample_n == 2


# --- cost_blindness ------------------------------------------------------------------------------


def _krw_trades(fees: list[float], notional: float = 420_000) -> list[TradeView]:
    return [
        trade(
            i,
            "BBB",
            "buy",
            D0 + timedelta(days=i),
            1,
            notional,
            0,
            None,
            fee=f,
            currency="KRW",
            fx=None,
            asset_class="crypto",
        )
        for i, f in enumerate(fees, start=1)
    ]


def test_cost_blindness_without_fees_is_insufficient():
    e = cost_blindness_evidence(_krw_trades([0, 0, 0, 0, 0]), [], WINDOW, TODAY)
    assert e.level == "insufficient" and e.caveat_ko == NO_FEES_RECORDED_KO
    assert e.sample_n == 5
    loose = SkillThresholds(fee_recorded_min_share=0.0)
    e2 = cost_blindness_evidence(_krw_trades([0, 0, 0, 0, 0]), [], WINDOW, TODAY, loose)
    assert e2.level == "none" and e2.caveat_ko is None
    # without fees the busy months still decide the level (imports carry no fee)
    busy1 = [MonthCount("2026-03", 4, 4, 8)]
    busy2 = busy1 + [MonthCount("2026-07", 5, 5, 10)]
    one = cost_blindness_evidence(_krw_trades([0, 0, 0, 0, 0]), busy1, WINDOW, TODAY)
    assert one.level == "some" and one.caveat_ko == NO_FEES_RECORDED_KO
    two = cost_blindness_evidence(_krw_trades([0, 0, 0, 0, 0]), busy2, WINDOW, TODAY)
    assert two.level == "strong" and two.caveat_ko == NO_FEES_RECORDED_KO
    assert two.severity == pytest.approx(1.0)  # busy term only, no bps term
    few = cost_blindness_evidence(_krw_trades([0, 0, 0]), busy2, WINDOW, TODAY)
    assert few.level == "insufficient" and few.caveat_ko is None  # below min_sample first


def test_cost_blindness_hand_calculation_and_busy_months():
    trades = _krw_trades([500, 500, 1000, 0, 0])
    e = cost_blindness_evidence(trades, [], WINDOW, TODAY)
    assert e.level == "none"
    assert e.lines[0].value == pytest.approx(2_000 / 2_100_000 * 1e4)  # 9.52 bp
    assert e.lines[0].text_ko == "거래 비용 합 2,000원 = 거래 금액의 0.10%"
    assert e.lines[1].text_ko == "수수료가 적힌 거래 3건 / 5건"
    busy1 = [MonthCount("2026-03", 4, 4, 8)]
    busy2 = busy1 + [MonthCount("2026-07", 5, 5, 10)]
    assert cost_blindness_evidence(trades, busy1, WINDOW, TODAY).level == "some"
    strong = cost_blindness_evidence(trades, busy2, WINDOW, TODAY)
    assert strong.level == "strong"
    assert "2026-03, 2026-07" in strong.lines[-1].text_ko
    heavy = cost_blindness_evidence(_krw_trades([3000] * 5), [], WINDOW, TODAY)
    assert heavy.level == "strong"  # 15,000 / 2,100,000 = 71 bp ≥ 50
    mid = cost_blindness_evidence(_krw_trades([1200] * 5), [], WINDOW, TODAY)
    assert mid.level == "some"  # 28.6 bp
    few = cost_blindness_evidence(_krw_trades([3000] * 4), [], WINDOW, TODAY)
    assert few.level == "insufficient" and few.caveat_ko is None


def test_cost_blindness_skips_trades_without_fx_and_says_so():
    trades = _krw_trades([500, 500, 1000, 0, 0]) + [
        trade(9, "AAA", "buy", D0, 1, 100, 0, None, fee=1, fx=None)
    ]
    e = cost_blindness_evidence(trades, [], WINDOW, TODAY)
    assert e.sample_n == 6
    assert e.lines[0].value == pytest.approx(2_000 / 2_100_000 * 1e4)
    assert any("환율이 없어" in t and "1건" in t for t in texts(e))


def test_cost_blindness_leaves_suspicious_trades_out_of_the_denominator():
    # one imported trade whose price is off by orders of magnitude (N-LEARN-4)
    bad = trade(
        9,
        "BBB",
        "buy",
        D0 + timedelta(days=9),
        1,
        420_000_000_000,
        0,
        None,
        currency="KRW",
        fx=None,
        asset_class="crypto",
        origin="import",
    )
    trades = _krw_trades([500, 500, 1000, 0, 0]) + [bad]
    swamped = cost_blindness_evidence(trades, [], WINDOW, TODAY)
    assert swamped.sample_n == 6 and swamped.excluded_suspicious == 0
    assert swamped.lines[0].value < 1e-4  # 2,000 / 4.2e11 → nothing left to read
    clean = cost_blindness_evidence(trades, [], WINDOW, TODAY, suspicious_ids=frozenset({9}))
    assert clean.sample_n == 5 and clean.excluded_suspicious == 1
    assert clean.lines[0].value == pytest.approx(2_000 / 2_100_000 * 1e4)  # 9.52 bp again
    assert clean.lines[1].text_ko == "수수료가 적힌 거래 3건 / 5건"  # recorded share without it
    note = [line for line in clean.lines if line.trade_ids == (9,)]
    assert (
        len(note) == 1 and note[0].text_ko == "단가 확인이 필요한 거래 1건은 비용 계산에서 뺐어요"
    )
    assert note[0].symbols == ("BBB",) and note[0].n == 1
    # an id outside the window changes nothing
    same = cost_blindness_evidence(trades, [], WINDOW, TODAY, suspicious_ids=frozenset({999}))
    assert same.lines[0].value == swamped.lines[0].value and same.excluded_suspicious == 0


# --- short_holding -------------------------------------------------------------------------------


def _closed_trips() -> list[TradeView]:
    d = D0
    return [
        trade(1, "AAA", "buy", d, 1, 100, 0, None),
        trade(2, "AAA", "sell", d + timedelta(days=10), 1, 110, 1, 100.0),
        trade(3, "BBB", "buy", d, 1, 100, 0, None),
        trade(4, "BBB", "sell", d + timedelta(days=45), 1, 90, 1, 100.0),
        trade(5, "AAA", "buy", d + timedelta(days=100), 1, 100, 0, None),
        trade(6, "AAA", "sell", d + timedelta(days=250), 1, 120, 1, 100.0),
    ]


def test_short_holding_median_and_share():
    r = replay_trades(_closed_trips(), TODAY)
    e = short_holding_evidence(r, TODAY)
    assert e.level == "some" and e.sample_n == 3
    assert e.lines[0].value == pytest.approx(45.0)
    assert e.lines[0].text_ko == "닫힌 포지션 3개의 중간 보유 기간 45일"
    assert e.lines[1].text_ko == "1개는 30일 안에 정리" and e.lines[1].trade_ids == (1, 2)
    assert e.window_start == D0 and e.window_end == TODAY
    strong = short_holding_evidence(r, TODAY, SkillThresholds(short_trip_days=50))
    assert strong.level == "strong"


def test_short_holding_shows_open_positions_even_when_insufficient():
    trades = _closed_trips()[:4] + [
        trade(7, "BBB", "buy", D0 + timedelta(days=280), 1, 100, 0, None)
    ]
    r = replay_trades(trades, TODAY)
    e = short_holding_evidence(r, TODAY)
    assert e.level == "insufficient" and e.sample_n == 2
    age = (TODAY - (D0 + timedelta(days=280))).days
    assert e.lines[-1].text_ko == f"지금 들고 있는 BBB {age}일째"
    assert e.lines[-1].symbols == ("BBB",)
    sus = short_holding_evidence(replay_trades(_closed_trips(), TODAY, frozenset({3})), TODAY)
    assert sus.sample_n == 2 and sus.excluded_suspicious == 1


# --- loss_holding -------------------------------------------------------------------------------


def test_loss_holding_rebuy_share():
    trades = [
        trade(1, "AAA", "buy", D0, 1, 100, 0, None),
        trade(2, "AAA", "sell", D0 + timedelta(days=5), 1, 90, 1, 100.0),
        trade(3, "AAA", "buy", D0 + timedelta(days=8), 1, 90, 0, None),
        trade(4, "AAA", "sell", D0 + timedelta(days=30), 1, 80, 1, 90.0),
        trade(5, "BBB", "buy", D0, 1, 100, 0, None),
        trade(6, "BBB", "sell", D0 + timedelta(days=3), 1, 120, 1, 100.0),
    ]
    r = replay_trades(trades, TODAY)
    rebuys = [flag("quick_rebuy_after_loss", 3, "AAA", D0 + timedelta(days=8))]
    e = loss_holding_evidence(r, rebuys, TODAY, SkillThresholds(min_sells=3))
    assert e.level == "strong" and e.sample_n == 3
    assert e.lines[0].text_ko == "손실 매도 2건 · 이익 매도 1건"
    assert e.lines[0].trade_ids == (2, 4)
    assert e.lines[1].text_ko == "손실 매도 2건 중 1건은 10일 안에 다시 샀어요"
    assert e.lines[1].value == pytest.approx(50.0) and e.lines[1].trade_ids == (3,)
    assert e.lines[1].n == 2
    assert e.window_start == D0
    assert loss_holding_evidence(r, rebuys, TODAY).level == "insufficient"  # min_sells 4
    assert loss_holding_evidence(r, [], TODAY, SkillThresholds(min_sells=3)).level == "none"


def test_loss_holding_rebuy_share_uses_the_flag_window_as_denominator():
    # three loss sells long before the pattern window, then the AAA record of the test above
    old_start = date(2025, 1, 1)
    trades: list[TradeView] = []
    for i in range(3):
        bought = old_start + timedelta(days=30 * i)
        trades.append(trade(2 * i + 1, "BBB", "buy", bought, 1, 100, 0, None))
        trades.append(trade(2 * i + 2, "BBB", "sell", bought + timedelta(days=10), 1, 90, 1, 100.0))
    trades += [
        trade(7, "AAA", "buy", D0, 1, 100, 0, None),
        trade(8, "AAA", "sell", D0 + timedelta(days=5), 1, 90, 1, 100.0),
        trade(9, "AAA", "buy", D0 + timedelta(days=8), 1, 90, 0, None),
        trade(10, "AAA", "sell", D0 + timedelta(days=30), 1, 80, 1, 90.0),
    ]
    r = replay_trades(trades, TODAY)
    # flagged over the one-year window; the flag carries the rebuy's date, not the sell's
    rebuys = [flag("quick_rebuy_after_loss", 9, "AAA", D0 + timedelta(days=8))]
    whole = loss_holding_evidence(r, rebuys, TODAY)
    assert whole.sample_n == 5 and whole.lines[0].text_ko == "손실 매도 5건 · 이익 매도 0건"
    assert whole.lines[1].value == pytest.approx(20.0) and whole.level == "some"  # 1 of 5 dilutes
    windowed = loss_holding_evidence(r, rebuys, TODAY, rebuy_window_start=WINDOW)
    span = (TODAY - WINDOW).days
    assert (
        windowed.lines[1].text_ko == f"최근 {span}일 손실 매도 2건 중 1건은 10일 안에 다시 샀어요"
    )
    assert windowed.lines[1].value == pytest.approx(50.0) and windowed.lines[1].n == 2
    assert windowed.level == "strong"  # 1 of 2 within the window
    # the whole-record parts are untouched by the window
    assert windowed.lines[0].text_ko == whole.lines[0].text_ko
    assert windowed.sample_n == 5 and windowed.window_start == old_start
    with pytest.raises(ValueError):
        loss_holding_evidence(r, rebuys, TODAY, rebuy_window_start=TODAY + timedelta(days=1))


def test_loss_holding_pairs_each_flag_with_a_loss_sell_inside_the_window():
    """A flag names the rebuy, the denominator names loss sells: a loss sold just before
    the window and bought back just after it must not count in one and not the other."""
    d = timedelta
    trades = [
        trade(1, "AAA", "buy", D0, 1, 100, 0, None),
        trade(2, "AAA", "sell", D0 + d(days=149), 1, 90, 1, 100.0),  # loss, before the window
        trade(3, "AAA", "buy", D0 + d(days=155), 1, 90, 0, None),  # its rebuy, inside
        trade(4, "AAA", "sell", D0 + d(days=200), 1, 80, 1, 90.0),  # loss, inside
        trade(5, "BBB", "buy", D0, 1, 100, 0, None),
        trade(6, "BBB", "sell", D0 + d(days=151), 1, 90, 1, 100.0),  # loss, inside
        trade(7, "BBB", "buy", D0 + d(days=155), 1, 90, 0, None),  # its rebuy, inside
    ]
    r = replay_trades(trades, TODAY)
    flags = [
        flag("quick_rebuy_after_loss", 3, "AAA", D0 + d(days=155)),
        flag("quick_rebuy_after_loss", 7, "BBB", D0 + d(days=155)),
    ]
    th = SkillThresholds(min_sells=3)
    whole = loss_holding_evidence(r, flags, TODAY, th)
    assert whole.lines[1].value == pytest.approx(200 / 3)  # both pair: 2 of 3 loss sells
    assert whole.lines[1].trade_ids == (3, 7) and whole.lines[1].n == 3
    windowed = loss_holding_evidence(r, flags, TODAY, th, rebuy_window_start=D0 + d(days=150))
    # denominator: AAA@200, BBB@151; the AAA flag pairs with the sell at 149, outside → dropped
    assert windowed.lines[1].value == pytest.approx(50.0) and windowed.lines[1].n == 2
    assert windowed.lines[1].trade_ids == (7,) and windowed.lines[1].symbols == ("BBB",)
    assert windowed.level == "strong"
    # window after the last loss sell: nothing to compare, so the line is left out, not 0%
    later = loss_holding_evidence(r, flags, TODAY, th, rebuy_window_start=D0 + d(days=201))
    assert len(later.lines) == 1 and later.level == "none"
    # a rebuy more than rebuy_days after the loss sell pairs with nothing: 0 of 3
    stale = [flag("quick_rebuy_after_loss", 3, "AAA", D0 + d(days=160))]
    unpaired = loss_holding_evidence(r, stale, TODAY, th)
    assert unpaired.lines[1].value == 0.0 and unpaired.lines[1].trade_ids == ()
    assert unpaired.level == "none"
    # the share can never exceed 100%: two flags on one loss sell count that sell once
    twice = [
        flag("quick_rebuy_after_loss", 7, "BBB", D0 + d(days=155)),
        flag("quick_rebuy_after_loss", 70, "BBB", D0 + d(days=156)),
    ]
    once = loss_holding_evidence(r, twice, TODAY, th, rebuy_window_start=D0 + d(days=151))
    assert once.lines[1].value == pytest.approx(50.0) and once.lines[1].trade_ids == (7, 70)
    # numerator 0 and denominator 0 (loss at 149, rebuy at 155, window at 150): no line
    lone = replay_trades(trades[:3], TODAY)
    one_flag = flags[:1]
    empty = loss_holding_evidence(
        lone, one_flag, TODAY, SkillThresholds(min_sells=1), rebuy_window_start=D0 + d(days=150)
    )
    assert len(empty.lines) == 1 and empty.level == "none"
    full = loss_holding_evidence(lone, one_flag, TODAY, SkillThresholds(min_sells=1))
    assert full.lines[1].value == pytest.approx(100.0) and full.level == "strong"
    with pytest.raises(ValueError):
        loss_holding_evidence(lone, one_flag, TODAY, rebuy_days=-1)


def test_loss_holding_median_hold_ratio():
    trades: list[TradeView] = []
    tid = 1
    day = D0
    for days, price in ((5, 110), (5, 110), (5, 110), (20, 90), (20, 90), (20, 90)):
        sold = day + timedelta(days=days)
        trades.append(trade(tid, "AAA", "buy", day, 1, 100, 0, None))
        trades.append(trade(tid + 1, "AAA", "sell", sold, 1, price, 1, 100.0))
        tid += 2
        day += timedelta(days=30)
    r = replay_trades(trades, TODAY)
    e = loss_holding_evidence(r, [], TODAY)
    assert e.level == "strong" and e.sample_n == 6
    assert e.lines[-1].text_ko == "이익 매도까지 중간 보유 5일 vs 손실 매도까지 20일"
    assert e.lines[-1].value == pytest.approx(4.0)
    mild = loss_holding_evidence(r, [], TODAY, SkillThresholds(hold_ratio=(4.5, 5.0)))
    assert mild.level == "none"
    some = loss_holding_evidence(r, [], TODAY, SkillThresholds(hold_ratio=(3.0, 5.0)))
    assert some.level == "some"


# --- class_drift ----------------------------------------------------------------------------------


def _exposure(stock: float, crypto: float, cash: float | None) -> Exposure:
    return Exposure(100.0, 100.0, stock, crypto, cash, stock)


def test_class_drift_levels():
    policy = Policy(target_stock_pct=80, target_crypto_pct=20, rebalance_band_pt=5)
    none = class_drift_evidence(_exposure(90, 10, 0.0), policy, False, TODAY)
    assert none.level == "insufficient" and none.caveat_ko == NO_POLICY_KO
    assert class_drift_evidence(None, policy, True, TODAY).level == "insufficient"
    # today's-state lines carry the holdings count as n, never 0 (N-LEARN-5)
    assert none.lines[0].n is None and none.sample_n == 0
    counted = class_drift_evidence(_exposure(90, 10, 0.0), policy, False, TODAY, holdings_count=3)
    assert counted.lines[0].n == 3 and counted.sample_n == 3 and counted.level == "insufficient"
    some = class_drift_evidence(_exposure(90, 10, 0.0), policy, True, TODAY)
    assert some.level == "some" and some.lines[0].value == pytest.approx(10.0)
    assert some.lines[0].n is None and some.sample_n == 3  # classes compared, no count given
    with_count = class_drift_evidence(_exposure(90, 10, 0.0), policy, True, TODAY, holdings_count=4)
    assert with_count.level == "some" and with_count.lines[0].n == 4 and with_count.sample_n == 4
    nothing = class_drift_evidence(_exposure(0, 0, 100.0), policy, True, TODAY, holdings_count=0)
    assert nothing.level == "insufficient"  # nothing held is not a drift
    with pytest.raises(ValueError):
        class_drift_evidence(_exposure(90, 10, 0.0), policy, True, TODAY, holdings_count=-1)
    assert some.lines[0].text_ko.startswith("주식 90.0% (목표 80.0%) · 코인 10.0% (목표 20.0%)")
    assert "현금 0.0% (목표 0.0%)" in some.lines[0].text_ko
    assert class_drift_evidence(_exposure(95, 5, 0.0), policy, True, TODAY).level == "strong"
    assert class_drift_evidence(_exposure(83, 17, 0.0), policy, True, TODAY).level == "none"
    on_band = class_drift_evidence(_exposure(85, 15, 0.0), policy, True, TODAY)
    assert on_band.level == "none"  # a drift equal to the band is inside it


def test_class_drift_without_cash_renormalises_targets():
    policy = Policy(target_stock_pct=60, target_crypto_pct=20, target_cash_pct=20)
    e = class_drift_evidence(_exposure(75, 25, None), policy, True, TODAY)
    assert e.level == "none" and e.sample_n == 2
    assert CASH_NOT_COMPARED_KO in e.lines[0].text_ko
    assert "(목표 75.0%)" in e.lines[0].text_ko


# --- ordering and first topics --------------------------------------------------------------------


def _ev(code: str, level: str, severity: float = 0.0) -> SkillEvidence:
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


def test_rank_skills_order():
    ranked = rank_skills(
        [
            _ev("no_journal", "insufficient"),
            _ev("chasing", "some", 0.2),
            _ev("oversizing", "strong", 0.4),
            _ev("concentration", "none"),
            _ev("cost_blindness", "strong", 0.9),
            _ev("short_holding", "some", 0.2),
        ]
    )
    assert [e.code for e in ranked] == [
        "cost_blindness",
        "oversizing",
        "chasing",
        "short_holding",
        "concentration",
        "no_journal",
    ]


def test_first_topics_ranking_and_default():
    catalog = {v for ids in SKILL_LESSONS.values() for v in ids}
    default = ("diversification-basics", "position-sizing", "stop-loss-and-rules")
    ranked = rank_skills(
        [
            _ev("cost_blindness", "strong", 0.9),
            _ev("chasing", "some"),
            _ev("short_holding", "some"),  # repeats holding-period-turnover
            _ev("concentration", "none"),
        ]
    )
    ids, source = first_topics(ranked, default, catalog)
    assert source == "ranking"
    assert ids == ("costs-fees-fx-tax", "holding-period-turnover", "chasing-buys")
    ids2, source2 = first_topics([_ev("concentration", "none")], default, catalog)
    assert (ids2, source2) == (default, "default")
    # a lesson missing from the catalog is skipped
    ids3, _ = first_topics(ranked, default, catalog - {"costs-fees-fx-tax"})
    assert ids3[0] == "holding-period-turnover"
    ids4, source4 = first_topics([], ("a", "b"), catalog)
    assert (ids4, source4) == ((), "default")


# --- wording rules -------------------------------------------------------------------------------


def _all_generated() -> list[str]:
    """Every line and caveat the functions above can produce, over a varied record."""
    policy = Policy()
    out: list[str] = []
    bbb = [
        trade(21, "BBB", "buy", D0, 1, 100, 0, None),
        trade(22, "BBB", "sell", D0 + timedelta(days=45), 1, 90, 1, 100.0),
    ]
    r = replay_trades(AAA_RECORD + bbb, TODAY, frozenset({2}))
    evs = [
        concentration_evidence(
            [holding("AAA", 60), holding("BBB", 40, "crypto")], 10.0, policy, lambda _s: 20.0, TODAY
        ),
        concentration_evidence([], None, policy, lambda _s: 20.0, TODAY),
        oversizing_evidence(r, policy, 12.0, D0, TODAY, SkillThresholds(min_sample=1)),
        rule_breaking_evidence(
            _adds(5),
            [flag("averaging_down_below_cut", 1)],
            [LagFlag("AAA", 80.0, 7, D0, 75.0, since_window_start=True)],
            1,
            False,
            False,
            D0,
            TODAY,
        ),
        chasing_evidence([flag("chasing_buy", 1)], 5, WINDOW, TODAY),
        loss_holding_evidence(r, [flag("quick_rebuy_after_loss", 5)], TODAY),
        loss_holding_evidence(
            r, [flag("quick_rebuy_after_loss", 5)], TODAY, rebuy_window_start=WINDOW
        ),
        cost_blindness_evidence(
            _krw_trades([500, 0, 0, 0, 0]) + [trade(9, "AAA", "buy", D0, 1, 1, 0, None, fx=None)],
            [MonthCount("2026-03", 4, 4, 8)],
            WINDOW,
            TODAY,
        ),
        cost_blindness_evidence(_krw_trades([500, 500, 1000, 0, 0]), [], WINDOW, TODAY),
        no_journal_evidence(_noted(1, 5) + _noted(0, 2, "import"), WINDOW, TODAY),
        cost_blindness_evidence(
            _krw_trades([500, 500, 1000, 0, 0]), [], WINDOW, TODAY, suspicious_ids=frozenset({1})
        ),
        short_holding_evidence(r, TODAY),
        class_drift_evidence(_exposure(90, 10, 0.0), policy, True, TODAY),
        class_drift_evidence(_exposure(90, 10, None), policy, False, TODAY),
        class_drift_evidence(_exposure(90, 10, None), policy, False, TODAY, holdings_count=2),
    ]
    for e in evs:
        out.extend(texts(e))
        out.append(e.label_ko)
        out.append(e.level_ko)
    return out


def test_no_banned_or_grading_words_in_constants_and_generated_text():
    constants = [
        getattr(skills, name)
        for name in dir(skills)
        if name.endswith("_KO") and isinstance(getattr(skills, name), str)
    ]
    assert len(constants) >= 25
    strings = constants + list(LEVEL_LABELS_KO.values()) + list(SKILL_LABELS_KO.values())
    strings += _all_generated()
    assert any(s for s in strings)
    for s in strings:
        assert not BANNED.search(s), s
        assert not GRADE.search(s), s
    # the disclaimer's "보장하지 않습니다" is the one allowed use of the word
    assert "보장하지 않습니다" in LEARN_DISCLAIMER_KO
    assert BANNED.search("수익을 보장합니다") is not None
    assert BANNED.search("수익 보장") is not None


def test_every_evidence_carries_sample_and_window():
    r = replay_trades(AAA_RECORD, TODAY)
    for e in (
        oversizing_evidence(r, Policy(), None, D0, TODAY),
        loss_holding_evidence(r, [], TODAY),
        short_holding_evidence(r, TODAY),
        chasing_evidence([], 0, WINDOW, TODAY),
    ):
        assert isinstance(e.sample_n, int) and e.min_sample >= 1
        assert e.window_end == TODAY
        assert e.level_ko == LEVEL_LABELS_KO[e.level]
        assert e.lesson_ids == SKILL_LESSONS[e.code]
        for line in e.lines:
            assert line.text_ko.strip()
    assert skills.sample_ko(3) == "표본 3건"
    with pytest.raises(ValueError):
        skills.sample_ko(-1)


def test_labels_cover_the_nine_habits_in_order_and_lessons_exist():
    assert list(SKILL_LABELS_KO) == [
        "concentration",
        "oversizing",
        "rule_breaking",
        "chasing",
        "loss_holding",
        "cost_blindness",
        "no_journal",
        "short_holding",
        "class_drift",
    ]
    assert set(SKILL_LESSONS) == set(SKILL_LABELS_KO)
    assert all(ids for ids in SKILL_LESSONS.values())
    assert SkillThresholds() == DEFAULT_THRESHOLDS
    assert set(LEVEL_LABELS_KO) == {"strong", "some", "none", "insufficient"}


def test_module_is_pure():
    source = Path(skills.__file__).read_text(encoding="utf-8")
    forbidden_tokens = (
        "import pandas",
        "pandas as",
        "sqlalchemy",
        "httpx",
        "fastapi",
        "app.db",
        "app.services",
        "numpy",
        "execute(",
        "Broker",
        "KillSwitch",
        "AM_LIVE_TRADING",
    )
    for forbidden in forbidden_tokens:
        assert forbidden not in source, forbidden
    imports = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
    assert all(
        line.startswith(
            (
                "import statistics",
                "from collections",
                "from dataclasses",
                "from datetime",
                "from typing",
                "from app.strategy.coach",
            )
        )
        for line in imports
    ), imports
