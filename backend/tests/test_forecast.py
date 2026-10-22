"""The forecasting engine on synthetic data, where the truth is known.

Canaries: features must not see the future; a random walk must not produce an "edge";
shuffled labels must have no skill; a planted signal must be found.
"""

from datetime import date

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
from app.forecast.report import KINDS, compare, score, verdicts
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


# Synthetic data ends long before the fixed production holdout: hold out its last 300 days.
CV = PurgedWalkForward(
    horizon_days=HORIZON_DAYS["1d"], min_train_days=730, holdout_days=300, fixed_holdout=None
)


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
    cv = PurgedWalkForward(horizon_days=32, holdout_days=365, fixed_holdout=None)
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


def test_latest_ranks_use_recent_peers_when_the_newest_date_is_sparse():
    from app.forecast.panel import latest_ranks

    panel = synth_panel()
    last = panel["date"].max()
    # Only one stock has a row on the newest date; its peers stop a day earlier.
    sparse = panel[(panel["date"] < last) | (panel["symbol"] == "S0")]
    row = sparse[(sparse["symbol"] == "S0") & (sparse["date"] == last)]
    fixed = latest_ranks(sparse, row)
    day_before = sparse["date"] == last - pd.Timedelta(days=1)
    peers = sparse[(sparse["asset_class"] == "stock") & day_before & (sparse["symbol"] != "S0")]
    v = row["r5"].iloc[0]
    expected = ((peers["r5"] < v).sum() + 1) / (len(peers) + 1)
    assert fixed["rank_r5"].iloc[0] == pytest.approx(expected)


class TooNarrow:
    """A forecaster whose 10-90% range is far too narrow (it covers about a quarter)."""

    name = "narrow"

    def fit(self, train, target):
        pass

    def predict(self, rows):
        n = len(rows)
        data = {"q10": [-0.3] * n, "q50": [0.0] * n, "q90": [0.3] * n, "p_up": [0.5] * n}
        return pd.DataFrame(data, index=rows.index)


def test_conformal_calibration_reaches_the_target_coverage():
    panel = synth_panel()
    oos = walk_forward(panel, "1d", {"narrow": TooNarrow}, CV)
    raw = ((oos["y"] >= oos["narrow_q10_raw"]) & (oos["y"] <= oos["narrow_q90_raw"])).mean()
    assert raw < 0.4
    # Once a full year of out-of-sample errors is available, coverage is on target.
    start = oos["date"].min() + pd.Timedelta(days=400)
    late = oos[oos["date"] >= start]
    covered = ((late["y"] >= late["narrow_q10"]) & (late["y"] <= late["narrow_q90"])).mean()
    assert covered == pytest.approx(0.8, abs=0.02)


# --- fixed holdout, its log, per-class and point-in-time edges (D-005 to D-007) ---------


def test_walk_forward_targets_stop_before_the_holdout():
    dates = pd.Series(pd.date_range(START, END, freq="D"))
    cv = PurgedWalkForward(horizon_days=32, holdout_days=365, fixed_holdout=None)
    holdout = cv.holdout(dates)
    last = list(cv.folds(dates))[-1]
    # A row dated just before test_end has a target ending before the holdout starts, even
    # a stock target stretched by holidays (21 sessions can span 35 days).
    assert last.test_end + pd.Timedelta(days=35) <= holdout.test_start


def test_holdout_start_is_fixed_while_data_grows():
    from app.forecast.cv import HOLDOUT_START

    cv = PurgedWalkForward(horizon_days=9)
    short = pd.Series(pd.date_range("2015-01-01", "2026-10-19", freq="D"))
    longer = pd.Series(pd.date_range("2015-01-01", "2027-03-01", freq="D"))
    assert cv.holdout(short).test_start == cv.holdout(longer).test_start
    assert cv.holdout(short).test_start == pd.Timestamp(HOLDOUT_START)
    assert list(cv.folds(short)) == list(cv.folds(longer))


