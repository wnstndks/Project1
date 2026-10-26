"""House periodic transaction reports: index ZIP, PTR text parsing, PDF text layer and HTTP.

Everything runs offline: HTTP goes through httpx MockTransport and PDFs are built in the test.
Names and tickers in the fixtures are invented.
"""

import io
import zipfile
from datetime import date, datetime
from pathlib import Path

import httpx2 as httpx
import pytest

from app.data import congress_provider as cp
from app.data.congress_provider import (
    CongressDataError,
    FakeCongressProvider,
    HouseClerkProvider,
    IndexEntry,
    IndexResult,
    PtrDocument,
    PtrRow,
    extract_text,
    normalize_symbol,
    parse_amount,
    parse_fd_index,
    parse_ptr_text,
    ptr_url,
    read_index_zip,
)

FIXTURES = Path(__file__).parent / "fixtures" / "congress"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def index_zip(xml: bytes, year: int = 2026) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{year}FD.txt", "Prefix\tLast\tFirst\n")
        zf.writestr(f"{year}FD.xml", xml)
    return buf.getvalue()


def _pdf_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def tiny_pdf(lines: list[str]) -> bytes:
    """A one-page PDF with `lines` of Helvetica text (none: a blank page like a scan)."""
    content = ""
    if lines:
        body = " T* ".join(f"({_pdf_string(line)}) Tj" for line in lines)
        content = f"BT /F1 11 Tf 14 TL 40 760 Td {body} ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets)
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out


# --- index -------------------------------------------------------------------------------------


def test_parse_fd_index_reads_members_and_blank_dates():
    # The real file starts with a UTF-8 BOM.
    entries = parse_fd_index(b"\xef\xbb\xbf" + fixture_bytes("house_fd_index.xml"))
    assert len(entries) == 5
    ptr = [e for e in entries if e.is_ptr]
    assert [e.doc_id for e in ptr] == ["20039001", "9001234", "20038002"]
    first = ptr[0]
    assert first.name == "Jane Doe" and first.state == "ST" and first.state_district == "ST01"
    assert first.filing_date == date(2026, 10, 1) and first.year == 2026
    assert ptr[1].name == "John Roe Jr." and ptr[1].prefix == "Hon."
    withdrawal = next(e for e in entries if e.filing_type == "W")
    assert withdrawal.filing_date is None and withdrawal.name == "Rich Aaronson"
    assert not withdrawal.is_ptr


def test_read_index_zip_returns_xml_member_and_rejects_garbage():
    xml = fixture_bytes("house_fd_index.xml")
    assert read_index_zip(index_zip(xml)) == xml
    with pytest.raises(CongressDataError, match="not a ZIP"):
        read_index_zip(b"not a zip")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("2026FD.txt", "x")
    with pytest.raises(CongressDataError, match="no XML"):
        read_index_zip(buf.getvalue())


def test_parse_fd_index_rejects_bad_xml_and_bad_dates():
    with pytest.raises(CongressDataError, match="invalid XML"):
        parse_fd_index(b"<FinancialDisclosure>")
    bad = (
        b"<FinancialDisclosure><Member><DocID>1</DocID><FilingDate>2026-10-01</FilingDate>"
        b"</Member></FinancialDisclosure>"
    )
    with pytest.raises(CongressDataError, match="bad FilingDate"):
        parse_fd_index(bad)


# --- PTR text ------------------------------------------------------------------------------------


