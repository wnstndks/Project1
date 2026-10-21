"""The two strategy baselines, run through the same `run_backtest` as strategies.

Baseline ① (CLAUDE.md): S&P 500 (SPY) and BTC held with the strategy's asset-class
budgets (stocks 0.8, coins 0.2, STRATEGIES.md S1), reset to those weights at the first
open of every month. For diagnosis also: no rebalancing, SPY alone, BTC alone, and the
same mix scaled with cash to the strategy's volatility (D-015 ①-3).

Baseline ② (D-001): the method of the G-Research Crypto Forecasting (2021-22) winners,
ported to daily bars: a LightGBM regression of market-residualized forward returns on
multi-window return and volatility features, trained in the same purged walk-forward, and
traded with S1's buy-only top-rank rule, budgets and costs. Differences from the original
are listed in `GRESEARCH_DIFFERENCES` (and DECISIONS.md D-021).

    py -m uv run python -m app.strategy.baselines   # preliminary baseline ① on real data
"""

import math
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from app.data.calendar import expected_dates
from app.forecast.cv import PurgedWalkForward
from app.forecast.panel import HORIZON_DAYS, HORIZONS
from app.strategy.backtest import (
    BacktestConfig,
    BacktestInputs,
    BacktestResult,
    run_backtest,
)
from app.strategy.evaluation import volatility_scale

# Asset-class budgets of S1 (STRATEGIES.md), shared by baseline ①.
BUDGETS = {"stock": 0.8, "crypto": 0.2}
STOCK_PROXY = "SPY"
CRYPTO_PROXY = "BTC-USD"
BASELINE_1 = {STOCK_PROXY: BUDGETS["stock"], CRYPTO_PROXY: BUDGETS["crypto"]}


def decision_dates(asset_class: str, start: date, end: date, freq: str = "W") -> pd.DatetimeIndex:
    """S1's calendar, fixed in advance: the last NYSE session of each week ("W") or month
    ("M") for stocks; every Sunday, or the last day of each month, for coins (UTC daily
    bars). Only dates in [start, end]."""
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    # Look past `end` so a week or month is only cut where the calendar really ends it.
    ahead = (end + pd.Timedelta(days=40)).date()
    if asset_class == "stock":
        days = pd.DatetimeIndex(expected_dates(STOCK_PROXY, start.date(), ahead))
    else:
        days = pd.date_range(start, ahead, freq="D")
    if days.empty:
        return days
    key = days.to_period("W-SUN" if freq == "W" else "M")
    last = pd.DatetimeIndex(pd.Series(days, index=days).groupby(key).max().to_numpy())
    return last[(last >= start) & (last <= end)].as_unit("ns")


def buy_and_hold_decisions(
    weights: Mapping[str, float],
    start: date,
    end: date,
    *,
    rebalance: bool = True,
) -> pd.DataFrame:
    """Target weights decided on `start` and, with `rebalance`, again on the last calendar
    day of every month (filled at each symbol's next open: the month's first)."""
    dates = [pd.Timestamp(start)]
    if rebalance:
        month_ends = pd.date_range(start, end, freq="ME")
        dates += [d for d in month_ends if d > pd.Timestamp(start) and d < pd.Timestamp(end)]
    rows = [(d, s, float(w)) for d in dates for s, w in weights.items()]
    return pd.DataFrame(rows, columns=["date", "symbol", "weight"])


def run_buy_and_hold(
    weights: Mapping[str, float],
    inputs: BacktestInputs,
    config: BacktestConfig,
    start: date,
    end: date,
    *,
    rebalance: bool = True,
) -> BacktestResult:
    """A baseline is only a weight schedule: same engine, costs, taxes and fills."""
    decisions = buy_and_hold_decisions(weights, start, end, rebalance=rebalance)
    return run_backtest(decisions, inputs, config, start=start, end=end)


def baseline_1_weights(budgets: Mapping[str, float] = BUDGETS) -> dict[str, float]:
    """Baseline ①: the stock budget in SPY, the coin budget in BTC."""
    return {STOCK_PROXY: float(budgets["stock"]), CRYPTO_PROXY: float(budgets["crypto"])}


