"""US House of Representatives stock-trade disclosures (STOCK Act periodic transaction reports).

The Clerk of the House publishes two things for free and without a key (checked 2026-10-23):
- a yearly index ZIP, `{year}FD.zip`, holding `{year}FD.xml` with one <Member> per filing
  (name, FilingType, StateDst, FilingDate, DocID). FilingType "P" is a periodic transaction
  report (PTR); withdrawals ("W") may have an empty FilingDate. A year's index also carries
  filings made in the following January.
- one PDF per filing. Electronically filed PTRs have a text layer whose rows read
  `<owner> <asset ... (TICKER) [ST]> <P|S|S (partial)|E> <date> <notification date> <amount>`
  followed by a small-caps "F S : New" filing-status line and, for some rows, "S O :" (the
  account the asset is held in) and "D :" (a free-text description) lines that describe the
  row above them. Paper filings are scans with no text layer and are reported as `no_text`
  rather than guessed.

All HTTP and the pypdf import live in this file, behind `CongressProvider`, so the service and
tests never touch the network. Senate filings (efdsearch.senate.gov) are not covered: the site
refused this network with HTTP 403 (DECISIONS.md D-030).
"""

import io
import logging
import re
import zipfile
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from typing import Protocol
from xml.etree import ElementTree as ET

import httpx2 as httpx
from pypdf import PdfReader
from pypdf.errors import PyPdfError

log = logging.getLogger(__name__)

INDEX_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
PTR_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"
# No contact address: the Clerk's site has no SEC-style User-Agent rule and the owner's email
# must not end up in a public repository.
USER_AGENT = "asset-manager (personal use)"
TIMEOUT = 20.0
ATTEMPTS = 2  # one retry on transport errors and 5xx

PTR_FILING_TYPE = "P"
OWNER_CODES = frozenset({"SP", "DC", "JT"})  # spouse, dependent child, joint; blank = filer
SIDES = {
    "P": "buy",
    "S": "sell",
    "S(PARTIAL)": "sell_partial",
    "P(PARTIAL)": "buy",
    "E": "exchange",
}


class CongressDataError(Exception):
    """A disclosure source failed or returned something unparseable. `status` is the HTTP
    status when the failure was an HTTP response (404 for a missing index or document)."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


# --- data ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class IndexEntry:
    """One filing in a year's index."""

    year: int
    doc_id: str
    filing_type: str  # "P" = periodic transaction report
    filing_date: date | None  # empty for some withdrawals
    first: str
    last: str
    prefix: str = ""
    suffix: str = ""
    state_district: str = ""  # "MD06"

    @property
    def is_ptr(self) -> bool:
        return self.filing_type == PTR_FILING_TYPE

    @property
    def name(self) -> str:
        """The filer as "Jane Doe Jr.", without the "Hon." prefix."""
        return " ".join(p for p in (self.first, self.last, self.suffix) if p)

    @property
    def state(self) -> str:
        return self.state_district[:2]


@dataclass(frozen=True)
class IndexResult:
    year: int
    entries: list[IndexEntry]
    modified: datetime | None  # HTTP Last-Modified, UTC naive


@dataclass(frozen=True)
class PtrRow:
    owner: str  # "SELF" | "SP" | "DC" | "JT"
    asset_name: str
    asset_type: str | None  # Clerk code such as "ST" (stock), "MF", "OP"; None when absent
    symbol: str | None  # ticker in parentheses at the end of the asset name
    side: str  # "buy" | "sell" | "sell_partial" | "exchange"
    transaction_date: date
    notification_date: date | None
    amount_low: int
    amount_high: int | None  # None for "Over $X"; equal to amount_low for an exact "$2,000.00"
    amount_label: str
    cap_gains_over_200: bool | None = None
    filing_status: str | None = None  # "New" | "Amended"
    description: str | None = None  # the "D :" line(s) under the row


@dataclass(frozen=True)
class PtrDocument:
    rows: list[PtrRow]
    filer_name: str | None = None
    state_district: str | None = None
    no_text: bool = False  # scanned paper filing: nothing to parse
    # Row chunks that did not parse; kept so a layout change shows up as a count, not silence.
    warnings: list[str] = field(default_factory=list)


