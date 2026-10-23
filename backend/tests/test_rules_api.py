"""Rule settings and rule checks over HTTP (plan G, DECISIONS.md D-027).

FakeProvider supplies quotes and bars; the artifacts directory is empty, so the forecast
reference is reported as `not_trained` rather than invented. Amounts are demo numbers.
"""

import pytest

from app.deps import get_artifacts_dir

from .test_portfolio_api import buy, krw_trade


@pytest.fixture(autouse=True)
def _no_model(client, tmp_path):
    client.app.dependency_overrides[get_artifacts_dir] = lambda: tmp_path


def settings_body(client, **over):
    """The current settings turned back into a PUT body, with numbers as strings the way
    the screen sends them."""
    current = client.get("/api/rules/settings").json()
    g = {k: str(v) if isinstance(v, float) else v for k, v in current["global"].items()}
    g.update(over)
    return {"global": g, "crypto": current["crypto"], "targets": current["targets"]}


# --- settings -------------------------------------------------------------------------------


def test_settings_default_to_config_with_the_crypto_layer(client):
    body = client.get("/api/rules/settings").json()
    assert body["global"]["cut_loss_pct"] == 15 and body["global"]["add_max_steps"] == 2
    assert body["crypto"] == {"cut_loss_pct": 25, "trailing_drop_pct": 30, "add_step_pct": 8}
    assert body["defaults"]["crypto"] == body["crypto"]
    assert body["targets"] == {} and body["warnings"] == []
    assert body["updated_at"] is None
    assert body["live_trading"] is False


def test_put_parses_strings_normalizes_symbols_and_drops_empty_overrides(client):
    body = settings_body(client, cut_loss_pct="12.5", add_max_steps=3)
    body["crypto"] = {"cut_loss_pct": "30", "trailing_drop_pct": None, "add_step_pct": None}
    body["targets"] = {
        "krw-btc": {"target_weight_pct": "10", "cut_loss_pct": None},
        "aapl": {"target_weight_pct": None},  # all empty: "use the global value"
    }
    res = client.put("/api/rules/settings", json=body)
    assert res.status_code == 200
    out = res.json()
    assert out["global"]["cut_loss_pct"] == 12.5 and out["global"]["add_max_steps"] == 3
    assert out["crypto"] == {"cut_loss_pct": 30, "trailing_drop_pct": None, "add_step_pct": None}
    assert list(out["targets"]) == ["BTC-USD"]
    assert out["targets"]["BTC-USD"]["target_weight_pct"] == 10
    assert out["updated_at"] is not None
    # Stored, not just echoed.
    again = client.get("/api/rules/settings").json()
    assert again["global"]["cut_loss_pct"] == 12.5 and "BTC-USD" in again["targets"]
    # The defaults are untouched by what the user saved.
    assert again["defaults"]["global"]["cut_loss_pct"] == 15


def test_put_warns_when_the_last_add_step_is_below_the_stop_loss(client):
    # 10% x 3 steps = -30%, below the -15% stop: legal, but the cut comes first.
    res = client.put(
        "/api/rules/settings", json=settings_body(client, add_step_pct="10", add_max_steps=3)
    )
    assert res.status_code == 200
    warnings = res.json()["warnings"]
    assert len(warnings) == 1 and warnings[0].startswith("전역") and "손절" in warnings[0]
    # The check response carries the same notes.
    assert client.get("/api/rules/check").json()["settings_notes"] == warnings


@pytest.mark.parametrize(
    "over",
    [
        {"cut_loss_pct": "0"},
        {"cut_loss_pct": "100"},
        {"below_ma_days": 0},
        {"add_max_steps": -1},
        {"max_risk_pct": "abc"},
    ],
)
def test_put_rejects_values_the_engine_rejects(client, over):
    res = client.put("/api/rules/settings", json=settings_body(client, **over))
    assert res.status_code == 422


def test_put_rejects_a_bad_symbol_override(client):
    body = settings_body(client)
    body["targets"] = {"AAPL": {"target_weight_pct": "150"}}
    res = client.put("/api/rules/settings", json=body)
    assert res.status_code == 422
    assert "AAPL" in res.json()["detail"]


# --- checks ---------------------------------------------------------------------------------


def test_check_without_holdings_is_empty_but_well_formed(client):
    body = client.get("/api/rules/check").json()
    assert body["checks"] == [] and body["skipped"] == []
    assert body["total_risk_pct_equity"] is None
    assert body["live_trading"] is False
    assert body["kill_switch"]["tripped"] is False
    assert body["labels"]["status"]["cut"] == "손절 검토"
    assert "두 배" in body["labels"]["prob_caveat"]


def test_check_reports_each_holding_in_its_own_currency(client):
    assert buy(client, "AAPL", 10, 100).status_code == 201
    assert krw_trade(client, "BTC", "0.01", "80000000").status_code == 201
    body = client.get("/api/rules/check").json()
    by_symbol = {c["symbol"]: c for c in body["checks"]}
    assert set(by_symbol) == {"AAPL", "BTC-USD"}

    stock, coin = by_symbol["AAPL"], by_symbol["BTC-USD"]
    assert stock["currency"] == "USD" and coin["currency"] == "KRW"
    # Levels follow the position's currency: the coin's stop is a won price.
    assert coin["avg_cost"] == 80_000_000
    assert coin["levels"]["cut_loss_price"] == pytest.approx(80_000_000 * 0.75)
    assert stock["levels"]["cut_loss_price"] == pytest.approx(85)
    # The asset-class layer applied to the coin, the global values to the stock.
    assert coin["rule"]["cut_loss_pct"] == 25 and stock["rule"]["cut_loss_pct"] == 15

    for c in (stock, coin):
        assert c["status"] in ("cut", "add", "hold")
        assert c["label_ko"] and c["chip_ko"]
        assert c["weight_room_pt"] is not None and c["weight_room_pt"] >= 0
        assert c["risk_pct_equity"] is not None
        assert c["notes"] == ["현금 기록이 없어 추매 가능 금액을 확인하지 못했습니다"]
        assert c["bars"] > 0 and c["history_error"] is None
        # No trained model: the reference probability is absent and says why.
        assert c["cut_prob_1m"] is None and c["cut_prob_1m_label"] is None
        assert c["forecast_status"] == "not_trained"
    # Loss at the stop as a share of equity, in each position's own currency, adds up.
    assert body["total_risk_pct_equity"] == pytest.approx(
        stock["risk_pct_equity"] + coin["risk_pct_equity"]
    )


def test_check_risk_share_uses_total_equity_in_the_position_currency(client):
    assert buy(client, "AAPL", 10, 100).status_code == 201
    body = client.get("/api/rules/check").json()
    [c] = body["checks"]
    equity = c["price"] * c["quantity"]  # the only holding
    expected = max(c["price"] - c["levels"]["cut_price"], 0) * c["quantity"] / equity * 100
    assert c["risk_pct_equity"] == pytest.approx(expected)
    assert body["total_risk_pct_equity"] == pytest.approx(expected)


def test_check_uses_the_saved_symbol_override(client):
    assert buy(client, "AAPL", 10, 100).status_code == 201
    body = settings_body(client)
    body["targets"] = {"AAPL": {"cut_loss_pct": "5", "target_weight_pct": "50"}}
    assert client.put("/api/rules/settings", json=body).status_code == 200
    [c] = client.get("/api/rules/check").json()["checks"]
    assert c["rule"]["cut_loss_pct"] == 5 and c["rule"]["target_weight_pct"] == 50
    assert c["levels"]["cut_loss_price"] == pytest.approx(95)
