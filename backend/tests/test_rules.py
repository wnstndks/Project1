"""Buy-more / stop-loss rule checks (app/strategy/rules.py, D-027): pure functions."""

import math
import os
from datetime import date, timedelta
from itertools import pairwise

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.strategy.risk import Book, RiskLimits
from app.strategy.rules import (
    BLOCK_LABELS,
    CRYPTO_DEFAULTS,
    NO_CASH_NOTE_KO,
    PROB_CAVEAT_KO,
    STATUS_LABELS,
    AssetClassRule,
    LimitState,
    PositionView,
    RuleSettings,
    SymbolRule,
    bars_below_ma,
    evaluate,
    prob_below,
    prob_below_label,
    sma,
)

SETTINGS = RuleSettings()
# The original defaults (10% × 3): useful where a step below the stop-loss is the point.
WIDE_STEPS = RuleSettings(add_step_pct=10.0, add_max_steps=3)
NO_LIMITS = LimitState()
START = date(2026, 1, 1)


@pytest.fixture
def clean_env(monkeypatch):
    """Settings built here never see backend/.env or the shell's AM_ variables (ISSUE-014)."""
    for key in list(os.environ):
        if key.upper().startswith("AM_"):
            monkeypatch.delenv(key)
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def config(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def bars(closes, highs=None, start=START) -> pd.DataFrame:
    df = pd.DataFrame(
        {"date": [start + timedelta(days=i) for i in range(len(closes))], "close": closes}
    )
    if highs is not None:
        df["high"] = highs
    return df


def flat(level: float, n: int = 100) -> pd.DataFrame:
    return bars([float(level)] * n)


def position(
    price: float,
    avg_cost: float = 100.0,
    weight: float = 10.0,
    steps: int = 0,
    symbol: str = "AAPL",
    asset_class: str = "stock",
    quantity: float = 1.0,
) -> PositionView:
    return PositionView(symbol, asset_class, quantity, avg_cost, price, weight, steps)


def codes(check) -> list[str]:
    return [t.code for t in check.triggers]


# Rallied to 150, then 130: the 60-bar high is 150, the stop 120.
RALLIED = bars([100.0] * 40 + [150.0] + [130.0] * 30)


# --- stop-loss conditions --------------------------------------------------------------


def test_cut_loss_fires_at_and_below_the_threshold():
    at = evaluate(position(85.0), flat(100), SETTINGS, NO_LIMITS)
    below = evaluate(position(84.0), flat(100), SETTINGS, NO_LIMITS)
    above = evaluate(position(85.5), flat(100), SETTINGS, NO_LIMITS)
    assert at.status == below.status == "cut"
    assert "cut_loss" in codes(at) and "cut_loss" in codes(below)
    assert above.status != "cut" and "cut_loss" not in codes(above)
    assert at.levels.cut_loss_price == pytest.approx(85.0)
    assert at.triggers[0].kind == "cut" and "−15%" in at.triggers[0].detail
    assert at.label_ko == "손절 검토" and at.chip_ko == "매도 검토"


def test_trailing_stop_measures_from_the_window_high_even_in_profit():
    # +19% on cost but −20.7% from the 60-bar high.
    check = evaluate(position(119.0), RALLIED, SETTINGS, NO_LIMITS)
    assert check.status == "cut"
    assert codes(check) == ["trailing_stop"]
    assert check.levels.trailing_high == 150.0
    assert check.levels.trailing_stop_price == pytest.approx(120.0)
    # The stop-loss level is the higher of the two legs.
    assert check.levels.cut_price == pytest.approx(120.0)
    assert check.cut_distance_pct == pytest.approx((120.0 / 119.0 - 1) * 100)
    # In profit, the review is about keeping the gain, not a stop-loss.
    assert check.label_ko == "이익 보전 검토" and check.chip_ko == "매도 검토"
    assert STATUS_LABELS[check.status] == "손절 검토"  # compatibility value, not for the UI


def test_trailing_stop_in_a_loss_without_the_cut_loss_leg_is_a_trend_exit():
    # Spiked to 115 then settled at 101 (above the 60-day average); price 88 is −12% on
    # cost, so only the trailing stop (115 × 0.8 = 92) fires.
    closes = [100.0] * 59 + [115.0] + [101.0] * 4
    check = evaluate(position(88.0), bars(closes), SETTINGS, NO_LIMITS)
    assert codes(check) == ["trailing_stop"]
    assert check.label_ko == "추세 이탈 · 매도 검토" and check.chip_ko == "매도 검토"


def test_trailing_high_uses_the_high_column_and_the_current_price():
    closes = [100.0] * 60
    highs = [100.0] * 59 + [160.0]
    with_highs = evaluate(position(127.0), bars(closes, highs), SETTINGS, NO_LIMITS)
    assert with_highs.levels.trailing_high == 160.0
    assert "trailing_stop" in codes(with_highs)  # 127 < 160 × 0.8 = 128
    # A current price above every bar becomes the high: a fresh high never trips the stop.
    new_high = evaluate(position(170.0), bars(closes, highs), SETTINGS, NO_LIMITS)
    assert new_high.levels.trailing_high == 170.0
    assert new_high.status == "hold" and "trailing_stop" not in codes(new_high)


def test_trailing_window_ignores_highs_older_than_the_lookback():
    closes = [200.0] + [100.0] * 60  # the 200 is the 61st bar back
    check = evaluate(position(100.0), bars(closes), SETTINGS, NO_LIMITS)
    assert check.levels.trailing_high == 100.0
    assert check.status == "hold"
    longer = RuleSettings(trailing_lookback_days=61)
    assert evaluate(position(100.0), bars(closes), longer, NO_LIMITS).levels.trailing_high == 200.0


def test_below_ma_counts_consecutive_closes_under_the_long_average():
    five = bars([100.0] * 65 + [90.0] * 5)
    four = bars([100.0] * 65 + [90.0] * 4)
    # Price 96 keeps the other stop-loss legs and the buy-more step (95) quiet.
    hit = evaluate(position(96.0), five, SETTINGS, NO_LIMITS)
    miss = evaluate(position(96.0), four, SETTINGS, NO_LIMITS)
    assert hit.status == "cut" and codes(hit) == ["below_ma"]
    assert "5일 연속" in hit.triggers[0].detail
    assert hit.label_ko == "추세 이탈 · 매도 검토"
    assert miss.status == "hold" and "below_ma" not in codes(miss)
    assert hit.levels.ma_long == pytest.approx((55 * 100 + 5 * 90) / 60)


def test_below_ma_uses_closes_not_the_live_price():
    # Closes are above the average; only the live quote dipped. No stop-loss on that.
    check = evaluate(position(96.0), flat(100), SETTINGS, NO_LIMITS)
    assert "below_ma" not in codes(check)


def test_bars_below_ma_helper():
    assert bars_below_ma(np.array([1.0, 2.0]), 3) is None
    closes = np.array([100.0] * 10 + [90.0, 90.0, 110.0, 90.0])
    assert bars_below_ma(closes, 5) == 1
    assert sma(closes, 2) == pytest.approx(100.0)
    assert sma(closes, 100) is None


# --- precedence -------------------------------------------------------------------------


def test_cut_wins_over_add_and_add_conditions_are_not_listed():
    # Bars at 50 put the 20-day average far below the price, so the step rule would fire.
    check = evaluate(position(84.0), flat(50), SETTINGS, NO_LIMITS)
    assert check.status == "cut"
    assert "cut_loss" in codes(check)
    assert "add_step" not in codes(check)
    # Buy-more levels are still reported for the UI.
    assert check.levels.add_price == pytest.approx(95.0)
    assert check.levels.next_add_step == 1


def test_labels_cover_every_status():
    assert set(STATUS_LABELS) == {"cut", "add", "hold"}
    assert "kill_switch" in BLOCK_LABELS and "max_position_weight" in BLOCK_LABELS
    add = evaluate(position(94.0), flat(50), SETTINGS, NO_LIMITS)
    hold = evaluate(position(100.0), flat(50), SETTINGS, NO_LIMITS)
    assert (add.status, add.label_ko, add.chip_ko) == ("add", "추매 검토", "추매 검토")
    assert (hold.status, hold.label_ko, hold.chip_ko) == ("hold", "관망", "관망")


# --- buy-more: steps ----------------------------------------------------------------------


def test_add_step_price_moves_with_steps_done_and_stops_at_the_maximum():
    first = evaluate(position(94.0), flat(50), SETTINGS, NO_LIMITS)
    assert first.status == "add" and codes(first) == ["add_step"]
    assert first.levels.add_price == pytest.approx(95.0)
    assert first.levels.next_add_step == 1
    assert "1회차" in first.triggers[0].label_ko

    second_pending = evaluate(position(94.0, steps=1), flat(50), SETTINGS, NO_LIMITS)
    assert second_pending.status == "hold"
    assert second_pending.levels.add_price == pytest.approx(90.0)
    assert second_pending.levels.next_add_step == 2
    assert second_pending.add_distance_pct == pytest.approx((90.0 / 94.0 - 1) * 100)

    second = evaluate(position(89.0, steps=1), flat(50), SETTINGS, NO_LIMITS)
    assert second.status == "add" and second.levels.next_add_step == 2

    exhausted = evaluate(position(86.0, steps=2), flat(50), SETTINGS, NO_LIMITS)
    assert exhausted.status == "hold"
    assert exhausted.levels.add_price is None
    assert exhausted.levels.next_add_step is None
    assert exhausted.add_distance_pct is None


def test_default_steps_all_sit_above_the_default_stop_loss():
    # 2 × 5% = 10% < 15%: no step can be a cut first, and the settings say so.
    assert SETTINGS.add_step_pct * SETTINGS.add_max_steps < SETTINGS.cut_loss_pct
    assert SETTINGS.validate_notes() == () and SETTINGS.warnings == ()
    for steps in (0, 1):
        check = evaluate(position(96.0, steps=steps), flat(50), SETTINGS, NO_LIMITS)
        assert check.levels.add_price > check.levels.cut_price
        assert "add_below_cut" not in codes(check)


def test_validate_notes_flag_a_last_step_below_the_stop_loss():
    (note,) = WIDE_STEPS.validate_notes()
    assert note.startswith("전역") and "−30%" in note and "−15%" in note
    assert WIDE_STEPS.warnings == WIDE_STEPS.validate_notes()
    # The crypto layer is checked on its own values when it differs from the global ones.
    crypto = RuleSettings(crypto=AssetClassRule(cut_loss_pct=8.0))
    assert [n.split(":")[0] for n in crypto.validate_notes()] == ["코인"]
    # A symbol that overrides one of the three values involved is checked too.
    symbol = RuleSettings(targets={"MSFT": SymbolRule(add_max_steps=4)})
    assert [n.split(":")[0] for n in symbol.validate_notes()] == ["MSFT"]
    quiet = RuleSettings(targets={"MSFT": SymbolRule(target_weight_pct=20.0)})
    assert quiet.validate_notes() == ()


def test_next_add_price_below_the_cut_price_is_pointed_out():
    # With 10% steps the second (−20%) is under the −15% stop-loss: the user should know.
    check = evaluate(position(95.0, steps=1), flat(50), WIDE_STEPS, NO_LIMITS)
    assert check.status == "hold"
    assert codes(check) == ["add_below_cut"]
    assert check.levels.add_price == pytest.approx(80.0)
    assert check.levels.cut_price == pytest.approx(85.0)
    # The first step (−10%) is above it: nothing to point out.
    assert "add_below_cut" not in codes(evaluate(position(95.0), flat(50), WIDE_STEPS, NO_LIMITS))
    # A trailing high can push the cut price above the step price as well.
    check = evaluate(position(125.0), RALLIED, SETTINGS, NO_LIMITS)
    assert check.status == "hold" and codes(check) == ["add_below_cut"]
    # Once the position is under review for cutting the note is moot.
    assert "add_below_cut" not in codes(evaluate(position(119.0), RALLIED, SETTINGS, NO_LIMITS))


def test_add_step_requires_the_price_above_the_short_average():
    # Price 94 is under the 20-day average (100): the step price is reached but held back.
    held = evaluate(position(94.0), flat(100), SETTINGS, NO_LIMITS)
    assert held.status == "hold"
    assert codes(held) == ["add_below_ma_short"]
    assert held.triggers[0].kind == "info"
    assert held.levels.ma_short == pytest.approx(100.0)

    without_filter = RuleSettings(add_requires_above_ma_short=False)
    assert evaluate(position(94.0), flat(100), without_filter, NO_LIMITS).status == "add"


def test_add_step_fires_only_at_or_below_the_step_price():
    assert evaluate(position(95.0), flat(50), SETTINGS, NO_LIMITS).status == "add"
    assert evaluate(position(95.5), flat(50), SETTINGS, NO_LIMITS).status == "hold"


# --- buy-more: target weight --------------------------------------------------------------


def test_below_target_weight_fires_at_the_gap_regardless_of_the_average():
    targets = {"AAPL": SymbolRule(target_weight_pct=20.0)}
    settings = RuleSettings(targets=targets)
    # Price at cost: the step price (95) is not reached, so only the weight rule can fire.
    low = evaluate(position(100.0, weight=15.0), flat(100), settings, NO_LIMITS)
    assert low.status == "add" and codes(low) == ["below_target"]
    assert low.levels.target_weight_pct == 20.0
    near = evaluate(position(100.0, weight=15.5), flat(100), settings, NO_LIMITS)
    assert near.status == "hold" and "below_target" not in codes(near)
    # No target for the symbol: the rule is off.
    other = evaluate(position(100.0, weight=1.0, symbol="MSFT"), flat(100), settings, NO_LIMITS)
    assert other.status == "hold" and other.levels.target_weight_pct is None


# --- limits ---------------------------------------------------------------------------------


def test_weight_cap_blocks_an_add_that_would_pass_the_cap():
    # Cap 20%, one order up to 5%: from 15% an order fits exactly, from 15.1% it does not.
    fits = evaluate(position(94.0, weight=15.0), flat(50), SETTINGS, NO_LIMITS)
    assert fits.status == "add" and fits.blocked_by == ()
    over = evaluate(position(94.0, weight=15.1), flat(50), SETTINGS, NO_LIMITS)
    assert over.status == "hold"
    assert codes(over) == ["add_step"]  # the condition stays visible
    assert over.blocked_by == ("max_position_weight",)
    at_cap = evaluate(position(94.0, weight=20.0), flat(50), SETTINGS, NO_LIMITS)
    assert at_cap.blocked_by == ("max_position_weight",)


def test_weight_room_is_the_distance_to_the_cap():
    room = evaluate(position(100.0, weight=12.0), flat(50), SETTINGS, NO_LIMITS).weight_room_pt
    assert room == pytest.approx(8.0)
    over = evaluate(position(100.0, weight=25.0), flat(50), SETTINGS, NO_LIMITS).weight_room_pt
    assert over == 0.0
    spy = evaluate(position(100.0, weight=20.0, symbol="SPY"), flat(50), SETTINGS, NO_LIMITS)
    assert spy.weight_room_pt == pytest.approx(60.0)


def test_index_fund_uses_its_own_cap():
    spy = evaluate(position(94.0, weight=20.0, symbol="SPY"), flat(50), SETTINGS, NO_LIMITS)
    assert spy.status == "add" and spy.blocked_by == ()
    capped = evaluate(position(94.0, weight=76.0, symbol="SPY"), flat(50), SETTINGS, NO_LIMITS)
    assert capped.status == "hold" and capped.blocked_by == ("max_index_fund_weight",)


def test_tighter_limits_from_settings_apply():
    limits = LimitState(limits=RiskLimits(max_position_weight=0.10))
    check = evaluate(position(94.0, weight=6.0), flat(50), SETTINGS, limits)
    assert check.status == "hold" and check.blocked_by == ("max_position_weight",)


def test_kill_switch_blocks_adds_but_still_reports_cuts():
    tripped = LimitState(kill_switch_tripped=True, kill_switch_reason="max_drawdown")
    add = evaluate(position(94.0), flat(50), SETTINGS, tripped)
    assert add.status == "hold"
    assert codes(add) == ["add_step"]
    assert add.blocked_by == ("kill_switch",)
    cut = evaluate(position(84.0), flat(50), SETTINGS, tripped)
    assert cut.status == "cut" and cut.blocked_by == ("kill_switch",)


def test_book_runs_the_same_pre_trade_check_as_paper_trading():
    # No cash: the order check rejects on cash, so the add is blocked.
    broke = LimitState(book=Book(cash=0.0, positions={"AAPL": 1_000_000.0, "MSFT": 9_000_000.0}))
    check = evaluate(position(94.0, weight=10.0), flat(50), SETTINGS, broke)
    assert check.blocked_by == ("cash",) and check.status == "hold"
    assert check.add_cap_krw is None
    assert check.notes == ()

    # Cash on hand: the largest single buy is the per-order cap (5% of equity).
    funded = LimitState(book=Book(cash=10_000_000.0, positions={"AAPL": 1_000_000.0}))
    check = evaluate(position(94.0, weight=100 / 11), flat(50), SETTINGS, funded)
    assert check.status == "add" and check.blocked_by == ()
    assert check.add_cap_krw == pytest.approx(0.05 * 11_000_000)

    # Position already at the symbol cap inside the book.
    full = LimitState(book=Book(cash=8_000_000.0, positions={"AAPL": 2_000_000.0}))
    check = evaluate(position(94.0, weight=20.0), flat(50), SETTINGS, full)
    assert check.status == "hold" and check.blocked_by == ("max_position_weight",)


def test_absolute_order_cap_bounds_the_add_size_and_the_weight_test():
    limits = LimitState(
        limits=RiskLimits(max_order_krw=100_000.0),
        book=Book(cash=10_000_000.0, positions={"AAPL": 1_000_000.0}),
    )
    check = evaluate(position(94.0, weight=100 / 11), flat(50), SETTINGS, limits)
    assert check.add_cap_krw == pytest.approx(100_000.0)
    # The absolute cap is under 1% of equity here, so 19% + one order still fits.
    check = evaluate(position(94.0, weight=19.0), flat(50), SETTINGS, limits)
    assert "max_position_weight" not in check.blocked_by
    check = evaluate(position(94.0, weight=19.5), flat(50), SETTINGS, limits)
    assert "max_position_weight" in check.blocked_by


def test_missing_cash_record_is_noted():
    check = evaluate(position(100.0), flat(50), SETTINGS, NO_LIMITS)
    assert check.notes == (NO_CASH_NOTE_KO,)
    assert "현금 기록" in NO_CASH_NOTE_KO


# --- risk at the stop -----------------------------------------------------------------------


def test_risk_amount_is_the_loss_at_the_cut_price():
    check = evaluate(position(100.0, quantity=10.0), flat(50), SETTINGS, NO_LIMITS)
    assert check.levels.risk_amount == pytest.approx(150.0)  # (100 − 85) × 10
    assert check.risk_pct_equity is None and "risk_over_limit" not in codes(check)
    # A stop above the price (review already open) carries no further risk.
    assert evaluate(position(119.0), RALLIED, SETTINGS, NO_LIMITS).levels.risk_amount == 0.0


def test_risk_share_of_equity_warns_past_the_limit():
    fine = evaluate(position(100.0, quantity=10.0), flat(50), SETTINGS, NO_LIMITS, equity=10_000.0)
    assert fine.risk_pct_equity == pytest.approx(1.5)
    assert "risk_over_limit" not in codes(fine)
    over = evaluate(position(100.0, quantity=10.0), flat(50), SETTINGS, NO_LIMITS, equity=5_000.0)
    assert over.risk_pct_equity == pytest.approx(3.0)
    warn = next(t for t in over.triggers if t.code == "risk_over_limit")
    assert warn.kind == "info" and "3.0%" in warn.detail and "한도 2%" in warn.detail
    assert over.status == "hold"  # a warning, not a review
    looser = RuleSettings(max_risk_pct=5.0)
    assert "risk_over_limit" not in codes(
        evaluate(position(100.0, quantity=10.0), flat(50), looser, NO_LIMITS, equity=5_000.0)
    )
    with pytest.raises(ValueError):
        evaluate(position(100.0), flat(50), SETTINGS, NO_LIMITS, equity=0.0)


# --- asset-class layer ------------------------------------------------------------------------


def test_crypto_defaults_widen_the_stops_and_steps():
    coin = position(80.0, symbol="BTC-USD", asset_class="crypto")
    stock = position(80.0)
    assert evaluate(stock, flat(100), SETTINGS, NO_LIMITS).status == "cut"
    check = evaluate(coin, flat(100), SETTINGS, NO_LIMITS)
    assert check.status == "hold" and "cut_loss" not in codes(check)
    assert check.levels.cut_loss_price == pytest.approx(75.0)  # 25%
    assert check.levels.trailing_stop_price == pytest.approx(70.0)  # 30% of the high 100
    assert check.levels.add_price == pytest.approx(92.0)  # 8%
    at = evaluate(
        position(75.0, symbol="BTC-USD", asset_class="crypto"), flat(100), SETTINGS, NO_LIMITS
    )
    assert at.status == "cut" and at.label_ko == "손절 검토"


def test_resolve_layers_global_crypto_symbol():
    settings = RuleSettings(targets={"BTC-USD": SymbolRule(cut_loss_pct=40.0)})
    assert settings.resolve("ETH-USD").cut_loss_pct == 15.0  # no asset class: global
    assert settings.resolve("ETH-USD", "crypto").cut_loss_pct == 25.0
    assert settings.resolve("ETH-USD", "stock").cut_loss_pct == 15.0
    assert settings.resolve("BTC-USD", "crypto").cut_loss_pct == 40.0  # symbol wins
    assert settings.resolve("BTC-USD", "crypto").add_step_pct == 8.0  # untouched: crypto
    partial = RuleSettings(crypto=AssetClassRule(trailing_drop_pct=35.0))
    assert partial.resolve("X", "crypto").cut_loss_pct == 15.0  # None falls to global
    assert partial.resolve("X", "crypto").trailing_drop_pct == 35.0
    assert AssetClassRule(25.0, 30.0, 8.0) == CRYPTO_DEFAULTS


def test_crypto_config_blank_means_global(clean_env):
    clean_env.setenv("AM_RULES_CRYPTO_CUT_LOSS_PCT", "")
    settings = RuleSettings.from_config(config())
    assert settings.crypto.cut_loss_pct is None
    assert settings.resolve("BTC-USD", "crypto").cut_loss_pct == 15.0
    assert settings.resolve("BTC-USD", "crypto").trailing_drop_pct == 30.0


# --- history ----------------------------------------------------------------------------------


def test_short_history_skips_the_moving_average_rules_but_not_the_others():
    check = evaluate(position(84.0), flat(100, n=30), SETTINGS, NO_LIMITS)
    assert check.status == "cut" and "cut_loss" in codes(check)
    assert "insufficient_history" in codes(check)
    info = next(t for t in check.triggers if t.code == "insufficient_history")
    assert info.kind == "info" and "60일 이동평균" in info.detail
    assert check.levels.ma_long is None
    assert check.levels.ma_short == pytest.approx(100.0)  # 30 bars are enough for 20


def test_sixty_bars_give_the_average_but_not_five_consecutive_days():
    # All 60 closes below their own average is impossible; 62 bars give 3 average points.
    check = evaluate(position(96.0), bars([100.0] * 59 + [90.0] * 3), SETTINGS, NO_LIMITS)
    assert check.levels.ma_long is not None
    assert "below_ma" not in codes(check)
    info = next(t for t in check.triggers if t.code == "insufficient_history")
    assert "봉 64개 필요" in info.detail


def test_fewer_bars_than_the_short_average_withholds_the_step_add():
    check = evaluate(position(94.0), flat(100, n=10), SETTINGS, NO_LIMITS)
    assert check.status == "hold"
    assert codes(check) == ["insufficient_history"]
    assert "20일선 위 조건" in check.triggers[0].detail


def test_no_bars_needs_an_as_of_date():
    with pytest.raises(ValueError):
        evaluate(position(84.0), None, SETTINGS, NO_LIMITS)
    check = evaluate(position(84.0), None, SETTINGS, NO_LIMITS, as_of=date(2026, 10, 22))
    assert check.status == "cut" and check.as_of == date(2026, 10, 22)
    assert check.levels.trailing_high == 84.0


def test_as_of_is_the_last_bar_date_whatever_the_row_order():
    frame = flat(100).iloc[::-1].reset_index(drop=True)
    check = evaluate(position(100.0), frame, SETTINGS, NO_LIMITS)
    assert check.as_of == START + timedelta(days=99)
    stamped = frame.assign(date=pd.to_datetime(frame["date"]))
    assert evaluate(position(100.0), stamped, SETTINGS, NO_LIMITS).as_of == check.as_of


def test_distances_are_percent_moves_from_the_current_price():
    check = evaluate(position(100.0), flat(100), SETTINGS, NO_LIMITS)
    assert check.cut_distance_pct == pytest.approx(-15.0)
    assert check.add_distance_pct == pytest.approx(-5.0)
    assert check.status == "hold"


# --- input validation ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        position(0.0),
        position(float("nan")),
        position(100.0, avg_cost=0.0),
        PositionView("AAPL", "stock", 0.0, 100.0, 100.0, 10.0),
        PositionView("AAPL", "stock", 1.0, 100.0, 100.0, -1.0),
        PositionView("AAPL", "stock", 1.0, 100.0, 100.0, 10.0, -1),
    ],
)
def test_invalid_positions_fail_closed(bad):
    with pytest.raises(ValueError):
        evaluate(bad, flat(100), SETTINGS, NO_LIMITS)


