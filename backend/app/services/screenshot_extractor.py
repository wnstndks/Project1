"""Read holdings from broker app screenshots with Claude's vision + structured output.

This is the only module that imports the Anthropic SDK. Tests use FakeExtractor.
"""

import base64
from dataclasses import dataclass
from typing import Literal, Protocol

import anthropic
from pydantic import BaseModel, Field

from app.services.errors import DomainError, UpstreamError


class ExtractedHolding(BaseModel):
    name: str = Field(description="Name exactly as shown in the screenshot, e.g. '애플' or 'Apple'")
    ticker: str | None = Field(
        description="US ticker (e.g. AAPL) or coin symbol (BTC, ETH, XRP, SOL); null if unsure"
    )
    asset_type: Literal["stock", "crypto"]
    quantity: str = Field(description="Quantity held as a plain decimal string, e.g. '12.5'")
    avg_price_usd: str | None = Field(
        description="Average purchase price per unit in USD as a decimal string; null if not shown"
    )
    cost_krw: str | None = Field(
        description="Total purchase amount in KRW (매입금액) as a decimal string; null if not shown"
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="low if any value was hard to read or the ticker is a guess"
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
holdings (잔고) of US stocks and cryptocurrencies, and extract one entry per holding.

- Include every individual holding row. Skip totals, cash balances, and summary rows.
- Copy numbers exactly as displayed, without thousands separators. Never estimate a value \
that is not visible: use null instead.
- Korean apps often show prices in both USD and KRW. Put the per-unit average purchase price \
in USD into avg_price_usd, and the total purchase amount in KRW (매입금액) into cost_krw.
- Infer the US ticker from Korean or English company names (애플 -> AAPL, 엔비디아 -> NVDA). \
Coins are only BTC, ETH, XRP or SOL; use those symbols. Mark guesses as low confidence.
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


DEMO_STATEMENT = ExtractedStatement(
    broker="데모 증권",
    holdings=[
        ExtractedHolding(
            name="애플",
            ticker="AAPL",
            asset_type="stock",
            quantity="12",
            avg_price_usd="231.40",
            cost_krw="3,840,000",
            confidence="high",
        ),
        ExtractedHolding(
            name="엔비디아",
            ticker="NVDA",
            asset_type="stock",
            quantity="25",
            avg_price_usd="128.75",
            cost_krw="4,410,000",
            confidence="high",
        ),
        ExtractedHolding(
            name="비트코인",
            ticker="BTC",
            asset_type="crypto",
            quantity="0.031",
            avg_price_usd=None,
            cost_krw="3,520,000",
            confidence="medium",
        ),
        ExtractedHolding(
            name="팔란티어",
            ticker="PLTR",
            asset_type="stock",
            quantity="40",
            avg_price_usd="92.10",
            cost_krw=None,
            confidence="low",
        ),
    ],
)


class FakeExtractor:
    """Returns a fixed statement; used by tests and when developing without an API key."""

    def __init__(self, statement: ExtractedStatement = DEMO_STATEMENT) -> None:
        self.statement = statement
        self.calls: list[list[Image]] = []

    def extract(self, images: list[Image]) -> ExtractedStatement:
        self.calls.append(images)
        return self.statement