def baseline_1_suite(
    inputs: BacktestInputs,
    config: BacktestConfig,
    start: date,
    end: date,
    strategy_returns: pd.Series | None = None,
    budgets: Mapping[str, float] = BUDGETS,
) -> dict[str, BacktestResult]:
    """Baseline ① and its diagnostic variants over [start, end]."""
    mix = baseline_1_weights(budgets)
    out = {
        "baseline_1": run_buy_and_hold(mix, inputs, config, start, end),
        "baseline_1_no_rebalance": run_buy_and_hold(
            mix, inputs, config, start, end, rebalance=False
        ),
        "spy": run_buy_and_hold({STOCK_PROXY: 1.0}, inputs, config, start, end),
        "btc": run_buy_and_hold({CRYPTO_PROXY: 1.0}, inputs, config, start, end),
    }
    if strategy_returns is not None:
        k = volatility_scale(strategy_returns, out["baseline_1"].returns)
        scaled = {s: w * k for s, w in mix.items()}
        out["baseline_1_vol_matched"] = run_buy_and_hold(scaled, inputs, config, start, end)
    return out


# --- rank rule shared with S1 ------------------------------------------------------------


def rank_rule_decisions(
    scores: pd.DataFrame,
    dates: Mapping[str, pd.DatetimeIndex],
    budgets: Mapping[str, float] = BUDGETS,
    *,
    min_assets: int = 3,
) -> pd.DataFrame:
    """S1's buy-only rank rule on any score: per class and decision date, rank by score
    (ties by symbol); not held and in the top ceil(n/3) -> buy; held and outside the top
    ceil(2n/3) -> sell; fewer than `min_assets` scored (none at all included) -> sell all of
    the class. Otherwise a symbol without a score that day keeps its state. Held symbols
    share the class budget equally.

    `scores`: [date, symbol, asset_class, score]. Returns decisions [date, symbol, weight].
    """
    rows = []
    for cls, when in dates.items():
        g = scores[scores["asset_class"] == cls]
        by_date = {d: x for d, x in g.groupby("date")}
        universe = sorted(set(g["symbol"]))
        held: set[str] = set()
        for d in when:
            # A decision date without any row is a date with fewer than `min_assets`
            # scores: S1 sells the class then too (too_few_assets), so does this rule.
            day = by_date.get(pd.Timestamp(d), g.iloc[0:0]).dropna(subset=["score"])
            n = len(day)
            if n < min_assets:
                held = set()
            else:
                ranked = day.sort_values(["score", "symbol"], ascending=[False, True])
                rank = {s: i + 1 for i, s in enumerate(ranked["symbol"])}
                enter, keep = math.ceil(n / 3), math.ceil(2 * n / 3)
                for s, r in rank.items():
                    if s not in held and r <= enter:
                        held.add(s)
                    elif s in held and r > keep:
                        held.discard(s)
            w = budgets[cls] / len(held) if held else 0.0
            rows += [(pd.Timestamp(d), s, w if s in held else 0.0) for s in universe]
    return pd.DataFrame(rows, columns=["date", "symbol", "weight"])


# --- baseline ②: G-Research Crypto Forecasting method, daily -----------------------------

# Confirmed: the target is the 15-minute log return from t+1 to t+16 minus beta x the
# weighted market return, beta from rolling 3750-minute averages (host tutorial); the top
# three used LightGBM and credited feature engineering (G-Research wrap-up). Not found:
# the winners' write-up, so their exact features and hyperparameters (확인 필요).
GRESEARCH_DIFFERENCES = (
    "minute bars -> daily bars; 15-minute target -> 1w (5 sessions / 7 coin days)",
    "market = weighted mean of 14 coins -> SPY for stocks, BTC for coins (D-001)",
    "beta from 3750-minute rolling means of the target-horizon returns -> 63-bar "
    "trailing beta of daily returns (no future data in the label's beta)",
    "14 coins -> strategy universe (15 index/sector ETFs, 4 coins), one model per class",
    "winners' feature list and hyperparameters unknown -> multi-window returns, "
    "volatility-scaled returns, returns relative to the class mean, market returns, beta",
    "scored by weighted Pearson correlation, long-short -> traded buy-only with S1's rank "
    "rule (no edge gate, no expected-return hurdle: the model predicts residuals), costs, "
    "taxes, KRW",
    "competition public/private split -> PurgedWalkForward with the fixed holdout",
)


@dataclass(frozen=True)
class GResearchConfig:
    horizon: str = "1w"
    windows: tuple[int, ...] = (1, 5, 10, 21, 63)
    vol_window: int = 20
    beta_window: int = 63
    benchmarks: Mapping[str, str] = field(
        default_factory=lambda: {"stock": STOCK_PROXY, "crypto": CRYPTO_PROXY}
    )
    engine: str = "lightgbm"  # "lightgbm" | "sklearn"
    n_estimators: int = 300
    params: Mapping[str, float] = field(
        default_factory=lambda: {
            "learning_rate": 0.05,
            "num_leaves": 31,
            "min_child_samples": 200,
            "subsample": 0.8,
            "subsample_freq": 1,
            "colsample_bytree": 0.8,
            "reg_lambda": 1.0,
            "random_state": 0,
        }
    )