def test_parse_ptr_text_reads_rows_across_wraps_and_pages():
    """The fixture follows the real layout: a row's text, its "F S" label, then for some rows
    "S O" / "D" labels, then the next row with no marker of its own (ISSUE-045)."""
    doc = parse_ptr_text(fixture_text("ptr_text_sample.txt"))
    assert doc.filer_name == "Hon. Jane Doe" and doc.state_district == "ST01"
    assert not doc.no_text and doc.warnings == []
    assert len(doc.rows) == 8
    r1, r2, r3, r4, r5, r6, r7, r8 = doc.rows
    assert r1 == PtrRow(
        owner="SP",
        asset_name="Quux Robotics Holdings, Inc. Class A Common Stock (QQXA)",
        asset_type="ST",
        symbol="QQXA",
        side="buy",
        transaction_date=date(2026, 8, 3),
        notification_date=date(2026, 9, 1),
        amount_low=15_001,
        amount_high=50_000,
        amount_label="$15,001 - $50,000",
        cap_gains_over_200=None,
        filing_status="New",
        description=None,
    )
    # A row held by the filer, right after the previous row's "S O" label: no owner code, the
    # asset name on its own line and "[ST]" on the next. It is a row, not part of the label.
    assert (r2.owner, r2.symbol, r2.side) == ("SELF", "ZYXW", "sell_partial")
    assert r2.asset_name == "Zyx Widget Corp Common Stock (ZYXW)" and r2.asset_type == "ST"
    assert (r2.amount_low, r2.amount_high) == (1_001, 15_000)
    assert (r3.owner, r3.asset_type, r3.symbol) == ("DC", "MF", None)
    assert (r3.amount_low, r3.amount_high, r3.amount_label) == (
        50_000_000,
        None,
        "Over $50,000,000",
    )
    assert r3.asset_name == "Blue Harbor Growth Fund Class I"
    # The row split across the page break: its fields came before the rest of the asset name.
    assert (r4.owner, r4.symbol, r4.side, r4.filing_status) == ("JT", "WXYZ", "sell", "Amended")
    assert r4.asset_name == "Wobble Energy Partners LP Units - Common Units (WXYZ)"
    assert (r4.amount_low, r4.amount_high) == (100_001, 250_000)
    assert (r5.side, r5.cap_gains_over_200, r5.notification_date) == (
        "exchange",
        True,
        date(2026, 9, 2),
    )
    assert r5.asset_name == "Fizz Beverage Corp Common Stock (FZZB)" and r5.symbol == "FZZB"
    # The "D:" label after a row's "F S" describes that row, not the next one.
    assert r5.description == "Exchanged in merger for Buzz Beverage shares."
    # "$100,001 -" at the foot of a page, the rest of the asset name on the next page, then
    # "$250,000": the upper bound is found after the asset text.
    assert (r6.owner, r6.symbol, r6.asset_type, r6.side) == ("DC", "GPKE", "ST", "sell_partial")
    assert r6.asset_name == "Granite Peak Energy Corporation Common Stock (GPKE)"
    assert (r6.transaction_date, r6.notification_date) == (date(2026, 9, 2), date(2026, 9, 15))
    assert (r6.amount_low, r6.amount_high, r6.amount_label) == (
        100_001,
        250_000,
        "$100,001 - $250,000",
    )
    assert r6.description is None
    # The spouse / dependent-child open range, whose figure wraps to the next line.
    assert (r7.owner, r7.asset_type, r7.symbol) == ("SP", "GS", None)
    assert r7.asset_name == "U.S. Treasury Note due 2/28/2029"
    assert (r7.amount_low, r7.amount_high) == (1_000_000, None)
    assert r7.amount_label == "Spouse/DC Over $1,000,000"
    # An exact amount, and a description that wrapped onto a second line at the end of the
    # document: one description, no broken row.
    assert (r8.owner, r8.symbol, r8.side) == ("SELF", "QZPH", "sell")
    assert (r8.amount_low, r8.amount_high, r8.amount_label) == (2_722, 2_723, "$2,722.50")
    assert r8.description == (
        "Investment in LLC which is acquiring and managing a commercial office property at "
        "225 Bush Street in San Francisco, CA."
    )
    assert [r.description for r in doc.rows[:4]] == [None] * 4


