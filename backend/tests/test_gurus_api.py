"""Investor endpoints: list, background sync, holdings, overlap with my positions.

FakeGuruProvider stands in for ARK and EDGAR; the TestClient runs background tasks before
returning, so a sync scheduled by a request has finished by the next request.
"""

from datetime import date

import pytest
from sqlalchemy.orm import sessionmaker

from app.data.guru_provider import FakeCusipResolver, FakeGuruProvider, GuruHolding, GuruSnapshot
from app.data.gurus import GURUS
from app.deps import get_cusip_resolver, get_guru_provider, get_sec_configured, get_session_factory
from app.services import gurus as gurus_service
from app.services.gurus import SEC_UA_MISSING

AS_OF = date(2026, 10, 20)


def snapshot(rows: list[tuple[str | None, str, float]], source: str = "ark") -> GuruSnapshot:
    total = sum(v for _, _, v in rows)
    return GuruSnapshot(
        as_of=AS_OF,
        source=source,
        holdings=[
            GuruHolding(
                symbol=s, cusip=f"C{i:08d}", name=n, shares=1, value_usd=v, weight=v / total
            )
            for i, (s, n, v) in enumerate(rows)
        ],
    )


@pytest.fixture(autouse=True)
def _clear_in_flight():
    gurus_service._in_flight.clear()


@pytest.fixture
def guru_provider() -> FakeGuruProvider:
    return FakeGuruProvider(
        {
            "cathie-wood": snapshot(
                [
                    ("TSLA", "TESLA INC", 500),
                    ("AAPL", "APPLE INC", 300),
                    ("RKLB", "ROCKET LAB", 200),
                ]
            ),
            "warren-buffett": snapshot(
                [
                    ("AAPL", "APPLE INC", 600),
                    ("KO", "COCA COLA CO", 300),
                    (None, "UNMAPPED CO", 100),
                ],
                source="13f",
            ),
        }
    )


@pytest.fixture
def gclient(client, db, guru_provider):
    app = client.app
    app.dependency_overrides[get_guru_provider] = lambda: guru_provider
    app.dependency_overrides[get_cusip_resolver] = lambda: FakeCusipResolver()
    app.dependency_overrides[get_sec_configured] = lambda: True
    # Background jobs open their own session on the test engine (StaticPool: one connection).
    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    app.dependency_overrides[get_session_factory] = lambda: factory
    return client


def buy(client, symbol: str, qty: str, price: str):
    res = client.post(
        "/api/transactions",
        json={
            "asset_type": "stock",
            "symbol": symbol,
            "side": "buy",
            "trade_date": "2026-10-01",
            "quantity": qty,
            "price": price,
        },
    )
    assert res.status_code == 201, res.text


def test_list_before_any_sync_and_without_sec_user_agent(gclient):
    body = gclient.get("/api/gurus").json()
    assert [g["id"] for g in body] == [g.id for g in GURUS]
    assert all(g["stale"] and g["holdings_count"] == 0 and g["synced_at"] is None for g in body)
    assert all(g["error"] is None for g in body)

    gclient.app.dependency_overrides[get_sec_configured] = lambda: False
    body = gclient.get("/api/gurus").json()
    assert all(g["error"] == SEC_UA_MISSING for g in body if g["source"] == "13f")
    assert all(g["error"] is None for g in body if g["source"] == "ark")


def test_compare_starts_first_sync_in_background_then_reports_overlaps(gclient, guru_provider):
    buy(gclient, "AAPL", "10", "100")
    buy(gclient, "TSLA", "5", "200")

    first = gclient.get("/api/gurus/compare")
    assert first.status_code == 200
    assert first.json()["syncing"] is True
    assert all(g["overlaps"] == [] for g in first.json()["gurus"])
    # The background job has run by now: every investor fetched exactly once.
    assert sorted(guru_provider.calls) == sorted(g.id for g in GURUS)

    body = gclient.get("/api/gurus/compare").json()
    assert body["syncing"] is False
    assert len(guru_provider.calls) == len(GURUS)  # no second fetch within the TTL
    by_id = {g["guru"]["id"]: g for g in body["gurus"]}
    weights = {
        h["symbol"]: round(h["weight"], 2) for h in gclient.get("/api/portfolio/holdings").json()
    }

    wood = by_id["cathie-wood"]
    assert wood["guru"]["as_of"] == "2026-10-20" and wood["guru"]["stale"] is False
    assert wood["guru"]["error"] is None and wood["guru"]["holdings_count"] == 3
    assert [(o["symbol"], o["guru_weight_pct"]) for o in wood["overlaps"]] == [
        ("TSLA", 50.0),
        ("AAPL", 30.0),
    ]
    assert [o["my_weight_pct"] for o in wood["overlaps"]] == [weights["TSLA"], weights["AAPL"]]
    assert wood["top_missing"] == [{"symbol": "RKLB", "name": "ROCKET LAB", "weight_pct": 20.0}]

    buffett = by_id["warren-buffett"]
    assert [(o["symbol"], o["guru_weight_pct"]) for o in buffett["overlaps"]] == [("AAPL", 60.0)]
    # An unmapped CUSIP cannot be matched to my tickers, so it is listed by name.
    assert buffett["top_missing"] == [
        {"symbol": "KO", "name": "COCA COLA CO", "weight_pct": 30.0},
        {"symbol": None, "name": "UNMAPPED CO", "weight_pct": 10.0},
    ]

    burry = by_id["michael-burry"]
    assert burry["guru"]["stale"] is True and "no fake snapshot" in burry["guru"]["error"]
    assert burry["overlaps"] == [] and burry["top_missing"] == []


def test_sync_returns_202_and_holdings_endpoint_cuts_to_top(gclient, guru_provider):
    res = gclient.post("/api/gurus/sync")
    assert res.status_code == 202
    assert res.json()["syncing"] is True
    assert len(res.json()["gurus"]) == len(GURUS)
    assert sorted(guru_provider.calls) == sorted(g.id for g in GURUS)

    body = gclient.get("/api/gurus/cathie-wood/holdings?top=2").json()
    assert body["total"] == 3
    assert body["guru"]["name_ko"] == "캐시 우드" and body["guru"]["source"] == "ark"
    assert [(h["symbol"], h["weight_pct"]) for h in body["holdings"]] == [
        ("TSLA", 50.0),
        ("AAPL", 30.0),
    ]
    assert set(body["holdings"][0]) == {
        "symbol",
        "cusip",
        "name",
        "shares",
        "value_usd",
        "weight_pct",
    }

    assert gclient.get("/api/gurus/nobody/holdings").status_code == 404
    assert gclient.get("/api/gurus/cathie-wood/holdings?top=0").status_code == 422


def test_sync_skips_13f_filers_without_sec_user_agent(gclient, guru_provider):
    gclient.app.dependency_overrides[get_sec_configured] = lambda: False
    gclient.post("/api/gurus/sync")
    assert sorted(guru_provider.calls) == ["cathie-wood"]

    body = {g["id"]: g for g in gclient.get("/api/gurus").json()}
    assert body["cathie-wood"]["holdings_count"] == 3 and body["cathie-wood"]["error"] is None
    assert body["warren-buffett"]["error"] == SEC_UA_MISSING
    assert body["warren-buffett"]["holdings_count"] == 0

    # Nothing left to try on a first visit, so compare does not keep reporting a sync.
    compare = gclient.get("/api/gurus/compare").json()
    assert compare["syncing"] is False
    assert sorted(guru_provider.calls) == ["cathie-wood"]
