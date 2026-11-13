"""Company fundamentals over HTTP (DECISIONS.md D-036): `/api/fundamentals/held` and
`/api/fundamentals/{symbol}`.

Synthetic tickers and round numbers only (AAA/BBB/CCC; AAPL as a common example for the
FakeProvider's own figures). The service clock is pinned so the cache and stale paths are
deterministic; nothing here reaches the network.
"""

import json
import re
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.fundamentals import get_source
from app.config import Settings, get_settings
from app.data.provider import Fundamentals, MarketDataError, MarketDataProvider, StatementRow
from app.db.models import AssetType, FundamentalsRow, Side, Transaction
from app.db.session import get_db
from app.deps import get_fundamentals_service, get_provider, get_quote_cache
from app.main import create_app
from app.schemas.fundamentals import DISCLAIMER_KO, SOURCE_FAKE_KO, SOURCE_KO
from app.services.fundamentals import FundamentalsService
from app.services.market_data import QuoteCache

from .test_portfolio_api import buy

T0 = datetime(2026, 10, 16, 12, 0)  # naive UTC, like the service clock
FIGURE_FIELDS = (
    "market_cap",
    "per_trailing",
    "per_forward",
    "pbr",
    "psr",
    "eps_trailing",
    "eps_forward",
    "book_value_per_share",
    "dividend_yield_pct",
    "operating_margin_pct",
    "net_margin_pct",
    "roe_pct",
    "revenue_growth_pct",
    "earnings_growth_pct",
    "debt_to_equity_pct",
)
TEXT_FIELDS = ("currency", "name", "sector", "industry", "summary")
# D-036 §4: the screen never judges a figure. The same words must not come from the server.
JUDGING = re.compile("저평가|고평가|싸다|비싸다|좋다|나쁘다|추천|사세요|파세요|오를|예상 수익")


def figures(symbol: str = "AAA", **changes) -> Fundamentals:
    """A profitable synthetic company with round numbers."""
    base = Fundamentals(
        symbol=symbol,
        currency="USD",
        name=f"{symbol} Inc.",
        sector="Technology",
        industry="Software - Application",
        summary=f"{symbol} Inc. is a synthetic company used in tests.",
        market_cap=2.0e11,
        per_trailing=25.0,
        per_forward=20.0,
        pbr=5.0,
        psr=4.0,
        eps_trailing=4.0,
        eps_forward=5.0,
        book_value_per_share=20.0,
        dividend_yield_pct=1.5,
        operating_margin_pct=30.0,
        net_margin_pct=16.0,
        roe_pct=20.0,
        revenue_growth_pct=10.0,
        earnings_growth_pct=-5.0,
        debt_to_equity_pct=80.0,
        annual=(
            StatementRow(date(2025, 12, 31), 5.0e10, 1.5e10, 8.0e9),
            StatementRow(date(2024, 12, 31), 4.5e10, 1.2e10, 7.0e9),
        ),
        quarterly=(StatementRow(date(2026, 9, 30), 1.4e10, 4.2e9, 2.3e9),),
    )
    return replace(base, **changes)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture(autouse=True)
def clock(client) -> Clock:
    clock = Clock()

    def service(
        db: Session = Depends(get_db), provider: MarketDataProvider = Depends(get_provider)
    ) -> FundamentalsService:
        return FundamentalsService(db, provider, now=clock)

    client.app.dependency_overrides[get_fundamentals_service] = service
    return clock


def get(client, symbol: str) -> dict:
    res = client.get(f"/api/fundamentals/{symbol}")
    assert res.status_code == 200, res.text
    return res.json()


def failing(message: str):
    def get_fundamentals(symbol: str):
        raise MarketDataError(message)

    return get_fundamentals


# --- one symbol -------------------------------------------------------------------------------