def test_bars_without_a_close_column_are_rejected():
    with pytest.raises(ValueError):
        evaluate(
            position(100.0), pd.DataFrame({"date": [START], "open": [1.0]}), SETTINGS, NO_LIMITS
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cut_loss_pct": 0},
        {"cut_loss_pct": 100},
        {"add_step_pct": -1},
        {"add_max_steps": -1},
        {"ma_long": 1},
        {"below_ma_days": 0},
        {"max_risk_pct": 0},
        {"crypto": AssetClassRule(cut_loss_pct=100.0)},
        {"targets": {"AAPL": SymbolRule(target_weight_pct=0.0)}},
    ],
)
def test_rule_settings_reject_nonsense(kwargs):
    with pytest.raises(ValueError):
        RuleSettings(**kwargs)


# --- settings -------------------------------------------------------------------------------


def test_defaults_match_config_defaults(clean_env):
    assert RuleSettings.from_config(config()) == RuleSettings()
    assert RuleSettings().add_step_pct == 5.0 and RuleSettings().add_max_steps == 2
    assert RuleSettings().crypto == CRYPTO_DEFAULTS and RuleSettings().max_risk_pct == 2.0


def test_config_values_change_the_check(clean_env):
    clean_env.setenv("AM_RULES_CUT_LOSS_PCT", "10")
    clean_env.setenv("AM_RULES_ADD_MAX_STEPS", "1")
    clean_env.setenv("AM_RULES_ADD_REQUIRES_ABOVE_MA_SHORT", "false")
    clean_env.setenv("AM_RULES_MAX_RISK_PCT", "5")
    tight = RuleSettings.from_config(config())
    assert tight.cut_loss_pct == 10.0 and tight.add_max_steps == 1
    assert tight.add_requires_above_ma_short is False and tight.max_risk_pct == 5.0
    assert evaluate(position(90.0), flat(100), tight, NO_LIMITS).status == "cut"
    assert evaluate(position(90.0), flat(100), SETTINGS, NO_LIMITS).status != "cut"
    # One step only, and no average filter: the step fires under the average, then no more.
    assert evaluate(position(94.0), flat(100), tight, NO_LIMITS).status == "add"
    assert evaluate(position(94.0, steps=1), flat(100), tight, NO_LIMITS).levels.add_price is None


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("AM_RULES_CUT_LOSS_PCT", "150"),
        ("AM_RULES_CUT_LOSS_PCT", "0"),
        ("AM_RULES_ADD_MAX_STEPS", "-1"),
        ("AM_RULES_MA_LONG", "1"),
        ("AM_RULES_CRYPTO_CUT_LOSS_PCT", "0"),
        ("AM_RULES_MAX_RISK_PCT", "100"),
    ],
)
def test_config_rejects_out_of_range_values(clean_env, key, value):
    clean_env.setenv(key, value)
    with pytest.raises(ValidationError):
        config()