class CongressProvider(Protocol):
    def index(self, year: int) -> IndexResult:
        """All filings listed for `year`. Raises CongressDataError (status 404 when the year's
        index does not exist yet)."""
        ...

    def ptr(self, year: int, doc_id: str) -> PtrDocument:
        """One periodic transaction report, parsed. Raises CongressDataError."""
        ...


def ptr_url(year: int, doc_id: str) -> str:
    return PTR_URL.format(year=year, doc_id=doc_id)


# --- index ---------------------------------------------------------------------------------------


def read_index_zip(data: bytes) -> bytes:
    """The XML member of a `{year}FD.zip` (the .txt member repeats it tab-separated)."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            if not names:
                raise CongressDataError("House index: ZIP has no XML member")
            return zf.read(names[0])
    except zipfile.BadZipFile as exc:
        raise CongressDataError("House index: not a ZIP file") from exc


def _index_date(text: str) -> date | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%m/%d/%Y").date()
    except ValueError as exc:
        raise CongressDataError(f"House index: bad FilingDate {text!r}") from exc


def parse_fd_index(xml_bytes: bytes) -> list[IndexEntry]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise CongressDataError(f"House index: invalid XML ({exc})") from exc
    entries = []
    for member in root.iter("Member"):
        text = {child.tag: (child.text or "").strip() for child in member}
        doc_id = text.get("DocID", "")
        if not doc_id:
            continue
        try:
            year = int(text.get("Year") or 0)
        except ValueError:
            year = 0
        entries.append(
            IndexEntry(
                year=year,
                doc_id=doc_id,
                filing_type=text.get("FilingType", ""),
                filing_date=_index_date(text.get("FilingDate", "")),
                first=text.get("First", ""),
                last=text.get("Last", ""),
                prefix=text.get("Prefix", ""),
                suffix=text.get("Suffix", ""),
                state_district=text.get("StateDst", ""),
            )
        )
    return entries


# --- PTR text ------------------------------------------------------------------------------------

# "S (partial) 08/06/2026 09/01/2026 $15,001 -" ; the upper bound may wrap to the next line.
# Amounts are ranges ("$1,001 - $15,000"), open ranges ("Over $50,000,000", and the spouse /
# dependent-child form "Spouse/DC Over $1,000,000", whose figure wraps to the next line) or,
# rarely, exact figures with cents ("$2,000.00").
_TXN = re.compile(
    r"(?<![A-Za-z])(?P<type>[PS]\s*\(partial\)|[PSE])\s+(?P<date>\d{2}/\d{2}/\d{4})"
    r"(?:\s+(?P<notif>\d{2}/\d{2}/\d{4}))?\s+"
    r"(?P<amount>(?:Spouse/DC\s+)?Over\s+\$[\d,]+|\$[\d,]+\s*-\s*(?:\$[\d,]+)?|\$[\d,]+\.\d{2})"
)
_AMOUNT_TAIL = re.compile(r"\$[\d,]+")
# The upper bound of a wrapped amount may come after the rest of the asset name when the row
# straddles a page break ("$100,001 -" / page header / "Stock (TICK) [ST] $250,000"); it is
# accepted on any of the next this-many lines.
_AMOUNT_TAIL_LINES = 3
_CAP_GAINS = re.compile(r"^[ \t]*(Yes|No|✓)(?![A-Za-z])")
_ASSET_CODE = re.compile(r"\[([A-Z]{2,4})\]")
_TICKER = re.compile(r"\(([A-Z][A-Z0-9.\-/]{0,9})\)\s*$")
# Small-caps labels come out letter-spaced: "F      S     : New", "D      : comment".
_LABEL = re.compile(r"^([A-Z](?:\s+[A-Z])*)\s*:\s*(.*)$")
_STATUS_LABEL = "FS"  # "Filing Status": the first label under every row
# "Description" and "Comments" are free text in a cell as wide as the table, so a long one
# wraps onto a further line; "S O" (Subholding Of, the account) and "F S" never do.
_FREE_TEXT_LABELS = frozenset({"D", "C"})
# Section headings whose lower-case letters were lost: "P T R", "F I", "T".
_HEADING = re.compile(r"^(?:[A-Z]\s+)*[A-Z]\s*$")
_HEADER_LINES = frozenset(
    {
        "ID Owner Asset Transaction",
        "Type",
        "Date Notification",
        "Date",
        "Amount Cap.",
        "Gains >",
        "$200?",
    }
)
_FURNITURE = (
    re.compile(r"^Filing ID #\d+"),
    re.compile(r"^Clerk of the House of Representatives"),
    re.compile(r"^Status:\s*"),
)
_END_OF_ROWS = (
    re.compile(r"^\* For the complete list of asset type abbreviations"),
    re.compile(r"^I CERTIFY"),
    re.compile(r"^Digitally Signed"),
)
_META = {"Name": "filer_name", "State/District": "state_district"}


def parse_amount(label: str) -> tuple[int, int | None]:
    """Bounds of an amount label: "$1,001 - $15,000" -> (1001, 15000), "Over $50,000,000" and
    "Spouse/DC Over $1,000,000" -> (…, None), an exact "$2,722.50" -> (2722, 2723)."""
    exact = re.fullmatch(r"\$([\d,]+)\.(\d{2})", label.strip())
    if exact:
        dollars, cents = int(exact.group(1).replace(",", "")), int(exact.group(2))
        return dollars, dollars + (cents > 0)
    nums = [int(n.replace(",", "")) for n in re.findall(r"\$([\d,]+)", label)]
    if re.match(r"(?:Spouse/DC\s+)?Over\b", label.lstrip()) and len(nums) == 1:
        return nums[0], None
    if len(nums) == 2:
        return nums[0], nums[1]
    raise ValueError(f"unrecognised amount {label!r}")


def _side(raw: str) -> str:
    key = re.sub(r"\s+", "", raw).upper()
    try:
        return SIDES[key]
    except KeyError as exc:
        raise ValueError(f"unknown transaction type {raw!r}") from exc


def normalize_symbol(ticker: str) -> str:
    """The app's (Yahoo) spelling of a ticker: "BRK.B" and "BRK/B" -> "BRK-B"."""
    return ticker.strip().upper().replace(".", "-").replace("/", "-")


