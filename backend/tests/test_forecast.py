"""The forecasting engine on synthetic data, where the truth is known.

Canaries: features must not see the future; a random walk must not produce an "edge";
shuffled labels must have no skill; a planted signal must be found.
"""

import numpy as np
import pandas as pd
import pytest

from app.forecast import metrics
from app.forecast.cv import PurgedWalkForward
from app.forecast.models import Climatology, EwmaStudentT, PooledGBDT
from app.forecast.panel import (
    HORIZON_DAYS,
    AssetSeries,
    ContextSeries,
    asset_features,
    asset_targets,
    build_panel,
    feature_columns,
)
from app.forecast.report import compare, score, verdicts
from app.forecast.walkforward import walk_forward

START = "2019-01-01"
END = "2023-06-30"


def synth_bars(seed: int, calendar: str, ar: float = 0.0, vol: float = 0.02) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(START, END, freq="D" if calendar == "crypto" else "B")
    n = len(dates)
    # Volatility regimes, so there is something real for range forecasts to learn.
    sigma = vol * np.exp(np.cumsum(rng.normal(0, 0.05, n)).clip(-1, 1))
    eps = rng.standard_t(5, n) * sigma / np.sqrt(5 / 3)
    r = np.empty(n)
    r[0] = eps[0]
    for t in range(1, n):
        r[t] = ar * r[t - 1] / sigma[t - 1] * sigma[t] + eps[t]
    close = 100 * np.exp(np.cumsum(r))
    open_ = np.r_[close[0], close[:-1]]
    wiggle = np.abs(rng.normal(0, 0.5, n)) * sigma
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) * np.exp(wiggle),
            "low": np.minimum(open_, close) * np.exp(-wiggle),
            "close": close,
            "adj_close": close,
            "volume": rng.lognormal(10, 0.3, n),
        },
        index=dates.date,
    )


def synth_panel(ar: float = 0.0) -> pd.DataFrame:
    assets = {f"S{i}": AssetSeries("stock", synth_bars(i, "stock", ar)) for i in range(8)}
    assets |= {
        f"C{i}": AssetSeries("crypto", synth_bars(100 + i, "crypto", ar, 0.04)) for i in range(4)
    }
    spy = synth_bars(200, "stock", vol=0.01)
    context = [ContextSeries("spy", spy, {"stock": 0, "crypto": 0})]
    return build_panel(assets, context, benchmarks={"stock": spy["close"]})


CV = PurgedWalkForward(horizon_days=HORIZON_DAYS["1d"], min_train_days=730, holdout_days=300)


def factories(panel: pd.DataFrame):
    feats = feature_columns(panel)
    return {
        "climatology": Climatology,
        "ewma_t": EwmaStudentT,
        "gbdt": lambda: PooledGBDT(feats, engine="sklearn", n_estimators=60),
    }


def run(panel: pd.DataFrame):
    oos = walk_forward(panel, "1d", factories(panel), CV)
    comps = verdicts(
        {
            "direction": compare(oos, "gbdt", "climatology", "brier", lags=4),
            "range": compare(oos, "gbdt", "ewma_t", "interval", lags=4),
        }
    )
    return oos, comps


def test_features_never_see_the_future():
    bars = synth_bars(1, "stock")
    cut = 600
    full = asset_features(bars)
    tampered = bars.copy()
    tampered.iloc[cut + 1 :] *= 3.0  # rewrite everything after row `cut`
    past_only = asset_features(tampered)
    pd.testing.assert_frame_equal(full.iloc[: cut + 1], past_only.iloc[: cut + 1])


def test_targets_are_forward_returns_over_known_volatility():
    bars = synth_bars(2, "crypto")
    t = asset_targets(bars, "crypto")
    p = np.log(bars["adj_close"].to_numpy())
    assert t["fr_1w"].iloc[100] == pytest.approx(p[107] - p[100])  # 7 coin days
    assert np.isnan(t["fr_1w"].iloc[-1])
    assert t["y_1w"].iloc[100] == pytest.approx(t["fr_1w"].iloc[100] / t["scale_1w"].iloc[100])


def test_folds_are_purged_and_leave_the_holdout_alone():
    dates = pd.Series(pd.date_range(START, END, freq="D"))
    cv = PurgedWalkForward(horizon_days=32, holdout_days=365)
    folds = list(cv.folds(dates))
    assert folds
    holdout = cv.holdout(dates)
    for prev, f in zip(folds, folds[1:], strict=False):
        assert f.test_start == prev.test_end
    for f in folds:
        assert f.train_end <= f.test_start - pd.Timedelta(days=32 + 5)
        assert f.test_end <= holdout.test_start
    assert holdout.train_end <= holdout.test_start - pd.Timedelta(days=37)


def test_stock_rows_see_coin_context_one_day_late():
    days = pd.date_range("2020-01-01", "2020-03-31", freq="D")
    marker = pd.DataFrame({"close": np.arange(1, len(days) + 1, dtype=float)}, index=days.date)
    ctx = ContextSeries("btc", marker, {"stock": 1, "crypto": 0}, kind="level")
    panel = build_panel(
        {
            "S": AssetSeries("stock", synth_bars(3, "stock").loc[days[0].date() : days[-1].date()]),
            "C": AssetSeries(
                "crypto", synth_bars(4, "crypto").loc[days[0].date() : days[-1].date()]
            ),
        },
        [ctx],
    )
    row = panel[(panel["symbol"] == "S") & (panel["date"] == "2020-02-14")].iloc[0]
    coin = panel[(panel["symbol"] == "C") & (panel["date"] == "2020-02-14")].iloc[0]
    day = (pd.Timestamp("2020-02-14") - days[0]).days + 1
    assert coin["btc"] == day  # same-day coin data is known when a coin's day closes
    assert row["btc"] == day - 1  # but not yet at the US close


def test_random_walk_has_no_edge_and_calibrated_ranges():
    oos, comps = run(synth_panel(ar=0.0))
    assert not comps["direction"].edge
    wf = oos[oos["segment"] == "walk_forward"]
    cov = score(wf, "gbdt", lags=4).coverage
    assert 0.72 <= cov <= 0.88


def test_planted_signal_is_detected():
    oos, comps = run(synth_panel(ar=0.35))
    assert comps["direction"].edge, comps["direction"]
    assert score(oos, "gbdt", lags=4).ic > 0.1


def test_shuffled_labels_have_no_skill():
    panel = synth_panel(ar=0.35)
    rng = np.random.default_rng(0)
    for col in ("y_1d", "fr_1d"):
        panel[col] = rng.permutation(panel[col].to_numpy())
    oos, comps = run(panel)
    assert not comps["direction"].edge
    assert abs(score(oos, "gbdt", lags=4).ic) < 0.05


def test_metric_sanity():
    assert metrics.kupiec(20, 100, 0.2) == pytest.approx(1.0)
    assert metrics.kupiec(40, 100, 0.2) < 0.001
    base, model = np.ones(200), np.full(200, 0.9)
    assert (
        metrics.diebold_mariano(base + np.random.default_rng(0).normal(0, 0.1, 200), model, 1)[1]
        < 0.01
    )
    adj = metrics.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adj == {"a": 0.03, "c": 0.06, "b": 0.06}
