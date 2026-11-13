"""Company fundamentals: provider units, the offline provider and the cache (D-036).

No network: `yf.Ticker` is replaced, and the info dicts are synthetic companies whose
figures are consistent by construction (price 200, EPS 8 -> PER 25, ...), so every expected
value below can be recomputed by hand from the numbers next to it.
"""

import json
import logging
import threading
import time
from collections import Counter
from dataclasses import fields, replace
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.data import yfinance_provider as yfp
from app.data.assets import has_fundamentals
from app.data.fake_provider import FakeProvider
from app.data.provider import Fundamentals, MarketDataError, StatementRow
from app.data.upbit_provider import RoutingProvider, UpbitProvider
from app.db.base import Base
from app.db.models import FundamentalsRow
from app.db.session import make_engine
from app.services import fundamentals as fundamentals_service
from app.services.fundamentals import (
    DEFAULT_ERROR_TTL,
    ERROR_MAX,
    FundamentalsService,
    FundamentalsView,
    from_payload,
    to_payload,
)
from tests.conftest import TODAY

NOW = datetime.combine(TODAY, datetime.min.time()) + timedelta(hours=10)
NAN = float("nan")

# --- synthetic Yahoo responses ---------------------------------------------------------------

Q_ENDS = ["2026-09-30", "2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"]
Y_ENDS = ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"]


def stmt(columns: dict, rows=("Total Revenue", "Operating Income", "Net Income")) -> pd.DataFrame:
    """A yfinance-shaped income statement: line items as rows, period ends as columns
    (ISO strings become Timestamps, as yfinance labels them)."""
    frame = pd.DataFrame(
        {pd.Timestamp(k) if isinstance(k, str) else k: list(v) for k, v in columns.items()},
        index=list(rows),
        dtype=float,
    )
    # Real statements carry dozens of other lines; one is enough to prove they are ignored.
    frame.loc["Gross Profit"] = 1.0
    return frame


# Newest quarter: 3.3 / 11 = 30% operating margin. Four newest quarters: revenue 40e9, net
# income 8e9 = 20% net margin. Same quarter a year before: revenue 8.8e9 (+25%), net 1.76e9
# (+25%).
QUARTERLY = stmt(
    {
        Q_ENDS[0]: (11.0e9, 3.3e9, 2.2e9),
        Q_ENDS[1]: (10.0e9, 2.9e9, 2.0e9),
        Q_ENDS[2]: (9.5e9, 2.7e9, 1.9e9),
        Q_ENDS[3]: (9.5e9, 2.8e9, 1.9e9),
        Q_ENDS[4]: (8.8e9, 2.5e9, 1.76e9),
        "2025-06-30": (NAN, NAN, NAN),  # Yahoo pads the table with an empty older period
    }
)
ANNUAL = stmt(
    {
        Y_ENDS[0]: (37.0e9, 10.5e9, 7.2e9),
        Y_ENDS[1]: (33.0e9, 9.0e9, 6.1e9),
        Y_ENDS[2]: (30.0e9, 8.0e9, 5.5e9),
        Y_ENDS[3]: (28.0e9, 7.0e9, 5.0e9),
        "2021-12-31": (NAN, NAN, NAN),
    }
)
MRQ = int(datetime(2026, 9, 26, tzinfo=UTC).timestamp())  # exact fiscal date; column says 09-30

INFO = {
    "quoteType": "EQUITY",
    "currency": "USD",
    "financialCurrency": "USD",
    "longName": "AAA Corporation",
    "shortName": "AAA Corp",
    "sector": "Technology",
    "industry": "Software - Application",
    "longBusinessSummary": "  AAA Corporation makes synthetic test data.  ",
    "currentPrice": 200.0,
    "regularMarketPrice": 200.0,
    "sharesOutstanding": 1_000_000_000,
    "marketCap": 200.0e9,  # 200 x 1e9
    "trailingEps": 8.0,
    "trailingPE": 25.0,  # 200 / 8
    "forwardEps": 10.0,
    "forwardPE": 20.0,  # 200 / 10
    "bookValue": 40.0,
    "priceToBook": 5.0,  # 200 / 40
    "totalRevenue": 40.0e9,
    "priceToSalesTrailing12Months": 5.0,  # 200e9 / 40e9
    "netIncomeToCommon": 8.0e9,
    "dividendRate": 2.0,
    "dividendYield": 1.0,  # percent in yfinance 1.7.0: 2 / 200
    "trailingAnnualDividendRate": 1.9,
    "trailingAnnualDividendYield": 0.0095,  # a fraction, unlike dividendYield
    "operatingMargins": 0.30,  # most recent quarter
    "profitMargins": 0.20,  # last 12 months
    "returnOnEquity": 0.22,  # on average equity; 8e9 / (40 x 1e9) = 20% on the ending one
    "revenueGrowth": 0.25,
    "earningsGrowth": 0.27,  # EPS, a little above net income (+25%) after buybacks
    "totalDebt": 20.0e9,
    "debtToEquity": 50.0,  # already percent: 20e9 / 40e9
    "mostRecentQuarter": MRQ,
}


def info(**changes) -> dict:
    """INFO with keys replaced; a value of `...` removes the key."""
    out = {**INFO, **changes}
    return {k: v for k, v in out.items() if v is not ...}


def parse(symbol="AAA", annual=ANNUAL, quarterly=QUARTERLY, **changes) -> Fundamentals:
    return yfp.parse_fundamentals(symbol, info(**changes), annual, quarterly)


def patch_ticker(monkeypatch, info_value, annual=ANNUAL, quarterly=QUARTERLY) -> list[str]:
    """Replace `yf.Ticker`; returns the log of what was asked ("AAA", "AAA.info", ...)."""
    asked: list[str] = []

    def answer(symbol, name, value):
        asked.append(f"{symbol}.{name}")
        if isinstance(value, Exception):
            raise value
        return value

    class Ticker:
        def __init__(self, symbol: str) -> None:
            asked.append(symbol)
            self.symbol = symbol

        info = property(lambda self: answer(self.symbol, "info", info_value))
        income_stmt = property(lambda self: answer(self.symbol, "income_stmt", annual))
        quarterly_income_stmt = property(
            lambda self: answer(self.symbol, "quarterly_income_stmt", quarterly)
        )

    monkeypatch.setattr(yfp, "yf", SimpleNamespace(Ticker=Ticker))
    return asked


# --- contract --------------------------------------------------------------------------------


def test_contract_field_names_and_order():
    """The API schema and the cached payload are built from these names."""
    assert [f.name for f in fields(StatementRow)] == [
        "period_end",
        "revenue",
        "operating_income",
        "net_income",
    ]
    assert [f.name for f in fields(Fundamentals)] == [
        "symbol",
        "currency",
        "name",
        "sector",
        "industry",
        "summary",
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
        "annual",
        "quarterly",
    ]


def test_has_fundamentals():
    assert has_fundamentals("AAA") and has_fundamentals("BRK-B") and has_fundamentals("SPY")
    for symbol in ("BTC-USD", "SOL-USD", "KRW-BTC", "KRW=X", "EURUSD=X", "^GSPC"):
        assert not has_fundamentals(symbol), symbol


# --- YFinanceProvider: units -----------------------------------------------------------------


def test_yfinance_full_response_in_fixed_units(monkeypatch):
    asked = patch_ticker(monkeypatch, INFO)
    got = yfp.YFinanceProvider().get_fundamentals("AAA")
    assert got == Fundamentals(
        symbol="AAA",
        currency="USD",
        name="AAA Corporation",
        sector="Technology",
        industry="Software - Application",
        summary="AAA Corporation makes synthetic test data.",
        market_cap=200.0e9,
        per_trailing=25.0,
        per_forward=20.0,
        pbr=5.0,
        psr=5.0,
        eps_trailing=8.0,
        eps_forward=10.0,
        book_value_per_share=40.0,
        dividend_yield_pct=1.0,  # already percent: not multiplied
        operating_margin_pct=30.0,  # fraction x 100
        net_margin_pct=20.0,
        roe_pct=22.0,
        revenue_growth_pct=25.0,
        earnings_growth_pct=27.0,
        debt_to_equity_pct=50.0,  # already percent: not multiplied
        annual=(
            StatementRow(date(2025, 12, 31), 37.0e9, 10.5e9, 7.2e9),
            StatementRow(date(2024, 12, 31), 33.0e9, 9.0e9, 6.1e9),
            StatementRow(date(2023, 12, 31), 30.0e9, 8.0e9, 5.5e9),
            StatementRow(date(2022, 12, 31), 28.0e9, 7.0e9, 5.0e9),
        ),
        quarterly=(
            StatementRow(date(2026, 9, 30), 11.0e9, 3.3e9, 2.2e9),
            StatementRow(date(2026, 6, 30), 10.0e9, 2.9e9, 2.0e9),
            StatementRow(date(2026, 3, 31), 9.5e9, 2.7e9, 1.9e9),
            StatementRow(date(2025, 12, 31), 9.5e9, 2.8e9, 1.9e9),
            StatementRow(date(2025, 9, 30), 8.8e9, 2.5e9, 1.76e9),
        ),
    )
    # One Ticker, one read of each of the three sources.
    assert asked == ["AAA", "AAA.info", "AAA.income_stmt", "AAA.quarterly_income_stmt"]


def test_reported_ratios_match_the_statement_rows_that_come_back():
    """What a reader of the payload can verify without Yahoo: the operating margin is the
    newest quarterly row's, the net margin the four newest rows', growth is row 0 against
    the row a year before."""
    f = parse()
    q = f.quarterly
    assert f.operating_margin_pct == pytest.approx(q[0].operating_income / q[0].revenue * 100)
    assert f.net_margin_pct == pytest.approx(
        sum(r.net_income for r in q[:4]) / sum(r.revenue for r in q[:4]) * 100
    )
    assert f.revenue_growth_pct == pytest.approx((q[0].revenue / q[4].revenue - 1) * 100)
    assert f.per_trailing == pytest.approx(INFO["currentPrice"] / f.eps_trailing)
    assert f.pbr == pytest.approx(INFO["currentPrice"] / f.book_value_per_share)
    assert f.psr == pytest.approx(f.market_cap / sum(r.revenue for r in q[:4]))