def test_holdout_log_refuses_a_second_final_look(tmp_path):
    from app.forecast.cv import HoldoutViewError, holdout_views, open_holdout

    log = tmp_path / "holdout_log.jsonl"
    kw = dict(holdout_start="2025-10-19", path=log)
    open_holdout("strategy", "aaa", data_end="2026-10-19", configs_tried=2, **kw)
    with pytest.raises(HoldoutViewError):
        open_holdout("strategy", "aaa", data_end="2026-11-30", configs_tried=2, **kw)
    # A new configuration must come with a raised counter.
    with pytest.raises(HoldoutViewError):
        open_holdout("strategy", "bbb", data_end="2026-10-19", configs_tried=2, **kw)
    open_holdout("strategy", "bbb", data_end="2026-10-19", configs_tried=3, **kw)
    # A forecast refit on newer data with the same configuration is a new (logged) look.
    open_holdout("forecast", "f1", data_end="2026-10-19", configs_tried=3, **kw)
    with pytest.raises(HoldoutViewError):
        open_holdout("forecast", "f1", data_end="2026-10-19", configs_tried=3, **kw)
    open_holdout("forecast", "f1", data_end="2026-10-20", configs_tried=3, **kw)
    assert len(holdout_views(log)) == 4


def test_committed_holdout_log_is_consistent_with_the_counter(tmp_path):
    """Every forecast look in the committed log was made with a counter no higher than
    CONFIGS_TRIED, and the next new configuration must raise the counter again."""
    from app.forecast.cv import HOLDOUT_LOG, HoldoutViewError, holdout_views, open_holdout
    from app.forecast.report import CONFIGS_TRIED

    copy = tmp_path / "holdout_log.jsonl"  # never write to the committed log in a test
    copy.write_bytes(HOLDOUT_LOG.read_bytes())
    views = [v for v in holdout_views(copy) if v["scope"] == "forecast"]
    most = max(v["configs_tried"] for v in views)
    assert views and most <= CONFIGS_TRIED
    with pytest.raises(HoldoutViewError):
        open_holdout(
            "forecast",
            "new-hash",
            holdout_start="2025-10-19",
            data_end="2026-10-19",
            configs_tried=most,
            path=copy,
        )
    open_holdout(
        "forecast",
        "new-hash",
        holdout_start="2025-10-19",
        data_end="2026-10-19",
        configs_tried=most + 1,
        path=copy,
    )


def test_year_share_leaves_out_partial_years():
    idx = pd.date_range("2019-10-01", "2021-12-31", freq="D")
    x = pd.Series(1.0, index=idx)
    x[idx.year == 2019] = -1.0  # three months only
    x[idx.year == 2021] = -1.0
    share, years = metrics.year_share(x)
    assert years == 2 and share == 0.5


