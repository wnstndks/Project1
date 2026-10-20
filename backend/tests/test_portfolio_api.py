from datetime import date

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


def test_update_keeps_fields_the_client_did_not_send(client):
    b = buy(client, "AAPL", 10, 100).json()
    client.put(
        f"/api/transactions/{b['id']}",
        json={
            "asset_type": "stock",
            "symbol": "AAPL",
            "side": "buy",
            "trade_date": "2026-10-01",
            "quantity": 10,
            "price": 100,
            "fx_rate": "1320",
        },
    )
    # A later edit of only the note must not wipe the recorded purchase FX rate.
    res = client.put(
        f"/api/transactions/{b['id']}",
        json={
            "asset_type": "stock",
            "symbol": "AAPL",
            "side": "buy",
            "trade_date": "2026-10-01",
            "quantity": 10,
            "price": 100,
            "note": "typo fixed",
        },
    )
    assert res.json()["fx_rate"] == 1320
    assert res.json()["note"] == "typo fixed"


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

    # KRW P&L = USD P&L at today's rate + the FX effect on the cost basis
    assert summary["unrealized_pnl_krw"] == pytest.approx(
        summary["unrealized_pnl"] * summary["usd_krw"] + summary["fx_pnl_krw"]
    )
    assert summary["market_value_krw"] == pytest.approx(
        sum(h["market_value_krw"] for h in holdings)
    )
    assert aapl["avg_cost_krw"] > 0


def test_transaction_list_includes_trade_date_fx(client, provider):
    buy(client, "AAPL", 1, 100, day="2026-10-02")
    tx = client.get("/api/transactions").json()[0]
    expected = provider.get_history("KRW=X", date(2026, 10, 2), date(2026, 10, 2))[0].close
    assert tx["usd_krw"] == pytest.approx(expected)


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
    # KRW cost is fixed at each buy date's FX rate, so it only moves on trade days
    assert by_date["2026-10-02"]["cost_basis_krw"] == by_date["2026-10-07"]["cost_basis_krw"]
    assert by_date["2026-10-08"]["cost_basis_krw"] > by_date["2026-10-07"]["cost_basis_krw"]


def test_history_krw_cost_shrinks_proportionally_on_sell(client):
    buy(client, "AAPL", 10, 100, day="2026-10-01")
    buy(client, "AAPL", 4, 120, day="2026-10-05", side="sell")

    by_date = {p["date"]: p for p in client.get("/api/portfolio/history").json()}
    before, after = by_date["2026-10-04"]["cost_basis_krw"], by_date["2026-10-05"]["cost_basis_krw"]
    assert after == pytest.approx(before * 0.6, abs=1)


def krw_trade(client, symbol, qty, price, day="2026-10-01", side="buy", fee=0):
    return client.post(
        "/api/transactions",
        json={
            "asset_type": "crypto",
            "symbol": symbol,
            "side": side,
            "trade_date": day,
            "currency": "KRW",
            "quantity": qty,
            "price": price,
            "fee": fee,
        },
    )


def test_krw_coin_is_valued_at_upbit_price_with_exact_krw_cost(client, provider):
    assert krw_trade(client, "BTC", "0.01", "80000000", fee="400").status_code == 201
    h = next(h for h in client.get("/api/portfolio/holdings").json() if h["symbol"] == "BTC-USD")
    assert h["currency"] == "KRW"
    assert h["cost_basis_krw"] == 800_400  # exact won spent, fee included
    upbit = provider.get_quote("KRW-BTC").price
    assert h["price_krw"] == pytest.approx(upbit)  # Upbit KRW price, not USD x FX
    assert h["market_value_krw"] == pytest.approx(0.01 * upbit)
    fx = client.get("/api/portfolio/summary").json()["usd_krw"]
    assert h["market_value"] == pytest.approx(0.01 * upbit / fx)


def test_krw_coin_realized_pnl_is_exact_in_won(client):
    krw_trade(client, "ETH", "2", "3000000", day="2026-10-01")
    krw_trade(client, "ETH", "1", "3500000", day="2026-10-05", side="sell", fee="1750")
    summary = client.get("/api/portfolio/summary").json()
    assert summary["realized_pnl_krw"] == 500_000 - 1_750


