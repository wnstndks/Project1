"""Data quality checks, series helpers and the strict loader for strategies and backtests."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app.data.calendar import expected_dates
from app.data.fake_provider import FakeProvider
from app.data.provider import Bar, CorporateEvent, DataUnavailableError
from app.data.quality import check_bars, validate_bars
from app.data.series import align_daily, total_return_index
from app.forecast.data import load_daily, load_usd_krw
from app.services.market_data import MarketDataService, QuoteCache
from tests.conftest import TODAY

# Friday 2026-10-16, 22:00 UTC: the stock bar of TODAY is final, the coin bar is not.
NOW_UTC = datetime(2026, 10, 16, 22, 0, tzinfo=UTC)


def _service(db, provider) -> MarketDataService:
    return MarketDataService(
        db,
        provider,
        QuoteCache(),
        now=lambda: datetime(2026, 10, 17, 7, 0),
        utc_now=lambda: NOW_UTC,
    )


class EditedProvider(FakeProvider):
    """FakeProvider with dates removed or bars changed, to break the strict loader."""

    def __init__(self, drop=(), edit=None, **kw) -> None:
        super().__init__(today=TODAY, **kw)
        self.drop = set(drop)
        self.edit = edit or {}

    def get_history(self, symbol, start, end):
        out = []
        for b in super().get_history(symbol, start, end):
            if b.date in self.drop:
                continue
            out.append(replace(b, **self.edit[b.date]) if b.date in self.edit else b)
        return out


# --- calendar ------------------------------------------------------------------------


def test_expected_dates_follow_each_market_calendar():
    week = (date(2026, 11, 23), date(2026, 11, 29))  # Thanksgiving on Thursday the 26th
    assert len(expected_dates("BTC-USD", *week)) == 7
    assert len(expected_dates("KRW=X", *week)) == 5
    assert date(2026, 11, 26) not in expected_dates("SPY", *week)
    assert len(expected_dates("SPY", *week)) == 4


# --- boundary validation ---------------------------------------------------------------


def test_validate_bars_drops_unusable_closes_and_keeps_broken_ranges():
    d = date(2026, 10, 1)
    bars = [
        Bar(d, 10, 11, 9, 10.5, 10.5, 100),
        Bar(d + timedelta(1), 10, 11, 9, 0.0, 0.0, 100),  # no close
        Bar(d + timedelta(2), 10, 11, 9, float("nan"), 10.0, 100),  # NaN close
        Bar(d + timedelta(3), 0.0, 0.0, 0.0, 20.1, 20.1, float("nan")),  # ^VIX-style
        Bar(d + timedelta(4), 10, 9, 11, 10.0, 10.0, 100),  # high < low
    ]
    kept = validate_bars("^VIX", bars)
    assert [b.date for b in kept] == [d, d + timedelta(3), d + timedelta(4)]
    assert kept[1].volume == 0.0


# --- quality report --------------------------------------------------------------------


def _frame(bars: list[Bar]) -> pd.DataFrame:
    return pd.DataFrame(
        [(b.open, b.high, b.low, b.close, b.adj_close, b.volume) for b in bars],
        columns=["open", "high", "low", "close", "adj_close", "volume"],
        index=[b.date for b in bars],
    )


def test_quality_report_finds_gaps_broken_bars_jumps_and_flat_runs():
    start, end = date(2026, 9, 1), date(2026, 9, 30)
    bars = FakeProvider(today=end).get_history("ETH-USD", start, end)
    by_date = {b.date: b for b in bars}
    by_date.pop(date(2026, 9, 10))
    by_date[date(2026, 9, 12)] = replace(by_date[date(2026, 9, 12)], high=0.0)
    b = by_date[date(2026, 9, 15)]  # opens 5% away from the previous close
    by_date[date(2026, 9, 15)] = replace(b, open=b.open * 1.05, high=max(b.high, b.open * 1.05))
    b = by_date[date(2026, 9, 20)]  # a +65% close
    by_date[date(2026, 9, 20)] = replace(b, close=b.close * 1.65, adj_close=b.adj_close * 1.65)
    for d in (date(2026, 9, 25), date(2026, 9, 26), date(2026, 9, 27)):  # repeated close
        prev = by_date[date(2026, 9, 24)]
        by_date[d] = replace(by_date[d], close=prev.close, adj_close=prev.adj_close)

    rep = check_bars("ETH-USD", _frame(sorted(by_date.values(), key=lambda b: b.date)))
    assert rep.missing == [date(2026, 9, 10)]
    assert rep.max_gap_days == 2
    assert rep.broken_ohlc == [date(2026, 9, 12)]
    assert date(2026, 9, 15) in [d for d, _ in rep.open_gaps]
    assert [d for d, _ in rep.extreme_returns] == [date(2026, 9, 20), date(2026, 9, 21)]
    assert rep.longest_flat_run == 3


def test_quality_report_uses_the_nyse_and_weekday_calendars():
    start, end = date(2026, 11, 20), date(2026, 12, 4)
    spy = FakeProvider(today=end).get_history("SPY", start, end)
    # Fake stock bars exist on every weekday, Thanksgiving included: that bar is "extra".
    rep = check_bars("SPY", _frame(spy))
    assert rep.missing == [] and rep.extra == [date(2026, 11, 26)]
    fx = [b for b in FakeProvider(today=end).get_history("KRW=X", start, end)]
    rep = check_bars("KRW=X", _frame(fx))
    assert len(rep.extra) == 4  # the fake FX series also has weekend bars


# --- total return ----------------------------------------------------------------------


def test_total_return_without_withholding_reproduces_yahoo_adjusted_close():
    idx = pd.to_datetime(["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06"])
    close = pd.Series([100.0, 101.0, 99.0, 100.0, 102.0], index=idx)
    dividends = pd.Series([1.0, 0.5], index=pd.to_datetime(["2026-03-04", "2026-03-06"]))
    # Yahoo: every bar before an ex-date t is multiplied by 1 - D / close[t-1].
    f4, f6 = 1 - 1.0 / 101.0, 1 - 0.5 / 100.0
    adj = close * np.array([f4 * f6, f4 * f6, f6, f6, 1.0])

    tr = total_return_index(close, dividends, withholding=0.0)
    np.testing.assert_allclose(tr.to_numpy(), adj.to_numpy(), rtol=1e-12)
    assert tr.iloc[-1] == close.iloc[-1]

    net = total_return_index(close, dividends, withholding=0.15)
    # 15% withheld: less reinvested, so the index grew less from the same last close.
    assert net.iloc[0] > tr.iloc[0]
    expected0 = 100.0 * (1 - 0.85 / 101.0) * (1 - 0.425 / 100.0)
    assert net.iloc[0] == pytest.approx(expected0)


def test_dividend_on_a_non_trading_date_counts_on_the_next_bar():
    idx = pd.to_datetime(["2026-03-06", "2026-03-09"])  # Friday, Monday
    close = pd.Series([100.0, 100.0], index=idx)
    tr = total_return_index(close, pd.Series([2.0], index=pd.to_datetime(["2026-03-07"])))
    assert tr.iloc[0] == pytest.approx(98.0)
    with pytest.raises(ValueError):
        total_return_index(close, pd.Series(dtype=float), withholding=1.0)


# --- calendar alignment ----------------------------------------------------------------


def test_align_daily_carries_values_forward_up_to_a_limit_with_their_age():
    fx = pd.Series(
        [1300.0, 1310.0, 1320.0], index=pd.to_datetime(["2026-10-01", "2026-10-02", "2026-10-09"])
    )
    out = align_daily({"fx": fx}, date(2026, 10, 1), date(2026, 10, 9), max_staleness_days=3)
    v, age = out.values["fx"], out.age_days["fx"]
    assert v[pd.Timestamp("2026-10-05")] == 1310.0 and age[pd.Timestamp("2026-10-05")] == 3
    assert np.isnan(v[pd.Timestamp("2026-10-06")]) and age[pd.Timestamp("2026-10-06")] == 4
    assert v[pd.Timestamp("2026-10-09")] == 1320.0 and age[pd.Timestamp("2026-10-09")] == 0


def test_align_daily_uses_a_value_known_before_the_window():
    s = pd.Series([5.0], index=pd.to_datetime(["2026-09-30"]))
    out = align_daily({"s": s}, date(2026, 10, 1), date(2026, 10, 2), max_staleness_days=5)
    assert list(out.values["s"]) == [5.0, 5.0]
    assert list(out.age_days["s"]) == [1, 2]


# --- strict loader ---------------------------------------------------------------------


def test_load_daily_returns_final_bars_and_split_adjusted_dividends(db):
    actions = {
        "SPY": [
            CorporateEvent(date(2026, 6, 19), "dividend", Decimal("1.80")),
            CorporateEvent(date(2026, 9, 18), "split", Decimal("2")),
        ]
    }
    provider = EditedProvider(actions=actions)
    out = load_daily(_service(db, provider), ["SPY", "BTC-USD", "KRW=X"], date(2026, 1, 2))
    spy, btc = out["SPY"], out["BTC-USD"]
    assert spy.bars.index[-1] == pd.Timestamp(TODAY)  # stock bar final at 22:00 UTC
    assert btc.bars.index[-1] == pd.Timestamp(TODAY - timedelta(days=1))  # coin is not yet
    # The dividend was paid on pre-split shares: restated on today's (split-adjusted) scale.
    assert spy.dividends.to_dict() == {pd.Timestamp("2026-06-19"): pytest.approx(0.90)}
    assert btc.dividends.empty
    assert {"open", "close", "adj_close", "ohlc_ok"} <= set(spy.bars.columns)
    tr = spy.total_return(0.15)
    assert tr.iloc[-1] == pytest.approx(spy.bars["close"].iloc[-1])
    # Without dividends total return is the close (FakeProvider has adj_close == close).
    np.testing.assert_allclose(out["BTC-USD"].total_return(0.0), btc.bars["adj_close"])


@pytest.mark.parametrize(
    ("symbol", "provider_kw", "message"),
    [
        ("ZZZZ", {"unknown": {"ZZZZ"}}, "unknown symbol"),
        ("SPY", {"drop": {date(2026, 9, 15)}}, "calendar dates without a bar"),
        ("BTC-USD", {"drop": {date(2026, 9, 15)}}, "calendar dates without a bar"),
        ("SPY", {"drop": {TODAY}}, "newest final bar"),
        ("SPY", {"edit": {date(2026, 9, 15): {"open": 0.0}}}, "without a usable open"),
    ],
)
def test_load_daily_raises_instead_of_degrading(db, symbol, provider_kw, message):
    provider = EditedProvider(**provider_kw)
    with pytest.raises(DataUnavailableError, match=message):
        load_daily(_service(db, provider), [symbol], date(2026, 9, 1))


def test_load_daily_rejects_a_late_start_unless_allowed(db):
    late = {date(2026, 1, 1) + timedelta(days=i) for i in range(90)}  # listed in April
    provider = EditedProvider(drop=late)
    svc = _service(db, provider)
    with pytest.raises(DataUnavailableError, match="history starts"):
        load_daily(svc, ["SPY"], date(2026, 1, 2))
    out = load_daily(svc, ["SPY"], date(2026, 1, 2), allow_late_start=True)
    assert out["SPY"].bars.index[0] >= pd.Timestamp("2026-04-01")


def test_load_usd_krw_fills_every_calendar_day(db):
    svc = _service(db, EditedProvider())
    fx = load_usd_krw(svc, date(2026, 9, 1), date(2026, 10, 15))
    assert len(fx) == 45 and fx.notna().all()


def test_load_usd_krw_refuses_long_gaps(db):
    gap = {date(2026, 9, 1) + timedelta(days=i) for i in range(10, 18)}
    with pytest.raises(DataUnavailableError, match="gap longer"):
        load_usd_krw(_service(db, EditedProvider(drop=gap)), date(2026, 9, 1), date(2026, 10, 15))
