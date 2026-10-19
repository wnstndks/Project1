import pytest

from app.deps import get_extractor
from app.services.screenshot_extractor import ExtractedHolding, ExtractedStatement, FakeExtractor

PNG = ("holdings.png", b"\x89PNG fake bytes", "image/png")


def holding(name, ticker, qty, avg=None, cost_krw=None, asset_type="stock", confidence="high"):
    return ExtractedHolding(
        name=name,
        ticker=ticker,
        asset_type=asset_type,
        quantity=qty,
        avg_price_usd=avg,
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
    assert apple["implied_fx"] == pytest.approx(1400)
    assert apple["diff"] == "new"

    assert rows["비트코인"]["symbol"] == "BTC-USD"
    assert rows["도지코인"]["status"] == "unsupported"
    assert rows["알수없음"]["status"] == "unknown"
    assert rows["깨진값"]["status"] == "invalid"

    msft = rows["마이크로소프트"]
    assert msft["price_estimated"] is True
    assert msft["implied_fx"] is None
    assert msft["avg_price_usd"] > 0

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


@pytest.mark.parametrize(
    "files",
    [
        [("a.gif", b"GIF89a", "image/gif")],
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
                    "avg_price_usd": "150",
                    "fx_rate": "1400",
                },
                {
                    "asset_type": "crypto",
                    "symbol": "BTC",
                    "quantity": "0.05",
                    "avg_price_usd": "60000",
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
                {"asset_type": "stock", "symbol": "AAPL", "quantity": "1", "avg_price_usd": "1"},
                {"asset_type": "stock", "symbol": "ZZZZ", "quantity": "1", "avg_price_usd": "1"},
            ],
        },
    )
    assert res.status_code == 422
    assert client.get("/api/transactions").json() == []


def test_status_endpoint(client):
    body = client.get("/api/imports/status").json()
    assert set(body) == {"configured", "model"}
