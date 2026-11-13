"""Deterministic offline provider for tests, CI and demos without network access."""

import hashlib
import math
import random
from datetime import date, datetime, timedelta

from app.data.assets import CRYPTO_ASSETS, FX_USDKRW, has_fundamentals, trades_every_day
from app.data.provider import (
    Bar,
    CorporateEvent,
    Fundamentals,
    MarketDataError,
    Quote,
    StatementRow,
    UpcomingEvent,
)

_BASE_PRICES = {
    "BTC-USD": 60000.0,
    "ETH-USD": 3000.0,
    "XRP-USD": 0.6,
    "SOL-USD": 150.0,
    FX_USDKRW: 1350.0,
    # Upbit KRW markets, roughly USD price x 1350 plus a small premium.
    "KRW-BTC": 82_000_000.0,
    "KRW-ETH": 4_100_000.0,
    "KRW-XRP": 820.0,
    "KRW-SOL": 205_000.0,
}
_EPOCH = date(2015, 1, 1)
_QUARTER = 91  # days between synthetic earnings releases / ex-dividend dates
_LOSS_EVERY = 4  # one synthetic company in four (by seed) reports losses
_SECTORS = (
    ("Technology", "Software - Application"),
    ("Healthcare", "Drug Manufacturers - General"),
    ("Consumer Cyclical", "Specialty Retail"),
    ("Industrials", "Specialty Industrial Machinery"),
    ("Financial Services", "Asset Management"),
    ("Energy", "Oil & Gas Integrated"),
)


