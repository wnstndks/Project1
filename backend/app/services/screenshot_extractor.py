"""Read holdings from broker app screenshots with a vision model + structured output.

Two interchangeable extractors share one prompt and output schema:
- OllamaExtractor: a local open-source vision model (free, the screenshot never leaves the PC).
- ClaudeExtractor: the Claude API (paid, most accurate). The only module importing the SDK.
Tests use FakeExtractor.
"""

import base64
from dataclasses import dataclass
from typing import Literal, Protocol

import anthropic
import httpx2 as httpx
from pydantic import BaseModel, Field, ValidationError

from app.services.errors import DomainError, UpstreamError


class ExtractedHolding(BaseModel):
    name: str = Field(description="Name exactly as shown in the screenshot, e.g. '애플' or 'Apple'")
    ticker: str | None = Field(
        description="US ticker (e.g. AAPL) or coin symbol (BTC, ETH, XRP, SOL); null if unsure"
    )
    ticker_shown: bool = Field(
        description="true only if the ticker symbol itself is printed in the screenshot"
    )
    asset_type: Literal["stock", "crypto"]
    quantity: str = Field(description="Quantity held as a plain decimal string, e.g. '12.5'")
    avg_price_usd: str | None = Field(
        description="Average purchase price per unit in USD as a decimal string; null if not shown"
    )
    avg_price_krw: str | None = Field(
        description="Average purchase price per unit in KRW (평균매수가) when shown in won; "
        "typical for coins on Upbit/Bithumb. Null if not shown"
    )
    cost_krw: str | None = Field(
        description="Total purchase amount in KRW (매입금액) as a decimal string; null if not shown"
    )
    # The next three are never written to the ledger. When the screen has no average price
    # (list views of 토스증권, 키움 and others), the service derives the purchase cost from
    # them: cost = market value - P&L, or market value / (1 + return / 100).
    market_value_krw: str | None = Field(
        description="Current market value of the position in KRW (평가금액) as displayed; "
        "null if not shown or shown only in dollars"
    )
    pnl_krw: str | None = Field(
        description="Unrealized profit or loss of the position in KRW (평가손익) exactly as "
        "displayed, WITH its sign, e.g. '-123456' or '+54000'; null if not shown or shown only "
        "in dollars"
    )
    return_pct: str | None = Field(
        description="Return percentage (수익률) exactly as displayed, with its sign, "
        "e.g. '+12.5' or '-3.2'; null if not shown"
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="low if any value was hard to read, the ticker is a guess, or it was "
        "unclear which number is the per-unit purchase price"
    )


class ExtractedStatement(BaseModel):
    holdings: list[ExtractedHolding]
    broker: str | None = Field(description="Broker app name if recognizable, else null")


@dataclass(frozen=True)
class Image:
    data: bytes
    media_type: str


class HoldingsExtractor(Protocol):
    def extract(self, images: list[Image]) -> ExtractedStatement: ...