def _wide(bars: Mapping[str, pd.DataFrame], symbols: list[str], col: str, daily: bool):
    frames = {s: bars[s][col].astype(float) for s in symbols}
    df = pd.DataFrame(frames).sort_index()
    df.index = pd.DatetimeIndex(df.index).normalize()
    if daily and len(df):
        df = df.reindex(pd.date_range(df.index[0], df.index[-1], freq="D"))
    return df


def gresearch_panel(
    bars: Mapping[str, pd.DataFrame],
    classes: Mapping[str, str],
    config: GResearchConfig | None = None,
) -> pd.DataFrame:
    """Features (row t uses bars up to t) and the residual target, one row per bar.

    Target: R = log close(t+h) - log open(t+1), the return a next-open fill earns, minus
    beta x the class benchmark's R. beta is the trailing 63-bar beta of daily returns.
    """
    config = config or GResearchConfig()
    parts = []
    for cls in ("stock", "crypto"):
        symbols = sorted(s for s, c in classes.items() if c == cls and s in bars)
        bench = config.benchmarks[cls]
        if not symbols or bench not in bars:
            continue
        daily = cls == "crypto"
        names = sorted(set(symbols) | {bench})
        close = np.log(_wide(bars, names, "close", daily))
        open_ = np.log(_wide(bars, names, "open", daily))
        h = HORIZONS[config.horizon][cls]
        r1 = close.diff()
        vol = r1.rolling(config.vol_window, min_periods=config.vol_window).std()
        fwd = close.shift(-h) - open_.shift(-1)
        m1 = r1[bench]
        m_var = m1.rolling(config.beta_window, min_periods=40).var()
        beta = pd.DataFrame(
            {s: r1[s].rolling(config.beta_window, min_periods=40).cov(m1) / m_var for s in names}
        )
        target = fwd - beta.mul(fwd[bench], axis=0)
        feats: dict[str, pd.DataFrame] = {}
        for w in config.windows:
            rw = close - close.shift(w)
            feats[f"r{w}"] = rw
            feats[f"z{w}"] = rw / (vol * np.sqrt(w))
            feats[f"rel{w}"] = rw.sub(rw[symbols].mean(axis=1), axis=0)
            feats[f"mkt{w}"] = pd.DataFrame({s: rw[bench] for s in names}, index=rw.index)
        feats["vol20"] = vol
        feats["vol_ratio"] = vol / r1.rolling(63, min_periods=63).std()
        feats["beta"] = beta
        for s in symbols:
            df = pd.DataFrame({k: v[s] for k, v in feats.items()})
            df["target"] = target[s]
            df["has_bar"] = bars[s]["close"].reindex(df.index).notna().to_numpy()
            df = df[df["has_bar"]].drop(columns="has_bar")
            df = df.reset_index(names="date")
            df["symbol"] = s
            df["asset_class"] = cls
            parts.append(df)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def _feature_cols(panel: pd.DataFrame) -> list[str]:
    return [c for c in panel.columns if c not in {"date", "symbol", "asset_class", "target"}]


def _model(config: GResearchConfig):
    if config.engine == "lightgbm":
        import lightgbm as lgb

        return lgb.LGBMRegressor(
            n_estimators=config.n_estimators, verbose=-1, n_jobs=4, **config.params
        )
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(
        max_iter=min(config.n_estimators, 300),
        learning_rate=float(config.params.get("learning_rate", 0.05)),
        min_samples_leaf=int(config.params.get("min_child_samples", 200)),
        random_state=0,
    )


def gresearch_oos(
    panel: pd.DataFrame,
    config: GResearchConfig | None = None,
    cv: PurgedWalkForward | None = None,
    *,
    include_holdout: bool = False,
) -> pd.DataFrame:
    """Out-of-sample predictions per class from purged walk-forward folds, and with
    `include_holdout` the holdout fold (segment "holdout"; only after the strategy's
    holdout look is logged, D-007). Columns: date, symbol, asset_class, score, target,
    segment."""
    config = config or GResearchConfig()
    cv = cv or PurgedWalkForward(horizon_days=HORIZON_DAYS[config.horizon])
    feats = _feature_cols(panel)
    out = []
    for _, g in panel.groupby("asset_class"):
        folds = [(f, "walk_forward") for f in cv.folds(g["date"])]
        if include_holdout:
            folds.append((cv.holdout(g["date"]), "holdout"))
        for fold, segment in folds:
            train = g[(g["date"] < fold.train_end) & g["target"].notna()]
            test = g[(g["date"] >= fold.test_start) & (g["date"] < fold.test_end)]
            if len(train) < 200 or test.empty:
                continue
            model = _model(config)
            model.fit(train[feats], train["target"])
            part = test[["date", "symbol", "asset_class", "target"]].copy()
            part["score"] = model.predict(test[feats])
            part["segment"] = segment
            out.append(part)
    if not out:
        return pd.DataFrame(columns=["date", "symbol", "asset_class", "target", "score"])
    return pd.concat(out, ignore_index=True)


