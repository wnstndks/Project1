"""Turn extracted screenshot holdings into reviewable rows, then into buy transactions."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal

from app.data.assets import UnsupportedSymbolError, normalize_symbol
from app.db.models import AssetType, Side, Transaction
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

RowStatus = Literal["ok", "unsupported", "unknown", "invalid"]
Diff = Literal["new", "same", "different"]


@dataclass
class PreviewRow:
    name: str
    symbol: str | None
    asset_type: AssetType
    quantity: Decimal | None
    avg_price_usd: Decimal | None
    cost_krw: Decimal | None
    # USD/KRW actually paid, implied by the KRW cost and the USD average price.
    implied_fx: Decimal | None
    # True when avg_price_usd was not shown and was derived from cost_krw at today's rate.
    price_estimated: bool
    confidence: str
    status: RowStatus
    message: str | None
    current_quantity: Decimal | None
    diff: Diff | None


@dataclass
class Preview:
    broker: str | None
    rows: list[PreviewRow]


@dataclass
class CommitRow:
    asset_type: AssetType
    symbol: str
    quantity: Decimal
    avg_price_usd: Decimal
    fx_rate: Decimal | None = None


def _decimal(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        value = Decimal(raw.replace(",", "").strip())
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
        for img in images:
            if img.media_type not in ALLOWED_TYPES:
                raise DomainError(f"Unsupported image type {img.media_type}; use PNG or JPEG")
            if len(img.data) > MAX_IMAGE_BYTES:
                raise DomainError("Each screenshot must be 10 MB or smaller")

        statement = self.extractor.extract(images)
        held = {h.symbol: h.quantity for h in self.portfolio.holdings()}
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
                    quantity=r.quantity,
                    price=r.avg_price_usd,
                    fx_rate=r.fx_rate,
                    note=IMPORT_NOTE,
                )
                for r in rows
            ]
        )

    def _row(self, h: ExtractedHolding, held: dict[str, Decimal], fx_today: Decimal) -> PreviewRow:
        qty = _decimal(h.quantity)
        avg_usd = _decimal(h.avg_price_usd)
        cost_krw = _decimal(h.cost_krw)
        asset_type = AssetType(h.asset_type)

        estimated = False
        if avg_usd is None and cost_krw is not None and qty:
            avg_usd = (cost_krw / qty / fx_today).quantize(Decimal("0.0001"), ROUND_HALF_UP)
            estimated = True
        implied_fx = None
        if cost_krw is not None and avg_usd is not None and qty and not estimated:
            implied_fx = (cost_krw / (qty * avg_usd)).quantize(Decimal("0.01"), ROUND_HALF_UP)
            # A wildly off rate means a misread number, not a real purchase rate.
            if not (Decimal("500") <= implied_fx <= Decimal("3000")):
                implied_fx = None

        symbol, status, message = self._resolve(h, asset_type)
        if status == "ok" and (qty is None or avg_usd is None):
            status, message = "invalid", "수량 또는 평균단가를 읽지 못했습니다"

        current = held.get(symbol) if symbol else None
        diff: Diff | None = None
        if symbol and qty is not None:
            diff = "new" if current is None else ("same" if current == qty else "different")

        return PreviewRow(
            name=h.name,
            symbol=symbol,
            asset_type=asset_type,
            quantity=qty,
            avg_price_usd=avg_usd,
            cost_krw=cost_krw,
            implied_fx=implied_fx,
            price_estimated=estimated,
            confidence=h.confidence,
            status=status,
            message=message,
            current_quantity=current,
            diff=diff,
        )

    def _resolve(
        self, h: ExtractedHolding, asset_type: AssetType
    ) -> tuple[str | None, RowStatus, str | None]:
        if not h.ticker:
            return None, "unknown", "티커를 알 수 없습니다. 직접 입력하세요"
        try:
            # Trust the asset type read from the screenshot: "DOGE" listed as a coin must not
            # fall through to a same-named stock ticker.
            symbol = normalize_symbol(asset_type, h.ticker)
        except UnsupportedSymbolError:
            if asset_type == AssetType.CRYPTO:
                return None, "unsupported", "지원하는 코인은 BTC, ETH, XRP, SOL입니다"
            return None, "unknown", f"'{h.ticker}'는 올바른 티커가 아닙니다"
        try:
            self.market.get_quote(symbol)
        except SymbolNotFoundError:
            return symbol, "unknown", f"{symbol} 시세를 찾을 수 없습니다"
        return symbol, "ok", None
