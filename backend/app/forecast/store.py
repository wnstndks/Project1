"""Trained forecaster runs on disk: artifacts/global/runs/{run_id}/ plus a current.json
pointer, written the same way as the per-symbol LSTM runs (immutable run directories,
atomically swapped pointer).

Models are pickled with joblib. Only files this app wrote are ever loaded, from its own
artifacts directory (excluded from git).
"""

import json
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd

GLOBAL = "global"


@dataclass
class Run:
    path: Path
    run_id: str
    meta: dict
    report: dict
    # horizon -> model name -> fitted forecaster
    models: dict
    # horizon -> model name -> asset class -> conformal offset
    offsets: dict

    def backtest(self, horizon: str) -> pd.DataFrame:
        path = self.path / f"oos_{horizon}.csv.gz"
        if not path.exists():
            return pd.DataFrame()
        return pd.read_csv(path, parse_dates=["date"])


def save(
    artifacts_dir: Path,
    meta: dict,
    report: dict,
    models: dict,
    offsets: dict,
    backtests: dict[str, pd.DataFrame],
) -> Path:
    base = artifacts_dir / GLOBAL
    run_id = f"{datetime.now():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
    run = base / "runs" / run_id
    run.mkdir(parents=True)
    joblib.dump({"models": models, "offsets": offsets}, run / "models.joblib")
    (run / "meta.json").write_text(json.dumps(meta, indent=2))
    (run / "report.json").write_text(json.dumps(report, indent=2))
    for horizon, df in backtests.items():
        df.to_csv(run / f"oos_{horizon}.csv.gz", index=False)
    pointer_tmp = base / f"current.json.{uuid.uuid4().hex}.tmp"
    pointer_tmp.write_text(json.dumps({"run": run_id}))
    os.replace(pointer_tmp, base / "current.json")
    _prune(base / "runs", keep=run_id)
    return run


def _prune(runs: Path, keep: str, retain: int = 3) -> None:
    old = sorted(p for p in runs.iterdir() if p.is_dir() and p.name != keep)
    for p in old[: max(0, len(old) - (retain - 1))]:
        shutil.rmtree(p, ignore_errors=True)


def resolve(artifacts_dir: Path) -> Path | None:
    base = artifacts_dir / GLOBAL
    try:
        run_id = json.loads((base / "current.json").read_text())["run"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None
    run = base / "runs" / run_id
    return run if (run / "models.joblib").exists() else None


def load(run: Path) -> Run:
    bundle = joblib.load(run / "models.joblib")
    return Run(
        path=run,
        run_id=run.name,
        meta=json.loads((run / "meta.json").read_text()),
        report=json.loads((run / "report.json").read_text()),
        models=bundle["models"],
        offsets=bundle["offsets"],
    )