class FakeProvider:
    """Geometric random walk seeded per symbol, so the same symbol and day give the same bar.

    Symbols listed in `unknown` behave like tickers the provider has never heard of.
    `upcoming` fixes the calendar of a symbol; other stocks get a deterministic quarterly one.
    `fundamentals` fixes the company figures of a symbol (None = "no statements"); other
    stocks get deterministic synthetic ones, some of them loss-making.
    """

    def __init__(
        self,
        today: date | None = None,
        unknown: set[str] | None = None,
        actions: dict[str, list[CorporateEvent]] | None = None,
        upcoming: dict[str, list[UpcomingEvent]] | None = None,
        fundamentals: dict[str, Fundamentals | None] | None = None,
    ) -> None:
        self.today = today or date.today()
        self.unknown = unknown or set()
        self.actions = actions or {}
        self.upcoming = upcoming or {}
        self.fundamentals = fundamentals or {}
        self.history_calls: list[tuple[str, date, date]] = []
        self.event_calls: list[str] = []
        self.fundamentals_calls: list[str] = []

    def get_history(self, symbol: str, start: date, end: date) -> list[Bar]:
        self.history_calls.append((symbol, start, end))
        if symbol in self.unknown:
            return []
        end = min(end, self.today)
        return [b for b in self._series(symbol, end) if b.date >= start]

    def get_quote(self, symbol: str) -> Quote | None:
        if symbol in self.unknown:
            return None
        last = self._series(symbol, self.today)[-1]
        return Quote(
            symbol=symbol, price=last.close, as_of=datetime.combine(last.date, datetime.min.time())
        )

    def get_name(self, symbol: str) -> str | None:
        return None if symbol in self.unknown else f"{symbol} Inc."

    def get_actions(self, symbol: str) -> list[CorporateEvent]:
        return list(self.actions.get(symbol, []))

    def get_upcoming_events(self, symbol: str) -> list[UpcomingEvent]:
        self.event_calls.append(symbol)
        if symbol in self.upcoming:
            return list(self.upcoming[symbol])
        if symbol in self.unknown or trades_every_day(symbol) or symbol.startswith("KRW-"):
            return []
        seed = int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16)
        estimated = seed % 2 == 0
        # Earnings every 91 days from a symbol-specific phase; the next two after `today`.
        earnings = _next_cycle(_EPOCH + timedelta(days=seed % _QUARTER), self.today, 2)
        out = [UpcomingEvent(symbol, "earnings", d, estimated) for d in earnings]
        if seed % 3 != 0:
            ex_date = _next_cycle(_EPOCH + timedelta(days=(seed // 7) % _QUARTER), self.today, 1)
            out += [UpcomingEvent(symbol, "ex_dividend", d) for d in ex_date]
        return sorted(out, key=lambda e: (e.date, e.kind))

    def get_fundamentals(self, symbol: str) -> Fundamentals | None:
        """Synthetic but internally consistent figures: PER = price / EPS, PBR = price /
        book value per share, PSR = market cap / last-4-quarter revenue, the operating
        margin is the newest quarter's and the net margin the last four quarters', like the
        real provider. A quarter keeps its numbers as `today` moves; the multiples follow
        the fake price. One symbol in four (by seed) loses money: negative net income,
        `per_trailing` None. Coins, Upbit markets and FX are None; `unknown` symbols raise.
        """
        self.fundamentals_calls.append(symbol)
        if symbol in self.fundamentals:
            return self.fundamentals[symbol]
        if not has_fundamentals(symbol):
            return None
        if symbol in self.unknown:
            raise MarketDataError(f"no fundamentals for {symbol}: unknown symbol")
        seed = _seed(symbol)
        rng = random.Random(seed ^ 0x5F3759DF)  # not the price walk's stream
        loss = seed % _LOSS_EVERY == 0
        price = self._series(symbol, self.today)[-1].close

        quarters = _quarter_ends(self.today, 20)  # newest first, covers four fiscal years
        rows = [_fake_quarter(symbol, q, loss) for q in quarters]
        ttm = rows[:4]
        revenue_ttm = sum(r.revenue for r in ttm)
        net_ttm = sum(r.net_income for r in ttm)
        annual = []
        for year in range(self.today.year - 1, self.today.year - 5, -1):
            year_rows = [r for r in rows if r.period_end.year == year]
            if len(year_rows) == 4:
                annual.append(
                    StatementRow(
                        date(year, 12, 31),
                        sum(r.revenue for r in year_rows),
                        sum(r.operating_income for r in year_rows),
                        sum(r.net_income for r in year_rows),
                    )
                )

        shares = max(1.0, float(round(rng.uniform(1.5, 9.0) * revenue_ttm / price)))
        market_cap = price * shares
        eps = net_ttm / shares
        eps_forward = eps * (0.6 if loss else 1.0 + rng.uniform(0.02, 0.25))
        book_value = price / rng.uniform(0.8, 12.0)
        pays_dividend = not loss and seed % 3 != 0
        year_ago = rows[4]
        sector, industry = _SECTORS[seed % len(_SECTORS)]
        return Fundamentals(
            symbol=symbol,
            currency="USD",
            name=f"{symbol} Inc.",
            sector=sector,
            industry=industry,
            summary=f"{symbol} Inc. is a synthetic company used for offline demos and tests.",
            market_cap=market_cap,
            per_trailing=round(price / eps, 4) if eps > 0 else None,
            per_forward=round(price / eps_forward, 4) if eps_forward > 0 else None,
            pbr=round(price / book_value, 4),
            psr=round(market_cap / revenue_ttm, 4),
            eps_trailing=round(eps, 6),
            eps_forward=round(eps_forward, 6),
            book_value_per_share=round(book_value, 4),
            dividend_yield_pct=round(rng.uniform(0.3, 4.0), 2) if pays_dividend else 0.0,
            operating_margin_pct=round(rows[0].operating_income / rows[0].revenue * 100, 2),
            net_margin_pct=round(net_ttm / revenue_ttm * 100, 2),
            roe_pct=round(net_ttm / (book_value * shares) * 100, 2),
            revenue_growth_pct=round((rows[0].revenue / year_ago.revenue - 1) * 100, 2),
            earnings_growth_pct=(
                round((rows[0].net_income / year_ago.net_income - 1) * 100, 2)
                if year_ago.net_income > 0
                else None
            ),
            debt_to_equity_pct=round(rng.uniform(0.0, 250.0), 2),
            annual=tuple(annual[:4]),
            quarterly=tuple(rows[:5]),
        )

    def _series(self, symbol: str, end: date) -> list[Bar]:
        seed = int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        crypto = symbol in CRYPTO_ASSETS or symbol.startswith("KRW-")
        vol = 0.035 if crypto else 0.015
        drift = 0.0006 if crypto else 0.0003
        price = _BASE_PRICES.get(symbol, 50.0 + seed % 300)
        every_day = trades_every_day(symbol) or symbol == FX_USDKRW

        bars: list[Bar] = []
        d = _EPOCH
        while d <= end:
            ret = rng.gauss(drift, vol)
            if every_day or d.weekday() < 5:
                open_ = price
                price = price * math.exp(ret)
                high = max(open_, price) * (1 + abs(rng.gauss(0, vol / 3)))
                low = min(open_, price) * (1 - abs(rng.gauss(0, vol / 3)))
                volume = float(rng.randint(1_000_000, 50_000_000))
                bars.append(Bar(d, open_, high, low, price, price, volume))
            d += timedelta(days=1)
        return bars


def _seed(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)


def _quarter_ends(before: date, n: int) -> list[date]:
    """The n most recent calendar quarter ends strictly before `before`, newest first."""
    year, month = before.year, (before.month - 1) // 3 * 3  # 0 = December of last year
    out: list[date] = []
    while len(out) < n:
        if month == 0:
            year, month = year - 1, 12
        out.append(date(year, month, 31 if month in (3, 12) else 30))
        month -= 3
    return out


def _fake_quarter(symbol: str, period_end: date, loss: bool) -> StatementRow:
    """One synthetic quarter, a function of the symbol and the quarter only: revenue grows
    at a symbol-specific rate from 2015 with a little noise, margins wobble around a
    symbol-specific level (negative for a loss-making company). Whole units."""
    base = random.Random(_seed(symbol) ^ 0x2545F491)
    revenue_0 = base.uniform(2e8, 2e10)
    growth = base.uniform(0.0, 0.04)  # per quarter
    margin = base.uniform(-0.30, -0.03) if loss else base.uniform(0.05, 0.35)
    k = (period_end.year - _EPOCH.year) * 4 + (period_end.month - 1) // 3
    noise = random.Random(_seed(f"{symbol}|{period_end.isoformat()}"))
    revenue = float(round(revenue_0 * (1 + growth) ** k * (1 + noise.uniform(-0.04, 0.04))))
    operating = float(round(revenue * (margin + noise.uniform(-0.02, 0.02))))
    # Interest widens a loss; tax takes a fifth of a profit.
    net = float(round(operating * 1.05 if operating < 0 else operating * 0.8))
    return StatementRow(period_end, revenue, operating, net)


def _next_cycle(first: date, after: date, n: int) -> list[date]:
    """The first n dates of the 91-day cycle starting at `first` that fall after `after`."""
    periods = max(0, (after - first).days // _QUARTER + 1)
    return [first + timedelta(days=(periods + i) * _QUARTER) for i in range(n)]