def test_symbol_returns_every_figure_with_source_date_and_disclaimer(client, provider):
    provider.fundamentals["AAA"] = figures()
    body = get(client, "AAA")
    assert body == {
        "symbol": "AAA",
        "supported": True,
        "as_of": "2026-10-16",
        "stale": False,
        "error": None,
        "currency": "USD",
        "name": "AAA Inc.",
        "sector": "Technology",
        "industry": "Software - Application",
        "summary": "AAA Inc. is a synthetic company used in tests.",
        "market_cap": 2.0e11,
        "per_trailing": 25.0,
        "per_forward": 20.0,
        "pbr": 5.0,
        "psr": 4.0,
        "eps_trailing": 4.0,
        "eps_forward": 5.0,
        "book_value_per_share": 20.0,
        "dividend_yield_pct": 1.5,
        "operating_margin_pct": 30.0,
        "net_margin_pct": 16.0,
        "roe_pct": 20.0,
        "revenue_growth_pct": 10.0,
        "earnings_growth_pct": -5.0,
        "debt_to_equity_pct": 80.0,
        "annual": [
            {
                "period_end": "2025-12-31",
                "revenue": 5.0e10,
                "operating_income": 1.5e10,
                "net_income": 8.0e9,
            },
            {
                "period_end": "2024-12-31",
                "revenue": 4.5e10,
                "operating_income": 1.2e10,
                "net_income": 7.0e9,
            },
        ],
        "quarterly": [
            {
                "period_end": "2026-09-30",
                "revenue": 1.4e10,
                "operating_income": 4.2e9,
                "net_income": 2.3e9,
            }
        ],
        "notes": [],
        "source_ko": SOURCE_KO,
        "disclaimer_ko": DISCLAIMER_KO,
    }


def test_symbol_is_normalized_and_cached_for_the_day(client, provider, clock):
    provider.fundamentals["AAA"] = figures()
    assert get(client, "aaa")["symbol"] == "AAA"
    clock.now = T0 + timedelta(hours=23)
    assert get(client, "AAA")["stale"] is False
    assert provider.fundamentals_calls == ["AAA"]  # the second answer came from the table
    clock.now = T0 + timedelta(hours=25)
    assert get(client, "AAA")["as_of"] == "2026-10-17"
    assert provider.fundamentals_calls == ["AAA", "AAA"]


def test_the_providers_figures_pass_through_unchanged(client, provider):
    """No unit is converted and nothing is recomputed between the provider and the wire."""
    expected = asdict(provider.get_fundamentals("AAPL"))
    provider.fundamentals_calls.clear()
    body = get(client, "AAPL")
    for name in (*TEXT_FIELDS, *FIGURE_FIELDS):
        assert body[name] == expected[name], name
    for period in ("annual", "quarterly"):
        assert len(body[period]) == len(expected[period]) > 0
        for sent, row in zip(body[period], expected[period], strict=True):
            assert sent == {**row, "period_end": row["period_end"].isoformat()}
    assert body["currency"] == "USD" and body["supported"] is True


@pytest.mark.parametrize(
    ("changes", "notes"),
    [
        # A loss over the last twelve months: no PER, and the response says why.
        ({"per_trailing": None, "eps_trailing": -1.2}, ["per_negative_earnings"]),
        ({"per_trailing": None, "eps_trailing": 0.0}, ["per_negative_earnings"]),
        (
            {"per_trailing": None, "eps_trailing": -1.2, "per_forward": None, "eps_forward": -0.5},
            ["per_negative_earnings", "per_forward_negative_earnings"],
        ),
        ({"per_forward": None, "eps_forward": -0.5}, ["per_forward_negative_earnings"]),
        # The EPS itself was left out (ADR): a 12-month net loss says the same thing.
        (
            {"per_trailing": None, "eps_trailing": None, "net_margin_pct": -8.0},
            ["per_negative_earnings"],
        ),
        # Missing without a stated reason: no note is made up.
        ({"per_trailing": None, "eps_trailing": None, "net_margin_pct": None}, []),
        ({"per_trailing": None, "eps_trailing": None, "net_margin_pct": 12.0}, []),
        ({"per_trailing": None, "eps_trailing": 3.0}, []),
        ({"per_forward": None, "eps_forward": None}, []),
        # A PER that is there is never annotated, whatever the EPS says.
        ({"per_trailing": 12.0, "eps_trailing": -1.0}, []),
    ],
)
def test_a_missing_per_is_explained_only_when_the_figures_say_why(client, provider, changes, notes):
    provider.fundamentals["AAA"] = figures(**changes)
    body = get(client, "AAA")
    assert body["notes"] == notes
    for name, value in changes.items():
        assert body[name] == value


