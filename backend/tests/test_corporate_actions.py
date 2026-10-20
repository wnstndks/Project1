from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.data.provider import CorporateEvent, MarketDataError, unadjust_dividends
from app.db.models import ActionStatus, CorporateAction, PriceBar
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


def test_confirmed_split_adjusts_quantity_and_allows_post_split_sells(client, db):
    trade(client, "NVDA", 10, 1000, date(2026, 1, 5))
    split = actions(client)[("NVDA", "split")]

    # Before confirming, selling 50 post-split shares looks like an oversell.
    assert trade(client, "NVDA", 50, 120, date(2026, 7, 1), side="sell").status_code == 422

    client.post(f"/api/corporate-actions/{split['id']}/confirm")
    h = next(h for h in client.get("/api/portfolio/holdings").json() if h["symbol"] == "NVDA")
    assert h["quantity"] == 100
    assert h["avg_cost"] == pytest.approx(100)  # same 10,000 invested over 10x the shares

    assert trade(client, "NVDA", 50, 120, date(2026, 7, 1), side="sell").status_code == 201
    # Ignoring the split now would make that sell an oversell, so it is refused and the
    # split stays confirmed.
    assert client.post(f"/api/corporate-actions/{split['id']}/ignore").status_code == 422
    db.expire_all()
    assert db.get(CorporateAction, split["id"]).status == ActionStatus.CONFIRMED
    assert client.get("/api/portfolio/holdings").status_code == 200


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


def test_dividends_before_a_later_split_are_restated_to_the_shares_then_held():
    # Yahoo lists NVDA's March 2024 dividend of $0.04 as $0.004 after the 10:1 split.
    events = [
        CorporateEvent(date(2024, 3, 5), "dividend", Decimal("0.004")),
        CorporateEvent(date(2024, 6, 10), "split", Decimal("10.0")),
        CorporateEvent(date(2024, 6, 11), "dividend", Decimal("0.01")),
    ]
    divs = {e.date: e.value for e in unadjust_dividends(events) if e.kind == "dividend"}
    assert divs == {date(2024, 3, 5): Decimal("0.04"), date(2024, 6, 11): Decimal("0.01")}


def test_reverse_split_leaves_no_dust_and_the_position_can_close(client, provider):
    provider.actions = {"NVDA": [CorporateEvent(SPLIT_DAY, "split", Decimal(str(1 / 30)))]}
    trade(client, "NVDA", 30, 10, date(2026, 1, 5))
    split = actions(client)[("NVDA", "split")]
    assert split["effect"] == 1
    client.post(f"/api/corporate-actions/{split['id']}/confirm")
    assert trade(client, "NVDA", 1, 300, date(2026, 7, 1), side="sell").status_code == 201
    assert all(h["symbol"] != "NVDA" for h in client.get("/api/portfolio/holdings").json())


def test_same_day_dividend_is_paid_on_pre_split_shares(client, provider):
    provider.actions = {
        "NVDA": [
            CorporateEvent(SPLIT_DAY, "split", Decimal("10")),
            CorporateEvent(SPLIT_DAY, "dividend", Decimal("1")),
        ]
    }
    trade(client, "NVDA", 10, 1000, date(2026, 1, 5))
    for a in actions(client).values():
        client.post(f"/api/corporate-actions/{a['id']}/confirm")
    assert client.get("/api/portfolio/summary").json()["dividends"] == pytest.approx(8.5)


def test_split_while_not_held_is_kept_for_history_but_dividends_are_not(client):
    trade(client, "NVDA", 10, 1000, date(2026, 1, 5))
    trade(client, "NVDA", 10, 1100, date(2026, 5, 1), side="sell")
    trade(client, "NVDA", 5, 130, date(2026, 9, 1))
    found = actions(client)
    assert set(found) == {("NVDA", "split")}
    # Nothing to decide: it cannot change the ledger, but history must undo Yahoo's
    # adjustment for the January-May holding.
    assert found[("NVDA", "split")]["status"] == "confirmed"
    assert found[("NVDA", "split")]["shares_before"] == 0


def test_withholding_rate_is_set_per_symbol(client):
    trade(client, "NVDA", 10, 1000, date(2026, 1, 5))
    div = actions(client)[("NVDA", "dividend")]
    client.post(f"/api/corporate-actions/{div['id']}/confirm")
    res = client.post("/api/corporate-actions/withholding", json={"symbol": "nvda", "rate": "0.21"})
    assert res.status_code == 200
    s = client.get("/api/portfolio/summary").json()
    assert s["dividends"] == pytest.approx(10 * 0.25 * 0.79)
    bad = client.post("/api/corporate-actions/withholding", json={"symbol": "NVDA", "rate": 1})
    assert bad.status_code == 422


def test_corrected_provider_amount_sends_a_confirmed_dividend_back_to_review(client, provider):
    trade(client, "NVDA", 10, 1000, date(2026, 1, 5))
    div = actions(client)[("NVDA", "dividend")]
    client.post(f"/api/corporate-actions/{div['id']}/confirm")
    provider.actions["NVDA"][2] = CorporateEvent(DIV_DAY, "dividend", Decimal("0.30"))
    corporate_actions._last_checked.clear()
    div = actions(client)[("NVDA", "dividend")]
    assert div["value"] == pytest.approx(0.30)
    assert div["status"] == "detected"


def test_new_split_drops_cached_bars(client, db):
    trade(client, "NVDA", 10, 1000, date(2026, 1, 5))
    client.get("/api/portfolio/history")  # caches NVDA bars
    assert db.scalar(select(func.count()).where(PriceBar.symbol == "NVDA"))
    actions(client)
    assert not db.scalar(select(func.count()).where(PriceBar.symbol == "NVDA"))


def test_confirming_a_reverse_split_that_breaks_later_sells_is_refused(client, provider, db):
    provider.actions = {"NVDA": [CorporateEvent(SPLIT_DAY, "split", Decimal("0.1"))]}
    trade(client, "NVDA", 10, 100, date(2026, 1, 5))
    trade(client, "NVDA", 5, 100, date(2026, 7, 1), side="sell")  # only 1 share after it
    split = actions(client)[("NVDA", "split")]
    assert client.post(f"/api/corporate-actions/{split['id']}/confirm").status_code == 422
    db.expire_all()
    assert db.get(CorporateAction, split["id"]).status == ActionStatus.DETECTED


def test_failed_lookup_is_retried_on_the_next_request(client, provider):
    trade(client, "NVDA", 10, 1000, date(2026, 1, 5))
    real = provider.get_actions

    def flaky(symbol):
        raise MarketDataError("rate limited")

    provider.get_actions = flaky
    assert client.get("/api/corporate-actions").json() == []
    provider.get_actions = real
    assert ("NVDA", "split") in actions(client)


def test_rounding_in_a_restated_amount_keeps_the_dividend_confirmed(client, provider):
    trade(client, "NVDA", 10, 1000, date(2026, 1, 5))
    div = actions(client)[("NVDA", "dividend")]
    client.post(f"/api/corporate-actions/{div['id']}/confirm")
    # $0.25 restated through a later 3:1 split and back: 0.083333 x 3.
    provider.actions["NVDA"][2] = CorporateEvent(DIV_DAY, "dividend", Decimal("0.249999"))
    corporate_actions._last_checked.clear()
    assert actions(client)[("NVDA", "dividend")]["status"] == "confirmed"
