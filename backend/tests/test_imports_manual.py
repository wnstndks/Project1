"""Holdings typed in on the import page (`POST /api/imports/manual`).

They must go through the same checks as screenshot rows and never need the screenshot
extractor. Synthetic quantities and prices only (public repo).
"""

import pytest

from app.deps import get_extractor


def quote(client, symbol):
    return client.get(f"/api/market/{symbol}/quote").json()["price"]


def manual(client, *rows):
    return client.post("/api/imports/manual", json={"rows": list(rows)})


def buy(client, symbol, quantity, price, **extra):
    body = {
        "asset_type": "stock",
        "symbol": symbol,
        "side": "buy",
        "trade_date": "2026-10-01",
        "quantity": quantity,
        "price": price,
        **extra,
    }
    assert client.post("/api/transactions", json=body).status_code == 201


class RefusingExtractor:
    """Stands in for a missing API key: any attempt to read a screenshot is a test failure."""

    def extract(self, images):
        raise AssertionError("manual import must not call the extractor")


def test_typed_price_passes_through_the_screenshot_checks(client):
    res = manual(
        client, {"asset_type": "stock", "symbol": " aapl ", "quantity": "10", "avg_price": "150"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["broker"] is None
    row = body["rows"][0]
    assert row["status"] == "ok" and row["symbol"] == "AAPL" and row["name"] == "AAPL"
    assert row["origin"] == "manual"
    assert row["quantity"] == 10 and row["avg_price"] == 150 and row["currency"] == "USD"
    assert row["price_estimated"] is False and row["message"] is None
    assert row["warning"] is None
    assert row["ticker_guessed"] is False and row["confidence"] == "high"
    assert row["diff"] == "new" and row["cost_krw"] is None and row["implied_fx"] is None


def test_missing_price_is_filled_with_the_current_price(client):
    row = manual(client, {"asset_type": "stock", "symbol": "MSFT", "quantity": "2"}).json()["rows"][
        0
    ]
    assert row["status"] == "ok"
    assert row["price_estimated"] is True
    assert row["avg_price"] == pytest.approx(quote(client, "MSFT"), abs=0.01)  # to the cent
    assert "현재가로 채웠어요" in row["message"]
    assert row["warning"] is None  # price == current price: no doubt


def test_typed_price_far_from_the_market_still_gets_the_screenshot_warning(client):
    # The 20x rule applies to typed prices too: a slipped decimal point is caught before import.
    far = quote(client, "AAPL") * 50
    row = manual(
        client,
        {"asset_type": "stock", "symbol": "AAPL", "quantity": "1", "avg_price": f"{far:.2f}"},
    ).json()["rows"][0]
    assert row["status"] == "ok" and row["warning"] is not None
    assert "배 차이" in row["warning"]


def test_difference_from_current_holdings_is_reported(client):
    buy(client, "AAPL", 4, 100)
    row = manual(
        client, {"asset_type": "stock", "symbol": "AAPL", "quantity": "10", "avg_price": "150"}
    ).json()["rows"][0]
    assert row["diff"] == "different" and row["current_quantity"] == 4
    # Typed: 10 @ 150 avg in total. Held: 4 @ 100. Recording 6 @ x keeps the average at 150:
    # (10*150 - 400) / 6 = 183.3333
    assert row["delta_quantity"] == 6
    assert row["delta_price"] == pytest.approx(183.3333)


def test_unknown_and_unsupported_tickers_fail_per_row(client):
    body = manual(
        client,
        {"asset_type": "stock", "symbol": "ZZZZ", "quantity": "1"},
        {"asset_type": "crypto", "symbol": "DOGE", "quantity": "100", "currency": "KRW"},
        {"asset_type": "stock", "symbol": "AAPL", "quantity": "1", "avg_price": "100"},
    ).json()
    unknown, unsupported, ok = body["rows"]
    assert unknown["status"] == "unknown" and "ZZZZ" in unknown["message"]
    assert unsupported["status"] == "unsupported" and "BTC, ETH, XRP, SOL" in unsupported["message"]
    assert ok["status"] == "ok"


def test_stock_in_won_is_rejected(client):
    res = manual(
        client, {"asset_type": "stock", "symbol": "AAPL", "quantity": "1", "currency": "KRW"}
    )
    assert res.status_code == 422
    assert "USD" in res.json()["detail"]


@pytest.mark.parametrize(
    "body",
    [
        {"rows": []},
        {"rows": [{"asset_type": "stock", "symbol": "AAPL", "quantity": "0"}]},
        {"rows": [{"asset_type": "stock", "symbol": "AAPL", "quantity": "1", "avg_price": "-5"}]},
        {"rows": [{"asset_type": "stock", "symbol": "", "quantity": "1"}]},
    ],
)
def test_invalid_input_is_rejected(client, body):
    assert client.post("/api/imports/manual", json=body).status_code == 422


def test_krw_coin_is_filled_with_the_upbit_price(client):
    row = manual(
        client, {"asset_type": "crypto", "symbol": "BTC", "quantity": "0.01", "currency": "KRW"}
    ).json()["rows"][0]
    assert row["status"] == "ok" and row["symbol"] == "BTC-USD"
    assert row["currency"] == "KRW" and row["name"] == "Bitcoin"
    assert row["avg_price"] == pytest.approx(quote(client, "KRW-BTC"), abs=1)  # to the won
    assert row["price_estimated"] is True and "현재가로 채웠어요" in row["message"]


def test_usd_coin_is_filled_with_the_dollar_price(client):
    row = manual(
        client, {"asset_type": "crypto", "symbol": "ETH-USD", "quantity": "0.5", "currency": "USD"}
    ).json()["rows"][0]
    assert row["status"] == "ok" and row["symbol"] == "ETH-USD" and row["currency"] == "USD"
    assert row["avg_price"] == pytest.approx(quote(client, "ETH-USD"), abs=0.01)


def test_missing_won_price_fails_that_row_only(client, provider):
    provider.unknown.add("KRW-SOL")
    body = manual(
        client,
        {"asset_type": "crypto", "symbol": "SOL", "quantity": "1", "currency": "KRW"},
        {
            "asset_type": "crypto",
            "symbol": "SOL",
            "quantity": "1",
            "avg_price": "200000",
            "currency": "KRW",
        },
    ).json()
    failed, typed = body["rows"]
    assert failed["status"] == "invalid" and "KRW-SOL" in failed["message"]
    assert failed["currency"] == "KRW" and failed["avg_price"] is None
    assert typed["status"] == "ok" and typed["avg_price"] == 200_000


def test_coin_held_in_another_currency_is_refused(client):
    buy(client, "BTC", "0.01", "60000", asset_type="crypto", currency="USD")
    row = manual(
        client, {"asset_type": "crypto", "symbol": "BTC", "quantity": "0.02", "currency": "KRW"}
    ).json()["rows"][0]
    assert row["status"] == "invalid" and "USD" in row["message"]


def test_manual_rows_need_no_extractor_and_commit_like_screenshot_rows(client):
    client.app.dependency_overrides[get_extractor] = RefusingExtractor
    row = manual(
        client, {"asset_type": "crypto", "symbol": "XRP", "quantity": "100", "currency": "KRW"}
    ).json()["rows"][0]
    assert row["status"] == "ok" and row["price_estimated"] is True

    res = client.post(
        "/api/imports/commit",
        json={
            "trade_date": "2026-10-01",
            "rows": [
                {
                    "asset_type": row["asset_type"],
                    "symbol": row["symbol"],
                    "quantity": str(row["quantity"]),
                    "currency": row["currency"],
                    "price": str(row["avg_price"]),
                }
            ],
        },
    )
    assert res.status_code == 200 and res.json()["created"] == 1
    tx = client.get("/api/transactions").json()[0]
    assert tx["symbol"] == "XRP-USD" and tx["currency"] == "KRW" and tx["quantity"] == 100