SYSTEM_PROMPT = """\
You read screenshots of a Korean investor's brokerage or exchange app showing their current \
holdings (잔고, 보유종목) of US stocks and cryptocurrencies, and extract one entry per holding.

- Include every individual holding row. Skip totals, cash balances, and summary rows.
- Copy numbers exactly as displayed, without thousands separators. Never estimate a value \
that is not visible: use null instead.

How Korean broker apps lay out a holding (키움 영웅문, 토스증권, 삼성증권, 미래에셋, NH, KB, \
한국투자, 신한 and others): each row has the name, then several numbers, usually in this order: \
보유수량/잔고수량 (quantity), 평균단가/매입단가/평단/매수평균가 (average purchase price \
PER SHARE), 현재가 (current price), 평가손익 (unrealized profit, in won or dollars), \
수익률 (return in %, signed, often colored red or blue), 평가금액 (market value), \
매입금액 (total purchase amount) and 비중 (weight in %). Several apps print a won and a dollar \
figure for the same item next to each other, e.g. "$1,234.50 / 1,700,000원" or \
"+124,000원 (+8.2%)".

List views (토스증권, 키움, 삼성 and others) often show NO average price at all: the first line \
has the name, quantity and market value (평가금액, in won), and the second line the unrealized \
P&L in won with the return in percent, e.g. "-123,456원 (-7.89%)". In that case leave \
avg_price_usd and avg_price_krw null and copy 평가금액 into market_value_krw, 평가손익 into \
pnl_krw and 수익률 into return_pct, each with its sign. NEVER write the return percentage, with \
or without its sign, into avg_price_usd.

Field rules:
- avg_price_usd is ONLY the average purchase price per share (평균단가/매입단가/평단/매수평균가). \
It is never 수익률, 평가손익, 평가금액, 매입금액, 비중 or 현재가. For US stocks it is a dollar \
amount ($ or 달러), usually with two decimals, and it has about the same number of digits as \
the current price (현재가) in the same row. A number with a % sign or a +/- sign, or a number \
hundreds of times smaller or larger than the current price, is not the unit price. If you \
cannot tell which number is the unit price, set avg_price_usd to null and confidence to "low" \
instead of guessing.
- market_value_krw, pnl_krw, return_pct: the position's market value (평가금액), unrealized \
P&L (평가손익) and return (수익률) exactly as shown, with their signs; won amounts only. The \
app recomputes the purchase cost from them when no average price is shown.
- avg_price_krw: a per-unit average price shown in won (평균매수가/매수평균가), usual for coins \
on Upbit/Bithumb and for brokers that show US stocks in won.
- cost_krw: the total purchase amount in won (매입금액/투자원금/매수금액) exactly as shown. \
Always fill it, together with quantity, whenever it is visible: the app recomputes the unit \
price from them to cross-check avg_price_usd.
- Keep won amounts in the *_krw fields and dollar amounts in avg_price_usd. Never put a won \
amount or a total into a per-unit dollar field.
- Infer the US ticker from Korean or English company names (애플 -> AAPL, 엔비디아 -> NVDA). \
For ETFs use the exchange-traded ticker, never a mutual fund share class \
(Vanguard S&P 500 ETF -> VOO, not VFINX). Set ticker_shown to false whenever you inferred the \
ticker rather than read it. Coins are only BTC, ETH, XRP or SOL; use those symbols.
- Set confidence to "low" whenever a value is partly hidden, cut off, or ambiguous between \
columns.
- If the image does not show holdings, return an empty list.\
"""


class ClaudeExtractor:
    def __init__(self, model: str, api_key: str | None = None) -> None:
        # Without an explicit key the SDK resolves ANTHROPIC_API_KEY or an `ant` login profile.
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.model = model

    def extract(self, images: list[Image]) -> ExtractedStatement:
        content: list[dict] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": img.media_type,
                    "data": base64.standard_b64encode(img.data).decode("ascii"),
                },
            }
            for img in images
        ]
        content.append({"type": "text", "text": "Extract the holdings from these screenshots."})

        try:
            response = self.client.beta.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": content}],
                output_format=ExtractedStatement,
                # Reading values off a screenshot is extraction, not deep reasoning.
                output_config={"effort": "low"},
                # On a safety decline, retry server-side on Anthropic's recommended model.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except (anthropic.AuthenticationError, TypeError) as exc:
            # The SDK raises TypeError when no credential source is configured at all.
            raise DomainError(
                "Anthropic API key is missing or invalid. Set AM_ANTHROPIC_API_KEY in backend/.env"
            ) from exc
        except anthropic.BadRequestError as exc:
            raise DomainError(f"The image could not be processed: {exc.message}") from exc
        except anthropic.RateLimitError as exc:
            raise UpstreamError("Claude API rate limit reached. Try again shortly.") from exc
        except anthropic.APIStatusError as exc:
            raise UpstreamError(f"Claude API error ({exc.status_code})") from exc
        except anthropic.APIConnectionError as exc:
            raise UpstreamError("Could not reach the Claude API") from exc

        if response.stop_reason == "refusal":
            raise DomainError("The screenshot could not be read (request declined)")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise UpstreamError("Claude returned an incomplete result. Try fewer images.")
        return response.parsed_output


