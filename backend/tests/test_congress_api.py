"""Congress endpoints: trades for my symbols, first-visit background sync, status, manual sync.

FakeCongressProvider stands in for the Clerk's site; the TestClient runs background tasks
before returning, so a sync scheduled by a request has finished by the next request. Dates are
relative to today because the endpoint filters by real time. Names and tickers are invented.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.api import congress as congress_api
from app.data.congress_provider import (
    FakeCongressProvider,
    IndexEntry,
    IndexResult,
    PtrDocument,
    PtrRow,
)
from app.deps import get_congress_max_batches, get_congress_provider, get_session_factory
from app.services import congress as congress_service
from app.services.congress import CongressService

TODAY = date.today()
FILED = TODAY - timedelta(days=10)
TRADED = TODAY - timedelta(days=20)


def ptr_row(symbol: str, side: str, owner: str, day: date) -> PtrRow:
    return PtrRow(
        owner=owner,
        asset_name=f"{symbol} Common Stock ({symbol})",
        asset_type="ST",
        symbol=symbol,
        side=side,
        transaction_date=day,
        notification_date=FILED,
        amount_low=1_001,
        amount_high=15_000,
        amount_label="$1,001 - $15,000",
        filing_status="New",
    )


@pytest.fixture(autouse=True)
def _clear_in_flight():
    congress_service._in_flight.clear()


@pytest.fixture
def congress_provider() -> FakeCongressProvider:
    report = IndexEntry(TODAY.year, "20039001", "P", FILED, "Jane", "Doe", "Hon.", "", "ST01")
    # Filed a day earlier, so the newest-first sync fetches the report before the scan.
    earlier = FILED - timedelta(days=1)
    scan = IndexEntry(TODAY.year, "9001234", "P", earlier, "John", "Roe", "Hon.", "", "CA12")
    return FakeCongressProvider(
        {TODAY.year: IndexResult(TODAY.year, [report, scan], None)},
        {
            "20039001": PtrDocument(
                rows=[
                    ptr_row("QQXA", "buy", "SP", TRADED),
                    ptr_row("ZYXW", "sell", "SELF", TRADED - timedelta(days=1)),
                ]
            ),
            "9001234": PtrDocument(rows=[], no_text=True),
        },
    )


@pytest.fixture
def cclient(client, db, congress_provider):
    app = client.app
    app.dependency_overrides[get_congress_provider] = lambda: congress_provider
    # Background jobs open their own session on the test engine (StaticPool: one connection).
    factory = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)
    app.dependency_overrides[get_session_factory] = lambda: factory
    return client


def test_trades_starts_first_sync_in_background_then_returns_my_symbols(cclient, congress_provider):
    first = cclient.get("/api/congress/trades", params={"symbols": "QQXA,ZYXW"})
    assert first.status_code == 200
    body = first.json()
    assert body["syncing"] is True and body["trades"] == []
    assert body["status"]["stale"] is True and body["status"]["synced_at"] is None
    assert "상원은 포함되지 않습니다" in body["status"]["coverage_note"]
    assert "투자 조언이 아닙니다" in body["status"]["coverage_note"]
    # The background job has run: both documents fetched exactly once.
    assert [c for c in congress_provider.calls if c[0] == "ptr"] == [
        ("ptr", str(TODAY.year), "20039001"),
        ("ptr", str(TODAY.year), "9001234"),
    ]

    second = cclient.get("/api/congress/trades", params={"symbols": "qqxa"}).json()
    assert second["syncing"] is False and second["status"]["stale"] is False
    assert second["status"]["syncing"] is False
    status = second["status"]
    assert (status["docs_parsed"], status["docs_no_text"], status["trades"]) == (1, 1, 2)
    assert [t["symbol"] for t in second["trades"]] == ["QQXA"]
    trade = second["trades"][0]
    assert trade["member"] == "Jane Doe" and trade["owner"] == "SP" and trade["side"] == "buy"
    assert trade["state"] == "ST" and trade["district"] == "ST01" and trade["party"] is None
    assert (trade["amount_low"], trade["amount_high"]) == (1001, 15000)
    assert trade["transaction_date"] == TRADED.isoformat()
    assert trade["doc_url"].endswith(f"/ptr-pdfs/{TODAY.year}/20039001.pdf")
    assert len(congress_provider.calls) == 4  # no second fetch within the TTL

    recent = cclient.get("/api/congress/trades", params={"symbols": "QQXA", "days": 5}).json()
    assert recent["trades"] == []
    assert cclient.get("/api/congress/trades").json()["trades"] == []  # no symbols, nothing


def test_status_and_manual_sync(cclient, congress_provider):
    before = cclient.get("/api/congress/status").json()
    assert before["synced_at"] is None and before["stale"] and before["docs_total"] == 0

    res = cclient.post("/api/congress/sync")
    assert res.status_code == 202 and res.json()["syncing"] is True

    after = cclient.get("/api/congress/status").json()
    assert after["synced_at"] is not None and after["error"] is None
    assert after["syncing"] is False  # the whole batch loop has finished
    assert after["docs_total"] == 2 and after["docs_pending"] == 0 and after["trades"] == 2

    # Within the TTL with nothing pending, "fetch now" schedules nothing and says so.
    calls = len(congress_provider.calls)
    again = cclient.post("/api/congress/sync")
    assert again.status_code == 202 and again.json()["syncing"] is False
    assert len(congress_provider.calls) == calls


def test_manual_sync_resumes_a_pending_backlog_within_the_ttl(
    cclient, congress_provider, monkeypatch
):
    class OneDocPerBatch(CongressService):
        def __init__(self, db, provider, **kwargs):
            super().__init__(db, provider, max_docs_per_sync=1, **kwargs)

    # One document per trigger, so the first run leaves a backlog; the ten-minute backlog
    # pause is treated as elapsed while the daily TTL is not.
    monkeypatch.setattr(congress_api, "CongressService", OneDocPerBatch)
    cclient.app.dependency_overrides[get_congress_max_batches] = lambda: 1
    monkeypatch.setattr(congress_service, "BACKLOG_RETRY", timedelta(0))

    first = cclient.post("/api/congress/sync")
    assert first.status_code == 202 and first.json()["syncing"] is True
    status = cclient.get("/api/congress/status").json()
    assert (status["docs_total"], status["docs_pending"], status["syncing"]) == (2, 1, False)

    # Within the TTL but with a document pending: "fetch now" really schedules a run.
    second = cclient.post("/api/congress/sync")
    assert second.status_code == 202 and second.json()["syncing"] is True
    status = cclient.get("/api/congress/status").json()
    assert status["docs_pending"] == 0 and status["docs_no_text"] == 1 and status["trades"] == 2
    assert [c for c in congress_provider.calls if c[0] == "ptr"] == [
        ("ptr", str(TODAY.year), "20039001"),
        ("ptr", str(TODAY.year), "9001234"),
    ]

    # Backlog done, TTL not passed: nothing is scheduled and the response says so.
    calls = len(congress_provider.calls)
    third = cclient.post("/api/congress/sync")
    assert third.json()["syncing"] is False and len(congress_provider.calls) == calls


def test_index_failure_is_reported_as_error_and_stale(cclient, congress_provider):
    congress_provider.fail_index.add(TODAY.year)
    cclient.post("/api/congress/sync")
    body = cclient.get("/api/congress/status").json()
    assert body["stale"] and "simulated failure" in body["error"] and body["trades"] == 0