@pytest.mark.parametrize(
    ("dividend_yield", "rate", "trailing_rate", "expected"),
    [
        (1.0, 2.0, 1.9, 1.0),  # percent (yfinance 1.7.0): 2 / 200 = 1%
        (0.01, 2.0, 1.9, 1.0),  # fraction (older yfinance): the same 1%
        (1.004, 2.0, None, 1.004),  # Yahoo rounds to two decimals; small differences pass
        (0, ..., 0, 0.0),  # a company that pays nothing
        (0.0, None, None, 0.0),
        (..., ..., ..., None),  # Yahoo says nothing about dividends
        (..., 2.0, ..., 1.0),  # only the rate: rate / price
        (3.0, 2.0, 1.9, None),  # 3% or 300%: neither is 2 / 200
        (0, 2.0, 1.9, None),  # "no yield" next to a dividend: contradictory
        (1.0, ..., 1.9, 1.0),  # no forward rate: settled loosely by the trailing one
        (0.01, ..., 1.9, 1.0),
        (1.0, ..., 9.0, None),  # trailing 4.5%: neither 1% nor 100% is near it
        (1.0, ..., ..., None),  # nothing to settle the unit with
        (-0.5, 2.0, 1.9, None),
        (NAN, ..., ..., None),
    ],
)
def test_dividend_yield_unit_is_settled_by_dividend_over_price(
    dividend_yield, rate, trailing_rate, expected
):
    got = parse(
        dividendYield=dividend_yield,
        dividendRate=rate,
        trailingAnnualDividendRate=trailing_rate,
    ).dividend_yield_pct
    assert got == (pytest.approx(expected) if expected is not None else None)


def test_trailing_dividend_yield_fraction_is_not_used_as_the_yield():
    """`trailingAnnualDividendYield` (0.0095) sits next to `dividendYield` (1.0) with another
    unit and another definition; it must not leak into the result."""
    assert parse(dividendYield=..., dividendRate=...).dividend_yield_pct is None


@pytest.mark.parametrize(
    ("field", "attr", "raw", "expected"),
    [
        ("earningsGrowth", "earnings_growth_pct", 0.27, 27.0),
        ("earningsGrowth", "earnings_growth_pct", 27.0, 27.0),
        ("earningsGrowth", "earnings_growth_pct", 0.40, 40.0),  # EPS vs net income: loose
        ("earningsGrowth", "earnings_growth_pct", 2.5, None),  # 250% or 2.5%... vs +25%
        ("returnOnEquity", "roe_pct", 0.22, 22.0),
        ("returnOnEquity", "roe_pct", 22.0, 22.0),
        ("returnOnEquity", "roe_pct", 0.45, 45.0),  # average vs ending equity: within a factor
        ("returnOnEquity", "roe_pct", -0.22, None),
        ("returnOnEquity", "roe_pct", 2.2, None),  # 220% or 2.2% against 20%
        ("debtToEquity", "debt_to_equity_pct", 50.0, 50.0),  # percent already
        ("debtToEquity", "debt_to_equity_pct", 0.5, 50.0),  # upstream switched to a ratio
        ("debtToEquity", "debt_to_equity_pct", 84.286, 84.286),
        ("debtToEquity", "debt_to_equity_pct", 500.0, None),
        ("debtToEquity", "debt_to_equity_pct", -12.0, None),  # negative equity
        ("debtToEquity", "debt_to_equity_pct", 0.0, None),  # "no debt" next to 20e9 of debt
    ],
)
def test_info_ratio_scale_is_checked_against_the_same_response(field, attr, raw, expected):
    got = getattr(parse(**{field: raw}), attr)
    assert got == (pytest.approx(expected) if expected is not None else None)


def test_debt_free_company_has_zero_debt_to_equity():
    assert parse(debtToEquity=0.0, totalDebt=0.0).debt_to_equity_pct == 0.0
    assert parse(debtToEquity=0.0, totalDebt=...).debt_to_equity_pct == 0.0  # unchecked


def test_dropped_ratio_is_logged_with_its_field(caplog):
    with caplog.at_level(logging.WARNING, logger=yfp.__name__):
        assert parse(returnOnEquity=2.2).roe_pct is None
    assert "AAA" in caplog.text and "returnOnEquity" in caplog.text


def test_ratios_without_a_reference_use_the_documented_scale():
    """No quarterly statement and no balance figures: nothing to compute from or check
    against, so `info` stands with the scale verified for this yfinance version. Except the
    operating margin, which `info` cannot stand in for."""
    f = parse(
        quarterly=None,
        netIncomeToCommon=...,
        totalRevenue=...,
        bookValue=...,
        priceToBook=...,
        totalDebt=...,
        operatingMargins=0.31125,
        profitMargins=0.27604,
        returnOnEquity=1.42257,
        revenueGrowth=0.117,
        earningsGrowth=-0.031,
        debtToEquity=84.286,
    )
    assert f.operating_margin_pct is None
    assert f.net_margin_pct == pytest.approx(27.604)
    assert f.roe_pct == pytest.approx(142.257)
    assert f.revenue_growth_pct == pytest.approx(11.7)
    assert f.earnings_growth_pct == pytest.approx(-3.1)
    assert f.debt_to_equity_pct == pytest.approx(84.286)
    assert f.quarterly == () and len(f.annual) == 4


# --- YFinanceProvider: statement first -------------------------------------------------------
# QUARTERLY gives 30% (newest quarter), 20% (four newest quarters) and +25% (newest quarter
# against the one a year before). Whatever `info` says, those are the figures.

NEWER_QUARTER = int(datetime(2026, 12, 26, tzinfo=UTC).timestamp())


@pytest.mark.parametrize(
    "changes",
    [
        {},
        # `info` describes another period or another definition (seen on real tickers: a
        # 12-month operating margin next to the newest quarter's rows).
        {"operatingMargins": 0.333, "profitMargins": 0.25, "revenueGrowth": 0.20},
        {"operatingMargins": -0.4974, "profitMargins": -1.5, "revenueGrowth": -0.25},
        # `info` has nothing, or nothing usable.
        {"operatingMargins": ..., "profitMargins": ..., "revenueGrowth": ...},
        {"operatingMargins": NAN, "profitMargins": "n/a", "revenueGrowth": None},
        # Upstream switched to percent.
        {"operatingMargins": 30.0, "profitMargins": 20.0, "revenueGrowth": 25.0},
        # Right after a release `info` is a quarter ahead of the statement table. The ratios
        # still describe the rows that are returned with them.
        {"mostRecentQuarter": NEWER_QUARTER, "operatingMargins": 0.10, "revenueGrowth": 0.05},
        {"mostRecentQuarter": ...},
        # The `info` totals the fallback would be checked against play no part either.
        {"totalRevenue": 1.0, "netIncomeToCommon": ..., "priceToSalesTrailing12Months": ...},
    ],
)
def test_statement_ratios_come_from_the_rows_whatever_info_says(changes):
    f = parse(**changes)
    assert (f.operating_margin_pct, f.net_margin_pct, f.revenue_growth_pct) == (30.0, 20.0, 25.0)
    q = f.quarterly
    assert f.operating_margin_pct == pytest.approx(q[0].operating_income / q[0].revenue * 100)
    assert f.net_margin_pct == pytest.approx(
        sum(r.net_income for r in q[:4]) / sum(r.revenue for r in q[:4]) * 100
    )
    assert f.revenue_growth_pct == pytest.approx((q[0].revenue / q[4].revenue - 1) * 100)


def test_operating_margin_is_the_newest_quarter_not_yahoos_twelve_months():
    """The case that prompted this: Yahoo's operatingMargins was the last four quarters'
    (201 / 310 = 64.84%) while the card says "most recent quarter" (66 / 100 = 66%)."""
    quarterly = stmt(
        {
            Q_ENDS[0]: (100.0e9, 66.0e9, 50.0e9),
            Q_ENDS[1]: (80.0e9, 52.0e9, 40.0e9),
            Q_ENDS[2]: (70.0e9, 45.0e9, 35.0e9),
            Q_ENDS[3]: (60.0e9, 38.0e9, 30.0e9),
            Q_ENDS[4]: (50.0e9, 30.0e9, 25.0e9),
        }
    )
    f = parse(quarterly=quarterly, operatingMargins=0.6484, profitMargins=0.5, revenueGrowth=1.0)
    assert f.operating_margin_pct == 66.0
    assert f.net_margin_pct == 50.0  # 155 / 310
    assert f.revenue_growth_pct == 100.0  # 100 / 50 - 1


def test_computed_ratios_are_rounded_to_four_decimals():
    thirds = stmt(dict.fromkeys(Q_ENDS[:4], (3.0e9, 1.0e9, 2.0e9)) | {Q_ENDS[4]: (7.0e9, 1.0, 1.0)})
    f = parse(quarterly=thirds)
    assert f.operating_margin_pct == 33.3333
    assert f.net_margin_pct == 66.6667
    assert f.revenue_growth_pct == -57.1429  # 3 / 7 - 1


def test_info_that_disagrees_with_the_statement_is_logged_and_the_statement_used(caplog):
    with caplog.at_level(logging.WARNING, logger=yfp.__name__):
        f = parse(profitMargins=0.25, revenueGrowth=0.20)
    assert (f.net_margin_pct, f.revenue_growth_pct) == (20.0, 25.0)
    assert "AAA" in caplog.text
    assert "profitMargins=0.25" in caplog.text and "revenueGrowth=0.2" in caplog.text
    assert "20.0000%" in caplog.text and "25.0000%" in caplog.text


def test_info_close_to_the_statement_is_not_logged(caplog):
    """Within 0.5 points or 5%: rounding upstream, not a disagreement. And the operating
    margin of `info` is not compared at all (its period is not fixed)."""
    with caplog.at_level(logging.WARNING, logger=yfp.__name__):
        f = parse(profitMargins=0.209, revenueGrowth=0.26, operatingMargins=0.10)
    assert (f.operating_margin_pct, f.net_margin_pct, f.revenue_growth_pct) == (30.0, 20.0, 25.0)
    assert caplog.text == ""


@pytest.mark.parametrize(
    "quarterly",
    [
        None,  # no quarterly statement at all
        stmt({q: (10.0e9, 2.0e9) for q in Q_ENDS}, rows=("Total Revenue", "Net Income")),  # bank
        stmt({Q_ENDS[0]: (11.0e9, NAN, 2.2e9), Q_ENDS[1]: (10.0e9, 2.9e9, 2.0e9)}),
        stmt({Q_ENDS[0]: (NAN, 3.3e9, 2.2e9), Q_ENDS[1]: (10.0e9, 2.9e9, 2.0e9)}),
        stmt({Q_ENDS[0]: (0.0, -3.3e9, -2.2e9), Q_ENDS[1]: (10.0e9, 2.9e9, 2.0e9)}),  # no sales
        stmt({Q_ENDS[0]: (-1.0e9, -3.3e9, -2.2e9), Q_ENDS[1]: (10.0e9, 2.9e9, 2.0e9)}),
    ],
)
def test_operating_margin_is_none_when_the_newest_quarter_cannot_give_it(quarterly):
    """Never Yahoo's operatingMargins (its period is unknown: a 12-month figure would sit
    under the label "most recent quarter"), and never an older quarter either."""
    f = parse(quarterly=quarterly, operatingMargins=0.42, revenueGrowth=..., profitMargins=...)
    assert f.operating_margin_pct is None


