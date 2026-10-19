"""Saving and loading trained models. Everything except the weights is plain JSON."""

import json
import os
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import torch

from app.ml.dataset import Scaler
from app.ml.model import LSTMForecaster


@dataclass
class TrainConfig:
    lookback: int = 60
    horizon: int = 5
    hidden: int = 64
    layers: int = 2
    dropout: float = 0.2
    epochs: int = 100
    patience: int = 10
    batch_size: int = 64
    lr: float = 1e-3
    seed: int = 42
    years: int = 8


@dataclass
class LoadedModel:
    model: LSTMForecaster
    config: TrainConfig
    meta: dict
    metrics: dict
    x_scaler: Scaler
    y_scaler: Scaler


def symbol_dir(artifacts_dir: Path, symbol: str) -> Path:
    # "KRW=X" or "BRK.B" must still be a safe directory name.
    return artifacts_dir / re.sub(r"[^A-Za-z0-9.\-]", "_", symbol)


def save(
    artifacts_dir: Path,
    symbol: str,
    model: LSTMForecaster,
    config: TrainConfig,
    meta: dict,
    metrics: dict,
    backtest: list[dict],
) -> Path:
    """Write a new immutable run directory, then atomically repoint `current.json` at it.

    Readers resolve the pointer once and read every file from that one run, so they never
    mix new weights with old scalers, and no directory in use is ever renamed (which fails
    on Windows while a file inside is open).
    """
    base = symbol_dir(artifacts_dir, symbol)
    run_id = f"{datetime.now():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
    run = base / "runs" / run_id
    run.mkdir(parents=True)
    torch.save(model.state_dict(), run / "model.pt")
    (run / "meta.json").write_text(json.dumps(meta | {"config": asdict(config)}, indent=2))
    (run / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (run / "backtest.json").write_text(json.dumps(backtest))
    pointer_tmp = base / f"current.json.{uuid.uuid4().hex}.tmp"
    pointer_tmp.write_text(json.dumps({"run": run_id}))
    os.replace(pointer_tmp, base / "current.json")
    _prune(base / "runs", keep=run_id)
    return run


def _prune(runs: Path, keep: str, retain: int = 3) -> None:
    """Delete old runs, keeping the newest few (a reader may still be loading one)."""
    old = sorted(p for p in runs.iterdir() if p.is_dir() and p.name != keep)
    for p in old[: max(0, len(old) - (retain - 1))]:
        shutil.rmtree(p, ignore_errors=True)


def resolve(artifacts_dir: Path, symbol: str) -> Path | None:
    """The run directory currently in use, or None when nothing is trained."""
    base = symbol_dir(artifacts_dir, symbol)
    try:
        run_id = json.loads((base / "current.json").read_text())["run"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        # Models saved before run directories existed live directly in `base`.
        return base if (base / "model.pt").exists() else None
    run = base / "runs" / run_id
    return run if (run / "model.pt").exists() else None


def exists(artifacts_dir: Path, symbol: str) -> bool:
    return resolve(artifacts_dir, symbol) is not None


def load(run: Path) -> LoadedModel:
    """Load everything from one resolved run directory (see `resolve`)."""
    d = run
    meta = json.loads((d / "meta.json").read_text())
    config = TrainConfig(**meta["config"])
    model = LSTMForecaster(
        len(meta["features"]), config.horizon, config.hidden, config.layers, config.dropout
    )
    model.load_state_dict(torch.load(d / "model.pt", weights_only=True))
    model.eval()
    return LoadedModel(
        model=model,
        config=config,
        meta=meta,
        metrics=json.loads((d / "metrics.json").read_text()),
        x_scaler=Scaler.from_dict(meta["x_scaler"]),
        y_scaler=Scaler.from_dict(meta["y_scaler"]),
    )


def load_backtest(run: Path) -> list[dict]:
    return json.loads((run / "backtest.json").read_text())