def gresearch_decisions(
    oos: pd.DataFrame,
    start: date,
    end: date,
    symbols: Collection[str] | None = None,
    freq: str = "W",
    budgets: Mapping[str, float] = BUDGETS,
) -> pd.DataFrame:
    """Baseline ② decisions: S1's rank rule on the ported model's scores."""
    scores = oos if symbols is None else oos[oos["symbol"].isin(set(symbols))]
    dates = {cls: decision_dates(cls, start, end, freq) for cls in budgets}
    return rank_rule_decisions(scores[["date", "symbol", "asset_class", "score"]], dates, budgets)


def main() -> None:  # pragma: no cover - needs market data
    """Preliminary baseline ① on real data over the walk-forward window (no forecasts)."""
    import json

    from app.config import get_settings
    from app.db.session import SessionLocal
    from app.deps import get_provider, get_quote_cache
    from app.forecast.cv import HOLDOUT_START
    from app.services.market_data import MarketDataService
    from app.strategy.backtest import load_inputs, summarize, with_costs
    from app.strategy.risk import RiskLimits

    first = date(2017, 1, 1)
    last = pd.Timestamp(HOLDOUT_START).date() - pd.Timedelta(days=1)
    symbols = {STOCK_PROXY: "stock", CRYPTO_PROXY: "crypto"}
    config = BacktestConfig()
    limits = RiskLimits.from_settings(get_settings())
    report = {}
    with SessionLocal() as db:
        market = MarketDataService(db, get_provider(), get_quote_cache())
        inputs = load_inputs(market, symbols, first, last)
        suite = baseline_1_suite(inputs, config, first, last)
        report["primary"] = {k: summarize(v, limits=limits) for k, v in suite.items()}
        cheap = baseline_1_suite(inputs, with_costs(config, 0.5), first, last)
        report["costs_x0.5"] = {k: summarize(v, limits=limits) for k, v in cheap.items()}
        no_tax = BacktestConfig(liquidate_at_end=False)
        report["no_final_liquidation"] = {
            "baseline_1": summarize(
                run_buy_and_hold(BASELINE_1, inputs, no_tax, first, last), limits=limits
            )
        }
        up_first = date(2021, 11, 1)
        up = load_inputs(market, symbols, up_first, last, upbit=True)
        up_weights = {STOCK_PROXY: BUDGETS["stock"], "KRW-BTC": BUDGETS["crypto"]}
        usd_same = run_buy_and_hold(BASELINE_1, inputs, config, up_first, last)
        report["upbit_from_2021_11"] = {
            "usd_x_fx": summarize(usd_same, limits=limits),
            "upbit_krw": summarize(
                run_buy_and_hold(up_weights, up, config, up_first, last), limits=limits
            ),
        }
    print(json.dumps(report, indent=2, default=str))


def gresearch_skill(oos: pd.DataFrame, lags: int = 7) -> dict:
    """Within-class daily rank IC of baseline ②'s scores against its residual target, with
    the HAC t (information only: baseline ② has no edge gate, D-021)."""
    from app.forecast import metrics

    out = {}
    for cls, g in oos[oos["segment"] == "walk_forward"].groupby("asset_class"):
        ic = metrics.daily_ic(g.dropna(subset=["target"]), "score", "target", min_assets=3)
        t, p = metrics.mean_test(ic.to_numpy(), lags)
        share, years = metrics.year_share(ic)
        out[cls] = {
            "dates": len(ic),
            "mean_ic": float(ic.mean()) if len(ic) else None,
            "hac_t": t,
            "p_one_sided": p,
            "year_share": share,
            "years": years,
        }
    return out


