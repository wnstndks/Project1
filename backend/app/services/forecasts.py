"""Serve the pooled forecaster: per-holding ranges, the portfolio range, training jobs.

Inference rebuilds the latest panel rows (held symbols and context refreshed, reference
assets read from the cache) and is memoized per trained run for a while, so pages do not
recompute ~70 assets on every request.
"""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.data.assets import FX_USDKRW, UPBIT_MARKETS, trades_every_day
from app.data.calendar import last_final_date, next_trading_dates
from app.data.provider import MarketDataError
from app.db.models import AssetType, Currency, ForecastLog, Transaction
from app.forecast import aggregate, store, universe
from app.forecast.data import Inputs, bars_frame, load_inputs
from app.forecast.panel import HORIZONS, AssetClass, build_panel, latest_ranks
from app.forecast.report import ASSET_CLASSES, live_edge_at
from app.forecast.walkforward import apply_offsets
from app.services.errors import ConflictError, DomainError, NotFoundError
from app.services.market_data import MarketDataService, SymbolNotFoundError
from app.services.portfolio import PortfolioService

INFERENCE_TTL = 30 * 60.0  # seconds
CORRELATION_DAYS = 730

_runs: dict[Path, store.Run] = {}
# Only the latest inference is kept: a retrain or a new holding replaces it.
_inference: dict[tuple, tuple[float, pd.DataFrame, Inputs]] = {}
_lock = threading.Lock()
# Serializes cache misses, so concurrent requests do not each rebuild the whole panel.
_compute_lock = threading.Lock()


def held_symbols(db: Session) -> list[tuple[str, AssetClass]]:
    """Every symbol ever traded, in its dollar form (KRW coins are stored as BTC-USD)."""
    rows = db.execute(select(Transaction.symbol, Transaction.asset_type).distinct()).all()
    return sorted(
        {(s, "crypto" if t == AssetType.CRYPTO else "stock") for s, t in rows},
    )


def _run(artifacts_dir: Path) -> store.Run:
    path = store.resolve(artifacts_dir)
    if path is None:
        raise NotFoundError(
            "예측 모델이 아직 학습되지 않았습니다. 학습을 시작하거나 "
            "`py -m uv run python -m app.forecast.train`을 실행하세요.",
            code="not_trained",
        )
    with _lock:
        run = _runs.get(artifacts_dir)
        if run is None or run.path != path:
            run = store.load(path)
            _runs[artifacts_dir] = run
    return run


def target_date(symbol: str, as_of: date, horizon: str) -> date:
    cls: AssetClass = "crypto" if trades_every_day(symbol) else "stock"
    return next_trading_dates(symbol, as_of, HORIZONS[horizon][cls])[-1]


def live_verdicts(report: dict) -> dict[str, dict[str, dict[str, str]]]:
    """The live reason per asset class, horizon and kind, read the way the symbol
    forecasts read it (`live_edge_at`), so the home and the detail page cannot disagree."""
    lookups = {kind: live_edge_at(report, kind) for kind in ("direction", "range")}
    today = date.today()  # the live lookup reads the saved report whatever the date
    return {
        cls: {h: {kind: at(today, cls, h).reason for kind, at in lookups.items()} for h in HORIZONS}
        for cls in ASSET_CLASSES
    }