def test_currency_rules(client):
    # Stocks are USD only; a coin position cannot mix KRW and USD trades.
    stock_krw = client.post(
        "/api/transactions",
        json={
            "asset_type": "stock",
            "symbol": "AAPL",
            "side": "buy",
            "trade_date": "2026-10-01",
            "currency": "KRW",
            "quantity": 1,
            "price": 1,
        },
    )
    assert stock_krw.status_code == 422
    krw_trade(client, "SOL", "1", "200000")
    usd = buy(client, "SOL", 1, 150, asset_type="crypto")
    assert usd.status_code == 422
    assert "mixed" in usd.json()["detail"]


def test_history_values_krw_coins_in_won(client):
    krw_trade(client, "BTC", "0.01", "80000000", day="2026-10-01")
    points = client.get("/api/portfolio/history").json()
    by_date = {p["date"]: p for p in points}
    assert by_date["2026-10-05"]["cost_basis_krw"] == 800_000
    assert by_date["2026-10-05"]["market_value_krw"] > 0


def test_krw_coins_carry_no_fx_pnl(client):
    krw_trade(client, "BTC", "0.01", "80000000")
    assert client.get("/api/portfolio/summary").json()["fx_pnl_krw"] == 0


def test_convert_existing_usd_coin_trades_to_krw(client):
    buy(client, "BTC", 0.02, 60000, asset_type="crypto", fee=6)
    res = client.post(
        "/api/transactions/convert-currency", json={"symbol": "btc", "currency": "KRW"}
    )
    assert res.status_code == 200
    tx = client.get("/api/transactions").json()[0]
    assert tx["currency"] == "KRW" and tx["fx_rate"] is None
    assert tx["price"] == pytest.approx(60000 * tx["usd_krw"], rel=1e-6)
    # Now an Upbit buy fits the position.
    assert krw_trade(client, "BTC", "0.01", "80000000").status_code == 201
    h = next(h for h in client.get("/api/portfolio/holdings").json() if h["symbol"] == "BTC-USD")
    assert h["currency"] == "KRW" and h["quantity"] == pytest.approx(0.03)


def test_stocks_cannot_be_converted_to_krw(client):
    buy(client, "AAPL", 1, 100)
    res = client.post(
        "/api/transactions/convert-currency", json={"symbol": "AAPL", "currency": "KRW"}
    )
    assert res.status_code == 422


def test_delete_all_requires_explicit_confirmation(client, db):
    from app.db.models import Transaction
    from app.services.transactions import IMPORT_NOTE

    buy(client, "AAPL", 10, 150)
    buy(client, "MSFT", 2, 400)
    # Mark the MSFT buy as a screenshot import.
    tx = db.query(Transaction).filter_by(symbol="MSFT").one()
    tx.note = IMPORT_NOTE
    db.commit()

    assert client.delete("/api/transactions").status_code == 422  # no confirm parameter
    res = client.delete("/api/transactions?confirm=imports")
    assert res.json() == {"deleted": 1}
    assert [t["symbol"] for t in client.get("/api/transactions").json()] == ["AAPL"]

    assert client.delete("/api/transactions?confirm=all").json() == {"deleted": 1}
    assert client.get("/api/transactions").json() == []
    assert client.get("/api/portfolio/holdings").json() == []


def test_deleting_imports_that_later_sells_depend_on_is_refused(client, db):
    from app.db.models import Transaction
    from app.services.transactions import IMPORT_NOTE

    buy(client, "AAPL", 10, 150, day="2026-09-01")
    buy(client, "AAPL", 5, 160, day="2026-10-01", side="sell")
    tx = db.query(Transaction).filter_by(side="buy").one()
    tx.note = IMPORT_NOTE
    db.commit()
    assert client.delete("/api/transactions?confirm=imports").status_code == 422
    assert len(client.get("/api/transactions").json()) == 2