def _date(text: str | None) -> date | None:
    return datetime.strptime(text, "%m/%d/%Y").date() if text else None


def _parse_chunk(lines: list[str], filing_status: str | None = None) -> PtrRow:
    """One table row from its text lines (asset text, then the transaction fields)."""
    text = "\n".join(lines)
    m = _TXN.search(text)
    if m is None:
        raise ValueError("no transaction fields")
    amount = re.sub(r"\s+", " ", m.group("amount")).strip()
    after = text[m.end() :]
    before_tail = ""
    if amount.endswith("-"):
        # "$100,001 -" at the foot of a page, then the rest of the asset name, then "$250,000".
        tail = _AMOUNT_TAIL.search(after)
        if tail is None or after[: tail.start()].count("\n") >= _AMOUNT_TAIL_LINES:
            raise ValueError("amount upper bound missing")
        amount = f"{amount} {tail.group(0)}"
        before_tail, after = after[: tail.start()], after[tail.end() :]
    cap_gains = None
    cap = _CAP_GAINS.match(after)
    if cap:
        cap_gains = cap.group(1) != "No"
        after = after[cap.end() :]
    low, high = parse_amount(amount)

    rest = re.sub(r"\s+", " ", " ".join((text[: m.start()], before_tail, after))).strip()
    owner = "SELF"
    head = rest.split(" ", 1)
    if head and head[0] in OWNER_CODES:
        owner = head[0]
        rest = head[1] if len(head) > 1 else ""
    asset_type = None
    codes = list(_ASSET_CODE.finditer(rest))
    if codes:
        asset_type = codes[-1].group(1)
        rest = (rest[: codes[-1].start()] + rest[codes[-1].end() :]).strip()
    if not rest:
        raise ValueError("asset name missing")
    ticker = _TICKER.search(rest)
    return PtrRow(
        owner=owner,
        asset_name=rest,
        asset_type=asset_type,
        symbol=normalize_symbol(ticker.group(1)) if ticker else None,
        side=_side(m.group("type")),
        transaction_date=_date(m.group("date")),
        notification_date=_date(m.group("notif")),
        amount_low=low,
        amount_high=high,
        amount_label=amount,
        cap_gains_over_200=cap_gains,
        filing_status=filing_status or None,
    )


