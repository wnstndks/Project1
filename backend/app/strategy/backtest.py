"""Strategy backtest: target weights in, a KRW equity curve after costs and taxes out.

A pure function over DataFrames (no DB, no network); prices come from the strict loader
(`app.forecast.data.load_daily`, `load_usd_krw`) through `BacktestInputs`.

Rules (DECISIONS.md D-003, D-008, D-014):
- A decision dated D is filled at the open of the symbol's next bar: the next NYSE session
  for stocks, D+1 00:00 UTC for coins. Nothing is ever filled on the bar that produced
  the signal. The OOS `fr` column (close-to-close) is never used here. Several decisions
  for a symbol before its fill: the latest wins.
- Prices are split-adjusted open/close. Dividends are paid on the ex-date as shares held
  at the previous close x cash per share x (1 - withholding), not reinvested gross as in
  adj_close.
- Everything is valued in KRW. USD assets use the USD/KRW rate of the previous day at the
  open (the newest rate known by then) and of the day at the close; buying or selling them
  pays the FX spread, since the account holds won. Upbit coins (sensitivity) trade in KRW.
- Each fill goes through the order-level rules of `app.strategy.risk` unchanged
  (`rebalance_orders`: `plan_rebalance` -> `check_order` -> `apply_decision`, with a
  cost per order and only the decided symbols traded): no leverage, no short sales,
  order and weight caps. Baselines pass `limits=None`: no caps, but still no leverage or
  shorts. The kill switch is not applied
  (adoption MDD is measured without it, D-003); `summarize` reports when it would trip.
- Korean taxes: overseas stock gains are netted per calendar year, 2.5M won deducted, 22%
  (moving-average cost, fees included as costs; KRW at the trade-date rate) and paid on
  Dec 31, selling pro rata if cash is short. Coin gains are taxed the same way from
  `crypto_tax_start`. By default every position is sold on the last day and that year is
  taxed too, so buy-and-hold pays tax on its gains like a trading strategy.

Defaults that need checking are listed in DECISIONS.md D-020 ("확인 필요").
"""

import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Literal

import numpy as np
import pandas as pd

from app.strategy.risk import (
    Book,
    Order,
    RiskLimits,
    apply_decision,
    kill_switch_triggers,
    max_drawdown,
    rebalance_orders,
)

Venue = Literal["us_stock", "crypto_usd", "upbit_krw"]
Fill = Literal["next_open", "next_close"]
# Changes smaller than this share of equity are not traded (sells to 0 always are).
MIN_TRADE_SHARE = 1e-6
WEIGHT_TOLERANCE = 1e-9
# Caps that never bind: what baselines run with (leverage and shorts stay impossible).
NO_LIMITS = RiskLimits(
    max_drawdown=1.0,
    daily_loss_limit=1.0,
    max_order_fraction=1.0,
    max_position_weight=1.0,
    max_index_fund_weight=1.0,
)


class LeverageError(ValueError):
    """Target weights that would borrow or sell short."""


@dataclass(frozen=True)
class Instrument:
    symbol: str
    asset_class: str  # "stock" | "crypto"
    venue: Venue

    @property
    def currency(self) -> str:
        return "KRW" if self.venue == "upbit_krw" else "USD"

    @property
    def daily(self) -> bool:
        return self.asset_class == "crypto"


def instrument(symbol: str, asset_class: str, *, upbit: bool = False) -> Instrument:
    if asset_class == "stock":
        return Instrument(symbol, "stock", "us_stock")
    return Instrument(symbol, "crypto", "upbit_krw" if upbit else "crypto_usd")


