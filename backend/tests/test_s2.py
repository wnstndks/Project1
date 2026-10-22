"""S2 rules on synthetic forecasts: the volatility conversion, no leverage, cuts any day but
adds only on weekly dates, the 0.25 band, no edge means no position, a missing row keeps
the state, outcomes are never read and a decision never depends on later rows."""

import math
from datetime import date

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

from app.strategy import s2
from app.strategy.signals import EdgeStatus, decision_dates

BUDGETS = {"stock": 0.80, "crypto": 0.20}
CONFIG = s2.s2_1d()
DAILY_VOL = {"stock": 0.010, "crypto": 0.035}


def _width_for(annual_vol: float, asset_class: str) -> float:
    """Standardized q90 - q10 (scale 1) that gives `annual_vol`."""
    return annual_vol / math.sqrt(CONFIG.bars_per_year[asset_class]) * s2.INTERVAL_WIDTH_IN_SIGMAS


def synthetic_oos(start="2021-01-01", end="2021-06-30", seed=0) -> pd.DataFrame:
    """Forecast rows for SPY (weekdays, holidays included on purpose) and BTC (every day),
    plus a symbol S2 never trades."""
    rng = np.random.default_rng(seed)
    parts = []
    for symbol, cls, freq in (
        ("SPY", "stock", "B"),
        ("BTC-USD", "crypto", "D"),
        ("QQQ", "stock", "B"),
    ):
        dates = pd.date_range(start, end, freq=freq)
        n = len(dates)
        half = rng.uniform(0.8, 1.6, n)
        q50 = rng.normal(0.0, 0.2, n)
        parts.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "symbol": symbol,
                    "asset_class": cls,
                    "y": rng.normal(size=n),
                    "fr": rng.normal(scale=0.02, size=n),
                    "scale": DAILY_VOL[cls] * rng.uniform(0.6, 1.8, n),
                    "gbdt_q10": q50 - half,
                    "gbdt_q50": q50,
                    "gbdt_q90": q50 + half,
                    "gbdt_p_up": rng.uniform(0.4, 0.6, n),
                    "ewma_t_q10": -1.1,
                    "ewma_t_q90": 1.1,
                    "segment": "walk_forward",
                }
            )
        )
    return pd.concat(parts, ignore_index=True)


def always(edge: bool, hit: float | None = 0.56):
    def edge_at(as_of, asset_class, horizon):
        return EdgeStatus(edge, "edge" if edge else "not_significant", hit, 100)

    return edge_at


def row(annual_vol: float, asset_class: str = "stock") -> dict:
    w = _width_for(annual_vol, asset_class)
    return {"scale": 1.0, "gbdt_q10": -w / 2, "gbdt_q90": w / 2}


EDGE = EdgeStatus(True, "edge", 0.56, 100)
NO_EDGE = EdgeStatus(False, "not_significant", None, 100)


def step(r, state, *, weekly, status=EDGE, cls="stock", day=date(2021, 3, 1)):
    return s2.decide(
        r, day, cls, state, weekly=weekly, status=status, budget=BUDGETS[cls], config=CONFIG
    )


def test_registered_values():
    assert CONFIG.name == "S2-1d" and CONFIG.horizon == "1d"
    assert dict(CONFIG.symbols) == {"stock": "SPY", "crypto": "BTC-USD"}
    assert (CONFIG.risk_budget, CONFIG.band, CONFIG.min_trade_share) == (0.06, 0.25, 0.02)
    assert dict(CONFIG.bars_per_year) == {"stock": 252, "crypto": 365}
    assert CONFIG.quantiles == ("gbdt_q10", "gbdt_q90")
    # Outcomes and direction never feed the rule.
    for col in ("y", "fr", "gbdt_q50", "gbdt_p_up"):
        assert col not in CONFIG.input_columns


def test_implied_vol_converts_the_80_percent_range():
    # A normal 80% interval is 2 x 1.2816 sigma wide.
    assert s2.implied_vol(-1.2816, 1.2816, 0.01, 252) == pytest.approx(0.01 * math.sqrt(252))
    assert s2.implied_vol(-0.5, 0.5, 0.02, 365) == pytest.approx(
        0.02 / 2.5632 * math.sqrt(365), rel=1e-4
    )
    for bad in ((0.5, -0.5, 0.01), (0.0, 0.0, 0.01), (-1, 1, float("nan")), (None, 1, 0.01)):
        assert math.isnan(s2.implied_vol(*bad, 252))