def _has_fields(lines: list[str]) -> bool:
    return _TXN.search("\n".join(lines)) is not None


def _is_furniture(line: str) -> bool:
    return (
        line in _HEADER_LINES
        or bool(_HEADING.match(line))
        or any(p.match(line) for p in _FURNITURE)
    )


def parse_ptr_text(text: str) -> PtrDocument:
    """Rows of an electronically filed PTR from its extracted text.

    The form's small-caps labels ("Filing Status", "Periodic Transaction Report") come out of
    pypdf with their lower-case letters as NUL characters ("F\\x00\\x00... S\\x00...: New"), so
    NULs are dropped first. Page headers, section headings and "Filing ID" footers are removed,
    so a row that wraps across a page break is still one row.

    The text of a row is followed by its "F S: New" filing-status label and then, for some
    rows, "S O: <account>" and "D: <description>" labels; the next row starts right after
    them, with no marker of its own (a row held by the filer has no owner code, and its asset
    name may take two or three lines). So a row's text is everything between the previous
    row's labels and its own "F S" label, and the labels after an "F S" are attached to the
    row just closed. A description that wrapped onto a further line is only joined to its
    label at the end of the document, where no row can follow it; in the middle of a document
    the wrapped fragment stays in front of the next row's asset name (rare, and the ticker at
    the end of the name is unaffected) rather than risk swallowing that row.

    A document without filing-status labels falls back to one row per set of transaction
    fields, with the asset text before them.
    """
    text = text.replace("\x00", "")
    meta: dict[str, str] = {}
    rows: list[PtrRow] = []
    warnings: list[str] = []
    chunk: list[str] = []  # non-label lines since the last status label: the next row
    trailer: dict[str, str] = {}  # labels since the last status label: about the row above
    open_label: str | None = None  # the last trailer label, whose value may have wrapped
    saw_status_label = False

    def close_trailer() -> None:
        """Attach the labels collected since the last status label to the row they follow."""
        nonlocal trailer, open_label
        if rows and trailer.get("D"):
            rows[-1] = replace(rows[-1], description=trailer["D"])
        trailer, open_label = {}, None

    def close_row(filing_status: str | None) -> None:
        nonlocal chunk
        if _has_fields(chunk):
            try:
                rows.append(_parse_chunk(chunk, filing_status))
            except ValueError as exc:
                warnings.append(f"{exc}: {' '.join(chunk)[:120]}")
        elif any(line.strip() for line in chunk):
            warnings.append(f"no transaction fields: {' '.join(chunk)[:120]}")
        chunk = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if any(p.match(line) for p in _END_OF_ROWS):
            break
        if _is_furniture(line):
            continue
        key, sep, value = line.partition(":")
        if sep and key.strip() in _META:
            meta[_META[key.strip()]] = value.strip()
            continue
        label = _LABEL.match(line)
        if label:
            name = re.sub(r"\s+", "", label.group(1))
            if name == _STATUS_LABEL:
                saw_status_label = True
                close_trailer()  # the previous row's labels, before this row is appended
                close_row(label.group(2).strip())
            else:
                trailer[name] = label.group(2).strip()
                open_label = name
            continue
        chunk.append(line)

    if saw_status_label:
        # After the last status label: the last row's labels, perhaps a wrapped description
        # (no row can follow it here), perhaps a trailing row without a status label.
        if chunk and not _has_fields(chunk) and open_label in _FREE_TEXT_LABELS:
            trailer[open_label] = " ".join([trailer[open_label], *chunk]).strip()
            chunk = []
        close_trailer()
        close_row(None)
    else:
        # Legacy layout: one row per set of transaction fields, with the asset text before
        # them and a wrapped amount or capital-gains mark right after.
        body = "\n".join(chunk)
        cursor = 0
        for m in _TXN.finditer(body):
            if m.start() < cursor:
                continue
            stop = m.end()
            if m.group("amount").rstrip().endswith("-"):
                tail = re.match(r"\s*\$[\d,]+", body[stop:])
                stop += tail.end() if tail else 0
            cap = re.match(r"[ \t]*(?:Yes|No|✓)(?![A-Za-z])", body[stop:])
            stop += cap.end() if cap else 0
            chunk = body[cursor:stop].strip("\n").split("\n")
            close_row(None)
            cursor = stop
        leftover = body[cursor:].strip()
        if leftover:
            warnings.append(f"unparsed trailing text: {leftover[:120]}")

    return PtrDocument(
        rows=rows,
        filer_name=meta.get("filer_name"),
        state_district=meta.get("state_district"),
        warnings=warnings,
    )