def test_operating_margin_can_be_negative_or_zero():
    loss = stmt({Q_ENDS[0]: (2.0e9, -0.8e9, -0.9e9)})
    assert parse(quarterly=loss, profitMargins=...).operating_margin_pct == -40.0
    flat = stmt({Q_ENDS[0]: (2.0e9, 0.0, 0.1e9)})
    assert parse(quarterly=flat, profitMargins=...).operating_margin_pct == 0.0


THREE_QUARTERS = stmt({q: (10.0e9, 3.0e9, 2.0e9) for q in Q_ENDS[:3]})
NOT_CONSECUTIVE = stmt(
    {q: (10.0e9, 3.0e9, 4.5e9) for q in ("2026-09-30", "2026-03-31", "2025-09-30", "2025-03-31")}
)
ONE_NET_INCOME_MISSING = stmt(
    dict.fromkeys(Q_ENDS[:3], (10.0e9, 3.0e9, 2.0e9)) | {Q_ENDS[3]: (10.0e9, 3.0e9, NAN)}
)
NO_SALES = stmt({q: (0.0, -1.0e9, -1.0e9) for q in Q_ENDS[:4]})


@pytest.mark.parametrize(
    ("quarterly", "changes", "expected"),
    [
        (THREE_QUARTERS, {}, 20.0),  # `info`: 0.20, consistent with 8e9 / 40e9
        (NOT_CONSECUTIVE, {}, 20.0),  # four rows spanning two years are not 12 months (45%)
        (ONE_NET_INCOME_MISSING, {}, 20.0),
        (NO_SALES, {}, 20.0),
        (None, {}, 20.0),
        (THREE_QUARTERS, {"profitMargins": 0.21}, 21.0),  # close to `info`'s own 20%: kept
        (THREE_QUARTERS, {"profitMargins": 20.0}, 20.0),  # percent upstream
        (THREE_QUARTERS, {"profitMargins": 0.41}, None),  # `info` contradicts itself
        (THREE_QUARTERS, {"profitMargins": ...}, None),  # nothing to fall back to
        # Without `info`'s own totals the documented scale stands.
        (THREE_QUARTERS, {"profitMargins": 0.41, "netIncomeToCommon": ...}, 41.0),
    ],
)
def test_net_margin_falls_back_to_info_without_four_full_quarters(quarterly, changes, expected):
    got = parse(quarterly=quarterly, **changes).net_margin_pct
    assert got == (pytest.approx(expected) if expected is not None else None)


NO_YEAR_AGO = stmt({q: (11.0e9, 3.3e9, 2.2e9) for q in Q_ENDS[:4]})
YEAR_AGO_ZERO = stmt(
    dict.fromkeys(Q_ENDS[:4], (11.0e9, 3.3e9, 2.2e9)) | {Q_ENDS[4]: (0.0, -1.0e9, -1.0e9)}
)
YEAR_AGO_MISSING = stmt(
    dict.fromkeys(Q_ENDS[:4], (11.0e9, 3.3e9, 2.2e9)) | {Q_ENDS[4]: (NAN, 2.5e9, 1.76e9)}
)
NEWEST_REVENUE_MISSING = stmt(
    {Q_ENDS[0]: (NAN, 3.3e9, 2.2e9)} | dict.fromkeys(Q_ENDS[1:], (8.8e9, 2.5e9, 1.76e9))
)
# Five rows, but the fifth is fifteen months back: not the same quarter a year before.
FIFTH_ROW_TOO_OLD = stmt(
    {
        q: (11.0e9, 3.3e9, 2.2e9)
        for q in ("2026-09-30", "2026-06-30", "2026-03-31", "2025-12-31", "2025-06-30")
    }
)


@pytest.mark.parametrize(
    ("quarterly", "changes", "expected"),
    [
        (NO_YEAR_AGO, {}, 25.0),  # `info`: 0.25
        (YEAR_AGO_ZERO, {}, 25.0),  # growth from nothing is not a number
        (YEAR_AGO_MISSING, {}, 25.0),
        (NEWEST_REVENUE_MISSING, {}, 25.0),
        (FIFTH_ROW_TOO_OLD, {}, 25.0),
        (None, {}, 25.0),
        (NO_YEAR_AGO, {"revenueGrowth": -0.031}, -3.1),
        (NO_YEAR_AGO, {"revenueGrowth": ...}, None),
        (NO_YEAR_AGO, {"revenueGrowth": NAN}, None),
    ],
)
def test_revenue_growth_falls_back_to_info_without_the_quarter_a_year_before(
    quarterly, changes, expected
):
    got = parse(quarterly=quarterly, **changes).revenue_growth_pct
    assert got == (pytest.approx(expected) if expected is not None else None)


def test_revenue_growth_uses_the_row_a_year_before_wherever_it_sits():
    """The table can lack a quarter: the row 350-380 days before the newest is the one,
    whether it is the fifth or the fourth."""
    missing_one = stmt(
        {
            "2026-09-30": (11.0e9, 3.3e9, 2.2e9),
            "2026-06-30": (10.0e9, 2.9e9, 2.0e9),
            "2025-12-31": (9.5e9, 2.8e9, 1.9e9),
            "2025-09-30": (8.8e9, 2.5e9, 1.76e9),  # fourth row
            "2025-06-30": (5.5e9, 1.0e9, 0.5e9),  # fifth row: would give +100%
        }
    )
    assert parse(quarterly=missing_one, revenueGrowth=1.0).revenue_growth_pct == 25.0


def test_statements_a_quarter_behind_the_info_do_not_reject_info_only_figures():
    """Right after a release `info` describes a quarter the statement table does not have
    yet. A figure that only `info` gives is then not compared with the older quarter."""
    f = parse(mostRecentQuarter=NEWER_QUARTER, earningsGrowth=2.5)
    assert f.earnings_growth_pct == pytest.approx(250.0)
    # With the quarters aligned the same +250% is rejected (net income grew 25%).
    assert parse(earningsGrowth=2.5).earnings_growth_pct is None
    # No `mostRecentQuarter` at all counts as aligned.
    assert parse(mostRecentQuarter=..., earningsGrowth=2.5).earnings_growth_pct is None


def test_float_noise_of_yahoo_fractions_is_rounded_away():
    f = parse(quarterly=None, profitMargins=0.20000000298, returnOnEquity=0.22000000477)
    assert f.net_margin_pct == 20.0 and f.roe_pct == 22.0


# --- YFinanceProvider: multiples and losses --------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({}, 25.0),
        ({"trailingEps": -2.26, "trailingPE": ...}, None),  # what Yahoo sends for a loss
        ({"trailingEps": -2.26, "trailingPE": -88.5}, None),  # a negative PER is not a PER
        ({"trailingEps": -2.26, "trailingPE": 15.0}, None),  # nor is a positive one
        ({"trailingEps": 0.0, "trailingPE": 15.0}, None),
        ({"trailingPE": 50.0}, None),  # not 200 / 8
        ({"trailingPE": 25.9}, 25.9),  # within 5%: the price moved a little
        ({"trailingPE": "Infinity"}, None),
        ({"trailingPE": NAN}, None),
        ({"trailingPE": ...}, None),  # not recomputed when Yahoo gives none
        ({"trailingEps": ..., "trailingPE": 25.0}, 25.0),  # nothing to check against
        ({"trailingEps": ..., "epsTrailingTwelveMonths": 8.0}, 25.0),  # the other EPS key
        ({"trailingEps": ..., "epsTrailingTwelveMonths": -1.0}, None),
        ({"currentPrice": ..., "regularMarketPrice": ..., "trailingPE": 31.0}, 31.0),
    ],
)
def test_trailing_per(changes, expected):
    assert parse(**changes).per_trailing == expected


def test_trailing_per_is_none_for_a_statement_loss_when_yahoo_gives_no_eps():
    loss = stmt({q: (5.0e9, -1.0e9, -1.2e9) for q in Q_ENDS})
    f = parse(
        quarterly=loss,
        trailingEps=...,
        trailingPE=40.0,
        profitMargins=-0.24,
        operatingMargins=-0.20,
        netIncomeToCommon=-4.8e9,
        totalRevenue=20.0e9,
        priceToSalesTrailing12Months=10.0,
        revenueGrowth=0.0,
        earningsGrowth=...,
        returnOnEquity=-0.12,
    )
    assert f.per_trailing is None and f.net_margin_pct == pytest.approx(-24.0)


def test_loss_making_company():
    """Modelled on a real loss-maker's shape: no trailingPE, a negative forwardPE, no
    earningsGrowth, zero dividend."""
    quarterly = stmt(
        {
            Q_ENDS[0]: (2.0e9, -0.8e9, -0.9e9),
            Q_ENDS[1]: (1.6e9, -0.8e9, -0.8e9),
            Q_ENDS[2]: (1.4e9, -0.9e9, -0.4e9),
            Q_ENDS[3]: (1.3e9, -0.8e9, -0.8e9),
            Q_ENDS[4]: (1.5e9, -1.0e9, -1.2e9),
        }
    )
    f = parse(
        symbol="BBB",
        quarterly=quarterly,
        currentPrice=10.0,
        regularMarketPrice=10.0,
        sharesOutstanding=1_450_000_000,
        marketCap=14.5e9,
        trailingEps=-2.0,
        trailingPE=...,
        forwardEps=-1.5,
        forwardPE=-6.6667,
        bookValue=4.0,
        priceToBook=2.5,
        totalRevenue=6.3e9,
        priceToSalesTrailing12Months=2.3016,
        netIncomeToCommon=-2.9e9,
        dividendRate=...,
        dividendYield=0,
        trailingAnnualDividendRate=0,
        operatingMargins=-0.53,  # Yahoo's, of some other period: not used
        profitMargins=-0.46032,  # -2.9 / 6.3
        returnOnEquity=-0.55,  # -2.9e9 / (4 x 1.45e9) = -50% on ending equity
        revenueGrowth=0.333,  # 2.0 / 1.5 - 1
        earningsGrowth=...,
        totalDebt=5.5e9,
        debtToEquity=95.0,
    )
    assert f.per_trailing is None and f.per_forward is None
    assert f.eps_trailing == -2.0 and f.eps_forward == -1.5  # the loss itself is reported
    assert f.pbr == 2.5 and f.psr == pytest.approx(2.3016)
    assert f.operating_margin_pct == pytest.approx(-40.0)  # -0.8 / 2.0, the newest quarter
    assert f.net_margin_pct == pytest.approx(-2.9 / 6.3 * 100, abs=1e-4)
    assert f.roe_pct == pytest.approx(-55.0)
    assert f.revenue_growth_pct == pytest.approx((2.0 / 1.5 - 1) * 100, abs=1e-4)
    assert f.earnings_growth_pct is None
    assert f.dividend_yield_pct == 0.0
    assert f.debt_to_equity_pct == pytest.approx(95.0)
    assert all(r.net_income < 0 for r in f.quarterly)


