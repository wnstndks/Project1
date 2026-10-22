"""S2 against baselines ① and ② on the walk-forward window (D-015 gate ①).

    py -m uv run python -m app.strategy.assess_s2 <out.json>   # from backend/

Inputs: the current forecast run's `oos_universe_{h}` (walk-forward rows only, D-022),
strict-loader prices up to the day before the holdout (D-020), the settings' risk limits
and class budgets. S2's edge is the point-in-time 1d vol edge (QLIKE, gbdt against
ewma_t, Holm over all 24 comparisons); the range comparison is reported, never used.

The registered conditions 7 and 8 (STRATEGIES.md S2) join gate ①: S2's net Sharpe above
the same rule with the EWMA-t width (d2), and a positive walk-forward vol DM on each
traded symbol. Diagnostics marked `not_adoptable` (the edge gate ignored, d2 itself, a
fixed exposure of baseline ①) explain a result; they are never strategies and never
counted in STRATEGY_CONFIGS_TRIED.

The holdout is not opened here, even when gate ① passes: D-015 ② is a separate, logged
step (`open_strategy_holdout`) taken on the lead's instruction.
"""

import json
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.forecast.report import EdgeLookup, EdgeStatus, PointInTimeEdge
from app.strategy.assess import FIRST_DAY, _clean
from app.strategy.backtest import BacktestConfig, BacktestResult, run_backtest, summarize
from app.strategy.risk import RiskLimits, max_drawdown

S2_HORIZON = "1d"
EDGE_KIND = "vol"
# Episodes whose drawdowns are reported (reference only, never a gate).
EPISODES = {
    "2018": ("2018-01-01", "2018-12-31"),
    "2020_covid": ("2020-02-01", "2020-04-30"),
    "2022": ("2022-01-01", "2022-12-31"),
}
# A day is "under target" when a symbol's weight at the close is this far below the
# weight its last filled decision asked for (5% order cap, drift).
UNDERFILL_GAP = 0.05
MDD_BOOTSTRAP_BLOCK = 20
MDD_BOOTSTRAP_SAMPLES = 2000


def edge_lookups(
    edge_at: EdgeLookup, start: date, end: date, classes=("stock", "crypto")
) -> list[tuple[str, date, EdgeStatus]]:
    """One lookup per (asset class, S2 decision date) in the window: the denominator of
    falsification 1 (both classes together, structurally too-early dates included)."""
    from app.strategy.s2 import daily_dates

    return [
        (cls, d, edge_at(d, cls, S2_HORIZON))
        for cls in classes
        for d in daily_dates(cls, start, end)
    ]


def edge_summary(looks: list[tuple[str, date, EdgeStatus]]) -> dict:
    out = {}
    for cls in sorted({c for c, _, _ in looks}):
        mine = [(d, s) for c, d, s in looks if c == cls]
        on = [d for d, s in mine if s.edge]
        out[cls] = {
            "lookups": len(mine),
            "with_edge": len(on),
            "first_edge": str(min(on)) if on else None,
            "reasons": dict(Counter(s.reason for _, s in mine)),
            "last_lookup": asdict(mine[-1][1]) if mine else None,
        }
    return out


def underfilled_days(result: BacktestResult, frame: pd.DataFrame, gap: float = UNDERFILL_GAP):
    """Per symbol: days whose closing weight is more than `gap` below the target of the
    newest decision already filled (decided on an earlier day), out of days with a target
    above zero."""
    out = {}
    for symbol, g in frame.groupby("symbol"):
        target = g.set_index("as_of")["target_weight"].astype(float).sort_index()
        # A decision on D is filled on the next bar at the earliest: compare from D + 1.
        target.index = target.index + pd.Timedelta(days=1)
        days = result.weights.index
        wanted = target.reindex(days.union(target.index)).ffill().reindex(days)
        actual = result.weights.get(symbol, pd.Series(0.0, index=days)).reindex(days)
        live = wanted > 0
        out[symbol] = {
            "days_with_target": int(live.sum()),
            "days_under_target": int((live & (actual < wanted - gap)).sum()),
        }
    return out


def drawdowns(result: BacktestResult) -> dict:
    """Largest drawdown within each calendar year and each episode (reference only)."""
    eq = result.equity
    by_year = {
        str(y): max_drawdown(g.to_numpy()) for y, g in eq.groupby(eq.index.year) if len(g) > 1
    }
    episodes = {}
    for name, (a, b) in EPISODES.items():
        g = eq.loc[a:b]
        episodes[name] = max_drawdown(g.to_numpy()) if len(g) > 1 else None
    return {"by_year": by_year, "episodes": episodes}