class OllamaExtractor:
    """Local vision model served by Ollama (https://ollama.com), using its JSON-schema output."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434") -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        # The first call loads the model into GPU memory, which can take a while.
        self.http = httpx.Client(timeout=300)

    def status(self) -> tuple[bool, str | None]:
        """(ready, problem). Ready means the server answers and the model is downloaded."""
        try:
            res = self.http.get(f"{self.base_url}/api/tags", timeout=3)
        except httpx.HTTPError:
            return False, "Ollama가 실행 중이 아닙니다. Ollama 앱을 실행하세요."
        names = {m.get("name") for m in res.json().get("models", [])}
        if self.model not in names and f"{self.model}:latest" not in names:
            return False, f"모델이 없습니다. 터미널에서 `ollama pull {self.model}`을 실행하세요."
        return True, None

    def extract(self, images: list[Image]) -> ExtractedStatement:
        body = {
            "model": self.model,
            "stream": False,
            "format": ExtractedStatement.model_json_schema(),
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "Extract the holdings from these screenshots. Reply with JSON only.",
                    "images": [base64.standard_b64encode(i.data).decode("ascii") for i in images],
                },
            ],
        }
        try:
            res = self.http.post(f"{self.base_url}/api/chat", json=body)
        except httpx.ConnectError as exc:
            raise UpstreamError("Ollama가 실행 중이 아닙니다. Ollama 앱을 실행하세요.") from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(f"Ollama request failed: {exc}") from exc
        if res.status_code == 404:
            raise DomainError(f"Ollama 모델이 없습니다. `ollama pull {self.model}`을 실행하세요.")
        if res.status_code != 200:
            raise UpstreamError(f"Ollama error {res.status_code}: {res.text[:200]}")
        try:
            return ExtractedStatement.model_validate_json(res.json()["message"]["content"])
        except (KeyError, ValidationError) as exc:
            raise UpstreamError(
                "The local model returned an unreadable result. Try again."
            ) from exc


DEMO_STATEMENT = ExtractedStatement(
    broker="데모 증권",
    holdings=[
        ExtractedHolding(
            ticker_shown=False,
            name="애플",
            ticker="AAPL",
            asset_type="stock",
            quantity="12",
            avg_price_usd="231.40",
            avg_price_krw=None,
            cost_krw="3,840,000",
            market_value_krw=None,
            pnl_krw=None,
            return_pct=None,
            confidence="high",
        ),
        ExtractedHolding(
            ticker_shown=False,
            name="엔비디아",
            ticker="NVDA",
            asset_type="stock",
            quantity="25",
            avg_price_usd="128.75",
            avg_price_krw=None,
            cost_krw="4,410,000",
            market_value_krw=None,
            pnl_krw=None,
            return_pct=None,
            confidence="high",
        ),
        ExtractedHolding(
            ticker_shown=False,
            name="비트코인",
            ticker="BTC",
            asset_type="crypto",
            quantity="0.031",
            avg_price_usd=None,
            avg_price_krw=None,
            cost_krw="3,520,000",
            market_value_krw=None,
            pnl_krw=None,
            return_pct=None,
            confidence="medium",
        ),
        ExtractedHolding(
            ticker_shown=False,
            name="팔란티어",
            ticker="PLTR",
            asset_type="stock",
            quantity="40",
            avg_price_usd="92.10",
            avg_price_krw=None,
            cost_krw=None,
            market_value_krw=None,
            pnl_krw=None,
            return_pct=None,
            confidence="low",
        ),
    ],
)


class FakeExtractor:
    """Returns a fixed statement; used by tests and when developing without an API key."""

    def __init__(self, statement: ExtractedStatement = DEMO_STATEMENT) -> None:
        self.statement = statement
        # Only the number of images per call is kept: a demo server must not retain uploads.
        self.calls: list[int] = []

    def extract(self, images: list[Image]) -> ExtractedStatement:
        self.calls.append(len(images))
        return self.statement
