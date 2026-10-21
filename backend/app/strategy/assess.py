"""Wave B: S1 against baselines ① and ② on the walk-forward window (D-015 gate ①).

    py -m uv run python -m app.strategy.assess <out.json>   # from backend/

Inputs: the current forecast run's `oos_universe_{h}` (walk-forward rows only, D-022),
strict-loader prices up to the day before the holdout (D-020), the settings' risk limits
and class budgets. The holdout is opened (`open_strategy_holdout`) only if gate ① passes.

Diagnostics marked `not_adoptable` (S1 with the edge gate ignored, random scores, the
top-minus-bottom rank spread) explain a result; they are never strategies and never
counted in STRATEGY_CONFIGS_TRIED.
"""

import json
import math
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd

from app.forecast import metrics
from app.forecast.report import EdgeStatus, PointInTimeEdge
from app.strategy.backtest import BacktestConfig, BacktestResult, run_backtest, summarize
from app.strategy.risk import RiskLimits, target_weights

FIRST_DAY = date(2017, 1, 1)  # first walk-forward test block (data start + 730 days)


def s1_decisions(
    frame: pd.DataFrame, budgets: Mapping[str, float], limits: RiskLimits
) -> pd.DataFrame:
    """Decisions [date, symbol, weight] from `signal_frame` rows via risk's S1 sizing."""
    rows = []
    for (as_of, _cls), g in frame.groupby(["as_of", "asset_class"], sort=True):
        signals = [
            SimpleNamespace(
                symbol=r.symbol, asset_class=r.asset_class, held_after=bool(r.held_after)
            )
            for r in g.itertuples(index=False)
        ]
        for symbol, w in target_weights(signals, budgets, limits).items():
            rows.append((pd.Timestamp(as_of), symbol, float(w)))
    return pd.DataFrame(rows, columns=["date", "symbol", "weight"])


def edge_lookups(edge_at, schedule: str, horizon: str, start: date, end: date) -> list:
    """One lookup per (asset class, decision date) in the window: the N-2 denominator."""
    from app.strategy.signals import decision_dates

    out = []
    for cls in ("stock", "crypto"):
        for d in decision_dates(schedule, cls, start, end):
            out.append((cls, d, edge_at(d, cls, horizon)))
    return out


def buy_stats(frame: pd.DataFrame) -> dict:
    out = {}
    for cls, g in frame.groupby("asset_class"):
        per_date = g.groupby("as_of")["action"].apply(lambda a: int((a == "buy").sum()))
        actions = Counter(g["action"])
        out[cls] = {
            "decision_dates": int(per_date.size),
            "buys": int(per_date.sum()),
            "mean_buys_per_date": float(per_date.mean()) if per_date.size else 0.0,
            "dates_with_a_buy": float((per_date > 0).mean()) if per_date.size else 0.0,
            "actions": dict(actions),
            "reasons": dict(Counter(g["reason"].fillna("none"))),
        }
    return out


def rank_spread(oos: pd.DataFrame, dates_by_class: Mapping[str, list], lags: int) -> dict:
    """Diagnostic (STRATEGIES S1): mean next-period return of the top third by score minus
    the bottom third, on decision dates, walk-forward rows of the strategy universe."""
    out = {}
    score = oos["gbdt_p_up"] - oos["climatology_p_up"].fillna(0.0)
    df = oos.assign(_s=score)
    for cls, when in dates_by_class.items():
        when = set(pd.to_datetime(list(when)))
        g = df[(df["asset_class"] == cls) & df["date"].isin(when)].dropna(subset=["fr", "_s"])
        spreads = []
        for _, day in g.groupby("date"):
            n = len(day)
            if n < 3:
                continue
            k = math.ceil(n / 3)
            ranked = day.sort_values(["_s", "symbol"], ascending=[False, True])
            spreads.append(ranked["fr"].head(k).mean() - ranked["fr"].tail(k).mean())
        x = np.asarray(spreads, dtype=float)
        t, p = metrics.mean_test(x, lags) if len(x) else (0.0, 1.0)
        out[cls] = {
            "dates": len(x),
            "mean_spread": float(x.mean()) if len(x) else None,
            "hac_t": t,
            "p_one_sided": p,
        }
    return out