def test_target_exposure_never_leverages():
    assert s2.target_exposure(0.15, 0.80, 0.06) == pytest.approx(0.5)
    assert s2.target_exposure(0.05, 0.80, 0.06) == 1.0  # calm: capped at the budget
    assert s2.target_exposure(0.60, 0.20, 0.06) == pytest.approx(0.5)
    assert s2.target_exposure(0.30, 0.0, 0.06) == 0.0
    with pytest.raises(ValueError):
        s2.target_exposure(float("nan"), 0.8, 0.06)


def test_weekly_date_sets_exposure_and_weight():
    sig, state = step(row(0.15), s2.S2State(), weekly=True)
    assert sig.action == "buy" and sig.label == "매수"
    assert state.allowed == pytest.approx(0.5) and state.exposure == pytest.approx(0.5)
    assert sig.target_exposure == pytest.approx(0.5)
    assert sig.reasons["target_weight"] == pytest.approx(0.40)  # 0.80 x 0.5
    assert sig.reasons["sigma"] == pytest.approx(0.15)
    assert sig.held_before is False and sig.held_after is True


def test_exposure_is_added_only_on_weekly_dates():
    state = s2.S2State(allowed=0.3, exposure=0.3)
    sig, after = step(row(0.05), state, weekly=False)  # k* = 1, but not a weekly date
    assert sig.action == "hold" and after == state
    sig, after = step(row(0.05), state, weekly=True)
    assert sig.action == "buy" and after.exposure == 1.0


def test_exposure_is_cut_on_any_day():
    state = s2.S2State(allowed=1.0, exposure=1.0)
    sig, after = step(row(0.30), state, weekly=False)  # k* = 0.25
    assert sig.action == "sell" and sig.label == "매도"
    assert after.exposure == pytest.approx(0.25) and after.allowed == pytest.approx(0.25)
    # The ratchet holds e down for the rest of the week even when volatility calms.
    sig, again = step(row(0.05), after, weekly=False)
    assert sig.action == "hold" and again.allowed == pytest.approx(0.25)


def test_band_boundary_is_inclusive():
    # From R = 0.5, a k* of exactly 0.25 lower trades; just inside the band does not.
    state = s2.S2State(allowed=0.5, exposure=0.5)
    vol_for = lambda k: 0.06 / (0.80 * k)  # noqa: E731
    sig, after = step(row(vol_for(0.25)), state, weekly=True)
    assert sig.action == "sell" and after.exposure == pytest.approx(0.25)
    sig, after = step(row(vol_for(0.2501)), state, weekly=True)
    assert sig.action == "hold" and after.exposure == 0.5
    assert after.allowed == pytest.approx(0.2501)


def test_no_edge_closes_and_waits_for_a_weekly_date():
    state = s2.S2State(allowed=0.6, exposure=0.6)
    sig, after = step(row(0.10), state, weekly=False, status=NO_EDGE)
    assert sig.action == "no_edge" and sig.label == "우위 없음"
    assert after == s2.S2State(0.0, 0.0) and sig.held_before and not sig.held_after
    assert sig.reasons["target_weight"] == 0.0 and sig.reasons["code"] == "not_significant"
    # The edge returns mid-week: e restarts at 0, so nothing is bought before the weekly date.
    sig, mid = step(row(0.10), after, weekly=False)
    assert sig.action == "hold" and mid.exposure == 0.0
    sig, week = step(row(0.10), mid, weekly=True)
    assert sig.action == "buy" and week.exposure == pytest.approx(0.75)


def test_missing_row_keeps_the_state_unless_there_is_no_edge():
    state = s2.S2State(allowed=0.6, exposure=0.6)
    sig, after = step(None, state, weekly=True)
    assert sig.action == "hold" and sig.reasons["code"] == "missing_row" and after == state
    bad = {"scale": 1.0, "gbdt_q10": 0.2, "gbdt_q90": -0.2}  # unusable range
    sig, after = step(bad, state, weekly=True)
    assert sig.reasons["code"] == "missing_row" and after == state
    sig, after = step(None, state, weekly=True, status=NO_EDGE)
    assert sig.action == "no_edge" and after.exposure == 0.0


