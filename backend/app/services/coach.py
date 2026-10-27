"""The portfolio coach: the user's investment policy and the checks built on it
(DECISIONS.md D-033).

The coach is not a strategy, not a forecast and not advice. It stores the targets and limits
the user chose and compares the holdings with them: weights and exposure, how much today's
mix moved over past windows, the orders a rebalance to the targets would mean (sizes and what
blocks them, never placed), habits in the trade log and a monthly review. Nothing here places
an order and `AM_LIVE_TRADING` is never changed. The arithmetic lives in the pure module
`app/strategy/coach.py`; this service feeds it from the ledger, the price cache and the rule
checks, and never replaces missing data with a proxy (symbols without bars are reported).

Amounts and percentages of the policy are stored as strings and round-trip as exact decimals,
like the ledger. Validation goes through the engine's `Policy` / `CashRecord` dataclasses;
their ValueError becomes a 422.
"""

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.data.assets import FX_USDKRW
from app.data.provider import MarketDataError
from app.db.models import (
    AssetType,
    CorporateAction,
    Currency,
    PolicySettingsRow,
    Side,
    Transaction,
)
from app.forecast.panel import AssetClass
from app.services.benchmarks import BenchmarkService, cash_flows
from app.services.corporate_actions import confirmed_events, split_events
from app.services.errors import DomainError
from app.services.ledger import ZERO, Position, build_positions, ordered, timeline
from app.services.market_data import MarketDataService, SymbolNotFoundError
from app.services.portfolio import Holding, PortfolioService, quote_symbol
from app.services.rules import RuleService
from app.strategy import coach as engine
from app.strategy.coach import CashRecord, HoldingView, Policy, RiskWindow, TradeView
from app.strategy.execution import KillSwitch
from app.strategy.risk import Book, RiskLimits, apply_decision, kill_switch_triggers, max_drawdown
from app.strategy.rules import BLOCK_LABELS

# A hand-entered cash balance older than this is flagged (D-033 §5).
CASH_STALE_DAYS = 30
SUM_TOLERANCE = Decimal("0.000001")
HUNDRED = Decimal("100")

POLICY_DECIMAL_KEYS = (
    "monthly_contribution_krw",
    "drawdown_tolerance_pct",
    "max_position_weight_pct",
    "max_crypto_weight_pct",
    "max_total_risk_pct",
    "rebalance_band_pt",
    "target_stock_pct",
    "target_crypto_pct",
    "target_cash_pct",
)
POLICY_KEYS = ("goal_krw", "goal_date", *POLICY_DECIMAL_KEYS)
CASH_KEYS = ("krw", "usd", "as_of")

# Past windows the risk figures are computed over, and the margin of bars loaded before them
# so the first return of the window exists.
WINDOWS: tuple[tuple[str, int], ...] = (("1y", 365), ("3y", 3 * 365))
HISTORY_MARGIN = timedelta(days=30)
# Beta against a benchmark in the symbol's own trade currency, so the rate stays out (D-033).
BETA_WINDOW_DAYS = 365
BETA_BENCHMARKS: dict[tuple[str, str], str] = {
    ("stock", "USD"): "SPY",
    ("crypto", "USD"): "BTC-USD",
    ("crypto", "KRW"): "KRW-BTC",
}
# Habit checks look at the last year of trades; bars start earlier so the first trade in the
# window has its 20 bars of run-up.
PATTERN_WINDOW_DAYS = 365
PATTERN_BARS_MARGIN = timedelta(days=45)
REVIEW_BENCHMARKS = ("SPY", "BTC-USD")
MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
# A trade whose unit price is this many times away from the close of its day was almost
# certainly imported wrong (a won amount, a total or a return read as the price). Same 20x rule
# as `statement_import.SUSPICIOUS_RATIO` and `frontend/src/lib/holdings.ts` (`단가 확인`); it is
# not imported from there because that module pulls in the screenshot extractor.
SUSPICIOUS_PRICE_RATIO = 20.0
# How far before the first trade bars are loaded so that day has a close to compare with.
SUSPICIOUS_LOOKBACK = timedelta(days=10)

IMPORTED_DATES_CAVEAT_KO = (
    "스크린샷으로 가져온 거래는 날짜가 실제 매수일과 다를 수 있어 실제 추이의 낙폭과 "
    "입금·시장 손익 구분이 왜곡될 수 있습니다."
)
ACTUAL_CURVE_NOTE_KO = (
    "실제 추이의 낙폭은 입금을 뺀 시간가중 지수로 계산한 정보이며, 킬스위치를 발동시키지 않습니다."
)
REQUIRED_RETURN_NOTE_KO = "목표 달성에 필요한 수익률은 산수이지 예측이 아닙니다."
FEES_CAVEAT_KO = "수수료·세금·환전 비용은 포함하지 않았습니다."
BENCHMARK_CAVEAT_KO = (
    "벤치마크는 같은 날 같은 돈을 넣었을 때의 값이며, 배당은 양쪽 모두 빠져 있습니다."
)
# N-COACH-1: a mis-priced trade turns the deposit of its day into a 10,000% "loss", so the
# time-weighted curve is not computed at all while one exists (fail closed, never a proxy).
SUSPICIOUS_ACTUAL_KO = (
    "단가 확인이 필요한 거래 {n}건({symbols})이 있어 실제 추이의 낙폭을 계산하지 않았습니다. "
    "거래 페이지에서 단가를 고치면 계산됩니다."
)
# The review's split of the change into deposits and market result is ledger fact, so it is
# shown, with this caveat first.
SUSPICIOUS_REVIEW_KO = (
    "넣은 돈·시장 손익에 단가 확인이 필요한 거래 {n}건이 들어 있어 값이 왜곡될 수 있습니다."
)
# N-COACH-2: habit flags exist only for the last PATTERN_WINDOW_DAYS of trades.
FLAGS_OUTSIDE_WINDOW_KO = "습관 점검은 최근 1년 거래만 보므로 이 달의 플래그는 세지 않았습니다."
PATTERN_DETAILS_KO: dict[str, str] = {
    "chasing_buy": "매수 전 20봉 동안 15% 넘게 움직인 뒤 산 거래",
    "averaging_down_below_cut": "평균단가 기준 손절선 아래에서 추가로 산 거래",
    "quick_rebuy_after_loss": "손실로 판 뒤 10일 안에 같은 종목을 다시 산 거래",
    "overtrading": "직전 12개월 평균의 2배를 넘고 6건 이상 거래한 달",
    "rule_lag": "손절선 아래 종가가 5봉 이상 이어졌는데 아직 보유 중인 종목",
}


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _dec(v: object, name: str) -> Decimal:
    """Exact decimal from a Decimal, int or numeric string; floats go through str()."""
    try:
        d = v if isinstance(v, Decimal) else Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise DomainError(f"{name}: 숫자가 아닙니다 ({v!r})", code="invalid_policy") from exc
    if not d.is_finite():
        raise DomainError(f"{name}: 유한한 숫자여야 합니다", code="invalid_policy")
    return d


