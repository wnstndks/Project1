"""Train an LSTM forecaster for one symbol and save it under artifacts/{symbol}/.

py -m uv run python -m app.ml.train --symbol AAPL
py -m uv run python -m app.ml.train --symbol BTC --epochs 50
"""

import argparse
import copy
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import torch
from torch import nn

from app.ml import artifacts
from app.ml.artifacts import TrainConfig
from app.ml.dataset import prepare
from app.ml.evaluate import evaluate
from app.ml.features import FEATURES, BarLike, bars_to_frame
from app.ml.model import LSTMForecaster

Log = Callable[[str], None]


def _seed_everything(seed: int) -> None:
    np.random.seed(seed)
    torch.manual_seed(seed)


def _predict(model: nn.Module, x: np.ndarray) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        return model(torch.from_numpy(x)).numpy()


def train_model(
    symbol: str,
    bars: Sequence[BarLike],
    config: TrainConfig,
    artifacts_dir: Path,
    log: Log = print,
) -> dict:
    """Train, evaluate on the held-out test split, save artifacts and return the metrics."""
    _seed_everything(config.seed)
    torch.set_num_threads(min(4, torch.get_num_threads()))

    df = bars_to_frame(bars)
    data = prepare(df, config.lookback, config.horizon)
    log(
        f"{symbol}: {len(df)} bars -> windows train {len(data.train.x)}, "
        f"val {len(data.val.x)}, test {len(data.test.x)}"
    )

    model = LSTMForecaster(
        len(FEATURES), config.horizon, config.hidden, config.layers, config.dropout
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=config.lr)
    loss_fn = nn.MSELoss()
    x_train, y_train = torch.from_numpy(data.train.x), torch.from_numpy(data.train.y)
    x_val, y_val = torch.from_numpy(data.val.x), torch.from_numpy(data.val.y)
    generator = torch.Generator().manual_seed(config.seed)

    best_loss, best_state, best_epoch, waited = float("inf"), None, 0, 0
    started = time.perf_counter()
    for epoch in range(1, config.epochs + 1):
        model.train()
        # Shuffling windows *within* the training split is fine; splits stay chronological.
        order = torch.randperm(len(x_train), generator=generator)
        for i in range(0, len(order), config.batch_size):
            batch = order[i : i + config.batch_size]
            optimizer.zero_grad()
            loss = loss_fn(model(x_train[batch]), y_train[batch])
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

        model.eval()
        with torch.no_grad():
            val_loss = loss_fn(model(x_val), y_val).item()
        if val_loss < best_loss - 1e-6:
            best_loss, best_state, best_epoch, waited = (
                val_loss,
                copy.deepcopy(model.state_dict()),
                epoch,
                0,
            )
        else:
            waited += 1
        if epoch == 1 or epoch % 10 == 0:
            log(f"  epoch {epoch:3d}  val_loss {val_loss:.4f}  best {best_loss:.4f} @ {best_epoch}")
        if waited >= config.patience:
            log(f"  early stop at epoch {epoch}")
            break

    model.load_state_dict(best_state)
    y_pred = data.y_scaler.inverse(_predict(model, data.test.x))
    train_up_ratio = float(np.mean(data.train.y_raw[:, 0] > 0))
    metrics = evaluate(data.test.base_close, data.test.y_raw, y_pred, train_up_ratio) | {
        "best_epoch": best_epoch,
        "best_val_loss": best_loss,
        "train_seconds": round(time.perf_counter() - started, 1),
    }

    # One-day-ahead backtest series for the "actual vs predicted" chart.
    backtest = []
    for i, d in enumerate(data.test.dates):
        base = float(data.test.base_close[i])
        backtest.append(
            {
                "date": str(d),
                "actual": round(base * float(np.exp(data.test.y_raw[i, 0])), 6),
                "predicted": round(base * float(np.exp(y_pred[i, 0])), 6),
                "naive": round(base, 6),
            }
        )

    def span(split) -> list[str]:
        return [str(split.dates[0]), str(split.dates[-1])]

    meta = {
        "symbol": symbol,
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "data_end": str(df.index[-1]),
        "features": FEATURES,
        "train_range": span(data.train),
        "val_range": span(data.val),
        "test_range": span(data.test),
        "x_scaler": data.x_scaler.to_dict(),
        "y_scaler": data.y_scaler.to_dict(),
    }
    out = artifacts.save(artifacts_dir, symbol, model, config, meta, metrics, backtest)
    log(f"Saved to {out}")
    return metrics


def _print_metrics(metrics: dict) -> None:
    print(f"\nTest set: {metrics['samples']} samples (best epoch {metrics['best_epoch']})")
    print(f"{'day':>4} {'':>9} {'MAE':>10} {'RMSE':>10} {'MAPE%':>7} {'dir%':>6}")
    for row in metrics["by_horizon"]:
        for name in ("model", "baseline"):
            m = row[name]
            print(
                f"{row['day']:>4} {name:>9} {m['mae']:>10.4f} {m['rmse']:>10.4f} "
                f"{m['mape']:>7.2f} {m['direction_acc']:>6.1f}"
            )


def main() -> None:
    from app.config import get_settings
    from app.data.assets import resolve_symbol
    from app.db.session import SessionLocal
    from app.deps import get_provider, get_quote_cache
    from app.services.market_data import MarketDataService

    parser = argparse.ArgumentParser(description="Train an LSTM price forecaster")
    parser.add_argument("--symbol", required=True, help="e.g. AAPL, BTC, ETH-USD")
    defaults = TrainConfig()
    for field, value in asdict(defaults).items():
        parser.add_argument(f"--{field.replace('_', '-')}", type=type(value), default=value)
    args = parser.parse_args()

    symbol = resolve_symbol(args.symbol)
    config = TrainConfig(**{f: getattr(args, f) for f in asdict(defaults)})

    with SessionLocal() as db:
        market = MarketDataService(db, get_provider(), get_quote_cache())
        start = date.today() - timedelta(days=365 * config.years)
        bars = market.get_history(symbol, start)

    metrics = train_model(symbol, bars, config, get_settings().artifacts_dir)
    _print_metrics(metrics)


if __name__ == "__main__":
    main()
