"""Out-of-sample metrics, always reported next to naive baselines."""

import numpy as np


def price_path(base_close: np.ndarray, cum_log_returns: np.ndarray) -> np.ndarray:
    """(n,) base prices and (n, horizon) cumulative log returns -> (n, horizon) prices."""
    return base_close[:, None] * np.exp(cum_log_returns)


def _errors(actual: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    err = pred - actual
    return {
        "mae": float(np.mean(np.abs(err))),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "mape": float(np.mean(np.abs(err) / actual) * 100),
    }


def evaluate(
    base_close: np.ndarray,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    train_up_ratio: float,
) -> dict:
    """Compare the model against two baselines on the test split.

    - naive: tomorrow's price equals today's close (zero return). The hardest baseline
      for price error metrics on a random-walk-like series.
    - majority direction: always predict the direction most common in the training data.
    """
    actual = price_path(base_close, y_true)
    pred = price_path(base_close, y_pred)
    naive = np.repeat(base_close[:, None], y_true.shape[1], axis=1)
    majority_up = train_up_ratio >= 0.5

    by_horizon = []
    for h in range(y_true.shape[1]):
        true_up = y_true[:, h] > 0
        by_horizon.append(
            {
                "day": h + 1,
                "model": _errors(actual[:, h], pred[:, h])
                | {"direction_acc": float(np.mean((y_pred[:, h] > 0) == true_up) * 100)},
                "baseline": _errors(actual[:, h], naive[:, h])
                | {"direction_acc": float(np.mean(true_up == majority_up) * 100)},
            }
        )
    return {"samples": int(len(base_close)), "by_horizon": by_horizon}