@dataclass(frozen=True)
class CostModel:
    """Proportional costs per side, as fractions of the traded amount."""

    commission: Mapping[str, float] = field(
        default_factory=lambda: {"us_stock": 0.0025, "crypto_usd": 0.001, "upbit_krw": 0.0005}
    )
    # Per symbol, falling back to the asset class.
    slippage_bps: Mapping[str, float] = field(
        default_factory=lambda: {
            "stock": 5.0,
            "crypto": 10.0,
            "BTC-USD": 5.0,
            "ETH-USD": 5.0,
            "KRW-BTC": 5.0,
            "KRW-ETH": 5.0,
        }
    )
    sec_fee: float = 0.0000278  # US stock sells only
    fx_spread: float = 0.001  # each KRW<->USD conversion

    def slippage(self, inst: Instrument) -> float:
        bps = self.slippage_bps.get(inst.symbol, self.slippage_bps.get(inst.asset_class, 0.0))
        return bps / 1e4

    def rate(self, inst: Instrument, side: str) -> float:
        r = self.commission.get(inst.venue, 0.0) + self.slippage(inst)
        if inst.currency == "USD":
            r += self.fx_spread
        if side == "sell" and inst.venue == "us_stock":
            r += self.sec_fee
        return r

    def round_trip(self, inst: Instrument) -> float:
        return self.rate(inst, "buy") + self.rate(inst, "sell")

    def scaled(self, factor: float) -> "CostModel":
        """Every cost multiplied by `factor` (sensitivity)."""
        return CostModel(
            {k: v * factor for k, v in self.commission.items()},
            {k: v * factor for k, v in self.slippage_bps.items()},
            self.sec_fee * factor,
            self.fx_spread * factor,
        )


@dataclass(frozen=True)
class TaxModel:
    stock_rate: float = 0.22
    stock_deduction_krw: float = 2_500_000
    dividend_withholding: float = 0.15
    crypto_rate: float = 0.22
    crypto_deduction_krw: float = 2_500_000
    # Coin gains realized on or after this date are taxed; None: never.
    crypto_tax_start: date | None = date(2027, 1, 1)

    def bucket(self, asset_class: str, on: date) -> str:
        if asset_class == "stock":
            return "stock"
        if self.crypto_tax_start is not None and on >= self.crypto_tax_start:
            return "crypto"
        return "crypto_untaxed"

    def due(self, gains: Mapping[str, float]) -> float:
        tax = max(0.0, gains.get("stock", 0.0) - self.stock_deduction_krw) * self.stock_rate
        tax += max(0.0, gains.get("crypto", 0.0) - self.crypto_deduction_krw) * self.crypto_rate
        return tax


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital_krw: float = 100_000_000
    costs: CostModel = field(default_factory=CostModel)
    taxes: TaxModel = field(default_factory=TaxModel)
    fill: Fill = "next_open"
    liquidate_at_end: bool = True
    # Orders smaller than this share of equity are skipped (a target of 0 still sells in
    # full). Part of a strategy's rules when it trades daily (S2: 0.02, the paper trader's
    # min_order_share); the default only drops rounding dust.
    min_trade_share: float = MIN_TRADE_SHARE


@dataclass(frozen=True)
class BacktestInputs:
    """Market data for a backtest, as the strict loader returns it."""

    bars: Mapping[str, pd.DataFrame]  # DatetimeIndex; open, close (split-adjusted)
    usdkrw: pd.Series  # KRW per USD for every calendar day (as of D+1 00:00 UTC)
    instruments: Mapping[str, Instrument]
    dividends: Mapping[str, pd.Series] = field(default_factory=dict)  # ex-date -> per share


@dataclass
class BacktestResult:
    equity: pd.Series  # KRW at each day's close; the last day after liquidation and tax
    positions: pd.DataFrame  # shares held at each day's close
    weights: pd.DataFrame  # share of equity at each day's close
    trades: pd.DataFrame
    initial_capital_krw: float
    costs_krw: float = 0.0  # commission, slippage, FX spread, SEC fee
    taxes_krw: float = 0.0  # capital gains tax paid
    withholding_krw: float = 0.0  # dividend tax withheld
    dividends_krw: float = 0.0  # dividends received, net
    tax_by_year: dict = field(default_factory=dict)
    # KRW of capital gains tax paid out of the account, by the day it was paid.
    tax_paid: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    untaxed_crypto_gains_krw: float = 0.0  # realized before crypto_tax_start

    @property
    def returns(self) -> pd.Series:
        prev = self.equity.shift(1)
        prev.iloc[0] = self.initial_capital_krw
        return self.equity / prev - 1


