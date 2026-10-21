"""Train and evaluate the pooled forecaster, then save it with its report.

    py -m uv run python -m app.forecast.train            # holdings + reference universe
    py -m uv run python -m app.forecast.train --engine sklearn

For each horizon: purged walk-forward out-of-sample predictions for every model, scores
against the baselines, the edge verdicts (Holm-corrected across all comparisons), and
final models refitted on all data with conformal offsets from the last year of
out-of-sample errors.

Two out-of-sample files per horizon: `oos_{h}` holds the held symbols (what the forecast
screen shows), `oos_universe_{h}` every reference symbol whatever is held (the input of
strategy backtests, tagged with `universe_group`).
"""

import argparse
import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from app.forecast import cv as cvmod
from app.forecast import panel as pnl
from app.forecast import report as rep
from app.forecast import store, universe
from app.forecast.cv import PurgedWalkForward
from app.forecast.data import Inputs
from app.forecast.models import Climatology, EwmaStudentT, PooledGBDT
from app.forecast.panel import HORIZON_DAYS, HORIZONS, build_panel, feature_columns
from app.forecast.walkforward import calibration_window, conformal_offsets, walk_forward

MODEL_NAMES = ("climatology", "ewma_t", "gbdt")


def factories(features: list[str], engine: str, n_estimators: int = 300) -> dict:
    return {
        "climatology": Climatology,
        "ewma_t": EwmaStudentT,
        "gbdt": lambda: PooledGBDT(features, engine=engine, n_estimators=n_estimators),
    }


def run_config(
    features: list[str], model: PooledGBDT, cv: dict, context: list[pnl.ContextSeries]
) -> dict:
    """Every setting that changes what is learned or how it is scored (ISSUE-007).

    The universe is the designed reference list, not the symbols actually loaded: holdings
    and download failures change from run to run without anyone choosing a new setting.
    CONFIGS_TRIED is recorded next to this, never in it, so a changed hash under an
    unchanged counter can be caught.
    """
    return {
        "panel": {
            "version": pnl.PANEL_VERSION,
            "horizons": pnl.HORIZONS,
            "min_vol": pnl.MIN_VOL,
            "min_vol_days": pnl.MIN_VOL_DAYS,
            "min_rank_assets": pnl.MIN_RANK_ASSETS,
            "context_fill_days": pnl.CONTEXT_FILL_DAYS,
        },
        "features": features,
        "model": model.config(),
        "baselines": {"ewma_t_dof": EwmaStudentT.DOF},
        "cv": cv,
        "context": {c.name: {"kind": c.kind, "lag": dict(c.lag)} for c in context},
        "reference_universe": dict(sorted(universe.reference_symbols().items())),
    }


def config_hash(config: dict) -> str:
    raw = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def universe_oos(oos: pd.DataFrame) -> pd.DataFrame:
    """Out-of-sample rows of the reference symbols, tagged by what they may be used for:
    `strategy` (D-008), `large_cap` (hindsight list, reported separately) or
    `training_only`. Symbols only there because they are held are left out."""
    groups = universe.universe_groups()
    out = oos[oos["symbol"].isin(groups)].copy()
    out["universe_group"] = out["symbol"].map(groups)
    return out.reset_index(drop=True)


def train(
    inputs: Inputs,
    held: list[str],
    artifacts_dir: Path,
    engine: str = "auto",
    horizons: tuple[str, ...] = tuple(HORIZONS),
    log: Callable[[str], None] = print,
    cv_options: dict | None = None,
    n_estimators: int = 300,
    holdout_log: Path | None = None,
) -> Path:
    """`holdout_log`: where the look at the holdout is recorded (and refused when it was
    already scored for this configuration and data, or the counter was not raised). None
    records nothing (tests)."""
    log(f"Building panel: {len(inputs.assets)} assets")
    panel = build_panel(inputs.assets, inputs.context, inputs.benchmarks)
    features = feature_columns(panel)
    make = factories(features, engine, n_estimators)
    gbdt = PooledGBDT(features, engine=engine, n_estimators=n_estimators)
    cv_config = {
        h: asdict(PurgedWalkForward(horizon_days=HORIZON_DAYS[h], **(cv_options or {})))
        for h in horizons
    }
    config = run_config(features, gbdt, cv_config, list(inputs.context))
    digest = config_hash(config)
    log(f"Config {digest}, CONFIGS_TRIED={rep.CONFIGS_TRIED}")
    if holdout_log is not None:
        first = PurgedWalkForward(horizon_days=HORIZON_DAYS[horizons[0]], **(cv_options or {}))
        cvmod.open_holdout(
            "forecast",
            digest,
            holdout_start=str(first.holdout_start(panel["date"]).date()),
            data_end=str(inputs.data_end),
            configs_tried=rep.CONFIGS_TRIED,
            path=holdout_log,
        )

    comparisons: dict[str, rep.Comparison] = {}
    scores: dict[str, dict] = {}
    models: dict[str, dict] = {}
    offsets: dict[str, dict] = {}
    backtests: dict[str, pd.DataFrame] = {}
    universe_oos_by_h: dict[str, pd.DataFrame] = {}
    for h in horizons:
        cv = PurgedWalkForward(horizon_days=HORIZON_DAYS[h], **(cv_options or {}))
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
        # Rank comparisons only on the strategy universe (ISSUE-020); Holm runs over all
        # horizons together in `verdicts`.
        for key, c in rep.compare_all(oos, lags, universe.strategy_symbols()).items():
            comparisons[f"{h}:{key}"] = c

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
        universe_oos_by_h[h] = universe_oos(oos)

    rep.verdicts(comparisons)
    report = {
        "horizons": {
            h: {
                "scores": scores[h],
                "comparisons": {
                    k.split(":", 1)[1]: rep.to_dict(c)
                    for k, c in comparisons.items()
                    if k.startswith(f"{h}:")
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
        "engine": gbdt.engine,
        "config_hash": digest,
        "configs_tried": rep.CONFIGS_TRIED,
        "config": config,
        "features": features,
        # Every loaded symbol (held ones included): the peers of rank features at
        # inference, so ranks compare against the assets the model was trained with.
        "universe": sorted(inputs.assets),
        "missing": inputs.missing,
        "held": held,
        "rows": len(panel),
    }
    run = store.save(artifacts_dir, meta, report, models, offsets, backtests, universe_oos_by_h)
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
            # Values that could not be computed are saved as null.
            v = {k: (math.nan if x is None else x) for k, x in c.items()}
            print(
                f"  {key:<16} DM {v['dm_stat']:+.2f} p(adj) {v['p_adjusted']:.3f}"
                f"  years {v['year_share']:.2f}  holdout p {v['holdout_p_value']:.3f}"
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
    run = train(
        inputs,
        [s for s, _ in held],
        get_settings().artifacts_dir,
        engine=args.engine,
        holdout_log=cvmod.HOLDOUT_LOG,
    )
    _print(store.load(run).report)


if __name__ == "__main__":
    main()
