"""Out-of-sample predictions from purged walk-forward folds, with conformal calibration.

Each fold trains every forecaster on data before the fold (minus the purge gap) and
predicts the fold. Before a fold's intervals are used they are calibrated on earlier
out-of-sample errors (conformalized quantile regression): if the raw 10-90% range missed
30% of the time last year, it is widened until it would have missed 20%.
"""

from collections.abc import Callable, Mapping

import numpy as np
import pandas as pd

from app.forecast.cv import Fold, PurgedWalkForward
from app.forecast.models import Forecaster

COVERAGE = 0.8
CALIBRATION_DAYS = 365
MIN_CALIBRATION_ROWS = 50
ForecasterFactory = Callable[[], Forecaster]


def conformal_offsets(calibration: pd.DataFrame, model: str) -> dict[str, float]:
    """Per asset class, how far to move q10 down and q90 up (negative narrows)."""
    out = {}
    for cls, g in calibration.groupby("asset_class"):
        g = g.dropna(subset=["y", f"{model}_q10", f"{model}_q90"])
        n = len(g)
        if n < MIN_CALIBRATION_ROWS:
            continue
        scores = np.maximum(g[f"{model}_q10"] - g["y"], g["y"] - g[f"{model}_q90"])
        level = min(1.0, np.ceil((n + 1) * COVERAGE) / n)
        out[cls] = float(np.quantile(scores, level))
    return out


def apply_offsets(
    pred: pd.DataFrame, offsets: Mapping[str, float], classes: pd.Series
) -> pd.DataFrame:
    pred = pred.copy()
    shift = classes.map(offsets).fillna(0.0).to_numpy()
    pred["q10"] = np.minimum(pred["q10"] - shift, pred["q50"])
    pred["q90"] = np.maximum(pred["q90"] + shift, pred["q50"])
    return pred


def calibration_window(oos: pd.DataFrame, before: pd.Timestamp, gap: pd.Timedelta) -> pd.DataFrame:
    """Earlier out-of-sample rows whose targets were fully known by `before`."""
    if oos.empty:
        return oos
    known = before - gap
    return oos[(oos["date"] < known) & (oos["date"] >= known - pd.Timedelta(days=CALIBRATION_DAYS))]


def _run_fold(
    panel: pd.DataFrame,
    fold: Fold,
    horizon: str,
    factories: Mapping[str, ForecasterFactory],
    history: pd.DataFrame,
    gap: pd.Timedelta,
) -> pd.DataFrame:
    target = f"y_{horizon}"
    train = panel[(panel["date"] < fold.train_end) & panel[target].notna()]
    test = panel[(panel["date"] >= fold.test_start) & (panel["date"] < fold.test_end)]
    test = test[test[target].notna()]
    if train.empty or test.empty:
        return pd.DataFrame()
    out = test[["date", "symbol", "asset_class"]].copy()
    out["y"] = test[target]
    out["fr"] = test[f"fr_{horizon}"]
    out["scale"] = test[f"scale_{horizon}"]
    calib = calibration_window(history, fold.test_start, gap)
    for name, make in factories.items():
        model = make()
        model.fit(train, target)
        pred = model.predict(test)
        if not calib.empty:
            pred = apply_offsets(pred, conformal_offsets(calib, name), test["asset_class"])
        for col in pred.columns:
            out[f"{name}_{col}"] = pred[col].to_numpy()
    return out


def walk_forward(
    panel: pd.DataFrame,
    horizon: str,
    factories: Mapping[str, ForecasterFactory],
    cv: PurgedWalkForward,
) -> pd.DataFrame:
    """Out-of-sample rows for every walk-forward fold, then the holdout ('segment')."""
    parts: list[pd.DataFrame] = []
    history = pd.DataFrame()
    for fold in cv.folds(panel["date"]):
        part = _run_fold(panel, fold, horizon, factories, history, cv.gap)
        if part.empty:
            continue
        part["segment"] = "walk_forward"
        parts.append(part)
        history = pd.concat(parts, ignore_index=True)
    part = _run_fold(panel, cv.holdout(panel["date"]), horizon, factories, history, cv.gap)
    if not part.empty:
        part["segment"] = "holdout"
        parts.append(part)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