def quarter(operating_income: float | None) -> StatementRow:
    return StatementRow(date(2026, 9, 30), 1.4e10, operating_income, 2.3e9)


def year(operating_income: float | None) -> StatementRow:
    return StatementRow(date(2025, 12, 31), 5.0e10, operating_income, 8.0e9)


@pytest.mark.parametrize(
    ("changes", "notes"),
    [
        # A PER of 25 (12-month net income is positive) beside an operating loss in the
        # newest quarter: the response points at it.
        ({"quarterly": (quarter(-2.0e9),)}, ["operating_loss_net_profit"]),
        (
            {"quarterly": (quarter(-2.0e9),), "annual": (year(-6.0e9),)},
            ["operating_loss_net_profit"],
        ),
        # The newest quarter decides: an operating profit there, whatever the year was.
        ({"quarterly": (quarter(4.2e9),), "annual": (year(-6.0e9),)}, []),
        # Only the newest row counts, not an older one.
        ({"quarterly": (quarter(4.2e9), quarter(-2.0e9))}, []),
        # No quarter, or a quarter without that line: the newest fiscal year decides.
        ({"quarterly": (), "annual": (year(-6.0e9),)}, ["operating_loss_net_profit_annual"]),
        (
            {"quarterly": (quarter(None),), "annual": (year(-6.0e9),)},
            ["operating_loss_net_profit_annual"],
        ),
        ({"quarterly": (), "annual": (year(1.5e10),)}, []),
        # Zero is not a loss, and nothing reported is not a loss either.
        ({"quarterly": (quarter(0.0),)}, []),
        ({"quarterly": (), "annual": ()}, []),
        ({"quarterly": (quarter(None),), "annual": (year(None),)}, []),
        # Without a PER there is nothing to misread: only the reason the PER is missing.
        (
            {"per_trailing": None, "eps_trailing": -1.2, "quarterly": (quarter(-2.0e9),)},
            ["per_negative_earnings"],
        ),
        ({"per_trailing": None, "eps_trailing": None, "quarterly": (quarter(-2.0e9),)}, []),
    ],
)
def test_a_per_beside_an_operating_loss_is_pointed_out(client, provider, changes, notes):
    provider.fundamentals["AAA"] = figures(**changes)
    body = get(client, "AAA")
    assert body["notes"] == notes
    # The figures themselves are sent as they are.
    assert body["per_trailing"] == changes.get("per_trailing", 25.0)
    sent = [row["operating_income"] for row in body["quarterly"]]
    assert sent == [row.operating_income for row in changes["quarterly"]]


@pytest.mark.parametrize(
    ("changes", "notes"),
    [
        # No statement row has an operating income line (a bank, an insurer).
        (
            {"quarterly": (quarter(None),), "annual": (year(None), year(None))},
            ["operating_income_not_reported"],
        ),
        ({"quarterly": (), "annual": (year(None),)}, ["operating_income_not_reported"]),
        # The newest quarter had no revenue to divide by.
        (
            {"quarterly": (StatementRow(date(2026, 9, 30), 0.0, -1.0e8, -1.2e8),)},
            ["zero_revenue_quarter"],
        ),
        # One row does report the line, or nothing was received at all: no reason is made up.
        ({"quarterly": (quarter(None),), "annual": (year(1.5e10),)}, []),
        ({"quarterly": (StatementRow(date(2026, 9, 30), None, 4.2e9, 2.3e9),)}, []),
        ({"quarterly": (), "annual": ()}, []),
    ],
)
def test_a_missing_operating_margin_is_explained_from_the_statements(
    client, provider, changes, notes
):
    # Without a PER, so only the operating-margin notes are in play.
    provider.fundamentals["AAA"] = figures(
        operating_margin_pct=None, per_trailing=None, eps_trailing=None, **changes
    )
    body = get(client, "AAA")
    assert body["operating_margin_pct"] is None
    assert body["notes"] == notes


def test_an_operating_margin_that_is_there_is_never_annotated(client, provider):
    provider.fundamentals["AAA"] = figures(
        operating_margin_pct=12.0, quarterly=(quarter(None),), annual=(year(None),)
    )
    assert get(client, "AAA")["notes"] == []


QUARTER_ENDS = (
    date(2026, 9, 30),
    date(2026, 6, 30),
    date(2026, 3, 31),
    date(2025, 12, 31),
    date(2025, 9, 30),
)


