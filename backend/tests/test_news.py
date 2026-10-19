from datetime import UTC, date, datetime, timedelta

import httpx2 as httpx
import pandas as pd
import pytest

from app.data.news_sources import Article, FinnhubClient, GdeltClient, NewsDataError
from app.deps import get_finnhub, get_gdelt, get_scorer
from app.ml.sentiment import KeywordScorer
from app.services.news import NewsService, article_feature_date, gdelt_query
from tests.conftest import TODAY
from tests.fakes import FakeFinnhub, FakeGdelt

NOW = datetime.combine(TODAY, datetime.min.time()) + timedelta(hours=22)  # UTC


def et(y, m, d, hh, mm=0):
    """A New York wall-clock time (EDT, UTC-4 in October) as an aware UTC datetime."""
    return datetime(y, m, d, hh + 4, mm, tzinfo=UTC)


def art(symbol_url, when, headline="Apple shares surge on record sales"):
    return Article(published_at=when, headline=headline, source="Test", url=symbol_url)


@pytest.fixture
def gdelt():
    return FakeGdelt()


@pytest.fixture
def finnhub():
    return FakeFinnhub(
        {
            "AAPL": [
                art("u1", et(2026, 10, 15, 10), "Apple shares surge on record sales"),
                art(
                    "u2", et(2026, 10, 16, 17), "Apple faces EU probe, stock falls"
                ),  # Fri after close
            ],
            "crypto": [
                art("c1", datetime(2026, 10, 16, 23, tzinfo=UTC), "Bitcoin rally extends"),
                art("c2", datetime(2026, 10, 16, 12, tzinfo=UTC), "Dogecoin memes again"),
            ],
        }
    )


@pytest.fixture
def service(db, provider, gdelt, finnhub):
    return NewsService(db, provider, gdelt, finnhub, KeywordScorer(), now=lambda: NOW)


@pytest.mark.parametrize(
    ("symbol", "name", "expected"),
    [
        ("AAPL", "Apple Inc.", '("Apple" OR "AAPL") sourcelang:english'),
        ("NVDA", "NVIDIA Corporation", '("NVIDIA" OR "NVDA") sourcelang:english'),
        ("BTC-USD", None, '("Bitcoin" OR "BTC") sourcelang:english'),
        ("VOO", "Vanguard S&P 500 ETF", '"S&P 500" sourcelang:english'),
    ],
)
def test_gdelt_query(symbol, name, expected):
    assert gdelt_query(symbol, name) == expected


def test_article_feature_date_respects_us_close():
    assert article_feature_date(et(2026, 10, 15, 15, 59), every_day=False) == date(2026, 10, 15)
    assert article_feature_date(et(2026, 10, 15, 16, 0), every_day=False) == date(2026, 10, 16)
    # Crypto bars close at 00:00 UTC, so the UTC date is used as is.
    late = datetime(2026, 10, 15, 23, 30, tzinfo=UTC)
    assert article_feature_date(late, every_day=True) == date(2026, 10, 15)


def test_sync_scores_dedupes_and_is_incremental(service, gdelt, finnhub, db):
    service.sync("AAPL", date(2026, 10, 1))
    service.sync("AAPL", date(2026, 10, 1))  # within TTLs: no new calls
    assert len(gdelt.calls) == 1
    assert len(finnhub.calls) == 1

    summary = service.summary("AAPL")
    by_url = {a.url: a for a in summary.articles}
    assert set(by_url) == {"u1", "u2"}
    assert by_url["u1"].positive > by_url["u1"].negative
    assert by_url["u2"].negative > by_url["u2"].positive


def test_crypto_news_filters_by_coin(service):
    service.sync("BTC-USD", date(2026, 10, 1))
    urls = [a.url for a in service.summary("BTC-USD").articles]
    assert urls == ["c1"]


def test_daily_features_never_use_post_close_news(service):
    service.sync("AAPL", date(2026, 10, 1))
    index = pd.DatetimeIndex(pd.bdate_range("2026-10-12", "2026-10-19"))  # Mon..Mon
    f = service.daily_features("AAPL", index)

    # Thursday 10:00 ET positive headline counts on Thursday.
    assert f.loc["2026-10-15", "finbert_score"] > 0
    # Friday 17:00 ET negative headline is after the close: it belongs to Monday, not Friday.
    assert f.loc["2026-10-16", "has_finbert"] == 0
    assert f.loc["2026-10-19", "finbert_score"] < 0

    # GDELT UTC day d is only usable from the next trading day for stocks.
    # FakeGdelt tone = weekday of the UTC day: Wed (2) shows up on Thu.
    assert f.loc["2026-10-15", "gdelt_tone"] == 2.0
    # Friday's UTC day (4) is only usable from Monday. (Data ends on "today", a Friday,
    # so the weekend days that would also map to Monday do not exist yet.)
    assert f.loc["2026-10-16", "gdelt_tone"] == 3.0
    assert f.loc["2026-10-19", "gdelt_tone"] == 4.0


def test_crypto_daily_features_use_same_utc_day(service):
    service.sync("BTC-USD", date(2026, 10, 1))
    index = pd.DatetimeIndex(pd.date_range("2026-10-12", "2026-10-16"))
    f = service.daily_features("BTC-USD", index)
    assert f.loc["2026-10-15", "gdelt_tone"] == 3.0  # Thursday's own UTC day
    assert f.loc["2026-10-16", "finbert_score"] > 0


def test_news_endpoint(client, gdelt, finnhub):
    client.app.dependency_overrides[get_gdelt] = lambda: gdelt
    client.app.dependency_overrides[get_finnhub] = lambda: finnhub
    client.app.dependency_overrides[get_scorer] = lambda: KeywordScorer()
    body = client.get("/api/news/aapl").json()
    assert body["symbol"] == "AAPL"
    assert body["finnhub_enabled"] is True
    assert {"headline", "positive", "negative"} <= set(body["articles"][0])

    client.app.dependency_overrides[get_finnhub] = lambda: None
    assert client.get("/api/news/MSFT").json()["finnhub_enabled"] is False


def test_gdelt_client_retries_rate_limit_and_parses():
    responses = iter(
        [
            httpx.Response(429, text="Please limit requests"),
            httpx.Response(
                200,
                json={"timeline": [{"data": [{"date": "20261015T000000Z", "value": 1.5}]}]},
            ),
        ]
        * 2
    )
    http = httpx.Client(transport=httpx.MockTransport(lambda req: next(responses)))
    sleeps = []
    client = GdeltClient(http=http, sleep=sleeps.append, clock=lambda: 1e9)
    days = client.daily("x", date(2026, 10, 15), date(2026, 10, 15))
    assert days[0].tone == 1.5
    assert 10 in sleeps  # backed off after the 429


def test_gdelt_client_gives_up_with_clear_error():
    http = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(429)))
    client = GdeltClient(http=http, sleep=lambda s: None, clock=lambda: 1e9)
    with pytest.raises(NewsDataError, match="rate limit"):
        client.daily("x", date(2026, 10, 15), date(2026, 10, 15))


def test_finnhub_key_sent_as_header_not_url():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=[])

    client = FinnhubClient("secret-key", http=None)
    client.http = httpx.Client(
        transport=httpx.MockTransport(handler), headers={"X-Finnhub-Token": "secret-key"}
    )
    client.company_news("AAPL", date(2026, 1, 1), date(2026, 1, 10))
    assert "secret-key" not in str(seen[0].url)
    assert seen[0].headers["X-Finnhub-Token"] == "secret-key"