def bootstrap_mdd_exceedance(
    returns: pd.Series,
    limit: float,
    *,
    block: float = MDD_BOOTSTRAP_BLOCK,
    n_boot: int = MDD_BOOTSTRAP_SAMPLES,
    seed: int = 0,
) -> float:
    """Share of stationary-bootstrap resamples of the daily returns whose drawdown exceeds
    `limit` (reference: how lucky the realized path may have been). Not a gate."""
    r = np.asarray(returns.dropna(), dtype=float)
    n = len(r)
    if n < 2:
        return float("nan")
    rng = np.random.default_rng(seed)
    p = 1.0 / block
    hits = 0
    for _ in range(n_boot):
        idx = np.empty(n, dtype=int)
        idx[0] = rng.integers(n)
        jumps = rng.random(n) < p
        starts = rng.integers(n, size=n)
        for t in range(1, n):
            idx[t] = starts[t] if jumps[t] else (idx[t - 1] + 1) % n
        path = np.cumprod(1 + r[idx])
        if max_drawdown(np.r_[1.0, path]) > limit:
            hits += 1
    return hits / n_boot


def fixed_exposure_weights(mix: Mapping[str, float], exposure: float) -> dict[str, float]:
    """Baseline ① scaled to a constant exposure (rest cash): S2's average exposure without
    its timing. Never above 1 (no leverage)."""
    k = float(min(1.0, max(0.0, exposure)))
    return {s: w * k for s, w in mix.items()}