def test_per_symbol_overrides_apply_to_that_symbol_only():
    settings = RuleSettings(targets={"AAPL": SymbolRule(cut_loss_pct=5.0, add_max_steps=0)})
    aapl = evaluate(position(95.0), flat(50), settings, NO_LIMITS)
    msft = evaluate(position(95.0, symbol="MSFT"), flat(50), settings, NO_LIMITS)
    assert aapl.status == "cut" and aapl.levels.cut_loss_price == pytest.approx(95.0)
    assert aapl.levels.add_price is None
    assert msft.status == "add" and msft.levels.cut_loss_price == pytest.approx(85.0)
    assert msft.levels.add_price == pytest.approx(95.0)


def test_from_config_takes_targets_from_the_caller(clean_env):
    settings = RuleSettings.from_config(config(), {"BTC-USD": SymbolRule(target_weight_pct=10.0)})
    assert settings.resolve("BTC-USD").target_weight_pct == 10.0
    assert settings.resolve("ETH-USD").target_weight_pct is None


# --- forecast range as a reference ---------------------------------------------------------


def test_prob_below_matches_the_quantiles():
    base, p10, p50, p90 = 100.0, 90.0, 100.0, 115.0
    assert prob_below(p50, base, p10, p50, p90) == pytest.approx(0.5)
    assert prob_below(p10, base, p10, p50, p90) == pytest.approx(0.1)
    assert prob_below(p90, base, p10, p50, p90) == pytest.approx(0.9)


