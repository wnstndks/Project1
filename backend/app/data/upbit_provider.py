"""Upbit (Korean exchange) public market data: KRW prices for the supported coins.

No API key is needed. Daily candles roll over at 00:00 UTC (09:00 KST), the same boundary
as yfinance's crypto bars.
"""

import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import httpx2 as httpx

from app.data.provider import Bar, CorporateEvent, MarketDataError, Quote

UPBIT_URL = "https://api.upbit.com/v1"
PAGE = 200  # Upbit's maximum candles per request


class UpbitProvider:
    def __init__(
        self, http: httpx.Client | None = None, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self.http = http or httpx.Client(timeout=20)
        self.sleep = sleep

    def get_history(self, symbol: str, start: date, end: date) -> list[Bar]:
        bars: dict[date, Bar] = {}
        cursor = end + timedelta(days=1)  # `to` is exclusive
        while cursor > start:
            rows = self._get(
                "/candles/days",
                {"market": symbol, "count": PAGE, "to": f"{cursor.isoformat()}T00:00:00"},
            )
            if not rows:
                break
            for r in rows:
                d = datetime.fromisoformat(r["candle_date_time_utc"]).date()
                if start <= d <= end:
                    bars[d] = Bar(
                        date=d,
                        open=float(r["opening_price"]),
                        high=float(r["high_price"]),
                        low=float(r["low_price"]),
                        close=float(r["trade_price"]),
                        adj_close=float(r["trade_price"]),
                        volume=float(r["candle_acc_trade_volume"]),
                    )
            oldest = min(datetime.fromisoformat(r["candle_date_time_utc"]).date() for r in rows)
            if len(rows) < PAGE or oldest <= start:
                break
            cursor = oldest
            self.sleep(0.15)  # Upbit allows about 10 candle requests per second
        return [bars[d] for d in sorted(bars)]

    def get_quote(self, symbol: str) -> Quote | None:
        rows = self._get("/ticker", {"markets": symbol}, missing_ok=True)
        if not rows:
            return None
        r = rows[0]
        as_of = datetime.fromtimestamp(r["trade_timestamp"] / 1000, tz=UTC).replace(tzinfo=None)
        return Quote(symbol=symbol, price=float(r["trade_price"]), as_of=as_of)

    def get_name(self, symbol: str) -> str | None:
        return None

    def get_actions(self, symbol: str) -> list[CorporateEvent]:
        return []

    def _get(self, path: str, params: dict, missing_ok: bool = False) -> list[dict]:
        try:
            res = self.http.get(UPBIT_URL + path, params=params)
        except httpx.HTTPError as exc:
            raise MarketDataError(f"Upbit request failed: {exc}") from exc
        if res.status_code == 404 and missing_ok:
            return []
        if res.status_code == 429:
            raise MarketDataError("Upbit rate limit reached; try again shortly")
        if res.status_code != 200:
            raise MarketDataError(f"Upbit error {res.status_code}: {res.text[:120]}")
        return res.json()


class RoutingProvider:
    """Sends Upbit market symbols ("KRW-BTC") to Upbit and everything else to the default."""

    def __init__(self, default, upbit) -> None:
        self.default = default
        self.upbit = upbit

    def _for(self, symbol: str):
        return self.upbit if symbol.startswith("KRW-") else self.default

    def get_history(self, symbol: str, start: date, end: date) -> list[Bar]:
        return self._for(symbol).get_history(symbol, start, end)

    def get_quote(self, symbol: str) -> Quote | None:
        return self._for(symbol).get_quote(symbol)

    def get_name(self, symbol: str) -> str | None:
        return self._for(symbol).get_name(symbol)

    def get_actions(self, symbol: str) -> list[CorporateEvent]:
        return self._for(symbol).get_actions(symbol)
