"""Read-through cache of daily bars and quotes in front of a MarketDataProvider."""

import threading
import time
from bisect import bisect_right
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.data.assets import FX_USDKRW
from app.data.provider import Bar, MarketDataProvider, Quote
from app.db.models import PriceBar, SymbolSync

# How long cached bars count as fresh before the most recent days are re-fetched.
# The latest bar may be an in-progress session, so it is always overwritten on refresh.
HISTORY_TTL = timedelta(minutes=15)
QUOTE_TTL_SECONDS = 60.0


class SymbolNotFoundError(LookupError):
    pass


class QuoteCache:
    """Process-wide in-memory quote cache shared across requests."""

    def __init__(
        self, ttl_seconds: float = QUOTE_TTL_SECONDS, clock: Callable[[], float] = time.monotonic
    ):
        self.ttl = ttl_seconds
        self.clock = clock
        self._items: dict[str, tuple[float, Quote]] = {}
        self._lock = threading.Lock()

    def get(self, symbol: str) -> Quote | None:
        with self._lock:
            item = self._items.get(symbol)
        if item is None or self.clock() - item[0] > self.ttl:
            return None
        return item[1]

    def put(self, quote: Quote) -> None:
        with self._lock:
            self._items[quote.symbol] = (self.clock(), quote)


class MarketDataService:
    def __init__(
        self,
        db: Session,
        provider: MarketDataProvider,
        quote_cache: QuoteCache,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.db = db
        self.provider = provider
        self.quote_cache = quote_cache
        self.now = now

    def get_history(self, symbol: str, start: date, end: date | None = None) -> list[PriceBar]:
        today = self.now().date()
        end = min(end or today, today)
        self._sync(symbol, start, today)

        rows = self.db.scalars(
            select(PriceBar)
            .where(PriceBar.symbol == symbol, PriceBar.date >= start, PriceBar.date <= end)
            .order_by(PriceBar.date)
        ).all()
        if not rows and not self._has_any_bars(symbol):
            raise SymbolNotFoundError(symbol)
        return list(rows)

    def get_quote(self, symbol: str) -> Quote:
        cached = self.quote_cache.get(symbol)
        if cached is not None:
            return cached
        quote = self.provider.get_quote(symbol)
        if quote is None:
            raise SymbolNotFoundError(symbol)
        self.quote_cache.put(quote)
        return quote

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Fetch several quotes concurrently; each provider call is a slow HTTP round trip."""
        with ThreadPoolExecutor(max_workers=8) as pool:
            return dict(zip(symbols, pool.map(self.get_quote, symbols), strict=True))

    def usd_krw(self) -> Quote:
        return self.get_quote(FX_USDKRW)

    def usd_krw_lookup(self, start: date) -> Callable[[date], Decimal]:
        """USD/KRW on any date since `start`, using the last known rate for weekends/holidays."""
        bars = self.get_history(FX_USDKRW, start - timedelta(days=10))
        dates = [b.date for b in bars]
        rates = [Decimal(str(b.close)) for b in bars]
        fallback = Decimal(str(self.usd_krw().price))

        def lookup(d: date) -> Decimal:
            i = bisect_right(dates, d)
            if i == 0:
                return rates[0] if rates else fallback
            return rates[i - 1]

        return lookup

    def _sync(self, symbol: str, start: date, today: date) -> None:
        """Fetch any missing bars, then write them in one short transaction.

        All network calls happen before the first write, so the SQLite write lock is never
        held while waiting on the provider.
        """
        sync = self.db.get(SymbolSync, symbol)
        now = self.now()

        bars: list[Bar] = []
        fetched_from = start if sync is None else min(start, sync.fetched_from)
        if sync is None:
            bars = self.provider.get_history(symbol, start, today)
            # Nothing came back (unknown symbol or a flaky upstream): record nothing so the
            # next request retries instead of trusting an empty cache.
            if not bars:
                return
        else:
            if start < sync.fetched_from:
                end = sync.fetched_from - timedelta(days=1)
                bars += self.provider.get_history(symbol, start, end)
            stale = now - sync.synced_at > HISTORY_TTL
            if stale:
                last = self._last_bar_date(symbol) or sync.fetched_from
                bars += self.provider.get_history(symbol, last, today)
            if not bars and not stale and start >= sync.fetched_from:
                return

        self._store(symbol, bars)
        # Upsert, not insert: concurrent first requests for the same symbol must not collide.
        stmt = sqlite_insert(SymbolSync).values(
            symbol=symbol, fetched_from=fetched_from, synced_at=now
        )
        self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=["symbol"],
                set_={
                    "fetched_from": func.min(SymbolSync.fetched_from, stmt.excluded.fetched_from),
                    "synced_at": stmt.excluded.synced_at,
                },
            )
        )
        self.db.commit()
        if sync is not None:
            self.db.expire(sync)  # reload the upserted row on next access

    def _store(self, symbol: str, bars: list[Bar]) -> None:
        # Chunked to stay under SQLite's bound-parameter limit.
        for i in range(0, len(bars), 500):
            self._upsert(symbol, bars[i : i + 500])

    def _upsert(self, symbol: str, bars: list[Bar]) -> None:
        values = [
            {
                "symbol": symbol,
                "date": b.date,
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "adj_close": b.adj_close,
                "volume": b.volume,
            }
            for b in bars
        ]
        stmt = sqlite_insert(PriceBar).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "date"],
            set_={
                k: stmt.excluded[k] for k in ("open", "high", "low", "close", "adj_close", "volume")
            },
        )
        self.db.execute(stmt)

    def _last_bar_date(self, symbol: str) -> date | None:
        return self.db.scalar(
            select(PriceBar.date)
            .where(PriceBar.symbol == symbol)
            .order_by(PriceBar.date.desc())
            .limit(1)
        )

    def _has_any_bars(self, symbol: str) -> bool:
        return self._last_bar_date(symbol) is not None
