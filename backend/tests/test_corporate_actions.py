from datetime import date
from decimal import Decimal

import pytest

from app.data.provider import CorporateEvent
from app.services import corporate_actions
from tests.conftest import TODAY

SPLIT_DAY = date(2026, 6, 10)
DIV_DAY = date(2026, 8, 1)


@pytest.fixture(autouse=True)
def _fresh_detection_cache():
    corporate_actions._last_checked.clear()


@pytest.fixture
def provider(provider):
    provider.actions = {
        "NVDA": [
            CorporateEvent(date(2020, 1, 2), "dividend", Decimal("0.04")),  # before first buy
            CorporateEvent(SPLIT_DAY, "split", Decimal("10")),
            CorporateEvent(DIV_DAY, "dividend", Decimal("0.25")),
        ],
        "MSFT": [CorporateEvent(date(2026, 9, 1), "dividend", Decimal("0.83"))],
    }
    return provider


def trade(client, symbol, qty, price, day, side="buy"):
    return client.post(
        "/api/transactions",
        json={
            "asset_type": "stock",
            "symbol": symbol,
            "side": side,
            "trade_date": str(day),
            "quantity": qty,
            "price": price,
        },
    )


def actions(client):
    return {(a["symbol"], a["kind"]): a for a in client.get("/api/corporate-actions").json()}


def test_detects_only_events_while_held(client):
    trade(client, "NVDA", 10, 1000, date(2026, 1, 5))
    trade(client, "MSFT", 1, 400, date(2026, 1, 5))
    trade(client, "MSFT", 1, 420, date(2026, 3, 1), side="sell")  # sold before its dividend
    found = actions(client)
    assert set(found) == {("NVDA", "split"), ("NVDA", "dividend")}
    split = found[("NVDA", "split")]
    assert split["status"] == "detected"
    assert split["shares_before"] == 10 and split["effect"] == 100


def test_confirmed_split_adjusts_quantity_and_allows_post_split_sells(client):
    trade(client, "NVDA", 10, 1000, date(2026, 1, 5))
    split = actions(client)[("NVDA", "split")]

    # Before confirming, selling 50 post-split shares looks like an oversell.
    assert trade(client, "NVDA", 50, 120, date(2026, 7, 1), side="sell").status_code == 422

    client.post(f"/api/corporate-actions/{split['id']}/confirm")
    h = next(h for h in client.get("/api/portfolio/holdings").json() if h["symbol"] == "NVDA")
    assert h["quantity"] == 100
    assert h["avg_cost"] == pytest.approx(100)  # same 10,000 invested over 10x the shares

    assert trade(client, "NVDA", 50, 120, date(2026, 7, 1), side="sell").status_code == 201
    # Ignoring the split now would make that sell an oversell, so it is refused.
    assert client.post(f"/api/corporate-actions/{split['id']}/ignore").status_code == 422


def test_confirmed_dividend_is_net_of_withholding_and_counts_in_total_pnl(client):
    trade(client, "NVDA", 10, 1000, date(2026, 1, 5))
    found = actions(client)
    client.post(f"/api/corporate-actions/{found[('NVDA', 'split')]['id']}/confirm")
    div = actions(client)[("NVDA", "dividend")]
    assert div["shares_before"] == 100  # the split happened before this ex-date
    client.post(f"/api/corporate-actions/{div['id']}/confirm")

    s = client.get("/api/portfolio/summary").json()
    assert s["dividends"] == pytest.approx(100 * 0.25 * 0.85)
    assert s["dividends_krw"] > 0
    assert s["total_pnl"] == pytest.approx(s["unrealized_pnl"] + s["realized_pnl"] + s["dividends"])


def test_history_restores_pre_split_prices(client, provider):
    trade(client, "NVDA", 10, 1000, date(2026, 1, 5))
    split = actions(client)[("NVDA", "split")]
    client.post(f"/api/corporate-actions/{split['id']}/confirm")

    points = {p["date"]: p for p in client.get("/api/portfolio/history").json()}
    bars = {b.date: b.close for b in provider.get_history("NVDA", date(2026, 6, 1), TODAY)}
    # The fake series is not split-adjusted, so the app multiplies pre-split closes by 10
    # (as it must for Yahoo's back-adjusted prices) while quantity is still 10.
    assert points["2026-06-09"]["market_value"] == pytest.approx(10 * bars[date(2026, 6, 9)] * 10)
    # From the ex-date on, 100 shares at the unadjusted close.
    assert points["2026-06-10"]["market_value"] == pytest.approx(100 * bars[date(2026, 6, 10)])


def test_ignored_events_do_not_change_the_ledger(client):
    trade(client, "NVDA", 10, 1000, date(2026, 1, 5))
    div = actions(client)[("NVDA", "dividend")]
    client.post(f"/api/corporate-actions/{div['id']}/ignore")
    assert client.get("/api/portfolio/summary").json()["dividends"] == 0
    assert actions(client)[("NVDA", "dividend")]["status"] == "ignored"


def test_confirm_all_dividends_leaves_splits_for_review(client):
    trade(client, "NVDA", 10, 1000, date(2026, 1, 5))
    actions(client)
    res = client.post("/api/corporate-actions/dividends/confirm-all").json()
    status = {a["kind"]: a["status"] for a in res}
    assert status == {"dividend": "confirmed", "split": "detected"}