class ForecastService:
    def __init__(
        self,
        db: Session,
        market: MarketDataService,
        portfolio: PortfolioService,
        artifacts_dir: Path,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.db = db
        self.market = market
        self.portfolio = portfolio
        self.artifacts_dir = artifacts_dir
        self.clock = clock

    # --- inference -----------------------------------------------------------------

    def _latest(self, run: store.Run) -> tuple[pd.DataFrame, Inputs]:
        """Predictions for the newest row of every held symbol, per horizon and model."""
        held = held_symbols(self.db)
        key = (run.run_id, tuple(held), self._bar_epoch())
        with _compute_lock:
            now = self.clock()
            with _lock:
                hit = _inference.get(key)
            if hit is not None and now - hit[0] < INFERENCE_TTL:
                return hit[1], hit[2]
            out, inputs = self._compute(run, held)
            with _lock:
                _inference.clear()
                _inference[key] = (now, out, inputs)
            return out, inputs

    def _bar_epoch(self) -> tuple[date | None, date | None]:
        """The newest stock and coin bars the calendar says are final by now. Part of the
        inference cache key: once a session has closed (and settled) the next request
        rebuilds instead of serving the previous session's row for up to INFERENCE_TTL
        (ISSUE-040). Whether the provider has delivered that bar yet is `_compute`'s
        problem; the key only asks whether it should exist."""
        today, now_utc = self.market.now().date(), self.market.utc_now()
        return (
            last_final_date(universe.STOCK_BENCHMARK, today, now_utc),
            last_final_date(universe.CRYPTO_BENCHMARK, today, now_utc),
        )

    def _compute(
        self, run: store.Run, held: list[tuple[str, AssetClass]]
    ) -> tuple[pd.DataFrame, Inputs]:
        start = date.today() - timedelta(days=CORRELATION_DAYS + 400)
        inputs = load_inputs(self.market, held, start=start, cached_reference=True)
        panel = build_panel(inputs.assets, inputs.context, inputs.benchmarks)
        symbols = [s for s, _ in held]
        rows = panel[panel["symbol"].isin(symbols)].groupby("symbol").tail(1)
        rows = latest_ranks(panel, rows).set_index("symbol")
        frames = []
        for h, models in run.models.items():
            for name, model in models.items():
                pred = model.predict(rows)
                pred = apply_offsets(pred, run.offsets[h].get(name, {}), rows["asset_class"])
                pred["scale"] = rows[f"scale_{h}"]
                pred["horizon"], pred["model"] = h, name
                pred["as_of"] = rows["date"].dt.date
                frames.append(pred)
        out = pd.concat(frames).reset_index(names="symbol")
        self._log(run, out, inputs)
        return out, inputs

    def _log(self, run: store.Run, preds: pd.DataFrame, inputs: Inputs) -> None:
        """Record the first forecast for each (symbol, horizon, as_of) for later scoring."""
        gb = preds[preds["model"] == "gbdt"].set_index(["symbol", "horizon"])
        base = preds[preds["model"] == "climatology"].set_index(["symbol", "horizon"])
        values = []
        for (symbol, h), r in gb.iterrows():
            values.append(
                {
                    "symbol": symbol,
                    "horizon": h,
                    "as_of": r["as_of"],
                    "target_date": target_date(symbol, r["as_of"], h),
                    "run_id": run.run_id,
                    "base_price": float(inputs.assets[symbol].bars["close"].iloc[-1]),
                    "q10": float(r["q10"] * r["scale"]),
                    "q50": float(r["q50"] * r["scale"]),
                    "q90": float(r["q90"] * r["scale"]),
                    "p_up": float(r["p_up"]),
                    "baseline_p_up": float(base.loc[(symbol, h), "p_up"]),
                    "created_at": datetime.now(),
                }
            )
        if values:
            self.db.execute(sqlite_insert(ForecastLog).values(values).on_conflict_do_nothing())
            self.db.commit()

    def track_record(self, symbol: str | None = None) -> dict:
        """Live forecasts scored against realized prices, next to the base-rate baseline."""
        stmt = select(ForecastLog).order_by(ForecastLog.as_of.desc())
        if symbol:
            stmt = stmt.where(ForecastLog.symbol == symbol)
        logs = list(self.db.scalars(stmt))
        prices: dict[str, pd.Series] = {}
        scored, pending = [], 0
        for row in logs:
            if row.symbol not in prices:
                start = min(r.as_of for r in logs if r.symbol == row.symbol)
                bars = self.market.get_history(
                    row.symbol, start, final_only=True, max_age=timedelta(hours=12)
                )
                prices[row.symbol] = pd.Series(
                    [b.adj_close for b in bars], index=[b.date for b in bars], dtype=float
                )
            series = prices[row.symbol]
            if series.empty or series.index[-1] < row.target_date:
                pending += 1
                continue
            start_px = series[series.index <= row.as_of]
            end_px = series[series.index <= row.target_date]
            if start_px.empty:
                continue
            realized = float(np.log(end_px.iloc[-1] / start_px.iloc[-1]))
            scored.append((row, realized))

        summary = []
        for h in HORIZONS:
            pairs = [(r, x) for r, x in scored if r.horizon == h]
            if not pairs:
                continue
            up = np.array([x > 0 for _, x in pairs], dtype=float)
            p = np.array([r.p_up for r, _ in pairs])
            b = np.array([r.baseline_p_up for r, _ in pairs])
            summary.append(
                {
                    "horizon": h,
                    "scored": len(pairs),
                    "coverage": float(np.mean([r.q10 <= x <= r.q90 for r, x in pairs])),
                    "hit_rate": float(np.mean((p > 0.5) == (up > 0))),
                    "baseline_hit_rate": float(np.mean((b > 0.5) == (up > 0))),
                    "brier": float(np.mean((p - up) ** 2)),
                    "baseline_brier": float(np.mean((b - up) ** 2)),
                }
            )
        return {
            "pending": pending,
            "summary": summary,
            "recent": [
                {
                    "symbol": r.symbol,
                    "horizon": r.horizon,
                    "as_of": r.as_of,
                    "target_date": r.target_date,
                    "q10": r.q10,
                    "q50": r.q50,
                    "q90": r.q90,
                    "p_up": r.p_up,
                    "realized": x,
                }
                for r, x in scored[:30]
            ],
        }

    def _horizon_rows(
        self,
        run: store.Run,
        mine: pd.DataFrame,
        symbol: str,
        asset_class: AssetClass,
        base: float,
    ) -> list[dict]:
        """One symbol's predictions per horizon, scaled back to prices from the latest close,
        with the live verdict. Shared by `forecast` and `held_forecasts`: the same numbers,
        whichever endpoint the page asks."""
        # The live verdict per class, horizon and kind (D-018): a range edge stays withheld
        # until its forward paper test is confirmed, whatever the walk-forward report says.
        direction_at = live_edge_at(run.report, "direction")
        range_at = live_edge_at(run.report, "range")
        rows = []
        for h, g in mine.groupby("horizon", sort=False):
            by_model = g.set_index("model")
            gb = by_model.loc["gbdt"]
            as_of = gb["as_of"]
            scale = float(gb["scale"])
            as_of_date = pd.Timestamp(as_of).date()
            direction = direction_at(as_of_date, asset_class, h)
            range_ = range_at(as_of_date, asset_class, h)
            rows.append(
                {
                    "horizon": h,
                    "as_of": as_of,
                    "target_date": target_date(symbol, as_of, h),
                    "base_price": base,
                    # Prices at the 10/50/90% quantiles (log returns scaled back).
                    "p10": base * float(np.exp(gb["q10"] * scale)),
                    "p50": base * float(np.exp(gb["q50"] * scale)),
                    "p90": base * float(np.exp(gb["q90"] * scale)),
                    "p_up": float(gb["p_up"]),
                    "baseline_p_up": float(by_model.loc["climatology", "p_up"]),
                    "baseline_p10": base * float(np.exp(by_model.loc["ewma_t", "q10"] * scale)),
                    "baseline_p90": base * float(np.exp(by_model.loc["ewma_t", "q90"] * scale)),
                    "direction_edge": direction.edge,
                    "direction_reason": direction.reason,
                    "range_edge": range_.edge,
                    "range_reason": range_.reason,
                }
            )
        return rows

    def held_forecasts(self) -> list[dict]:
        """Every held symbol's horizons in one call (the home used to ask per symbol), as
        ratios to the latest close. Symbols without a prediction (history too short) are
        left out rather than failing the whole list."""
        run = _run(self.artifacts_dir)
        preds, inputs = self._latest(run)
        out = []
        for symbol, asset_class in held_symbols(self.db):
            mine = preds[preds["symbol"] == symbol]
            if mine.empty:
                continue
            base = float(inputs.assets[symbol].bars["close"].iloc[-1])
            out.append(
                {
                    "symbol": symbol,
                    "asset_class": asset_class,
                    "horizons": [
                        {
                            "horizon": r["horizon"],
                            "as_of": r["as_of"],
                            "target_date": r["target_date"],
                            "low_ratio": r["p10"] / base,
                            "mid_ratio": r["p50"] / base,
                            "high_ratio": r["p90"] / base,
                            "p_up": r["p_up"],
                            "baseline_p_up": r["baseline_p_up"],
                            "direction_edge": r["direction_edge"],
                            "range_edge": r["range_edge"],
                            "direction_reason": r["direction_reason"],
                            "range_reason": r["range_reason"],
                        }
                        for r in self._horizon_rows(run, mine, symbol, asset_class, base)
                    ],
                }
            )
        return out

    def forecast(self, symbol: str) -> dict:
        run = _run(self.artifacts_dir)
        preds, inputs = self._latest(run)
        mine = preds[preds["symbol"] == symbol]
        held = dict(held_symbols(self.db))
        if mine.empty:
            if symbol in held:
                raise DomainError(
                    f"{symbol}은(는) 가격 이력이 짧아(300거래일 미만) 아직 예측하지 않습니다",
                    code="insufficient_history",
                )
            raise NotFoundError(f"{symbol}은(는) 보유 종목이 아니라 예측하지 않습니다")
        bars = inputs.assets[symbol].bars
        base = float(bars["close"].iloc[-1])
        fallback: AssetClass = "crypto" if trades_every_day(symbol) else "stock"
        horizons = self._horizon_rows(run, mine, symbol, held.get(symbol, fallback), base)
        holding = next((h for h in self.portfolio.holdings() if h.symbol == symbol), None)
        krw_rate = None
        if holding is not None and holding.currency == Currency.KRW and symbol in UPBIT_MARKETS:
            # Upbit won per dollar of this coin, premium included: what the user actually sees.
            premium = self._premia([symbol], inputs).get(symbol)
            fx = inputs.context_close("usdkrw")
            if premium is not None and not premium.empty and fx is not None:
                krw_rate = float(fx.iloc[-1] * np.exp(premium.iloc[-1]))
        return {
            "symbol": symbol,
            "trained_at": run.meta["trained_at"],
            "data_end": run.meta["data_end"],
            "krw_rate": krw_rate,
            "horizons": horizons,
            "recent": [{"date": d, "close": float(c)} for d, c in bars["close"].iloc[-90:].items()],
        }

    def portfolio_forecast(self, seed: int = 0) -> dict:
        run = _run(self.artifacts_dir)
        preds, inputs = self._latest(run)
        holdings = [h for h in self.portfolio.holdings() if h.quantity > 0]
        gb = preds[preds["model"] == "gbdt"]
        usdkrw = inputs.context_close("usdkrw")
        if usdkrw is None:
            usdkrw = bars_frame(
                self.market.get_history(FX_USDKRW, date.today() - timedelta(days=400))
            )["close"]

        returns = pd.DataFrame(
            {
                h.symbol: np.log(inputs.assets[h.symbol].bars["adj_close"])
                for h in holdings
                if h.symbol in inputs.assets
            }
        )
        returns[aggregate.FX] = np.log(usdkrw)
        returns.index = pd.to_datetime(returns.index)
        # Align on weekdays: a coin's Monday return then spans the weekend, like a stock's.
        returns = returns.sort_index().ffill()
        returns = returns[returns.index.dayofweek < 5].diff().iloc[-CORRELATION_DAYS:]

        upbit = [
            h.symbol for h in holdings if h.currency == Currency.KRW and h.symbol in UPBIT_MARKETS
        ]
        premia = self._premia(upbit, inputs)
        premium_model = aggregate.fit_premium(premia)

        out = []
        for h in run.models:
            assets = []
            for hold in holdings:
                row = gb[(gb["symbol"] == hold.symbol) & (gb["horizon"] == h)]
                if row.empty:
                    continue
                r = row.iloc[0]
                assets.append(
                    aggregate.AssetForecast(
                        hold.symbol,
                        float(hold.market_value_krw),
                        float(r["q10"] * r["scale"]),
                        float(r["q50"] * r["scale"]),
                        float(r["q90"] * r["scale"]),
                    )
                )
            cols = [a.symbol for a in assets] + [aggregate.FX]
            corr = aggregate.correlation(returns[cols])
            days = {"1d": 1, "1w": 7, "1m": 30}[h]
            fx = aggregate.fx_forecast(usdkrw, days)
            premium = (
                {s: premium_model.horizon(float(p.iloc[-1]), days) for s, p in premia.items()}
                if premium_model
                else None
            )
            pf = aggregate.simulate(assets, fx, corr, seed=seed, premium=premium)
            out.append({"horizon": h} | pf.__dict__)
        covered = {a for a in preds["symbol"]}
        return {
            "trained_at": run.meta["trained_at"],
            "horizons": out,
            "kimchi_premium": {s: float(np.expm1(p.iloc[-1])) for s, p in premia.items()},
            "excluded": [h.symbol for h in holdings if h.symbol not in covered],
        }

    def _premia(self, symbols: list[str], inputs: Inputs) -> dict[str, pd.Series]:
        """Daily log kimchi premium per coin: Upbit won close over dollar close x USD/KRW."""
        fx = inputs.context_close("usdkrw")
        if fx is None:
            return {}
        fx = pd.Series(fx.to_numpy(), index=pd.to_datetime(fx.index))
        out = {}
        start = date.today() - timedelta(days=CORRELATION_DAYS)
        for symbol in symbols:
            if symbol not in inputs.assets:
                continue
            try:
                bars = self.market.get_history(UPBIT_MARKETS[symbol], start, final_only=True)
            except (SymbolNotFoundError, MarketDataError):
                continue
            krw = pd.Series([b.close for b in bars], index=pd.to_datetime([b.date for b in bars]))
            usd = inputs.assets[symbol].bars["close"]
            usd = pd.Series(usd.to_numpy(), index=pd.to_datetime(usd.index))
            rate = fx.reindex(krw.index.union(fx.index)).ffill().reindex(krw.index)
            out[symbol] = np.log(krw / (usd.reindex(krw.index) * rate)).dropna()
        return out

    def status(self) -> dict:
        path = store.resolve(self.artifacts_dir)
        if path is None:
            return {"trained": False}
        run = _run(self.artifacts_dir)
        return {
            "trained": True,
            "meta": run.meta,
            "report": run.report,
            "live": live_verdicts(run.report),
        }

    def backtest(self, symbol: str, horizon: str) -> list[dict]:
        run = _run(self.artifacts_dir)
        df = run.backtest(horizon)
        if df.empty:
            return []
        df = df[df["symbol"] == symbol].sort_values("date")
        return [
            {
                "date": r.date.date(),
                "actual": float(r.fr),
                "q10": float(r.gbdt_q10 * r.scale),
                "q50": float(r.gbdt_q50 * r.scale),
                "q90": float(r.gbdt_q90 * r.scale),
                "p_up": float(r.gbdt_p_up),
                "segment": r.segment,
            }
            for r in df.itertuples()
        ]


@dataclass
class ForecastJob:
    state: str = "running"  # running | done | failed
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: datetime | None = None
    error: str | None = None
    log: list[str] = field(default_factory=list)


class ForecastTraining:
    """One global training job at a time, in a background thread with its own session."""

    def __init__(self) -> None:
        self.job: ForecastJob | None = None
        self._lock = threading.Lock()

    def start(
        self,
        session_factory: Callable[[], Session],
        make_market: Callable[[Session], MarketDataService],
        artifacts_dir: Path,
        engine: str = "auto",
    ) -> ForecastJob:
        from app.forecast.train import train

        with self._lock:
            if self.job is not None and self.job.state == "running":
                raise ConflictError("예측 모델 학습이 이미 진행 중입니다")
            job = self.job = ForecastJob()

        def run() -> None:
            try:
                with session_factory() as db:
                    held = held_symbols(db)
                    job.log.append(f"시세 불러오는 중: 보유 {len(held)}종목 + 참조 종목")
                    inputs = load_inputs(make_market(db), held)
                train(
                    inputs, [s for s, _ in held], artifacts_dir, engine=engine, log=job.log.append
                )
                job.state = "done"
            except Exception as exc:
                job.state, job.error = "failed", str(exc)
            finally:
                job.finished_at = datetime.now()

        threading.Thread(target=run, name="train-forecaster", daemon=True).start()
        return job