def test_confidence_is_display_only():
    for hit, level in ((0.60, "high"), (0.53, "medium"), (0.50, "low"), (None, "low")):
        status = EdgeStatus(True, "edge", hit, 100)
        sig, after = step(row(0.15), s2.S2State(), weekly=True, status=status)
        assert sig.confidence == level
        assert after.exposure == pytest.approx(0.5)


def test_decision_dates_are_sessions_and_days():
    stock = s2.daily_dates("stock", "2021-06-28", "2021-07-09")
    assert date(2021, 7, 5) not in stock  # Independence Day observed
    assert date(2021, 7, 3) not in stock and date(2021, 7, 2) in stock
    coin = s2.daily_dates("crypto", "2021-06-28", "2021-07-04")
    assert len(coin) == 7


def test_frame_is_daily_and_weekly_flags_follow_the_s1_calendar():
    oos = synthetic_oos()
    frame = s2.signal_frame(oos, always(True), CONFIG, BUDGETS)
    assert set(frame["symbol"]) == {"SPY", "BTC-USD"}  # QQQ is never traded
    for cls in ("stock", "crypto"):
        f = frame[frame["asset_class"] == cls]
        start, end = oos["date"].min(), oos["date"].max()
        assert [d.date() for d in f["as_of"]] == s2.daily_dates(cls, start, end)
        weekly = set(decision_dates("weekly", cls, start, end))
        assert set(f.loc[f["weekly"], "as_of"].dt.date) == weekly
        # Exposure only rises on weekly dates.
        rises = f[f["exposure"] > f["exposure_before"] + 1e-12]
        assert rises["weekly"].all() and not rises.empty
    # Holiday rows in the synthetic data (weekdays) are never decision dates.
    assert pd.Timestamp("2021-04-02") not in set(frame.loc[frame["symbol"] == "SPY", "as_of"])


def test_no_edge_anywhere_means_no_position():
    frame = s2.signal_frame(synthetic_oos(), always(False), CONFIG, BUDGETS)
    assert not frame.empty
    assert (frame["action"] == "no_edge").all() and (frame["target_weight"] == 0).all()


def test_outcomes_are_never_read():
    oos = synthetic_oos()
    shuffled = oos.copy()
    rng = np.random.default_rng(1)
    for col in ("y", "fr", "gbdt_q50", "gbdt_p_up"):
        shuffled[col] = rng.permutation(shuffled[col].to_numpy())
    a = s2.signal_frame(oos, always(True), CONFIG, BUDGETS)
    b = s2.signal_frame(shuffled, always(True), CONFIG, BUDGETS)
    pdt.assert_frame_equal(a, b)
    with pytest.raises(ValueError):
        s2.signal_frame(oos.drop(columns=["gbdt_q90"]), always(True), CONFIG, BUDGETS)


def test_later_rows_do_not_change_earlier_decisions():
    oos = synthetic_oos()
    cut = pd.Timestamp("2021-04-15")
    full = s2.signal_frame(oos, always(True), CONFIG, BUDGETS, "2021-01-01", "2021-06-30")
    early = s2.signal_frame(oos[oos["date"] <= cut], always(True), CONFIG, BUDGETS,
                            "2021-01-01", "2021-04-15")  # fmt: skip
    pdt.assert_frame_equal(full[full["as_of"] <= cut].reset_index(drop=True), early)


def test_edge_is_asked_only_about_the_decision_date():
    calls = []

    def edge_at(as_of, asset_class, horizon):
        calls.append((as_of, asset_class, horizon))
        return EDGE

    frame = s2.signal_frame(synthetic_oos(), edge_at, CONFIG, BUDGETS)
    assert sorted(calls) == sorted(
        (d.date(), c, "1d") for d, c in zip(frame["as_of"], frame["asset_class"], strict=True)
    )


