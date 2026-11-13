"""Published company figures of a stock (DECISIONS.md D-036).

Facts with a source and a date, not a signal: no field here says whether a figure is high or
low. The figures are market data, so they are plain floats like the price schemas (`Num` is
for ledger Decimals). Units are fixed by the provider layer: every `*_pct` field is a percent
on the 0-100 scale, money is in whole units of `currency` (the statement currency), PER / PBR
/ PSR are plain multiples.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel

# Why a figure is missing, as a code. The wording lives in the frontend
# (`src/lib/fundamentals.ts`), like the forecast verdict reasons.
#   per_negative_earnings            trailing EPS is zero or negative, so there is no PER
#   per_forward_negative_earnings    the estimated EPS is zero or negative, so no forward PER
#   operating_loss_net_profit        there is a PER (12-month net income is positive) while the
#                                    latest quarter's operating income is negative: the PER
#                                    alone reads like a company that earns from its business
#   operating_loss_net_profit_annual the same against the latest fiscal year, used only when
#                                    the latest quarter's operating income is not reported
#   operating_income_not_reported    no operating margin, and none of the statement rows has
#                                    an operating income line (banks and insurers report none)
#   zero_revenue_quarter             no operating margin because the newest quarter's revenue
#                                    is zero
#   net_income_above_operating_income        over the newest four quarters net income is larger
#                                            than a positive operating income, so the net
#                                            margin is not "what the business kept of its sales"
#   net_income_above_operating_income_annual the same for the newest fiscal year, used only
#                                            when four consecutive full quarters are not there
#   currency_mismatch                statements are not in USD (an ADR) and the figures that
#                                    mix the two currencies were left out by the provider
# A note only states what the figures themselves show; it never says why or what to do.
NoteCode = Literal[
    "per_negative_earnings",
    "per_forward_negative_earnings",
    "operating_loss_net_profit",
    "operating_loss_net_profit_annual",
    "operating_income_not_reported",
    "zero_revenue_quarter",
    "net_income_above_operating_income",
    "net_income_above_operating_income_annual",
    "currency_mismatch",
]

SOURCE_KO = "Yahoo Finance"
# `AM_MARKET_PROVIDER=fake`: the numbers are synthetic and the screen has to say so.
SOURCE_FAKE_KO = "합성 데이터(오프라인 데모용)"
DISCLAIMER_KO = (
    "공개된 재무 숫자이며 투자 조언이 아닙니다. "
    "이 숫자만으로 매수·매도를 판단할 수 없습니다. 업종마다 기준이 다릅니다."
)


class StatementRowOut(BaseModel):
    """One period of the income statement, in whole units of the statement currency."""

    period_end: date
    revenue: float | None
    operating_income: float | None
    net_income: float | None


class FundamentalsOut(BaseModel):
    symbol: str
    # False for assets without financial statements (coins, ETFs): every figure is null.
    supported: bool
    # UTC date of the last successful fetch; null when nothing was ever fetched.
    as_of: date | None
    # The figures are older than the cache TTL or the last refresh failed (`error` says why).
    stale: bool
    error: str | None
    currency: str | None  # statement currency, e.g. "USD"; an ADR reports in another one
    name: str | None
    sector: str | None
    industry: str | None
    summary: str | None  # business description, original English text

    market_cap: float | None
    per_trailing: float | None  # price / last-12-month EPS; null when that EPS is <= 0
    per_forward: float | None  # price / analysts' estimated EPS (an estimate)
    pbr: float | None
    psr: float | None
    eps_trailing: float | None
    eps_forward: float | None
    book_value_per_share: float | None
    dividend_yield_pct: float | None
    operating_margin_pct: float | None  # most recent quarter
    net_margin_pct: float | None  # last 12 months
    roe_pct: float | None
    revenue_growth_pct: float | None  # newest quarter against the same quarter a year before
    earnings_growth_pct: float | None  # same comparison
    debt_to_equity_pct: float | None

    annual: list[StatementRowOut]  # newest first, at most 4
    quarterly: list[StatementRowOut]  # newest first, at most 5
    notes: list[NoteCode]
    source_ko: str
    disclaimer_ko: str


class HeldFundamentalsOut(BaseModel):
    """Figures of every held stock, in the order of the holdings list (largest value first).
    Held ETFs are included with `supported=false`; coins are not listed."""

    items: list[FundamentalsOut]
    # The oldest `as_of` among the items that have figures: all of them are at least this fresh.
    as_of: date | None
    source_ko: str
    disclaimer_ko: str