def test_earnings_growth_from_a_loss_base_is_not_checked_against_net_income():
    """Growth from a negative base is not a number, so there is no reference; whatever
    Yahoo gives is converted with the documented scale."""
    quarterly = stmt(
        dict.fromkeys(Q_ENDS[:4], (11.0e9, 3.3e9, 2.2e9)) | {Q_ENDS[4]: (8.8e9, -1.0e9, -0.5e9)}
    )
    f = parse(quarterly=quarterly, earningsGrowth=1.5)
    assert f.earnings_growth_pct == pytest.approx(150.0)
    assert f.net_margin_pct == 20.0  # 8.8 / 44: the rest of the response still checks out


@pytest.mark.parametrize(
    ("changes", "per_forward"),
    [
        ({}, 20.0),
        ({"forwardEps": -1.77, "forwardPE": -7.755}, None),
        ({"forwardEps": 0.79, "forwardPE": 6.36, "currentPrice": 5.0}, 6.36),
        ({"forwardEps": ..., "forwardPE": ...}, None),  # no analyst estimate
        ({"forwardEps": ..., "epsForward": 10.0}, 20.0),
        ({"forwardPE": 99.0}, None),
    ],
)
def test_forward_per(changes, per_forward):
    assert parse(**changes).per_forward == per_forward


def test_negative_book_value_has_no_pbr_but_is_reported():
    f = parse(bookValue=-3.5, priceToBook=-57.1, returnOnEquity=..., debtToEquity=...)
    assert f.pbr is None and f.book_value_per_share == -3.5


def test_inconsistent_pbr_is_dropped():
    assert parse(priceToBook=75.67).pbr is None  # not 200 / 40


# --- YFinanceProvider: trailing EPS, PER and PSR from the statement --------------------------
# Yahoo was seen moving `trailingEps` with the price while holding `trailingPE` (same
# statements, EPS +2% overnight). The two always agree with each other, so only the
# statement can tell. Diluted EPS of the four newest quarters: 2.2 + 2.0 + 1.9 + 1.9 = 8.0.

BASE_QUARTERS = [
    (11.0e9, 3.3e9, 2.2e9),
    (10.0e9, 2.9e9, 2.0e9),
    (9.5e9, 2.7e9, 1.9e9),
    (9.5e9, 2.8e9, 1.9e9),
    (8.8e9, 2.5e9, 1.76e9),
]


def with_eps(eps: list[float], ends=Q_ENDS, row: str = "Diluted EPS") -> pd.DataFrame:
    """QUARTERLY's figures plus an EPS line, one value per period end (NAN = not reported)."""
    return stmt(
        {end: (*BASE_QUARTERS[i], eps[i]) for i, end in enumerate(ends)},
        rows=("Total Revenue", "Operating Income", "Net Income", row),
    )


QUARTERLY_EPS = with_eps([2.2, 2.0, 1.9, 1.9, 1.76])


@pytest.mark.parametrize(
    "changes",
    [
        {},
        # The real case, scaled: EPS moved +2% with the price, PER held, the pair consistent
        # (200 / 8.16 = 24.51), so the old check passed it.
        {"trailingEps": 8.16, "trailingPE": 24.5098},
        {"trailingEps": 7.2, "trailingPE": 27.7778},
        # Yahoo gives nothing, or nothing usable.
        {"trailingEps": ..., "trailingPE": ...},
        {"trailingEps": NAN, "trailingPE": "Infinity"},
        # Yahoo says "loss" while the four quarters add up to a profit.
        {"trailingEps": -1.0, "trailingPE": ...},
        {"trailingPE": 50.0},
        {"mostRecentQuarter": NEWER_QUARTER},
    ],
)
def test_trailing_eps_and_per_come_from_the_four_quarters_whatever_yahoo_says(changes):
    f = parse(quarterly=QUARTERLY_EPS, **changes)
    assert f.eps_trailing == 8.0  # 2.2 + 2.0 + 1.9 + 1.9
    assert f.per_trailing == 25.0  # 200 / 8
    assert f.per_trailing == pytest.approx(INFO["currentPrice"] / f.eps_trailing)


def test_per_divides_the_price_of_the_same_response():
    f = parse(quarterly=QUARTERLY_EPS, currentPrice=210.0, trailingPE=25.0)
    assert f.per_trailing == 26.25  # 210 / 8, not Yahoo's 25
    f = parse(quarterly=QUARTERLY_EPS, currentPrice=..., regularMarketPrice=355.63)
    assert f.per_trailing == round(355.63 / 8.0, 4)


def test_yahoo_eps_that_moved_with_the_price_is_logged_and_not_used(caplog):
    with caplog.at_level(logging.WARNING, logger=yfp.__name__):
        f = parse(quarterly=QUARTERLY_EPS, trailingEps=8.16, trailingPE=24.5098)
    assert (f.eps_trailing, f.per_trailing) == (8.0, 25.0)
    assert "AAA" in caplog.text and "trailingEps=8.16" in caplog.text


@pytest.mark.parametrize("yahoo_eps", [8.0, 8.02, 7.98, 8.07, 7.93])
def test_yahoo_eps_within_a_percent_is_not_logged(caplog, yahoo_eps):
    """Yahoo rounds to cents and so do the four quarters: a cent or two, or under 1%, is
    rounding. The statement's figure is used all the same."""
    with caplog.at_level(logging.WARNING, logger=yfp.__name__):
        f = parse(quarterly=QUARTERLY_EPS, trailingEps=yahoo_eps, trailingPE=200.0 / yahoo_eps)
    assert f.eps_trailing == 8.0 and caplog.text == ""


@pytest.mark.parametrize(
    ("eps", "expected"),
    [
        ([-0.5, -0.6, 0.1, -0.2, 0.3], -1.2),  # a loss over the twelve months
        ([0.5, -0.5, 0.25, -0.25, 1.0], 0.0),  # exactly nothing earned
        ([0.03, -0.1, -0.05, 0.03, -0.06], -0.09),  # float noise of the sum is rounded away
    ],
)
def test_statement_eps_at_or_below_zero_has_no_per_whatever_yahoo_gives(eps, expected):
    f = parse(quarterly=with_eps(eps), trailingEps=0.5, trailingPE=15.0)
    assert f.eps_trailing == expected  # the loss itself is reported
    assert f.per_trailing is None


def test_fiscal_year_that_ends_with_the_newest_quarter_gives_the_eps():
    """Yahoo leaves the fourth quarter's EPS empty; the annual column is those same twelve
    months. Numbers of the real case: statement 8.98, Yahoo 9.16 a day after the price rose,
    PER 38.82 from Yahoo against 355.63 / 8.98 = 39.60."""
    quarterly = with_eps([NAN, 2.02, 2.01, 2.84, 1.85])
    with_eps_row = ("Total Revenue", "Operating Income", "Net Income", "Diluted EPS")
    annual = stmt(
        {Q_ENDS[0]: (37.0e9, 10.5e9, 7.2e9, 8.98), Q_ENDS[4]: (33.0e9, 9.0e9, 6.1e9, 7.46)},
        rows=with_eps_row,
    )
    yahoo = {"currentPrice": 355.63, "trailingEps": 9.16, "trailingPE": 38.8242}
    f = parse(annual=annual, quarterly=quarterly, **yahoo)
    assert f.eps_trailing == 8.98
    assert f.per_trailing == 39.6024

    # A fiscal year that ended three quarters ago is not the last twelve months: Yahoo's
    # pair stands in (and passes, being consistent with itself).
    older = stmt(
        {Y_ENDS[0]: (37.0e9, 10.5e9, 7.2e9, 8.98), Y_ENDS[1]: (33.0e9, 9.0e9, 6.1e9, 7.46)},
        rows=with_eps_row,
    )
    f = parse(annual=older, quarterly=quarterly, **yahoo)
    assert (f.eps_trailing, f.per_trailing) == (9.16, 38.8242)


HALF_YEARS = ["2026-09-30", "2026-03-31", "2025-09-30", "2025-03-31", "2024-09-30"]


@pytest.mark.parametrize(
    "quarterly",
    [
        QUARTERLY,  # no EPS line at all
        None,
        with_eps([2.2, 2.0, 1.9, 1.9, 1.76], row="Basic EPS"),  # basic is not a substitute
        with_eps([2.2, NAN, 1.9, 1.9, 1.76]),  # one of the four quarters not reported
        with_eps([2.2, 2.0, 1.9, 1.9, 1.76], ends=HALF_YEARS),  # four rows, two years
        with_eps([2.2, 2.0, 1.9], ends=Q_ENDS[:3]),
    ],
)
def test_without_four_quarters_of_diluted_eps_yahoos_pair_stands_in(quarterly):
    """Checked as before, which a pair that drifted together still passes: without the
    statement there is nothing better to hold it against."""
    assert parse(quarterly=quarterly).eps_trailing == 8.0
    assert parse(quarterly=quarterly).per_trailing == 25.0
    drifted = parse(quarterly=quarterly, trailingEps=8.16, trailingPE=24.5098)
    assert (drifted.eps_trailing, drifted.per_trailing) == (8.16, 24.5098)
    assert parse(quarterly=quarterly, trailingPE=50.0).per_trailing is None  # not 200 / 8
    assert parse(quarterly=quarterly, trailingEps=-2.26, trailingPE=15.0).per_trailing is None


def test_adr_keeps_yahoos_per_and_never_the_statement_eps():
    """The statement's EPS is in the statement currency (491 TWD); the price is in USD."""
    in_twd = with_eps([147.13, 136.25, 110.4, 97.5, 87.2])
    f = parse(quarterly=in_twd, financialCurrency="TWD", trailingEps=16.0, trailingPE=12.5)
    assert f.eps_trailing is None
    assert f.per_trailing == 12.5  # Yahoo's: 200 / 16, both in USD


def test_statement_eps_without_a_price_keeps_yahoos_multiple_unchecked():
    no_price = {"currentPrice": ..., "regularMarketPrice": ...}
    f = parse(quarterly=QUARTERLY_EPS, **no_price)
    assert (f.eps_trailing, f.per_trailing) == (8.0, 25.0)
    assert parse(quarterly=QUARTERLY_EPS, trailingPE=..., **no_price).per_trailing is None
    assert parse(quarterly=QUARTERLY_EPS, trailingPE=-3.0, **no_price).per_trailing is None


