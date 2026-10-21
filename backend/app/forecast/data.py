"""Load the training universe and context series through the price cache.

Only final bars are used (`final_only=True`): an unfinished session would leak an intraday
price into a row labelled as a close. The first load downloads full histories (about a
minute for the whole universe); later loads only fetch the missing days.

`load_inputs` feeds the forecaster: reference assets that fail are skipped and listed in
`missing`, but benchmarks and context series are required. `load_daily` / `load_usd_krw`
(bottom of the file) feed strategies, backtests and paper trading and never degrade:
anything missing raises DataUnavailableError.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd

from app.data.assets import FX_USDKRW
from app.data.calendar import calendar_kind, expected_dates, last_final_date
from app.data.provider import DataUnavailableError, MarketDataError, split_adjusted_dividends
from app.data.quality import FX_MAX_GAP_DAYS, ohlc_ok
from app.data.series import align_daily, total_return_index
from app.forecast import universe
from app.forecast.panel import AssetClass, AssetSeries, ContextSeries
from app.services.market_data import MarketDataService, SymbolNotFoundError

log = logging.getLogger(__name__)

# Long enough for two years of warm-up and several years of walk-forward folds.
DEFAULT_START = date(2015, 1, 1)


@dataclass
class Inputs:
    assets: dict[str, AssetSeries]
    context: list[ContextSeries]
    benchmarks: dict[AssetClass, pd.Series]
    missing: list[str] = field(default_factory=list)

    @property
    def data_end(self) -> date:
        return max(a.bars.index.max() for a in self.assets.values())

    def context_close(self, name: str) -> pd.Series | None:
        for c in self.context:
            if c.name == name:
                return c.bars["close"]
        return None


def bars_frame(bars) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "adj_close": [b.adj_close for b in bars],
            "volume": [b.volume for b in bars],
        },
        index=[b.date for b in bars],
    ).sort_index()


# The strict loader accepts a first bar this long after the requested start (a holiday or a
# weekend at the start is not a late listing).
LATE_START_GRACE = timedelta(days=7)

# How old reference assets may be at inference: they only feed cross-sectional ranks.
REFERENCE_MAX_AGE = timedelta(hours=20)


MIN_BARS = 300


def _load(
    market: MarketDataService,
    symbol: str,
    start: date,
    max_age: timedelta | None = None,
    required: bool = False,
) -> pd.DataFrame | None:
    """Final bars of one symbol, or None when it is unavailable or too short.

    `required` symbols (benchmarks and context series) raise DataUnavailableError instead:
    without them the panel would silently lose features the model was trained with.
    """
    try:
        bars = market.get_history(symbol, start, final_only=True, max_age=max_age)
    except (SymbolNotFoundError, MarketDataError) as exc:
        if required:
            raise DataUnavailableError(f"{symbol}: required series unavailable ({exc})") from exc
        log.warning("Skipping %s: %s", symbol, exc)
        return None
    if len(bars) < MIN_BARS:
        if required:
            raise DataUnavailableError(f"{symbol}: only {len(bars)} final bars since {start}")
        return None
    return bars_frame(bars)


def load_inputs(
    market: MarketDataService,
    held: Iterable[tuple[str, AssetClass]],
    start: date = DEFAULT_START,
    cached_reference: bool = False,
) -> Inputs:
    """Held symbols (in their USD form, e.g. BTC-USD) plus the reference universe.

    `cached_reference` refreshes reference assets at most every REFERENCE_MAX_AGE (for
    inference, where they only feed cross-sectional ranks). Held symbols and context series
    are always brought up to date.
    """
    held = dict(held)
    wanted = universe.reference_symbols()
    for symbol, cls in held.items():
        wanted.setdefault(symbol, cls)
    context_symbols = {symbol for symbol, _, _ in universe.CONTEXT.values()}
    required = context_symbols | {universe.STOCK_BENCHMARK, universe.CRYPTO_BENCHMARK}

    assets: dict[str, AssetSeries] = {}
    missing: list[str] = []
    for symbol, cls in wanted.items():
        stale_ok = cached_reference and symbol not in held and symbol not in context_symbols
        df = _load(
            market,
            symbol,
            start,
            REFERENCE_MAX_AGE if stale_ok else None,
            required=symbol in required,
        )
        if df is None:
            missing.append(symbol)
        else:
            assets[symbol] = AssetSeries(cls, df)

    context: list[ContextSeries] = []
    frames: dict[str, pd.DataFrame] = {}
    for name, (symbol, kind, lag) in universe.CONTEXT.items():
        df = (
            assets[symbol].bars if symbol in assets else _load(market, symbol, start, required=True)
        )
        frames[name] = df
        context.append(ContextSeries(name, df, lag, kind))
    if "vix" in frames and "vix3m" in frames:
        # Term structure: short-dated fear above long-dated marks stress.
        ratio = (frames["vix"]["close"] / frames["vix3m"]["close"]).dropna()
        context.append(
            ContextSeries(
                "vix_term", pd.DataFrame({"close": ratio}), universe.CONTEXT["vix"][2], "level"
            )
        )

    benchmarks: dict[AssetClass, pd.Series] = {}
    for cls, symbol in (("stock", universe.STOCK_BENCHMARK), ("crypto", universe.CRYPTO_BENCHMARK)):
        if symbol in assets:
            benchmarks[cls] = assets[symbol].bars["adj_close"]
    return Inputs(assets, context, benchmarks, missing)


# --- strict loader for strategies, backtests and paper trading -------------------------
#
# Unlike `load_inputs`, nothing here degrades quietly: a missing symbol, a hole in the
# calendar, a stale tail or an unusable open raises DataUnavailableError.


@dataclass(frozen=True)
class DailyBars:
    symbol: str
    # DatetimeIndex of bar dates. open/high/low/close are split-adjusted (Yahoo "Close"),
    # adj_close also reinvests gross dividends. ohlc_ok is False where the intraday range is
    # broken (see app.data.quality); open and close are always usable.
    bars: pd.DataFrame
    # Ex-date -> split-adjusted gross cash dividend per share, in the quote currency. Empty
    # for coins and FX.
    dividends: pd.Series
    # Calendar dates (python dates) the calendar expected but the provider has no bar for.
    # Only Yahoo FX may have any (London holidays); other symbols raise instead.
    missing: tuple[date, ...] = ()

    def total_return(self, withholding: float) -> pd.Series:
        """Close with dividends net of `withholding` reinvested; equals adj_close at 0."""
        return total_return_index(self.bars["close"], self.dividends, withholding)


def load_daily(
    market: MarketDataService,
    symbols: Iterable[str],
    start: date,
    end: date | None = None,
    *,
    allow_late_start: bool = False,
    require_open: bool = True,
) -> dict[str, DailyBars]:
    """Final daily bars and dividends for each symbol over [start, end] (end: latest final).

    Raises DataUnavailableError when a symbol is unknown or the provider fails; when its
    history starts more than a week after `start` (unless `allow_late_start`, then it starts
    at listing); when a calendar date is missing (NYSE sessions for stocks, every day for
    coins; Yahoo FX may skip holidays but not more than FX_MAX_GAP_DAYS); when the newest
    final bar the calendar promises is absent; or, with `require_open`, when a bar has no
    usable open (next-open execution needs it).
    """
    now_utc = market.utc_now()
    today = market.now().date()
    end = min(end or today, today)
    out: dict[str, DailyBars] = {}
    for symbol in symbols:
        out[symbol] = _load_strict(
            market, symbol, start, end, now_utc, allow_late_start, require_open
        )
    return out


def _load_strict(
    market: MarketDataService,
    symbol: str,
    start: date,
    end: date,
    now_utc: datetime,
    allow_late_start: bool,
    require_open: bool,
) -> DailyBars:
    def fail(reason: str) -> DataUnavailableError:
        return DataUnavailableError(f"{symbol}: {reason}")

    try:
        rows = market.get_history(symbol, start, end, final_only=True)
    except SymbolNotFoundError as exc:
        raise fail("unknown symbol") from exc
    except MarketDataError as exc:
        raise fail(f"provider failed ({exc})") from exc
    if not rows:
        raise fail(f"no final bars in {start}..{end}")

    kind = calendar_kind(symbol)
    first, last = rows[0].date, rows[-1].date
    if first > start + LATE_START_GRACE and not allow_late_start:
        raise fail(f"history starts {first}, after the requested {start}")

    expected_last = last_final_date(symbol, end, now_utc)
    lag = (expected_last - last).days if expected_last and expected_last > last else 0
    if lag > (FX_MAX_GAP_DAYS if kind == "weekdays" else 0):
        raise fail(f"newest final bar is {last}, expected {expected_last}")

    have = {r.date for r in rows}
    missing = [d for d in expected_dates(symbol, first, last) if d not in have]
    if kind == "weekdays":
        dates = sorted(have)
        gaps = [
            (a, b) for a, b in zip(dates, dates[1:], strict=False) if (b - a).days > FX_MAX_GAP_DAYS
        ]
        if gaps:
            raise fail(f"gap longer than {FX_MAX_GAP_DAYS} days: {gaps[:3]}")
    elif missing:
        raise fail(f"{len(missing)} calendar dates without a bar, e.g. {missing[:5]}")

    df = bars_frame(rows)
    df.index = pd.DatetimeIndex(df.index)
    df["ohlc_ok"] = [
        ohlc_ok(o, h, lo, c)
        for o, h, lo, c in zip(df["open"], df["high"], df["low"], df["close"], strict=True)
    ]
    if require_open:
        bad = df.index[~(df["open"] > 0)]
        if len(bad):
            raise fail(f"{len(bad)} bars without a usable open, e.g. {[d.date() for d in bad[:5]]}")

    dividends = pd.Series(dtype=float)
    if kind == "xnys":
        try:
            events = market.provider.get_actions(symbol)
        except MarketDataError as exc:
            raise fail(f"dividends unavailable ({exc})") from exc
        divs = [
            (pd.Timestamp(e.date), float(e.value))
            for e in split_adjusted_dividends(events)
            if e.kind == "dividend" and first < e.date <= last
        ]
        if divs:
            dividends = pd.Series(dict(divs)).sort_index()
    return DailyBars(symbol, df, dividends, tuple(missing))


def load_usd_krw(
    market: MarketDataService,
    start: date,
    end: date | None = None,
    max_staleness_days: int = FX_MAX_GAP_DAYS,
) -> pd.Series:
    """USD/KRW (KRW per dollar) for every calendar day in [start, end], as known at D+1 00:00
    UTC (see app.data.series). Weekends and holidays carry the previous rate; a day whose
    latest rate is older than `max_staleness_days` raises DataUnavailableError."""
    end = min(end or market.now().date(), market.now().date())
    fx = load_daily(market, [FX_USDKRW], start - timedelta(days=10), end, require_open=False)[
        FX_USDKRW
    ]
    aligned = align_daily({FX_USDKRW: fx.bars["close"]}, start, end, max_staleness_days)
    rate = aligned.values[FX_USDKRW]
    if rate.isna().any():
        bad = rate.index[rate.isna()]
        raise DataUnavailableError(
            f"{FX_USDKRW}: no rate within {max_staleness_days} days for {len(bad)} days, "
            f"e.g. {[d.date() for d in bad[:5]]}"
        )
    return rate