def assess(  # pragma: no cover - needs market data and a forecast run
    out_path: str | None = None, *, seed: int = 0
) -> dict:
    from app.config import get_settings
    from app.db.session import SessionLocal
    from app.deps import get_provider, get_quote_cache
    from app.forecast import store
    from app.forecast.cv import HOLDOUT_START
    from app.forecast.panel import HORIZON_DAYS
    from app.forecast.report import CONFIGS_TRIED
    from app.forecast.universe import strategy_symbols
    from app.services.market_data import MarketDataService
    from app.strategy import baselines as bl
    from app.strategy import s2
    from app.strategy.backtest import load_inputs, with_costs
    from app.strategy.evaluation import (
        STRATEGY_CONFIGS_TRIED,
        adoption_gate,
        edge_share,
        excess_return_test,
        sharpe_test,
        strategy_config_hash,
        symbol_dm,
        volatility_scale,
        walk_forward_decision_end,
    )
    from app.strategy.risk import budgets_from_settings

    settings = get_settings()
    limits = RiskLimits.from_settings(settings)
    budgets = budgets_from_settings(settings)
    universe = strategy_symbols()
    last = pd.Timestamp(HOLDOUT_START).date() - timedelta(days=1)
    cfg = s2.s2_1d()
    d2_cfg = s2.ewma_variant(cfg)
    base_config = BacktestConfig()  # baselines: the recorded conditions (D-020, D-021)
    s2_config = BacktestConfig(min_trade_share=cfg.min_trade_share)
    run_dir = settings.artifacts_dir / store.GLOBAL / "runs"
    current = json.loads((settings.artifacts_dir / store.GLOBAL / "current.json").read_text())
    run = store.load(run_dir / current["run"])

    # All three horizons: the vol edge is Holm-adjusted with all 24 comparisons.
    oos = {}
    for h in ("1d", "1w", "1m"):
        frame = run.universe_oos(h)
        oos[h] = frame[frame["segment"] == "walk_forward"].reset_index(drop=True)
    edge = PointInTimeEdge(oos, rank_symbols=universe, configs_tried=CONFIGS_TRIED)
    vol_edge = edge.lookup(EDGE_KIND)
    rows = oos[S2_HORIZON]
    decide_end = walk_forward_decision_end(rows)

    with SessionLocal() as db:
        market = MarketDataService(db, get_provider(), get_quote_cache())
        inputs = load_inputs(market, universe, date(2015, 1, 1), last)

    def backtest(frame: pd.DataFrame, config: BacktestConfig = s2_config) -> BacktestResult:
        return run_backtest(
            s2.decisions(frame), inputs, config, limits=limits, start=FIRST_DAY, end=last
        )

    frame = s2.signal_frame(rows, vol_edge, cfg, budgets, start=FIRST_DAY, end=decide_end)
    strat = backtest(frame)
    d2_frame = s2.signal_frame(rows, vol_edge, d2_cfg, budgets, start=FIRST_DAY, end=decide_end)
    d2 = backtest(d2_frame)

    def always(d, cls, hz):
        return EdgeStatus(True, "diagnostic_edge_ignored")

    d1_frame = s2.signal_frame(rows, always, cfg, budgets, start=FIRST_DAY, end=decide_end)
    d1 = backtest(d1_frame)

    suite = bl.baseline_1_suite(
        inputs, base_config, FIRST_DAY, last, strategy_returns=strat.returns, budgets=budgets
    )
    gr = bl.GResearchConfig()
    gr_oos = bl.gresearch_oos(bl.gresearch_panel(inputs.bars, dict(universe), gr), gr)
    gr_dec = bl.gresearch_decisions(gr_oos, FIRST_DAY, decide_end, freq="W", budgets=budgets)
    base2 = run_backtest(gr_dec, inputs, base_config, limits=limits, start=FIRST_DAY, end=last)
    base2_free = run_backtest(gr_dec, inputs, base_config, start=FIRST_DAY, end=last)
    mean_exposure = float(strat.weights.sum(axis=1).mean())
    fixed = bl.run_buy_and_hold(
        fixed_exposure_weights(bl.baseline_1_weights(budgets), mean_exposure),
        inputs, base_config, FIRST_DAY, last,
    )  # fmt: skip

    looks = edge_lookups(vol_edge, FIRST_DAY, decide_end)
    share = edge_share([s for _, _, s in looks])
    traded = list(cfg.symbols.values())
    dms = {s: symbol_dm(rows, s, EDGE_KIND, HORIZON_DAYS[S2_HORIZON]) for s in traded}
    gate = adoption_gate(
        strat, suite["baseline_1"], base2, suite["baseline_1_vol_matched"],
        edge_share=share, limits=limits, seed=seed, ablation=d2, symbol_dm=dms,
    )  # fmt: skip
    baselines = {"baseline_1": suite["baseline_1"], "baseline_2": base2}

    cheap = with_costs(s2_config, 0.5)
    strat_cheap = backtest(frame, cheap)
    base1_cheap = bl.run_buy_and_hold(
        bl.baseline_1_weights(budgets), inputs, with_costs(base_config, 0.5), FIRST_DAY, last
    )

    last_day = pd.Timestamp(decide_end).date()
    report = {
        "strategy": cfg.name,
        "run": run.run_id,
        "config_hash": run.meta.get("config_hash"),
        "data_end": run.meta.get("data_end"),
        "window": {"start": str(FIRST_DAY), "end": str(last), "holdout_start": HOLDOUT_START},
        "decision_end": str(decide_end),
        "seed": seed,
        "limits": asdict(limits),
        "budgets": budgets,
        "strategy_configs_tried": STRATEGY_CONFIGS_TRIED,
        "s2_config": repr(cfg),
        "min_trade_share": {
            "s2": s2_config.min_trade_share,
            "baselines": base_config.min_trade_share,
        },
        "costs": {
            "commission": dict(base_config.costs.commission),
            "slippage_bps": dict(base_config.costs.slippage_bps),
            "sec_fee": base_config.costs.sec_fee,
            "fx_spread": base_config.costs.fx_spread,
        },
        "taxes": {k: str(v) for k, v in asdict(base_config.taxes).items()},
        "initial_capital_krw": base_config.initial_capital_krw,
        "edge": {
            "kind": EDGE_KIND,
            "share": share,
            "lookups": len(looks),
            "by_class": edge_summary(looks),
            "range_diagnostic_last": {
                cls: asdict(edge.status(last_day, cls, S2_HORIZON, "range"))
                for cls in ("stock", "crypto")
            },
            "symbol_vol_dm": dms,
        },
        "actions": {cls: dict(Counter(g["action"])) for cls, g in frame.groupby("asset_class")},
        "strategy_summary": summarize(strat, baselines, limits=limits),
        "strategy_drawdowns": drawdowns(strat),
        "strategy_mdd_bootstrap_p_over_limit": bootstrap_mdd_exceedance(
            strat.returns, limits.max_drawdown, seed=seed
        ),
        "underfilled": underfilled_days(strat, frame),
        "baselines": {
            **{k: summarize(v, {}, limits=limits) for k, v in suite.items()},
            "baseline_2": summarize(base2, {}, limits=limits),
            "baseline_2_no_limits_sensitivity": summarize(base2_free, {}, limits=limits),
        },
        "vol_scale_k": volatility_scale(strat.returns, suite["baseline_1"].returns),
        "gate": gate.to_dict(),
        "sharpe_vs_baseline_1": asdict(
            sharpe_test(strat.returns, suite["baseline_1"].returns, n_trials=STRATEGY_CONFIGS_TRIED)
        ),
        "sharpe_vs_d2": asdict(
            sharpe_test(strat.returns, d2.returns, n_trials=STRATEGY_CONFIGS_TRIED)
        ),
        "costs_x0.5": {
            "strategy": summarize(strat_cheap, {"baseline_1": base1_cheap}, limits=limits),
            "baseline_1": summarize(base1_cheap, {}, limits=limits),
        },
        "diagnostics_not_adoptable": {
            "d1_edge_gate_ignored": {
                "summary": summarize(d1, baselines, limits=limits),
                "excess_vs_baseline_1": asdict(
                    excess_return_test(d1.returns, suite["baseline_1"].returns, seed=seed)
                ),
                "drawdowns": drawdowns(d1),
            },
            "d2_ewma_width": {
                "summary": summarize(d2, baselines, limits=limits),
                "drawdowns": drawdowns(d2),
            },
            "baseline_1_fixed_exposure": {
                "exposure": mean_exposure,
                "summary": summarize(fixed, {}, limits=limits),
            },
        },
        "holdout": {"opened": False, "reason": "not opened by this run (D-015 ②)"},
        "strategy_config_hash": strategy_config_hash(
            {"strategy": cfg.name, "run": run.run_id, "config": repr(cfg)}
        ),
    }
    report = _clean(report)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str, ensure_ascii=False)
    return report


if __name__ == "__main__":  # pragma: no cover
    assess(sys.argv[1] if len(sys.argv) > 1 else None)