def validate_decisions(decisions: pd.DataFrame) -> pd.DataFrame:
    """Decisions as [date, symbol, weight], sorted. Raises LeverageError for negative
    weights (short sales), weights that are not finite, or a date whose weights add up
    to more than 1 (borrowing)."""
    missing = {"date", "symbol", "weight"} - set(decisions.columns)
    if missing:
        raise ValueError(f"decisions lack columns {sorted(missing)}")
    d = decisions[["date", "symbol", "weight"]].copy()
    d["date"] = pd.to_datetime(d["date"]).dt.normalize()
    w = d["weight"].astype(float)
    if not np.isfinite(w).all():
        raise LeverageError("target weights must be finite")
    if (w < -WEIGHT_TOLERANCE).any():
        raise LeverageError("negative target weight: short selling is not allowed")
    totals = w.groupby(d["date"]).sum()
    if (totals > 1 + WEIGHT_TOLERANCE).any():
        bad = totals[totals > 1 + WEIGHT_TOLERANCE]
        raise LeverageError(
            f"target weights add up to more than 1 (leverage) on {bad.index[0].date()}: "
            f"{bad.iloc[0]:.4f}"
        )
    d["weight"] = w.clip(lower=0.0)
    return d.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)


def _session(inst: Instrument, fill: Fill) -> int:
    # Order of events within a UTC day: coin open (00:00), stock open, stock close, coin
    # close (24:00). Dividends are credited between the coin and the stock open.
    if fill == "next_open":
        return 0 if inst.daily else 2
    return 4 if inst.daily else 3