@pytest.mark.parametrize(
    "changes",
    [
        {},
        # A bank: Yahoo's own revenue is 4% below the four quarters' (38.4e9 against 40e9).
        {"totalRevenue": 38.4e9, "priceToSalesTrailing12Months": 5.2083},
        {"priceToSalesTrailing12Months": 0.4159},
        {"priceToSalesTrailing12Months": ...},
        {"totalRevenue": ...},
    ],
)
def test_psr_is_the_market_cap_over_the_four_quarters_revenue(changes):
    f = parse(**changes)
    assert f.psr == 5.0  # 200e9 / (11 + 10 + 9.5 + 9.5)e9
    assert f.psr == pytest.approx(f.market_cap / sum(r.revenue for r in f.quarterly[:4]))


def test_psr_rounds_and_logs_only_a_large_difference(caplog):
    with caplog.at_level(logging.WARNING, logger=yfp.__name__):
        f = parse(marketCap=123.456789e9, priceToSalesTrailing12Months=3.2)  # 3.7% above
    assert f.psr == 3.0864 and caplog.text == ""
    with caplog.at_level(logging.WARNING, logger=yfp.__name__):
        parse(priceToSalesTrailing12Months=0.4159)
    assert "priceToSalesTrailing12Months=0.4159" in caplog.text


@pytest.mark.parametrize(
    ("quarterly", "changes", "expected"),
    [
        (None, {}, 5.0),  # Yahoo's 5.0 = 200e9 / 40e9, its own totalRevenue
        (THREE_QUARTERS, {}, 5.0),
        (NOT_CONSECUTIVE, {}, 5.0),
        (NO_SALES, {}, 5.0),  # nothing to divide by in the statement
        (None, {"priceToSalesTrailing12Months": 0.4159}, None),  # not 200e9 / 40e9
        (None, {"priceToSalesTrailing12Months": ...}, None),
        (None, {"totalRevenue": ..., "priceToSalesTrailing12Months": 7.5}, 7.5),  # unchecked
        (QUARTERLY, {"marketCap": ...}, 5.0),  # no market cap to divide: Yahoo's, unchecked
        (QUARTERLY, {"financialCurrency": "TWD"}, None),  # USD over TWD
    ],
)
def test_psr_falls_back_to_yahoo_without_four_full_quarters(quarterly, changes, expected):
    assert parse(quarterly=quarterly, **changes).psr == expected


def test_adr_with_statements_in_another_currency():
    """Statements in TWD, quote in USD: Yahoo's PSR divides USD by TWD and its book value
    matched neither currency, and the EPS and market cap are USD amounts that
    `Fundamentals.currency` (TWD) would mislabel. Ratios inside one currency stay."""
    f = parse(financialCurrency="TWD", priceToSalesTrailing12Months=0.4159, priceToBook=75.67)
    assert f.currency == "TWD"
    assert f.market_cap is None and f.pbr is None and f.psr is None
    assert f.eps_trailing is None and f.eps_forward is None and f.book_value_per_share is None
    assert f.per_trailing == 25.0 and f.per_forward == 20.0  # price / EPS, both in USD
    assert f.dividend_yield_pct == 1.0  # dividend / price, both in USD
    assert f.operating_margin_pct == 30.0 and f.net_margin_pct == 20.0
    assert f.revenue_growth_pct == 25.0 and f.earnings_growth_pct == 27.0
    # No same-currency equity to compare with, so these keep the documented scale.
    assert f.roe_pct == 22.0 and f.debt_to_equity_pct == 50.0
    assert f.quarterly[0].revenue == 11.0e9  # the statement itself, in TWD


@pytest.mark.parametrize("missing", ["financialCurrency", "currency"])
def test_unknown_currency_is_treated_like_a_mismatch(missing):
    f = parse(**{missing: ...})
    assert f.market_cap is None and f.eps_trailing is None and f.pbr is None and f.psr is None
    assert f.per_trailing == 25.0
    assert f.currency == (None if missing == "financialCurrency" else "USD")


def test_currency_comparison_ignores_case():
    assert parse(financialCurrency="usd").market_cap == 200.0e9


# --- YFinanceProvider: statements ------------------------------------------------------------


def test_statement_rows_sorted_newest_first_and_capped():
    shuffled = stmt(
        {
            "2024-03-31": (3.0, 0.3, 0.2),
            "2026-03-31": (5.0, 0.5, 0.4),
            "2022-03-31": (1.0, 0.1, 0.0),
            "2025-03-31": (4.0, 0.4, 0.3),
            "2023-03-31": (2.0, 0.2, 0.1),
            "2021-03-31": (0.5, 0.0, -0.1),
        }
    )
    rows = yfp.statement_rows(shuffled, 4)
    assert [r.period_end.year for r in rows] == [2026, 2025, 2024, 2023]
    assert [r.revenue for r in yfp.statement_rows(shuffled, 5)] == [5.0, 4.0, 3.0, 2.0, 1.0]


def test_statement_nan_and_missing_lines_are_none_for_that_value_only():
    frame = stmt(
        {"2025-12-31": (10.0, NAN, 2.0), "2024-12-31": (float("inf"), 1.0, NAN)},
    )
    assert yfp.statement_rows(frame, 4) == (
        StatementRow(date(2025, 12, 31), 10.0, None, 2.0),
        StatementRow(date(2024, 12, 31), None, 1.0, None),
    )
    # A bank: no "Operating Income" line at all.
    bank = stmt({"2025-12-31": (10.0, 2.0)}, rows=("Total Revenue", "Net Income"))
    assert yfp.statement_rows(bank, 4) == (StatementRow(date(2025, 12, 31), 10.0, None, 2.0),)


def test_statement_empty_periods_dropped_at_the_ends_and_kept_in_the_middle():
    frame = stmt(
        {
            "2026-12-31": (NAN, NAN, NAN),  # a column Yahoo added before filling it
            "2026-09-30": (9.0, 1.0, 0.5),
            "2026-06-30": (NAN, NAN, NAN),  # a gap in Yahoo's table
            "2026-03-31": (7.0, 1.0, 0.5),
            "2025-12-31": (NAN, NAN, NAN),
            "2025-09-30": (NAN, NAN, NAN),
        }
    )
    assert yfp.statement_rows(frame, 5) == (
        StatementRow(date(2026, 9, 30), 9.0, 1.0, 0.5),
        StatementRow(date(2026, 6, 30), None, None, None),
        StatementRow(date(2026, 3, 31), 7.0, 1.0, 0.5),
    )
    # The cap can cut right after a gap: no empty row is left at the end.
    assert yfp.statement_rows(frame, 2) == (StatementRow(date(2026, 9, 30), 9.0, 1.0, 0.5),)


def test_statement_column_labels():
    aware = pd.Timestamp("2025-12-31 00:00", tz="America/New_York")
    frame = pd.DataFrame(
        {
            aware: (3.0, 2.0, 1.0),
            "2024-12-31": (2.0, 1.0, 0.5),  # a plain string, not a Timestamp
            date(2023, 12, 31): (1.0, 0.5, 0.2),
            0: (99.0, 99.0, 99.0),  # a positional label is not 1970-01-01
            "TTM": (98.0, 98.0, 98.0),
        },
        index=["Total Revenue", "Operating Income", "Net Income"],
    )
    assert [r.period_end for r in yfp.statement_rows(frame, 5)] == [
        date(2025, 12, 31),
        date(2024, 12, 31),
        date(2023, 12, 31),
    ]


@pytest.mark.parametrize("frame", [None, pd.DataFrame(), {}, [], "n/a", pd.Series([1.0])])
def test_statement_empty_shapes(frame):
    assert yfp.statement_rows(frame, 4) == ()


def test_statement_gap_falls_back_to_info_and_matches_last_year_by_date():
    """One quarter missing in the middle (seen on a real large cap): the four newest rows
    are not twelve months, so the net margin is checked against `info` instead, and the
    year-ago quarter is found by its date, not by counting rows."""
    gap = stmt(
        {
            Q_ENDS[0]: (11.0e9, 3.3e9, 2.2e9),
            Q_ENDS[1]: (NAN, NAN, NAN),
            Q_ENDS[2]: (9.5e9, 2.7e9, 1.9e9),
            Q_ENDS[3]: (9.5e9, 2.8e9, 1.9e9),
            Q_ENDS[4]: (8.8e9, 2.5e9, 1.76e9),
            "2025-06-30": (8.0e9, 2.0e9, 1.5e9),
        }
    )
    f = parse(quarterly=gap)
    assert [r.period_end for r in f.quarterly] == [date.fromisoformat(q) for q in Q_ENDS]
    assert f.quarterly[1] == StatementRow(date(2026, 6, 30), None, None, None)
    assert f.net_margin_pct == 20.0 and f.revenue_growth_pct == 25.0
    assert f.operating_margin_pct == 30.0


def test_half_year_reporter_is_not_summed_as_twelve_months():
    """Four half-years are two years; with no usable 12-month sum the net margin is checked
    against `info` (8e9 / 40e9 = 20%), not against 4 rows that span 24 months."""
    halves = stmt(
        {
            "2026-06-30": (20.0e9, 6.0e9, 9.0e9),
            "2025-12-31": (20.0e9, 6.0e9, 9.0e9),
            "2025-06-30": (20.0e9, 6.0e9, 9.0e9),
            "2024-12-31": (20.0e9, 6.0e9, 9.0e9),
        }
    )
    mrq = int(datetime(2026, 6, 30, tzinfo=UTC).timestamp())
    f = parse(quarterly=halves, mostRecentQuarter=mrq, revenueGrowth=0.0, earningsGrowth=0.0)
    assert f.net_margin_pct == 20.0  # 45% from the four rows would have rejected it
    assert f.operating_margin_pct == 30.0  # 6 / 20, the newest reported period


# --- YFinanceProvider: failures and non-companies --------------------------------------------


@pytest.mark.parametrize("symbol", ["BTC-USD", "ETH-USD", "KRW-BTC", "KRW=X", "^GSPC"])
def test_yfinance_assets_without_statements_skip_the_request(monkeypatch, symbol):
    asked = patch_ticker(monkeypatch, RuntimeError("must not be called"))
    assert yfp.YFinanceProvider().get_fundamentals(symbol) is None
    assert asked == []


@pytest.mark.parametrize("quote_type", ["ETF", "MUTUALFUND", "INDEX", "etf"])
def test_yfinance_fund_is_none_and_statements_are_not_requested(monkeypatch, quote_type):
    fund = {
        "quoteType": quote_type,
        "trailingPE": 23.86,
        "priceToBook": 1.75,
        "dividendYield": 1,
        "yield": 0.01,
    }
    asked = patch_ticker(monkeypatch, fund, RuntimeError("no"), RuntimeError("no"))
    assert yfp.YFinanceProvider().get_fundamentals("SPY") is None
    assert asked == ["SPY", "SPY.info"]


