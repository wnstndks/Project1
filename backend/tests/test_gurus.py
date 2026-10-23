"""Well-known investor holdings: parsing, fund combination, 13F quirks, TTL and caching.

Everything runs offline: HTTP goes through httpx MockTransport, the service gets
FakeGuruProvider and FakeCusipResolver.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx2 as httpx
import pytest
from sqlalchemy import select

from app.data import guru_provider as gp
from app.data.guru_provider import (
    ArkProvider,
    FakeCusipResolver,
    FakeGuruProvider,
    GuruDataError,
    GuruHolding,
    GuruSnapshot,
    OpenFigiClient,
    Sec13FProvider,
    choose_filings,
    combine_funds,
    parse_13f_table,
    parse_ark_csv,
)
from app.data.gurus import GURUS, Guru, find_guru
from app.db.models import CusipTicker, GuruHoldingRecord, GuruSync
from app.services import gurus as gurus_service
from app.services.errors import NotFoundError
from app.services.gurus import SEC_UA_MISSING, GuruService

FIXTURES = Path(__file__).parent / "fixtures" / "gurus"
NOW = datetime(2026, 10, 22, 12, 0)
ARK_DAY = date(2026, 10, 22)
UA = "asset-manager-test admin@example.com"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _no_in_flight():
    gurus_service._in_flight.clear()


# --- investor list ---------------------------------------------------------------------------


def test_guru_list_is_consistent():
    assert len({g.id for g in GURUS}) == len(GURUS)
    for g in GURUS:
        if g.source == "ark":
            assert g.funds and all(f in gp.ARK_FUND_FILES for f in g.funds)
        else:
            assert g.cik and len(g.cik) == 10 and g.cik.isdigit()
    assert find_guru("warren-buffett").cik == "0001067983"
    assert find_guru("nobody") is None


# --- ARK CSV -----------------------------------------------------------------------------------


def test_parse_ark_csv_skips_footer_and_normalises_tickers():
    fund = parse_ark_csv(fixture("ark_arkk.csv"), "ARKK")
    assert fund.as_of == ARK_DAY
    assert len(fund.rows) == 10  # disclaimer footer dropped
    by_name = {r.name: r for r in fund.rows}
    assert by_name["ROCKET LAB"].symbol == "RKLB"  # "RKLB UQ"
    assert by_name["ARCTURUS THERAPEUTICS HOLDIN"].symbol == "ARCT"
    openai = by_name["OPENAI GROUP PBC SERIES C"]
    assert openai.symbol is None and openai.cusip == "PPOPENAIC"
    assert by_name["TESLA INC"].shares == 1000 and by_name["TESLA INC"].value_usd == 400_000
    assert by_name["TESLA INC"].weight == pytest.approx(0.4)
    assert sum(r.weight for r in fund.rows) == pytest.approx(1.0)


def test_parse_ark_csv_rejects_unexpected_layout():
    with pytest.raises(GuruDataError, match="unexpected columns"):
        parse_ark_csv("foo,bar\n1,2\n", "ARKK")
    with pytest.raises(GuruDataError, match="no holdings rows"):
        parse_ark_csv("date,fund,company,ticker,cusip,shares,market value ($),weight (%)\n", "X")


def test_combine_funds_weights_by_market_value():
    arkk = parse_ark_csv(fixture("ark_arkk.csv"), "ARKK")
    arkw = parse_ark_csv(fixture("ark_arkw.csv"), "ARKW")
    snap = combine_funds([arkk, arkw])
    assert snap.as_of == ARK_DAY and snap.source == "ark" and snap.note is None
    by_symbol = {h.symbol: h for h in snap.holdings if h.symbol}
    total = 1_000_000 + 400_000
    tsla = by_symbol["TSLA"]
    assert tsla.shares == 1500 and tsla.value_usd == 600_000
    assert tsla.weight == pytest.approx(600_000 / total)
    assert by_symbol["DKNG"].weight == pytest.approx(50_000 / total)
    assert snap.holdings[0].symbol == "TSLA"  # largest first
    assert sum(h.weight for h in snap.holdings) == pytest.approx(1.0)
    # Cash and private rows survive, keyed apart from tickers.
    assert any(h.symbol is None and h.cusip == "X9USDGSFT" for h in snap.holdings)


def test_combine_funds_excludes_fund_files_that_stopped_updating():
    arkk = parse_ark_csv(fixture("ark_arkk.csv"), "ARKK")
    stale = parse_ark_csv(fixture("ark_arkw.csv").replace("10/22/2026", "09/01/2026"), "ARKW")
    snap = combine_funds([arkk, stale])
    assert snap.as_of == ARK_DAY
    assert "ARKW(2026-09-01)" in snap.note
    tsla = next(h for h in snap.holdings if h.symbol == "TSLA")
    assert tsla.shares == 1000 and tsla.weight == pytest.approx(0.4)
    assert not any(h.symbol == "DKNG" for h in snap.holdings)


def _ark_transport(fail: set[str] = frozenset()):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        path = str(req.url).rsplit("/", 1)[-1]
        fund = next(f for f, p in gp.ARK_FUND_FILES.items() if p == path)
        if fund in fail:
            return httpx.Response(503, text="unavailable")
        body = fixture(f"ark_{fund.lower()}.csv")
        return httpx.Response(200, content=body.encode("utf-8-sig"))

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_ark_provider_fetches_each_fund_and_combines():
    http, seen = _ark_transport()
    guru = Guru("cw", "캐시 우드", "Cathie Wood", "ark", funds=("ARKK", "ARKW"))
    snap = ArkProvider(http=http).fetch(guru)
    assert [str(r.url) for r in seen] == [
        gp.ARK_BASE + gp.ARK_FUND_FILES["ARKK"],
        gp.ARK_BASE + gp.ARK_FUND_FILES["ARKW"],
    ]
    assert next(h for h in snap.holdings if h.symbol == "TSLA").shares == 1500


def test_ark_provider_fails_whole_fetch_when_one_fund_fails():
    http, seen = _ark_transport(fail={"ARKW"})
    guru = Guru("cw", "캐시 우드", "Cathie Wood", "ark", funds=("ARKK", "ARKW"))
    with pytest.raises(GuruDataError, match="ARKW: HTTP 503"):
        ArkProvider(http=http).fetch(guru)
    assert len(seen) == 3  # ARKK once, ARKW retried once


# --- 13F ---------------------------------------------------------------------------------------


def test_parse_13f_table_sums_by_cusip_and_excludes_options_and_debt():
    rows = {r.cusip: r for r in parse_13f_table(fixture("13f_table.xml").encode(), False)}
    assert set(rows) == {"037833100", "084670702"}  # HAL call option and PRN note dropped
    assert rows["037833100"].value_usd == 900_000 and rows["037833100"].shares == 3000
    assert rows["084670702"].name == "BERKSHIRE HATHAWAY INC"


def test_parse_13f_table_scales_pre_2023_thousands():
    rows = {r.cusip: r for r in parse_13f_table(fixture("13f_table.xml").encode(), True)}
    assert rows["037833100"].value_usd == 900_000_000


def test_parse_13f_table_rejects_other_xml():
    with pytest.raises(GuruDataError, match="unexpected root"):
        parse_13f_table(b"<edgarSubmission/>", False)
    with pytest.raises(GuruDataError, match="invalid XML"):
        parse_13f_table(b"<informationTable>", False)


RECENT = {
    "form": ["4", "13F-HR/A", "13F-HR", "13F-HR/A", "13F-HR"],
    "accessionNumber": [
        "0000000000-26-000001",
        "0001193125-26-400000",
        "0001193125-26-352200",
        "0000950123-26-008361",
        "0001193125-26-226661",
    ],
    "filingDate": ["2026-09-10", "2026-09-01", "2026-08-14", "2026-08-01", "2026-05-15"],
    "reportDate": ["2026-09-09", "2026-06-30", "2026-06-30", "2026-03-31", "2026-03-31"],
}


def test_choose_filings_takes_latest_quarter_and_its_later_amendments():
    chosen = choose_filings(RECENT)
    assert [f.accession for f in chosen] == ["0001193125-26-352200", "0001193125-26-400000"]
    assert chosen[0].report_date == date(2026, 6, 30) and not chosen[0].in_thousands
    assert (
        choose_filings(
            {
                "form": ["4"],
                "accessionNumber": ["x"],
                "filingDate": ["2026-01-01"],
                "reportDate": ["2026-01-01"],
            }
        )
        == []
    )


def test_choose_filings_marks_old_filings_as_thousands():
    recent = {
        "form": ["13F-HR"],
        "accessionNumber": ["0001-22-1"],
        "filingDate": ["2022-11-14"],
        "reportDate": ["2022-09-30"],
    }
    assert choose_filings(recent)[0].in_thousands


def _sec_transport(amendment_type: str = "NEW HOLDINGS"):
    seen = []
    cik = "0001067983"
    base = "https://www.sec.gov/Archives/edgar/data/1067983/"
    original, amendment = "000119312526352200", "000119312526400000"
    primary = fixture("13f_amendment_primary.xml").replace("NEW HOLDINGS", amendment_type)
    routes = {
        f"https://data.sec.gov/submissions/CIK{cik}.json": json.dumps(
            {"filings": {"recent": RECENT}}
        ),
        base + original + "/index.json": json.dumps(
            {"directory": {"item": [{"name": "primary_doc.xml"}, {"name": "56757.xml"}]}}
        ),
        base + original + "/56757.xml": fixture("13f_table.xml"),
        base + amendment + "/primary_doc.xml": primary,
        base + amendment + "/index.json": json.dumps(
            {"directory": {"item": [{"name": "infotable.xml"}, {"name": "primary_doc.xml"}]}}
        ),
        base + amendment + "/infotable.xml": fixture("13f_amendment_table.xml"),
    }

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        body = routes.get(str(req.url))
        return httpx.Response(200, text=body) if body else httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": UA})
    return client, seen


def test_sec_provider_merges_new_holdings_amendment():
    http, seen = _sec_transport()
    snap = Sec13FProvider(UA, http=http).fetch(find_guru("warren-buffett"))
    assert snap.as_of == date(2026, 6, 30) and snap.source == "13f"
    assert all(r.headers["User-Agent"] == UA for r in seen)
    by_cusip = {h.cusip: h for h in snap.holdings}
    assert set(by_cusip) == {"037833100", "084670702", "91324P102"}
    assert all(h.symbol is None for h in snap.holdings)  # tickers come from the resolver
    assert by_cusip["037833100"].weight == pytest.approx(900_000 / 1_100_000)
    assert snap.holdings[0].cusip == "037833100"


def test_sec_provider_restatement_replaces_table():
    http, _ = _sec_transport("RESTATEMENT")
    snap = Sec13FProvider(UA, http=http).fetch(find_guru("warren-buffett"))
    assert [h.cusip for h in snap.holdings] == ["91324P102"]


def test_sec_provider_requires_user_agent():
    with pytest.raises(GuruDataError, match="AM_SEC_USER_AGENT"):
        Sec13FProvider("  ").fetch(find_guru("warren-buffett"))


def test_sec_provider_reports_http_errors():
    http = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(403)))
    with pytest.raises(GuruDataError, match="HTTP 403"):
        Sec13FProvider(UA, http=http).fetch(find_guru("warren-buffett"))


# --- OpenFIGI ----------------------------------------------------------------------------------


def _figi_item(ticker: str, exch: str = "US", name: str = "X") -> dict:
    return {"ticker": ticker, "exchCode": exch, "name": name}


def test_openfigi_batches_prefers_us_listing_and_spaces_requests():
    seen: list[list[dict]] = []
    sleeps: list[float] = []
    ticks = iter(range(0, 10_000, 1))  # clock advances 1s per call, under the 2.5s spacing

    def handler(req: httpx.Request) -> httpx.Response:
        jobs = json.loads(req.content)
        seen.append(jobs)
        out = []
        for job in jobs:
            c = job["idValue"]
            if c == "084670702":
                out.append({"data": [_figi_item("BRK/B", "UN"), _figi_item("BRK/B", "US")]})
            elif c == "PPOPENAIC":
                out.append({"error": "Invalid idValue format."})
            elif c == "G6683N103":
                out.append({"warning": "No identifier found."})
            else:
                out.append({"data": [_figi_item("T" + c[-3:], "US", name=f"N{c}")]})
        return httpx.Response(200, json=out)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenFigiClient(http=http, sleep=sleeps.append, clock=lambda: float(next(ticks)))
    OpenFigiClient._last_request = 0.0
    cusips = [f"{i:09d}" for i in range(20)] + ["084670702", "PPOPENAIC", "G6683N103"]
    result = client.map_cusips(cusips + ["000000000"])  # duplicate is asked once
    assert [len(j) for j in seen] == [10, 10, 3]
    assert all(j["exchCode"] == "US" and j["idType"] == "ID_CUSIP" for jobs in seen for j in jobs)
    assert result["084670702"] == ("BRK-B", "X")  # US composite, Yahoo-style class suffix
    assert result["PPOPENAIC"] == (None, None) and result["G6683N103"] == (None, None)
    assert result["000000005"] == ("T005", "N000000005")
    assert len(sleeps) == 3 and all(s > 0 for s in sleeps)  # kept under 25 requests/minute


def test_openfigi_waits_out_rate_limit_once_and_sends_key_header():
    responses = iter(
        [
            httpx.Response(429, headers={"ratelimit-reset": "7"}),
            httpx.Response(200, json=[{"data": [_figi_item("AAPL")]}]),
        ]
    )
    headers = []

    def handler(req: httpx.Request) -> httpx.Response:
        headers.append(req.headers)
        return next(responses)

    sleeps = []
    client = OpenFigiClient(api_key="k", http=None, sleep=sleeps.append, clock=lambda: 1e9)
    client.http = httpx.Client(
        transport=httpx.MockTransport(handler), headers={"X-OPENFIGI-APIKEY": "k"}
    )
    assert client.batch == 100
    assert client.map_cusips(["037833100"]) == {"037833100": ("AAPL", "X")}
    assert 7.0 in sleeps
    assert all(h["X-OPENFIGI-APIKEY"] == "k" for h in headers)


def test_openfigi_gives_up_with_clear_error():
    http = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(429)))
    client = OpenFigiClient(http=http, sleep=lambda s: None, clock=lambda: 1e9)
    with pytest.raises(GuruDataError, match="rate limited"):
        client.map_cusips(["037833100"])


# --- service -------------------------------------------------------------------------------------


def h(symbol, cusip, name, shares, value, weight) -> GuruHolding:
    return GuruHolding(symbol, cusip, name, shares, value, weight)


ARK_SNAPSHOT = GuruSnapshot(
    ARK_DAY,
    "ark",
    [
        h("TSLA", "88160R101", "TESLA INC", 1500, 600_000, 0.6),
        h("COIN", "19260Q107", "COINBASE", 1000, 300_000, 0.3),
        h(None, "X9USDGSFT", "GOLDMAN TRSY", 100_000, 100_000, 0.1),
    ],
    note=None,
)
Q2 = date(2026, 6, 30)
SEC_SNAPSHOT = GuruSnapshot(
    Q2,
    "13f",
    [
        h(None, "037833100", "APPLE INC", 3000, 900_000, 0.75),
        h(None, "084670702", "BERKSHIRE HATHAWAY INC", 200, 200_000, 1 / 6),
        h(None, "G6683N103", "NU HOLDINGS", 100, 100_000, 1 / 12),
    ],
)


class Clock:
    def __init__(self, at: datetime = NOW) -> None:
        self.at = at

    def __call__(self) -> datetime:
        return self.at

    def advance(self, **kwargs) -> None:
        self.at += timedelta(**kwargs)


@pytest.fixture
def provider() -> FakeGuruProvider:
    return FakeGuruProvider({"cathie-wood": ARK_SNAPSHOT, "warren-buffett": SEC_SNAPSHOT})


@pytest.fixture
def resolver() -> FakeCusipResolver:
    return FakeCusipResolver(
        {"037833100": ("AAPL", "APPLE INC"), "084670702": ("BRK-B", "BERKSHIRE HATHAWAY INC-CL B")}
    )


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def service(db, provider, resolver, clock) -> GuruService:
    return GuruService(db, provider, resolver, now=clock)


def test_sync_stores_snapshot_and_list_reports_status(service, provider, db):
    result = service.sync("cathie-wood")
    assert result.fetched and result.error is None and result.as_of == ARK_DAY
    rows = service.holdings("cathie-wood")
    assert [r.symbol for r in rows] == ["TSLA", "COIN", None]
    status = {s.guru.id: s for s in service.list_all()}
    cw = status["cathie-wood"]
    assert cw.as_of == ARK_DAY and cw.error is None and not cw.stale and cw.holdings_count == 3
    assert cw.synced_at == NOW
    wb = status["warren-buffett"]
    assert wb.as_of is None and wb.stale and wb.holdings_count == 0 and wb.error is None


def test_sync_respects_ttl_unless_forced(service, provider, clock):
    service.sync("cathie-wood")
    assert service.sync("cathie-wood").fetched is False
    assert provider.calls == ["cathie-wood"]
    assert service.sync("cathie-wood", force=True).fetched
    clock.advance(hours=25)
    service.sync("cathie-wood")
    assert provider.calls == ["cathie-wood"] * 3


def test_13f_ttl_is_a_week(service, provider, clock):
    service.sync("warren-buffett")
    clock.advance(days=6)
    assert service.sync("warren-buffett").fetched is False
    clock.advance(days=2)
    assert service.sync("warren-buffett").fetched
    assert provider.calls == ["warren-buffett"] * 2


def test_failed_sync_keeps_previous_holdings_and_marks_stale(service, provider, clock, db):
    service.sync("cathie-wood")
    provider.fail.add("cathie-wood")
    clock.advance(hours=25)
    result = service.sync("cathie-wood")
    assert result.fetched and "simulated failure" in result.error and result.as_of == ARK_DAY
    assert [r.symbol for r in service.holdings("cathie-wood")] == ["TSLA", "COIN", None]
    status = next(s for s in service.list_all() if s.guru.id == "cathie-wood")
    assert status.stale and status.error == "cathie-wood: simulated failure"
    assert status.as_of == ARK_DAY and status.synced_at == clock.at
    # A later success clears the error; failures are retried after an hour.
    provider.fail.clear()
    clock.advance(hours=2)
    assert service.sync("cathie-wood").error is None
    assert db.get(GuruSync, "cathie-wood").error is None


def test_old_snapshot_is_stale_even_after_successful_sync(service, clock):
    service.sync("cathie-wood")
    clock.advance(days=8)
    assert next(s for s in service.list_all() if s.guru.id == "cathie-wood").stale


def test_snapshot_note_is_stored(service, provider, db):
    provider.snapshots["cathie-wood"] = GuruSnapshot(
        ARK_DAY, "ark", ARK_SNAPSHOT.holdings, note="갱신이 멈춘 펀드 파일 제외: ARKF(2026-01-02)"
    )
    service.sync("cathie-wood")
    assert "ARKF" in next(s for s in service.list_all() if s.guru.id == "cathie-wood").note


def test_13f_investors_are_skipped_without_sec_user_agent(db, provider, resolver, clock):
    service = GuruService(db, provider, resolver, now=clock, sec_configured=False)
    result = service.sync("warren-buffett")
    assert result.fetched is False and result.error == SEC_UA_MISSING
    assert provider.calls == []
    status = {s.guru.id: s for s in service.list_all()}
    assert status["warren-buffett"].error == SEC_UA_MISSING and status["warren-buffett"].stale
    assert status["cathie-wood"].error is None
    results = service.sync_all()
    assert provider.calls == ["cathie-wood"]
    assert all(r.error == SEC_UA_MISSING for g, r in results.items() if g != "cathie-wood")


def test_13f_sync_resolves_tickers_through_cache_then_resolver(service, resolver, db, clock):
    db.add(CusipTicker(cusip="037833100", symbol="AAPL", name="APPLE INC", resolved_at=NOW))
    db.commit()
    service.sync("warren-buffett")
    # Only the two unknown CUSIPs were asked, largest position first.
    assert resolver.calls == [["084670702", "G6683N103"]]
    rows = service.holdings("warren-buffett")
    assert [(r.symbol, r.cusip) for r in rows] == [
        ("AAPL", "037833100"),
        ("BRK-B", "084670702"),
        (None, "G6683N103"),
    ]
    cached = {c.cusip: c for c in db.scalars(select(CusipTicker))}
    assert cached["084670702"].symbol == "BRK-B" and cached["084670702"].resolved_at == NOW
    assert cached["G6683N103"].symbol is None  # a miss is cached too

    # A miss is not asked again for a month, then retried.
    clock.advance(days=8)
    service.sync("warren-buffett")
    assert resolver.calls == [["084670702", "G6683N103"]]
    clock.advance(days=30)
    service.sync("warren-buffett")
    assert resolver.calls[-1] == ["G6683N103"]


def test_resolution_budget_continues_on_later_calls(db, provider, resolver, clock):
    service = GuruService(db, provider, resolver, now=clock, max_resolve_per_sync=1)
    service.sync("warren-buffett")
    assert resolver.calls == [["037833100"]]
    assert [r.symbol for r in service.holdings("warren-buffett")] == ["AAPL", None, None]
    # Within the TTL nothing is fetched, but the next unmapped CUSIP gets its turn.
    result = service.sync("warren-buffett")
    assert result.fetched is False
    assert resolver.calls == [["037833100"], ["084670702"]]
    assert [r.symbol for r in service.holdings("warren-buffett")] == ["AAPL", "BRK-B", None]
    assert provider.calls == ["warren-buffett"]


def test_resolver_failure_does_not_fail_the_sync(db, provider, clock):
    class Broken:
        def map_cusips(self, cusips):
            raise GuruDataError("OpenFIGI: rate limited")

    service = GuruService(db, provider, Broken(), now=clock)
    result = service.sync("warren-buffett")
    assert result.error is None and result.as_of == Q2
    assert all(r.symbol is None for r in service.holdings("warren-buffett"))


def test_sync_without_resolver_leaves_tickers_unmapped(db, provider, clock):
    service = GuruService(db, provider, None, now=clock)
    service.sync("warren-buffett")
    assert all(r.symbol is None for r in service.holdings("warren-buffett"))


def test_sync_replaces_old_snapshot_rows(service, provider, clock, db):
    service.sync("cathie-wood")
    provider.snapshots["cathie-wood"] = GuruSnapshot(
        ARK_DAY + timedelta(days=1), "ark", [h("TSLA", "88160R101", "TESLA INC", 1, 1.0, 1.0)]
    )
    clock.advance(hours=25)
    service.sync("cathie-wood")
    rows = db.scalars(select(GuruHoldingRecord)).all()
    assert len(rows) == 1 and rows[0].as_of == ARK_DAY + timedelta(days=1)


def test_overlap_matches_my_symbols_case_insensitively(service):
    service.sync("cathie-wood")
    service.sync("warren-buffett")
    overlap = service.overlap(["tsla", "AAPL", "MSFT"])
    assert set(overlap) == {"cathie-wood", "warren-buffett"}
    assert [x.symbol for x in overlap["cathie-wood"]] == ["TSLA"]
    assert [x.symbol for x in overlap["warren-buffett"]] == ["AAPL"]
    assert service.overlap([]) == {}
    assert service.overlap(["MSFT"]) == {}


def test_sync_all_covers_every_investor(service, provider, clock):
    results = service.sync_all()
    assert set(results) == {g.id for g in GURUS}
    assert results["cathie-wood"].error is None and results["warren-buffett"].error is None
    assert "no fake snapshot" in results["ray-dalio"].error
    assert sorted(provider.calls) == sorted(g.id for g in GURUS)
    # Failures are retried after an hour, not on every call; successes wait for the TTL.
    results = service.sync_all()
    assert not results["cathie-wood"].fetched and not results["ray-dalio"].fetched
    clock.advance(hours=2)
    results = service.sync_all()
    assert results["cathie-wood"].fetched is False and results["ray-dalio"].fetched


def test_unknown_investor(service):
    with pytest.raises(NotFoundError):
        service.holdings("nobody")
    with pytest.raises(NotFoundError):
        service.sync("nobody")
