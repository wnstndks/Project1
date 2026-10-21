"""Forecasters: honest baselines and the pooled gradient-boosted model.

Every forecaster learns the standardized forward return y = fr / scale and predicts the
10/50/90% quantiles of y and the probability that y > 0. Quantiles are later multiplied by
the row's `scale` to become returns.
"""

from typing import Protocol

import numpy as np
import pandas as pd
from scipy import stats

QUANTILES = (0.1, 0.5, 0.9)
PRED_COLUMNS = ["q10", "q50", "q90", "p_up"]


class Forecaster(Protocol):
    name: str

    def fit(self, train: pd.DataFrame, target: str) -> None: ...

    def predict(self, rows: pd.DataFrame) -> pd.DataFrame:
        """Columns q10, q50, q90 (standardized) and p_up, aligned to `rows`."""
        ...


def _by_class(rows: pd.DataFrame, values: dict[str, np.ndarray], width: int) -> np.ndarray:
    out = np.full((len(rows), width), np.nan)
    for cls, v in values.items():
        out[(rows["asset_class"] == cls).to_numpy()] = v
    return out


class Climatology:
    """The long-run distribution of each asset class: no information about today."""

    name = "climatology"

    def fit(self, train: pd.DataFrame, target: str) -> None:
        self._values = {}
        for cls, g in train.dropna(subset=[target]).groupby("asset_class"):
            y = g[target].to_numpy()
            self._values[cls] = np.r_[np.quantile(y, QUANTILES), (y > 0).mean()]

    def predict(self, rows: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(
            _by_class(rows, self._values, 4), columns=PRED_COLUMNS, index=rows.index
        )


class EwmaStudentT:
    """Volatility-only baseline: median zero, spread from the EWMA volatility estimate
    with fat (Student-t, 5 dof) tails. The standard risk-desk forecast to beat."""

    name = "ewma_t"
    DOF = 5

    def fit(self, train: pd.DataFrame, target: str) -> None:
        self._scale = {}
        self._p_up = {}
        for cls, g in train.dropna(subset=[target, "ewma_ratio"]).groupby("asset_class"):
            ratio = g["ewma_ratio"].clip(lower=0.05)
            # How the standardized target relates to the EWMA/20-day vol ratio, in-sample.
            self._scale[cls] = float(np.std(g[target] / ratio))
            self._p_up[cls] = float((g[target] > 0).mean())

    def predict(self, rows: pd.DataFrame) -> pd.DataFrame:
        unit_t = stats.t.ppf(QUANTILES, self.DOF) * np.sqrt((self.DOF - 2) / self.DOF)
        out = np.full((len(rows), 4), np.nan)
        ratio = rows["ewma_ratio"].clip(lower=0.05).fillna(1.0).to_numpy()
        for cls, s in self._scale.items():
            m = (rows["asset_class"] == cls).to_numpy()
            out[m, :3] = np.outer(ratio[m] * s, unit_t)
            out[m, 3] = self._p_up[cls]
        return pd.DataFrame(out, columns=PRED_COLUMNS, index=rows.index)


class PooledGBDT:
    """One gradient-boosted model per quantile over all assets, plus a classifier for
    P(up). Heavily regularized: daily returns are mostly noise, and a flexible model
    fitted loosely memorizes it.

    With LightGBM (the `ml` dependency group) the number of trees is chosen by early
    stopping on the last fifth of the training dates, separated by a gap longer than any
    target, and the model is then refitted on all of them. scikit-learn's histogram GBDT,
    the fallback, uses a fixed number of trees (its early stopping splits at random,
    which would leak across time).
    """

    name = "gbdt"
    VALIDATION_SHARE = 0.2
    VALIDATION_GAP = pd.Timedelta(days=40)
    PATIENCE = 50
    MIN_TREES = 20
    # Per-engine settings; n_estimators is passed separately. Part of the config hash.
    LIGHTGBM_PARAMS = {
        "learning_rate": 0.02,
        "num_leaves": 15,
        "min_child_samples": 500,
        "subsample": 0.7,
        "subsample_freq": 1,
        "colsample_bytree": 0.7,
        "reg_lambda": 10.0,
        "random_state": 0,
    }
    SKLEARN_PARAMS = {
        "max_iter_cap": 300,
        "learning_rate": 0.05,
        "max_leaf_nodes": 15,
        "min_samples_leaf": 500,
        "l2_regularization": 10.0,
        "random_state": 0,
    }

    def __init__(self, features: list[str], engine: str = "auto", n_estimators: int = 1000) -> None:
        self.features = features
        self.n_estimators = n_estimators
        if engine == "auto":
            try:
                import lightgbm  # noqa: F401

                engine = "lightgbm"
            except ImportError:
                engine = "sklearn"
        self.engine = engine
        self.trees: dict[str, int] = {}

    def config(self) -> dict:
        """Everything that changes what this model learns, for the run's config hash."""
        out: dict = {
            "engine": self.engine,
            "n_estimators": self.n_estimators,
            "quantiles": list(QUANTILES),
        }
        if self.engine == "lightgbm":
            out["params"] = dict(self.LIGHTGBM_PARAMS)
            out["early_stopping"] = {
                "validation_share": self.VALIDATION_SHARE,
                "validation_gap_days": self.VALIDATION_GAP.days,
                "patience": self.PATIENCE,
                "min_trees": self.MIN_TREES,
            }
        else:
            out["params"] = dict(self.SKLEARN_PARAMS)
        return out

    def _model(self, kind: str, alpha: float = 0.5, n_estimators: int | None = None):
        n = n_estimators or self.n_estimators
        if self.engine == "lightgbm":
            import lightgbm as lgb

            common = dict(n_estimators=n, verbose=-1, n_jobs=4, **self.LIGHTGBM_PARAMS)
            if kind == "classifier":
                return lgb.LGBMClassifier(**common)
            return lgb.LGBMRegressor(objective="quantile", alpha=alpha, **common)
        from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

        params = dict(self.SKLEARN_PARAMS)
        common = dict(max_iter=min(n, params.pop("max_iter_cap")), **params)
        if kind == "classifier":
            return HistGradientBoostingClassifier(**common)
        return HistGradientBoostingRegressor(loss="quantile", quantile=alpha, **common)

    def _fit(self, key: str, kind: str, alpha: float, data: pd.DataFrame, y: np.ndarray):
        X = data[self.features]
        if self.engine != "lightgbm":
            return self._model(kind, alpha).fit(X, y)
        import lightgbm as lgb

        dates = np.sort(data["date"].unique())
        cut = pd.Timestamp(dates[int(len(dates) * (1 - self.VALIDATION_SHARE))])
        inner = (data["date"] < cut - self.VALIDATION_GAP).to_numpy()
        val = (data["date"] >= cut).to_numpy()
        trees = self.n_estimators
        if inner.sum() > 1000 and val.sum() > 1000:
            probe = self._model(kind, alpha).fit(
                X[inner],
                y[inner],
                eval_X=X[val],
                eval_y=y[val],
                callbacks=[lgb.early_stopping(self.PATIENCE, verbose=False)],
            )
            trees = max(probe.best_iteration_ or self.n_estimators, self.MIN_TREES)
        self.trees[key] = trees
        return self._model(kind, alpha, n_estimators=trees).fit(X, y)

    def fit(self, train: pd.DataFrame, target: str) -> None:
        data = train.dropna(subset=[target])
        y = data[target].to_numpy()
        self._quantile_models = [
            self._fit(f"q{int(a * 100)}", "regressor", a, data, y) for a in QUANTILES
        ]
        self._classifier_model = self._fit("p_up", "classifier", 0.5, data, (y > 0).astype(int))

    def predict(self, rows: pd.DataFrame) -> pd.DataFrame:
        X = rows[self.features]
        q = np.column_stack([m.predict(X) for m in self._quantile_models])
        q.sort(axis=1)  # quantile models are fitted separately and may cross
        p_up = self._classifier_model.predict_proba(X)[:, 1]
        return pd.DataFrame(np.column_stack([q, p_up]), columns=PRED_COLUMNS, index=rows.index)
