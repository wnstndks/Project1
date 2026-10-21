"""Strategy backtest, baselines and the adoption tests on synthetic prices.

Canaries: a position on bar t depends only on signals up to t-1 (fills at the next open);
random signals earn nothing over a baseline and do not pass; a strategy that outputs the
baseline's weights is the baseline; taxes net gains within a year with the deduction and
no loss carry-forward; leverage and short sales are refused.
"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.data.calendar import expected_dates
from app.strategy import baselines as bl
from app.strategy.backtest import (
    BacktestConfig,
    BacktestInputs,
    CostModel,
    LeverageError,
    TaxModel,
    instrument,
    run_backtest,
    summarize,
)
from app.strategy.evaluation import adoption_gate, excess_return_test
from app.strategy.risk import RiskLimits

START, END = date(2019, 1, 1), date(2021, 12, 31)
FX = 1300.0
FREE = CostModel(commission={}, slippage_bps={}, sec_fee=0.0, fx_spread=0.0)
NO_TAX = TaxModel(stock_rate=0.0, crypto_rate=0.0, dividend_withholding=0.0)


def walk(seed: int, dates, vol: float, drift: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, vol, len(dates))
    close = 100 * np.exp(np.cumsum(r))
    gap = rng.normal(0, vol / 3, len(dates))
    open_ = np.r_[100.0, close[:-1]] * np.exp(gap)
    return pd.DataFrame({"open": open_, "close": close}, index=pd.DatetimeIndex(dates))


def market(n_stocks: int = 6, n_coins: int = 4, seed: int = 0) -> BacktestInputs:
    sessions = pd.DatetimeIndex(expected_dates("SPY", START, END))
    days = pd.date_range(START, END, freq="D")
    bars, insts = {}, {}
    stocks = ["SPY"] + [f"S{i}" for i in range(1, n_stocks)]
    coins = ["BTC-USD"] + [f"C{i}" for i in range(1, n_coins)]
    for i, s in enumerate(stocks):
        bars[s] = walk(seed + i, sessions, 0.01, 0.0003)
        insts[s] = instrument(s, "stock")
    for i, s in enumerate(coins):
        bars[s] = walk(seed + 100 + i, days, 0.04, 0.001)
        insts[s] = instrument(s, "crypto")
    fx = pd.Series(FX, index=pd.date_range(pd.Timestamp(START) - pd.Timedelta(days=1), END))
    return BacktestInputs(bars, fx, insts)


def classes(inputs: BacktestInputs) -> dict[str, str]:
    return {s: i.asset_class for s, i in inputs.instruments.items()}


def random_decisions(inputs: BacktestInputs, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for cls in ("stock", "crypto"):
        scores = []
        for d in bl.decision_dates(cls, START, END):
            for s, c in classes(inputs).items():
                if c == cls:
                    scores.append((d, s, cls, rng.normal()))
        df = pd.DataFrame(scores, columns=["date", "symbol", "asset_class", "score"])
        rows.append(bl.rank_rule_decisions(df, {cls: bl.decision_dates(cls, START, END)}))
    return pd.concat(rows, ignore_index=True)


def test_fill_is_the_next_open_never_the_signal_bar():
    inputs = market()
    friday = pd.Timestamp("2020-03-06")
    dec = pd.DataFrame({"date": [friday], "symbol": ["SPY"], "weight": [0.5]})
    res = run_backtest(dec, inputs, BacktestConfig(costs=FREE, taxes=NO_TAX))
    trade = res.trades.iloc[0]
    monday = pd.Timestamp("2020-03-09")
    assert trade["date"] == monday
    assert trade["price_krw"] == pytest.approx(inputs.bars["SPY"].loc[monday, "open"] * FX)
    assert res.positions.loc[:friday, "SPY"].eq(0).all()

    sunday = pd.Timestamp("2020-03-08")
    dec = pd.DataFrame({"date": [sunday], "symbol": ["BTC-USD"], "weight": [0.5]})
    res = run_backtest(dec, inputs, BacktestConfig(costs=FREE, taxes=NO_TAX))
    trade = res.trades.iloc[0]
    assert trade["date"] == pd.Timestamp("2020-03-09")
    assert trade["price_krw"] == pytest.approx(inputs.bars["BTC-USD"].loc[monday, "open"] * FX)


def test_position_on_bar_t_depends_only_on_signals_before_t():
    inputs = market()
    base = random_decisions(inputs, seed=1)
    cut = pd.Timestamp("2020-06-15")
    other = random_decisions(inputs, seed=2)
    changed = pd.concat([base[base["date"] < cut], other[other["date"] >= cut]])
    cfg = BacktestConfig(liquidate_at_end=False)
    a = run_backtest(base, inputs, cfg, start=START, end=END)
    b = run_backtest(changed, inputs, cfg, start=START, end=END)
    # A decision dated `cut` fills on the next bar at the earliest: day `cut` is untouched.
    pd.testing.assert_frame_equal(a.positions.loc[:cut], b.positions.loc[:cut])
    pd.testing.assert_series_equal(a.equity.loc[:cut], b.equity.loc[:cut])
    assert not a.positions.loc[cut + pd.Timedelta(days=7) :].equals(
        b.positions.loc[cut + pd.Timedelta(days=7) :]
    )


def test_strategy_with_baseline_weights_is_the_baseline():
    inputs = market()
    cfg = BacktestConfig()
    base = bl.run_buy_and_hold(bl.BASELINE_1, inputs, cfg, START, END)
    same = bl.buy_and_hold_decisions(bl.BASELINE_1, START, END)
    strat = run_backtest(same, inputs, cfg, start=START, end=END)
    pd.testing.assert_series_equal(base.equity, strat.equity)
    assert base.costs_krw == strat.costs_krw and base.taxes_krw == strat.taxes_krw
    summary = summarize(strat, {"baseline_1": base}, limits=RiskLimits())
    assert summary["excess_vs_baseline_1"]["cumulative"] == 0.0


def test_random_signals_do_not_beat_the_baseline():
    inputs = market(seed=7)
    cfg = BacktestConfig()
    base = bl.run_buy_and_hold(bl.BASELINE_1, inputs, cfg, START, END)
    pvals = []
    for seed in range(3):
        strat = run_backtest(random_decisions(inputs, seed), inputs, cfg, start=START, end=END)
        test = excess_return_test(strat.returns, base.returns, n_boot=300)
        pvals.append(test.p_value)
        vol = bl.run_buy_and_hold(
            {s: w * 0.5 for s, w in bl.BASELINE_1.items()}, inputs, cfg, START, END
        )
        verdict = adoption_gate(
            strat, base, base, vol, edge_share=1.0, limits=RiskLimits(), seed=seed
        )
        assert verdict.status == "rejected"
        # Costs alone push a random strategy below the baseline, never above it.
        assert test.mean_daily < 2e-4
    assert min(pvals) > 0.05


def test_leverage_and_short_selling_are_refused():
    inputs = market()
    day = pd.Timestamp("2020-03-06")
    over = pd.DataFrame({"date": [day, day], "symbol": ["SPY", "S1"], "weight": [0.7, 0.5]})
    with pytest.raises(LeverageError):
        run_backtest(over, inputs)
    short = pd.DataFrame({"date": [day], "symbol": ["SPY"], "weight": [-0.1]})
    with pytest.raises(LeverageError):
        run_backtest(short, inputs)
    nan = pd.DataFrame({"date": [day], "symbol": ["SPY"], "weight": [np.nan]})
    with pytest.raises(LeverageError):
        run_backtest(nan, inputs)


def test_risk_caps_from_risk_module_bind_in_the_backtest():
    inputs = market()
    day = pd.Timestamp("2020-03-06")
    dec = pd.DataFrame({"date": [day], "symbol": ["SPY"], "weight": [0.9]})
    limits = RiskLimits(max_order_fraction=0.05, max_position_weight=0.2)
    res = run_backtest(dec, inputs, BacktestConfig(costs=FREE, taxes=NO_TAX), limits=limits)
    trade = res.trades.iloc[0]
    assert trade["status"] == "clipped"
    assert trade["notional"] == pytest.approx(0.05 * 100_000_000)
    # Without limits (baselines) only cash binds.
    res = run_backtest(dec, inputs, BacktestConfig(costs=FREE, taxes=NO_TAX))
    assert res.trades.iloc[0]["notional"] == pytest.approx(0.9 * 100_000_000)


def _one_stock(prices: dict[str, float]) -> BacktestInputs:
    sessions = pd.DatetimeIndex(expected_dates("SPY", START, END))
    s = pd.Series(np.nan, index=sessions)
    for d, p in prices.items():
        s[pd.Timestamp(d)] = p
    s = s.ffill().bfill()
    bars = {"SPY": pd.DataFrame({"open": s, "close": s})}
    fx = pd.Series(FX, index=pd.date_range(pd.Timestamp(START) - pd.Timedelta(days=1), END))
    return BacktestInputs(bars, fx, {"SPY": instrument("SPY", "stock")})


def test_taxes_net_within_a_year_with_deduction_and_no_carry_forward():
    # 2019: buy at 100, sell at 90 (loss). 2020: buy at 100, sell at 110 (gain).
    inputs = _one_stock(
        {
            "2019-01-02": 100,
            "2019-06-03": 90,
            "2019-07-01": 100,
            "2020-01-02": 100,
            "2020-06-01": 110,
            "2020-07-01": 100,
        }  # fmt: skip
    )
    dec = pd.DataFrame(
        {
            "date": pd.to_datetime(["2019-01-01", "2019-05-31", "2019-12-31", "2020-05-29"]),
            "symbol": ["SPY"] * 4,
            "weight": [1.0, 0.0, 1.0, 0.0],
        }
    )
    cfg = BacktestConfig(costs=FREE, liquidate_at_end=False)
    res = run_backtest(dec, inputs, cfg, start=START, end=date(2020, 12, 31))
    capital = 100_000_000
    assert res.tax_by_year[2019] == 0.0  # a loss: no tax, and nothing carried to 2020
    after_loss = capital * 0.9
    gain_2020 = after_loss * 0.1
    assert res.tax_by_year[2020] == pytest.approx((gain_2020 - 2_500_000) * 0.22)
    assert res.equity.iloc[-1] == pytest.approx(after_loss * 1.1 - res.tax_by_year[2020])


def test_gains_and_losses_of_different_stocks_net_in_one_year():
    sessions = pd.DatetimeIndex(expected_dates("SPY", START, END))
    up = pd.Series(100.0, index=sessions)
    up[sessions >= "2019-06-03"] = 150.0
    down = pd.Series(100.0, index=sessions)
    down[sessions >= "2019-06-03"] = 80.0
    bars = {
        "A": pd.DataFrame({"open": up, "close": up}),
        "B": pd.DataFrame({"open": down, "close": down}),
    }
    fx = pd.Series(FX, index=pd.date_range(pd.Timestamp(START) - pd.Timedelta(days=1), END))
    inputs = BacktestInputs(bars, fx, {s: instrument(s, "stock") for s in bars})
    dec = pd.DataFrame(
        {
            "date": pd.to_datetime(["2019-01-01"] * 2 + ["2019-07-01"] * 2),
            "symbol": ["A", "B", "A", "B"],
            "weight": [0.5, 0.5, 0.0, 0.0],
        }
    )
    cfg = BacktestConfig(costs=FREE, liquidate_at_end=False)
    res = run_backtest(dec, inputs, cfg, start=START, end=date(2019, 12, 31))
    net = 50_000_000 * 0.5 - 50_000_000 * 0.2
    assert res.tax_by_year[2019] == pytest.approx((net - 2_500_000) * 0.22)


def test_coin_gains_are_taxed_only_from_the_start_date():
    days = pd.date_range(START, END, freq="D")
    p = pd.Series(100.0, index=days)
    p[days >= "2020-06-01"] = 200.0
    bars = {"BTC-USD": pd.DataFrame({"open": p, "close": p})}
    fx = pd.Series(FX, index=pd.date_range(pd.Timestamp(START) - pd.Timedelta(days=1), END))
    inputs = BacktestInputs(bars, fx, {"BTC-USD": instrument("BTC-USD", "crypto")})
    dec = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-01", "2020-07-01"]),
            "symbol": ["BTC-USD"] * 2,
            "weight": [1.0, 0.0],
        }
    )
    later = BacktestConfig(costs=FREE, taxes=TaxModel(crypto_tax_start=date(2027, 1, 1)))
    res = run_backtest(dec, inputs, later, start=date(2020, 1, 1), end=date(2020, 12, 31))
    assert res.taxes_krw == 0.0
    assert res.untaxed_crypto_gains_krw == pytest.approx(100_000_000)
    now = BacktestConfig(costs=FREE, taxes=TaxModel(crypto_tax_start=date(2020, 1, 1)))
    res = run_backtest(dec, inputs, now, start=date(2020, 1, 1), end=date(2020, 12, 31))
    assert res.taxes_krw == pytest.approx((100_000_000 - 2_500_000) * 0.22)


def test_dividends_are_paid_net_of_withholding_on_the_ex_date():
    inputs = _one_stock({"2019-01-02": 100})
    ex = pd.Timestamp("2019-03-15")
    inputs = BacktestInputs(
        inputs.bars, inputs.usdkrw, inputs.instruments, {"SPY": pd.Series({ex: 2.0})}
    )
    dec = pd.DataFrame({"date": [pd.Timestamp("2019-01-01")], "symbol": ["SPY"], "weight": [1.0]})
    costs = CostModel(commission={}, slippage_bps={}, sec_fee=0.0, fx_spread=0.001)
    res = run_backtest(dec, inputs, BacktestConfig(costs=costs), end=date(2019, 6, 28))
    shares = 100_000_000 / (1.001) / (100 * FX)
    gross = shares * 2.0 * FX
    assert res.withholding_krw == pytest.approx(gross * 0.15)
    assert res.dividends_krw == pytest.approx(gross * 0.85 * 0.999)


def test_costs_charge_each_side_once():
    inputs = _one_stock({"2019-01-02": 100})
    dec = pd.DataFrame(
        {
            "date": pd.to_datetime(["2019-01-01", "2019-02-01"]),
            "symbol": ["SPY"] * 2,
            "weight": [1.0, 0.0],
        }
    )
    costs = CostModel()
    res = run_backtest(dec, inputs, BacktestConfig(costs=costs, taxes=NO_TAX), end=date(2019, 3, 1))
    buy, sell = (
        costs.rate(inputs.instruments["SPY"], "buy"),
        costs.rate(inputs.instruments["SPY"], "sell"),
    )
    bought = 100_000_000 / (1 + buy)
    assert res.equity.iloc[-1] == pytest.approx(bought * (1 - sell))
    assert costs.round_trip(inputs.instruments["SPY"]) == pytest.approx(buy + sell)


def test_upbit_sensitivity_trades_in_won_without_fx_spread():
    from app.strategy.backtest import upbit_decisions

    days = pd.date_range(START, END, freq="D")
    won = pd.Series(50_000_000.0, index=days)
    bars = {"KRW-BTC": pd.DataFrame({"open": won, "close": won})}
    inputs = BacktestInputs(
        bars, pd.Series(dtype=float), {"KRW-BTC": instrument("KRW-BTC", "crypto", upbit=True)}
    )
    dec = upbit_decisions(
        pd.DataFrame({"date": [pd.Timestamp("2020-01-01")], "symbol": ["BTC-USD"], "weight": [1]})
    )
    res = run_backtest(dec, inputs, BacktestConfig(taxes=NO_TAX), end=date(2020, 1, 10))
    rate = CostModel().rate(inputs.instruments["KRW-BTC"], "buy")
    assert rate == pytest.approx(0.0005 + 0.0005)  # Upbit fee + 5bp slippage, no FX
    assert res.trades.iloc[0]["price_krw"] == 50_000_000.0


def test_rank_rule_bands():
    d1, d2 = pd.Timestamp("2020-01-03"), pd.Timestamp("2020-01-10")
    syms = [f"S{i}" for i in range(6)]
    s1 = pd.DataFrame({"date": d1, "symbol": syms, "asset_class": "stock",
                       "score": [6, 5, 4, 3, 2, 1]})  # fmt: skip
    # S0 drops to rank 4 (inside the hold band of 4) and stays, S1 to rank 6 (sold), S5 and
    # S4 take the top two and enter.
    s2 = pd.DataFrame({"date": d2, "symbol": syms, "asset_class": "stock",
                       "score": [3, 1, 4, 2, 5, 6]})  # fmt: skip
    out = bl.rank_rule_decisions(pd.concat([s1, s2]), {"stock": pd.DatetimeIndex([d1, d2])})
    w1 = out[out["date"] == d1].set_index("symbol")["weight"]
    w2 = out[out["date"] == d2].set_index("symbol")["weight"]
    assert set(w1[w1 > 0].index) == {"S0", "S1"}
    assert w1["S0"] == pytest.approx(0.4)
    assert set(w2[w2 > 0].index) == {"S0", "S4", "S5"}
    assert w2["S4"] == pytest.approx(0.8 / 3)
    few = s1.head(2)
    out = bl.rank_rule_decisions(few, {"stock": pd.DatetimeIndex([d1])})
    assert (out["weight"] == 0).all()


def test_decision_calendar():
    fridays = bl.decision_dates("stock", date(2024, 11, 25), date(2024, 12, 31))
    # Thanksgiving week ends on a Friday half-day session; Christmas week on Friday 27th.
    assert pd.Timestamp("2024-11-29") in fridays and pd.Timestamp("2024-12-27") in fridays
    sundays = bl.decision_dates("crypto", date(2024, 12, 1), date(2024, 12, 31))
    assert (sundays.dayofweek == 6).all() and len(sundays) == 5


def test_gresearch_features_do_not_see_the_future():
    inputs = market(n_stocks=4, n_coins=3)
    panel = bl.gresearch_panel(inputs.bars, classes(inputs))
    cut = pd.Timestamp("2020-06-30")
    tampered = {s: b.copy() for s, b in inputs.bars.items()}
    for b in tampered.values():
        b.loc[b.index > cut] *= 3.0
    again = bl.gresearch_panel(tampered, classes(inputs))
    feats = [c for c in panel.columns if c not in {"date", "symbol", "asset_class", "target"}]
    a = panel[panel["date"] <= cut].set_index(["date", "symbol"])[feats]
    b = again[again["date"] <= cut].set_index(["date", "symbol"])[feats]
    pd.testing.assert_frame_equal(a, b)


def test_gresearch_baseline_runs_through_the_same_engine():
    from app.forecast.cv import PurgedWalkForward

    inputs = market(n_stocks=4, n_coins=3)
    config = bl.GResearchConfig(engine="sklearn", n_estimators=30)
    panel = bl.gresearch_panel(inputs.bars, classes(inputs), config)
    cv = PurgedWalkForward(horizon_days=9, min_train_days=365, fixed_holdout=None,
                           holdout_days=120)  # fmt: skip
    # The holdout fold is only predicted on request (after the logged look, D-007).
    assert set(bl.gresearch_oos(panel, config, cv)["segment"]) == {"walk_forward"}
    oos = bl.gresearch_oos(panel, config, cv, include_holdout=True)
    assert set(oos["segment"]) == {"walk_forward", "holdout"}
    assert oos.groupby("asset_class")["date"].min().min() >= pd.Timestamp(START) + pd.Timedelta(
        days=365
    )
    dec = bl.gresearch_decisions(oos, START, END)
    res = run_backtest(dec, inputs, BacktestConfig(), start=START, end=END)
    assert np.isfinite(res.equity).all() and res.equity.iloc[-1] > 0


def test_strategy_tests_find_a_real_advantage_and_deflate_for_trials():
    from app.forecast import metrics

    rng = np.random.default_rng(3)
    idx = pd.date_range("2018-01-01", periods=1500, freq="D")
    base = pd.Series(rng.normal(0.0003, 0.01, len(idx)), index=idx)
    better = base + pd.Series(rng.normal(0.001, 0.003, len(idx)), index=idx)
    test = excess_return_test(better, base, n_boot=500)
    assert test.hac_p < 0.001 and test.bootstrap_p < 0.01
    noise = base + pd.Series(rng.normal(0.0, 0.003, len(idx)), index=idx)
    assert excess_return_test(noise, base, n_boot=500).p_value > 0.05

    _, stat, p = metrics.sharpe_difference(better.to_numpy(), base.to_numpy(), 5)
    assert stat > 0 and p < 0.01
    _, _, p_same = metrics.sharpe_difference(base.to_numpy(), base.to_numpy(), 5)
    assert p_same >= 0.5
    _, sr0_one, p_one = metrics.deflated_sharpe(better.to_numpy(), 1)
    _, sr0_many, p_many = metrics.deflated_sharpe(better.to_numpy(), 100)
    assert sr0_one == 0.0 and sr0_many > 0 and p_many > p_one


def test_baseline_rank_rule_and_calendar_match_s1_signals():
    """Baseline ② must trade S1's rule (D-001). baselines.py keeps its own copy, written
    by the evaluator; this checks it against signals.py on the same scores."""
    from app.forecast.report import EdgeStatus
    from app.forecast.universe import strategy_symbols
    from app.strategy import s1, signals

    start, end = date(2020, 1, 1), date(2021, 6, 30)
    for cls in ("stock", "crypto"):
        for sched, freq in (("weekly", "W"), ("monthly", "M")):
            ours = [d.date() for d in bl.decision_dates(cls, start, end, freq)]
            assert ours == signals.decision_dates(sched, cls, start, end), (cls, sched)

    rng = np.random.default_rng(5)
    days = pd.date_range(start, end, freq="D")
    rows = []
    for sym, cls in strategy_symbols().items():
        p = rng.uniform(0.3, 0.7, len(days))
        rows.append(
            pd.DataFrame(
                {
                    "date": days,
                    "symbol": sym,
                    "asset_class": cls,
                    "scale": 0.02,
                    "gbdt_q10": -1.0,
                    "gbdt_q50": 0.5,  # always clears a zero hurdle
                    "gbdt_q90": 1.0,
                    "gbdt_p_up": p,
                    "climatology_p_up": 0.5,
                }
            )
        )
    oos = pd.concat(rows, ignore_index=True)
    oos = oos.drop(index=oos.sample(frac=0.05, random_state=1).index)  # some missing rows
    # Decision dates with no row at all for a class (as at the end of the walk-forward rows):
    # both rules must sell the whole class there.
    blank = {
        "stock": ["2020-06-26", "2020-07-02", "2021-03-26"],
        "crypto": ["2020-06-28", "2020-07-05", "2021-03-28"],
    }
    for cls, ds in blank.items():
        oos = oos[~((oos["asset_class"] == cls) & oos["date"].isin(pd.to_datetime(ds)))]
    oos = oos[oos["date"] <= "2021-06-10"]  # rows stop before the last decision dates
    config = s1.s1_1w({"stock": 0.0, "crypto": 0.0})
    frame = signals.signal_frame(oos, lambda *_: EdgeStatus(True, "edge"), config, start, end)
    scores = oos.assign(score=oos["gbdt_p_up"] - oos["climatology_p_up"])
    dates = {cls: bl.decision_dates(cls, start, end) for cls in ("stock", "crypto")}
    ours = bl.rank_rule_decisions(scores[["date", "symbol", "asset_class", "score"]], dates)
    for cls, when in dates.items():
        for d in when:
            theirs = frame[(frame["as_of"] == d) & (frame["asset_class"] == cls)]
            mine = ours[(ours["date"] == d) & (ours["weight"] > 0)]
            mine = mine[mine["symbol"].map(strategy_symbols()) == cls]
            assert set(mine["symbol"]) == set(theirs.loc[theirs["held_after"], "symbol"]), (cls, d)
    for ds in blank.values():
        for d in pd.to_datetime(ds):
            assert not ((ours["date"] == d) & (ours["weight"] > 0)).any()
    assert (ours[ours["date"] > "2021-06-10"]["weight"] == 0).all()
    assert (ours["weight"] > 0).sum() > 300


def test_edge_on_exactly_half_the_decision_dates_is_not_enough():
    inputs = market(seed=11)
    cfg = BacktestConfig()
    base = bl.run_buy_and_hold(bl.BASELINE_1, inputs, cfg, START, END)
    half = adoption_gate(base, base, base, base, edge_share=0.5, limits=RiskLimits())
    assert not half.checks["1_forecast_edge"]  # 50% without an edge rejects (S1 rule 1)
    ok = adoption_gate(base, base, base, base, edge_share=0.51, limits=RiskLimits())
    assert ok.checks["1_forecast_edge"]


def test_walk_forward_decisions_stop_at_the_last_out_of_sample_row():
    from app.strategy.evaluation import walk_forward_decision_end, walk_forward_window

    oos = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-09-01", "2025-09-10", "2025-10-01"]),
            "segment": ["walk_forward", "walk_forward", "holdout"],
        }
    )
    assert walk_forward_decision_end(oos) == date(2025, 9, 10)
    assert walk_forward_window(date(2017, 1, 1), date(2026, 10, 19))[1] == date(2025, 10, 18)


def test_s1_decisions_size_held_symbols_with_the_risk_rules():
    from app.strategy.assess import s1_decisions

    d = pd.Timestamp("2020-01-03")
    frame = pd.DataFrame(
        {
            "as_of": [d] * 4,
            "symbol": ["A", "B", "C", "D"],
            "asset_class": "stock",
            "held_after": np.array([True, True, False, True]),
        }
    )
    out = s1_decisions(frame, {"stock": 0.8, "crypto": 0.2}, RiskLimits())
    w = out.set_index("symbol")["weight"]
    assert w["C"] == 0.0
    # 0.8 / 3 = 0.267 is above the 20% symbol cap, so each held symbol gets 0.2.
    assert w[["A", "B", "D"]].tolist() == pytest.approx([0.2, 0.2, 0.2])