def synth_oos(signal: float, seed: int = 0, start: str = "2016-01-01", end: str = "2021-12-31"):
    """OOS rows with the columns report.py reads; `signal` sets how much p_up knows."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, end, freq="D")
    rows = []
    for cls, n in (("stock", 6), ("crypto", 4)):
        for i in range(n):
            y = rng.standard_t(5, len(dates))
            score = signal * y + rng.normal(0, 1, len(dates))
            q = rng.normal(0, 0.05, len(dates))
            rows.append(
                pd.DataFrame(
                    {
                        "date": dates,
                        "symbol": f"{cls[0].upper()}{i}",
                        "asset_class": cls,
                        "y": y,
                        "fr": y * 0.02,
                        "gbdt_p_up": 1 / (1 + np.exp(-0.3 * score)),
                        "climatology_p_up": 0.52,
                        "gbdt_q10": -1.3 + q,
                        "gbdt_q50": q,
                        "gbdt_q90": 1.3 + q,
                        "ewma_t_q10": -1.3,
                        "ewma_t_q50": 0.0,
                        "ewma_t_q90": 1.3,
                        "segment": np.where(dates >= "2021-06-01", "holdout", "walk_forward"),
                    }
                )
            )
    return pd.concat(rows, ignore_index=True)


def test_rank_comparison_is_per_class_and_finds_a_planted_ranking():
    from app.forecast.report import FAMILY_SIZE, compare_all

    planted = verdicts(compare_all(synth_oos(signal=0.4), lags=9))
    assert set(planted) == {f"{c}:{k}" for c in ("stock", "crypto") for k in KINDS}
    assert planted["stock:rank"].edge and planted["crypto:rank"].edge
    assert FAMILY_SIZE == 24
    noise = verdicts(compare_all(synth_oos(signal=0.0), lags=9))
    assert not any(c.edge for c in noise.values())


def test_point_in_time_edge_uses_only_outcomes_known_by_then():
    from app.forecast.report import PointInTimeEdge, target_end_dates

    # Five sessions from Friday 2018-12-21 end on Monday 12-31 (Christmas): 10 days, more
    # than HORIZON_DAYS["1w"]. A calendar-day cut-off would count it as known on 12-30.
    assert target_end_dates(pd.DatetimeIndex(["2018-12-21"]), "stock", "1w")[0] == (
        pd.Timestamp("2018-12-31")
    )
    oos = synth_oos(signal=0.4)
    edge = PointInTimeEdge({"1w": oos, "1m": oos})
    for as_of, horizon in ((date(2019, 6, 30), "1w"), (date(2018, 12, 30), "1w"),
                           (date(2018, 12, 31), "1m")):  # fmt: skip
        before = edge.edge_at(as_of, "stock", horizon)
        # Rewrite every outcome that was not yet known on `as_of`.
        tampered = oos.copy()
        for cls in ("stock", "crypto"):
            rows = tampered["asset_class"] == cls
            ends = target_end_dates(pd.DatetimeIndex(tampered.loc[rows, "date"]), cls, horizon)
            idx = tampered.index[rows][ends > pd.Timestamp(as_of)]
            tampered.loc[idx, ["y", "fr"]] = -tampered.loc[idx, ["y", "fr"]]
        after = PointInTimeEdge({"1w": tampered, "1m": tampered}).edge_at(as_of, "stock", horizon)
        assert before == after, (as_of, horizon)
        assert before.edge and before.reason == "edge"
        assert before.hit_rate_lower is not None and before.hit_rate_lower > 0.5
    # Too early to judge: less than two full years of known outcomes.
    early = edge.edge_at(date(2016, 9, 1), "stock", "1w")
    assert not early.edge and early.reason == "insufficient_history"


def test_point_in_time_edge_holiday_spans_on_real_sessions():
    """Regression for verifier B-1 (w2a_pit_holiday_leak.py): on S1-1m month ends next to
    holidays, rows whose 21-session target ends after the decision date must not count,
    even though they are more than 32 calendar days old."""
    from app.data.calendar import expected_dates
    from app.forecast.report import PointInTimeEdge, target_end_dates

    sessions = pd.DatetimeIndex(expected_dates("SPY", date(2014, 6, 2), date(2023, 6, 30)))
    rng = np.random.default_rng(0)
    rows = []
    for i in range(8):
        y = rng.normal(0, 1, len(sessions))
        q = rng.normal(0, 0.05, len(sessions))
        rows.append(
            pd.DataFrame(
                {
                    "date": sessions,
                    "symbol": f"E{i}",
                    "asset_class": "stock",
                    "y": y,
                    "fr": 0.01 * y,
                    "gbdt_p_up": 0.5 + 0.02 * y + rng.normal(0, 0.05, len(sessions)),
                    "climatology_p_up": 0.52,
                    "gbdt_q10": -1.3 + q,
                    "gbdt_q50": q,
                    "gbdt_q90": 1.3 + q,
                    "ewma_t_q10": -1.3,
                    "ewma_t_q50": 0.0,
                    "ewma_t_q90": 1.3,
                    "segment": "walk_forward",
                }
            )
        )
    oos = pd.concat(rows, ignore_index=True)
    edge = PointInTimeEdge({"1m": oos})
    ends = target_end_dates(pd.DatetimeIndex(oos["date"]), "stock", "1m")
    for as_of in (date(2017, 1, 31), date(2018, 12, 31), date(2023, 1, 31)):
        cut = pd.Timestamp(as_of)
        late = ends > cut
        # The holiday edge exists: rows 32+ days old whose target is still open.
        assert (late & (oos["date"] + pd.Timedelta(days=32) <= cut).to_numpy()).any(), as_of
        before = edge.edge_at(as_of, "stock", "1m")
        tampered = oos.copy()
        tampered.loc[late, ["y", "fr", "gbdt_p_up"]] = [5.0, 0.05, 0.0]
        after = PointInTimeEdge({"1m": tampered}).edge_at(as_of, "stock", "1m")
        assert before == after, as_of
        assert before.n > 0 and before.hit_rate_lower is not None


def test_point_in_time_edge_tolerates_a_class_without_rows():
    from app.forecast.report import PointInTimeEdge

    oos = synth_oos(signal=0.4)
    edge = PointInTimeEdge({"1w": oos[oos["asset_class"] == "stock"]})
    status = edge.edge_at(date(2019, 6, 30), "crypto", "1w")
    assert not status.edge and status.reason == "no_data"
    assert edge.edge_at(date(2019, 6, 30), "stock", "1w").edge


def test_point_in_time_edge_stays_off_without_skill():
    from app.forecast.report import PointInTimeEdge

    edge = PointInTimeEdge({"1w": synth_oos(signal=0.0, seed=4)})
    on = [
        edge.edge_at(d.date(), cls, "1w").edge
        for d in pd.date_range("2018-01-07", "2021-05-30", freq="4W-SUN")
        for cls in ("stock", "crypto")
    ]
    assert not any(on)


def test_live_rank_edge_waits_for_the_forward_test():
    from app.forecast.report import compare_all, live_edge_at, to_dict

    comps = verdicts(compare_all(synth_oos(signal=0.4), lags=9))
    report = {"horizons": {"1w": {"comparisons": {k: to_dict(c) for k, c in comps.items()}}}}
    status = live_edge_at(report)(date(2026, 10, 20), "stock", "1w")
    assert comps["stock:rank"].edge
    assert not status.edge and status.reason == "forward_test_pending"


def vol_oos(knows: bool, seed: int = 0, shuffle: bool = False):
    """OOS rows whose outcomes have a slowly changing volatility. With `knows`, gbdt's 10-90%
    range follows it while ewma_t's range stays at the long-run width; otherwise gbdt has
    the same width as ewma_t plus noise. The median differs between them (gbdt q50 noisy),
    so a location error cannot pass for volatility skill."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2016-01-01", "2021-12-31", freq="D")
    z90 = metrics.RANGE_TO_SIGMA / 2
    rows = []
    for cls, n in (("stock", 6), ("crypto", 4)):
        for i in range(n):
            log_sigma = np.zeros(len(dates))
            for t in range(1, len(dates)):
                log_sigma[t] = 0.98 * log_sigma[t - 1] + rng.normal(0, 0.1)
            sigma = np.exp(log_sigma)
            y = sigma * rng.standard_normal(len(dates))
            if shuffle:
                y = rng.permutation(y)
            width = sigma if knows else np.exp(rng.normal(0, 0.05, len(dates)))
            q50 = rng.normal(0, 0.2, len(dates))
            rows.append(
                pd.DataFrame(
                    {
                        "date": dates,
                        "symbol": f"{cls[0].upper()}{i}",
                        "asset_class": cls,
                        "y": y,
                        "fr": y * 0.02,
                        "gbdt_p_up": 0.5,
                        "climatology_p_up": 0.5,
                        "gbdt_q10": q50 - z90 * width,
                        "gbdt_q50": q50,
                        "gbdt_q90": q50 + z90 * width,
                        "ewma_t_q10": -z90,
                        "ewma_t_q50": 0.0,
                        "ewma_t_q90": z90,
                        "segment": np.where(dates >= "2021-06-01", "holdout", "walk_forward"),
                    }
                )
            )
    return pd.concat(rows, ignore_index=True)


