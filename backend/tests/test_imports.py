import pytest

from app.deps import get_extractor
from app.services.screenshot_extractor import ExtractedHolding, ExtractedStatement, FakeExtractor

PNG = ("holdings.png", b"\x89PNG\r\n\x1a\nfake image body", "image/png")


def holding(name, ticker, qty, avg=None, cost_krw=None, asset_type="stock", confidence="high"):
    return ExtractedHolding(
        name=name,
        ticker_shown=ticker is not None and ticker.isascii() and name == ticker,
        ticker=ticker,
        asset_type=asset_type,
        quantity=qty,
        avg_price_usd=avg,
        avg_price_krw=None,
        cost_krw=cost_krw,
        confidence=confidence,
    )


@pytest.fixture
def extractor(client):
    fake = FakeExtractor(
        ExtractedStatement(
            broker="토스증권",
            holdings=[
                holding("애플", "AAPL", "10", avg="150", cost_krw="2,100,000"),  # paid 1400 KRW/USD
                holding("비트코인", "BTC", "0.05", avg="60000", asset_type="crypto"),
                holding("도지코인", "DOGE", "100", avg="0.1", asset_type="crypto"),
                holding("알수없음", None, "3", avg="10", confidence="low"),
                holding("마이크로소프트", "MSFT", "2", cost_krw="1,000,000"),  # no USD price
                holding("깨진값", "NVDA", "abc", avg="100"),
            ],
        )
    )
    client.app.dependency_overrides[get_extractor] = lambda: fake
    return fake


def upload(client, *files):
    return client.post("/api/imports/screenshot", files=[("files", f) for f in (files or [PNG])])


def test_preview_classifies_rows(client, extractor):
    res = upload(client)
    assert res.status_code == 200
    body = res.json()
    assert body["broker"] == "토스증권"
    rows = {r["name"]: r for r in body["rows"]}

    apple = rows["애플"]
    assert apple["status"] == "ok" and apple["symbol"] == "AAPL"
    assert apple["ticker_guessed"] is True  # "애플" on screen, ticker inferred
    assert apple["implied_fx"] == pytest.approx(1400)
    assert apple["diff"] == "new"

    assert rows["비트코인"]["symbol"] == "BTC-USD"
    assert rows["도지코인"]["status"] == "unsupported"
    assert rows["알수없음"]["status"] == "unknown"
    assert rows["깨진값"]["status"] == "invalid"

    msft = rows["마이크로소프트"]
    assert msft["price_estimated"] is True
    assert msft["implied_fx"] is None
    assert msft["avg_price"] > 0 and msft["currency"] == "USD"

    assert len(extractor.calls) == 1


def test_preview_reports_difference_from_current_holdings(client, extractor):
    client.post(
        "/api/transactions",
        json={
            "asset_type": "stock",
            "symbol": "AAPL",
            "side": "buy",
            "trade_date": "2026-10-01",
            "quantity": 4,
            "price": 100,
        },
    )
    apple = next(r for r in upload(client).json()["rows"] if r["symbol"] == "AAPL")
    assert apple["diff"] == "different"
    assert apple["current_quantity"] == 4
    # Screenshot: 10 @ 150 avg. Held: 4 @ 100. Recording 6 @ x keeps the average at 150:
    # (10*150 - 400) / 6 = 183.3333
    assert apple["delta_quantity"] == 6
    assert apple["delta_price"] == pytest.approx(183.3333)


def test_no_delta_offered_when_it_cannot_be_priced(client, extractor):
    # Held 10 @ 200 = 2000; screenshot 12 @ 150 = 1800: the extra 2 would need a negative price.
    client.post(
        "/api/transactions",
        json={
            "asset_type": "stock",
            "symbol": "AAPL",
            "side": "buy",
            "trade_date": "2026-10-01",
            "quantity": 10,
            "price": 200,
        },
    )
    extractor.statement.holdings[0] = holding("애플", "AAPL", "12", avg="150")
    apple = next(r for r in upload(client).json()["rows"] if r["symbol"] == "AAPL")
    assert apple["diff"] == "different"
    assert apple["delta_quantity"] is None and apple["delta_price"] is None


@pytest.mark.parametrize(
    "files",
    [
        [("a.gif", b"GIF89a", "image/gif")],
        [("fake.png", b"<html>not an image</html>", "image/png")],
        [PNG] * 6,
    ],
)
def test_preview_rejects_bad_uploads(client, extractor, files):
    assert upload(client, *files).status_code == 422
    assert extractor.calls == []