@pytest.mark.parametrize("empty", [None, {}, {"trailingPegRatio": None}, [], "error"])
def test_yfinance_unknown_ticker_is_an_error_not_none(monkeypatch, empty):
    """An unknown ticker and a swallowed HTTP error both look like this; reporting either
    as "no statements" would cache a wrong answer for a day."""
    patch_ticker(monkeypatch, empty, pd.DataFrame(), pd.DataFrame())
    with pytest.raises(MarketDataError, match="ZZZZ"):
        yfp.YFinanceProvider().get_fundamentals("ZZZZ")


def test_yfinance_info_failure_becomes_market_data_error(monkeypatch):
    patch_ticker(monkeypatch, RuntimeError("Too Many Requests"))
    with pytest.raises(MarketDataError, match="AAA.*Too Many Requests"):
        yfp.YFinanceProvider().get_fundamentals("AAA")


@pytest.mark.parametrize("failing", ["annual", "quarterly"])
def test_yfinance_statement_failure_becomes_market_data_error(monkeypatch, failing):
    frames = {"annual": ANNUAL, "quarterly": QUARTERLY, failing: KeyError("timeSeries")}
    patch_ticker(monkeypatch, INFO, frames["annual"], frames["quarterly"])
    with pytest.raises(MarketDataError, match="AAA"):
        yfp.YFinanceProvider().get_fundamentals("AAA")


def test_yfinance_revenue_without_any_statement_is_a_failed_fetch(monkeypatch):
    """yfinance answers a failed statement request with an empty frame."""
    patch_ticker(monkeypatch, INFO, pd.DataFrame(), None)
    with pytest.raises(MarketDataError, match="income statement"):
        yfp.YFinanceProvider().get_fundamentals("AAA")


def test_yfinance_one_statement_is_enough(monkeypatch):
    patch_ticker(monkeypatch, INFO, ANNUAL, pd.DataFrame())
    f = yfp.YFinanceProvider().get_fundamentals("AAA")
    assert f.quarterly == () and len(f.annual) == 4
    assert f.operating_margin_pct is None  # no newest quarter to compute it from
    assert f.net_margin_pct == 20.0 and f.revenue_growth_pct == 25.0  # `info` stands in


def test_yfinance_equity_with_almost_nothing(monkeypatch):
    patch_ticker(monkeypatch, {"quoteType": "EQUITY", "shortName": "New Co"}, None, None)
    f = yfp.YFinanceProvider().get_fundamentals("NEWC")
    assert f == Fundamentals("NEWC", None, "New Co", *([None] * 18), annual=(), quarterly=())


def test_yfinance_bad_values_are_none_not_errors():
    f = parse(
        marketCap=NAN,
        trailingEps="n/a",
        trailingPE=float("inf"),
        forwardEps=None,
        forwardPE=True,  # a bool is not 1.0
        bookValue=float("-inf"),
        priceToBook=None,
        priceToSalesTrailing12Months={"raw": 5.0},
        dividendYield="Infinity",
        dividendRate=...,
        operatingMargins=None,
        profitMargins="",
        returnOnEquity=NAN,
        revenueGrowth=[],
        earningsGrowth=...,
        debtToEquity=None,
        longName=None,
        shortName="",
        sector=123,
        longBusinessSummary="   ",
        mostRecentQuarter="soon",
    )
    nothing_from_info = Fundamentals(
        "AAA",
        "USD",
        None,
        None,
        "Software - Application",
        *([None] * 16),
        annual=f.annual,
        quarterly=f.quarterly,
    )
    # The statement still gives its three ratios.
    assert f == replace(
        nothing_from_info,
        operating_margin_pct=30.0,
        net_margin_pct=20.0,
        revenue_growth_pct=25.0,
    )
    assert len(f.annual) == 4 and len(f.quarterly) == 5


def test_yfinance_numeric_strings_and_ints_are_accepted():
    f = parse(marketCap="200000000000", trailingEps=8, trailingPE="25.0")
    assert f.market_cap == 200.0e9 and f.per_trailing == 25.0 and f.eps_trailing == 8.0


# --- Upbit / routing -------------------------------------------------------------------------


def test_upbit_has_no_fundamentals_and_routing_delegates():
    default = FakeProvider(today=TODAY)
    upbit = UpbitProvider(http=object())  # never used: no request is made
    routed = RoutingProvider(default, upbit)
    assert upbit.get_fundamentals("KRW-BTC") is None
    assert routed.get_fundamentals("KRW-BTC") is None
    assert routed.get_fundamentals("AAA") == default.get_fundamentals("AAA")
    assert default.fundamentals_calls == ["AAA", "AAA"]  # KRW-BTC never reached it


# --- FakeProvider ----------------------------------------------------------------------------

SYNTHETIC = [f"{c}{c}{c}" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]


def test_fake_is_deterministic_and_shaped_like_the_contract():
    a = FakeProvider(today=TODAY).get_fundamentals("AAA")
    b = FakeProvider(today=TODAY).get_fundamentals("AAA")
    assert a == b and a is not None
    assert a.symbol == "AAA" and a.currency == "USD" and a.name == "AAA Inc."
    assert a.sector and a.industry and a.summary
    assert len(a.annual) == 4 and len(a.quarterly) == 5
    assert [r.period_end for r in a.quarterly] == [
        date(2026, 9, 30),
        date(2026, 6, 30),
        date(2026, 3, 31),
        date(2025, 12, 31),
        date(2025, 9, 30),
    ]
    assert [r.period_end for r in a.annual] == [date(y, 12, 31) for y in (2025, 2024, 2023, 2022)]
    assert a != FakeProvider(today=TODAY).get_fundamentals("BBB")
    assert from_payload(json.loads(json.dumps(to_payload(a)))) == a


@pytest.mark.parametrize("symbol", SYNTHETIC)
def test_fake_figures_are_internally_consistent(symbol):
    p = FakeProvider(today=TODAY)
    f = p.get_fundamentals(symbol)
    price = p.get_quote(symbol).price
    q = f.quarterly
    revenue_ttm = sum(r.revenue for r in q[:4])
    net_ttm = sum(r.net_income for r in q[:4])
    assert f.pbr == pytest.approx(price / f.book_value_per_share, rel=1e-3)
    assert f.psr == pytest.approx(f.market_cap / revenue_ttm, rel=1e-3)
    # The EPS is the four quarters' net income per share (shares = market cap / price), the
    # same statement-first definitions as the real provider.
    assert f.eps_trailing * f.market_cap / price == pytest.approx(net_ttm, rel=1e-3)
    assert f.operating_margin_pct == pytest.approx(
        q[0].operating_income / q[0].revenue * 100, abs=0.01
    )
    assert f.net_margin_pct == pytest.approx(net_ttm / revenue_ttm * 100, abs=0.01)
    assert f.revenue_growth_pct == pytest.approx((q[0].revenue / q[4].revenue - 1) * 100, abs=0.01)
    if net_ttm > 0:
        assert f.eps_trailing > 0
        assert f.per_trailing == pytest.approx(price / f.eps_trailing, rel=1e-3)
        assert f.per_forward == pytest.approx(price / f.eps_forward, rel=1e-3)
        assert f.roe_pct > 0
    else:  # a loss: no PER, and the loss itself is visible
        assert f.eps_trailing < 0 and f.per_trailing is None and f.per_forward is None
        assert all(r.net_income < 0 for r in f.quarterly + f.annual)
        assert f.net_margin_pct < 0 and f.roe_pct < 0
        assert f.earnings_growth_pct is None and f.dividend_yield_pct == 0.0


def test_fake_annual_row_is_the_sum_of_its_four_quarters():
    """The synthetic fiscal year is the calendar year. In January the four newest quarters
    are exactly last year."""
    f = FakeProvider(today=date(2026, 1, 15)).get_fundamentals("AAA")
    assert [r.period_end for r in f.quarterly[:4]] == [
        date(2025, 12, 31),
        date(2025, 9, 30),
        date(2025, 6, 30),
        date(2025, 3, 31),
    ]
    year = f.annual[0]
    assert year.period_end == date(2025, 12, 31)
    assert year.revenue == sum(r.revenue for r in f.quarterly[:4])
    assert year.operating_income == sum(r.operating_income for r in f.quarterly[:4])
    assert year.net_income == sum(r.net_income for r in f.quarterly[:4])


# Pinned so the fake stays the same across runs and platforms, and so API and screen tests
# can pick a known loss-maker without an override.
FAKE_LOSS_MAKERS = ["DDD", "GGG", "JJJ", "OOO", "QQQ", "UUU", "WWW", "ZZZ"]


def test_fake_has_both_profitable_and_loss_making_companies():
    p = FakeProvider(today=TODAY)
    losses = [s for s in SYNTHETIC if p.get_fundamentals(s).per_trailing is None]
    assert losses == FAKE_LOSS_MAKERS
    assert p.get_fundamentals("AAA").per_trailing > 0


def test_fake_quarter_keeps_its_numbers_as_today_moves():
    early = FakeProvider(today=TODAY).get_fundamentals("AAA")
    later = FakeProvider(today=TODAY + timedelta(days=100)).get_fundamentals("AAA")
    assert later.quarterly[0].period_end == date(2026, 12, 31)
    assert later.quarterly[1:] == early.quarterly[:4]
    assert later.annual[0].period_end == date(2026, 12, 31)
    assert later.annual[1:] == early.annual[:3]


def test_fake_override_wins_including_none():
    fixed = replace(FakeProvider(today=TODAY).get_fundamentals("AAA"), per_trailing=12.5)
    p = FakeProvider(today=TODAY, fundamentals={"AAA": fixed, "SPY": None})
    assert p.get_fundamentals("AAA") is fixed
    assert p.get_fundamentals("SPY") is None
    assert p.get_fundamentals("BBB") is not None
    assert p.fundamentals_calls == ["AAA", "SPY", "BBB"]


@pytest.mark.parametrize("symbol", ["BTC-USD", "ETH-USD", "KRW-BTC", "KRW-SOL", "KRW=X"])
def test_fake_assets_without_statements_are_none(symbol):
    assert FakeProvider(today=TODAY).get_fundamentals(symbol) is None


def test_fake_unknown_symbol_raises():
    with pytest.raises(MarketDataError, match="ZZZZ"):
        FakeProvider(today=TODAY, unknown={"ZZZZ"}).get_fundamentals("ZZZZ")


# --- payload ---------------------------------------------------------------------------------

