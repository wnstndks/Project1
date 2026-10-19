"""News collection (GDELT + Finnhub), FinBERT scoring and leakage-safe daily news features.

Time boundary rules (a feature dated t may only use news published before the close of t):
- Stocks: the US close is 16:00 America/New_York. An article published at or after the close
  belongs to the next trading day.
- GDELT days are UTC calendar days, which run past the US close, so a stock's GDELT day d is
  only used from the first trading day after d.
- Crypto daily bars close at 00:00 UTC, so UTC calendar days line up with bars directly.
"""

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.data.assets import CRYPTO_ASSETS, trades_every_day
from app.data.calendar import us_close_utc
from app.data.news_sources import Article, FinnhubClient, GdeltClient, NewsDataError
from app.data.provider import MarketDataProvider
from app.db.models import GdeltDaily, NewsArticle, NewsCoverage, NewsSync
from app.ml.sentiment import SentimentScorer

NEW_YORK = ZoneInfo("America/New_York")
US_CLOSE = time(16, 0)
GDELT_TTL = timedelta(hours=6)
# GDELT returns sub-daily buckets for ranges of a week or less; always ask for more.
GDELT_MIN_SPAN = timedelta(days=8)
FINNHUB_TTL = timedelta(minutes=30)
FINNHUB_LOOKBACK = timedelta(days=365)

NEWS_FEATURES = [
    "finbert_score",
    "article_count",
    "gdelt_tone",
    "gdelt_volume",
    "has_finbert",
    "has_gdelt",
    # 1 where headline collection covered the date. Separates "no articles" from "no data":
    # Finnhub's free tier only reaches back about a year.
    "finbert_covered",
]

# GDELT rejects short phrases ("The specified phrase is too short"), so tickers like "AAPL"
# or "BTC" cannot be searched; queries use names of at least MIN_PHRASE characters.
MIN_PHRASE = 5
_GDELT_OVERRIDES = {
    "BTC-USD": '"Bitcoin"',
    "ETH-USD": '"Ethereum"',
    # Bare "Ripple" matches "ripple effect" and "Solana" matches place names.
    "XRP-USD": '("XRP price" OR "XRP Ledger" OR "Ripple Labs")',
    "SOL-USD": '("Solana blockchain" OR "Solana network" OR "Solana price")',
    "SPY": '"S&P 500"',
    "VOO": '"S&P 500"',
    "IVV": '"S&P 500"',
    "QQQ": '"Nasdaq 100"',
}
# Words used to pick a coin's headlines out of Finnhub's general crypto feed.
_CRYPTO_KEYWORDS = {
    "BTC-USD": ("Bitcoin", "BTC"),
    "ETH-USD": ("Ethereum", "Ether", "ETH"),
    "XRP-USD": ("XRP", "Ripple"),
    "SOL-USD": ("Solana", "SOL"),
}
_CORP_SUFFIX = re.compile(
    r"[,.]?\s+(inc|corp|corporation|co|company|ltd|plc|holdings|group|class [a-z])\.?$", re.I
)


def gdelt_query(symbol: str, name: str | None) -> str:
    if symbol in _GDELT_OVERRIDES:
        return f"{_GDELT_OVERRIDES[symbol]} sourcelang:english"
    full = re.sub(r"[^\w&.\- ]", "", name or symbol).strip()
    base = full
    while (stripped := _CORP_SUFFIX.sub("", base)) != base:
        base = stripped
    # "Meta" or "Visa" alone is too short for GDELT: fall back to the full official name.
    phrase = base if len(base) >= MIN_PHRASE else full.rstrip(".")
    return f'"{phrase}" sourcelang:english'


@dataclass
class SyncReport:
    warnings: list[str]


def article_feature_date(published_at: datetime, every_day: bool) -> date:
    """Calendar date whose close is the first one after publication (before trading-day roll)."""
    utc = published_at.replace(tzinfo=UTC) if published_at.tzinfo is None else published_at
    if every_day:
        return utc.astimezone(UTC).date()
    local = utc.astimezone(NEW_YORK)
    # Early-close days (13:00 ET) are honored: later articles belong to the next session.
    close = us_close_utc(local.date())
    return local.date() + timedelta(days=1) if utc >= close else local.date()