def quarters(operating: tuple, net: tuple, ends: tuple = QUARTER_ENDS) -> tuple[StatementRow, ...]:
    """Consecutive quarters, newest first, with the given operating and net income."""
    return tuple(
        StatementRow(end, 1.0e10, op, n) for end, op, n in zip(ends, operating, net, strict=False)
    )


def fiscal_year(operating: float | None, net: float | None) -> tuple[StatementRow, ...]:
    return (StatementRow(date(2025, 12, 31), 5.0e10, operating, net),)


ABOVE = "net_income_above_operating_income"
ABOVE_ANNUAL = "net_income_above_operating_income_annual"


@pytest.mark.parametrize(
    ("changes", "notes"),
    [
        # Twelve months: 4 x 3.0e9 net against 4 x 2.0e9 operating income.
        ({"quarterly": quarters((2.0e9,) * 4, (3.0e9,) * 4)}, [ABOVE]),
        # Only the newest four quarters count: the fifth would tip the sums the other way.
        ({"quarterly": quarters((2.0e9,) * 4 + (9.0e10,), (3.0e9,) * 4 + (0.0,))}, [ABOVE]),
        ({"quarterly": quarters((3.0e9,) * 4 + (0.0,), (2.0e9,) * 4 + (9.0e10,))}, []),
        # Boundaries: equal sums, and an operating income of zero, are not "above".
        ({"quarterly": quarters((2.0e9,) * 4, (2.0e9,) * 4)}, []),
        ({"quarterly": quarters((0.0,) * 4, (3.0e9,) * 4)}, []),
        ({"quarterly": quarters((1.0e9, -1.0e9, 1.0e9, -1.0e9), (3.0e9,) * 4)}, []),
        # Four full quarters that do not qualify are the answer: the year is not consulted.
        (
            {
                "quarterly": quarters((3.0e9,) * 4, (2.0e9,) * 4),
                "annual": fiscal_year(1.0e10, 2.0e10),
            },
            [],
        ),
        # No twelve-month sum (a line missing in one quarter, three quarters only, or a gap
        # in the quarters): the newest fiscal year decides, and the note says so.
        (
            {
                "quarterly": quarters((2.0e9, None, 2.0e9, 2.0e9), (3.0e9,) * 4),
                "annual": fiscal_year(1.0e10, 2.0e10),
            },
            [ABOVE_ANNUAL],
        ),
        (
            {
                "quarterly": quarters((2.0e9,) * 4, (3.0e9, 3.0e9, None, 3.0e9)),
                "annual": fiscal_year(1.0e10, 2.0e10),
            },
            [ABOVE_ANNUAL],
        ),
        (
            {
                "quarterly": quarters((2.0e9,) * 3, (3.0e9,) * 3),
                "annual": fiscal_year(1.0e10, 2.0e10),
            },
            [ABOVE_ANNUAL],
        ),
        (
            {
                "quarterly": quarters(
                    (2.0e9,) * 4,
                    (3.0e9,) * 4,
                    ends=(
                        date(2026, 9, 30),
                        date(2026, 6, 30),
                        date(2025, 12, 31),
                        date(2025, 9, 30),
                    ),
                ),
                "annual": fiscal_year(1.0e10, 2.0e10),
            },
            [ABOVE_ANNUAL],
        ),
        ({"quarterly": (), "annual": fiscal_year(1.0e10, 2.0e10)}, [ABOVE_ANNUAL]),
        # The year's own boundaries: equal, zero or missing operating income, nothing at all.
        ({"quarterly": (), "annual": fiscal_year(1.0e10, 1.0e10)}, []),
        ({"quarterly": (), "annual": fiscal_year(0.0, 2.0e10)}, []),
        ({"quarterly": (), "annual": fiscal_year(None, 2.0e10)}, []),
        ({"quarterly": (), "annual": fiscal_year(1.0e10, None)}, []),
        ({"quarterly": (), "annual": ()}, []),
        # Without a net margin on the screen there is no figure to read differently.
        ({"quarterly": quarters((2.0e9,) * 4, (3.0e9,) * 4), "net_margin_pct": None}, []),
    ],
)
def test_net_income_above_operating_income_is_pointed_out(client, provider, changes, notes):
    provider.fundamentals["AAA"] = figures(**changes)
    assert get(client, "AAA")["notes"] == notes


