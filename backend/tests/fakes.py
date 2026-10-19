from datetime import date, timedelta

from app.data.news_sources import Article, GdeltDay, NewsDataError


class FakeGdelt:
    def __init__(self) -> None:
        self.calls: list[tuple[str, date, date]] = []
        self.fail = False

    def daily(self, query: str, start: date, end: date, attempts: int = 4) -> list[GdeltDay]:
        self.calls.append((query, start, end))
        if self.fail:
            raise NewsDataError("GDELT rate limit: try again in a minute")
        days = []
        d = start
        while d <= end:
            # Deterministic tone that differs by weekday so alignment bugs show up.
            days.append(GdeltDay(d, tone=float(d.weekday()), volume=10 + d.day, volume_norm=1000))
            d += timedelta(days=1)
        return days


class FakeFinnhub:
    def __init__(self, articles: dict[str, list[Article]] | None = None) -> None:
        self.articles = articles or {}
        self.calls: list[tuple[str, date, date]] = []

    def company_news(self, symbol: str, start: date, end: date) -> list[Article]:
        self.calls.append((symbol, start, end))
        return [a for a in self.articles.get(symbol, []) if start <= a.published_at.date() <= end]

    def crypto_news(self) -> list[Article]:
        self.calls.append(("crypto", date.min, date.min))
        return self.articles.get("crypto", [])
