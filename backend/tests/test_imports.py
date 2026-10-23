import pytest

from app.deps import get_extractor
from app.services.screenshot_extractor import ExtractedHolding, ExtractedStatement, FakeExtractor

PNG = ("holdings.png", b"\x89PNG\r\n\x1a\nfake image body", "image/png")


def holding(
    name,
    ticker,
    qty,
    avg=None,
    cost_krw=None,
    asset_type="stock",
    confidence="high",
    return_pct=None,
    market_value_krw=None,
    pnl_krw=None,
):
    return ExtractedHolding(
        name=name,
        ticker_shown=ticker is not None and ticker.isascii() and name == ticker,
        ticker=ticker,
        asset_type=asset_type,
        quantity=qty,
        avg_price_usd=avg,
        avg_price_krw=None,
        cost_krw=cost_krw,
        market_value_krw=market_value_krw,
        pnl_krw=pnl_krw,
        return_pct=return_pct,
        confidence=confidence,
    )


def quote(client, symbol):
    return client.get(f"/api/market/{symbol}/quote").json()["price"]


def usdkrw(client):
    return client.get("/api/market/fx/usdkrw").json()["price"]


@pytest.fixture
def extractor(client):
    fx = usdkrw(client)
    fake = FakeExtractor(
        ExtractedStatement(
            broker="토스증권",
            holdings=[
                # 10 shares at $150; the won cost says the rate paid was 10% below today's.
                holding("애플", "AAPL", "10", avg="150", cost_krw=f"{10 * 150 * fx * 0.9:,.0f}"),
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
    assert apple["warning"] is None
    assert apple["ticker_guessed"] is True  # "애플" on screen, ticker inferred
    assert apple["implied_fx"] == pytest.approx(usdkrw(client) * 0.9, rel=1e-3)
    assert apple["price_estimated"] is False and apple["message"] is None
    assert apple["diff"] == "new"

    assert rows["비트코인"]["symbol"] == "BTC-USD"
    assert rows["도지코인"]["status"] == "unsupported"
    assert rows["알수없음"]["status"] == "unknown"
    assert rows["깨진값"]["status"] == "invalid"

    msft = rows["마이크로소프트"]
    assert msft["price_estimated"] is True
    assert msft["implied_fx"] is None
    assert msft["avg_price"] > 0 and msft["currency"] == "USD"
    assert msft["status"] == "ok" and "매입금액과 수량으로 계산한 단가" in msft["message"]

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


def test_jpeg_named_png_is_accepted_and_relabelled(client, extractor):
    # Messengers often save JPEG screenshots with a .png name; the browser then says image/png.
    jpeg_as_png = ("shot.png", b"\xff\xd8\xff\xe0" + b"jpeg body", "image/png")
    assert upload(client, jpeg_as_png).status_code == 200


def test_heic_gets_a_helpful_message(client, extractor):
    heic = ("IMG_0001.png", b"\x00\x00\x00\x18ftypheic" + b"body", "image/png")
    res = upload(client, heic)
    assert res.status_code == 422
    assert "HEIC" in res.json()["detail"]


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
                        "market_value_krw": None,
                        "pnl_krw": None,
                        "return_pct": None,
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
            market_value_krw=None,
            pnl_krw=None,
            return_pct=None,
            confidence="high",
        )
    ]
    row = upload(client).json()["rows"][0]
    assert row["currency"] == "KRW"
    assert row["avg_price"] == 80_000_000
    assert row["implied_fx"] is None
    assert row["warning"] is None  # the won cost agrees with the won price

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


def test_misread_unit_prices_are_flagged_with_a_suggestion(client, extractor):
    price = client.get("/api/market/GOOG/quote").json()["price"]
    fx = client.get("/api/market/fx/usdkrw").json()["price"]
    extractor.statement.holdings[:] = [
        # The KRW valuation of all 13 shares in the USD unit-price field (a Woori screen).
        holding("총액", "GOOG", "13", avg=f"{price * fx * 13:.0f}"),
        # The KRW unit price in the USD field.
        holding("원화", "GOOG", "2", avg=f"{price * fx:.0f}"),
    ]
    rows = {r["name"]: r for r in upload(client).json()["rows"]}
    assert rows["총액"]["status"] == "invalid" and "원화 총액" in rows["총액"]["message"]
    assert rows["원화"]["status"] == "invalid" and "원화 금액" in rows["원화"]["message"]
    # A certain misread is rejected outright; the softer warning is for `ok` rows only.
    assert rows["총액"]["warning"] is None and rows["원화"]["warning"] is None


def test_price_outside_the_sanity_band_is_still_invalid(client, extractor):
    price = client.get("/api/market/GOOG/quote").json()["price"]
    extractor.statement.holdings[:] = [holding("천배", "GOOG", "1", avg=f"{price * 5000:.2f}")]
    row = upload(client).json()["rows"][0]
    assert row["status"] == "invalid" and "너무 다릅니다" in row["message"]
    assert row["warning"] is None


def test_plausible_prices_are_not_flagged(client, extractor):
    quotes = {s: client.get(f"/api/market/{s}/quote").json()["price"] for s in ("NVDA", "AAPL")}
    extractor.statement.holdings[:] = [
        # A 200x winner is possible, so it stays importable, but it is flagged for a look.
        holding("장기 보유", "NVDA", "100", avg=f"{quotes['NVDA'] * 0.005:.4f}"),
        # Losing two thirds is ordinary: no warning at all.
        holding("큰 손실", "AAPL", "3", avg=f"{quotes['AAPL'] * 3:.2f}"),
    ]
    rows = {r["name"]: r for r in upload(client).json()["rows"]}
    assert {r["status"] for r in rows.values()} == {"ok"}
    assert rows["장기 보유"]["warning"] and "배 차이" in rows["장기 보유"]["warning"]
    assert rows["큰 손실"]["warning"] is None


def test_price_far_from_market_keeps_ok_status_with_a_warning(client, extractor):
    # The real failure: six US stocks came in at 1/28 to 1/430 of the current price because
    # the return column was read as the price. They passed PRICE_SANITY and were imported.
    price = client.get("/api/market/GOOG/quote").json()["price"]
    extractor.statement.holdings[:] = [
        holding("28분의 1", "GOOG", "5", avg=f"{price / 28:.2f}"),
        holding("25배", "GOOG", "2", avg=f"{price * 25:.2f}"),
        holding("19배", "GOOG", "2", avg=f"{price * 19:.2f}"),  # inside the band: fine
    ]
    rows = {r["name"]: r for r in upload(client).json()["rows"]}
    assert {r["status"] for r in rows.values()} == {"ok"}  # the user can still fix the price
    low = rows["28분의 1"]["warning"]
    assert "현재가" in low and "28배 차이" in low and "매수가를 직접 확인" in low
    assert "매입금액 기준" not in low  # nothing to derive a hint from
    assert "25배 차이" in rows["25배"]["warning"]
    assert rows["19배"]["warning"] is None


def test_return_percentage_read_as_the_price_is_warned(client, extractor):
    price = client.get("/api/market/GOOG/quote").json()["price"]
    extractor.statement.holdings[:] = [
        # The displayed +7.89% return landed in the price field.
        holding("수익률", "GOOG", "5", avg="7.89", return_pct="+7.89"),
        # Within 2% of the return still counts (OCR noise); the ratio alone would not flag it.
        holding(
            "근사", "GOOG", "5", avg=f"{price / 5:.2f}", return_pct=f"+{price / 5 * 1.01:.2f}%"
        ),
        # A return that is shown but unrelated to the price: no warning.
        holding("정상", "GOOG", "5", avg=f"{price * 0.9:.2f}", return_pct=f"-{price * 0.3:.2f}"),
    ]
    rows = {r["name"]: r for r in upload(client).json()["rows"]}
    assert {r["status"] for r in rows.values()} == {"ok"}
    assert "수익률(+7.89%)을 단가로 읽은 것 같습니다" in rows["수익률"]["warning"]
    assert "단가로 읽은 것 같습니다" in rows["근사"]["warning"]
    assert rows["정상"]["warning"] is None


def test_read_price_is_checked_against_the_won_cost(client, extractor):
    price, fx = quote(client, "GOOG"), usdkrw(client)
    value = 5 * price * fx  # 평가금액 of 5 shares today
    extractor.statement.holdings[:] = [
        # 28x below the market, but 매입금액 agrees (rate paid 10% below today's): a real winner.
        holding(
            "진짜 승자",
            "GOOG",
            "10",
            avg=f"{price / 28:.2f}",
            cost_krw=f"{10 * price / 28 * fx * 0.9:,.0f}",
        ),
        # 28x below the market, and 매입금액 says the price is wrong: replaced by the implied one.
        holding("교정", "GOOG", "10", avg=f"{price / 28:.2f}", cost_krw=f"{10 * price * fx:,.0f}"),
        # A plausible price that the market value and P&L contradict (cost = 2x): warn, keep it.
        holding(
            "불일치",
            "GOOG",
            "5",
            avg=f"{price:.2f}",
            market_value_krw=f"{value:,.0f}",
            pnl_krw=f"-{value:,.0f}",
        ),
        # A 20% gain in won means the rate paid was 20% below today's: still the same purchase.
        holding(
            "환율 차이",
            "GOOG",
            "5",
            avg=f"{price:.2f}",
            market_value_krw=f"{value:,.0f}",
            pnl_krw=f"+{value * 0.2:,.0f}",
        ),
    ]
    rows = {r["name"]: r for r in upload(client).json()["rows"]}
    assert {r["status"] for r in rows.values()} == {"ok"}

    winner = rows["진짜 승자"]
    assert winner["warning"] is None and winner["price_estimated"] is False
    assert winner["avg_price"] == pytest.approx(price / 28, abs=0.01)
    assert winner["implied_fx"] == pytest.approx(fx * 0.9, rel=5e-3)  # price rounded to cents

    fixed = rows["교정"]
    assert fixed["price_estimated"] is True and fixed["warning"] is None
    assert fixed["avg_price"] == pytest.approx(price, rel=1e-3)
    assert fixed["implied_fx"] is None
    assert "다른 숫자로 보여 쓰지 않고" in fixed["message"]
    assert "매입금액과 수량으로 계산한 단가를 넣었습니다(오늘 환율 기준)" in fixed["message"]

    off = rows["불일치"]
    assert off["price_estimated"] is False and off["avg_price"] == pytest.approx(price, abs=0.01)
    assert (
        "평가금액과 평가손익으로 계산한 단가" in off["warning"]
        and "100% 다릅니다" in off["warning"]
    )
    assert off["cost_krw"] == pytest.approx(2 * value, abs=1)  # the derived cost is still shown

    drift = rows["환율 차이"]
    assert drift["warning"] is None and drift["price_estimated"] is False
    assert drift["implied_fx"] == pytest.approx(fx * 0.8, rel=1e-3)


def test_list_view_without_average_price_derives_it_from_value_and_pnl(client, extractor):
    # 토스증권-style list: name, quantity and market value on the first line, "-123,456원
    # (-7.89%)" on the second. There is no average price anywhere on the screen.
    price, fx = quote(client, "GOOG"), usdkrw(client)
    value = 5 * price * fx
    cost = value / (1 - 0.0789)  # bought 7.89% above today's value
    extractor.statement.holdings[:] = [
        holding(
            "손익",
            "GOOG",
            "5",
            market_value_krw=f"{value:,.0f}원",
            pnl_krw=f"−{cost - value:,.0f}원",  # U+2212 minus, as some apps render it
            return_pct="-7.89%",
        ),
        holding(
            "수익률만", "GOOG", "2", market_value_krw=f"{2 * price * fx:,.0f}", return_pct="+8.2"
        ),
        holding("손익과 수익률", "GOOG", "1", pnl_krw="-30,000", return_pct="-10%"),
        holding("수량 없음", "GOOG", "", market_value_krw=f"{value:,.0f}", pnl_krw="-1,000"),
    ]
    rows = {r["name"]: r for r in upload(client).json()["rows"]}

    loss = rows["손익"]
    assert loss["status"] == "ok" and loss["price_estimated"] is True and loss["warning"] is None
    assert loss["cost_krw"] == pytest.approx(cost, abs=1)
    assert loss["avg_price"] == pytest.approx(cost / 5 / fx, rel=1e-3)
    assert loss["implied_fx"] is None
    assert "화면에 평균단가가 없어 평가금액과 평가손익으로 계산한 단가입니다" in loss["message"]

    only = rows["수익률만"]
    assert only["cost_krw"] == pytest.approx(2 * price * fx / 1.082, abs=1)
    assert "평가금액과 수익률로" in only["message"]

    both = rows["손익과 수익률"]
    assert both["cost_krw"] == 300_000 and "평가손익과 수익률로" in both["message"]

    assert rows["수량 없음"]["status"] == "invalid"


def test_return_read_as_the_price_is_replaced_when_value_and_pnl_are_shown(client, extractor):
    # The real failure: the magnitude of the return (-7.89%) sat in the price field. With the
    # market value and the P&L on screen the price is recomputed rather than merely flagged.
    price, fx = quote(client, "GOOG"), usdkrw(client)
    value = 5 * price * fx
    cost = value / (1 - 0.0789)
    extractor.statement.holdings[:] = [
        holding(
            "교정",
            "GOOG",
            "5",
            avg="7.89",
            market_value_krw=f"{value:,.0f}",
            pnl_krw=f"-{cost - value:,.0f}",
            return_pct="-7.89",
        ),
    ]
    row = upload(client).json()["rows"][0]
    assert row["status"] == "ok" and row["price_estimated"] is True and row["warning"] is None
    assert row["avg_price"] == pytest.approx(cost / 5 / fx, rel=1e-3)
    assert "화면의 단가 $7.89은 수익률로 보여 쓰지 않고" in row["message"]
    assert "평가금액과 평가손익으로 계산한 단가를 넣었습니다" in row["message"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("-123,456원", "-123456"),
        ("−7.89%", "-7.89"),
        ("▼ 3,000", "-3000"),
        ("+54,000", "54000"),
        # Arrows after the number (N-23): 토스증권 prints "7.89%▼".
        ("7.89%▼", "-7.89"),
        ("3.2%▽", "-3.2"),
        ("▲7.89%", "7.89"),
        ("△3.2%", "3.2"),
        ("-7.89%▼", "-7.89"),
        ("7.89%", "7.89"),  # no mark at all: positive
        ("+3.2%▼", "3.2"),  # contradictory marks: the one before the number wins
        ("-3.2%▲", "-3.2"),
        ("0", "0"),
        ("abc", None),
        (None, None),
    ],
)
def test_signed_decimal_keeps_the_sign(raw, expected):
    from decimal import Decimal

    from app.services.statement_import import _signed_decimal

    assert _signed_decimal(raw) == (Decimal(expected) if expected is not None else None)