def _to_index(dates: Sequence[date], index: pd.DatetimeIndex) -> np.ndarray:
    """Position of the first index date >= each date (len(index) when after the last bar)."""
    return np.searchsorted(index.values, pd.to_datetime(list(dates)).values, side="left")


@dataclass
class NewsSummary:
    articles: list[NewsArticle]
    days: list[dict]
    finnhub_enabled: bool
    warnings: list[str]


class NewsService:
    def __init__(
        self,
        db: Session,
        provider: MarketDataProvider,
        gdelt: GdeltClient,
        finnhub: FinnhubClient | None,
        scorer: SentimentScorer,
        now: Callable[[], datetime] = lambda: datetime.now(UTC).replace(tzinfo=None),
    ) -> None:
        self.db = db
        self.provider = provider
        self.gdelt = gdelt
        self.finnhub = finnhub
        self.scorer = scorer
        self.now = now

    # ---- syncing -------------------------------------------------------------------------

    def sync(self, symbol: str, start: date, interactive: bool = False) -> SyncReport:
        """Fetch any news for `symbol` since `start` that is not cached yet.

        Interactive syncs (a user is waiting) try each source once and report failures as
        warnings, falling back to cached data. Background syncs wait out rate limits and raise.
        """
        state = self._state(symbol)
        today = self.now().date()
        warnings: list[str] = []
        # Phase 1: network and FinBERT only. Each step returns a write to apply later, so the
        # SQLite write lock is never held while waiting on GDELT, Finnhub or the model.
        steps = [("GDELT", lambda: self._fetch_gdelt(state, start, today, interactive))]
        if self.finnhub is not None:
            since = max(start, today - FINNHUB_LOOKBACK)
            steps.append(("Finnhub", lambda: self._fetch_finnhub(state, since, today)))
        writes = []
        for name, step in steps:
            try:
                writes.append(step())
            except NewsDataError as exc:
                if not interactive:
                    raise
                warnings.append(f"{name}: {exc}")
        # Phase 2: one short write transaction.
        purge = getattr(self, "_purge_gdelt", None)
        if purge is not None:
            self.db.execute(
                delete(GdeltDaily).where(
                    GdeltDaily.symbol == purge[0], GdeltDaily.query != purge[1]
                )
            )
            self._purge_gdelt = None
        for write in writes:
            if write is not None:
                write()
        self._persist_state(state)
        self.db.commit()
        return SyncReport(warnings)

    def _state(self, symbol: str) -> NewsSync:
        """The sync state. A new symbol gets a transient object, persisted in the write phase."""
        state = self.db.get(NewsSync, symbol)
        if state is None:
            name = None if symbol in CRYPTO_ASSETS else self.provider.get_name(symbol)
            return NewsSync(symbol=symbol, name=name, query=gdelt_query(symbol, name))
        query = gdelt_query(symbol, state.name)
        if query != state.query:
            # The query changed (e.g. a better phrase): old rows answer a different question.
            self._purge_gdelt = (symbol, query)
            state.query = query
            state.gdelt_from = state.gdelt_synced_at = None
        return state

    def _persist_state(self, state: NewsSync) -> None:
        if state in self.db:
            return
        # Upsert: two first requests for the same symbol must not collide on the primary key.
        cols = (
            "name",
            "query",
            "gdelt_from",
            "gdelt_synced_at",
            "finnhub_from",
            "finnhub_synced_at",
        )
        values = {"symbol": state.symbol} | {c: getattr(state, c) for c in cols}
        stmt = sqlite_insert(NewsSync).values(**values)
        self.db.execute(
            stmt.on_conflict_do_update(
                index_elements=["symbol"], set_={c: stmt.excluded[c] for c in cols}
            )
        )

    def _fetch_gdelt(
        self, state: NewsSync, start: date, today: date, interactive: bool = False
    ) -> Callable[[], None] | None:
        now = self.now()
        if state.gdelt_from is None or start < state.gdelt_from:
            fetch_from = start
        elif state.gdelt_synced_at is None or now - state.gdelt_synced_at > GDELT_TTL:
            fetch_from = self._last_gdelt_date(state.symbol) or start
        else:
            return None
        fetch_from = min(fetch_from, today - GDELT_MIN_SPAN)
        attempts = 1 if interactive else 4
        days = self.gdelt.daily(state.query, fetch_from, today, attempts=attempts)

        def write() -> None:
            self._write_gdelt(state, days, now)
            state.gdelt_from = min(state.gdelt_from or fetch_from, fetch_from)
            state.gdelt_synced_at = now

        return write

    def _write_gdelt(self, state: NewsSync, days: list, now: datetime) -> None:
        if days:
            stmt = sqlite_insert(GdeltDaily).values(
                [
                    {
                        "symbol": state.symbol,
                        "date": d.date,
                        "tone": d.tone,
                        "volume": d.volume,
                        "volume_norm": d.volume_norm,
                        "query": state.query,
                        "first_seen_at": now,
                    }
                    for d in days
                ]
            )
            self.db.execute(
                stmt.on_conflict_do_update(
                    index_elements=["symbol", "date"],
                    # first_seen_at is kept from the first insert on purpose.
                    set_={k: stmt.excluded[k] for k in ("tone", "volume", "volume_norm", "query")},
                )
            )

    def _fetch_finnhub(
        self, state: NewsSync, start: date, today: date
    ) -> Callable[[], None] | None:
        now = self.now()
        fresh = state.finnhub_synced_at is not None and now - state.finnhub_synced_at <= FINNHUB_TTL
        if state.symbol in CRYPTO_ASSETS and fresh:
            # The general crypto feed has no history to backfill: only the TTL matters.
            return None
        if state.finnhub_from is None or start < state.finnhub_from:
            fetch_from = start
        elif not fresh:
            last = self.db.scalar(
                select(NewsArticle.published_at)
                .where(NewsArticle.symbol == state.symbol)
                .order_by(NewsArticle.published_at.desc())
                .limit(1)
            )
            fetch_from = last.date() if last else start
        else:
            return None

        if state.symbol in CRYPTO_ASSETS:
            feed = self.finnhub.crypto_news()
            articles = self._for_coin(state.symbol, feed)
            # The general crypto feed only holds recent items: this sync covers the span of
            # the whole feed (before keyword filtering), not the requested start.
            covered_from = min((a.published_at.date() for a in feed), default=None)
        else:
            articles = self.finnhub.company_news(state.symbol, fetch_from, today)
            covered_from = fetch_from
        rows = self._score_articles(state.symbol, articles)

        def write() -> None:
            self.db.add_all(rows)
            if covered_from is not None:
                self.db.add(
                    NewsCoverage(
                        symbol=state.symbol, source="finnhub", start=covered_from, end=today
                    )
                )
                state.finnhub_from = min(state.finnhub_from or covered_from, covered_from)
            state.finnhub_synced_at = now

        return write

    @staticmethod
    def _for_coin(symbol: str, feed: list[Article]) -> list[Article]:
        words = _CRYPTO_KEYWORDS[symbol]
        return [
            a
            for a in feed
            if any(re.search(rf"\b{re.escape(w)}\b", a.headline, re.I) for w in words)
        ]

    def _score_articles(self, symbol: str, articles: list[Article]) -> list[NewsArticle]:
        known = set(self.db.scalars(select(NewsArticle.url).where(NewsArticle.symbol == symbol)))
        fresh = list({a.url: a for a in articles if a.url not in known}.values())
        if not fresh:
            return []
        scores = self.scorer.score([a.headline for a in fresh])
        return [
            NewsArticle(
                symbol=symbol,
                published_at=a.published_at.astimezone(UTC).replace(tzinfo=None),
                source=a.source[:100],
                headline=a.headline[:500],
                url=a.url[:1000],
                positive=s.positive,
                negative=s.negative,
                neutral=s.neutral,
            )
            for a, s in zip(fresh, scores, strict=True)
        ]

    def _last_gdelt_date(self, symbol: str) -> date | None:
        return self.db.scalar(
            select(GdeltDaily.date)
            .where(GdeltDaily.symbol == symbol)
            .order_by(GdeltDaily.date.desc())
            .limit(1)
        )

    # ---- reading -------------------------------------------------------------------------

    def summary(self, symbol: str, days: int = 30, limit: int = 30) -> NewsSummary:
        today = self.now().date()
        report = self.sync(symbol, today - timedelta(days=days), interactive=True)
        articles = list(
            self.db.scalars(
                select(NewsArticle)
                .where(NewsArticle.symbol == symbol)
                .order_by(NewsArticle.published_at.desc())
                .limit(limit)
            )
        )
        gd = self.db.scalars(
            select(GdeltDaily)
            .where(GdeltDaily.symbol == symbol, GdeltDaily.date >= today - timedelta(days=days))
            .order_by(GdeltDaily.date)
        )
        return NewsSummary(
            articles=articles,
            days=[{"date": g.date, "tone": g.tone, "volume": g.volume} for g in gd],
            finnhub_enabled=self.finnhub is not None,
            warnings=report.warnings,
        )

    def daily_features(self, symbol: str, index: pd.DatetimeIndex) -> pd.DataFrame:
        """News features aligned to a symbol's bar dates, using only pre-close information."""
        every_day = trades_every_day(symbol)
        out = pd.DataFrame(0.0, index=index, columns=NEWS_FEATURES)
        if len(index) == 0:
            return out
        start = index[0].date() - timedelta(days=7)
        n = len(index)

        rows = self.db.execute(
            select(NewsArticle.published_at, NewsArticle.positive, NewsArticle.negative).where(
                NewsArticle.symbol == symbol,
                NewsArticle.published_at >= datetime.combine(start, time.min),
            )
        ).all()
        if rows:
            pos = _to_index([article_feature_date(r[0], every_day) for r in rows], index)
            score = np.array([r[1] - r[2] for r in rows])
            keep = pos < n
            sums = np.bincount(pos[keep], weights=score[keep], minlength=n)
            counts = np.bincount(pos[keep], minlength=n)
            has = counts > 0
            out.loc[has, "finbert_score"] = sums[has] / counts[has]
            out["article_count"] = np.log1p(counts)
            out["has_finbert"] = has.astype(float)

        # Coverage is the union of the date ranges actually collected, so gaps (e.g. weeks
        # the app was not opened while the crypto feed rolled over) stay uncovered.
        covered = np.zeros(n, dtype=bool)
        for start_d, end_d in self.db.execute(
            select(NewsCoverage.start, NewsCoverage.end).where(
                NewsCoverage.symbol == symbol, NewsCoverage.source == "finnhub"
            )
        ):
            covered |= (index >= pd.Timestamp(start_d)) & (index <= pd.Timestamp(end_d))
        out["finbert_covered"] = covered.astype(float)

        gd = self.db.execute(
            select(GdeltDaily.date, GdeltDaily.tone, GdeltDaily.volume, GdeltDaily.volume_norm)
            .where(
                GdeltDaily.symbol == symbol,
                GdeltDaily.date >= start,
                GdeltDaily.query
                == select(NewsSync.query).where(NewsSync.symbol == symbol).scalar_subquery(),
            )
            .order_by(GdeltDaily.date)
        ).all()
        if gd:
            # A UTC day ends after the US close, so stocks may only use it from the next day.
            shift = timedelta(days=0 if every_day else 1)
            pos = _to_index([g[0] + shift for g in gd], index)
            tone = np.full(n, np.nan)
            vol = np.full(n, np.nan)
            for p, (_, t, v, norm) in zip(pos, gd, strict=True):
                if p >= n:
                    continue
                # Several UTC days can map onto one trading day (weekends): the latest wins.
                if t is not None:
                    tone[p] = t
                if v is not None and norm:
                    vol[p] = np.log1p(v / norm * 1e5)
            has = ~np.isnan(tone)
            out["gdelt_tone"] = np.where(has, tone, 0.0)
            out["gdelt_volume"] = np.nan_to_num(vol)
            out["has_gdelt"] = has.astype(float)
        return out