SPARSE = Fundamentals("CCC", None, None, None, None, None, *([None] * 15))


@pytest.mark.parametrize(
    "data",
    [
        FakeProvider(today=TODAY).get_fundamentals("AAA"),
        FakeProvider(today=TODAY).get_fundamentals("DDD"),
        SPARSE,
        replace(SPARSE, annual=(StatementRow(date(2025, 12, 31), None, -1.5, 0.0),)),
    ],
)
def test_payload_round_trip_through_json(data):
    payload = to_payload(data)
    assert from_payload(payload) == data
    assert from_payload(json.loads(json.dumps(payload))) == data  # what the JSON column does


def test_payload_is_plain_json_with_iso_dates():
    data = FakeProvider(today=TODAY).get_fundamentals("AAA")
    payload = to_payload(data)
    assert set(payload) == {f.name for f in fields(Fundamentals)}
    assert isinstance(payload["annual"], list) and isinstance(payload["quarterly"], list)
    assert payload["quarterly"][0] == {
        "period_end": "2026-09-30",
        "revenue": data.quarterly[0].revenue,
        "operating_income": data.quarterly[0].operating_income,
        "net_income": data.quarterly[0].net_income,
    }
    json.dumps(payload, allow_nan=False)  # nothing a JSON column cannot hold


def _broken_payloads() -> list:
    good = to_payload(FakeProvider(today=TODAY).get_fundamentals("AAA"))
    row = good["annual"][0]
    return [
        None,
        [],
        "{}",
        {},
        {k: v for k, v in good.items() if k != "psr"},  # written before a field existed
        {**good, "ev_to_ebitda": 12.0},  # written by a newer version
        {**good, "symbol": None},
        {**good, "per_trailing": "25.0"},
        {**good, "pbr": True},
        {**good, "name": 5},
        {**good, "annual": None},
        {**good, "annual": [{**row, "period_end": "31/12/2025"}]},
        {**good, "annual": [{**row, "period_end": 20251231}]},
        {**good, "annual": [{k: v for k, v in row.items() if k != "net_income"}]},
        {**good, "quarterly": [{**row, "revenue": "1e9"}]},
        {**good, "quarterly": ["2025-12-31"]},
    ]


@pytest.mark.parametrize("payload", _broken_payloads())
def test_unreadable_payload_is_none(payload):
    assert from_payload(payload) is None


# --- FundamentalsService ---------------------------------------------------------------------


class Clock:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t


class FailingProvider(FakeProvider):
    """`get_fundamentals` raises for the symbols in `fail`, like a scraper outage."""

    def __init__(self, fail: set[str], exc: type[Exception] = MarketDataError, **kw) -> None:
        super().__init__(**kw)
        self.fail = fail
        self.exc = exc

    def get_fundamentals(self, symbol):
        if symbol in self.fail:
            self.fundamentals_calls.append(symbol)
            raise self.exc(f"fundamentals down for {symbol}")
        return super().get_fundamentals(symbol)


@pytest.fixture
def clock() -> Clock:
    return Clock(NOW)


def make(db, provider, clock, **kw) -> FundamentalsService:
    return FundamentalsService(db, provider, now=clock, **kw)


def test_first_call_fetches_then_cache_then_refetch_after_ttl(db, clock):
    p = FakeProvider(today=TODAY)
    svc = make(db, p, clock)
    expected = FakeProvider(today=TODAY).get_fundamentals("AAA")

    view = svc.get("AAA")
    assert view == FundamentalsView("AAA", expected, NOW, False, None, True)
    assert p.fundamentals_calls == ["AAA"]

    for hours in (0, 1, 12, 23.99):
        clock.t = NOW + timedelta(hours=hours)
        assert svc.get("AAA") == view  # same figures, same fetch time, not stale
    assert p.fundamentals_calls == ["AAA"]  # inside the TTL: no request

    clock.t = NOW + timedelta(hours=25)
    again = svc.get("AAA")
    assert p.fundamentals_calls == ["AAA", "AAA"]
    assert again.fetched_at == clock.t and not again.stale and again.data == expected


def test_ttl_boundary_is_inclusive(db, clock):
    p = FakeProvider(today=TODAY)
    svc = make(db, p, clock, ttl=timedelta(hours=2))
    svc.get("AAA")
    clock.t = NOW + timedelta(hours=2) - timedelta(seconds=1)
    svc.get("AAA")
    assert p.fundamentals_calls == ["AAA"]
    clock.t = NOW + timedelta(hours=2)
    svc.get("AAA")
    assert p.fundamentals_calls == ["AAA", "AAA"]


def test_row_stores_payload_and_both_times(db, clock):
    p = FakeProvider(today=TODAY)
    make(db, p, clock).get("AAA")
    row = db.get(FundamentalsRow, "AAA")
    assert row.payload == to_payload(FakeProvider(today=TODAY).get_fundamentals("AAA"))
    assert row.fetched_at == NOW and row.attempted_at == NOW and row.error is None
    assert db.scalars(select(FundamentalsRow)).all() == [row]


def test_a_new_service_instance_reads_the_cache(db, clock):
    """The service is built per request; the table is the cache."""
    p = FakeProvider(today=TODAY)
    first = make(db, p, clock).get("AAA")
    clock.t = NOW + timedelta(hours=3)
    assert make(db, p, clock).get("AAA") == first
    assert p.fundamentals_calls == ["AAA"]


def test_failure_keeps_last_figures_marks_stale_and_holds_the_retry(db, clock):
    p = FailingProvider(fail=set(), today=TODAY)
    svc = make(db, p, clock)
    good = svc.get("AAA")

    failed_at = NOW + timedelta(hours=25)
    clock.t = failed_at
    p.fail = {"AAA"}
    view = svc.get("AAA")
    assert view == FundamentalsView("AAA", good.data, NOW, True, "fundamentals down for AAA", True)
    row = db.get(FundamentalsRow, "AAA")
    assert row.fetched_at == NOW and row.attempted_at == failed_at
    assert row.payload == to_payload(good.data)  # not replaced, not cleared
    assert p.fundamentals_calls == ["AAA", "AAA"]

    # Inside `error_ttl` nothing is asked, and the answer stays "stale, with the reason".
    for minutes in (0, 5, 30, 59):
        clock.t = failed_at + timedelta(minutes=minutes)
        assert svc.get("AAA") == view
    assert p.fundamentals_calls == ["AAA", "AAA"]

    # At `error_ttl` it is retried; still failing moves the attempt time, not the figures.
    clock.t = failed_at + DEFAULT_ERROR_TTL
    assert svc.get("AAA") == view
    assert p.fundamentals_calls == ["AAA", "AAA", "AAA"]
    assert db.get(FundamentalsRow, "AAA").attempted_at == clock.t
    clock.t = failed_at + DEFAULT_ERROR_TTL + timedelta(minutes=59)
    svc.get("AAA")
    assert p.fundamentals_calls == ["AAA", "AAA", "AAA"]

    # Recovery replaces the figures and clears the error.
    clock.t = failed_at + 2 * DEFAULT_ERROR_TTL
    p.fail = set()
    back = svc.get("AAA")
    assert p.fundamentals_calls == ["AAA", "AAA", "AAA", "AAA"]
    assert back == FundamentalsView("AAA", good.data, clock.t, False, None, True)
    assert db.get(FundamentalsRow, "AAA").error is None


def test_first_fetch_failure_has_no_figures_and_no_made_up_ones(db, clock):
    p = FailingProvider(fail={"AAA"}, today=TODAY)
    svc = make(db, p, clock)
    view = svc.get("AAA")
    assert view == FundamentalsView("AAA", None, None, True, "fundamentals down for AAA", True)
    row = db.get(FundamentalsRow, "AAA")
    assert row.payload is None and row.fetched_at is None and row.attempted_at == NOW

    svc.get("AAA")
    assert p.fundamentals_calls == ["AAA"]  # held back like any other failure
    clock.t = NOW + DEFAULT_ERROR_TTL
    p.fail = set()
    assert svc.get("AAA").data is not None
    assert p.fundamentals_calls == ["AAA", "AAA"]


def test_unknown_symbol_of_the_fake_is_an_error_view(db, clock):
    svc = make(db, FakeProvider(today=TODAY, unknown={"ZZZZ"}), clock)
    view = svc.get("ZZZZ")
    assert view.data is None and view.stale and view.supported
    assert "ZZZZ" in view.error


def test_any_exception_from_the_provider_is_contained(db, clock):
    p = FailingProvider(fail={"AAA"}, exc=RuntimeError, today=TODAY)
    views = make(db, p, clock).get_many(["AAA", "BBB"])
    assert views[0].error == "fundamentals down for AAA" and views[0].data is None
    assert views[1].error is None and views[1].data is not None


def test_long_error_message_fits_the_column(db, clock):
    class Chatty(FakeProvider):
        def get_fundamentals(self, symbol):
            raise MarketDataError("x" * 1000)

    view = make(db, Chatty(today=TODAY), clock).get("AAA")
    assert view.error == "x" * ERROR_MAX
    assert db.get(FundamentalsRow, "AAA").error == "x" * ERROR_MAX


def test_exception_without_a_message_still_reports_something(db, clock):
    class Silent(FakeProvider):
        def get_fundamentals(self, symbol):
            raise TimeoutError

    assert make(db, Silent(today=TODAY), clock).get("AAA").error == "TimeoutError"


@pytest.mark.parametrize("symbol", ["BTC-USD", "KRW-BTC", "KRW=X"])
def test_assets_without_statements_touch_neither_provider_nor_cache(db, clock, symbol):
    p = FakeProvider(today=TODAY)
    view = make(db, p, clock).get(symbol)
    assert view == FundamentalsView(symbol, None, None, False, None, False)
    assert p.fundamentals_calls == []
    assert db.scalars(select(FundamentalsRow)).all() == []


def test_fund_identified_by_the_provider_is_cached_as_unsupported(db, clock):
    """An ETF is only known to have no statements after a lookup; that answer is cached so
    it is not asked on every request."""
    p = FakeProvider(today=TODAY, fundamentals={"SPY": None})
    svc = make(db, p, clock)
    view = svc.get("SPY")
    assert view == FundamentalsView("SPY", None, NOW, False, None, False)
    row = db.get(FundamentalsRow, "SPY")
    assert row.payload is None and row.fetched_at == NOW and row.error is None

    clock.t = NOW + timedelta(hours=5)
    assert svc.get("SPY") == view
    assert p.fundamentals_calls == ["SPY"]
    clock.t = NOW + timedelta(hours=24)
    svc.get("SPY")
    assert p.fundamentals_calls == ["SPY", "SPY"]