def test_an_operating_loss_is_not_reported_twice(client, provider):
    """Twelve months of operating loss with a net profit: the operating-loss note says it;
    the "net above operating" note needs a positive operating income."""
    provider.fundamentals["AAA"] = figures(quarterly=quarters((-2.0e9,) * 4, (3.0e9,) * 4))
    assert get(client, "AAA")["notes"] == ["operating_loss_net_profit"]
    provider.fundamentals["BBB"] = figures("BBB", quarterly=(), annual=fiscal_year(-6.0e9, 8.0e9))
    assert get(client, "BBB")["notes"] == ["operating_loss_net_profit_annual"]
    # A loss in the newest quarter alone, inside a profitable twelve months, is two
    # different facts about two different lines: both are stated.
    provider.fundamentals["CCC"] = figures(
        "CCC", quarterly=quarters((-1.0e9, 3.0e9, 3.0e9, 3.0e9), (4.0e9,) * 4)
    )
    assert get(client, "CCC")["notes"] == ["operating_loss_net_profit", ABOVE]


def test_an_adr_reports_the_currency_mismatch(client, provider):
    mixed = dict.fromkeys(
        ("market_cap", "pbr", "psr", "eps_trailing", "eps_forward", "book_value_per_share")
    )
    provider.fundamentals["AAA"] = figures(currency="TWD", **mixed)
    body = get(client, "AAA")
    assert body["notes"] == ["currency_mismatch"]
    assert body["currency"] == "TWD" and body["market_cap"] is None and body["per_trailing"] == 25.0
    # Statements in another currency with the figures present, or an unknown currency: no note.
    provider.fundamentals["BBB"] = figures("BBB", currency="TWD")
    provider.fundamentals["CCC"] = figures("CCC", currency=None, **mixed)
    provider.fundamentals["DDD"] = figures("DDD", currency="USD", **mixed)
    assert [get(client, s)["notes"] for s in ("BBB", "CCC", "DDD")] == [[], [], []]


@pytest.mark.parametrize(
    ("asked", "symbol"), [("btc", "BTC-USD"), ("ETH-USD", "ETH-USD"), ("KRW-BTC", "KRW-BTC")]
)
def test_a_coin_is_unsupported_without_asking_the_provider(client, provider, db, asked, symbol):
    body = get(client, asked)
    assert body["symbol"] == symbol
    assert body["supported"] is False
    assert (body["as_of"], body["stale"], body["error"]) == (None, False, None)
    assert all(body[name] is None for name in (*TEXT_FIELDS, *FIGURE_FIELDS))
    assert body["annual"] == [] and body["quarterly"] == [] and body["notes"] == []
    assert body["source_ko"] == SOURCE_KO and body["disclaimer_ko"] == DISCLAIMER_KO
    assert provider.fundamentals_calls == []
    assert db.get(FundamentalsRow, symbol) is None


def test_an_etf_is_unsupported_after_one_lookup(client, provider):
    provider.fundamentals["SPY"] = None  # the provider's "a price but no statements"
    body = get(client, "SPY")
    assert body["supported"] is False and body["error"] is None and body["stale"] is False
    assert body["as_of"] == "2026-10-16"  # when it was looked up
    assert all(body[name] is None for name in FIGURE_FIELDS)
    assert get(client, "SPY")["supported"] is False
    assert provider.fundamentals_calls == ["SPY"]


def test_an_unknown_ticker_is_404_and_an_invalid_one_422(client, provider):
    res = client.get("/api/fundamentals/ZZZZ")
    assert res.status_code == 404
    assert res.json() == {"detail": "Unknown symbol 'ZZZZ'"}
    for bad in ("A%20B", "AAA-USD", "TOOLONGTICKER", "%5EGSPC"):
        res = client.get(f"/api/fundamentals/{bad}")
        assert res.status_code == 422, bad
    assert provider.fundamentals_calls == ["ZZZZ"]  # invalid input never reached the provider


