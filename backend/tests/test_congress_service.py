"""Congress trade service: sync batches, TTL, failures that keep the last data, reads.

Runs offline with FakeCongressProvider. Names and tickers are invented.
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.data.congress_provider import (
    FakeCongressProvider,
    IndexEntry,
    IndexResult,
    PtrDocument,
    PtrRow,
)
from app.db.models import CongressDoc, CongressSync, CongressTrade
from app.services import congress as congress_service
from app.services.congress import (
    DOC_FAILED,
    DOC_NO_TEXT,
    DOC_PARSED,
    SOURCE,
    CongressService,
)

NOW = datetime(2026, 10, 23, 12, 0)
MODIFIED_2026 = datetime(2026, 10, 22, 13, 0, 37)
MODIFIED_2025 = datetime(2026, 1, 20, 13, 0, 0)


def entry(
    doc_id: str,
    filing_date: date | None,
    year: int = 2026,
    first: str = "Jane",
    last: str = "Doe",
    district: str = "ST01",
    filing_type: str = "P",
) -> IndexEntry:
    return IndexEntry(year, doc_id, filing_type, filing_date, first, last, "Hon.", "", district)


def row(
    symbol: str | None = "QQXA",
    side: str = "buy",
    day: date = date(2026, 9, 20),
    owner: str = "SELF",
    low: int = 1_001,
    high: int | None = 15_000,
) -> PtrRow:
    label = f"${low:,} - ${high:,}" if high else f"Over ${low:,}"
    return PtrRow(
        owner=owner,
        asset_name=f"{symbol or 'Some'} Common Stock ({symbol})",
        asset_type="ST" if symbol else "MF",
        symbol=symbol,
        side=side,
        transaction_date=day,
        notification_date=day + timedelta(days=7),
        amount_low=low,
        amount_high=high,
        amount_label=label,
        filing_status="New",
    )


# Index: A newest, B a scanned filing, C filed in January, D in last year's index within the
# lookback, E too old, F a non-PTR filing, G a withdrawal without a date.
A = entry("20039001", date(2026, 10, 1))
B = entry("9001234", date(2026, 9, 15), first="John", last="Roe", district="CA12")
C = entry("20038002", date(2026, 1, 20))
D = entry("20037001", date(2025, 11, 1), year=2025, first="John", last="Roe", district="CA12")
E = entry("20036001", date(2025, 9, 1), year=2025)
F = entry("10078001", date(2026, 5, 15), filing_type="C")
G = entry("8070", None, first="Rich", last="Aaronson", district="MI04", filing_type="W")

DOCS = {
    "20039001": PtrDocument(rows=[row("QQXA"), row("ZYXW", "sell", date(2026, 9, 25), "SP")]),
    "9001234": PtrDocument(rows=[], no_text=True),
    "20038002": PtrDocument(rows=[row("QQXA", "sell_partial", date(2026, 1, 5), "DC")]),
    "20037001": PtrDocument(
        rows=[row("QQXA", day=date(2025, 10, 20), low=50_000_000, high=None)],
        warnings=["no transaction fields: junk"],
    ),
    "20036001": PtrDocument(rows=[row("OLDX", day=date(2025, 8, 1))]),
}


class Clock:
    def __init__(self, at: datetime = NOW) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    def advance(self, **kwargs) -> None:
        self.at += timedelta(**kwargs)


@pytest.fixture(autouse=True)
def _no_in_flight():
    congress_service._in_flight.clear()


@pytest.fixture
def provider() -> FakeCongressProvider:
    return FakeCongressProvider(
        {
            2026: IndexResult(2026, [A, B, C, F, G], MODIFIED_2026),
            2025: IndexResult(2025, [D, E], MODIFIED_2025),
        },
        dict(DOCS),
    )


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def service(db, provider, clock, sleeps) -> CongressService:
    # Batches follow each other without a real pause in tests; `sleeps` records the pauses.
    return CongressService(db, provider, now=clock, sleep=sleeps.append)


def _doc_calls(provider: FakeCongressProvider) -> list[str]:
    return [c[2] for c in provider.calls if c[0] == "ptr"]


def _index_calls(provider: FakeCongressProvider) -> list[str]:
    return [c[1] for c in provider.calls if c[0] == "index"]


def test_first_sync_stores_trades_docs_and_status(service, provider, db, sleeps):
    result = service.sync()
    assert result.fetched and result.error is None and result.batches == 1
    # Both indexes, then the PTRs within a year, newest filing first; F, G and E are skipped.
    assert provider.calls[:2] == [("index", "2026"), ("index", "2025")]
    assert _doc_calls(provider) == ["20039001", "9001234", "20038002", "20037001"]
    counts = (result.docs_fetched, result.docs_parsed, result.docs_no_text, result.docs_failed)
    assert counts == (4, 3, 1, 0) and result.docs_pending == 0
    assert sleeps == []  # everything fit in one batch

    docs = {d.doc_id: d for d in db.scalars(select(CongressDoc))}
    assert docs["9001234"].status == DOC_NO_TEXT and docs["9001234"].rows == 0
    assert docs["20037001"].status == DOC_PARSED and docs["20037001"].error == "1 row(s) unparsed"
    assert docs["20039001"].member == "Jane Doe" and docs["20039001"].year == 2026

    sync = db.get(CongressSync, SOURCE)
    assert sync.synced_at == NOW and sync.index_modified == MODIFIED_2026
    assert sync.docs_total == 4 and sync.error is None

    status = service.status()
    assert not status.stale and status.error is None and not status.syncing
    assert (status.docs_total, status.docs_parsed, status.docs_no_text) == (4, 3, 1)
    assert status.docs_failed == 0 and status.docs_pending == 0 and status.trades == 4

    trades = service.trades(["qqxa"])
    assert [t.transaction_date for t in trades] == [
        date(2026, 9, 20),
        date(2026, 1, 5),
        date(2025, 10, 20),
    ]
    newest = trades[0]
    assert newest.member == "Jane Doe" and newest.state == "ST" and newest.district == "ST01"
    assert newest.chamber == "house" and newest.party is None and newest.owner == "SELF"
    assert newest.filing_date == date(2026, 10, 1) and newest.doc_id == "20039001"
    assert newest.doc_url.endswith("/ptr-pdfs/2026/20039001.pdf")
    old = trades[2]
    assert old.doc_url.endswith("/ptr-pdfs/2025/20037001.pdf")  # last year's index and path
    assert (old.amount_low, old.amount_high) == (50_000_000, None)
    assert old.amount_label == "Over $50,000,000"
    assert [t.owner for t in service.trades(["ZYXW"])] == ["SP"]


def test_sync_respects_ttl_unless_forced(service, provider, clock):
    service.sync()
    calls = len(provider.calls)
    skipped = service.sync()
    assert not skipped.fetched and skipped.error is None and len(provider.calls) == calls
    clock.advance(hours=25)
    again = service.sync()
    assert again.fetched and again.docs_fetched == 0  # nothing new in the index
    assert len(provider.calls) == calls + 2  # two index reads, no documents
    forced = service.sync(force=True)
    assert forced.fetched and len(provider.calls) == calls + 4


def test_index_failure_keeps_data_and_sets_error_then_retries_after_an_hour(
    service, provider, clock, db
):
    service.sync()
    provider.fail_index.add(2026)
    clock.advance(hours=25)
    result = service.sync()
    assert result.fetched and "simulated failure" in result.error
    assert len(service.trades(["QQXA"])) == 3  # the stored rows stay
    status = service.status()
    assert status.stale and "simulated failure" in status.error
    assert status.synced_at == clock.at and status.index_modified == MODIFIED_2026
    assert status.docs_total == 4

    clock.advance(minutes=30)
    assert not service.sync().fetched  # retried after an hour, not on every request
    clock.advance(minutes=31)
    provider.fail_index.clear()
    result = service.sync()
    assert result.fetched and result.error is None
    assert db.get(CongressSync, SOURCE).error is None and not service.status().stale


def test_nothing_is_written_when_the_first_index_fetch_fails(service, provider, db):
    provider.fail_index.add(2025)
    result = service.sync()
    assert result.fetched and "2025" in result.error
    assert _doc_calls(provider) == []
    assert db.scalars(select(CongressTrade)).all() == []
    assert db.scalars(select(CongressDoc)).all() == []
    sync = db.get(CongressSync, SOURCE)
    assert sync.error and sync.docs_total == 0 and sync.index_modified is None
    status = service.status()
    assert status.stale and status.trades == 0 and status.docs_pending == 0


def test_missing_current_year_index_is_empty_but_missing_last_year_is_an_error(db, provider):
    clock = Clock(datetime(2026, 1, 5, 9, 0))
    service = CongressService(db, provider, now=clock)
    provider.missing_index.add(2026)
    result = service.sync()
    assert result.fetched and result.error is None
    assert _doc_calls(provider) == ["20037001", "20036001"]  # last year's index, both in window
    assert db.get(CongressSync, SOURCE).index_modified == MODIFIED_2025

    provider.missing_index = {2025}
    result = service.sync(force=True)
    assert result.fetched and "HTTP 404" in result.error


def test_failed_documents_are_retried_and_scanned_ones_are_not(db, provider, clock):
    # One batch per trigger here, so the failure is not retried within the same run.
    service = CongressService(db, provider, now=clock, max_batches=1)
    provider.fail_docs.add("20038002")
    first = service.sync()
    assert first.docs_failed == 1 and first.docs_pending == 1
    assert db.get(CongressDoc, (SOURCE, "20038002")).status == DOC_FAILED
    assert len(service.trades(["QQXA"])) == 2

    provider.fail_docs.clear()
    provider.calls.clear()
    clock.advance(hours=25)
    second = service.sync()
    assert _doc_calls(provider) == ["20038002"]  # not the parsed ones, not the scan
    assert second.docs_parsed == 1 and second.docs_pending == 0
    assert db.get(CongressDoc, (SOURCE, "20038002")).status == DOC_PARSED
    assert len(service.trades(["QQXA"])) == 3


def test_batch_cap_leaves_pending_documents_for_the_next_sync(db, provider, clock):
    service = CongressService(db, provider, now=clock, max_docs_per_sync=2, max_batches=1)
    first = service.sync()
    assert _doc_calls(provider) == ["20039001", "9001234"]
    assert first.docs_fetched == 2 and first.docs_pending == 2
    assert service.status().docs_pending == 2 and not service.status().stale
    provider.calls.clear()
    second = service.sync(force=True)
    assert _doc_calls(provider) == ["20038002", "20037001"]
    assert second.docs_pending == 0 and service.status().docs_pending == 0


def test_one_trigger_works_through_the_backlog_in_batches_with_a_pause(db, provider, clock):
    sleeps: list[float] = []
    service = CongressService(
        db, provider, now=clock, max_docs_per_sync=1, pause=1.5, sleep=sleeps.append
    )
    result = service.sync()
    assert result.batches == 4 and result.docs_fetched == 4 and result.docs_pending == 0
    assert (result.docs_parsed, result.docs_no_text, result.docs_failed) == (3, 1, 0)
    assert sleeps == [1.5, 1.5, 1.5]  # a pause between batches, none before the first
    assert _index_calls(provider) == ["2026", "2025"]  # the index is read once per trigger
    assert _doc_calls(provider) == ["20039001", "9001234", "20038002", "20037001"]
    status = service.status()
    assert status.docs_pending == 0 and not status.syncing and status.trades == 4


def test_batching_stops_at_the_cap_and_resumes_on_the_next_trigger(db, provider, clock):
    sleeps: list[float] = []
    service = CongressService(
        db, provider, now=clock, max_docs_per_sync=1, max_batches=2, sleep=sleeps.append
    )
    first = service.sync()
    assert first.batches == 2 and first.docs_fetched == 2 and first.docs_pending == 2
    assert len(sleeps) == 1 and service.status().docs_pending == 2
    second = service.sync(force=True)
    assert second.batches == 2 and second.docs_pending == 0
    assert len(service.trades(["QQXA"])) == 3


def test_batching_stops_on_index_error_and_without_progress(db, provider, clock):
    sleeps: list[float] = []
    service = CongressService(db, provider, now=clock, max_docs_per_sync=1, sleep=sleeps.append)
    provider.fail_index.add(2026)
    result = service.sync()
    assert result.batches == 1 and result.error and sleeps == []

    # Only failing documents left: one batch of retries, then stop instead of spinning.
    provider.fail_index.clear()
    provider.fail_docs.update(DOCS)
    clock.advance(hours=2)
    result = service.sync()
    assert result.batches == 1 and result.docs_failed == 1 and result.docs_pending == 4
    assert sleeps == [] and result.error is None


def test_status_reports_syncing_while_a_run_is_in_flight(service):
    assert not service.status().syncing
    assert service.due()
    congress_service._in_flight.add(SOURCE)
    assert service.status().syncing
    assert not service.due()  # the API must not schedule a second run


def test_pending_backlog_resumes_within_the_ttl_after_a_short_pause(db, provider, clock):
    service = CongressService(db, provider, now=clock, max_docs_per_sync=1, max_batches=1)
    first = service.sync()
    assert first.docs_pending == 3
    # Right after a run nothing is due, even with a backlog: the Clerk's site gets a pause.
    assert not service.due() and not service.sync().fetched
    clock.advance(minutes=10)
    assert service.due()
    second = service.sync()
    assert second.fetched and second.docs_fetched == 1 and second.docs_pending == 2
    assert _index_calls(provider) == ["2026", "2025", "2026", "2025"]  # once per run
    # Once the backlog is done the daily TTL applies again.
    clock.advance(minutes=10)
    service = CongressService(db, provider, now=clock, max_docs_per_sync=5)
    assert service.sync().docs_pending == 0
    clock.advance(hours=3)
    assert not service.due() and not service.sync().fetched
    clock.advance(hours=22)
    assert service.due()


def test_backlog_does_not_shorten_the_retry_after_an_error(db, provider, clock):
    service = CongressService(db, provider, now=clock, max_docs_per_sync=1, max_batches=1)
    service.sync()
    provider.fail_index.add(2026)
    clock.advance(minutes=10)
    assert service.sync().error
    clock.advance(minutes=30)
    assert not service.due()  # an hour, not ten minutes, after a failure
    clock.advance(minutes=31)
    assert service.due()


def test_failed_documents_wait_for_the_daily_ttl_not_the_backlog_pause(db, provider, clock):
    service = CongressService(db, provider, now=clock, max_batches=1)
    provider.fail_docs.add("20038002")
    result = service.sync()
    assert result.docs_failed == 1 and result.docs_pending == 1
    assert service.status().docs_pending == 1  # still shown as pending on the status
    clock.advance(minutes=10)
    assert not service.due()  # only never-downloaded documents shorten the wait
    clock.advance(hours=24)
    assert service.due()


def test_existing_dotted_symbols_are_normalised_on_the_next_sync(service, provider, db):
    service.sync()
    old = db.scalars(select(CongressTrade).where(CongressTrade.symbol == "ZYXW")).one()
    old.symbol = "BRK.B"  # stored before tickers were normalised
    slashed = db.scalars(select(CongressTrade).where(CongressTrade.doc_id == "20038002")).one()
    slashed.symbol = "mog/a"
    db.commit()
    assert service.trades(["BRK-B"]) == [] and service.trades(["MOG-A"]) == []
    service.sync(force=True)
    assert [t.symbol for t in service.trades(["BRK-B"])] == ["BRK-B"]
    assert [t.symbol for t in service.trades(["MOG-A"])] == ["MOG-A"]
    # Lookups accept the Clerk's spelling too.
    assert [t.symbol for t in service.trades(["brk.b", " mog/a "])] == ["BRK-B", "MOG-A"]
    odd = select(CongressTrade).where(
        CongressTrade.symbol.like("%.%") | CongressTrade.symbol.like("%/%")
    )
    assert db.scalars(odd).all() == []


def test_documents_parsed_before_a_parser_change_are_read_again_once(db, provider, clock):
    # Once the cut-off has passed, everything stored before it is re-read; the cut-off here is
    # one hour from now, as if the parser were about to change.
    service = CongressService(
        db, provider, now=clock, max_docs_per_sync=3, reparse_before=NOW + timedelta(hours=1)
    )
    first = service.sync()
    assert sorted(_doc_calls(provider)) == ["20037001", "20038002", "20039001", "9001234"]
    assert first.batches == 2 and first.docs_pending == 0

    # Before the cut-off nothing is waiting; after it the stored documents make a run due
    # after the backlog pause, not the daily TTL.
    clock.advance(minutes=10)
    assert not service.due()
    clock.advance(minutes=60)
    assert service.due()

    provider.calls.clear()
    # The parser now reads the newest document differently, and the Clerk has dropped D
    # (20037001) from last year's index.
    provider.docs["20039001"] = PtrDocument(rows=[row("QQXA", day=date(2026, 9, 28))])
    provider.indexes[2025] = IndexResult(2025, [E], MODIFIED_2025)
    second = service.sync()
    # The listed parsed documents are re-read (not the scan, not the unlisted one).
    assert sorted(_doc_calls(provider)) == ["20038002", "20039001"]
    assert (second.batches, second.docs_parsed, second.docs_pending) == (1, 2, 0)
    rows = db.scalars(select(CongressTrade).where(CongressTrade.doc_id == "20039001")).all()
    assert [(r.row_no, r.transaction_date) for r in rows] == [(0, date(2026, 9, 28))]
    assert service.trades(["ZYXW"]) == []  # the old rows of that document are gone
    assert len(service.trades(["QQXA"])) == 3  # the unlisted document's rows stay

    # Nothing is waiting any more (the unlisted document stops counting), so the daily TTL
    # applies again, and the next run reads nothing.
    clock.advance(minutes=10)
    assert not service.due()
    provider.calls.clear()
    clock.advance(hours=25)
    third = service.sync()
    assert _doc_calls(provider) == [] and third.docs_pending == 0

    # The default cut-off lies before any document these tests store: no re-read.
    assert congress_service.REPARSE_BEFORE < NOW


def test_reparsing_a_document_replaces_its_rows_without_duplicates(service, provider, db):
    service.sync()
    doc = db.get(CongressDoc, (SOURCE, "20039001"))
    doc.status = DOC_FAILED  # as if the first parse had failed
    db.commit()
    provider.docs["20039001"] = PtrDocument(rows=[row("QQXA", day=date(2026, 9, 28))])
    service.sync(force=True)
    rows = db.scalars(select(CongressTrade).where(CongressTrade.doc_id == "20039001")).all()
    assert [(r.row_no, r.transaction_date) for r in rows] == [(0, date(2026, 9, 28))]
    assert service.trades(["ZYXW"]) == []
    assert db.get(CongressDoc, (SOURCE, "20039001")).status == DOC_PARSED


def test_trades_filters_by_symbol_date_and_limit(service):
    service.sync()
    assert service.trades([]) == []
    assert service.trades(["NOPE"]) == []
    since = service.trades(["QQXA"], since=date(2026, 1, 1))
    assert [t.transaction_date for t in since] == [date(2026, 9, 20), date(2026, 1, 5)]
    both = service.trades(["QQXA", "ZYXW"], limit=2)
    assert [(t.symbol, t.transaction_date) for t in both] == [
        ("ZYXW", date(2026, 9, 25)),
        ("QQXA", date(2026, 9, 20)),
    ]


def test_concurrent_sync_is_skipped_while_one_is_running(service, provider):
    congress_service._in_flight.add(SOURCE)
    result = service.sync()
    assert not result.fetched and provider.calls == []
    congress_service._in_flight.clear()
    assert service.sync().fetched


def test_status_before_any_sync_and_staleness_after_three_days(service, clock):
    status = service.status()
    assert status.stale and status.synced_at is None and status.trades == 0
    service.sync()
    clock.advance(days=2)
    assert not service.status().stale
    clock.advance(days=2)
    assert service.status().stale
