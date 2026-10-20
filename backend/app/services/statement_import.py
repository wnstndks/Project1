"""Turn extracted screenshot holdings into reviewable rows, then into buy transactions."""

import re
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal

from app.data.assets import UnsupportedSymbolError, normalize_symbol
from app.db.models import AssetType, Currency, Side, Transaction
from app.schemas.transactions import TransactionIn
from app.services.errors import DomainError
from app.services.market_data import MarketDataService, SymbolNotFoundError
from app.services.portfolio import PortfolioService
from app.services.screenshot_extractor import ExtractedHolding, HoldingsExtractor, Image
from app.services.transactions import TransactionService

MAX_IMAGES = 5
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp"}
IMPORT_NOTE = "스크린샷 가져오기"
# Average cost / current price outside this range means a misread number.
PRICE_SANITY = (Decimal("0.02"), Decimal("50"))

RowStatus = Literal["ok", "unsupported", "unknown", "invalid"]
Diff = Literal["new", "same", "different"]


@dataclass
class PreviewRow:
    name: str
    symbol: str | None
    asset_type: AssetType
    quantity: Decimal | None
    # The trade currency: USD for stocks, KRW for coins held on Korean exchanges.
    currency: Currency
    # Average purchase price per unit, in `currency`.
    avg_price: Decimal | None
    cost_krw: Decimal | None
    # USD/KRW actually paid, implied by the KRW cost and the USD average price (USD rows).
    implied_fx: Decimal | None
    # True when a USD price was not shown and was derived from cost_krw at today's rate.
    price_estimated: bool
    # True when the ticker was inferred from the name rather than printed on screen.
    ticker_guessed: bool
    confidence: str
    status: RowStatus
    message: str | None
    current_quantity: Decimal | None
    diff: Diff | None
    # When the screenshot shows more than is held: the extra units, and the price that makes
    # the moving-average cost after the buy equal the screenshot's average price.
    delta_quantity: Decimal | None
    delta_price: Decimal | None


@dataclass
class Preview:
    broker: str | None
    rows: list[PreviewRow]


@dataclass
class CommitRow:
    asset_type: AssetType
    symbol: str
    quantity: Decimal
    price: Decimal
    currency: Currency = Currency.USD
    fx_rate: Decimal | None = None