def final(out_path: str | None = None) -> dict:  # pragma: no cover - needs market data
    """Wave B baselines ① and ② on real data over the walk-forward window (D-020). The
    holdout is not loaded: bars end the day before HOLDOUT_START."""
    import json
    from dataclasses import asdict

    from app.config import get_settings
    from app.db.session import SessionLocal
    from app.deps import get_provider, get_quote_cache
    from app.forecast.cv import HOLDOUT_START
    from app.forecast.universe import strategy_symbols
    from app.services.market_data import MarketDataService
    from app.strategy.backtest import load_inputs, summarize, with_costs
    from app.strategy.evaluation import excess_return_test, walk_forward_decision_end
    from app.strategy.risk import RiskLimits

    seed = 0
    first = date(2017, 1, 1)
    last = pd.Timestamp(HOLDOUT_START).date() - pd.Timedelta(days=1)
    settings = get_settings()
    limits = RiskLimits.from_settings(settings)
    config = BacktestConfig()
    universe = strategy_symbols()
    report: dict = {
        "window": {"start": str(first), "end": str(last), "holdout_start": HOLDOUT_START},
        "seed": seed,
        "limits": asdict(limits),
        "costs": {
            "commission": dict(config.costs.commission),
            "slippage_bps": dict(config.costs.slippage_bps),
            "sec_fee": config.costs.sec_fee,
            "fx_spread": config.costs.fx_spread,
        },
        "taxes": {k: str(v) for k, v in asdict(config.taxes).items()},
        "initial_capital_krw": config.initial_capital_krw,
    }
    with SessionLocal() as db:
        market = MarketDataService(db, get_provider(), get_quote_cache())
        inputs = load_inputs(market, universe, date(2015, 1, 1), last)
        up_first = date(2021, 10, 21)
        up = load_inputs(
            market, {STOCK_PROXY: "stock", CRYPTO_PROXY: "crypto"}, up_first, last, upbit=True
        )

    def summ(results: dict) -> dict:
        return {k: summarize(v, limits=limits) for k, v in results.items()}

    suite = baseline_1_suite(inputs, config, first, last)
    report["baseline_1"] = summ(suite)
    report["baseline_1_costs_x0.5"] = summ(
        {"baseline_1": run_buy_and_hold(BASELINE_1, inputs, with_costs(config, 0.5), first, last)}
    )
    report["baseline_1_costs_x2"] = summ(
        {"baseline_1": run_buy_and_hold(BASELINE_1, inputs, with_costs(config, 2.0), first, last)}
    )
    up_weights = {STOCK_PROXY: BUDGETS["stock"], "KRW-BTC": BUDGETS["crypto"]}
    report["upbit_sensitivity"] = summ(
        {
            "usd_x_fx": run_buy_and_hold(BASELINE_1, inputs, config, up_first, last),
            "upbit_krw": run_buy_and_hold(up_weights, up, config, up_first, last),
        }
    )

    gr = GResearchConfig()
    classes = {s: c for s, c in universe.items()}
    panel = gresearch_panel(inputs.bars, classes, gr)
    oos = gresearch_oos(panel, gr)
    decide_end = walk_forward_decision_end(oos)
    decisions = gresearch_decisions(oos, first, decide_end)
    b2 = run_backtest(decisions, inputs, config, limits=limits, start=first, end=last)
    b2_cheap = run_backtest(
        decisions, inputs, with_costs(config, 0.5), limits=limits, start=first, end=last
    )
    report["baseline_2"] = {
        "config": {
            "horizon": gr.horizon,
            "windows": list(gr.windows),
            "vol_window": gr.vol_window,
            "beta_window": gr.beta_window,
            "benchmarks": dict(gr.benchmarks),
            "engine": gr.engine,
            "n_estimators": gr.n_estimators,
            "params": dict(gr.params),
        },
        "differences": list(GRESEARCH_DIFFERENCES),
        "oos_rows": len(oos),
        "oos_start": str(oos["date"].min().date()),
        "decision_end": str(decide_end),
        "decisions": int(decisions["date"].nunique()),
        "skill": gresearch_skill(oos),
        "edge_gate": "none (D-021): traded on every decision date",
        "summary": summarize(b2, {"baseline_1": suite["baseline_1"]}, limits=limits),
        "summary_costs_x0.5": summarize(b2_cheap, limits=limits),
        "excess_vs_baseline_1": asdict(
            excess_return_test(b2.returns, suite["baseline_1"].returns, "baseline_1", seed=seed)
        ),
        "trades": {
            "decision_orders": int((b2.trades["kind"] == "decision").sum()),
            "clipped": int((b2.trades["status"] == "clipped").sum()),
            "rejected": int((b2.trades["status"] == "rejected").sum()),
        },
    }
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str, ensure_ascii=False)
    return report


if __name__ == "__main__":  # pragma: no cover
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--final":
        final(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        main()
