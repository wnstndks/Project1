"""Feature engineering on daily bars.

Every feature at row t uses only data up to and including t. Targets at row t are the
cumulative log returns from t to t+1..t+horizon, so they look into the future by design
and must never be used as inputs.
"""

from collections.abc import Sequence
from typing import Protocol

import numpy as np
import pandas as pd

FEATURES = [
    "log_ret",
    "ma_ratio_5",
    "ma_ratio_20",
    "rsi_14",
    "volatility_20",
    "hl_range",
    "volume_change",
]
WARMUP = 20  # rows needed before every rolling feature is defined


class BarLike(Protocol):
    date: object
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    volume: float


def bars_to_frame(bars: Sequence[BarLike]) -> pd.DataFrame:
    df = pd.DataFrame(
        {
            "date": [b.date for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "adj_close": [b.adj_close for b in bars],
            "volume": [b.volume for b in bars],
        }
    )
    return df.set_index("date").sort_index()


def _rsi(price: pd.Series, period: int = 14) -> pd.Series:
    delta = price.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100.0) / 100.0


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    p = df["adj_close"]
    out = pd.DataFrame(index=df.index)
    out["log_ret"] = np.log(p).diff()
    out["ma_ratio_5"] = p / p.rolling(5).mean() - 1
    out["ma_ratio_20"] = p / p.rolling(20).mean() - 1
    out["rsi_14"] = _rsi(p)
    out["volatility_20"] = out["log_ret"].rolling(20).std()
    out["hl_range"] = (df["high"] - df["low"]) / df["close"]
    out["volume_change"] = np.log1p(df["volume"]).diff().replace([np.inf, -np.inf], 0.0)
    return out


def add_targets(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    log_p = np.log(df["adj_close"])
    return pd.DataFrame(
        {f"y_{k}": log_p.shift(-k) - log_p for k in range(1, horizon + 1)}, index=df.index
    )