def sniff_image_type(data: bytes) -> str | None:
    """The real image format from the file's first bytes.

    Browsers label uploads by file extension, and screenshots shared through messengers or
    saved by some apps are often JPEG or WebP files named ".png". The content decides.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _describe_unsupported(data: bytes) -> str:
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftyphevc"):
        return (
            "아이폰 HEIC 사진 형식은 지원하지 않습니다. 스크린샷을 PNG/JPEG로 저장하거나 "
            "설정 > 카메라 > 포맷에서 '높은 호환성'을 선택해 다시 캡처하세요"
        )
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "GIF는 지원하지 않습니다. PNG나 JPEG로 저장해 주세요"
    return "이미지 파일이 아니거나 손상된 파일입니다. PNG, JPEG 또는 WebP 스크린샷을 올려 주세요"


def _decimal(raw: str | None) -> Decimal | None:
    """Parse a positive number from model output like "12주", "$231.40" or "3,840,000원"."""
    if raw is None:
        return None
    cleaned = re.sub(r"[^\d.]", "", raw)
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return value if value > 0 else None


class StatementImportService:
    def __init__(
        self,
        extractor: HoldingsExtractor,
        market: MarketDataService,
        portfolio: PortfolioService,
        transactions: TransactionService,
    ) -> None:
        self.extractor = extractor
        self.market = market
        self.portfolio = portfolio
        self.transactions = transactions

    def preview(self, images: list[Image]) -> Preview:
        if not images:
            raise DomainError("Upload at least one screenshot")
        if len(images) > MAX_IMAGES:
            raise DomainError(f"Upload at most {MAX_IMAGES} screenshots at a time")
        checked = []
        for img in images:
            if len(img.data) > MAX_IMAGE_BYTES:
                raise DomainError("스크린샷은 한 장에 10MB 이하여야 합니다")
            # Trust the bytes, not the client's label; the vision model needs the real type.
            real = sniff_image_type(img.data)
            if real not in ALLOWED_TYPES:
                raise DomainError(_describe_unsupported(img.data))
            checked.append(Image(img.data, real))
        images = checked

        statement = self.extractor.extract(images)
        held = {
            h.symbol: (
                h.quantity,
                h.cost_basis_krw if h.currency == Currency.KRW else h.cost_basis,
                h.currency,
            )
            for h in self.portfolio.holdings()
        }
        fx_today = Decimal(str(self.market.usd_krw().price))
        return Preview(
            broker=statement.broker,
            rows=[self._row(h, held, fx_today) for h in statement.holdings],
        )

    def commit(self, rows: list[CommitRow], trade_date: date) -> list[Transaction]:
        if not rows:
            raise DomainError("Nothing to import")
        return self.transactions.create_many(
            [
                TransactionIn(
                    asset_type=r.asset_type,
                    symbol=r.symbol,
                    side=Side.BUY,
                    trade_date=trade_date,
                    currency=r.currency,
                    quantity=r.quantity,
                    price=r.price,
                    # A KRW trade's won cost is exact; a separate FX rate would be meaningless.
                    fx_rate=r.fx_rate if r.currency == Currency.USD else None,
                    note=IMPORT_NOTE,
                )
                for r in rows
            ]
        )

    def _row(
        self,
        h: ExtractedHolding,
        held: dict[str, tuple[Decimal, Decimal, Currency]],
        fx_today: Decimal,
    ) -> PreviewRow:
        qty = _decimal(h.quantity)
        avg_usd = _decimal(h.avg_price_usd)
        avg_krw = _decimal(h.avg_price_krw)
        cost_krw = _decimal(h.cost_krw)
        asset_type = AssetType(h.asset_type)

        estimated = False
        implied_fx = None
        # Coins on Korean exchanges are bought in won: keep them in KRW (exact won cost).
        krw_coin = asset_type == AssetType.CRYPTO and (avg_krw is not None or avg_usd is None)
        if krw_coin:
            currency = Currency.KRW
            avg = avg_krw
            if avg is None and cost_krw is not None and qty:
                avg = (cost_krw / qty).quantize(Decimal("0.01"), ROUND_HALF_UP)
        else:
            currency = Currency.USD
            avg = avg_usd
            if avg is None and cost_krw is not None and qty:
                avg = (cost_krw / qty / fx_today).quantize(Decimal("0.0001"), ROUND_HALF_UP)
                estimated = True
            if cost_krw is not None and avg is not None and qty and not estimated:
                implied_fx = (cost_krw / (qty * avg)).quantize(Decimal("0.01"), ROUND_HALF_UP)
                # A wildly off rate means a misread number, not a real purchase rate.
                if not (Decimal("500") <= implied_fx <= Decimal("3000")):
                    implied_fx = None

        symbol, status, message, market = self._resolve(h, asset_type)
        if status == "ok" and (qty is None or avg is None):
            status, message = "invalid", "수량 또는 평균단가를 읽지 못했습니다"
        if status == "ok" and market and avg is not None:
            # Vision models sometimes put the won amount, or the position total, in the
            # unit-price field. No real average cost is 50x the current price either way.
            now = Decimal(str(market)) * (fx_today if currency == Currency.KRW else 1)
            ratio = avg / now
            if not PRICE_SANITY[0] <= ratio <= PRICE_SANITY[1]:
                status = "invalid"
                unit = "₩" if currency == Currency.KRW else "$"
                message = (
                    f"평균단가가 현재가({unit}{now:,.2f})의 {ratio:,.1f}배입니다. 원화 금액이나 "
                    "총액을 단가로 읽었을 수 있으니 단가를 확인하세요"
                )

        current, current_cost, held_currency = (
            held.get(symbol, (None, None, None)) if symbol else (None, None, None)
        )
        if status == "ok" and held_currency is not None and held_currency != currency:
            status = "invalid"
            message = f"이미 {held_currency}로 기록된 종목입니다. 통화를 맞춰 직접 입력하세요"
        # Both or neither: a delta without a valid price must not be recordable.
        delta_qty = delta_price = None
        if (
            current is not None
            and held_currency == currency
            and qty is not None
            and qty > current
            and avg is not None
        ):
            price = (qty * avg - current_cost) / (qty - current)
            if price > 0:
                delta_qty = qty - current
                delta_price = price.quantize(Decimal("0.0001"), ROUND_HALF_UP)
        diff: Diff | None = None
        if symbol and qty is not None:
            diff = "new" if current is None else ("same" if current == qty else "different")

        return PreviewRow(
            name=h.name,
            symbol=symbol,
            asset_type=asset_type,
            quantity=qty,
            currency=currency,
            avg_price=avg,
            cost_krw=cost_krw,
            implied_fx=implied_fx,
            price_estimated=estimated,
            ticker_guessed=not h.ticker_shown,
            confidence=h.confidence,
            status=status,
            message=message,
            current_quantity=current,
            diff=diff,
            delta_quantity=delta_qty,
            delta_price=delta_price,
        )

    def _resolve(
        self, h: ExtractedHolding, asset_type: AssetType
    ) -> tuple[str | None, RowStatus, str | None, float | None]:
        """The symbol, its status, a message for the user, and its current USD price."""
        if not h.ticker:
            return None, "unknown", "티커를 알 수 없습니다. 직접 입력하세요", None
        try:
            # Trust the asset type read from the screenshot: "DOGE" listed as a coin must not
            # fall through to a same-named stock ticker.
            symbol = normalize_symbol(asset_type, h.ticker)
        except UnsupportedSymbolError:
            if asset_type == AssetType.CRYPTO:
                return None, "unsupported", "지원하는 코인은 BTC, ETH, XRP, SOL입니다", None
            return None, "unknown", f"'{h.ticker}'는 올바른 티커가 아닙니다", None
        try:
            quote = self.market.get_quote(symbol)
        except SymbolNotFoundError:
            return symbol, "unknown", f"{symbol} 시세를 찾을 수 없습니다", None
        return symbol, "ok", None, quote.price
