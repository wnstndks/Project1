"""News sources: GDELT (free, daily tone/volume back to 2017) and Finnhub (headlines, API key).

Both are official APIs; nothing here scrapes web pages.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx2 as httpx

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
FINNHUB_URL = "https://finnhub.io/api/v1"


class NewsDataError(Exception):
    """A news source failed or is unavailable."""


@dataclass(frozen=True)
class Article:
    published_at: datetime  # UTC, timezone-aware
    headline: str
    source: str
    url: str


@dataclass(frozen=True)
class GdeltDay:
    date: date  # UTC calendar day the articles were published
    tone: float | None
    volume: int | None  # matching articles that day
    volume_norm: int | None  # all monitored articles that day (denominator)


def _ymdhms(d: date, end: bool = False) -> str:
    return d.strftime("%Y%m%d") + ("235959" if end else "000000")


def _daily(points: list[dict], mode: str) -> dict[date, dict]:
    """Collapse GDELT points to one per UTC day.

    Short ranges come back in 15-minute or hourly buckets; keying them by date would keep
    only the last bucket of each day. Tone is averaged, article counts are summed.
    """
    buckets: dict[date, list[dict]] = {}
    for p in points:
        buckets.setdefault(datetime.strptime(p["date"][:8], "%Y%m%d").date(), []).append(p)
    out: dict[date, dict] = {}
    for d, ps in buckets.items():
        if mode == "timelinetone":
            out[d] = {"value": sum(p["value"] for p in ps) / len(ps)}
        else:
            out[d] = {
                "value": sum(p["value"] for p in ps),
                "norm": sum(p.get("norm") or 0 for p in ps) or None,
            }
    return out


class GdeltClient:
    """GDELT DOC 2.0 timelines. GDELT allows one request every 5 seconds per client."""

    MIN_INTERVAL = 6.0
    _lock = threading.Lock()
    _last_request = 0.0

    def __init__(
        self,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.http = http or httpx.Client(timeout=120)
        self.sleep = sleep
        self.clock = clock

    def daily(self, query: str, start: date, end: date, attempts: int = 4) -> list[GdeltDay]:
        """`attempts` > 1 waits and retries on rate limits (for background collection only)."""
        tone = self._timeline(query, "timelinetone", start, end, attempts)
        volume = self._timeline(query, "timelinevolraw", start, end, attempts)
        days = sorted(set(tone) | set(volume))
        return [
            GdeltDay(
                date=d,
                tone=tone[d]["value"] if d in tone else None,
                volume=volume[d]["value"] if d in volume else None,
                volume_norm=volume[d].get("norm") if d in volume else None,
            )
            for d in days
        ]

    def _timeline(
        self, query: str, mode: str, start: date, end: date, attempts: int
    ) -> dict[date, dict]:
        params = {
            "query": query,
            "mode": mode,
            "format": "json",
            "startdatetime": _ymdhms(start),
            "enddatetime": _ymdhms(end, end=True),
            "timelinesmooth": 0,
        }
        for attempt in range(attempts):
            self._throttle()
            try:
                res = self.http.get(GDELT_URL, params=params)
            except httpx.HTTPError as exc:
                raise NewsDataError(f"GDELT request failed: {exc}") from exc
            if res.status_code == 429:
                if attempt + 1 < attempts:
                    self.sleep(10 * (attempt + 1))
                continue
            # GDELT answers some query errors ("phrase is too short") with 200 + plain text.
            if res.status_code != 200 or not res.text.lstrip().startswith("{"):
                raise NewsDataError(f"GDELT error {res.status_code}: {res.text[:120]}")
            timeline = res.json().get("timeline") or []
            return _daily(timeline[0]["data"] if timeline else [], mode)
        raise NewsDataError("GDELT rate limit: try again in a minute")

    def _throttle(self) -> None:
        with GdeltClient._lock:
            wait = GdeltClient._last_request + self.MIN_INTERVAL - self.clock()
            if wait > 0:
                self.sleep(wait)
            GdeltClient._last_request = self.clock()


class FinnhubClient:
    """Finnhub company news (free tier: about one year back, 60 requests/minute)."""

    def __init__(self, api_key: str, http: httpx.Client | None = None) -> None:
        # The key goes in a header, never in the URL, so it does not end up in logs.
        self.http = http or httpx.Client(timeout=30, headers={"X-Finnhub-Token": api_key})

    def company_news(self, symbol: str, start: date, end: date) -> list[Article]:
        out: list[Article] = []
        # Finnhub caps results per call, so ask a month at a time.
        cursor = start
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=30), end)
            rows = self._get(
                "/company-news",
                {"symbol": symbol, "from": cursor.isoformat(), "to": chunk_end.isoformat()},
            )
            out += [self._article(r) for r in rows if r.get("headline") and r.get("url")]
            cursor = chunk_end + timedelta(days=1)
        return out

    def crypto_news(self) -> list[Article]:
        """Latest general crypto news (Finnhub offers no per-coin history)."""
        rows = self._get("/news", {"category": "crypto"})
        return [self._article(r) for r in rows if r.get("headline") and r.get("url")]

    def _get(self, path: str, params: dict) -> list[dict]:
        try:
            res = self.http.get(FINNHUB_URL + path, params=params)
        except httpx.HTTPError as exc:
            raise NewsDataError(f"Finnhub request failed: {exc}") from exc
        if res.status_code == 401:
            raise NewsDataError("Finnhub API key is invalid. Check AM_FINNHUB_API_KEY")
        if res.status_code == 429:
            raise NewsDataError("Finnhub rate limit reached; try again in a minute")
        if res.status_code != 200:
            raise NewsDataError(f"Finnhub error {res.status_code}")
        return res.json() or []

    @staticmethod
    def _article(r: dict) -> Article:
        return Article(
            published_at=datetime.fromtimestamp(r["datetime"], tz=UTC),
            headline=r["headline"].strip(),
            source=r.get("source") or "",
            url=r["url"],
        )
