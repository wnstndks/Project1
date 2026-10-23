"""The pooled forecaster end to end on the fake provider: train, serve, aggregate."""

from datetime import date

import numpy as np
import pytest
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data.fake_provider import FakeProvider
from app.db.base import Base
from app.db.session import make_engine
from app.deps import get_artifacts_dir
from app.forecast import aggregate, universe
from app.forecast.data import load_inputs
from app.forecast.train import train
from app.services import forecasts
from app.services.market_data import MarketDataService, QuoteCache
from tests.conftest import TODAY


@pytest.fixture(autouse=True)
def _fresh_caches():
    forecasts._runs.clear()
    forecasts._inference.clear()


@pytest.fixture
def artifacts(client, tmp_path):
    client.app.dependency_overrides[get_artifacts_dir] = lambda: tmp_path
    return tmp_path


def buy(client, symbol, qty, price, asset_type="stock", currency="USD"):
    res = client.post(
        "/api/transactions",
        json={
            "asset_type": asset_type,
            "symbol": symbol,
            "side": "buy",
            "trade_date": "2026-01-05",
            "quantity": qty,
            "price": price,
            "currency": currency,
        },
    )
    assert res.status_code == 201, res.text


HELD = [("AAPL", "stock"), ("BTC-USD", "crypto")]


@pytest.fixture(scope="module")
def trained_dir(tmp_path_factory):
    """Train once for the module, on its own database: training is the slow part."""
    mp = pytest.MonkeyPatch()
    # A small universe and few, long folds keep this quick.
    mp.setattr(universe, "INDEX_ETFS", ["SPY"])
    mp.setattr(universe, "SECTOR_ETFS", ["XLK", "XLE"])
    mp.setattr(universe, "LARGE_CAPS", ["MSFT", "JPM", "XOM"])
    mp.setattr(universe, "COINS", ["BTC-USD", "ETH-USD", "SOL-USD"])
    mp.setattr(universe, "FALLEN_COINS", [])
    engine = make_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    out = tmp_path_factory.mktemp("artifacts")
    with sessionmaker(bind=engine)() as db:
        market = MarketDataService(db, FakeProvider(today=TODAY), QuoteCache())
        inputs = load_inputs(market, HELD, start=date(2022, 6, 1))
    train(
        inputs,
        [s for s, _ in HELD],
        out,
        engine="sklearn",
        cv_options={"min_train_days": 365, "test_days": 400, "holdout_days": 180},
        n_estimators=30,
        log=lambda _: None,
    )
    yield out
    mp.undo()
    engine.dispose()


@pytest.fixture
def trained(client, trained_dir):
    client.app.dependency_overrides[get_artifacts_dir] = lambda: trained_dir
    buy(client, "AAPL", 10, 150)
    buy(client, "BTC", "0.01", "100000000", asset_type="crypto", currency="KRW")


def test_untrained_status_and_forecast(client, artifacts):
    assert client.get("/api/forecasts/status").json()["trained"] is False
    res = client.get("/api/forecasts/AAPL")
    assert res.status_code == 404


def test_symbol_forecast_has_ordered_ranges_and_verdicts(client, trained):
    status = client.get("/api/forecasts/status").json()
    assert status["trained"] and set(status["report"]["horizons"]) == {"1d", "1w", "1m"}

    body = client.get("/api/forecasts/AAPL").json()
    assert [h["horizon"] for h in body["horizons"]] == ["1d", "1w", "1m"]
    for h in body["horizons"]:
        assert h["p10"] <= h["p50"] <= h["p90"]
        assert 0 <= h["p_up"] <= 1
        assert h["target_date"] > h["as_of"]
        assert isinstance(h["direction_edge"], bool)
        assert h["direction_reason"] in {"edge", "not_significant", "no_data"}
        # A range edge is never live before its forward paper test (D-006). The reason says
        # whether the walk-forward found one to wait for (ISSUE-037, D-028).
        comp = status["report"]["horizons"][h["horizon"]]["comparisons"]["stock:range"]
        assert h["range_edge"] is False
        assert h["range_reason"] == ("forward_test_pending" if comp["edge"] else "not_significant")
    week = body["horizons"][1]
    # Five NYSE sessions after a Friday close is the next Friday.
    assert (date.fromisoformat(week["target_date"]) - date.fromisoformat(week["as_of"])).days == 7

    coin = client.get("/api/forecasts/BTC").json()
    assert coin["symbol"] == "BTC-USD"
    month = coin["horizons"][2]
    assert (
        date.fromisoformat(month["target_date"]) - date.fromisoformat(month["as_of"])
    ).days == 30


def test_unheld_symbol_is_not_forecast(client, trained):
    assert client.get("/api/forecasts/MSFT").status_code == 404


def test_portfolio_forecast_brackets_current_value(client, trained):
    body = client.get("/api/forecasts/portfolio").json()
    total = client.get("/api/portfolio/summary").json()["market_value_krw"]
    for h in body["horizons"]:
        assert h["value_krw"] == pytest.approx(total, rel=1e-6)
        assert h["p10"] < h["p50"] < h["p90"]
        assert h["var95"] >= 0 and h["es95"] >= h["var95"]
    widths = [h["p90"] - h["p10"] for h in body["horizons"]]
    assert widths[0] < widths[2]  # a month is more uncertain than a day


