from datetime import date

import numpy as np
import pytest

from app.data.fake_provider import FakeProvider
from app.deps import get_artifacts_dir
from app.ml.artifacts import TrainConfig
from app.ml.dataset import feature_frame, prepare, split_bounds
from app.ml.evaluate import evaluate
from app.ml.features import FEATURES, add_features, bars_to_frame
from app.ml.train import train_model
from app.services.predictions import future_dates
from tests.conftest import TODAY

LOOKBACK, HORIZON = 30, 5
SMALL = TrainConfig(lookback=LOOKBACK, horizon=HORIZON, hidden=8, layers=1, epochs=3, patience=2)


@pytest.fixture(scope="module")
def frame():
    bars = FakeProvider(today=TODAY).get_history("AAPL", date(2022, 1, 1), TODAY)
    return bars_to_frame(bars)


def test_targets_are_future_cumulative_log_returns(frame):
    f = feature_frame(frame, HORIZON)
    t = 100
    p = frame["adj_close"].loc[f.index]
    expected = np.log(p.iloc[t + 3] / p.iloc[t])
    assert f["y_3"].iloc[t] == pytest.approx(expected)
    assert f["y_1"].iloc[-1:].isna().all()
    assert not f[FEATURES].isna().any().any()


def test_features_do_not_use_future_rows(frame):
    full = add_features(frame)
    truncated = add_features(frame.iloc[:300])
    # Row 299 must be identical whether or not later rows exist.
    np.testing.assert_allclose(full.iloc[299].to_numpy(), truncated.iloc[299].to_numpy())


def test_splits_are_chronological_and_purged():
    train, val, test = split_bounds(1000, LOOKBACK, HORIZON, 0.15, 0.15)
    assert train[-1] + HORIZON < val[0]
    assert val[-1] + HORIZON < test[0]
    assert test[-1] + HORIZON <= 999


def test_scaler_is_fit_on_training_rows_only(frame):
    data = prepare(frame, LOOKBACK, HORIZON)
    altered = frame.copy()
    # Wildly change everything from the validation period on; train-fitted scalers must not move.
    # (Training targets legitimately reach `horizon` rows past the last training window; the
    # purge gap keeps those rows before the first validation window.)
    cutoff = data.val.dates[0]
    altered.loc[altered.index >= cutoff, ["adj_close", "close", "high", "low"]] *= 10
    altered_data = prepare(altered, LOOKBACK, HORIZON)
    np.testing.assert_allclose(data.x_scaler.mean, altered_data.x_scaler.mean)
    np.testing.assert_allclose(data.y_scaler.std, altered_data.y_scaler.std)


def test_evaluate_baseline_has_zero_error_when_prices_do_not_move():
    base = np.array([100.0, 100.0])
    y_true = np.zeros((2, 2))
    metrics = evaluate(base, y_true, np.full((2, 2), 0.01), train_up_ratio=0.6)
    day1 = metrics["by_horizon"][0]
    assert day1["baseline"]["mae"] == 0
    assert day1["model"]["mae"] == pytest.approx(100 * (np.exp(0.01) - 1))


def test_future_dates_skip_weekends_for_stocks_only():
    friday = date(2026, 10, 16)
    assert future_dates(friday, 2, every_day=False) == [date(2026, 10, 19), date(2026, 10, 20)]
    assert future_dates(friday, 2, every_day=True) == [date(2026, 10, 17), date(2026, 10, 18)]


def test_train_smoke_and_prediction_api(tmp_path, client, provider):
    client.app.dependency_overrides[get_artifacts_dir] = lambda: tmp_path

    assert client.get("/api/predictions/AAPL").status_code == 404

    bars = provider.get_history("AAPL", date(2022, 1, 1), TODAY)
    metrics = train_model("AAPL", bars, SMALL, tmp_path, log=lambda _: None)
    assert len(metrics["by_horizon"]) == HORIZON

    res = client.get("/api/predictions/aapl")
    assert res.status_code == 200
    body = res.json()
    assert len(body["forecast"]) == HORIZON
    assert all(p["price"] > 0 for p in body["forecast"])
    assert body["metrics"]["by_horizon"][0]["baseline"]["mae"] > 0

    backtest = client.get("/api/predictions/AAPL/backtest").json()
    assert len(backtest) == metrics["samples"]
    assert [m["symbol"] for m in client.get("/api/predictions").json()] == ["AAPL"]
