"""Panel returns follow the calendar, not bar order (ISSUE-010), and the run config hash
covers every setting but not the holdings (ISSUE-007)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.data.calendar import expected_dates
from app.forecast import train, universe
from app.forecast.models import PooledGBDT
from app.forecast.panel import HORIZON_DAYS, HORIZONS, AssetSeries, ContextSeries, build_panel


def bars(dates) -> pd.DataFrame:
    dates = pd.DatetimeIndex(dates)
    rng = np.random.default_rng(0)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, len(dates))))
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "adj_close": close,
            "volume": 1e6,
        },
        index=dates,
    )


@pytest.mark.parametrize(
    ("cls", "dates", "gap", "before", "after"),
    [
        (
            "crypto",
            pd.date_range("2021-01-01", "2021-06-30"),
            "2021-03-10",
            "2021-03-09",
            "2021-03-11",
        ),
        # 2021-03-10 is a Wednesday session.
        (
            "stock",
            pd.bdate_range("2021-01-01", "2021-06-30"),
            "2021-03-10",
            "2021-03-09",
            "2021-03-11",
        ),
    ],
)
def test_returns_and_targets_do_not_span_a_missing_bar(cls, dates, gap, before, after):
    full = bars(dates)
    holed = full.drop(pd.Timestamp(gap))
    panel = build_panel({"A": AssetSeries(cls, holed)}).set_index("date")
    log_p = np.log(full["adj_close"])
    # The day after the hole has no 1-day return, the day before no 1-day target.
    assert np.isnan(panel.loc[after, "r1"])
    assert np.isnan(panel.loc[before, "fr_1d"])
    # Longer targets are measured between dates, not bars: a week after Thursday
    # 2021-03-04 is 2021-03-11 for both (7 coin days, 5 NYSE sessions).
    t = pd.Timestamp("2021-03-04")
    expected = log_p[pd.Timestamp("2021-03-11")] - log_p[t]
    assert panel.loc[t, "fr_1w"] == pytest.approx(expected)
    assert pd.Timestamp(gap) not in panel.index


def test_stock_rows_see_vix_and_rates_a_day_late():
    for name in ("vix", "vix3m", "us10y", "btc", "dxy", "usdkrw"):
        assert universe.CONTEXT[name][2]["stock"] == 1


def test_context_lag_is_by_date():
    days = pd.bdate_range("2021-01-01", "2021-03-31")
    vix = pd.DataFrame({"close": np.arange(len(days), dtype=float) + 10}, index=days)
    ctx = [ContextSeries("vix", vix, {"stock": 1, "crypto": 0}, "level")]
    panel = build_panel({"A": AssetSeries("stock", bars(days))}, ctx).set_index("date")
    # Monday's row sees Friday's close, Tuesday's row Monday's.
    assert panel.loc["2021-03-08", "vix"] == vix.loc["2021-03-05", "close"]
    assert panel.loc["2021-03-09", "vix"] == vix.loc["2021-03-08", "close"]


def test_config_hash_tracks_settings_but_not_holdings():
    feats = ["r1", "r5"]
    ctx = [ContextSeries("vix", pd.DataFrame({"close": [1.0]}), {"stock": 1, "crypto": 0})]
    base = train.run_config(feats, PooledGBDT(feats, engine="sklearn"), {"1d": {}}, ctx)
    same = train.run_config(feats, PooledGBDT(feats, engine="sklearn"), {"1d": {}}, ctx)
    assert train.config_hash(base) == train.config_hash(same)
    assert "configs_tried" not in base

    other = PooledGBDT(feats, engine="sklearn")
    other.SKLEARN_PARAMS = {**other.SKLEARN_PARAMS, "learning_rate": 0.1}
    changed = train.run_config(feats, other, {"1d": {}}, ctx)
    assert train.config_hash(changed) != train.config_hash(base)

    lag0 = [ContextSeries("vix", ctx[0].bars, {"stock": 0, "crypto": 0})]
    assert train.config_hash(
        train.run_config(feats, PooledGBDT(feats, engine="sklearn"), {"1d": {}}, lag0)
    ) != train.config_hash(base)


def test_universe_oos_keeps_reference_symbols_only():
    oos = pd.DataFrame({"symbol": ["SPY", "AAPL", "EOS-USD", "BTC-USD", "ZZZZ"], "y": 0.0})
    out = train.universe_oos(oos)
    assert list(out["symbol"]) == ["SPY", "AAPL", "EOS-USD", "BTC-USD"]
    assert list(out["universe_group"]) == ["strategy", "large_cap", "training_only", "strategy"]


def test_horizon_days_cover_the_longest_span_on_the_calendar():
    # Over the whole window exchange_calendars knows (unscheduled closures included).
    sessions = pd.DatetimeIndex(
        pd.to_datetime(expected_dates("SPY", date(2006, 1, 1), date(2027, 12, 31)))
    )
    for name, steps in HORIZONS.items():
        h = steps["stock"]
        longest = (sessions[h:] - sessions[:-h]).days.max()
        assert HORIZON_DAYS[name] >= longest, name
        assert HORIZON_DAYS[name] >= steps["crypto"], name