def test_labels_under_a_row_never_swallow_the_next_row():
    # The regression the first ISSUE-045 fix had: a wrapped-label rule glued the next row's
    # asset-name line onto "S O" / "D" and dropped the row or truncated its name.
    text = (
        "Acme Co - Class C Capital Stock\n(ZQRK) [ST]\nP 09/14/2026 09/14/2026 $1,001 - $15,000\n"
        "F S: New\nS O: Big Broker #2\n"
        "Apple Pie Inc. - Common Stock (APLP)\n[ST]\nP 09/08/2026 09/08/2026 $1,001 - $15,000\n"
        "F S: New\nS O: Big Broker IRA\n"
        "Micro Soft Corporation - Common\nStock (MSFX) [ST]\n"
        "P 09/10/2026 09/10/2026 $1,001 - $15,000\n"
        "F S: New\nD: Bought on a dip.\n"
        "Net Flicks, Inc. - Common Stock (NFLZ)\n[ST]\nP 09/14/2026 09/14/2026 $1,001 - $15,000\n"
        "F S: New\n"
    )
    doc = parse_ptr_text(text)
    assert doc.warnings == []
    assert [(r.owner, r.symbol, r.asset_name) for r in doc.rows] == [
        ("SELF", "ZQRK", "Acme Co - Class C Capital Stock (ZQRK)"),
        ("SELF", "APLP", "Apple Pie Inc. - Common Stock (APLP)"),
        ("SELF", "MSFX", "Micro Soft Corporation - Common Stock (MSFX)"),
        ("SELF", "NFLZ", "Net Flicks, Inc. - Common Stock (NFLZ)"),
    ]
    assert [r.description for r in doc.rows] == [None, None, "Bought on a dip.", None]

    # A description that wraps in the middle of a document: the fragment is left in front of
    # the next row's asset name (the ticker is unaffected) rather than risk swallowing the row.
    wrapped = (
        "Acme Co (ZQRK) [ST] P 09/14/2026 09/14/2026 $1,001 - $15,000\nF S: New\n"
        "D: Investment in LLC which is acquiring and managing a commercial office property in San\n"
        "Francisco, CA.\n"
        "Apple Pie Inc. - Common Stock (APLP)\n[ST]\nP 09/08/2026 09/08/2026 $1,001 - $15,000\n"
        "F S: New\n"
    )
    doc = parse_ptr_text(wrapped)
    assert doc.warnings == [] and [r.symbol for r in doc.rows] == ["ZQRK", "APLP"]
    assert doc.rows[0].description.endswith("property in San")
    assert doc.rows[1].asset_name == "Francisco, CA. Apple Pie Inc. - Common Stock (APLP)"


def test_rows_without_recognisable_fields_are_reported_even_after_a_free_text_label():
    # A free-text label does not make an unparseable row disappear into the description.
    text = (
        "Acme Co (ZQRK) [ST] P 09/14/2026 09/14/2026 $1,001 - $15,000\nF S: New\n"
        "D: Sold to cover.\n"
        "Mystery Holding [ST]\nP 09/15/2026 09/15/2026 about ten grand\nF S: New\n"
    )
    doc = parse_ptr_text(text)
    assert [r.symbol for r in doc.rows] == ["ZQRK"] and doc.rows[0].description == "Sold to cover."
    assert len(doc.warnings) == 1 and doc.warnings[0].startswith("no transaction fields: Mystery")


def test_amount_upper_bound_is_searched_a_few_lines_ahead_but_not_further():
    near = (
        "JT Acme Co Common S 09/02/2026 09/15/2026 $100,001 -\n"
        "Stock (ZQRK) [ST] $250,000\nF S : New\n"
    )
    row = parse_ptr_text(near).rows[0]
    assert (row.symbol, row.amount_high, row.asset_name) == (
        "ZQRK",
        250_000,
        "Acme Co Common Stock (ZQRK)",
    )

    def with_filler(lines: list[str]):
        body = "".join(f"{line}\n" for line in lines)
        return parse_ptr_text(
            f"JT Acme Co Common S 09/02/2026 09/15/2026 $100,001 -\n{body}$250,000\nF S : New\n"
        )

    # The bound on the third line after the fields still belongs to the row...
    third = with_filler(["Stock Units", "Series B (ZQRK) [ST]"])
    assert third.warnings == [] and third.rows[0].amount_high == 250_000
    assert third.rows[0].asset_name == "Acme Co Common Stock Units Series B (ZQRK)"
    # ...but a dollar figure four lines down is not taken for it: the row is reported, not guessed.
    far = with_filler(["Stock Units", "Series B", "(ZQRK) [ST]"])
    assert far.rows == [] and "amount upper bound missing" in far.warnings[0]


def test_tickers_are_normalised_to_the_app_spelling():
    assert normalize_symbol("BRK.B") == "BRK-B" and normalize_symbol("brk/b") == "BRK-B"
    text = (
        "SP Berk Holdings Class B (BRK.B) [ST] P 01/02/2026 01/20/2026 $1,001 - $15,000\n"
        "F S : New\n"
        "Moog Like Inc Class A (MOG.A) [ST] S 01/03/2026 01/20/2026 $1,001 - $15,000\n"
        "F S : New\n"
    )
    assert [r.symbol for r in parse_ptr_text(text).rows] == ["BRK-B", "MOG-A"]


