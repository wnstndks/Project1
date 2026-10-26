"""Public holdings of well-known investors: ARK ETF CSVs and SEC EDGAR 13F filings.

All HTTP for this feature lives here (ARK, EDGAR, OpenFIGI), behind `GuruProvider`, so the
service and tests never touch the network. Nothing is scraped from web pages: ARK's CSVs are
the files behind its "download holdings" buttons, EDGAR's submissions JSON and filing
archives are official APIs, and OpenFIGI is Bloomberg's open symbology service.

Source quirks found on 2026-10-22 and handled below:
- ARK tickers sometimes carry a Bloomberg exchange suffix ("RKLB UQ"); cash, futures and
  private placements have no ticker. Some fund files stop updating (ARKF/ARKX were last
  modified 2026-01-02), so funds much older than the freshest one are left out of the combined
  portfolio and named in the snapshot note instead of being shown as current.
- 13F tables repeat an issuer once per reporting sub-manager (Berkshire lists Apple 12 times),
  so rows are summed by CUSIP. Options (`putCall`) and debt principal (`PRN`) are excluded.
  Values are whole dollars since the 2023-01-03 EDGAR release; older filings used thousands.
- A 13F-HR/A is either a RESTATEMENT (replaces the table) or NEW HOLDINGS (adds rows that
  were confidential), so the amendment type decides whether to merge or replace.
- Some filers (Norges Bank, 2026-10-23) file a quarter under confidential treatment: the
  original 13F-HR has an empty table and the rows appear a year later as a NEW HOLDINGS
  amendment. The newest quarter with rows is used instead, at most MAX_QUARTERS_BACK back.
- The submissions JSON names the filer (`name`, `formerNames`); a CIK whose name does not
  contain the investor's `expected_name` is refused ("CIK 불일치") before any table is read.
- SEC rejects requests without a declared User-Agent of the form "app contact@domain".
"""

import csv
import io
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Protocol

import httpx2 as httpx

from app.data.gurus import Guru

log = logging.getLogger(__name__)

TIMEOUT = 20.0
ATTEMPTS = 2  # one retry


class GuruDataError(Exception):
    """A holdings source failed, is misconfigured or returned something unparseable."""


class EmptyTableError(GuruDataError):
    """A 13F information table with no equity rows (confidential treatment)."""


# Error prefix for a CIK whose EDGAR name does not match the investor; the service does not
# retry these hourly since only a code change can fix them.
CIK_MISMATCH = "CIK 불일치"
# Quarters to step back when the newest 13F table is empty.
MAX_QUARTERS_BACK = 2


@dataclass(frozen=True)
class GuruHolding:
    symbol: str | None  # Yahoo-style ticker (BRK-B); None for cash, private or unresolved rows
    cusip: str | None
    name: str
    shares: float
    value_usd: float
    weight: float  # share of the snapshot's total value, 0..1


@dataclass(frozen=True)
class GuruSnapshot:
    as_of: date
    source: str  # "ark" | "13f"
    holdings: list[GuruHolding]
    # Non-fatal caveats about this snapshot, e.g. funds excluded as stale.
    note: str | None = None


class GuruProvider(Protocol):
    def fetch(self, guru: Guru) -> GuruSnapshot:
        """The investor's latest public holdings. Raises GuruDataError on failure."""
        ...


class CusipResolver(Protocol):
    def map_cusips(self, cusips: list[str]) -> dict[str, tuple[str | None, str | None]]:
        """CUSIP -> (US ticker or None, issuer name or None). Missing keys were not attempted."""
        ...


def _client(headers: dict[str, str] | None = None) -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, headers=headers or {}, follow_redirects=False)


def _get(http: httpx.Client, url: str, what: str) -> httpx.Response:
    """GET with one retry on transport errors and 5xx. 4xx is final."""
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            res = http.get(url)
        except httpx.HTTPError as exc:
            last = exc
            continue
        if res.status_code >= 500 and attempt + 1 < ATTEMPTS:
            last = GuruDataError(f"{what}: HTTP {res.status_code}")
            continue
        if res.status_code != 200:
            raise GuruDataError(f"{what}: HTTP {res.status_code}")
        return res
    raise GuruDataError(f"{what}: {last}") from last