def test_decisions_are_budget_times_exposure_and_never_leverage():
    frame = s2.signal_frame(synthetic_oos(), always(True), CONFIG, BUDGETS)
    dec = s2.decisions(frame)
    assert list(dec.columns) == ["date", "symbol", "weight"]
    assert len(dec) == len(frame)
    budget = frame["asset_class"].map(BUDGETS)
    np.testing.assert_allclose(dec["weight"], budget * frame["exposure"])
    assert (dec["weight"] >= 0).all()
    assert (dec.loc[dec["symbol"] == "SPY", "weight"] <= 0.80 + 1e-12).all()
    assert (dec.loc[dec["symbol"] == "BTC-USD", "weight"] <= 0.20 + 1e-12).all()
    bad = frame.assign(target_weight=0.9)
    with pytest.raises(ValueError):
        s2.decisions(bad)


def test_ewma_variant_only_swaps_the_width_source():
    d2 = s2.ewma_variant(CONFIG)
    assert d2.quantiles == ("ewma_t_q10", "ewma_t_q90")
    assert (d2.risk_budget, d2.band, d2.symbols) == (
        CONFIG.risk_budget,
        CONFIG.band,
        CONFIG.symbols,
    )
    oos = synthetic_oos()
    a = s2.signal_frame(oos, always(False), d2, BUDGETS)
    b = s2.signal_frame(oos, always(False), CONFIG, BUDGETS)
    # With no edge both stay in cash: the difference can only come from edge days.
    assert (a["target_weight"] == 0).all() and (b["target_weight"] == 0).all()
    on = s2.signal_frame(oos, always(True), d2, BUDGETS)
    assert not on["sigma"].equals(s2.signal_frame(oos, always(True), CONFIG, BUDGETS)["sigma"])


def test_deterministic():
    oos = synthetic_oos(seed=3)
    a = s2.signal_frame(oos, always(True), CONFIG, BUDGETS)
    b = s2.signal_frame(oos.sample(frac=1.0, random_state=0), always(True), CONFIG, BUDGETS)
    pdt.assert_frame_equal(a, b)


def test_day_by_day_paper_path_matches_the_replay():
    """`decide_day` (paper trading, one date at a time with the stored state) makes the
    same decisions as `signal_frame` (backtest replay)."""
    oos = synthetic_oos(end="2021-03-31")
    frame = s2.signal_frame(oos, always(True), CONFIG, BUDGETS)
    prev: dict[str, s2.S2State] = {}
    got = []
    for cls in ("stock", "crypto"):
        for d in s2.daily_dates(cls, oos["date"].min(), oos["date"].max()):
            assert s2.is_decision_day(cls, d)
            (sig,) = s2.decide_day(oos, d, prev, always(True), CONFIG, BUDGETS, (cls,))
            prev[cls] = sig.state
            assert sig.state.exposure == sig.target_exposure
            got.append((pd.Timestamp(d), sig.symbol, sig.action, sig.target_exposure))
    want = list(
        zip(frame["as_of"], frame["symbol"], frame["action"], frame["exposure"], strict=True)
    )
    assert sorted(got) == sorted(want)
    assert not s2.is_decision_day("stock", date(2021, 4, 2))  # Good Friday
    assert s2.is_weekly_day("stock", date(2021, 4, 1)) and s2.is_weekly_day(
        "crypto", date(2021, 4, 4)
    )


def test_paper_decider_round_trips_the_stored_state():
    oos = synthetic_oos(end="2021-03-31")
    decide = s2.paper_decider(BUDGETS)
    assert CONFIG.universe == {"SPY": "stock", "BTC-USD": "crypto"}
    prev: dict = {}
    for d in s2.daily_dates("stock", "2021-01-04", "2021-03-31"):
        (sig,) = decide(oos, d, prev, always(True), CONFIG, "stock")
        assert sig.reasons["R"] == sig.target_exposure
        prev = {"e": sig.reasons["e"], "R": sig.reasons["R"]}  # what paper.py stores
    frame = s2.signal_frame(oos, always(True), CONFIG, BUDGETS, "2021-01-04", "2021-03-31")
    last = frame[frame["symbol"] == "SPY"].iloc[-1]
    assert prev == {"e": last["allowed"], "R": last["exposure"]}
    for bad in ({"e": 0.5}, {"e": float("nan"), "R": 0.1}, {"e": 0.5, "R": 1.5}):
        with pytest.raises(ValueError):
            decide(oos, date(2021, 3, 31), bad, always(True), CONFIG, "stock")