def test_a_failed_first_lookup_is_200_with_the_error_and_no_figures(client, provider):
    provider.get_fundamentals = failing("upstream said no")
    body = get(client, "AAA")
    assert body["supported"] is True
    assert (body["as_of"], body["stale"], body["error"]) == (None, True, "upstream said no")
    assert all(body[name] is None for name in FIGURE_FIELDS)
    assert body["annual"] == [] and body["notes"] == []
    # Still 200 when the quote source is down too: only a ticker it does not know is a 404.
    provider.get_quote = failing("quotes are down")
    assert get(client, "BBB")["error"] == "upstream said no"


def test_a_failed_refresh_keeps_the_last_figures_as_stale(client, provider, clock):
    provider.fundamentals["AAA"] = figures()
    fresh = get(client, "AAA")
    working = provider.get_fundamentals

    clock.now = T0 + timedelta(hours=25)
    calls = []
    provider.get_fundamentals = lambda s: (calls.append(s), failing("rate limited")(s))[1]
    stale = get(client, "AAA")
    assert stale["stale"] is True and stale["error"] == "rate limited"
    assert stale["as_of"] == "2026-10-16"  # the date of the figures, not of the failed attempt
    assert {k: v for k, v in stale.items() if k not in ("stale", "error")} == {
        k: v for k, v in fresh.items() if k not in ("stale", "error")
    }
    # Not asked again inside the failure hold-off (1 hour).
    clock.now += timedelta(minutes=50)
    assert get(client, "AAA")["stale"] is True
    assert calls == ["AAA"]

    clock.now += timedelta(minutes=20)
    provider.get_fundamentals = working
    provider.fundamentals["AAA"] = figures(per_trailing=30.0)
    again = get(client, "AAA")
    assert (again["stale"], again["error"], again["as_of"]) == (False, None, "2026-10-17")
    assert again["per_trailing"] == 30.0


# --- held stocks ------------------------------------------------------------------------------


def test_held_is_empty_without_holdings(client, provider):
    res = client.get("/api/fundamentals/held")
    assert res.status_code == 200
    assert res.json() == {
        "items": [],
        "as_of": None,
        "source_ko": SOURCE_KO,
        "disclaimer_ko": DISCLAIMER_KO,
    }
    assert provider.fundamentals_calls == []


def test_held_lists_the_held_stocks_only_largest_first(client, provider):
    assert buy(client, "AAA", 1, 100).status_code == 201
    assert buy(client, "BBB", 50, 100).status_code == 201
    assert buy(client, "btc", 0.5, 60000, asset_type="crypto").status_code == 201
    # Sold out: in the ledger, not held.
    assert buy(client, "CCC", 3, 100).status_code == 201
    assert buy(client, "CCC", 3, 110, day="2026-10-02", side="sell").status_code == 201

    body = client.get("/api/fundamentals/held").json()
    holdings = client.get("/api/portfolio/holdings").json()
    stocks = [h["symbol"] for h in holdings if h["asset_type"] == "stock"]
    assert sorted(stocks) == ["AAA", "BBB"]
    assert [i["symbol"] for i in body["items"]] == stocks  # the order of the holdings list
    assert sorted(provider.fundamentals_calls) == ["AAA", "BBB"]  # the coin was never asked
    assert all(i["supported"] and not i["stale"] and i["per_trailing"] for i in body["items"])
    assert body["as_of"] == "2026-10-16"
    assert body["source_ko"] == SOURCE_KO and body["disclaimer_ko"] == DISCLAIMER_KO
    # "held" is its own route, not the ticker HELD.
    assert "items" in body and "symbol" not in body


