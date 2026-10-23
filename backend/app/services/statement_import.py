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
from app.services.transactions import IMPORT_NOTE, TransactionService

MAX_IMAGES = 5
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp"}
# Average cost / current price outside this range cannot be a real holding. Long-held winners
# reach 0.005 (NVDA bought in 2016) and big losers 50+, so the band is wide.
PRICE_SANITY = (Decimal("0.001"), Decimal("1000"))
# Inside that band, a unit price 20x away from the current price is still rarely a real
# holding: vision models read the return (%), the P&L or another column as the price. Such rows
# stay `ok` with a `warning` so the user can type the right price (the frontend leaves them
# unselected by default). Same threshold as SUSPICIOUS_COST_RATIO in frontend/src/lib/holdings.ts.
SUSPICIOUS_RATIO = Decimal("20")
# A unit price within this fraction of the displayed return (%) is the return itself.
RETURN_MATCH_TOLERANCE = Decimal("0.02")
# A dollar price and a won cost agree when the purchase rate they imply is within this fraction
# of today's USD/KRW. The rate has stayed between roughly 900 and 1,600 won since 1998, so a
# correct pair always lands inside; a column read as the price lands 10x or more outside.
FX_DRIFT_TOLERANCE = Decimal("0.5")
# Won rows have no exchange rate in between: cost / quantity must match the won price closely.
DERIVED_PRICE_TOLERANCE = Decimal("0.05")
# Purchase rates outside this band are misread numbers, not rates anyone paid.
IMPLIED_FX_BAND = (Decimal("500"), Decimal("3000"))

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
    # Won cost: read off the screen (매입금액), or derived from the market value and the P&L or
    # return when a list view shows those instead.
    cost_krw: Decimal | None
    # USD/KRW actually paid, implied by the KRW cost and the USD average price (USD rows).
    implied_fx: Decimal | None
    # True when the price was not shown (or looked like another column) and was computed from
    # cost_krw and the quantity, at today's rate for USD rows. `message` then says so.
    price_estimated: bool
    # True when the ticker was inferred from the name rather than printed on screen.
    ticker_guessed: bool
    confidence: str
    status: RowStatus
    message: str | None
    # A doubt about the unit price that is not certain enough to reject the row (see
    # SUSPICIOUS_RATIO). Only set on `ok` rows; the frontend leaves such rows unselected.
    warning: str | None
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


_NEGATIVE_MARKS = ("-", "−", "–", "▼", "▽")
_POSITIVE_MARKS = ("+", "▲", "△")


def _sign_mark(text: str) -> int:
    """-1, +1 or 0 for the sign marks in a piece of text around a number."""
    if any(mark in text for mark in _NEGATIVE_MARKS):
        return -1
    if any(mark in text for mark in _POSITIVE_MARKS):
        return 1
    return 0


def _signed_decimal(raw: str | None) -> Decimal | None:
    """Parse a signed number like "-123,456원", "−7.89%", "+54,000" or "3.2%▼"; zero is
    allowed. Broker apps put the sign before the number or an arrow after it; a mark
    before the number wins when the two disagree."""
    if raw is None:
        return None
    cleaned = re.sub(r"[^\d.]", "", raw)
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    digits = list(re.finditer(r"\d", raw))
    prefix, suffix = raw[: digits[0].start()], raw[digits[-1].end() :]
    sign = _sign_mark(prefix) or _sign_mark(suffix)
    return -value if sign < 0 else value


def _derive_cost_krw(
    value: Decimal | None, pnl: Decimal | None, pct: Decimal | None
) -> tuple[Decimal, str] | None:
    """The won purchase cost implied by what list views show instead of it, with the words
    for the message: market value - P&L, market value / (1 + return), or P&L / return."""
    if value is not None and pnl is not None:
        cost, how = value - pnl, "평가금액과 평가손익으로"
    elif value is not None and pct is not None and pct > -100:
        cost, how = value / (1 + pct / 100), "평가금액과 수익률로"
    elif pnl is not None and pct:
        cost, how = pnl / (pct / 100), "평가손익과 수익률로"
    else:
        return None
    return (cost.quantize(Decimal("1"), ROUND_HALF_UP), how) if cost > 0 else None