def test_backtest_points_cover_walk_forward_and_holdout(client, trained):
    points = client.get("/api/forecasts/AAPL/backtest?horizon=1w").json()
    assert {p["segment"] for p in points} == {"walk_forward", "holdout"}
    assert all(p["q10"] <= p["q90"] for p in points)


def test_aggregation_respects_correlation_and_seed():
    a = aggregate.AssetForecast("A", 1_000_000, -0.1, 0.0, 0.1)
    b = aggregate.AssetForecast("B", 1_000_000, -0.1, 0.0, 0.1)
    fx = aggregate.AssetForecast(aggregate.FX, 0, -1e-9, 0.0, 1e-9)
    together = np.array([[1, 0.999, 0], [0.999, 1, 0], [0, 0, 1]])
    apart = np.eye(3)
    joint = aggregate.simulate([a, b], fx, together, seed=1)
    indep = aggregate.simulate([a, b], fx, apart, seed=1)
    # Diversification narrows the range; perfectly correlated assets do not diversify.
    assert (indep.p90 - indep.p10) < (joint.p90 - joint.p10)
    assert aggregate.simulate([a, b], fx, apart, seed=1) == indep
    # A single asset's 10% quantile carries through.
    one = aggregate.simulate([a], fx, np.eye(2), paths=40_000, seed=2)
    assert one.p10 == pytest.approx(1_000_000 * np.exp(-0.1), rel=0.01)


def test_live_forecasts_are_logged_once_and_scored_later(client, trained, db):
    from sqlalchemy import func, select

    from app.db.models import ForecastLog

    client.get("/api/forecasts/AAPL")
    forecasts._inference.clear()
    client.get("/api/forecasts/AAPL")  # recomputed, but the first forecast is kept
    assert db.scalar(select(func.count()).select_from(ForecastLog)) == 6  # 2 symbols x 3

    # Pretend one forecast was made a month ago, so its target date has passed.
    row = db.scalar(
        select(ForecastLog).where(ForecastLog.symbol == "AAPL", ForecastLog.horizon == "1w")
    )
    row.as_of, row.target_date = date(2026, 9, 1), date(2026, 9, 8)
    row.q10, row.q90, row.p_up = -1.0, 1.0, 0.9
    db.commit()

    body = client.get("/api/forecasts/track-record?symbol=AAPL").json()
    week = next(s for s in body["summary"] if s["horizon"] == "1w")
    assert week["scored"] == 1 and week["coverage"] == 1.0
    assert body["recent"][0]["as_of"] == "2026-09-01"
    assert body["pending"] == 2  # the 1d and 1m forecasts are not due yet


def test_untrained_error_has_a_machine_readable_code(client, artifacts):
    assert client.get("/api/forecasts/AAPL").json()["code"] == "not_trained"


def test_upbit_coins_carry_the_kimchi_premium(client, trained):
    body = client.get("/api/forecasts/portfolio").json()
    assert "BTC-USD" in body["kimchi_premium"]
    coin = client.get("/api/forecasts/BTC").json()
    assert coin["krw_rate"] and coin["krw_rate"] > 0
    assert client.get("/api/forecasts/AAPL").json()["krw_rate"] is None  # a USD stock


def test_held_symbol_without_enough_history_says_so(client, trained, monkeypatch):
    real = forecasts.load_inputs

    def without_msft(*args, **kwargs):
        inputs = real(*args, **kwargs)
        inputs.assets.pop("MSFT", None)
        return inputs

    monkeypatch.setattr(forecasts, "load_inputs", without_msft)
    buy(client, "MSFT", 1, 400)
    res = client.get("/api/forecasts/MSFT")
    assert res.status_code == 422 and res.json()["code"] == "insufficient_history"
    # The bulk list leaves it out instead of failing for everyone.
    assert [h["symbol"] for h in client.get("/api/forecasts/held").json()] == ["AAPL", "BTC-USD"]


def test_premium_reverts_toward_its_mean():
    model = aggregate.PremiumModel(mu=0.01, phi=0.9, sigma=0.005)
    mean, sd = model.horizon(current=0.08, days=30)
    assert mean == pytest.approx((0.01 - 0.08) * (1 - 0.9**30))
    assert 0 < sd < 0.005 * np.sqrt(30)
    a = aggregate.AssetForecast("BTC-USD", 1_000_000, -0.1, 0.0, 0.1)
    fx = aggregate.AssetForecast(aggregate.FX, 0, -1e-9, 0.0, 1e-9)
    plain = aggregate.simulate([a], fx, np.eye(2), seed=3)
    with_premium = aggregate.simulate([a], fx, np.eye(2), seed=3, premium={"BTC-USD": (mean, sd)})
    assert with_premium.p50 < plain.p50  # a high premium is expected to shrink


