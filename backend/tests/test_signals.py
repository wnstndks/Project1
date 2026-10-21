"""Signal rules (S1): no edge means no signal, outcomes are never read, a date's signal
only depends on that date's rows and earlier decisions, and the result is deterministic."""

from datetime import date

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

from app.strategy import s1
from app.strategy.signals import EdgeStatus, decide, decision_dates, signal_frame

COST = {"stock": 0.001, "crypto": 0.002}
STOCKS = ["SPY", "QQQ", "IWM", "DIA", "XLB", "XLE"]
COINS = ["BTC-USD", "ETH-USD", "XRP-USD", "SOL-USD"]


def synthetic_oos(start="2021-01-01", end="2021-06-30", seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    parts = []
    for symbols, cls, freq in ((STOCKS, "stock", "B"), (COINS, "crypto", "D")):
        dates = pd.date_range(start, end, freq=freq)
        for sym in symbols:
            n = len(dates)
            q50 = rng.normal(0.1, 0.3, n)
            parts.append(
                pd.DataFrame(
                    {
                        "date": dates,
                        "symbol": sym,
                        "asset_class": cls,
                        "y": rng.normal(size=n),
                        "fr": rng.normal(scale=0.02, size=n),
                        "scale": rng.uniform(0.02, 0.08, n),
                        "gbdt_q10": q50 - 1.2,
                        "gbdt_q50": q50,
                        "gbdt_q90": q50 + 1.2,
                        "gbdt_p_up": rng.uniform(0.4, 0.65, n),
                        "climatology_p_up": 0.53 if cls == "stock" else 0.51,
                        "segment": "walk_forward",
                    }
                )
            )
    return pd.concat(parts, ignore_index=True)


def always(edge: bool, hit: float | None = 0.56):
    def edge_at(as_of, asset_class, horizon):
        return EdgeStatus(edge, "edge" if edge else "no_rank_edge", hit, 100)

    return edge_at


CONFIG = s1.s1_1w(COST)


def test_no_edge_gives_no_signal_anywhere():
    frame = signal_frame(synthetic_oos(), always(False), CONFIG)
    assert not frame.empty
    assert set(frame["action"]) == {"no_edge"}
    assert not frame["held_after"].any()
    assert set(frame["reason"]) == {"no_rank_edge"}


def test_outcomes_do_not_change_signals():
    oos = synthetic_oos()
    base = signal_frame(oos, always(True), CONFIG)
    rng = np.random.default_rng(1)
    other = oos.assign(y=rng.normal(size=len(oos)), fr=rng.normal(size=len(oos)))
    pdt.assert_frame_equal(base, signal_frame(other, always(True), CONFIG))
    pdt.assert_frame_equal(base, signal_frame(oos.drop(columns=["y", "fr"]), always(True), CONFIG))


def test_later_rows_do_not_change_earlier_signals():
    oos = synthetic_oos()
    cut = pd.Timestamp("2021-04-04")  # a Sunday: a coin decision date
    base = signal_frame(oos, always(True), CONFIG)
    later = oos["date"] > cut
    rng = np.random.default_rng(2)
    changed = oos.copy()
    changed.loc[later, "gbdt_p_up"] = rng.uniform(0, 1, later.sum())
    changed.loc[later, "gbdt_q50"] = rng.normal(size=later.sum())
    truncated = oos[~later]
    for other in (changed, truncated):
        got = signal_frame(other, always(True), CONFIG)
        pdt.assert_frame_equal(
            base[base["as_of"] <= cut].reset_index(drop=True),
            got[got["as_of"] <= cut].reset_index(drop=True),
        )
    # Signals do change after the cut, so the comparison above is not vacuous.
    after = signal_frame(changed, always(True), CONFIG)
    assert (
        not base[base["as_of"] > cut]
        .reset_index(drop=True)
        .equals(after[after["as_of"] > cut].reset_index(drop=True))
    )


def test_deterministic_and_order_independent():
    oos = synthetic_oos()
    a = signal_frame(oos, always(True), CONFIG)
    b = signal_frame(oos.sample(frac=1.0, random_state=3), always(True), CONFIG)
    pdt.assert_frame_equal(a, b)
    pdt.assert_frame_equal(a, signal_frame(oos, always(True), CONFIG))


def test_edge_is_asked_on_decision_dates_only():
    calls = []

    def edge_at(as_of, asset_class, horizon):
        calls.append((as_of, asset_class, horizon))
        return EdgeStatus(True, "edge")

    signal_frame(synthetic_oos(), edge_at, CONFIG)
    stock_days = {d for d, c, _ in calls if c == "stock"}
    coin_days = {d for d, c, _ in calls if c == "crypto"}
    assert stock_days == set(decision_dates("weekly", "stock", "2021-01-01", "2021-06-30"))
    assert all(d.weekday() == 6 for d in coin_days)
    assert {h for *_, h in calls} == {"1w"}
    assert len(calls) == len(set(calls))


def _day(scores: dict[str, float], cls="stock", d="2021-03-05", q50=1.0, scale=0.05):
    return pd.DataFrame(
        {
            "date": pd.Timestamp(d),
            "symbol": list(scores),
            "asset_class": cls,
            "scale": scale,
            "gbdt_q10": q50 - 1,
            "gbdt_q50": q50,
            "gbdt_q90": q50 + 1,
            "gbdt_p_up": [0.5 + s for s in scores.values()],
            "climatology_p_up": 0.5,
        }
    )


def by_symbol(signals):
    return {s.symbol: s for s in signals}


def test_entry_keep_and_exit_bands():
    # 6 stocks: enter in the top 2, keep within the top 4.
    rows = _day({"SPY": 0.06, "QQQ": 0.05, "IWM": 0.04, "DIA": 0.03, "XLB": 0.02, "XLE": 0.01})
    d = date(2021, 3, 5)
    got = by_symbol(decide(rows, d, {"IWM", "XLE"}, always(True), CONFIG))
    assert got["SPY"].action == "buy" and got["QQQ"].action == "buy"
    assert got["IWM"].action == "hold" and got["IWM"].held_after  # rank 3, inside keep band
    assert got["DIA"].action == "hold" and not got["DIA"].held_after  # not held, not top 2
    assert got["XLE"].action == "sell" and not got["XLE"].held_after  # rank 6
    assert got["SPY"].reasons["rank"] == 1 and got["SPY"].reasons["n"] == 6
    assert got["SPY"].label == "매수"
    assert got["SPY"].confidence == "high" and got["SPY"].confidence_value == 0.56


def test_hurdle_blocks_entry_when_expected_return_is_below_cost():
    rows = _day({"SPY": 0.06, "QQQ": 0.05, "IWM": 0.04}, q50=0.01, scale=0.05)  # 5bp < 10bp
    got = by_symbol(decide(rows, date(2021, 3, 5), set(), always(True), CONFIG))
    assert got["SPY"].action == "hold" and got["SPY"].reasons["code"] == "below_hurdle"
    assert not got["SPY"].held_after


def test_too_few_assets_and_missing_rows():
    rows = _day({"BTC-USD": 0.05, "ETH-USD": 0.01}, cls="crypto", d="2021-03-07")
    got = by_symbol(decide(rows, date(2021, 3, 7), {"BTC-USD"}, always(True), CONFIG))
    assert {s.action for s in got.values()} == {"no_edge"}
    assert got["BTC-USD"].reasons["code"] == "too_few_assets" and not got["BTC-USD"].held_after

    rows = _day({"SPY": 0.06, "QQQ": 0.05, "IWM": 0.04})
    got = by_symbol(decide(rows, date(2021, 3, 5), {"XLK"}, always(True), CONFIG))
    assert got["XLK"].action == "hold" and got["XLK"].held_after
    assert got["XLK"].reasons["code"] == "missing_row"
    got = by_symbol(decide(rows, date(2021, 3, 5), {"XLK"}, always(False), CONFIG))
    assert got["XLK"].action == "no_edge" and not got["XLK"].held_after


def test_ties_break_alphabetically_and_other_dates_and_symbols_are_ignored():
    rows = _day({"QQQ": 0.05, "DIA": 0.05, "IWM": 0.0, "AAPL": 0.5})
    rows = pd.concat([rows, _day({"XLB": 0.9}, d="2021-03-04")])
    got = by_symbol(decide(rows, date(2021, 3, 5), set(), always(True), CONFIG))
    assert set(got) == {"QQQ", "DIA", "IWM"}  # AAPL is outside the strategy universe
    assert got["DIA"].reasons["rank"] == 1 and got["QQQ"].reasons["rank"] == 2


def test_missing_input_column_is_rejected():
    rows = _day({"SPY": 0.1}).drop(columns=["climatology_p_up"])
    with pytest.raises(ValueError):
        decide(rows, date(2021, 3, 5), set(), always(True), CONFIG)


def test_decision_dates_follow_the_calendar():
    # Good Friday 2024-03-29 is an NYSE holiday: that week decides on Thursday.
    weekly = decision_dates("weekly", "stock", "2024-03-18", "2024-04-07")
    assert weekly == [date(2024, 3, 22), date(2024, 3, 28), date(2024, 4, 5)]
    # A week still in progress at `end` has no decision yet.
    assert decision_dates("weekly", "stock", "2024-03-18", "2024-03-27") == [date(2024, 3, 22)]
    assert decision_dates("weekly", "crypto", "2024-03-18", "2024-04-07") == [
        date(2024, 3, 24),
        date(2024, 3, 31),
        date(2024, 4, 7),
    ]
    assert decision_dates("monthly", "stock", "2024-01-01", "2024-03-31") == [
        date(2024, 1, 31),
        date(2024, 2, 29),
        date(2024, 3, 28),
    ]
    assert decision_dates("monthly", "crypto", "2024-01-15", "2024-03-30") == [
        date(2024, 1, 31),
        date(2024, 2, 29),
    ]


def test_large_cap_reference_keeps_the_rule():
    ref = s1.large_cap_reference(CONFIG)
    assert ref.horizon == CONFIG.horizon and ref.entry_fraction == CONFIG.entry_fraction
    assert set(ref.universe.values()) == {"stock"} and "SPY" not in ref.universe
    assert sum(s1.CLASS_BUDGETS.values()) == pytest.approx(1.0)


def test_registered_hurdle_costs_are_the_dearest_round_trip_per_class():
    costs = s1.round_trip_costs()
    assert costs["stock"] == pytest.approx(0.0080278)
    assert costs["crypto"] == pytest.approx(0.006)  # SOL/XRP slip 10bp; BTC/ETH 5bp