def _in_currency(market_usd: Decimal, currency: Currency, fx: Decimal) -> Decimal:
    """The current USD price expressed in the row's trade currency."""
    return market_usd * (fx if currency == Currency.KRW else 1)


def _misread_price(
    avg: Decimal, qty: Decimal, market_usd: Decimal, currency: Currency, fx: Decimal
) -> str | None:
    """Recognize the ways vision models misread the unit price: a won amount in the dollar
    field, or the position total instead of the per-unit price."""
    now = _in_currency(market_usd, currency, fx)
    ratio = avg / now

    def near(target: Decimal) -> bool:
        # Small targets would flag ordinary losers: 3 shares of a stock that fell by two
        # thirds look like a total of 3 units. Only 20x and beyond is clearly a misread.
        return target >= 20 and Decimal("0.8") <= ratio / target <= Decimal("1.25")

    candidates = [(qty, avg / qty, "보유 총액")]
    if currency == Currency.USD:
        candidates = [
            (fx * qty, avg / fx / qty, "원화 총액"),
            (fx, avg / fx, "원화 금액"),
            *candidates,
        ]
    unit = "₩" if currency == Currency.KRW else "$"
    for target, fixed, what in candidates:
        if near(target):
            return (
                f"{what}을 단가로 읽은 것 같습니다(현재가 {unit}{now:,.2f}). "
                f"단가는 약 {unit}{fixed:,.2f}일 수 있으니 확인하세요"
            )
    if not PRICE_SANITY[0] <= ratio <= PRICE_SANITY[1]:
        return f"평균단가가 현재가({unit}{now:,.2f})와 너무 다릅니다. 단가를 확인하세요"
    return None


def _price_doubt(
    avg: Decimal, now: Decimal, currency: Currency, return_pct: str | None
) -> tuple[str, str] | None:
    """Why the unit price read off the screen looks like another column: (what it looks
    like, message for the user). Plausible enough to leave the row `ok`, unlike
    `_misread_price`.

    Two signs: the price equals the displayed return (%), or it is SUSPICIOUS_RATIO away from
    the current price. A won cost that agrees with the price clears the doubt (see `_row`).
    """
    unit = "₩" if currency == Currency.KRW else "$"
    pct = _decimal(return_pct)
    ratio = avg / now
    if (
        return_pct is not None
        and pct is not None
        and abs(avg - pct) <= pct * RETURN_MATCH_TOLERANCE
    ):
        shown = return_pct.strip() if "%" in return_pct else f"{return_pct.strip()}%"
        return "수익률", (
            f"수익률({shown})을 단가로 읽은 것 같습니다(현재가 {unit}{now:,.2f}). "
            "매수가를 직접 확인하세요"
        )
    if ratio >= SUSPICIOUS_RATIO or ratio <= 1 / SUSPICIOUS_RATIO:
        times = max(ratio, 1 / ratio).quantize(Decimal("1"), ROUND_HALF_UP)
        return "다른 숫자", (
            f"평균단가 {unit}{avg:,.2f}이 현재가 {unit}{now:,.2f}과 {times}배 차이 납니다. "
            "수익률이나 다른 숫자를 단가로 읽었을 수 있으니 매수가를 직접 확인하세요"
        )
    return None