def test_failed_refresh_of_a_fund_stays_unsupported_but_stale(db, clock):
    p = FailingProvider(fail=set(), today=TODAY, fundamentals={"SPY": None})
    svc = make(db, p, clock)
    svc.get("SPY")
    clock.t = NOW + timedelta(hours=25)
    p.fundamentals.pop("SPY")
    p.fail = {"SPY"}
    view = svc.get("SPY")
    assert view == FundamentalsView("SPY", None, NOW, True, "fundamentals down for SPY", False)


def test_figures_replaced_by_no_statements_clear_the_payload(db, clock):
    """A symbol the provider reclassifies as a fund must not keep showing company figures."""
    p = FakeProvider(today=TODAY)
    svc = make(db, p, clock)
    assert svc.get("AAA").supported
    clock.t = NOW + timedelta(hours=25)
    p.fundamentals["AAA"] = None
    view = svc.get("AAA")
    assert view == FundamentalsView("AAA", None, clock.t, False, None, False)
    assert db.get(FundamentalsRow, "AAA").payload is None


def test_get_many_keeps_order_dedupes_and_fetches_only_what_is_due(db, clock):
    p = FailingProvider(fail={"CCC"}, today=TODAY, fundamentals={"SPY": None})
    svc = make(db, p, clock)
    svc.get("BBB")  # already cached
    clock.t = NOW + timedelta(hours=1)

    views = svc.get_many(["CCC", "BTC-USD", "AAA", "BBB", "SPY", "AAA", "KRW-BTC"])
    assert [v.symbol for v in views] == ["CCC", "BTC-USD", "AAA", "BBB", "SPY", "KRW-BTC"]
    by = {v.symbol: v for v in views}
    assert by["CCC"].error and by["CCC"].stale and by["CCC"].data is None
    assert by["AAA"].data is not None and by["AAA"].fetched_at == clock.t
    assert by["BBB"].data is not None and by["BBB"].fetched_at == NOW  # from the cache
    assert not by["SPY"].supported and not by["BTC-USD"].supported
    assert not by["KRW-BTC"].supported
    # Coins never reach the provider, BBB was fresh, the duplicate is asked once. The calls
    # run on a thread pool, so only their multiset is fixed.
    assert sorted(p.fundamentals_calls) == ["AAA", "BBB", "CCC", "SPY"]

    assert svc.get_many([]) == []
    assert sorted(p.fundamentals_calls) == ["AAA", "BBB", "CCC", "SPY"]


def test_get_many_fetches_more_symbols_than_workers(db, clock):
    p = FakeProvider(today=TODAY)
    views = make(db, p, clock).get_many(SYNTHETIC)
    assert [v.symbol for v in views] == SYNTHETIC
    assert all(v.data is not None and v.data.symbol == v.symbol for v in views)
    assert sorted(p.fundamentals_calls) == SYNTHETIC
    assert len(db.scalars(select(FundamentalsRow)).all()) == len(SYNTHETIC)


def test_no_database_write_before_every_request_is_back(db, clock):
    """Network first, then one transaction: while any request is still running, none of
    this batch's rows exist yet."""
    seen: list[int] = []

    class Watching(FakeProvider):
        def get_fundamentals(self, symbol):
            seen.append(len(stored))
            return super().get_fundamentals(symbol)

    stored: list[str] = []
    svc = make(db, Watching(today=TODAY), clock)
    original = svc._store

    def store(symbol, result, now):
        stored.append(symbol)
        original(symbol, result, now)

    svc._store = store
    svc.get_many(["AAA", "BBB", "CCC"])
    assert seen == [0, 0, 0] and stored == ["AAA", "BBB", "CCC"]


def test_payload_from_an_older_schema_is_a_cache_miss(db, clock):
    db.add(
        FundamentalsRow(
            symbol="AAA",
            fetched_at=NOW - timedelta(hours=1),  # fresh by the clock
            attempted_at=NOW - timedelta(hours=1),
            payload={"symbol": "AAA", "per": 25.0},
            error=None,
        )
    )
    db.commit()
    p = FakeProvider(today=TODAY)
    view = make(db, p, clock).get("AAA")
    assert p.fundamentals_calls == ["AAA"]  # refetched although inside the TTL
    assert view.data == FakeProvider(today=TODAY).get_fundamentals("AAA")
    assert view.fetched_at == NOW and not view.stale
    assert db.get(FundamentalsRow, "AAA").payload == to_payload(view.data)


def test_unreadable_payload_and_a_failed_refetch_shows_nothing_rather_than_half(db, clock):
    db.add(
        FundamentalsRow(
            symbol="AAA",
            fetched_at=NOW - timedelta(hours=1),
            attempted_at=NOW - timedelta(hours=1),
            payload={"symbol": "AAA", "per": 25.0},
            error=None,
        )
    )
    db.commit()
    p = FailingProvider(fail={"AAA"}, today=TODAY)
    svc = make(db, p, clock)
    view = svc.get("AAA")
    assert view == FundamentalsView("AAA", None, None, True, "fundamentals down for AAA", True)
    svc.get("AAA")
    assert p.fundamentals_calls == ["AAA"]  # the failure holds the retry back as usual


def test_service_with_the_real_parser_end_to_end(db, clock, monkeypatch):
    """YFinanceProvider (patched Ticker) -> service -> row -> view."""
    asked = patch_ticker(monkeypatch, INFO)
    svc = make(db, yfp.YFinanceProvider(), clock)
    view = svc.get("AAA")
    assert view.data == parse() and view.fetched_at == NOW and not view.stale
    assert svc.get("AAA") == view
    assert asked.count("AAA.info") == 1
    assert svc.get("BTC-USD").supported is False
    assert asked.count("BTC-USD") == 0


# --- FundamentalsService: requests that arrive together --------------------------------------


class SlowProvider(FailingProvider):
    """A lookup takes a moment, like the network, so requests that arrive together overlap."""

    def __init__(self, delay: float = 0.05, **kw) -> None:
        super().__init__(**kw)
        self.delay = delay

    def get_fundamentals(self, symbol):
        time.sleep(self.delay)
        return super().get_fundamentals(symbol)


@pytest.fixture
def session_factory(tmp_path):
    """A database file with one connection per session, as in the running app, where every
    request thread has its own session. (The `db` fixture is one shared in-memory
    connection and cannot stand in for that.)"""
    engine = make_engine(f"sqlite:///{tmp_path / 'fundamentals.db'}")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


def run_together(n: int, session_factory, provider, symbols, now: datetime = NOW) -> list:
    """`get_many(symbols)` from n threads released at the same moment, each with its own
    session and its own service, like n requests. Returns the n results."""
    barrier = threading.Barrier(n)
    results: list = [None] * n
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            with session_factory() as db:
                service = FundamentalsService(db, provider, now=lambda: now)
                barrier.wait(timeout=10)
                results[i] = service.get_many(symbols)
        except BaseException as exc:  # reported by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == [] and not any(t.is_alive() for t in threads)
    return results


def test_concurrent_requests_ask_the_provider_once_per_symbol(session_factory):
    """Ten requests hit an empty cache at once (the home page is polled, and a visitor can
    fire a burst): one of them fetches, the others wait and read what it stored."""
    p = SlowProvider(fail=set(), today=TODAY)
    results = run_together(10, session_factory, p, ["AAA", "BBB", "CCC"])
    assert Counter(p.fundamentals_calls) == {"AAA": 1, "BBB": 1, "CCC": 1}
    assert all(r == results[0] for r in results)
    assert [v.symbol for v in results[0]] == ["AAA", "BBB", "CCC"]
    assert all(v.data is not None and not v.stale and v.fetched_at == NOW for v in results[0])


def test_concurrent_requests_try_a_failing_symbol_once_per_error_ttl(session_factory):
    p = SlowProvider(fail={"AAA"}, today=TODAY)
    results = run_together(10, session_factory, p, ["AAA", "BBB"])
    assert Counter(p.fundamentals_calls) == {"AAA": 1, "BBB": 1}
    for aaa, bbb in results:
        assert aaa == FundamentalsView("AAA", None, None, True, "fundamentals down for AAA", True)
        assert bbb.data is not None and not bbb.stale

    # A second burst inside `error_ttl` asks nothing at all.
    later = NOW + DEFAULT_ERROR_TTL - timedelta(seconds=1)
    assert run_together(10, session_factory, p, ["AAA", "BBB"], now=later) == results
    assert Counter(p.fundamentals_calls) == {"AAA": 1, "BBB": 1}

    # A burst after it retries the failed symbol once, not ten times.
    run_together(10, session_factory, p, ["AAA", "BBB"], now=NOW + DEFAULT_ERROR_TTL)
    assert Counter(p.fundamentals_calls) == {"AAA": 2, "BBB": 1}


def test_concurrent_requests_for_different_symbols_each_get_theirs(session_factory):
    p = SlowProvider(fail=set(), today=TODAY)
    barrier = threading.Barrier(6)
    got: dict[str, FundamentalsView] = {}

    def worker(symbol: str) -> None:
        with session_factory() as db:
            barrier.wait(timeout=10)
            got[symbol] = FundamentalsService(db, p, now=lambda: NOW).get(symbol)

    threads = [threading.Thread(target=worker, args=(s,)) for s in SYNTHETIC[:6]]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(got) == SYNTHETIC[:6]
    assert all(v.data is not None and v.data.symbol == s for s, v in got.items())
    assert Counter(p.fundamentals_calls) == dict.fromkeys(SYNTHETIC[:6], 1)


def test_cache_hit_does_not_wait_for_a_running_refresh(session_factory):
    """Only a request that has something to fetch takes the refresh lock. With the lock
    held (another request is on the network), a cached symbol is still answered at once."""
    p = FakeProvider(today=TODAY)
    with session_factory() as db:
        first = FundamentalsService(db, p, now=lambda: NOW).get("AAA")
    done: list[FundamentalsView] = []

    def reader() -> None:
        with session_factory() as db:
            done.append(FundamentalsService(db, p, now=lambda: NOW).get("AAA"))

    assert fundamentals_service._REFRESH_LOCK.acquire(timeout=5)
    try:
        t = threading.Thread(target=reader)
        t.start()
        t.join(timeout=10)
        assert not t.is_alive()
    finally:
        fundamentals_service._REFRESH_LOCK.release()
    assert done == [first] and p.fundamentals_calls == ["AAA"]


def test_refresh_lock_is_released_when_the_write_fails(db, clock):
    svc = make(db, FakeProvider(today=TODAY), clock)

    def broken(symbol, result, now):
        raise RuntimeError("disk full")

    svc._store = broken
    with pytest.raises(RuntimeError, match="disk full"):
        svc.get("AAA")
    assert fundamentals_service._REFRESH_LOCK.acquire(blocking=False)
    fundamentals_service._REFRESH_LOCK.release()
