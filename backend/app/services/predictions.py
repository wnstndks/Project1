"""Serve forecasts from trained artifacts and run training jobs in the background."""

import threading
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import torch

from app.data.calendar import next_trading_dates
from app.ml import artifacts
from app.ml.artifacts import LoadedModel, TrainConfig
from app.ml.dataset import latest_window
from app.ml.features import bars_to_frame
from app.ml.train import train_model
from app.services.errors import ConflictError, NotFoundError
from app.services.market_data import MarketDataService

_model_cache: dict[tuple[Path, str], tuple[Path, LoadedModel]] = {}
_cache_lock = threading.Lock()


def _load(artifacts_dir: Path, symbol: str) -> LoadedModel:
    """Load once per process and reload only when `current.json` points at a new run."""
    run = artifacts.resolve(artifacts_dir, symbol)
    if run is None:
        raise NotFoundError(
            f"No trained model for {symbol}. Train one with "
            f"`py -m uv run python -m app.ml.train --symbol {symbol}` or the train button."
        )
    key = (artifacts_dir, symbol)
    with _cache_lock:
        cached = _model_cache.get(key)
        if cached is None or cached[0] != run:
            cached = (run, artifacts.load(run))
            _model_cache[key] = cached
    return cached[1]


def _history_start(config: TrainConfig) -> date:
    # Enough calendar days for warm-up + lookback trading days, with room for holidays.
    return date.today() - timedelta(days=int((config.lookback + 40) * 1.6))


class PredictionService:
    def __init__(self, market: MarketDataService, artifacts_dir: Path) -> None:
        self.market = market
        self.artifacts_dir = artifacts_dir

    def forecast(self, symbol: str) -> dict:
        loaded = _load(self.artifacts_dir, symbol)
        config = loaded.config
        bars = self.market.get_history(symbol, _history_start(config), final_only=True)
        df = bars_to_frame(bars)
        x = latest_window(df, config.lookback, config.horizon, loaded.x_scaler)
        with torch.no_grad():
            y = loaded.y_scaler.inverse(loaded.model(torch.from_numpy(x)).numpy())[0]

        last_date, base = df.index[-1], float(df["close"].iloc[-1])
        dates = next_trading_dates(symbol, last_date, config.horizon)
        return {
            "symbol": symbol,
            "as_of": last_date,
            "base_price": base,
            "forecast": [
                {
                    "date": d,
                    "price": base * float(np.exp(r)),
                    "return_pct": float(np.expm1(r) * 100),
                }
                for d, r in zip(dates, y, strict=True)
            ],
            "metrics": loaded.metrics,
            "trained_at": loaded.meta["trained_at"],
            "train_range": loaded.meta["train_range"],
            "test_range": loaded.meta["test_range"],
            "recent": [{"date": b.date, "close": b.close} for b in bars[-60:]],
        }

    def backtest(self, symbol: str) -> list[dict]:
        _load(self.artifacts_dir, symbol)
        return artifacts.load_backtest(artifacts.resolve(self.artifacts_dir, symbol))

    def trained(self) -> list[dict]:
        if not self.artifacts_dir.exists():
            return []
        out = []
        for d in sorted(self.artifacts_dir.iterdir()):
            if d.is_dir() and artifacts.exists(self.artifacts_dir, d.name):
                loaded = _load(self.artifacts_dir, d.name)
                day1 = loaded.metrics["by_horizon"][0]
                out.append(
                    {
                        "symbol": loaded.meta["symbol"],
                        "trained_at": loaded.meta["trained_at"],
                        "mape_model": day1["model"]["mape"],
                        "mape_baseline": day1["baseline"]["mape"],
                    }
                )
        return out


@dataclass
class TrainingJob:
    symbol: str
    state: str = "running"  # running | done | failed
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    error: str | None = None
    log: list[str] = field(default_factory=list)


class TrainingJobs:
    """In-process background training. One job at a time, since training is CPU-bound."""

    def __init__(self) -> None:
        self._jobs: dict[str, TrainingJob] = {}
        self._lock = threading.Lock()

    def get(self, symbol: str) -> TrainingJob | None:
        return self._jobs.get(symbol)

    def start(
        self, symbol: str, market: MarketDataService, artifacts_dir: Path, config: TrainConfig
    ) -> TrainingJob:
        with self._lock:
            running = [j for j in self._jobs.values() if j.state == "running"]
            if running:
                raise ConflictError(f"Training for {running[0].symbol} is already running")
            job = TrainingJob(symbol)
            self._jobs[symbol] = job

        try:
            # Fetch on the request thread: the DB session is not shared with the worker.
            start = date.today() - timedelta(days=365 * config.years)
            bars = market.get_history(symbol, start, final_only=True)
        except Exception:
            self._jobs.pop(symbol, None)
            raise

        def run() -> None:
            try:
                train_model(symbol, bars, config, artifacts_dir, log=job.log.append)
                job.state = "done"
            except Exception as exc:
                job.state, job.error = "failed", str(exc)
            finally:
                job.finished_at = datetime.now()

        threading.Thread(target=run, name=f"train-{symbol}", daemon=True).start()
        return job