def test_capital_gains_mark_is_read_at_the_end_of_the_line():
    def row(mark: str):
        return parse_ptr_text(
            f"Acme Co (ZQRK) [ST] S 01/02/2026 01/20/2026 $1,001 - $15,000{mark}\nF S : New\n"
        ).rows[0]

    assert row(" ✓").cap_gains_over_200 is True and row(" ✓").symbol == "ZQRK"
    assert row(" Yes").cap_gains_over_200 is True
    assert row(" No").cap_gains_over_200 is False
    assert row("").cap_gains_over_200 is None


def test_parse_ptr_text_drops_nul_characters_of_small_caps_labels():
    # pypdf renders the form's small-caps labels with NULs for the lower-case letters.
    text = (
        "Name: Hon. Jane Doe\n"
        "DC Acme Rocket Co Common Stock (ZQRK) [ST]\n"
        "S 08/25/2026 09/01/2026 $100,001 -\n"
        "$250,000\n"
        "F\x00\x00\x00\x00\x00 S\x00\x00\x00\x00\x00: New\n"
    )
    doc = parse_ptr_text(text)
    assert len(doc.rows) == 1 and doc.warnings == []
    row = doc.rows[0]
    assert (row.owner, row.symbol, row.filing_status) == ("DC", "ZQRK", "New")
    assert row.amount_label == "$100,001 - $250,000" and row.amount_high == 250_000


def test_parse_ptr_text_legacy_layout_without_status_labels():
    doc = parse_ptr_text(fixture_text("ptr_text_legacy.txt"))
    assert doc.filer_name == "Hon. John Roe Jr." and doc.warnings == []
    assert [(r.owner, r.symbol, r.side, r.amount_high) for r in doc.rows] == [
        ("SP", "ZQRK", "buy", 15_000),
        ("SELF", None, "sell", 50_000),
    ]
    assert doc.rows[1].asset_name == "Beta Gamma Fund" and doc.rows[1].asset_type == "MF"


def test_parse_ptr_text_reports_unparseable_rows_instead_of_guessing():
    text = (
        "SP Mystery Holding [ST]\nF S : New\n"
        "DC Known Co (KNWN) [ST]\nP 01/02/2026 01/20/2026 $1,001 - $15,000\nF S : New\n"
    )
    doc = parse_ptr_text(text)
    assert [r.symbol for r in doc.rows] == ["KNWN"]
    assert len(doc.warnings) == 1 and "no transaction fields" in doc.warnings[0]
    empty = parse_ptr_text("")
    assert empty.rows == [] and empty.warnings == [] and not empty.no_text


def test_transaction_type_is_not_read_from_a_word_ending_in_p():
    doc = parse_ptr_text("ACME CORP S 01/02/2026 01/20/2026 $1,001 - $15,000\nF S : New\n")
    assert doc.rows[0].side == "sell" and doc.rows[0].asset_name == "ACME CORP"


def test_parse_amount():
    assert parse_amount("$1,001 - $15,000") == (1_001, 15_000)
    assert parse_amount("Over $50,000,000") == (50_000_000, None)
    assert parse_amount("Spouse/DC Over $1,000,000") == (1_000_000, None)
    assert parse_amount("$2,000.00") == (2_000, 2_000)
    assert parse_amount("$2,722.50") == (2_722, 2_723)
    with pytest.raises(ValueError):
        parse_amount("$1,001")
    with pytest.raises(ValueError):
        parse_amount("Overt $1,001")


# --- PDF -----------------------------------------------------------------------------------------


def test_extract_text_reads_text_layer_and_is_empty_for_a_blank_page():
    pdf = tiny_pdf(
        [
            "Name: Hon. Jane Doe",
            "SP Acme Rocket Co Common Stock (ZQRK) [ST] P 03/02/2026 03/20/2026 $1,001 - $15,000",
            "F S : New",
        ]
    )
    assert len(pdf) < 1024
    doc = parse_ptr_text(extract_text(pdf))
    assert doc.filer_name == "Hon. Jane Doe"
    assert [(r.owner, r.symbol, r.side, r.filing_status) for r in doc.rows] == [
        ("SP", "ZQRK", "buy", "New")
    ]
    assert extract_text(tiny_pdf([])).strip() == ""


def test_extract_text_rejects_non_pdf_bytes():
    with pytest.raises(CongressDataError, match="PDF"):
        extract_text(b"hello, not a pdf")


# --- HTTP ----------------------------------------------------------------------------------------