def test_edges_follow_the_live_verdict_per_asset_class(client, trained, trained_dir):
    client.get("/api/forecasts/AAPL")  # loads the run so its report can be edited in place
    report = forecasts._runs[trained_dir].report
    comparisons = report["horizons"]["1d"]["comparisons"]
    assert {"stock:direction", "stock:range", "crypto:direction"} <= set(comparisons)
    comparisons["stock:direction"]["edge"] = True
    comparisons["stock:range"]["edge"] = True
    comparisons["crypto:direction"]["edge"] = False

    day = client.get("/api/forecasts/AAPL").json()["horizons"][0]
    assert day["horizon"] == "1d"
    assert day["direction_edge"] is True and day["direction_reason"] == "edge"
    # A range edge in the report is still withheld until its forward test confirms it.
    assert day["range_edge"] is False and day["range_reason"] == "forward_test_pending"

    # The coin reads the crypto comparison, not the stock one.
    coin_day = client.get("/api/forecasts/BTC").json()["horizons"][0]
    assert coin_day["direction_edge"] is False
    assert coin_day["direction_reason"] == "not_significant"


def test_status_live_verdicts_are_the_symbol_forecasts_verdicts(client, trained, trained_dir):
    from app.forecast.report import live_edge_at

    status = client.get("/api/forecasts/status").json()
    assert set(status["live"]) == {"stock", "crypto"}
    assert all(set(by_h) == {"1d", "1w", "1m"} for by_h in status["live"].values())
    report = forecasts._runs[trained_dir].report
    for cls in ("stock", "crypto"):
        for h in ("1d", "1w", "1m"):
            assert status["live"][cls][h] == {
                "direction": live_edge_at(report, "direction")(TODAY, cls, h).reason,
                "range": live_edge_at(report, "range")(TODAY, cls, h).reason,
            }
    # The detail page's badges and the home's model sentence read the same verdict.
    for h in client.get("/api/forecasts/AAPL").json()["horizons"]:
        assert status["live"]["stock"][h["horizon"]] == {
            "direction": h["direction_reason"],
            "range": h["range_reason"],
        }

    comparisons = report["horizons"]["1d"]["comparisons"]
    comparisons["stock:direction"]["edge"] = True
    comparisons["stock:range"]["edge"] = True
    live = client.get("/api/forecasts/status").json()["live"]["stock"]["1d"]
    assert live["direction"] == "edge"
    # The report's raw range flag is not the live verdict: the forward test comes first.
    assert live["range"] == "forward_test_pending"
    assert client.get("/api/forecasts/AAPL").json()["horizons"][0]["direction_reason"] == "edge"


def test_untrained_status_has_no_live_verdicts_and_no_held_list(client, artifacts):
    body = client.get("/api/forecasts/status").json()
    assert body["trained"] is False and body["live"] == {}
    res = client.get("/api/forecasts/held")
    assert res.status_code == 404 and res.json()["code"] == "not_trained"


def test_held_forecasts_list_every_held_symbol_once_as_ratios(client, trained):
    body = client.get("/api/forecasts/held").json()
    # Sorted by symbol, holdings only: MSFT is in the reference universe but not held.
    assert [(h["symbol"], h["asset_class"]) for h in body] == [
        ("AAPL", "stock"),
        ("BTC-USD", "crypto"),
    ]
    single = client.get("/api/forecasts/AAPL").json()
    horizons = body[0]["horizons"]
    assert [h["horizon"] for h in horizons] == ["1d", "1w", "1m"]
    for mine, theirs in zip(horizons, single["horizons"], strict=True):
        base = theirs["base_price"]
        assert mine["low_ratio"] == pytest.approx(theirs["p10"] / base)
        assert mine["mid_ratio"] == pytest.approx(theirs["p50"] / base)
        assert mine["high_ratio"] == pytest.approx(theirs["p90"] / base)
        assert mine["low_ratio"] <= mine["mid_ratio"] <= mine["high_ratio"]
        for key in (
            "as_of",
            "target_date",
            "p_up",
            "baseline_p_up",
            "direction_edge",
            "range_edge",
            "direction_reason",
            "range_reason",
        ):
            assert mine[key] == theirs[key], key
    coin = next(h for h in body if h["symbol"] == "BTC-USD")
    assert (
        coin["horizons"][0]["direction_reason"]
        == (client.get("/api/forecasts/BTC").json()["horizons"][0]["direction_reason"])
    )


def test_inference_is_rebuilt_once_a_new_session_has_closed(client, trained, monkeypatch):
    """Regression for ISSUE-040: the 30-minute inference cache used to outlive a session
    close, so the previous session's row (and a past 1d target date) was served on."""
    computed: list = []
    real = forecasts.ForecastService._compute

    def counting(self, run, held):
        computed.append(held)
        return real(self, run, held)

    monkeypatch.setattr(forecasts.ForecastService, "_compute", counting)
    final = {"date": date(2026, 10, 15)}
    monkeypatch.setattr(forecasts, "last_final_date", lambda *_: final["date"])
    client.get("/api/forecasts/AAPL")
    client.get("/api/forecasts/held")
    assert len(computed) == 1  # within INFERENCE_TTL the cached inference is reused
    final["date"] = date(2026, 10, 16)  # the next session closed and settled
    client.get("/api/forecasts/AAPL")
    assert len(computed) == 2
