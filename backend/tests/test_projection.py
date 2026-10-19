import numpy as np
import pytest

from app.services.projection import ProjectionParams, simulate


def run(**kwargs):
    defaults = dict(
        start_values=np.array([10_000_000.0, 5_000_000.0]),
        annual_return=np.array([0.07, 0.10]),
        annual_vol=np.array([0.18, 0.70]),
        correlation=0.3,
        contribution_weights=np.array([0.7, 0.3]),
    )
    params = kwargs.pop("params", ProjectionParams(years=10, simulations=2000))
    return simulate(params=params, **(defaults | kwargs))


def test_zero_volatility_matches_compound_interest():
    params = ProjectionParams(years=5, monthly_contribution_krw=1_000_000, inflation_pct=0)
    result = run(
        params=params,
        start_values=np.array([10_000_000.0, 0.0]),
        annual_return=np.array([0.06, 0.0]),
        annual_vol=np.array([0.0, 0.0]),
        contribution_weights=np.array([1.0, 0.0]),
    )
    g = 1.06 ** (1 / 12)
    months = 60
    expected = 10_000_000 * g**months + 1_000_000 * (g**months - 1) / (g - 1)
    final = result.years[-1]
    assert final.p10 == final.p50 == final.p90 == pytest.approx(expected, rel=1e-6)
    assert final.contributed_krw == 10_000_000 + 60 * 1_000_000


def test_same_seed_is_reproducible_and_different_seed_is_not():
    a = run(params=ProjectionParams(years=5, simulations=1000, seed=1))
    b = run(params=ProjectionParams(years=5, simulations=1000, seed=1))
    c = run(params=ProjectionParams(years=5, simulations=1000, seed=2))
    assert a.years == b.years
    assert a.years[-1].p50 != c.years[-1].p50


def test_percentiles_are_ordered_and_inflation_lowers_real_values():
    result = run(params=ProjectionParams(years=10, simulations=2000, inflation_pct=3))
    for p in result.years[1:]:
        assert p.p10 <= p.p50 <= p.p90
        assert p.p50_real < p.p50
    assert len(result.years) == 11  # year 0 .. 10


def test_expected_growth_matches_the_annual_return_on_average():
    params = ProjectionParams(years=1, simulations=20000, seed=7)
    result = run(
        params=params,
        start_values=np.array([1_000_000.0, 0.0]),
        annual_return=np.array([0.10, 0.0]),
        annual_vol=np.array([0.30, 0.0]),
    )
    assert result.final_mean == pytest.approx(1_100_000, rel=0.01)


def test_target_probability():
    params = ProjectionParams(years=1, simulations=2000, target_krw=1.0)
    assert run(params=params).prob_target == 100.0


def test_projection_api(client, provider):
    client.post(
        "/api/transactions",
        json={
            "asset_type": "stock",
            "symbol": "AAPL",
            "side": "buy",
            "trade_date": "2026-01-05",
            "quantity": 10,
            "price": 100,
        },
    )
    a = client.get("/api/projection/assumptions").json()
    assert a["classes"]["stock"]["weight_pct"] == pytest.approx(100)
    assert a["classes"]["crypto"]["proxy"] == "BTC-USD"
    assert a["classes"]["stock"]["vol_pct"] > 0

    res = client.post(
        "/api/projection/simulate",
        json={
            "years": 3,
            "monthly_contribution_krw": 500000,
            "simulations": 500,
            "target_krw": 1e8,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert [y["year"] for y in body["years"]] == [0, 1, 2, 3]
    assert body["used_return_pct"]["stock"] == 7.0
    assert 0 <= body["prob_target"] <= 100

    assert client.post("/api/projection/simulate", json={"years": 0}).status_code == 422
