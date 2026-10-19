"""Windowing, chronological splitting and train-only scaling."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.ml.features import FEATURES, WARMUP, add_features, add_targets


@dataclass(frozen=True)
class Scaler:
    """Standardization fitted on the training split only."""

    mean: np.ndarray
    std: np.ndarray

    @classmethod
    def fit(cls, x: np.ndarray) -> "Scaler":
        std = x.std(axis=0)
        return cls(mean=x.mean(axis=0), std=np.where(std < 1e-12, 1.0, std))

    def transform(self, x: np.ndarray) -> np.ndarray:
        return (x - self.mean) / self.std

    def inverse(self, x: np.ndarray) -> np.ndarray:
        return x * self.std + self.mean

    def to_dict(self) -> dict:
        return {"mean": self.mean.tolist(), "std": self.std.tolist()}

    @classmethod
    def from_dict(cls, d: dict) -> "Scaler":
        return cls(mean=np.asarray(d["mean"]), std=np.asarray(d["std"]))


@dataclass
class Split:
    x: np.ndarray  # (n, lookback, features), scaled
    y: np.ndarray  # (n, horizon), scaled
    y_raw: np.ndarray  # (n, horizon) cumulative log returns
    dates: np.ndarray  # date of the last input row of each window
    base_close: np.ndarray  # close on that date, the price the forecast starts from


@dataclass
class PreparedData:
    train: Split
    val: Split
    test: Split
    x_scaler: Scaler
    y_scaler: Scaler


def feature_frame(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Features plus targets, without the warm-up rows. The last `horizon` rows have NaN targets."""
    frame = add_features(df).join(add_targets(df, horizon))
    frame["close"] = df["close"]
    return frame.iloc[WARMUP:]


def split_bounds(n: int, lookback: int, horizon: int, val_frac: float, test_frac: float):
    """Window end indices for each split, purged so no target overlaps the next split.

    A window ending at row t has targets reaching t + horizon. Dropping the last `horizon`
    windows of train and validation keeps every train target strictly before validation data.
    """
    ends = np.arange(lookback - 1, n - horizon)
    n_test = int(len(ends) * test_frac)
    n_val = int(len(ends) * val_frac)
    n_train = len(ends) - n_val - n_test
    if n_train - horizon < 50 or n_val - horizon < 10 or n_test < 10:
        raise ValueError(f"Not enough history to train: only {len(ends)} usable windows")
    train = ends[: n_train - horizon]
    val = ends[n_train : n_train + n_val - horizon]
    test = ends[n_train + n_val :]
    return train, val, test


def prepare(
    df: pd.DataFrame,
    lookback: int,
    horizon: int,
    val_frac: float = 0.15,
    test_frac: float = 0.15,
) -> PreparedData:
    frame = feature_frame(df, horizon)
    x_all = frame[FEATURES].to_numpy(dtype=np.float64)
    y_all = frame[[f"y_{k}" for k in range(1, horizon + 1)]].to_numpy(dtype=np.float64)
    train_ends, val_ends, test_ends = split_bounds(
        len(frame), lookback, horizon, val_frac, test_frac
    )

    # Fit scalers only on rows the training windows can see.
    last_train_row = train_ends[-1]
    x_scaler = Scaler.fit(x_all[: last_train_row + 1])
    y_scaler = Scaler.fit(y_all[train_ends])
    x_scaled = x_scaler.transform(x_all)

    def make(ends: np.ndarray) -> Split:
        idx = ends[:, None] + np.arange(-lookback + 1, 1)[None, :]
        return Split(
            x=x_scaled[idx].astype(np.float32),
            y=y_scaler.transform(y_all[ends]).astype(np.float32),
            y_raw=y_all[ends],
            dates=frame.index.to_numpy()[ends],
            base_close=frame["close"].to_numpy()[ends],
        )

    return PreparedData(make(train_ends), make(val_ends), make(test_ends), x_scaler, y_scaler)


def latest_window(df: pd.DataFrame, lookback: int, horizon: int, x_scaler: Scaler) -> np.ndarray:
    """The most recent `lookback` feature rows, scaled, shaped (1, lookback, features)."""
    frame = feature_frame(df, horizon)
    if len(frame) < lookback:
        raise ValueError(f"Need {lookback} rows after warm-up, have {len(frame)}")
    x = frame[FEATURES].to_numpy(dtype=np.float64)[-lookback:]
    return x_scaler.transform(x)[None].astype(np.float32)