def test_vol_comparison_finds_a_planted_volatility_forecast_only():
    from app.forecast.report import compare_all

    planted = verdicts(compare_all(vol_oos(knows=True), lags=5))
    assert planted["stock:vol"].edge and planted["crypto:vol"].edge
    assert planted["stock:vol"].dm_stat > 5
    noise = verdicts(compare_all(vol_oos(knows=False, seed=1), lags=5))
    assert not noise["stock:vol"].edge and not noise["crypto:vol"].edge
    # Shuffled outcomes break the link between the forecast and the volatility.
    shuffled = verdicts(compare_all(vol_oos(knows=True, seed=2, shuffle=True), lags=5))
    assert not shuffled["stock:vol"].edge and not shuffled["crypto:vol"].edge


def test_vol_loss_scores_the_width_not_the_median():
    y = np.array([0.5, -1.0, 2.0])
    lo, hi = np.array([-1.0, -2.0, -0.5]), np.array([1.0, 2.0, 1.5])
    shifted = metrics.qlike(y, metrics.implied_sigma(lo + 0.7, hi + 0.7))
    assert shifted == pytest.approx(metrics.qlike(y, metrics.implied_sigma(lo, hi)))
    # The right volatility beats a wrong one in expectation.
    rng = np.random.default_rng(0)
    draws = 2.0 * rng.standard_normal(200_000)
    assert metrics.qlike(draws, np.full(len(draws), 2.0)).mean() < (
        metrics.qlike(draws, np.full(len(draws), 1.0)).mean()
    )
    assert metrics.implied_sigma(np.array([0.0]), np.array([0.0]))[0] == metrics.MIN_SIGMA


