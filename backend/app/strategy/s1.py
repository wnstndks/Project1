"""S1: rank within an asset class, long only (registered in docs/dev/STRATEGIES.md).

Everything here is fixed by the registration. Changing a value after seeing results is a
new strategy configuration: raise STRATEGY_CONFIGS_TRIED and log it in STRATEGIES.md.
"""

from collections.abc import Mapping
from dataclasses import replace

from app.forecast.panel import AssetClass
from app.forecast.universe import LARGE_CAPS, strategy_symbols
from app.strategy.backtest import CostModel, instrument
from app.strategy.signals import SignalConfig

# Share of the portfolio each asset class may use; the rest of a class's share stays cash
# when fewer assets are held. Coins are about four times as volatile, so 0.8/0.2 roughly
# balances their risk (0.78/0.22, rounded). The baseline SPY/BTC mix uses the same split.
CLASS_BUDGETS: Mapping[AssetClass, float] = {"stock": 0.80, "crypto": 0.20}


def round_trip_costs(
    model: CostModel | None = None, universe: Mapping[str, AssetClass] | None = None
) -> dict[AssetClass, float]:
    """The entry hurdle's cost per asset class: the dearest round trip in the class under
    the backtest's cost model, so the hurdle is never below what a trade actually costs.
    Backtests and paper trading both take it from here (registered value)."""
    model = model or CostModel()
    out: dict[AssetClass, float] = {}
    for symbol, cls in (universe or strategy_symbols()).items():
        out[cls] = max(out.get(cls, 0.0), model.round_trip(instrument(symbol, cls)))
    return out


def s1_1w(round_trip_cost: Mapping[AssetClass, float]) -> SignalConfig:
    """The main configuration: 1w forecasts, weekly decisions. Adoption is judged on it."""
    return SignalConfig(
        name="S1-1w",
        horizon="1w",
        schedule="weekly",
        round_trip_cost=dict(round_trip_cost),
        universe=strategy_symbols(),
    )


def s1_1m(round_trip_cost: Mapping[AssetClass, float]) -> SignalConfig:
    """The secondary configuration: 1m forecasts, monthly decisions. Reported only."""
    return SignalConfig(
        name="S1-1m",
        horizon="1m",
        schedule="monthly",
        round_trip_cost=dict(round_trip_cost),
        universe=strategy_symbols(),
    )


def large_cap_reference(config: SignalConfig) -> SignalConfig:
    """The same rule on the hindsight-picked large caps (ISSUE-020): reported separately,
    never used to adopt. Stocks only, so the coin side yields no signals."""
    return replace(
        config, name=f"{config.name}-large-caps", universe={s: "stock" for s in LARGE_CAPS}
    )
