"""Train and evaluate the pooled forecaster, then save it with its report.

    py -m uv run python -m app.forecast.train            # holdings + reference universe
    py -m uv run python -m app.forecast.train --engine sklearn

For each horizon: purged walk-forward out-of-sample predictions for every model, scores
against the baselines, the edge verdicts (Holm-corrected across all comparisons), and
final models refitted on all data with conformal offsets from the last year of
out-of-sample errors.
"""

import argparse
import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.forecast import report as rep
from app.forecast import store
from app.forecast.cv import PurgedWalkForward
from app.forecast.data import Inputs
from app.forecast.models import Climatology, EwmaStudentT, PooledGBDT
from app.forecast.panel import HORIZON_DAYS, HORIZONS, build_panel, feature_columns
from app.forecast.walkforward import calibration_window, conformal_offsets, walk_forward

MODEL_NAMES = ("climatology", "ewma_t", "gbdt")
# (comparison key, candidate, baseline, metric)
COMPARISONS = (
    ("direction", "gbdt", "climatology", "brier"),
    ("range", "gbdt", "ewma_t", "interval"),
)


def factories(features: list[str], engine: str, n_estimators: int = 300) -> dict:
    return {
        "climatology": Climatology,
        "ewma_t": EwmaStudentT,
        "gbdt": lambda: PooledGBDT(features, engine=engine, n_estimators=n_estimators),
    }


def config_hash(features: list[str], engine: str, cv: dict) -> str:
    raw = json.dumps({"features": features, "engine": engine, "cv": cv}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def train(
    inputs: Inputs,
    held: list[str],
    artifacts_dir: Path,
    engine: str = "auto",
    horizons: tuple[str, ...] = tuple(HORIZONS),
    log: Callable[[str], None] = print,
    cv_options: dict | None = None,
    n_estimators: int = 300,
) -> Path:
    log(f"Building panel: {len(inputs.assets)} assets")
    panel = build_panel(inputs.assets, inputs.context, inputs.benchmarks)
    features = feature_columns(panel)
    make = factories(features, engine, n_estimators)
    engine_used = PooledGBDT(features, engine=engine).engine

    comparisons: dict[str, rep.Comparison] = {}
    scores: dict[str, dict] = {}
    models: dict[str, dict] = {}
    offsets: dict[str, dict] = {}
    backtests: dict[str, pd.DataFrame] = {}
    cv_config = {}
    for h in horizons:
        cv = PurgedWalkForward(horizon_days=HORIZON_DAYS[h], **(cv_options or {}))
        cv_config[h] = asdict(cv)
        lags = HORIZON_DAYS[h]
        log(f"[{h}] walk-forward")
        oos = walk_forward(panel, h, make, cv)
        if oos.empty:
            log(f"[{h}] not enough history, skipped")
            continue
        scores[h] = {
            seg: {m: rep.to_dict(rep.score(g, m, lags)) for m in MODEL_NAMES}
            for seg, g in oos.groupby("segment")
        }
        for key, model, baseline, metric in COMPARISONS:
            comparisons[f"{h}:{key}"] = rep.compare(oos, model, baseline, metric, lags)

        log(f"[{h}] final fit")
        target = f"y_{h}"
        train_rows = panel[panel[target].notna()]
        models[h] = {}
        for name, factory in make.items():
            m = factory()
            m.fit(train_rows, target)
            models[h][name] = m
        recent = calibration_window(oos, oos["date"].max() + cv.gap, cv.gap)
        offsets[h] = {name: conformal_offsets(recent, name) for name in MODEL_NAMES}
        backtests[h] = oos[oos["symbol"].isin(held)]

    rep.verdicts(comparisons)
    report = {
        "horizons": {
            h: {
                "scores": scores[h],
                "comparisons": {
                    key: rep.to_dict(comparisons[f"{h}:{key}"]) for key, *_ in COMPARISONS
                },
            }
            for h in scores
        },
        "comparisons_tried": len(comparisons),
        "configs_tried": rep.CONFIGS_TRIED,
    }
    meta = {
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "data_end": str(inputs.data_end),
        "engine": engine_used,
        "config_hash": config_hash(features, engine_used, cv_config),
        "features": features,
        "universe": sorted(inputs.assets),
        "missing": inputs.missing,
        "held": held,
        "rows": len(panel),
    }
    run = store.save(artifacts_dir, meta, report, models, offsets, backtests)
    log(f"Saved to {run}")
    return run


def _print(report: dict) -> None:
    for h, r in report["horizons"].items():
        print(f"\n== {h} ==")
        for seg, by_model in r["scores"].items():
            print(f"  {seg}")
            for m, s in by_model.items():
                print(
                    f"    {m:<12} loss {s['interval_loss']:.4f}  cover {s['coverage']:.3f}"
                    f"  brier {s['brier']:.4f}  hit {s['hit_rate']:.3f}  ic {s['ic'] or 0:.3f}"
                )
        for key, c in r["comparisons"].items():
            print(
                f"  {key:<9} DM {c['dm_stat']:+.2f} p(adj) {c['p_adjusted']:.3f}"
                f"  years {c['year_share']:.2f}  holdout p {c['holdout_p_value']:.3f}"
                f"  -> {'EDGE' if c['edge'] else 'no edge'}"
            )


def main() -> None:
    from app.config import get_settings
    from app.db.session import SessionLocal
    from app.deps import get_provider, get_quote_cache
    from app.forecast.data import load_inputs
    from app.services.forecasts import held_symbols
    from app.services.market_data import MarketDataService

    parser = argparse.ArgumentParser(description="Train the pooled forecaster")
    parser.add_argument("--engine", choices=["auto", "lightgbm", "sklearn"], default="auto")
    args = parser.parse_args()

    with SessionLocal() as db:
        market = MarketDataService(db, get_provider(), get_quote_cache())
        held = held_symbols(db)
        inputs = load_inputs(market, held)
    run = train(inputs, [s for s, _ in held], get_settings().artifacts_dir, engine=args.engine)
    _print(store.load(run).report)


if __name__ == "__main__":
    main()
