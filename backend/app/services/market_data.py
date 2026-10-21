"""Read-through cache of daily bars and quotes in front of a MarketDataProvider.

Finality: a cached bar is final only if it was *fetched* after its session closed, not
merely because its date has passed. `symbol_syncs.synced_at` (naive UTC) is the time the
cache's tail was last downloaded; every refresh re-downloads from OVERLAP before the newest
bar, so a bar that was still in progress at one sync is either rewritten by the next one or,
if the provider no longer returns it, deleted. `get_history(final_only=True)` therefore
returns only bars final at `synced_at`, and refreshes first when a bar cached in progress
should have closed by now.
"""

import logging
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
from app.data.calendar import bar_is_final, expected_dates
from app.data.provider import Bar, DataUnavailableError, MarketDataProvider, Quote
from app.data.quality import FX_MAX_GAP_DAYS, validate_bars
from app.db.models import PriceBar, SymbolSync

log = logging.getLogger(__name__)

# How long cached bars count as fresh before the most recent days are re-fetched.
# The latest bar may be an in-progress session, so it is always overwritten on refresh.
HISTORY_TTL = timedelta(minutes=15)
# Refreshes re-download this many days before the newest cached bar. Comparing that overlap
# with the cache reveals a provider-side re-adjustment (after a split or dividend Yahoo
# rescales the whole past series), which would otherwise leave a fake jump at the seam.
OVERLAP = timedelta(days=10)
RESCALE_TOLERANCE = 1e-4
QUOTE_TTL_SECONDS = 60.0
# A synced_at further in the future than this is not trusted (clock skew, or a value written
# in local time before synced_at became UTC).
CLOCK_SKEW = timedelta(minutes=5)


