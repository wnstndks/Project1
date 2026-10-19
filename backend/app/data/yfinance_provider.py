"""The only module allowed to import yfinance.

yfinance is an unofficial scraper of Yahoo Finance and can break or be rate limited,
so every failure is converted to MarketDataError at this boundary.
"""

from datetime import date, datetime, timedelta

import pandas as pd
import yfinance as yf

from app.data.provider import Bar, MarketDataError, Quote


class YFinanceProvider:
    def get_history(self, symbol: str, start: date, end: date) -> list[Bar]:
        # yfinance treats `end` as exclusive.
        df = self._download(symbol, start=start, end=end + timedelta(days=1))
        return [
            Bar(
                date=ts.date(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                adj_close=float(row["Adj Close"]),
                volume=float(row["Volume"]),
            )
            for ts, row in df.iterrows()
            if start <= ts.date() <= end and not pd.isna(row["Close"])
        ]

    def get_quote(self, symbol: str) -> Quote | None:
        # The last daily bar is the in-progress session while the market is open.
        df = self._download(symbol, period="5d")
        df = df.dropna(subset=["Close"])
        if df.empty:
            return None
        ts = df.index[-1]
        return Quote(symbol=symbol, price=float(df["Close"].iloc[-1]), as_of=_to_datetime(ts))

    @staticmethod
    def _download(symbol: str, **kwargs) -> pd.DataFrame:
        try:
            return yf.Ticker(symbol).history(interval="1d", auto_adjust=False, **kwargs)
        except Exception as exc:  # yfinance raises many unrelated exception types
            raise MarketDataError(f"yfinance request failed for {symbol}: {exc}") from exc


def _to_datetime(ts: pd.Timestamp) -> datetime:
    return ts.to_pydatetime().replace(tzinfo=None)