LAST_MODIFIED = "Thu, 22 Oct 2026 13:00:37 GMT"


def _house_transport(pdf: bytes) -> tuple[httpx.Client, list[httpx.Request]]:
    xml = fixture_bytes("house_fd_index.xml")
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path.endswith("/2026FD.zip"):
            return httpx.Response(
                200, content=index_zip(xml), headers={"Last-Modified": LAST_MODIFIED}
            )
        if req.url.path.endswith("/ptr-pdfs/2026/20039001.pdf"):
            return httpx.Response(200, content=pdf)
        return httpx.Response(404)

    client = httpx.Client(
        transport=httpx.MockTransport(handler), headers={"User-Agent": cp.USER_AGENT}
    )
    return client, seen


def test_house_provider_fetches_index_and_ptr():
    pdf = tiny_pdf(["SP Acme Rocket Co (ZQRK) [ST] P 03/02/2026 03/20/2026 $1,001 - $15,000"])
    http, seen = _house_transport(pdf)
    provider = HouseClerkProvider(http=http)

    result = provider.index(2026)
    assert result.year == 2026 and len(result.entries) == 5
    assert result.modified == datetime(2026, 10, 22, 13, 0, 37)

    doc = provider.ptr(2026, "20039001")
    assert [r.symbol for r in doc.rows] == ["ZQRK"] and not doc.no_text

    assert [str(r.url) for r in seen] == [
        cp.INDEX_URL.format(year=2026),
        ptr_url(2026, "20039001"),
    ]
    assert all(r.headers["User-Agent"] == "asset-manager (personal use)" for r in seen)
    assert "@" not in cp.USER_AGENT  # no contact address in a public repository

    with pytest.raises(CongressDataError, match="HTTP 404") as exc:
        provider.ptr(2026, "123")
    assert exc.value.status == 404
    with pytest.raises(CongressDataError, match="HTTP 404") as exc:
        provider.index(2027)
    assert exc.value.status == 404


def test_house_provider_reports_scanned_pdf_as_no_text():
    http, _ = _house_transport(tiny_pdf([]))
    doc = HouseClerkProvider(http=http).ptr(2026, "20039001")
    assert doc.no_text and doc.rows == []


def test_house_provider_retries_5xx_and_transport_errors_once():
    calls: list[int] = []

    def flaky(req: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    http = httpx.Client(transport=httpx.MockTransport(flaky))
    with pytest.raises(CongressDataError, match="HTTP 503"):
        HouseClerkProvider(http=http).index(2026)
    assert len(calls) == 2

    attempts: list[int] = []
    pdf = tiny_pdf([])

    def recovers(req: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            raise httpx.ConnectError("boom", request=req)
        return httpx.Response(200, content=pdf)

    http = httpx.Client(transport=httpx.MockTransport(recovers))
    assert HouseClerkProvider(http=http).ptr(2026, "1").no_text
    assert len(attempts) == 2


def test_default_client_declares_user_agent_without_contact():
    headers = HouseClerkProvider().http.headers
    assert headers["User-Agent"] == cp.USER_AGENT and "@" not in headers["User-Agent"]


def test_fake_provider_records_calls_and_fails_on_demand():
    entry = IndexEntry(2026, "1", "P", date(2026, 10, 1), "Jane", "Doe", state_district="ST01")
    fake = FakeCongressProvider(
        {2026: IndexResult(2026, [entry], None)}, {"1": PtrDocument(rows=[])}
    )
    assert fake.index(2026).entries == [entry] and fake.index(2025).entries == []
    assert fake.ptr(2026, "1").rows == []
    fake.fail_index.add(2026)
    with pytest.raises(CongressDataError, match="simulated"):
        fake.index(2026)
    fake.missing_index.add(2024)
    with pytest.raises(CongressDataError) as exc:
        fake.index(2024)
    assert exc.value.status == 404
    with pytest.raises(CongressDataError) as exc:
        fake.ptr(2026, "nope")
    assert exc.value.status == 404
    fake.fail_docs.add("1")
    with pytest.raises(CongressDataError, match="simulated"):
        fake.ptr(2026, "1")
    assert fake.calls[0] == ("index", "2026") and ("ptr", "2026", "1") in fake.calls


def test_ptr_url():
    assert (
        ptr_url(2026, "20039001")
        == "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/2026/20039001.pdf"
    )