def run_backtest(
    decisions: pd.DataFrame,
    inputs: BacktestInputs,
    config: BacktestConfig | None = None,
    *,
    limits: RiskLimits | None = None,
    start: date | None = None,
    end: date | None = None,
) -> BacktestResult:
    """Simulate `decisions` (target share of equity per symbol, dated by the signal day).

    Symbols absent from a decision date keep their positions; a weight of 0 sells. The
    simulation runs over calendar days [start, end]: by default from the first decision to
    the last day every traded symbol has a bar.
    """
    config = config or BacktestConfig()
    lim = limits or NO_LIMITS
    costs, taxes = config.costs, config.taxes
    dec = validate_decisions(decisions)
    symbols = sorted(set(dec["symbol"]))
    for s in symbols:
        if s not in inputs.instruments or s not in inputs.bars:
            raise ValueError(f"{s}: no instrument or bars")
    bars = {s: inputs.bars[s].sort_index() for s in symbols}
    for b in bars.values():
        b.index = pd.DatetimeIndex(b.index).normalize()
    if start is None:
        start = dec["date"].min().date() if len(dec) else min(b.index[0] for b in bars.values())
    if end is None:
        end = min(b.index[-1] for b in bars.values()).date()
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    days = pd.date_range(start, end, freq="D")
    if days.empty:
        raise ValueError("empty backtest period")
    insts = {s: inputs.instruments[s] for s in symbols}

    fx = None
    if any(i.currency == "USD" for i in insts.values()):
        fx = inputs.usdkrw.copy()
        fx.index = pd.DatetimeIndex(fx.index).normalize()
        fx = fx.reindex(pd.date_range(start - pd.Timedelta(days=1), end, freq="D"))
        if fx.isna().any():
            raise ValueError(f"USD/KRW missing on {fx.index[fx.isna()][0].date()}")

    def fx_close(t: pd.Timestamp) -> float:
        return float(fx.loc[t]) if fx is not None else 1.0

    def fx_open(t: pd.Timestamp) -> float:
        return float(fx.loc[t - pd.Timedelta(days=1)]) if fx is not None else 1.0

    def to_krw(s: str, price: float, rate: float) -> float:
        return price * rate if insts[s].currency == "USD" else price

    close_grid = {s: b["close"].astype(float).reindex(days.union(b.index)).ffill().reindex(days)
                  for s, b in bars.items()}  # fmt: skip
    bar_dates = {s: b.index for s, b in bars.items()}

    # Fill events: (day, session) -> {symbol: weight}; the latest decision wins.
    events: dict[tuple[pd.Timestamp, int], dict[str, float]] = defaultdict(dict)
    for row in dec.itertuples(index=False):
        idx = bar_dates[row.symbol]
        pos = idx.searchsorted(row.date, side="right")
        if pos >= len(idx) or idx[pos] > end or idx[pos] < start:
            continue
        events[(idx[pos], _session(insts[row.symbol], config.fill))][row.symbol] = row.weight

    dividends: dict[pd.Timestamp, list[tuple[str, float]]] = defaultdict(list)
    for s in symbols:
        div = inputs.dividends.get(s)
        if div is None or not len(div) or insts[s].asset_class != "stock":
            continue
        idx = bar_dates[s]
        for ex, amount in div.items():
            pos = idx.searchsorted(pd.Timestamp(ex).normalize())
            if 0 < pos < len(idx):
                dividends[idx[pos]].append((s, float(amount)))

    cash = float(config.initial_capital_krw)
    shares: dict[str, float] = defaultdict(float)
    basis: dict[str, float] = defaultdict(float)  # KRW cost of the shares held
    marks: dict[str, float] = {}  # latest KRW price per symbol
    gains: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    trades: list[dict] = []
    totals = defaultdict(float)
    tax_by_year: dict[int, float] = {}
    tax_paid: dict[pd.Timestamp, float] = {}

    def equity_now() -> float:
        return cash + sum(shares[s] * marks[s] for s in shares if shares[s] > 0)

    def record_sale(s: str, t: pd.Timestamp, sold: float, proceeds: float) -> None:
        held = shares[s]
        frac = min(1.0, sold / held) if held > 0 else 1.0
        out = basis[s] * frac
        bucket = taxes.bucket(insts[s].asset_class, t.date())
        year = t.year
        gains[year][bucket] += proceeds - out
        basis[s] -= out
        shares[s] = 0.0 if frac >= 1.0 else held - sold
        if shares[s] <= 0:
            shares[s], basis[s] = 0.0, 0.0

    def execute(t: pd.Timestamp, targets: dict[str, float], prices: dict[str, float], kind: str):
        nonlocal cash
        marks.update(prices)
        held = {s: shares[s] * marks[s] for s in shares if shares[s] > 0}
        book = Book(cash, held)
        equity = book.equity
        if equity <= 0:
            return
        target = {s: v / equity for s, v in held.items()}
        target.update(targets)

        def rate_of(order: Order) -> float:
            return costs.rate(insts[order.symbol], order.side)

        # Positions outside this decision keep their drifted weight and are not traded.
        checked = rebalance_orders(
            book,
            target,
            lim,
            fee_rate=rate_of,
            min_notional=config.min_trade_share * equity,
            trade_only=targets,
        )
        for d in checked:
            order = d.order
            s = order.symbol
            rate = rate_of(order)
            # The same book update rebalance_orders applied, to follow cash and positions.
            book = apply_decision(book, d, fee_rate=rate)
            if d.notional > 0:
                price = prices[s]
                fee = d.notional * rate
                totals["costs"] += fee
                if order.side == "buy":
                    shares[s] += d.notional / price
                    basis[s] += d.notional + fee
                else:
                    full = s not in book.positions
                    sold = shares[s] if full else min(shares[s], d.notional / price)
                    record_sale(s, t, sold, d.notional - fee)
            trades.append(
                {
                    "date": t,
                    "symbol": s,
                    "side": order.side,
                    "requested": order.notional,
                    "notional": d.notional,
                    "status": d.status,
                    "reasons": ",".join(d.reasons),
                    "price_krw": prices[s],
                    "equity": equity,
                    "kind": kind,
                }
            )
        cash = book.cash

    def sell_fraction(t: pd.Timestamp, frac: float, kind: str, year_of_gain: int) -> None:
        """Sell `frac` of every position at today's close marks (tax payment, final
        liquidation); gains count in `year_of_gain`."""
        nonlocal cash
        equity = equity_now()
        for s in sorted(shares):
            if shares[s] <= 0:
                continue
            sold = shares[s] * frac
            notional = sold * marks[s]
            rate = costs.rate(insts[s], "sell")
            fee = notional * rate
            totals["costs"] += fee
            cash += notional - fee
            held = shares[s]
            out = basis[s] * min(1.0, sold / held)
            bucket = taxes.bucket(insts[s].asset_class, t.date())
            gains[year_of_gain][bucket] += notional - fee - out
            basis[s] -= out
            shares[s] = 0.0 if frac >= 1.0 else held - sold
            if shares[s] <= 0:
                shares[s], basis[s] = 0.0, 0.0
            trades.append(
                {
                    "date": t,
                    "symbol": s,
                    "side": "sell",
                    "requested": notional,
                    "notional": notional,
                    "status": "accepted",
                    "reasons": "",
                    "price_krw": marks[s],
                    "equity": equity,
                    "kind": kind,
                }
            )

    def settle_taxes(t: pd.Timestamp, year: int, final: bool) -> None:
        nonlocal cash
        due = taxes.due(gains.get(year, {}))
        tax_by_year[year] = due
        totals["untaxed"] += gains.get(year, {}).get("crypto_untaxed", 0.0)
        if due <= 0:
            return
        if cash < due and not final:
            net = sum(
                shares[s] * marks[s] * (1 - costs.rate(insts[s], "sell"))
                for s in shares
                if shares[s] > 0
            )
            if net > 0:
                # Gains of these sales belong to next year's return (paid in May in reality).
                sell_fraction(t, min(1.0, (due - cash) / net), "tax", year + 1)
        paid = min(due, max(cash, 0.0)) if not final else due
        cash -= paid
        totals["taxes"] += paid
        tax_paid[t] = tax_paid.get(t, 0.0) + paid

    equity_rows, pos_rows = [], []
    last = days[-1]
    for t in days:
        for session in (0, 1, 2, 3, 4):
            if session == 1:
                for s, amount in dividends.get(t, []):
                    held = shares[s]
                    if held <= 0:
                        continue
                    gross = held * amount * fx_open(t)
                    withheld = gross * taxes.dividend_withholding
                    net = gross - withheld
                    conv = net * costs.fx_spread
                    cash += net - conv
                    totals["withholding"] += withheld
                    totals["costs"] += conv
                    totals["dividends"] += net - conv
                continue
            targets = events.get((t, session))
            if not targets:
                continue
            opening = session in (0, 2)
            prices = {}
            for s in targets:
                b = bars[s].loc[t]
                raw = float(b["open"] if opening else b["close"])
                prices[s] = to_krw(s, raw, fx_open(t) if opening else fx_close(t))
            execute(t, targets, prices, "decision")
        for s in symbols:
            c = close_grid[s].loc[t]
            if not math.isnan(c):
                marks[s] = to_krw(s, float(c), fx_close(t))
        if t == last:
            if config.liquidate_at_end:
                sell_fraction(t, 1.0, "liquidation", t.year)
            settle_taxes(t, t.year, final=True)
        elif (t + pd.Timedelta(days=1)).year != t.year:
            settle_taxes(t, t.year, final=False)
        equity_rows.append(equity_now())
        pos_rows.append({s: shares[s] for s in symbols})

    equity = pd.Series(equity_rows, index=days, name="equity")
    positions = pd.DataFrame(pos_rows, index=days, columns=symbols).fillna(0.0)
    closes_krw = pd.DataFrame(
        {
            s: close_grid[s] * (fx.reindex(days) if insts[s].currency == "USD" else 1.0)
            for s in symbols
        },
        index=days,
    )
    weights = (positions * closes_krw).div(equity.replace(0, np.nan), axis=0).fillna(0.0)
    trade_cols = ["date", "symbol", "side", "requested", "notional", "status", "reasons",
                  "price_krw", "equity", "kind"]  # fmt: skip
    return BacktestResult(
        equity=equity,
        positions=positions,
        weights=weights,
        trades=pd.DataFrame(trades, columns=trade_cols),
        initial_capital_krw=float(config.initial_capital_krw),
        costs_krw=totals["costs"],
        taxes_krw=totals["taxes"],
        withholding_krw=totals["withholding"],
        dividends_krw=totals["dividends"],
        tax_by_year=tax_by_year,
        tax_paid=pd.Series(tax_paid, dtype=float),
        untaxed_crypto_gains_krw=totals["untaxed"],
    )


