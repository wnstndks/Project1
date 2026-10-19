import pytest


def buy(client, symbol, qty, price, day="2026-10-01", asset_type="stock", side="buy", fee=0):
    return client.post(
        "/api/transactions",
        json={
            "asset_type": asset_type,
            "symbol": symbol,
            "side": side,
            "trade_date": day,
            "quantity": qty,
            "price": price,
            "fee": fee,
        },
    )


def test_create_normalizes_symbol_and_keeps_decimals(client):
    res = buy(client, "btc", 0.12345678, 60000.5, asset_type="crypto")
    assert res.status_code == 201
    body = res.json()
    assert body["symbol"] == "BTC-USD"
    assert body["quantity"] == 0.12345678
    assert body["price"] == 60000.5


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({"symbol": "DOGE", "asset_type": "crypto"}, 422),  # not in the 4-coin allowlist
        ({"symbol": "ZZZZ"}, 422),  # provider does not know it
        ({"day": "2099-01-01"}, 422),
        ({"qty": 0}, 422),
        ({"qty": 0.123456789}, 422),  # more than 8 decimals
    ],
)
def test_create_validation(client, payload, status):
    args = {"symbol": "AAPL", "qty": 1, "price": 100} | payload
    assert buy(client, **args).status_code == status


def test_oversell_rejected_on_create_update_and_delete(client):
    b = buy(client, "AAPL", 10, 100, day="2026-10-01").json()
    s = buy(client, "AAPL", 8, 110, day="2026-10-05", side="sell").json()

    assert buy(client, "AAPL", 5, 110, day="2026-10-06", side="sell").status_code == 422

    edit = {
        "asset_type": "stock",
        "symbol": "AAPL",
        "side": "buy",
        "trade_date": "2026-10-01",
        "quantity": 5,
        "price": 100,
    }
    assert client.put(f"/api/transactions/{b['id']}", json=edit).status_code == 422
    assert client.delete(f"/api/transactions/{b['id']}").status_code == 422

    assert client.delete(f"/api/transactions/{s['id']}").status_code == 204
    assert client.delete(f"/api/transactions/{b['id']}").status_code == 204
    assert client.get("/api/transactions").json() == []


def test_update_and_missing_transaction(client):
    b = buy(client, "AAPL", 1, 100).json()
    edit = {
        "asset_type": "stock",
        "symbol": "msft",
        "side": "buy",
        "trade_date": "2026-10-02",
        "quantity": 2,
        "price": 300,
    }
    res = client.put(f"/api/transactions/{b['id']}", json=edit)
    assert res.status_code == 200
    assert res.json()["symbol"] == "MSFT"
    assert client.delete("/api/transactions/999").status_code == 404


def test_holdings_and_summary(client):
    buy(client, "AAPL", 10, 100, fee=1)
    buy(client, "BTC", 0.5, 50000, asset_type="crypto")
    buy(client, "AAPL", 4, 120, day="2026-10-02", side="sell")

    holdings = client.get("/api/portfolio/holdings").json()
    assert {h["symbol"] for h in holdings} == {"AAPL", "BTC-USD"}
    aapl = next(h for h in holdings if h["symbol"] == "AAPL")
    assert aapl["quantity"] == 6
    assert aapl["avg_cost"] == pytest.approx(100.1)
    assert aapl["realized_pnl"] == pytest.approx(4 * (120 - 100.1))
    assert sum(h["weight"] for h in holdings) == pytest.approx(100)

    summary = client.get("/api/portfolio/summary").json()
    assert summary["holdings_count"] == 2
    assert summary["market_value"] == pytest.approx(sum(h["market_value"] for h in holdings))
    assert summary["market_value_krw"] == pytest.approx(
        summary["market_value"] * summary["usd_krw"]
    )
    alloc = {a["asset_type"]: a["weight"] for a in summary["allocation"]}
    assert alloc["stock"] + alloc["crypto"] == pytest.approx(100)


def test_empty_portfolio(client):
    summary = client.get("/api/portfolio/summary").json()
    assert summary["market_value"] == 0
    assert summary["holdings_count"] == 0
    assert client.get("/api/portfolio/history").json() == []


def test_history_tracks_positions_over_time(client):
    buy(client, "AAPL", 10, 100, day="2026-10-01")
    buy(client, "AAPL", 10, 100, day="2026-10-08")

    points = client.get("/api/portfolio/history").json()
    by_date = {p["date"]: p for p in points}
    assert points[0]["date"] == "2026-10-01"
    assert by_date["2026-10-07"]["cost_basis"] == 1000
    assert by_date["2026-10-08"]["cost_basis"] == 2000
    # weekend days are forward-filled, not dropped
    assert by_date["2026-10-03"]["market_value"] == by_date["2026-10-02"]["market_value"]