def test_prob_below_is_monotone_and_clipped_in_the_tails():
    args = (100.0, 90.0, 101.0, 115.0)
    levels = [40.0, 60.0, 80.0, 90.0, 95.0, 101.0, 108.0, 115.0, 130.0, 200.0, 500.0]
    probs = [prob_below(x, *args) for x in levels]
    assert all(a <= b for a, b in pairwise(probs))
    assert probs[0] == 0.01 and probs[-1] == 0.99
    # Just outside a quantile the slope continues instead of jumping to the clip.
    assert 0.01 < prob_below(88.0, *args) < 0.1
    assert 0.9 < prob_below(118.0, *args) < 0.99


def test_prob_below_interpolates_in_log_space():
    # Midpoint in log space between p10 and p50 maps to 0.3.
    base, p10, p50, p90 = 100.0, 80.0, 100.0, 120.0
    mid = math.exp((math.log(0.8) + math.log(1.0)) / 2) * base
    assert prob_below(mid, base, p10, p50, p90) == pytest.approx(0.3)


def test_prob_below_returns_none_for_bad_inputs():
    assert prob_below(100.0, 100.0, 110.0, 100.0, 120.0) is None  # out of order
    assert prob_below(0.0, 100.0, 90.0, 100.0, 110.0) is None
    assert prob_below(100.0, 100.0, float("nan"), 100.0, 110.0) is None
    assert prob_below(100.0, -1.0, 90.0, 100.0, 110.0) is None