def _utc(naive: datetime) -> datetime:
    return naive.replace(tzinfo=UTC)


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
        utc_now: Callable[[], datetime] | None = None,
    ) -> None:
        """`now` is the local wall clock (for "today"); `utc_now` defaults to the same instant
        in UTC and drives cache freshness and finality."""
        self.db = db
        self.provider = provider
        self.quote_cache = quote_cache
        self.now = now
        self.utc_now = utc_now or (lambda: now().astimezone(UTC))

    def get_history(
        self,
        symbol: str,
        start: date,
        end: date | None = None,
        final_only: bool = False,
        max_age: timedelta | None = None,
    ) -> list[PriceBar]:
        """Daily bars from the cache, syncing missing ones first.

        `final_only` keeps only bars that were final when they were downloaded (see the
        module docstring); a bar cached while its session was open is refreshed once it has
        closed, and left out until a final version arrives. Models must use it: a partial
        bar's prices and volume look nothing like the completed bars they were trained on.

        `max_age` skips the sync while the cache was refreshed more recently than that, for
        bulk reads (the forecaster's reference universe) that can tolerate older data. It
        never lets an in-progress bar pass as final.
        """
        today = self.now().date()
        end = min(end or today, today)
        now_utc = self.utc_now()
        sync = self.db.get(SymbolSync, symbol)
        force = final_only and sync is not None and self._closed_since_sync(symbol, sync, now_utc)
        fresh = (
            max_age is not None
            and sync is not None
            and not force
            and timedelta(0) <= now_utc - _utc(sync.synced_at) < max_age
            and sync.fetched_from <= start
        )
        if not fresh:
            self._sync(symbol, start, today, force=force)

        rows = self.db.scalars(
            select(PriceBar)
            .where(PriceBar.symbol == symbol, PriceBar.date >= start, PriceBar.date <= end)
            .order_by(PriceBar.date)
        ).all()
        if not rows and not self._has_any_bars(symbol):
            raise SymbolNotFoundError(symbol)
        rows = list(rows)
        if final_only:
            confirmed_at = self._confirmed_at(symbol, now_utc)
            rows = [
                r
                for r in rows
                if confirmed_at is not None and bar_is_final(symbol, r.date, confirmed_at)
            ]
        return rows

    def _confirmed_at(self, symbol: str, now_utc: datetime) -> datetime | None:
        """When the cache's tail was last downloaded, if that can be trusted."""
        sync = self.db.get(SymbolSync, symbol)
        if sync is None:
            return None
        synced = _utc(sync.synced_at)
        return None if synced > now_utc + CLOCK_SKEW else synced

    def _closed_since_sync(self, symbol: str, sync: SymbolSync, now_utc: datetime) -> bool:
        """True if a bar cached while in progress has closed since, so a refresh would
        replace it with the final version (or tell us the provider dropped it)."""
        synced = _utc(sync.synced_at)
        if synced > now_utc + CLOCK_SKEW:
            return True
        # Only bars dated around the sync can have been in progress then.
        recent = self.db.scalars(
            select(PriceBar.date).where(
                PriceBar.symbol == symbol, PriceBar.date >= synced.date() - timedelta(days=3)
            )
        )
        return any(
            not bar_is_final(symbol, d, synced) and bar_is_final(symbol, d, now_utc) for d in recent
        )

    def refill_gaps(self, symbol: str) -> list[date]:
        """Re-request calendar dates missing inside the cached range (the provider skipped
        them once, ISSUE-010) and store the bars that come back. Returns the dates that are
        still missing. Leaves `synced_at` alone: only older holes are filled.
        """
        have = list(
            self.db.scalars(
                select(PriceBar.date).where(PriceBar.symbol == symbol).order_by(PriceBar.date)
            )
        )
        if not have:
            return []
        cached = set(have)
        missing = [d for d in expected_dates(symbol, have[0], have[-1]) if d not in cached]
        if not missing:
            return []
        bars = self._fetch(symbol, missing[0], missing[-1])
        # Bars on a different scale (the provider re-adjusted since) must not be mixed in;
        # the next stale refresh detects the re-adjustment and replaces the whole series.
        known = {
            r.date: r.close
            for r in self.db.scalars(
                select(PriceBar).where(
                    PriceBar.symbol == symbol, PriceBar.date.in_([b.date for b in bars][:900])
                )
            )
        }
        ratios = sorted(b.close / known[b.date] for b in bars if b.date in known)
        if ratios and abs(ratios[len(ratios) // 2] - 1) > RESCALE_TOLERANCE * 10:
            log.warning("%s: provider history rescaled; gaps left for the next refresh", symbol)
            return missing
        wanted = set(missing)
        found = [b for b in bars if b.date in wanted]
        exists = self.db.scalar(select(SymbolSync.symbol).where(SymbolSync.symbol == symbol))
        if found and exists is not None:  # not dropped while fetching
            self._store(symbol, found)
            self.db.commit()
            log.info("%s: filled %d of %d missing dates", symbol, len(found), len(missing))
        else:
            found = []
        got = {b.date for b in found}
        return [d for d in missing if d not in got]

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

    def usd_krw_lookup(self, start: date, strict: bool = False) -> Callable[[date], Decimal]:
        """USD/KRW on any date since `start`, using the last known rate for weekends/holidays.

        The default suits display (the ledger): today's in-progress bar counts, and a date
        without history falls back to the earliest rate or the live quote. `strict=True` (for
        backtests and paper trading) uses final bars only and raises DataUnavailableError
        instead: for a date before the history, or when the last rate is more than
        FX_MAX_GAP_DAYS old.
        """
        bars = self.get_history(FX_USDKRW, start - timedelta(days=10), final_only=strict)
        dates = [b.date for b in bars]
        rates = [Decimal(str(b.close)) for b in bars]
        if strict:
            if not bars:
                raise DataUnavailableError(f"{FX_USDKRW}: no final bars since {start}")

            def strict_lookup(d: date) -> Decimal:
                i = bisect_right(dates, d)
                if i == 0 or (d - dates[i - 1]).days > FX_MAX_GAP_DAYS:
                    known = dates[i - 1] if i else None
                    raise DataUnavailableError(
                        f"{FX_USDKRW}: no rate within {FX_MAX_GAP_DAYS} days of {d} "
                        f"(last known {known})"
                    )
                return rates[i - 1]

            return strict_lookup
        fallback = Decimal(str(self.usd_krw().price))

        def lookup(d: date) -> Decimal:
            i = bisect_right(dates, d)
            if i == 0:
                return rates[0] if rates else fallback
            return rates[i - 1]

        return lookup

    def _fetch(self, symbol: str, start: date, end: date) -> list[Bar]:
        return validate_bars(symbol, self.provider.get_history(symbol, start, end))

    def _sync(
        self, symbol: str, start: date, today: date, retry: bool = True, force: bool = False
    ) -> None:
        """Fetch any missing bars, then write them in one short transaction.

        All network calls happen before the first write, so the SQLite write lock is never
        held while waiting on the provider. `synced_at` moves only when the tail was really
        re-downloaded: a failed (empty) refresh or a backfill of older dates must not make
        the cached tail look newer than it is.
        """
        sync = self.db.get(SymbolSync, symbol)
        now_utc = self.utc_now()

        bars: list[Bar] = []
        replace = False
        tail_refreshed = False
        # (since, dates the provider returned, when the replaced rows were cached)
        prune: tuple[date, set[date], datetime | None] | None = None
        fetched_from = start if sync is None else min(start, sync.fetched_from)
        if sync is None:
            bars = self._fetch(symbol, start, today)
            # Nothing came back (unknown symbol or a flaky upstream): record nothing so the
            # next request retries instead of trusting an empty cache.
            if not bars:
                return
            tail_refreshed = True
            # Rows left without a sync record (dropped or legacy) cannot be proven final.
            prune = (bars[0].date, {b.date for b in bars}, None)
        else:
            if start < sync.fetched_from:
                end = sync.fetched_from - timedelta(days=1)
                bars += self._fetch(symbol, start, end)
            synced = _utc(sync.synced_at)
            stale = force or now_utc - synced > HISTORY_TTL or synced > now_utc + CLOCK_SKEW
            if stale:
                last = self._last_bar_date(symbol) or sync.fetched_from
                fresh = self._fetch(symbol, last - OVERLAP, today)
                if fresh:
                    tail_refreshed = True
                    full = None
                    if self._rescaled(symbol, fresh, before=last):
                        # The provider re-adjusted its history: every cached bar is on the
                        # old scale, so replace the whole series rather than patching the end.
                        full = self._fetch(symbol, fetched_from, today)
                    if full is not None and self._covers_cache(symbol, full):
                        bars, replace = full, True
                    else:
                        bars += fresh
                        trusted = synced if synced <= now_utc + CLOCK_SKEW else None
                        prune = (last - OVERLAP, {b.date for b in fresh}, trusted)
                else:
                    log.warning("%s: refresh returned no bars; cache left as it was", symbol)
            if not bars and not tail_refreshed and start >= sync.fetched_from:
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
        elif prune is not None:
            self._prune(symbol, *prune)
        self._store(symbol, bars)
        # Upsert, not insert: concurrent first requests for the same symbol must not collide.
        synced_at = now_utc.astimezone(UTC).replace(tzinfo=None)
        stmt = sqlite_insert(SymbolSync).values(
            symbol=symbol, fetched_from=fetched_from, synced_at=synced_at
        )
        update = {"fetched_from": func.min(SymbolSync.fetched_from, stmt.excluded.fetched_from)}
        if tail_refreshed:
            update["synced_at"] = stmt.excluded.synced_at
        self.db.execute(stmt.on_conflict_do_update(index_elements=["symbol"], set_=update))
        self.db.commit()
        if sync is not None:
            self.db.expire(sync)  # reload the upserted row on next access

    def _prune(
        self, symbol: str, since: date, returned: set[date], cached_at: datetime | None
    ) -> None:
        """Delete cached bars from `since` on that the provider no longer returns and that
        were still in progress when cached (`cached_at` None: not known to be final). A bar
        that was final when cached is kept even if the provider skips it for a while."""
        dates = self.db.scalars(
            select(PriceBar.date).where(PriceBar.symbol == symbol, PriceBar.date >= since)
        )
        gone = [
            d
            for d in dates
            if d not in returned and (cached_at is None or not bar_is_final(symbol, d, cached_at))
        ]
        for i in range(0, len(gone), 500):
            self.db.execute(
                delete(PriceBar).where(
                    PriceBar.symbol == symbol, PriceBar.date.in_(gone[i : i + 500])
                )
            )
        if gone:
            log.info(
                "%s: removed %d unconfirmed bars the provider no longer returns", symbol, len(gone)
            )

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