def test_held_keeps_an_etf_as_unsupported_and_a_failure_as_an_item(client, provider, clock):
    for symbol in ("AAA", "BBB", "SPY"):
        assert buy(client, symbol, 10, 100).status_code == 201
    provider.fundamentals["AAA"] = figures()
    provider.fundamentals["SPY"] = None
    working = provider.get_fundamentals

    def flaky(symbol: str):
        if symbol == "BBB":
            raise MarketDataError("BBB is down")
        return working(symbol)

    provider.get_fundamentals = flaky
    res = client.get("/api/fundamentals/held")
    assert res.status_code == 200  # one bad symbol does not fail the list
    items = {i["symbol"]: i for i in res.json()["items"]}
    assert set(items) == {"AAA", "BBB", "SPY"}
    assert items["AAA"]["supported"] and items["AAA"]["per_trailing"] == 25.0
    assert items["SPY"]["supported"] is False and items["SPY"]["per_trailing"] is None
    assert items["BBB"]["supported"] is True
    assert (items["BBB"]["stale"], items["BBB"]["error"]) == (True, "BBB is down")
    assert items["BBB"]["as_of"] is None and items["BBB"]["per_trailing"] is None

    # The list is dated by its oldest figures: BBB recovers a day later, AAA is still cached.
    clock.now = T0 + timedelta(hours=20)
    provider.get_fundamentals = working
    body = client.get("/api/fundamentals/held").json()
    by_symbol = {i["symbol"]: i for i in body["items"]}
    assert by_symbol["BBB"]["as_of"] == "2026-10-17" and by_symbol["BBB"]["error"] is None
    assert by_symbol["AAA"]["as_of"] == "2026-10-16"
    assert body["as_of"] == "2026-10-16"


# --- wording and source -----------------------------------------------------------------------


def test_the_server_text_never_judges_a_figure(client, provider):
    assert "투자 조언이 아닙니다" in DISCLAIMER_KO
    assert "이 숫자만으로 매수·매도를 판단할 수 없습니다" in DISCLAIMER_KO
    assert "업종마다 기준이 다릅니다" in DISCLAIMER_KO
    for text in (DISCLAIMER_KO, SOURCE_KO, SOURCE_FAKE_KO):
        assert not JUDGING.search(text), text
    assert buy(client, "AAPL", 1, 100).status_code == 201
    for path in ("/api/fundamentals/AAPL", "/api/fundamentals/held", "/api/fundamentals/btc"):
        text = json.dumps(client.get(path).json(), ensure_ascii=False)
        assert not JUDGING.search(text), path


def test_synthetic_figures_are_labelled_as_such(monkeypatch):
    get_settings.cache_clear()
    try:
        monkeypatch.setenv("AM_MARKET_PROVIDER", "fake")
        assert get_source() == SOURCE_FAKE_KO
        get_settings.cache_clear()
        monkeypatch.setenv("AM_MARKET_PROVIDER", "yfinance")
        assert get_source() == SOURCE_KO
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


# --- the read-only demo -----------------------------------------------------------------------


@pytest.fixture
def demo(db, provider):
    """A demo instance whose ledger holds one stock (AAA) and one coin."""
    for asset_type, symbol, quantity, price in (
        (AssetType.STOCK, "AAA", Decimal("10"), Decimal("100")),
        (AssetType.CRYPTO, "ETH-USD", Decimal("0.5"), Decimal("3000")),
    ):
        db.add(
            Transaction(
                asset_type=asset_type,
                symbol=symbol,
                side=Side.BUY,
                trade_date=date(2026, 10, 1),
                quantity=quantity,
                price=price,
            )
        )
    db.commit()
    app = create_app(Settings(_env_file=None, demo_mode=True))
    quote_cache = QuoteCache()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_provider] = lambda: provider
    app.dependency_overrides[get_quote_cache] = lambda: quote_cache
    with TestClient(app, base_url="http://localhost") as c:
        yield c


def test_demo_serves_its_own_symbols_and_refuses_the_rest(demo, provider, db):
    refused = {
        "detail": "데모에서는 데모 장부에 있는 종목만 볼 수 있어요",
        "code": "demo_symbol_not_allowed",
    }
    for outside in ("BBB", "bbb", "AAAA", "DOGE-USD"):
        res = demo.get(f"/api/fundamentals/{outside}")
        assert res.status_code == 403 and res.json() == refused, outside
    # Refused before the provider or the cache table was touched.
    assert provider.fundamentals_calls == []
    assert db.query(FundamentalsRow).count() == 0

    res = demo.get("/api/fundamentals/AAA")
    assert res.status_code == 200 and res.json()["supported"] is True
    assert provider.fundamentals_calls == ["AAA"]  # a demo symbol does reach the provider
    assert demo.get("/api/fundamentals/eth").json()["supported"] is False

    held = demo.get("/api/fundamentals/held")
    assert held.status_code == 200
    assert [i["symbol"] for i in held.json()["items"]] == ["AAA"]
    assert provider.fundamentals_calls == ["AAA"]  # served from the table the second time
