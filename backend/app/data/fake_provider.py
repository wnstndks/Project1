"""Deterministic offline provider for tests, CI and demos without network access."""

import hashlib
import math
import random
from datetime import date, datetime, timedelta

from app.data.assets import CRYPTO_ASSETS, FX_USDKRW, trades_every_day
from app.data.provider import Bar, CorporateEvent, Quote

_BASE_PRICES = {
    "BTC-USD": 60000.0,
    "ETH-USD": 3000.0,
    "XRP-USD": 0.6,
    "SOL-USD": 150.0,
    FX_USDKRW: 1350.0,
    # Upbit KRW markets, roughly USD price x 1350 plus a small premium.
    "KRW-BTC": 82_000_000.0,
    "KRW-ETH": 4_100_000.0,
    "KRW-XRP": 820.0,
    "KRW-SOL": 205_000.0,
}
_EPOCH = date(2015, 1, 1)


class FakeProvider:
    """Geometric random walk seeded per symbol, so the same symbol and day give the same bar.

    Symbols listed in `unknown` behave like tickers the provider has never heard of.
    """

    def __init__(
        self,
        today: date | None = None,
        unknown: set[str] | None = None,
        actions: dict[str, list[CorporateEvent]] | None = None,
    ) -> None:
        self.today = today or date.today()
        self.unknown = unknown or set()
        self.actions = actions or {}
        self.history_calls: list[tuple[str, date, date]] = []

    def get_history(self, symbol: str, start: date, end: date) -> list[Bar]:
        self.history_calls.append((symbol, start, end))
        if symbol in self.unknown:
            return []
        end = min(end, self.today)
        return [b for b in self._series(symbol, end) if b.date >= start]

    def get_quote(self, symbol: str) -> Quote | None:
        if symbol in self.unknown:
            return None
        last = self._series(symbol, self.today)[-1]
        return Quote(
            symbol=symbol, price=last.close, as_of=datetime.combine(last.date, datetime.min.time())
        )

    def get_name(self, symbol: str) -> str | None:
        return None if symbol in self.unknown else f"{symbol} Inc."

    def get_actions(self, symbol: str) -> list[CorporateEvent]:
        return list(self.actions.get(symbol, []))

    def _series(self, symbol: str, end: date) -> list[Bar]:
        seed = int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        crypto = symbol in CRYPTO_ASSETS or symbol.startswith("KRW-")
        vol = 0.035 if crypto else 0.015
        drift = 0.0006 if crypto else 0.0003
        price = _BASE_PRICES.get(symbol, 50.0 + seed % 300)
        every_day = trades_every_day(symbol) or symbol == FX_USDKRW

        bars: list[Bar] = []
        d = _EPOCH
        while d <= end:
            ret = rng.gauss(drift, vol)
            if every_day or d.weekday() < 5:
                open_ = price
                price = price * math.exp(ret)
                high = max(open_, price) * (1 + abs(rng.gauss(0, vol / 3)))
                low = min(open_, price) * (1 - abs(rng.gauss(0, vol / 3)))
                volume = float(rng.randint(1_000_000, 50_000_000))
                bars.append(Bar(d, open_, high, low, price, price, volume))
            d += timedelta(days=1)
        return bars