# --- summaries ---------------------------------------------------------------------------

DAYS_PER_YEAR = 365.25


def cagr(result: BacktestResult) -> float:
    years = len(result.equity) / DAYS_PER_YEAR
    final = float(result.equity.iloc[-1])
    if years <= 0 or final <= 0:
        return -1.0
    return (final / result.initial_capital_krw) ** (1 / years) - 1


def sharpe(returns: pd.Series) -> float:
    """Annualized Sharpe of calendar-day returns (rf = 0, cash earns nothing)."""
    r = returns.to_numpy(dtype=float)
    sd = r.std()
    return float(r.mean() / sd * np.sqrt(365)) if sd > 0 else 0.0


def turnover(result: BacktestResult) -> float:
    """Average yearly one-way turnover: half the traded amount over equity, per year.
    Signal trades only (tax sales and the final liquidation are left out)."""
    t = result.trades
    t = t[(t["kind"] == "decision") & (t["notional"] > 0)]
    years = len(result.equity) / DAYS_PER_YEAR
    if t.empty or years <= 0:
        return 0.0
    return float((t["notional"] / t["equity"]).sum() / 2 / years)


def cost_share(result: BacktestResult) -> float:
    """Costs and taxes over the profit before them; inf when that profit is not positive."""
    paid = result.costs_krw + result.taxes_krw + result.withholding_krw
    gross = float(result.equity.iloc[-1]) - result.initial_capital_krw + paid
    return paid / gross if gross > 0 else math.inf


