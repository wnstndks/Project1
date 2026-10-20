"""Read-through cache of daily bars and quotes in front of a MarketDataProvider."""

import threading
import time
from bisect import bisect_right
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, inspect, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.data.assets import FX_USDKRW
from app.data.calendar import bar_is_final
from app.data.provider import Bar, MarketDataProvider, Quote
from app.db.models import PriceBar, SymbolSync

# How long cached bars count as fresh before the most recent days are re-fetched.
# The latest bar may be an in-progress session, so it is always overwritten on refresh.
HISTORY_TTL = timedelta(minutes=15)
# Refreshes re-download this many days before the newest cached bar. Comparing that overlap
# with the cache reveals a provider-side re-adjustment (after a split or dividend Yahoo
# rescales the whole past series), which would otherwise leave a fake jump at the seam.
OVERLAP = timedelta(days=10)
RESCALE_TOLERANCE = 1e-4
QUOTE_TTL_SECONDS = 60.0


def drop_cached_bars(db: Session, symbol: str) -> None:
    """Forget a symbol's cached bars so the next request downloads its full history.
    Left for the caller to commit."""
    db.execute(delete(PriceBar).where(PriceBar.symbol == symbol))
    db.execute(delete(SymbolSync).where(SymbolSync.symbol == symbol))


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
        utc_now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.db = db
        self.provider = provider
        self.quote_cache = quote_cache
        self.now = now
        self.utc_now = utc_now

    def get_history(
        self, symbol: str, start: date, end: date | None = None, final_only: bool = False
    ) -> list[PriceBar]:
        """Daily bars from the cache, syncing missing ones first.

        `final_only` drops a bar whose session is still open (today's partial stock bar, the
        current UTC day for coins). Models must use it: a partial bar's volume and range look
        nothing like the completed bars they were trained on.
        """
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
        rows = list(rows)
        if final_only:
            now = self.utc_now()
            while rows and not bar_is_final(symbol, rows[-1].date, now):
                rows.pop()
        return rows

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

    def _sync(self, symbol: str, start: date, today: date, retry: bool = True) -> None:
        """Fetch any missing bars, then write them in one short transaction.

        All network calls happen before the first write, so the SQLite write lock is never
        held while waiting on the provider.
        """
        sync = self.db.get(SymbolSync, symbol)
        now = self.now()

        bars: list[Bar] = []
        replace = False
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
                fresh = self.provider.get_history(symbol, last - OVERLAP, today)
                full = None
                if self._rescaled(symbol, fresh, before=last):
                    # The provider re-adjusted its history: every cached bar is on the old
                    # scale, so replace the whole series rather than patching the end.
                    full = self.provider.get_history(symbol, fetched_from, today)
                if full is not None and self._covers_cache(symbol, full):
                    bars, replace = full, True
                else:
                    bars += fresh
            if not bars and not stale and start >= sync.fetched_from:
                return
            # The cache may have been dropped while we were fetching (a new split was
            # recorded). Writing a partial window would then claim the full range, so
            # download everything instead.
            if (
                not replace
                and self.db.scalar(select(SymbolSync.symbol).where(SymbolSync.symbol == symbol))
                is None
            ):
                if retry:
                    if inspect(sync).persistent:
                        self.db.expunge(sync)  # so the retry reads the row's absence
                    self._sync(symbol, start, today, retry=False)
                return

        if replace:
            self.db.execute(delete(PriceBar).where(PriceBar.symbol == symbol))
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

    def _rescaled(self, symbol: str, fresh: list[Bar], before: date) -> bool:
        """True if the provider re-scaled its past bars (ignoring the last cached bar, which
        may have been an in-progress session).

        A re-adjustment moves every bar before the ex-date by the same factor, so the changed
        bars are a run at the start of the overlap (all of it if the ex-date is later). Changes
        anywhere else are corrections to single bars, simply overwritten by the refresh. A
        one-bar run at the very start is ambiguous and is treated as a re-adjustment: a full
        refetch is merely wasted if it was not, while a missed one leaves a permanent seam.
        """
        overlap = {b.date: b for b in fresh if b.date < before}
        if not overlap:
            return False
        cached = list(
            self.db.scalars(
                select(PriceBar)
                .where(PriceBar.symbol == symbol, PriceBar.date.in_(list(overlap)))
                .order_by(PriceBar.date)
            )
        )
        for field in ("close", "adj_close"):
            ratios = [
                getattr(overlap[row.date], field) / getattr(row, field)
                for row in cached
                if getattr(row, field)
            ]
            changed = [abs(r - 1) > RESCALE_TOLERANCE for r in ratios]
            run = next((i for i, c in enumerate(changed) if not c), len(changed))
            if run == 0 or any(changed[run:]):
                continue
            head = ratios[:run]
            if max(head) / min(head) - 1 <= RESCALE_TOLERANCE * 10:
                return True
        return False

    def _covers_cache(self, symbol: str, bars: list[Bar]) -> bool:
        """A full refetch may replace the cache only if it reaches back as far (a truncated
        response must not wipe older history)."""
        oldest = self.db.scalar(select(func.min(PriceBar.date)).where(PriceBar.symbol == symbol))
        return bool(bars) and (oldest is None or bars[0].date <= oldest + timedelta(days=7))

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