def _clean(obj):
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_clean(v) for v in obj]
    if isinstance(obj, float | np.floating):
        return float(obj) if math.isfinite(obj) else None
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _summary(result: BacktestResult, baselines: dict, limits: RiskLimits) -> dict:
    return summarize(result, baselines, limits=limits)


def assess(out_path: str | None = None, *, seed: int = 0) -> dict:  # pragma: no cover
    from app.config import get_settings
    from app.db.session import SessionLocal
    from app.deps import get_provider, get_quote_cache
    from app.forecast import store
    from app.forecast.cv import HOLDOUT_START
    from app.forecast.panel import HORIZON_DAYS
    from app.forecast.universe import strategy_symbols
    from app.services.market_data import MarketDataService
    from app.strategy import baselines as bl
    from app.strategy import s1, signals
    from app.strategy.backtest import load_inputs
    from app.strategy.evaluation import (
        STRATEGY_CONFIGS_TRIED,
        adoption_gate,
        edge_share,
        excess_return_test,
        open_strategy_holdout,
        sharpe_test,
        strategy_config_hash,
        volatility_scale,
        walk_forward_decision_end,
    )
    from app.strategy.risk import budgets_from_settings

    settings = get_settings()
    limits = RiskLimits.from_settings(settings)
    budgets = budgets_from_settings(settings)
    universe = strategy_symbols()
    last = pd.Timestamp(HOLDOUT_START).date() - timedelta(days=1)
    bt_config = BacktestConfig()
    run_dir = settings.artifacts_dir / store.GLOBAL / "runs"
    current = json.loads((settings.artifacts_dir / store.GLOBAL / "current.json").read_text())
    run = store.load(run_dir / current["run"])

    oos = {}
    for h in ("1d", "1w", "1m"):
        frame = run.universe_oos(h)
        oos[h] = frame[frame["segment"] == "walk_forward"].reset_index(drop=True)
    edge = PointInTimeEdge(oos, rank_symbols=universe)

    with SessionLocal() as db:
        market = MarketDataService(db, get_provider(), get_quote_cache())
        inputs = load_inputs(market, universe, date(2015, 1, 1), last)

    report: dict = {
        "run": run.run_id,
        "config_hash": run.meta.get("config_hash"),
        "data_end": run.meta.get("data_end"),
        "window": {"start": str(FIRST_DAY), "end": str(last), "holdout_start": HOLDOUT_START},
        "seed": seed,
        "limits": asdict(limits),
        "budgets": budgets,
        "strategy_configs_tried": STRATEGY_CONFIGS_TRIED,
        "round_trip_costs": s1.round_trip_costs(),
        "costs": {
            "commission": dict(bt_config.costs.commission),
            "slippage_bps": dict(bt_config.costs.slippage_bps),
            "sec_fee": bt_config.costs.sec_fee,
            "fx_spread": bt_config.costs.fx_spread,
        },
        "taxes": {k: str(v) for k, v in asdict(bt_config.taxes).items()},
        "initial_capital_krw": bt_config.initial_capital_krw,
        "fill": bt_config.fill,
        "liquidate_at_end": bt_config.liquidate_at_end,
    }

    # Baselines, recomputed with the settings' budgets (same as the earlier constants).
    gr = bl.GResearchConfig()
    gr_panel = bl.gresearch_panel(inputs.bars, dict(universe), gr)
    gr_oos = bl.gresearch_oos(gr_panel, gr)

    for cfg in (s1.s1_1w(s1.round_trip_costs()), s1.s1_1m(s1.round_trip_costs())):
        h = cfg.horizon
        rows = oos[h][oos[h]["symbol"].isin(universe)]
        decide_end = walk_forward_decision_end(oos[h])
        frame = signals.signal_frame(rows, edge.edge_at, cfg, start=FIRST_DAY, end=decide_end)
        decisions = s1_decisions(frame, budgets, limits)
        strat = run_backtest(decisions, inputs, bt_config, limits=limits, start=FIRST_DAY, end=last)

        suite = bl.baseline_1_suite(
            inputs, bt_config, FIRST_DAY, last, strategy_returns=strat.returns, budgets=budgets
        )
        freq = "W" if cfg.schedule == "weekly" else "M"
        gr_dec = bl.gresearch_decisions(gr_oos, FIRST_DAY, decide_end, freq=freq, budgets=budgets)
        base2 = run_backtest(gr_dec, inputs, bt_config, limits=limits, start=FIRST_DAY, end=last)

        looks = edge_lookups(edge.edge_at, cfg.schedule, h, FIRST_DAY, decide_end)
        share = edge_share([s for _, _, s in looks])
        gate = adoption_gate(
            strat, suite["baseline_1"], base2, suite["baseline_1_vol_matched"],
            edge_share=share, limits=limits, seed=seed,
        )  # fmt: skip
        baselines = {"baseline_1": suite["baseline_1"], "baseline_2": base2}

        # Diagnostics, not adoptable and not counted (CLAUDE.md: analyse, do not tune).
        def always(d, cls, hz):
            return EdgeStatus(True, "diagnostic_edge_ignored")

        no_gate = signals.signal_frame(rows, always, cfg, start=FIRST_DAY, end=decide_end)
        no_gate_bt = run_backtest(
            s1_decisions(no_gate, budgets, limits), inputs, bt_config,
            limits=limits, start=FIRST_DAY, end=last,
        )  # fmt: skip
        rng = np.random.default_rng(seed)
        randomized = rows.assign(gbdt_p_up=rng.uniform(0.3, 0.7, len(rows)))
        rand = signals.signal_frame(randomized, always, cfg, start=FIRST_DAY, end=decide_end)
        rand_bt = run_backtest(
            s1_decisions(rand, budgets, limits), inputs, bt_config,
            limits=limits, start=FIRST_DAY, end=last,
        )  # fmt: skip
        dates_by_class = {
            cls: signals.decision_dates(cfg.schedule, cls, FIRST_DAY, decide_end)
            for cls in ("stock", "crypto")
        }

        section = {
            "decision_end": str(decide_end),
            "signal_rows": len(frame),
            "edge": {
                "share": share,
                "lookups": len(looks),
                "by_class": {
                    cls: {
                        "lookups": sum(1 for c, _, _ in looks if c == cls),
                        "with_edge": sum(1 for c, _, s in looks if c == cls and s.edge),
                        "reasons": dict(Counter(s.reason for c, _, s in looks if c == cls)),
                    }
                    for cls in ("stock", "crypto")
                },
                "last_lookup": {
                    cls: asdict(next(s for c, d, s in reversed(looks) if c == cls))
                    for cls in ("stock", "crypto")
                },
            },
            "buys": buy_stats(frame),
            "decisions": int(decisions["date"].nunique()) if len(decisions) else 0,
            "strategy": _summary(strat, baselines, limits),
            "baselines": {
                **{k: _summary(v, {}, limits) for k, v in suite.items()},
                "baseline_2": _summary(base2, {}, limits),
            },
            "vol_scale_k": volatility_scale(strat.returns, suite["baseline_1"].returns),
            "gate": gate.to_dict(),
            "sharpe_vs_baseline_1": asdict(
                sharpe_test(
                    strat.returns, suite["baseline_1"].returns, n_trials=STRATEGY_CONFIGS_TRIED
                )
            ),
            "diagnostics_not_adoptable": {
                "edge_gate_ignored": {
                    "summary": _summary(no_gate_bt, baselines, limits),
                    "buys": buy_stats(no_gate),
                    "excess_vs_baseline_1": asdict(
                        excess_return_test(
                            no_gate_bt.returns, suite["baseline_1"].returns, seed=seed
                        )
                    ),
                },
                "random_scores_edge_ignored": {
                    "summary": _summary(rand_bt, baselines, limits),
                    "buys": buy_stats(rand),
                },
                "rank_spread": rank_spread(rows, dates_by_class, HORIZON_DAYS[h]),
            },
        }
        holdout = None
        if gate.status == "candidate" and cfg.name == "S1-1w":
            access = open_strategy_holdout(
                {"strategy": cfg.name, "run": run.run_id, "config": repr(cfg)},
                pd.Timestamp(run.meta["data_end"]).date(),
                note="S1-1w passed gate ①",
            )
            holdout = {"opened": True, "config_hash": access.config_hash}
        section["holdout"] = holdout or {"opened": False, "reason": "gate ① not passed"}
        section["strategy_config_hash"] = strategy_config_hash(
            {"strategy": cfg.name, "run": run.run_id, "config": repr(cfg)}
        )
        report[cfg.name] = section

    report = _clean(report)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str, ensure_ascii=False)
    return report


if __name__ == "__main__":  # pragma: no cover
    assess(sys.argv[1] if len(sys.argv) > 1 else None)