def _cost_agrees(read_avg: Decimal, cost_avg: Decimal, currency: Currency) -> bool:
    """Whether the price read off the screen and the one implied by the won cost describe the
    same purchase. Dollar rows get room for the exchange rate paid; won rows almost none."""
    tolerance = FX_DRIFT_TOLERANCE if currency == Currency.USD else DERIVED_PRICE_TOLERANCE
    return abs(cost_avg / read_avg - 1) <= tolerance


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
        asset_type = AssetType(h.asset_type)

        # Coins on Korean exchanges are bought in won: keep them in KRW (exact won cost).
        krw_coin = asset_type == AssetType.CRYPTO and (avg_krw is not None or avg_usd is None)
        currency = Currency.KRW if krw_coin else Currency.USD
        read_avg = avg_krw if krw_coin else avg_usd
        unit = "₩" if krw_coin else "$"
        # Won per unit of the trade currency, and the precision of a derived unit price.
        fx = Decimal(1) if krw_coin else fx_today
        places = Decimal("0.01") if krw_coin else Decimal("0.0001")
        fx_note = "" if krw_coin else "(오늘 환율 기준)"

        # The won cost: read off the screen (매입금액), else derived from what list views show
        # instead of it. From it, the unit price the cost implies at today's rate.
        cost_krw, cost_how = _decimal(h.cost_krw), "매입금액과 수량으로"
        if cost_krw is None:
            derived = _derive_cost_krw(
                _decimal(h.market_value_krw),
                _signed_decimal(h.pnl_krw),
                _signed_decimal(h.return_pct),
            )
            if derived is not None:
                cost_krw, cost_how = derived
        cost_avg = None
        if cost_krw is not None and qty:
            cost_avg = (cost_krw / qty / fx).quantize(places, ROUND_HALF_UP)

        symbol, status, message, market = self._resolve(h, asset_type)
        if status == "ok" and (qty is None or (read_avg is None and cost_avg is None)):
            status, message = "invalid", "수량 또는 평균단가를 읽지 못했습니다"

        # Is the price read off the screen a different column? Certain misreads reject the
        # row; plausible ones become a doubt that the won cost may clear or confirm below.
        doubt = None
        if status == "ok" and read_avg is not None:
            market_usd = Decimal(str(market))
            misread = _misread_price(read_avg, qty, market_usd, currency, fx_today)
            if misread:
                status, message = "invalid", misread
            else:
                now = _in_currency(market_usd, currency, fx_today)
                doubt = _price_doubt(read_avg, now, currency, h.return_pct)

        avg = read_avg
        estimated = False
        implied_fx = None
        warning = None
        if status == "ok" and cost_avg is not None:
            if read_avg is None:
                avg, estimated = cost_avg, True
                message = f"화면에 평균단가가 없어 {cost_how} 계산한 단가입니다{fx_note}"
            elif _cost_agrees(read_avg, cost_avg, currency):
                # Two independent numbers agree: even a 100x winner is real.
                doubt = None
            elif doubt is not None:
                # The price looked like another column and the cost says it is one.
                avg, estimated = cost_avg, True
                message = (
                    f"화면의 단가 {unit}{read_avg:,.2f}은 {doubt[0]}로 보여 쓰지 않고, "
                    f"{cost_how} 계산한 단가를 넣었습니다{fx_note}"
                )
                doubt = None
            else:
                off = (abs(cost_avg / read_avg - 1) * 100).quantize(Decimal("1"), ROUND_HALF_UP)
                warning = (
                    f"평균단가 {unit}{read_avg:,.2f}이 {cost_how} 계산한 단가 "
                    f"{unit}{cost_avg:,.2f}과 {off}% 다릅니다. "
                    "둘 중 하나를 잘못 읽었을 수 있으니 확인하세요"
                )
            if not estimated and currency == Currency.USD:
                # The rate actually paid, implied by the won cost and the dollar price.
                implied_fx = (cost_krw / (qty * read_avg)).quantize(Decimal("0.01"), ROUND_HALF_UP)
                if not IMPLIED_FX_BAND[0] <= implied_fx <= IMPLIED_FX_BAND[1]:
                    implied_fx = None
        if doubt is not None:
            warning = doubt[1]

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
            warning=warning,
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
