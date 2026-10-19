"""Saving and loading trained models. Everything except the weights is plain JSON."""

import json
import re
from dataclasses import asdict, dataclass
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
    out = symbol_dir(artifacts_dir, symbol)
    out.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), out / "model.pt")
    (out / "meta.json").write_text(json.dumps(meta | {"config": asdict(config)}, indent=2))
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    (out / "backtest.json").write_text(json.dumps(backtest))
    return out


def exists(artifacts_dir: Path, symbol: str) -> bool:
    return (symbol_dir(artifacts_dir, symbol) / "model.pt").exists()


def load(artifacts_dir: Path, symbol: str) -> LoadedModel:
    d = symbol_dir(artifacts_dir, symbol)
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


def load_backtest(artifacts_dir: Path, symbol: str) -> list[dict]:
    return json.loads((symbol_dir(artifacts_dir, symbol) / "backtest.json").read_text())


def mtime(artifacts_dir: Path, symbol: str) -> float:
    return (symbol_dir(artifacts_dir, symbol) / "model.pt").stat().st_mtime