def _date(v: object, name: str) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v))
    except ValueError as exc:
        raise DomainError(f"{name}: 날짜가 아닙니다 ({v!r})", code="invalid_policy") from exc


def _pct(ratio: Decimal) -> Decimal:
    return Decimal(str(ratio)) * HUNDRED


def _text(d: Decimal) -> str:
    """`20.00` -> `20`, `12.50` -> `12.5`, for Korean messages."""
    return format(d.normalize(), "f")


def _store(v: object) -> object:
    """JSON value for the row: decimals and dates as strings, None as null."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


def _asset_class(asset_type: AssetType) -> AssetClass:
    return "crypto" if asset_type == AssetType.CRYPTO else "stock"


def _series(values: Iterable[float], dates: Iterable[date]) -> pd.Series:
    return pd.Series(list(values), index=pd.to_datetime(list(dates)), dtype=float)


def _month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _price_suspicious(price: float, close: float) -> bool:
    """The 20x rule: a unit price `SUSPICIOUS_PRICE_RATIO` or more times above or below the
    close of its day, both in the trade currency. Non-positive inputs cannot be judged."""
    if not (price > 0 and close > 0):
        return False
    ratio = price / close
    return ratio >= SUSPICIOUS_PRICE_RATIO or ratio <= 1 / SUSPICIOUS_PRICE_RATIO


class CoachService:
    def __init__(
        self,
        db: Session,
        market: MarketDataService,
        portfolio: PortfolioService,
        rules: RuleService,
        benchmarks: BenchmarkService,
        settings: Settings | None = None,
        today: Callable[[], date] = date.today,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.db = db
        self.market = market
        self.portfolio = portfolio
        self.rules = rules
        self.benchmarks = benchmarks
        self.settings = settings or get_settings()
        self.today = today
        self.now = now

    # --- policy ------------------------------------------------------------------------------

    def defaults(self) -> dict:
        """The policy implied by the AM_RISK_* / AM_RULES_* / AM_COACH_* settings
        (`Policy.from_config`), as exact decimals."""
        policy = Policy.from_config(self.settings)
        out: dict = {"goal_krw": None, "goal_date": None}
        for key in POLICY_DECIMAL_KEYS:
            out[key] = Decimal(str(getattr(policy, key)))
        return out

    def _row(self) -> PolicySettingsRow | None:
        return self.db.get(PolicySettingsRow, 1)

    def get_policy(self) -> dict:
        """The stored policy, or the defaults while nothing is stored. Keys missing from an
        older row take their default; a value the current engine cannot read is reported,
        not silently replaced."""
        row = self._row()
        if row is None:
            return self.defaults()
        values = self.defaults()
        stored = dict(row.policy_json or {})
        try:
            for key in POLICY_DECIMAL_KEYS:
                if stored.get(key) is not None:
                    values[key] = _dec(stored[key], key)
            if stored.get("goal_krw") is not None:
                values["goal_krw"] = _dec(stored["goal_krw"], "goal_krw")
            if stored.get("goal_date"):
                values["goal_date"] = _date(stored["goal_date"], "goal_date")
            # A goal date that has since passed is a warning, not a reason to refuse the read.
            self._validate_policy(values, today=None)
        except DomainError as exc:
            raise DomainError(
                f"저장된 정책을 적용할 수 없습니다 ({exc}). 코치 페이지에서 다시 저장하세요.",
                code="invalid_policy_settings",
            ) from exc
        return values

    def get_cash(self) -> dict | None:
        """`{"krw", "usd", "as_of"}` as Decimal/date, or None while no cash was entered."""
        row = self._row()
        stored = dict(row.cash_json or {}) if row is not None else {}
        if not stored:
            return None
        try:
            return {
                "krw": _dec(stored.get("krw", 0), "krw"),
                "usd": _dec(stored.get("usd", 0), "usd"),
                "as_of": _date(stored.get("as_of"), "as_of"),
            }
        except DomainError as exc:
            raise DomainError(
                f"저장된 현금 기록을 읽을 수 없습니다 ({exc}). 코치 페이지에서 다시 저장하세요.",
                code="invalid_policy_settings",
            ) from exc

    def cash_stale(self, cash: Mapping[str, object] | None) -> bool:
        if cash is None:
            return False
        return (self.today() - _date(cash["as_of"], "as_of")).days > CASH_STALE_DAYS

    def policy_payload(self) -> dict:
        row = self._row()
        policy = self.get_policy()
        cash = self.get_cash()
        return {
            "policy": policy,
            "cash": cash,
            "defaults": self.defaults(),
            "warnings": self._notes(self._policy_obj(policy), self._cash_record(cash)),
            "updated_at": row.updated_at if row is not None else None,
            "cash_stale": self.cash_stale(cash),
            "policy_set": row is not None,
        }

    def update_policy(
        self, policy_values: Mapping[str, object], cash_values: Mapping[str, object] | None
    ) -> dict:
        """Validate and store. `cash_values=None` clears the cash record. Rule violations
        are `DomainError` (422) naming the field."""
        today = self.today()
        values: dict = {}
        for key in POLICY_DECIMAL_KEYS:
            if policy_values.get(key) is None:
                raise DomainError(f"{key}: 값이 없습니다", code="invalid_policy")
            values[key] = _dec(policy_values[key], key)
        goal_krw = policy_values.get("goal_krw")
        values["goal_krw"] = None if goal_krw is None else _dec(goal_krw, "goal_krw")
        goal_date = policy_values.get("goal_date")
        values["goal_date"] = None if goal_date in (None, "") else _date(goal_date, "goal_date")
        self._validate_policy(values, today=today)

        cash: dict | None = None
        if cash_values is not None:
            cash = {
                "krw": _dec(cash_values.get("krw", 0), "krw"),
                "usd": _dec(cash_values.get("usd", 0), "usd"),
                "as_of": _date(cash_values.get("as_of"), "as_of"),
            }
            self._validate_cash(cash, today=today)

        row = self._row()
        if row is None:
            row = PolicySettingsRow(id=1, policy_json={}, cash_json={})
            self.db.add(row)
        row.policy_json = {k: _store(values[k]) for k in POLICY_KEYS}
        row.cash_json = {} if cash is None else {k: _store(cash[k]) for k in CASH_KEYS}
        row.updated_at = self.now()
        self.db.commit()
        return self.policy_payload()

    # --- validation through the engine's dataclasses ---------------------------------------

    @staticmethod
    def _policy_obj(values: Mapping[str, object]) -> Policy:
        """`Policy` from stored/API values (exact decimals become the engine's floats);
        ValueError propagates."""
        kwargs: dict = {}
        for key in POLICY_KEYS:
            v = values.get(key)
            kwargs[key] = v if v is None or isinstance(v, date) else float(v)  # type: ignore[arg-type]
        return Policy(**kwargs)

    @classmethod
    def _validate_policy(cls, values: Mapping[str, object], *, today: date | None) -> Policy:
        """`Policy.__post_init__` does the range and cross-field checks; the two most common
        ones are repeated first with a Korean message. `today=None` skips the goal-date rule
        (reading a stored row must not fail because time passed)."""
        total = values["target_stock_pct"] + values["target_crypto_pct"] + values["target_cash_pct"]
        if abs(total - HUNDRED) > SUM_TOLERANCE:
            raise DomainError(
                f"자산군 목표 비중(주식·코인·현금)의 합이 100이어야 합니다 (지금 {_text(total)}%)",
                code="invalid_policy",
            )
        crypto, cap = values["target_crypto_pct"], values["max_crypto_weight_pct"]
        if crypto > cap:
            raise DomainError(
                f"코인 목표 비중({_text(crypto)}%)이 코인 합산 상한({_text(cap)}%)보다 큽니다",
                code="invalid_policy",
            )
        try:
            policy = cls._policy_obj(values)
        except ValueError as exc:
            raise DomainError(f"정책이 잘못되었습니다: {exc}", code="invalid_policy") from exc
        if today is not None and policy.goal_date is not None and policy.goal_date <= today:
            raise DomainError(
                f"목표일은 오늘({today.isoformat()}) 이후여야 합니다", code="invalid_policy"
            )
        return policy

    @staticmethod
    def _cash_record(cash: Mapping[str, object] | None) -> CashRecord | None:
        if cash is None:
            return None
        try:
            return CashRecord(float(cash["krw"]), float(cash["usd"]), _date(cash["as_of"], "as_of"))  # type: ignore[arg-type]
        except ValueError as exc:
            raise DomainError(f"현금 기록이 잘못되었습니다: {exc}", code="invalid_policy") from exc

    def _validate_cash(self, cash: Mapping[str, object], *, today: date) -> CashRecord:
        record = self._cash_record(cash)
        assert record is not None
        if record.as_of is not None and record.as_of > today:
            raise DomainError(
                f"현금 기준일은 오늘({today.isoformat()}) 이후일 수 없습니다",
                code="invalid_policy",
            )
        return record

    def _notes(self, policy: Policy, cash: CashRecord | None) -> list[str]:
        """Legal but noteworthy choices: the engine's own remarks (`Policy.notes`) plus what
        only the service knows (risk limits, today, the cash record)."""
        notes = list(policy.notes())
        risk_cap = float(self.settings.risk_max_position_weight) * 100
        if policy.max_position_weight_pct > risk_cap + 1e-9:
            notes.append(
                f"종목 상한 {policy.max_position_weight_pct:g}%는 모의투자 리스크 한도"
                f"({risk_cap:g}%)보다 느슨합니다. 모의투자 주문은 여전히 리스크 한도 안에서만"
                " 나갑니다."
            )
        today = self.today()
        if policy.goal_date is not None and policy.goal_date <= today:
            notes.append("목표일이 지났습니다. 새 목표일을 적어 주세요.")
        if cash is None:
            if policy.target_cash_pct > 0:
                notes.append(
                    "현금 목표 비중이 있지만 현금 잔고를 적지 않아 현금 비중은 확인할 수 없습니다."
                )
        elif cash.stale(today, CASH_STALE_DAYS) and cash.as_of is not None:
            days = (today - cash.as_of).days
            notes.append(f"현금 기준일이 {days}일 지났습니다. 잔고를 다시 적어 주세요.")
        return notes

    # --- shared inputs ---------------------------------------------------------------------

    def _transactions(self) -> list[Transaction]:
        return ordered(self.db.scalars(select(Transaction)))

    def _fx_now(self) -> float:
        return float(self.market.usd_krw().price)

    def _holding_views(self) -> tuple[list[Holding], list[HoldingView]]:
        """Open positions as the engine's views: the price in the trade currency (Upbit won
        for KRW coins), the won figures at today's rate, and the user's per-symbol target
        from the rule settings (never stored twice)."""
        holdings = [h for h in self.portfolio.holdings() if h.quantity > ZERO]
        targets = self.rules.get_settings().targets
        views: list[HoldingView] = []
        for h in holdings:
            krw = h.currency == Currency.KRW
            rule = targets.get(h.symbol)
            target = None if rule is None else rule.target_weight_pct
            views.append(
                HoldingView(
                    symbol=h.symbol,
                    asset_class=_asset_class(h.asset_type),
                    currency=h.currency.value,
                    quantity=float(h.quantity),
                    price=float(h.price_krw if krw else h.price),
                    price_krw=float(h.price_krw),
                    value_krw=float(h.market_value_krw),
                    cost_basis_krw=float(h.cost_basis_krw),
                    target_pct=None if target is None else float(target),
                )
            )
        return holdings, views

    def _bars(
        self, qsym: str, start: date, *, adjusted: bool = True
    ) -> tuple[pd.Series | None, str | None]:
        """Final daily closes of a pricing symbol (adjusted for yfinance symbols, as traded
        for Upbit won markets and the FX rate), or None with the reason. No proxy.
        `adjusted=False` takes the plain close of yfinance symbols too (to compare with a
        price actually paid)."""
        try:
            rows = self.market.get_history(qsym, start, final_only=True)
        except SymbolNotFoundError:
            return None, "시세를 찾을 수 없습니다"
        except MarketDataError as exc:
            return None, f"시세를 받지 못했습니다 ({type(exc).__name__})"
        if not rows:
            return None, "확정된 일봉이 없습니다"
        raw = not adjusted or qsym.startswith("KRW-") or qsym == FX_USDKRW
        return _series(
            (r.close if raw else r.adj_close for r in rows), (r.date for r in rows)
        ), None

    def _suspicious_trades(self, txs: Sequence[Transaction]) -> list[Transaction]:
        """Trades whose unit price fails the 20x rule against the close of their day (the
        last final close on or before it), in the trade currency: Upbit won closes for KRW
        coins, USD closes for stocks and USD coins. Yahoo closes are split-adjusted back in
        time, so the ratio of every later split is put back first (as `portfolio.history`
        does). A trade with no close to compare against is not judged."""
        if not txs:
            return []
        start = min(t.trade_date for t in txs) - SUSPICIOUS_LOOKBACK
        splits: dict[str, list[tuple[date, Decimal]]] = {}
        for e in split_events(self.db, sorted({t.symbol for t in txs})):
            splits.setdefault(e.symbol, []).append((e.ex_date, e.value))
        closes: dict[str, pd.Series | None] = {}
        out: list[Transaction] = []
        for tx in txs:
            qsym = quote_symbol(tx.symbol, tx.currency or Currency.USD)
            if qsym not in closes:
                closes[qsym], _ = self._bars(qsym, start, adjusted=False)
            s = closes[qsym]
            if s is None:
                continue
            before = s[s.index <= pd.Timestamp(tx.trade_date)]
            if before.empty:
                continue
            close = float(before.iloc[-1])
            if qsym == tx.symbol:
                for ex_date, ratio in splits.get(tx.symbol, ()):
                    if ex_date > tx.trade_date:
                        close *= float(ratio)
            if _price_suspicious(float(tx.price), close):
                out.append(tx)
        return out

    def _native_closes(
        self, views: Sequence[HoldingView], start: date
    ) -> tuple[dict[str, pd.Series], dict[str, str]]:
        """Closes in each holding's trade currency; a symbol without bars gets an empty
        series and its reason, so the engine reports it as excluded."""
        closes: dict[str, pd.Series] = {}
        errors: dict[str, str] = {}
        for h in views:
            s, err = self._bars(quote_symbol(h.symbol, Currency(h.currency)), start)
            if s is None:
                closes[h.symbol] = pd.Series(dtype=float)
                errors[h.symbol] = err or "시세 없음"
            else:
                closes[h.symbol] = s
        return closes, errors

    # --- diagnosis -------------------------------------------------------------------------

    def diagnosis(self) -> dict:
        """Where the holdings stand against the policy: weights, concentration, exposure,
        the risk of today's mix over the last 1 and 3 years, correlation, beta per symbol,
        the real curve's drawdown, policy violations and the goal arithmetic."""
        today = self.today()
        policy_values = self.get_policy()
        policy = self._policy_obj(policy_values)
        policy_set = self._row() is not None
        cash_values = self.get_cash()
        cash = self._cash_record(cash_values)
        fx_now = self._fx_now()
        cash_krw = cash.total_krw(fx_now) if cash is not None else None
        _, views = self._holding_views()
        base = {
            "as_of": today,
            "policy_set": policy_set,
            "policy": policy_values,
            "cash_krw": cash_krw,
            "cash_as_of": cash.as_of if cash is not None else None,
            "cash_stale": cash.stale(today, CASH_STALE_DAYS) if cash is not None else False,
            "usd_krw": fx_now,
            "checked_at": self.now(),
        }
        if not views:
            return base | {
                "empty": True,
                "equity_krw": cash_krw or 0.0,
                "invested_krw": 0.0,
                "weights": [],
                "concentration": None,
                "exposure": None,
                "risk": {"windows": [], "actual": None, "actual_error": None},
                "correlation": None,
                "betas": [],
                "total_risk_pct_equity": None,
                "violations": [],
                "required_annual_return_pct": None,
                "goal_years": None,
                "caveats": ["보유 종목이 없어 점검할 것이 없습니다."],
            }

        limits = policy.limits(RiskLimits.from_settings(self.settings))
        w = engine.weights(views, cash_krw)
        exp = engine.exposure(views, cash_krw)
        conc = engine.concentration(w)
        weights_pct = {x.symbol: x.weight_pct for x in w}
        asset_class = {h.symbol: h.asset_class for h in views}
        currency = {h.symbol: h.currency for h in views}
        grid, ppy = engine.choose_grid(asset_class)

        caveats: list[str] = [engine.PAST_CAVEAT_KO]
        start = today - timedelta(days=WINDOWS[-1][1]) - HISTORY_MARGIN
        closes, errors = self._native_closes(views, start)
        for symbol, reason in errors.items():
            caveats.append(f"{symbol}: {reason}. 과거 변동성 계산에서 제외했습니다.")
        fx_series, fx_error = self._bars(FX_USDKRW, start)
        if fx_series is None:
            fx_series = pd.Series(dtype=float)
            caveats.append(f"USD/KRW: {fx_error}. 달러 종목의 원화 수익률을 계산하지 못했습니다.")

        returns: pd.DataFrame | None
        try:
            returns = engine.krw_return_frame(
                closes, fx_series, currency, grid, asset_class=asset_class
            )
        except ValueError as exc:
            returns = None
            caveats.append(f"과거 수익률을 만들지 못했습니다: {exc}")
        windows = [
            self._window(returns, name, days, weights_pct, exp.equity_krw, ppy, grid, today)
            for name, days in WINDOWS
        ]
        risk3y = windows[-1]
        correlation = self._correlation(returns, list(weights_pct), today)
        betas = self._betas(views, today)
        actual, actual_error = self._actual(today)
        if actual is not None:
            caveats += [ACTUAL_CURVE_NOTE_KO, IMPORTED_DATES_CAVEAT_KO]

        check = self.rules.check_all()
        total_risk = check["total_risk_pct_equity"]
        kill_tripped = bool(check["kill_switch"]["tripped"])
        viols = engine.violations(
            policy, w, exp, risk3y, total_risk, cash, today, kill_tripped, limits
        )

        required, years = None, None
        if policy.goal_krw is not None and policy.goal_date is not None:
            years = (policy.goal_date - today).days / 365.25
            if years > 0:
                required = engine.required_annual_return_pct(
                    exp.equity_krw, policy.monthly_contribution_krw, policy.goal_krw, years
                )
                caveats.append(REQUIRED_RETURN_NOTE_KO)

        return base | {
            "empty": False,
            "equity_krw": exp.equity_krw,
            "invested_krw": exp.invested_krw,
            "weights": [asdict(x) | {"cap_pct": limits.symbol_cap(x.symbol) * 100} for x in w],
            "concentration": asdict(conc),
            "exposure": asdict(exp),
            "risk": {
                "windows": [self._window_dict(x) for x in windows],
                "actual": actual,
                "actual_error": actual_error,
            },
            "correlation": correlation,
            "betas": betas,
            "total_risk_pct_equity": total_risk,
            "violations": [asdict(v) for v in viols],
            "required_annual_return_pct": required,
            "goal_years": years,
            "caveats": caveats,
        }

    def _window(
        self,
        returns: pd.DataFrame | None,
        name: str,
        days: int,
        weights_pct: Mapping[str, float],
        equity_krw: float,
        ppy: int,
        grid: str,
        today: date,
    ) -> RiskWindow:
        """`risk_window` over the returns of the last `days`, or an unusable window naming
        why (no returns at all, or none inside the window)."""
        if returns is not None:
            cut = returns[returns.index >= pd.Timestamp(today - timedelta(days=days))]
            try:
                return engine.risk_window(
                    cut, weights_pct, equity_krw, name=name, periods_per_year=ppy, grid=grid
                )
            except ValueError as exc:
                reason = f"창 안의 수익률을 계산할 수 없습니다 ({exc})"
        else:
            reason = "과거 수익률이 없어 계산하지 못했습니다"
        return RiskWindow(
            name=name,
            grid=grid,
            periods_per_year=ppy,
            rows=0,
            start=None,
            end=None,
            annual_vol_pct=0.0,
            swing_1sigma_krw=0.0,
            max_drawdown_pct=0.0,
            drawdown_peak=None,
            drawdown_trough=None,
            coverage_pct=0.0,
            included=(),
            excluded=tuple(engine.Excluded(s, 0) for s in weights_pct),
            method="none",
            usable=False,
            reason=reason,
        )

    @staticmethod
    def _window_dict(w: RiskWindow) -> dict:
        d = asdict(w)
        d["included"] = list(w.included)
        d["excluded"] = [asdict(e) for e in w.excluded]
        return d

    @staticmethod
    def _correlation(returns: pd.DataFrame | None, symbols: list[str], today: date) -> dict:
        """Pairwise correlation over the 3-year window for the heatmap."""
        if returns is not None:
            cut = returns[returns.index >= pd.Timestamp(today - timedelta(days=WINDOWS[-1][1]))]
            try:
                t = engine.correlation_table(cut)
                return {
                    "symbols": list(t.symbols),
                    "matrix": [list(row) for row in t.matrix],
                    "method": t.method,
                    "rows": t.rows,
                    "excluded": list(t.excluded),
                }
            except ValueError:
                pass
        return {"symbols": [], "matrix": [], "method": "none", "rows": 0, "excluded": symbols}

    def _betas(self, views: Sequence[HoldingView], today: date) -> list[dict]:
        """Each symbol's beta to the benchmark of its asset class and trade currency over the
        last year, both sides in that currency. A symbol that is its own benchmark is left
        out; missing bars are reported, not replaced."""
        start = today - timedelta(days=BETA_WINDOW_DAYS + 10)
        cache: dict[str, tuple[pd.Series | None, str | None]] = {}

        def bars(qsym: str) -> tuple[pd.Series | None, str | None]:
            if qsym not in cache:
                cache[qsym] = self._bars(qsym, start)
            return cache[qsym]

        out: list[dict] = []
        for h in views:
            bench = BETA_BENCHMARKS.get((h.asset_class, h.currency))
            qsym = quote_symbol(h.symbol, Currency(h.currency))
            if bench is None or qsym == bench or h.symbol == bench:
                continue
            item = {
                "symbol": h.symbol,
                "benchmark": bench,
                "window": "1y",
                "beta": None,
                "r2": None,
                "rows": 0,
                "reason": None,
            }
            y, y_err = bars(qsym)
            x, x_err = bars(bench)
            if y is None or x is None:
                item["reason"] = f"{qsym if y is None else bench}: {y_err or x_err}"
                out.append(item)
                continue
            b = engine.beta(y.pct_change().dropna(), x.pct_change().dropna())
            if b is None:
                item["reason"] = "겹치는 날이 60일보다 적어 계산하지 않았습니다"
            else:
                item.update({"beta": b.beta, "r2": b.r2, "rows": b.rows})
            out.append(item)
        return out

    def _flows(self, txs: Sequence[Transaction]) -> pd.Series:
        """Net won that entered the portfolio per day (buys positive, sells negative), at the
        rate the ledger itself used for each trade."""
        fx_on = self.market.usd_krw_lookup(txs[0].trade_date - timedelta(days=10))
        flows = cash_flows(txs, fx_on)
        return _series((float(f.amount_krw) for f in flows), (f.date for f in flows))

    def _actual(self, today: date) -> tuple[dict | None, str | None]:
        """Drawdown and kill-switch triggers of the real value curve with deposits taken out
        (`twr_index`), for information: it never trips the switch (D-027).

        Fails closed (None plus the reason) while a trade fails the 20x price rule, since its
        deposit would read as an impossible one-day loss, and when the engine refuses the
        curve (a day with `1 + r <= 0`); the reason is shown as it is."""
        txs = self._transactions()
        if not txs:
            return None, None
        suspicious = self._suspicious_trades(txs)
        if suspicious:
            symbols = ", ".join(sorted({t.symbol for t in suspicious}))
            return None, SUSPICIOUS_ACTUAL_KO.format(n=len(suspicious), symbols=symbols)
        points = self.portfolio.history()
        if len(points) < 2:
            return None, "자산 추이가 2일 미만이라 계산하지 않았습니다"
        values = _series((p.market_value_krw for p in points), (p.date for p in points))
        try:
            index = engine.twr_index(values, self._flows(txs))
        except ValueError as exc:
            return None, str(exc)
        limits = RiskLimits.from_settings(self.settings)
        peak = float(index.cummax().iloc[-1])
        current = 1.0 - float(index.iloc[-1]) / peak if peak > 0 else 0.0
        triggers = kill_switch_triggers(index, limits)
        since = today - timedelta(days=365)
        return {
            "since": points[0].date,
            "points": len(points),
            "twr_max_drawdown_pct": max_drawdown(index.to_numpy()) * 100,
            "current_drawdown_pct": max(current, 0.0) * 100,
            "daily_loss_breaches_1y": sum(
                1 for t in triggers if t.reason_code == "daily_loss" and t.date >= since
            ),
            "drawdown_breaches_1y": sum(
                1 for t in triggers if t.reason_code == "max_drawdown" and t.date >= since
            ),
            "limit_drawdown_pct": limits.max_drawdown * 100,
            "limit_daily_loss_pct": limits.daily_loss_limit * 100,
        }, None

    # --- rebalancing -----------------------------------------------------------------------

    def rebalance(self) -> dict:
        """The orders a move to the policy's targets would mean, over the current holdings
        only, checked against the limits the way paper trading checks them. Nothing is placed;
        fees are 0 and the UI says so."""
        policy = self._policy_obj(self.get_policy())
        cash = self._cash_record(self.get_cash())
        fx_now = self._fx_now()
        cash_krw = cash.total_krw(fx_now) if cash is not None else None
        _, views = self._holding_views()
        headline = {
            "headline_ko": engine.REBALANCE_HEADLINE_KO,
            "disclaimer_ko": engine.DISCLAIMER_KO,
            "band_pt": policy.rebalance_band_pt,
            "cash_known": cash is not None,
        }
        if not views:
            return headline | {
                "empty": True,
                "equity_krw": cash_krw or 0.0,
                "class_targets": {},
                "unallocated_pct": 0.0,
                "targets": [],
                "orders": [],
                "after": None,
                "notes": ["보유 종목이 없어 비교할 비중이 없습니다."],
            }

        limits = policy.limits(RiskLimits.from_settings(self.settings))
        plan = engine.construct_targets(views, policy, limits, cash_known=cash is not None)
        book = Book(cash_krw or 0.0, {h.symbol: h.value_krw for h in views})
        decisions = engine.rebalance_plan(book, plan, limits, policy.rebalance_band_pt)
        w = {x.symbol: x for x in engine.weights(views, cash_krw)}
        by_symbol = {h.symbol: h for h in views}

        targets = []
        for h in views:
            target = plan.targets.get(h.symbol, 0.0) * 100
            current = w[h.symbol].weight_pct
            targets.append(
                {
                    "symbol": h.symbol,
                    "asset_class": h.asset_class,
                    "current_pct": current,
                    "target_pct": target,
                    "drift_pt": current - target,
                    "source": plan.source.get(h.symbol, "remainder"),
                    "capped": h.symbol in plan.capped,
                }
            )

        orders = []
        after = book
        for d in decisions:
            h = by_symbol[d.order.symbol]
            allowed = d.notional
            qty = None
            if h.price_krw > 0:
                qty = round(allowed / h.price_krw, 4 if h.asset_class == "crypto" else 2)
            realized = None
            if d.order.side == "sell" and h.value_krw > 0:
                realized = allowed * (1.0 - h.cost_basis_krw / h.value_krw)
            orders.append(
                {
                    "symbol": h.symbol,
                    "side": d.order.side,
                    "requested_krw": d.order.notional,
                    "allowed_krw": allowed,
                    "status": d.status,
                    "reasons": list(d.reasons),
                    "labels": [BLOCK_LABELS.get(r, r) for r in d.reasons],
                    "approx_qty": qty,
                    "price": h.price,
                    "currency": h.currency,
                    "price_krw": h.price_krw,
                    "realized_pnl_krw_if_sold": realized,
                }
            )
            after = apply_decision(after, d)

        equity_after = after.equity
        notes = list(plan.notes)
        if cash is None:
            notes.append(engine.NO_CASH_NOTE_KO)
        notes.append(FEES_CAVEAT_KO)
        return headline | {
            "empty": False,
            "equity_krw": book.equity,
            "class_targets": dict(plan.class_targets),
            "unallocated_pct": plan.unallocated_pct,
            "targets": targets,
            "orders": orders,
            "after": {
                "weights": [
                    {"symbol": s, "weight_pct": v / equity_after * 100 if equity_after > 0 else 0.0}
                    for s, v in after.positions.items()
                ],
                "cash_krw": after.cash,
                "cash_pct": after.cash / equity_after * 100
                if cash is not None and equity_after > 0
                else None,
            },
            "notes": notes,
        }

    # --- habits in the trade log -----------------------------------------------------------

    def _trade_views(
        self, txs: Sequence[Transaction], events: Iterable[CorporateAction]
    ) -> list[TradeView]:
        """Every trade with the position state just before it, from one replay of the ledger
        (`ledger.timeline`, confirmed splits included). Average costs are in the trade's own
        currency: the ledger's dollar cost for USD trades, its exact won cost for KRW ones."""
        positions: dict[str, Position] = {}
        views: list[TradeView] = []
        for item in timeline(txs, events):
            if isinstance(item, CorporateAction):
                pos = positions.get(item.symbol)
                if pos is not None:
                    pos.apply_action(item)
                continue
            pos = positions.setdefault(item.symbol, Position(item.symbol, item.asset_type))
            currency = item.currency or Currency.USD
            qty_before = float(pos.quantity)
            avg_before: float | None = None
            if pos.quantity > ZERO:
                avg_before = float(pos.avg_cost_krw if currency == Currency.KRW else pos.avg_cost)
            pos.apply(item)
            views.append(
                TradeView(
                    id=item.id,
                    symbol=item.symbol,
                    asset_class=_asset_class(item.asset_type),
                    side=item.side.value,
                    date=item.trade_date,
                    quantity=float(item.quantity),
                    price=float(item.price),
                    currency=currency.value,
                    avg_cost_before=avg_before,
                    qty_before=qty_before,
                )
            )
        return views

    def patterns(self) -> dict:
        """Habits in the last year of trades, each as a count with the trades behind it, plus
        held positions sitting below their stop-loss. Not a signal; the user's own rules
        (`rule_settings`) supply the stop-loss percentages."""
        today = self.today()
        window_start = today - timedelta(days=PATTERN_WINDOW_DAYS)
        txs = self._transactions()
        base = {"window_start": window_start, "window_end": today}
        if not txs:
            return base | {
                "empty": True,
                "trades_considered": 0,
                "trades_without_bars": 0,
                "patterns": [],
                "monthly": [],
                "rule_lag": [],
                "caveats": ["거래 기록이 없습니다."],
            }

        trades = self._trade_views(txs, confirmed_events(self.db))
        recent = [t for t in trades if t.date >= window_start]
        holdings, views = self._holding_views()
        rules = self.rules.get_settings()

        # Closes in each trade's currency for the symbols traded recently or still held.
        symbols: dict[str, str] = {t.symbol: t.currency for t in recent}
        for h in views:
            symbols.setdefault(h.symbol, h.currency)
        closes: dict[str, pd.Series] = {}
        missing: list[str] = []
        for symbol, cur in symbols.items():
            s, _ = self._bars(
                quote_symbol(symbol, Currency(cur)), window_start - PATTERN_BARS_MARGIN
            )
            if s is None:
                missing.append(symbol)
            else:
                closes[symbol] = s

        def cut_pct_of(symbol: str, asset_class: str) -> float:
            return float(rules.resolve(symbol, asset_class).cut_loss_pct)  # type: ignore[arg-type]

        chasing, skipped = engine.chasing_buys(recent, closes)
        averaging = engine.averaging_down_below_cut(recent, cut_pct_of)
        rebuys = engine.quick_rebuy_after_loss(recent)
        counts = engine.monthly_trade_counts(trades)
        busy = engine.overtrading(counts)
        positions = [
            (
                h.symbol,
                float(h.avg_cost_krw if h.currency == Currency.KRW else h.avg_cost),
                cut_pct_of(h.symbol, _asset_class(h.asset_type)),
            )
            for h in holdings
        ]
        lag = engine.rule_lag(positions, closes)
        currency_of = {h.symbol: h.currency.value for h in holdings}

        def pattern(code: str, flags: Sequence[engine.Flag], months: Sequence[str] = ()) -> dict:
            return {
                "code": code,
                "label_ko": engine.PATTERN_LABELS_KO[code],
                "count": len(flags) if flags else len(months),
                "detail": PATTERN_DETAILS_KO[code],
                "trades": [asdict(f) for f in flags],
                "months": list(months),
            }

        caveats = [
            "거래 기록에서 집계한 패턴이며, 예측이나 신호가 아닙니다.",
            "스크린샷으로 가져온 거래는 날짜가 업로드일일 수 있어 패턴이 실제와 다를 수 있습니다.",
        ]
        if missing:
            caveats.append(f"시세를 받지 못해 건너뛴 종목: {', '.join(sorted(missing))}")
        return base | {
            "empty": False,
            "trades_considered": len(recent),
            "trades_without_bars": skipped,
            "patterns": [
                pattern("chasing_buy", chasing),
                pattern("averaging_down_below_cut", averaging),
                pattern("quick_rebuy_after_loss", rebuys),
                pattern("overtrading", [], [m.month for m in busy]),
            ],
            "monthly": [asdict(m) for m in counts],
            "rule_lag": [asdict(f) | {"currency": currency_of.get(f.symbol, "USD")} for f in lag],
            "caveats": caveats,
        }

    # --- monthly review --------------------------------------------------------------------

    @staticmethod
    def _parse_month(month: str | None, today: date) -> tuple[int, int]:
        if month is None:
            return today.year, today.month
        m = MONTH_RE.match(month)
        if m is None or not 1 <= int(m.group(2)) <= 12:
            raise DomainError(f"달은 YYYY-MM 형식이어야 합니다 ({month})", code="invalid_month")
        return int(m.group(1)), int(m.group(2))

    @staticmethod
    def _months(first: date, today: date) -> list[str]:
        """Calendar months from `first`'s to `today`'s, newest first."""
        out: list[str] = []
        year, month = today.year, today.month
        while (year, month) >= (first.year, first.month):
            out.append(f"{year:04d}-{month:02d}")
            year, month = (year - 1, 12) if month == 1 else (year, month - 1)
        return out

    def review(self, month: str | None = None) -> dict:
        """One calendar month: the value change split into cash put in and market result,
        realized P&L and dividends from the ledger, the same money in SPY and BTC, the
        trades made and the ones a habit check flagged."""
        today = self.today()
        year, m = self._parse_month(month, today)
        first_day = date(year, m, 1)
        if first_day > today:
            raise DomainError("아직 오지 않은 달입니다", code="invalid_month")
        next_month = date(year + (m == 12), m % 12 + 1, 1)
        start = first_day - timedelta(days=1)
        end = min(next_month - timedelta(days=1), today)
        key = _month_key(first_day)

        txs = self._transactions()
        base = {"month": key, "start": start, "end": end}
        if not txs:
            return base | {
                "empty": True,
                "start_point": None,
                "end_point": None,
                "start_value_krw": 0.0,
                "end_value_krw": 0.0,
                "change_krw": 0.0,
                "contributions_krw": 0.0,
                "market_pnl_krw": 0.0,
                "realized_pnl_krw": 0.0,
                "dividends_krw": 0.0,
                "benchmarks": [],
                "trades": {"buys": 0, "sells": 0},
                "flagged_trades": [],
                "flags_counted": True,
                "suspicious_trades": 0,
                "violations_now": 0,
                "months_available": [key],
                "caveats": ["거래 기록이 없습니다."],
            }

        # My curve and the benchmarks on one grid; `compare` runs history() once for both.
        comparison = self.benchmarks.compare(list(REVIEW_BENCHMARKS), start)
        flows = self._flows(txs)
        review: engine.PeriodReview | None = None
        if comparison.mine:
            history = _series(
                (p.market_value_krw for p in comparison.mine), (p.date for p in comparison.mine)
            )
            try:
                review = engine.period_review(history, flows, start, end)
            except ValueError:
                review = None
        change = review.change_krw if review is not None else 0.0

        fx_on = self.market.usd_krw_lookup(txs[0].trade_date - timedelta(days=10))
        events = confirmed_events(self.db)
        at_end = build_positions(txs, as_of=end, fx_on=fx_on, events=events)
        at_start = build_positions(txs, as_of=start, fx_on=fx_on, events=events)

        def total(positions: Mapping[str, Position], attr: str) -> float:
            return float(sum((getattr(p, attr) for p in positions.values()), ZERO))

        benchmarks = []
        for s in comparison.benchmarks:
            before = [p for p in s.points if p.date <= start]
            until = [p for p in s.points if p.date <= end]
            start_value = before[-1].value_krw if before else 0.0
            end_value = until[-1].value_krw if until else 0.0
            benchmarks.append(
                {
                    "symbol": s.symbol,
                    "name_ko": s.name_ko,
                    "start_value_krw": start_value,
                    "end_value_krw": end_value,
                    "change_krw": end_value - start_value,
                    "excess_krw": change - (end_value - start_value),
                }
            )

        in_month = [t for t in txs if first_day <= t.trade_date <= end]
        # Habit flags exist only inside the pattern window (today − 1 year); a month that
        # starts before it is not counted at all rather than counted in part (N-COACH-2).
        flags_counted = first_day >= today - timedelta(days=PATTERN_WINDOW_DAYS)
        flagged = (
            [
                f
                for p in self.patterns()["patterns"]
                for f in p["trades"]
                if first_day <= f["date"] <= end
            ]
            if flags_counted
            else []
        )
        # Mis-priced trades up to the end of the month distort the start/end values and the
        # deposits; the ledger facts stay, the caveat comes first (N-COACH-1).
        suspicious = [t for t in self._suspicious_trades(txs) if t.trade_date <= end]
        caveats: list[str] = []
        if suspicious:
            caveats.append(SUSPICIOUS_REVIEW_KO.format(n=len(suspicious)))
        if not flags_counted:
            caveats.append(FLAGS_OUTSIDE_WINDOW_KO)
        caveats += [BENCHMARK_CAVEAT_KO, FEES_CAVEAT_KO, IMPORTED_DATES_CAVEAT_KO]
        return base | {
            "empty": False,
            "start_point": review.start_point if review is not None else None,
            "end_point": review.end_point if review is not None else None,
            "start_value_krw": review.start_value_krw if review is not None else 0.0,
            "end_value_krw": review.end_value_krw if review is not None else 0.0,
            "change_krw": change,
            "contributions_krw": review.contributions_krw if review is not None else 0.0,
            "market_pnl_krw": review.market_pnl_krw if review is not None else 0.0,
            "realized_pnl_krw": total(at_end, "realized_pnl_krw")
            - total(at_start, "realized_pnl_krw"),
            "dividends_krw": total(at_end, "dividends_krw") - total(at_start, "dividends_krw"),
            "benchmarks": benchmarks,
            "trades": {
                "buys": sum(1 for t in in_month if t.side == Side.BUY),
                "sells": sum(1 for t in in_month if t.side == Side.SELL),
            },
            "flagged_trades": flagged,
            "flags_counted": flags_counted,
            "suspicious_trades": len(suspicious),
            "violations_now": self._violations_now(today),
            "months_available": self._months(txs[0].trade_date, today),
            "caveats": caveats,
        }

    def _violations_now(self, today: date) -> int:
        """Warnings from the weight- and exposure-based checks alone (no bars), for the
        review's headline count."""
        policy = self._policy_obj(self.get_policy())
        cash = self._cash_record(self.get_cash())
        _, views = self._holding_views()
        if not views:
            return 0
        cash_krw = cash.total_krw(self._fx_now()) if cash is not None else None
        limits = policy.limits(RiskLimits.from_settings(self.settings))
        found = engine.violations(
            policy,
            engine.weights(views, cash_krw),
            engine.exposure(views, cash_krw),
            None,
            None,
            cash,
            today,
            KillSwitch(self.db).state().tripped,
            limits,
        )
        return sum(1 for v in found if v.severity == "warn")