# --- ARK -----------------------------------------------------------------------------------

ARK_BASE = "https://assets.ark-funds.com/fund-documents/funds-etf-csv/"
ARK_FUND_FILES = {
    "ARKK": "ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv",
    "ARKW": "ARK_NEXT_GENERATION_INTERNET_ETF_ARKW_HOLDINGS.csv",
    "ARKG": "ARK_GENOMIC_REVOLUTION_ETF_ARKG_HOLDINGS.csv",
    "ARKQ": "ARK_AUTONOMOUS_TECH._%26_ROBOTICS_ETF_ARKQ_HOLDINGS.csv",
    "ARKF": "ARK_FINTECH_INNOVATION_ETF_ARKF_HOLDINGS.csv",
    "ARKX": "ARK_SPACE_EXPLORATION_%26_INNOVATION_ETF_ARKX_HOLDINGS.csv",
}
# A fund file this much older than the freshest fund's file is no longer maintained.
ARK_MAX_FUND_LAG = timedelta(days=7)


@dataclass(frozen=True)
class FundHoldings:
    fund: str
    as_of: date
    rows: list[GuruHolding]  # weights are within this fund


def _money(text: str) -> float | None:
    cleaned = re.sub(r"[,$%\s]", "", text or "")
    if cleaned in ("", "-"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _ark_symbol(ticker: str) -> str | None:
    # "RKLB UQ" -> "RKLB": ARK appends Bloomberg exchange codes to some tickers.
    first = (ticker or "").strip().split()
    return first[0].upper() if first else None


def parse_ark_csv(text: str, fund: str) -> FundHoldings:
    """One ARK fund file. Rows whose date column is not a date (the disclaimer footer) are
    skipped; weight is each row's share of the file's market value."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames:
        raise GuruDataError(f"ARK {fund}: empty CSV")
    cols = {name.strip().lower(): name for name in reader.fieldnames}
    try:
        c_date, c_company, c_ticker, c_cusip, c_shares = (
            cols["date"],
            cols["company"],
            cols["ticker"],
            cols["cusip"],
            cols["shares"],
        )
        c_value = next(v for k, v in cols.items() if k.startswith("market value"))
    except (KeyError, StopIteration) as exc:
        raise GuruDataError(f"ARK {fund}: unexpected columns {reader.fieldnames}") from exc

    as_of: date | None = None
    raw: list[tuple[str | None, str | None, str, float, float]] = []
    for row in reader:
        try:
            day = datetime.strptime((row.get(c_date) or "").strip(), "%m/%d/%Y").date()
        except ValueError:
            continue  # disclaimer footer or blank line
        value = _money(row.get(c_value) or "")
        if value is None:
            continue
        as_of = max(as_of, day) if as_of else day
        cusip = (row.get(c_cusip) or "").strip() or None
        raw.append(
            (
                _ark_symbol(row.get(c_ticker) or ""),
                cusip,
                (row.get(c_company) or "").strip(),
                _money(row.get(c_shares) or "") or 0.0,
                value,
            )
        )
    if as_of is None or not raw:
        raise GuruDataError(f"ARK {fund}: no holdings rows")
    total = sum(r[4] for r in raw)
    rows = [
        GuruHolding(symbol=s, cusip=c, name=n, shares=sh, value_usd=v, weight=v / total)
        for s, c, n, sh, v in raw
    ]
    return FundHoldings(fund, as_of, rows)


def combine_funds(funds: list[FundHoldings]) -> GuruSnapshot:
    """Funds combined by market value (equivalent to fund-size-weighted fund weights).

    Funds whose file date lags the freshest by more than ARK_MAX_FUND_LAG are excluded and
    named in the note: showing January positions as today's would be wrong.
    """
    if not funds:
        raise GuruDataError("ARK: no fund data")
    latest = max(f.as_of for f in funds)
    fresh = [f for f in funds if latest - f.as_of <= ARK_MAX_FUND_LAG]
    stale = [f for f in funds if f not in fresh]
    by_key: dict[str, dict] = {}
    for f in fresh:
        for h in f.rows:
            # Rows without a ticker (cash, private placements) are kept apart by CUSIP/name.
            if h.symbol:
                key = h.symbol
            elif h.cusip:
                key = f"cusip:{h.cusip}"
            else:
                key = f"name:{h.name}"
            acc = by_key.setdefault(
                key, {"symbol": h.symbol, "cusip": h.cusip, "name": h.name, "sh": 0.0, "v": 0.0}
            )
            acc["sh"] += h.shares
            acc["v"] += h.value_usd
    total = sum(a["v"] for a in by_key.values())
    if total <= 0:
        raise GuruDataError("ARK: combined market value is zero")
    holdings = sorted(
        (
            GuruHolding(a["symbol"], a["cusip"], a["name"], a["sh"], a["v"], a["v"] / total)
            for a in by_key.values()
        ),
        key=lambda h: h.value_usd,
        reverse=True,
    )
    note = None
    if stale:
        parts = ", ".join(f"{f.fund}({f.as_of.isoformat()})" for f in sorted(stale, key=str))
        note = f"갱신이 멈춘 펀드 파일 제외: {parts}"
    return GuruSnapshot(as_of=latest, source="ark", holdings=holdings, note=note)


class ArkProvider:
    """Daily holdings CSVs of ARK's active ETFs. No key or User-Agent needed."""

    def __init__(self, http: httpx.Client | None = None) -> None:
        self.http = http or _client()

    def fetch(self, guru: Guru) -> GuruSnapshot:
        if guru.source != "ark" or not guru.funds:
            raise GuruDataError(f"{guru.id}: not an ARK investor")
        funds = []
        for fund in guru.funds:
            try:
                path = ARK_FUND_FILES[fund]
            except KeyError as exc:
                raise GuruDataError(f"ARK {fund}: unknown fund") from exc
            res = _get(self.http, ARK_BASE + path, f"ARK {fund}")
            funds.append(parse_ark_csv(res.content.decode("utf-8-sig", errors="replace"), fund))
        return combine_funds(funds)


# --- SEC 13F -------------------------------------------------------------------------------

SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/"
# EDGAR release of 2023-01-03 switched 13F values from thousands of dollars to dollars.
SEC_DOLLARS_FROM = date(2023, 1, 3)
_13F_NS = "{http://www.sec.gov/edgar/document/thirteenf/informationtable}"


@dataclass(frozen=True)
class Filing:
    form: str  # "13F-HR" | "13F-HR/A"
    accession: str  # "0001193125-26-352200"
    filing_date: date
    report_date: date

    @property
    def acc_nodash(self) -> str:
        return self.accession.replace("-", "")

    @property
    def in_thousands(self) -> bool:
        return self.filing_date < SEC_DOLLARS_FROM


@dataclass
class TableRow:
    name: str
    cusip: str
    value_usd: float
    shares: float


def choose_filing_sets(recent: dict) -> list[list[Filing]]:
    """Per reported quarter, newest first: the original 13F-HR (the latest one when a quarter
    was filed twice) followed by its later amendments in filing order."""
    forms = recent.get("form") or []
    filings = []
    for i, form in enumerate(forms):
        if form not in ("13F-HR", "13F-HR/A"):
            continue
        report = recent["reportDate"][i]
        if not report:
            continue
        filings.append(
            Filing(
                form=form,
                accession=recent["accessionNumber"][i],
                filing_date=date.fromisoformat(recent["filingDate"][i]),
                report_date=date.fromisoformat(report),
            )
        )
    originals: dict[date, Filing] = {}
    for f in filings:
        if f.form == "13F-HR":
            current = originals.get(f.report_date)
            if current is None or f.filing_date > current.filing_date:
                originals[f.report_date] = f
    sets = []
    for report_date in sorted(originals, reverse=True):
        original = originals[report_date]
        amendments = sorted(
            (
                f
                for f in filings
                if f.form == "13F-HR/A"
                and f.report_date == report_date
                and (f.filing_date, f.accession) > (original.filing_date, original.accession)
            ),
            key=lambda f: (f.filing_date, f.accession),
        )
        sets.append([original, *amendments])
    return sets


def choose_filings(recent: dict) -> list[Filing]:
    """The newest quarter's original 13F-HR and its later amendments; [] without a 13F-HR."""
    sets = choose_filing_sets(recent)
    return sets[0] if sets else []


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_13f_table(xml_bytes: bytes, in_thousands: bool) -> list[TableRow]:
    """Rows of an informationTable summed by CUSIP; options and debt principal excluded."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise GuruDataError(f"13F table: invalid XML ({exc})") from exc
    if _local(root.tag) != "informationTable":
        raise GuruDataError(f"13F table: unexpected root <{_local(root.tag)}>")
    scale = 1000.0 if in_thousands else 1.0
    by_cusip: dict[str, TableRow] = {}
    for item in root:
        if _local(item.tag) != "infoTable":
            continue
        fields = {_local(child.tag): child for child in item}
        if (fields.get("putCall") is not None) and (fields["putCall"].text or "").strip():
            continue
        amount = fields.get("shrsOrPrnAmt")
        sub = {_local(c.tag): (c.text or "").strip() for c in amount} if amount is not None else {}
        if sub.get("sshPrnamtType", "SH").upper() != "SH":
            continue
        cusip = (fields["cusip"].text or "").strip().upper() if "cusip" in fields else ""
        if not cusip:
            continue
        try:
            value = float((fields["value"].text or "0").replace(",", "")) * scale
            shares = float((sub.get("sshPrnamt") or "0").replace(",", ""))
        except (KeyError, ValueError):
            continue
        name = (fields["nameOfIssuer"].text or "").strip() if "nameOfIssuer" in fields else ""
        row = by_cusip.get(cusip)
        if row is None:
            by_cusip[cusip] = TableRow(name=name, cusip=cusip, value_usd=value, shares=shares)
        else:
            row.value_usd += value
            row.shares += shares
    return list(by_cusip.values())


def _amendment_type(primary_doc: bytes) -> str:
    """RESTATEMENT or NEW HOLDINGS from a 13F-HR/A cover page (restatement when unsure)."""
    try:
        root = ET.fromstring(primary_doc)
    except ET.ParseError:
        return "RESTATEMENT"
    for el in root.iter():
        if _local(el.tag) == "amendmentType":
            return (el.text or "").strip().upper() or "RESTATEMENT"
    return "RESTATEMENT"


def _rows_to_snapshot(rows: list[TableRow], as_of: date, note: str | None = None) -> GuruSnapshot:
    total = sum(r.value_usd for r in rows)
    if not rows or total <= 0:
        raise EmptyTableError("13F table: no equity rows")
    holdings = sorted(
        (
            GuruHolding(
                symbol=None,
                cusip=r.cusip,
                name=r.name,
                shares=r.shares,
                value_usd=r.value_usd,
                weight=r.value_usd / total,
            )
            for r in rows
        ),
        key=lambda h: h.value_usd,
        reverse=True,
    )
    return GuruSnapshot(as_of=as_of, source="13f", holdings=holdings, note=note)


def check_filer_name(guru: Guru, submissions: dict) -> None:
    """Refuse a CIK whose EDGAR name (current or former) lacks the investor's keyword."""
    if not guru.expected_name:
        return
    current = str(submissions.get("name") or "")
    names = [current] + [
        str(f.get("name") or "")
        for f in (submissions.get("formerNames") or [])
        if isinstance(f, dict)
    ]
    if not any(guru.expected_name in n.upper() for n in names):
        raise GuruDataError(
            f"{CIK_MISMATCH}: EDGAR 이름 '{current}'에 '{guru.expected_name}'가 없음 "
            f"(CIK {guru.cik})"
        )


class Sec13FProvider:
    """Latest 13F information table from EDGAR. Tickers are left None (CUSIP only); the
    service resolves them through `CusipResolver` and its cache."""

    def __init__(self, user_agent: str, http: httpx.Client | None = None) -> None:
        self.user_agent = user_agent.strip()
        self.http = http or _client(
            {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}
        )

    def fetch(self, guru: Guru) -> GuruSnapshot:
        if not self.user_agent:
            raise GuruDataError("AM_SEC_USER_AGENT 미설정")
        if guru.source != "13f" or not guru.cik:
            raise GuruDataError(f"{guru.id}: not a 13F filer")
        cik = guru.cik.zfill(10)
        res = _get(self.http, SEC_SUBMISSIONS.format(cik=cik), f"EDGAR submissions {cik}")
        try:
            submissions = res.json()
            recent = submissions["filings"]["recent"]
        except (ValueError, KeyError, TypeError) as exc:
            raise GuruDataError(f"EDGAR submissions {cik}: unexpected JSON") from exc
        check_filer_name(guru, submissions)
        sets = choose_filing_sets(recent)
        if not sets:
            raise GuruDataError(f"EDGAR {cik}: no 13F-HR filing")
        # A quarter filed under confidential treatment has an empty table; show the newest
        # quarter that has rows and say so, rather than an empty portfolio or nothing.
        empty: list[date] = []
        for filings in sets[: 1 + MAX_QUARTERS_BACK]:
            rows = self._rows(cik, filings)
            note = None
            if empty:
                skipped = ", ".join(d.isoformat() for d in empty)
                note = (
                    f"기밀 처리로 표가 비어 있는 분기 제외: {skipped}. "
                    f"{filings[0].report_date.isoformat()} 기준 표를 표시"
                )
            try:
                return _rows_to_snapshot(rows, filings[0].report_date, note)
            except EmptyTableError:
                empty.append(filings[0].report_date)
        raise EmptyTableError(
            f"EDGAR {cik}: 13F table: no equity rows in the last {len(empty)} quarter(s)"
        )

    def _rows(self, cik: str, filings: list[Filing]) -> list[TableRow]:
        """The quarter's table with its amendments applied."""
        rows = self._table(cik, filings[0])
        for amendment in filings[1:]:
            base = SEC_ARCHIVE.format(cik=int(cik), acc=amendment.acc_nodash)
            kind = _amendment_type(
                _get(self.http, base + "primary_doc.xml", f"EDGAR {amendment.accession}").content
            )
            amended = self._table(cik, amendment)
            if kind == "NEW HOLDINGS":
                known = {r.cusip for r in rows}
                rows = rows + [r for r in amended if r.cusip not in known]
            else:
                rows = amended
        return rows

    def _table(self, cik: str, filing: Filing) -> list[TableRow]:
        base = SEC_ARCHIVE.format(cik=int(cik), acc=filing.acc_nodash)
        index = _get(self.http, base + "index.json", f"EDGAR {filing.accession} index")
        try:
            items = index.json()["directory"]["item"]
        except (ValueError, KeyError, TypeError) as exc:
            raise GuruDataError(f"EDGAR {filing.accession}: unexpected index") from exc
        candidates = [
            it["name"]
            for it in items
            if it.get("name", "").lower().endswith(".xml")
            and it["name"].lower() != "primary_doc.xml"
        ]
        if not candidates:
            raise GuruDataError(f"EDGAR {filing.accession}: no information table XML")
        for name in candidates:
            body = _get(self.http, base + name, f"EDGAR {filing.accession}/{name}").content
            try:
                return parse_13f_table(body, filing.in_thousands)
            except GuruDataError:
                continue  # some filers attach other XML; try the next one
        raise GuruDataError(f"EDGAR {filing.accession}: no parseable information table")


# --- OpenFIGI --------------------------------------------------------------------------------

OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"


class OpenFigiClient:
    """CUSIP -> US ticker. Without a key: 25 requests/minute, 10 jobs each; with a key:
    25 requests per 6 seconds, 100 jobs each. Requests are spaced to stay under the limit."""

    _lock = threading.Lock()
    _last_request = 0.0

    def __init__(
        self,
        api_key: str = "",
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.api_key = api_key.strip()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-OPENFIGI-APIKEY"] = self.api_key
        self.http = http or _client(headers)
        self.sleep = sleep
        self.clock = clock
        self.batch = 100 if self.api_key else 10
        self.min_interval = 0.3 if self.api_key else 2.5

    def map_cusips(self, cusips: list[str]) -> dict[str, tuple[str | None, str | None]]:
        out: dict[str, tuple[str | None, str | None]] = {}
        unique = list(dict.fromkeys(c for c in cusips if c))
        for start in range(0, len(unique), self.batch):
            chunk = unique[start : start + self.batch]
            jobs = [{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in chunk]
            results = self._post(jobs)
            for cusip, item in zip(chunk, results, strict=True):
                out[cusip] = _pick_figi(item)
        return out

    def _post(self, jobs: list[dict]) -> list[dict]:
        for attempt in range(ATTEMPTS):
            self._throttle()
            try:
                res = self.http.post(OPENFIGI_URL, json=jobs)
            except httpx.HTTPError as exc:
                if attempt + 1 < ATTEMPTS:
                    continue
                raise GuruDataError(f"OpenFIGI request failed: {exc}") from exc
            if res.status_code == 429:
                if attempt + 1 == ATTEMPTS:
                    raise GuruDataError("OpenFIGI: rate limited (HTTP 429)")
                try:
                    wait = float(res.headers.get("ratelimit-reset", "60"))
                except ValueError:
                    wait = 60.0
                self.sleep(min(wait, 120.0))
                continue
            if res.status_code != 200:
                raise GuruDataError(f"OpenFIGI error {res.status_code}: {res.text[:120]}")
            data = res.json()
            if not isinstance(data, list) or len(data) != len(jobs):
                raise GuruDataError("OpenFIGI: unexpected response shape")
            return data
        raise GuruDataError("OpenFIGI: request failed")

    def _throttle(self) -> None:
        with OpenFigiClient._lock:
            wait = OpenFigiClient._last_request + self.min_interval - self.clock()
            if wait > 0:
                self.sleep(wait)
            OpenFigiClient._last_request = self.clock()


def _pick_figi(item: dict) -> tuple[str | None, str | None]:
    """The US composite listing's ticker in Yahoo form (BRK/B -> BRK-B), else (None, None).
    Unknown identifiers come back as {"warning": ...} or {"error": ...}."""
    data = item.get("data") if isinstance(item, dict) else None
    if not data:
        return None, None
    best = next((d for d in data if d.get("exchCode") == "US"), data[0])
    ticker = (best.get("ticker") or "").strip().upper().replace("/", "-")
    return (ticker or None), (best.get("name") or None)


# --- Fakes and wiring --------------------------------------------------------------------------


class FakeGuruProvider:
    """Fixed snapshots for tests and demos; records calls and can be told to fail."""

    def __init__(self, snapshots: dict[str, GuruSnapshot] | None = None) -> None:
        self.snapshots = snapshots or {}
        self.calls: list[str] = []
        self.fail: set[str] = set()

    def fetch(self, guru: Guru) -> GuruSnapshot:
        self.calls.append(guru.id)
        if guru.id in self.fail:
            raise GuruDataError(f"{guru.id}: simulated failure")
        try:
            return self.snapshots[guru.id]
        except KeyError as exc:
            raise GuruDataError(f"{guru.id}: no fake snapshot") from exc


@dataclass
class FakeCusipResolver:
    table: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)

    def map_cusips(self, cusips: list[str]) -> dict[str, tuple[str | None, str | None]]:
        self.calls.append(list(cusips))
        return {c: self.table.get(c, (None, None)) for c in cusips}


class RoutingGuruProvider:
    """Sends ARK investors to ArkProvider and 13F filers to Sec13FProvider."""

    def __init__(self, ark: GuruProvider, sec: GuruProvider) -> None:
        self.ark = ark
        self.sec = sec

    def fetch(self, guru: Guru) -> GuruSnapshot:
        return (self.ark if guru.source == "ark" else self.sec).fetch(guru)


def build_guru_provider(sec_user_agent: str) -> RoutingGuruProvider:
    return RoutingGuruProvider(ArkProvider(), Sec13FProvider(sec_user_agent))


def build_cusip_resolver(openfigi_api_key: str) -> OpenFigiClient:
    return OpenFigiClient(openfigi_api_key)