def test_commit_creates_buys_with_actual_fx(client, extractor):
    res = client.post(
        "/api/imports/commit",
        json={
            "trade_date": "2026-10-01",
            "rows": [
                {
                    "asset_type": "stock",
                    "symbol": "AAPL",
                    "quantity": "10",
                    "price": "150",
                    "fx_rate": "1400",
                },
                {
                    "asset_type": "crypto",
                    "symbol": "BTC",
                    "quantity": "0.05",
                    "price": "60000",
                },
            ],
        },
    )
    assert res.status_code == 200
    assert res.json() == {"created": 2}

    txs = {t["symbol"]: t for t in client.get("/api/transactions").json()}
    assert txs["AAPL"]["fx_rate"] == 1400
    assert txs["AAPL"]["usd_krw"] == 1400  # recorded rate wins over the market rate
    assert txs["AAPL"]["note"] == "스크린샷 가져오기"
    assert txs["BTC-USD"]["fx_rate"] is None

    aapl = next(h for h in client.get("/api/portfolio/holdings").json() if h["symbol"] == "AAPL")
    assert aapl["cost_basis_krw"] == pytest.approx(10 * 150 * 1400)


def test_commit_is_all_or_nothing(client, extractor):
    res = client.post(
        "/api/imports/commit",
        json={
            "trade_date": "2026-10-01",
            "rows": [
                {"asset_type": "stock", "symbol": "AAPL", "quantity": "1", "price": "1"},
                {"asset_type": "stock", "symbol": "ZZZZ", "quantity": "1", "price": "1"},
            ],
        },
    )
    assert res.status_code == 422
    assert client.get("/api/transactions").json() == []


def test_status_endpoint(client):
    body = client.get("/api/imports/status").json()
    assert set(body) == {"configured", "engine", "model", "problem"}


def test_ollama_extractor_parses_structured_reply():
    import json

    import httpx2 as httpx

    from app.services.screenshot_extractor import Image, OllamaExtractor

    sent = []

    def handler(req: httpx.Request) -> httpx.Response:
        sent.append(json.loads(req.content))
        content = json.dumps(
            {
                "broker": "우리은행",
                "holdings": [
                    {
                        "name": "애플",
                        "ticker": "AAPL",
                        "ticker_shown": False,
                        "asset_type": "stock",
                        "quantity": "3",
                        "avg_price_usd": None,
                        "avg_price_krw": None,
                        "cost_krw": "1,200,000",
                        "confidence": "medium",
                    }
                ],
            }
        )
        return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})

    ex = OllamaExtractor("qwen2.5vl:7b")
    ex.http = httpx.Client(transport=httpx.MockTransport(handler))
    statement = ex.extract([Image(b"png-bytes", "image/png")])
    assert statement.broker == "우리은행"
    assert statement.holdings[0].cost_krw == "1,200,000"
    # The image goes inline as base64 and the reply is constrained by our JSON schema.
    assert sent[0]["messages"][1]["images"]
    assert sent[0]["format"]["properties"]["holdings"]


def test_ollama_status_reports_missing_model():
    import httpx2 as httpx

    from app.services.screenshot_extractor import OllamaExtractor

    ex = OllamaExtractor("qwen2.5vl:7b")
    ex.http = httpx.Client(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json={"models": [{"name": "llama3:latest"}]})
        )
    )
    ready, problem = ex.status()
    assert not ready and "ollama pull qwen2.5vl:7b" in problem


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12주", "12"),
        ("$231.40", "231.40"),
        ("3,840,000원", "3840000"),
        ("0.031 BTC", "0.031"),
        ("abc", None),
        ("0", None),
        (None, None),
    ],
)
def test_decimal_parsing_strips_units(raw, expected):
    from decimal import Decimal

    from app.services.statement_import import _decimal

    assert _decimal(raw) == (Decimal(expected) if expected else None)


def test_upbit_coin_rows_are_kept_in_krw(client, extractor):
    extractor.statement.holdings[:] = [
        ExtractedHolding(
            name="비트코인",
            ticker="BTC",
            ticker_shown=True,
            asset_type="crypto",
            quantity="0.05",
            avg_price_usd=None,
            avg_price_krw="80,000,000",
            cost_krw="4,000,000",
            confidence="high",
        )
    ]
    row = upload(client).json()["rows"][0]
    assert row["currency"] == "KRW"
    assert row["avg_price"] == 80_000_000
    assert row["implied_fx"] is None

    res = client.post(
        "/api/imports/commit",
        json={
            "trade_date": "2026-10-01",
            "rows": [
                {
                    "asset_type": "crypto",
                    "symbol": "BTC",
                    "quantity": "0.05",
                    "currency": "KRW",
                    "price": "80000000",
                    "fx_rate": "1400",
                }
            ],
        },
    )
    assert res.status_code == 200
    tx = client.get("/api/transactions").json()[0]
    assert tx["currency"] == "KRW" and tx["price"] == 80_000_000
    assert tx["fx_rate"] is None  # a won trade needs no FX rate