def extract_text(pdf: bytes) -> str:
    """Text layer of a PDF, pages joined by newlines. Empty for scanned documents."""
    try:
        reader = PdfReader(io.BytesIO(pdf))
        if reader.is_encrypted:
            reader.decrypt("")
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except (PyPdfError, ValueError, KeyError, TypeError) as exc:
        raise CongressDataError(f"PDF: {exc.__class__.__name__}: {str(exc)[:120]}") from exc


# --- HTTP ----------------------------------------------------------------------------------------


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=False)


def _get(http: httpx.Client, url: str, what: str) -> httpx.Response:
    """GET with one retry on transport errors and 5xx. 4xx is final and carries its status."""
    last: Exception | None = None
    for attempt in range(ATTEMPTS):
        try:
            res = http.get(url)
        except httpx.HTTPError as exc:
            last = exc
            continue
        if res.status_code >= 500 and attempt + 1 < ATTEMPTS:
            last = CongressDataError(f"{what}: HTTP {res.status_code}", res.status_code)
            continue
        if res.status_code != 200:
            raise CongressDataError(f"{what}: HTTP {res.status_code}", res.status_code)
        return res
    raise CongressDataError(f"{what}: {last}") from last


def _http_date(value: str | None) -> datetime | None:
    """HTTP Last-Modified as a naive UTC datetime; None when absent or malformed."""
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


class HouseClerkProvider:
    """Index ZIPs and PTR PDFs from disclosures-clerk.house.gov."""

    def __init__(self, http: httpx.Client | None = None) -> None:
        self.http = http or _client()

    def index(self, year: int) -> IndexResult:
        res = _get(self.http, INDEX_URL.format(year=year), f"House index {year}")
        entries = parse_fd_index(read_index_zip(res.content))
        return IndexResult(year, entries, _http_date(res.headers.get("last-modified")))

    def ptr(self, year: int, doc_id: str) -> PtrDocument:
        res = _get(self.http, ptr_url(year, doc_id), f"House PTR {doc_id}")
        text = extract_text(res.content)
        if not text.strip():
            return PtrDocument(rows=[], no_text=True)
        return parse_ptr_text(text)


# --- fake -----------------------------------------------------------------------------------------


class FakeCongressProvider:
    """Fixed indexes and documents for tests; records calls and can be told to fail."""

    def __init__(
        self,
        indexes: dict[int, IndexResult] | None = None,
        docs: dict[str, PtrDocument] | None = None,
    ) -> None:
        self.indexes = indexes or {}
        self.docs = docs or {}
        self.calls: list[tuple[str, ...]] = []
        self.fail_index: set[int] = set()
        self.missing_index: set[int] = set()  # years answered with HTTP 404
        self.fail_docs: set[str] = set()

    def index(self, year: int) -> IndexResult:
        self.calls.append(("index", str(year)))
        if year in self.fail_index:
            raise CongressDataError(f"House index {year}: simulated failure")
        if year in self.missing_index:
            raise CongressDataError(f"House index {year}: HTTP 404", 404)
        return self.indexes.get(year) or IndexResult(year, [], None)

    def ptr(self, year: int, doc_id: str) -> PtrDocument:
        self.calls.append(("ptr", str(year), doc_id))
        if doc_id in self.fail_docs:
            raise CongressDataError(f"House PTR {doc_id}: simulated failure")
        try:
            return self.docs[doc_id]
        except KeyError as exc:
            raise CongressDataError(f"House PTR {doc_id}: HTTP 404", 404) from exc


def build_congress_provider() -> HouseClerkProvider:
    return HouseClerkProvider()