def test_point_in_time_vol_edge_uses_only_outcomes_known_by_then():
    from app.forecast.report import PointInTimeEdge, target_end_dates

    oos = vol_oos(knows=True)
    as_of = date(2019, 6, 30)
    before = PointInTimeEdge({"1d": oos}).lookup("vol")(as_of, "stock", "1d")
    tampered = oos.copy()
    for cls in ("stock", "crypto"):
        rows = tampered["asset_class"] == cls
        ends = target_end_dates(pd.DatetimeIndex(tampered.loc[rows, "date"]), cls, "1d")
        idx = tampered.index[rows][ends > pd.Timestamp(as_of)]
        tampered.loc[idx, ["y", "fr"]] = 10 * tampered.loc[idx, ["y", "fr"]]
    after = PointInTimeEdge({"1d": tampered}).lookup("vol")(as_of, "stock", "1d")
    assert before == after
    assert before.edge and before.reason == "edge"
    assert before.hit_rate_lower is not None and before.hit_rate_lower > 0.5
    with pytest.raises(ValueError):
        PointInTimeEdge({"1d": oos}).lookup("volatility")


def test_live_range_and_vol_edges_wait_for_the_forward_test():
    from app.forecast.report import compare_all, live_edge_at, to_dict

    comps = verdicts(compare_all(vol_oos(knows=True), lags=5))
    report = {"horizons": {"1d": {"comparisons": {k: to_dict(c) for k, c in comps.items()}}}}
    assert comps["stock:vol"].edge
    for kind in ("vol", "range", "rank"):
        status = live_edge_at(report, kind=kind)(date(2026, 10, 20), "stock", "1d")
        assert not status.edge and status.reason == "forward_test_pending", kind
    # Direction is read from the report as before (no edge here).
    assert live_edge_at(report, kind="direction")(date(2026, 10, 20), "stock", "1d").reason == (
        "not_significant"
    )