def settlement_days(result: BacktestResult) -> set[date]:
    """Days on which taxes were paid out of the equity: the last day of each year with
    tax due, and the final day (liquidation and its tax)."""
    eq = result.equity
    if eq.empty:
        return set()
    last_of_year = eq.groupby(eq.index.year).apply(lambda g: g.index[-1].date())
    days = {d for y, d in last_of_year.items() if result.tax_by_year.get(int(y), 0.0) > 0}
    days.add(eq.index[-1].date())
    return days


def summarize(
    result: BacktestResult,
    baselines: Mapping[str, BacktestResult] | None = None,
    *,
    limits: RiskLimits,
) -> dict:
    """Headline numbers; excess figures are against each baseline over the same days.

    `limits` is required (pass `RiskLimits.from_settings(settings)`): a user's stricter
    limits must not be replaced quietly by the dataclass defaults.
    """
    eq = result.equity
    r = result.returns
    # Taxes paid are cash leaving the account, not a market loss: the daily-loss rule
    # leaves them out (ISSUE-034); the drawdown rule still counts them.
    triggers = kill_switch_triggers(eq, limits, flows=-result.tax_paid)
    out = {
        "start": str(eq.index[0].date()),
        "end": str(eq.index[-1].date()),
        "final_krw": float(eq.iloc[-1]),
        "cumulative_return": float(eq.iloc[-1] / result.initial_capital_krw - 1),
        "cagr": cagr(result),
        "sharpe": sharpe(r),
        "volatility": float(r.std() * np.sqrt(365)),
        "max_drawdown": max_drawdown(np.r_[result.initial_capital_krw, eq.to_numpy()]),
        "turnover": turnover(result),
        # Invested share of equity, averaged over days (the order cap fills slowly).
        "avg_exposure": float(result.weights.sum(axis=1).mean()),
        "costs_krw": result.costs_krw,
        "taxes_krw": result.taxes_krw,
        "withholding_krw": result.withholding_krw,
        "dividends_krw": result.dividends_krw,
        "cost_share": cost_share(result),
        "kill_switch_first": str(triggers[0].date) if triggers else None,
        "kill_switch_count": len(triggers),
        # Triggers on a day taxes were paid (the year's last day) or the final sale: the
        # curve fell by a payment, not by the market (ISSUE-034). Reference only, as the
        # kill switch is off in adoption backtests (D-003).
        "kill_switch_on_settlement_days": [
            str(t.date) for t in triggers if t.date in settlement_days(result)
        ],
    }
    for name, base in (baselines or {}).items():
        br = base.returns
        common = r.index.intersection(br.index)
        diff = r.loc[common] - br.loc[common]
        out[f"excess_vs_{name}"] = {
            "cagr": out["cagr"] - cagr(base),
            "cumulative": out["cumulative_return"]
            - float(base.equity.iloc[-1] / base.initial_capital_krw - 1),
            "mean_daily": float(diff.mean()) if len(diff) else 0.0,
        }
    return out