def test_prob_below_handles_a_degenerate_quantile_pair():
    # q10 == q50: everything strictly below is at most 0.1, the point itself 0.5.
    assert prob_below(99.0, 100.0, 100.0, 100.0, 110.0) == pytest.approx(0.1)
    assert prob_below(100.0, 100.0, 100.0, 100.0, 110.0) == pytest.approx(0.5)
    expected = 0.5 + 0.4 * (math.log(1.05) / math.log(1.10))
    assert prob_below(105.0, 100.0, 100.0, 100.0, 110.0) == pytest.approx(expected)


def test_prob_below_label_rounds_inside_the_range_and_buckets_outside():
    args = (100.0, 90.0, 100.0, 115.0)
    assert prob_below_label(100.0, *args) == "약 50%"
    assert prob_below_label(90.0, *args) == "약 10%"
    assert prob_below_label(115.0, *args) == "약 90%"
    assert prob_below_label(92.0, *args) == "약 20%"  # 0.18 → nearest 5%
    # Outside the forecast range the extrapolated figure is a bucket, never a number.
    assert prob_below_label(89.0, *args) == "10% 미만"
    assert prob_below_label(50.0, *args) == "5% 미만"  # extrapolation hit the floor clip
    assert prob_below_label(116.0, *args) == "90% 초과"
    assert prob_below_label(500.0, *args) == "95% 초과"
    assert prob_below_label(100.0, 100.0, 110.0, 100.0, 120.0) is None
    assert "두 배" in PROB_CAVEAT_KO