def with_costs(config: BacktestConfig, factor: float) -> BacktestConfig:
    """`config` with every trading cost multiplied by `factor` (sensitivity runs)."""
    return replace(config, costs=config.costs.scaled(factor))


def upbit_decisions(decisions: pd.DataFrame) -> pd.DataFrame:
    """Decisions with coins renamed to their Upbit KRW markets (BTC-USD -> KRW-BTC), for
    the sensitivity run on `load_inputs(..., upbit=True)` data."""
    from app.data.assets import UPBIT_MARKETS

    out = decisions.copy()
    out["symbol"] = out["symbol"].map(lambda s: UPBIT_MARKETS.get(s, s))
    return out


def load_inputs(
    market,
    symbols: Mapping[str, str],
    start: date,
    end: date | None = None,
    *,
    upbit: bool = False,
) -> BacktestInputs:
    """Strict-loader data for `symbols` ({symbol: asset class}); raises
    DataUnavailableError instead of degrading. With `upbit`, coins are read from their
    Upbit KRW markets (keys stay the Yahoo symbols' Upbit names, e.g. KRW-BTC)."""
    from app.data.assets import UPBIT_MARKETS
    from app.forecast.data import load_daily, load_usd_krw

    names = {
        s: (UPBIT_MARKETS[s] if upbit and cls == "crypto" else s) for s, cls in symbols.items()
    }
    loaded = load_daily(market, list(names.values()), start, end, allow_late_start=True)
    bars, dividends, insts = {}, {}, {}
    for s, cls in symbols.items():
        name = names[s]
        daily = loaded[name]
        bars[name] = daily.bars
        dividends[name] = daily.dividends
        insts[name] = instrument(name, cls, upbit=upbit and cls == "crypto")
    fx = load_usd_krw(market, start - timedelta(days=1), end)
    return BacktestInputs(bars, fx, insts, dividends)
