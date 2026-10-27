"""Serve the buy-more / stop-loss rule checks (app/strategy/rules.py, DECISIONS.md D-027).

The engine is pure; this service feeds it. Each holding becomes a `PositionView` in its own
pricing currency (USD, or Upbit won for coins held in KRW), its final daily bars are loaded
from the market cache, `rules.evaluate` runs, and the forecaster's 1-month range is attached
as a reference probability. The user's rule settings live in one `rule_settings` row.

This is not a signal and places no orders; `AM_LIVE_TRADING` is read for display only.
"""

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, fields
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.data.assets import base_symbol, resolve_symbol
from app.data.provider import MarketDataError
from app.db.models import (
    ActionKind,
    AssetType,
    CorporateAction,
    Currency,
    RuleSettingsRow,
    Side,
    Transaction,
)
from app.forecast.panel import AssetClass
from app.services.corporate_actions import confirmed_events
from app.services.errors import DomainError
from app.services.forecasts import ForecastService
from app.services.ledger import ZERO, split_quantity, timeline
from app.services.market_data import MarketDataService, SymbolNotFoundError
from app.services.portfolio import Holding, PortfolioService, quote_symbol
from app.strategy.execution import KillState, KillSwitch
from app.strategy.risk import RiskLimits
from app.strategy.rules import (
    BLOCK_LABELS,
    PROB_CAVEAT_KO,
    STATUS_LABELS,
    AssetClassRule,
    LimitState,
    PositionView,
    RuleSettings,
    SymbolRule,
    evaluate,
    prob_below,
    prob_below_label,
)

log = logging.getLogger(__name__)

# Bars loaded per holding: enough for a 60-bar average plus a 5-bar streak with margin, and
# the same window the forecaster's price panel uses.
BARS_LOOKBACK = timedelta(days=400)
# The forecast horizon the reference probability is read from.
REFERENCE_HORIZON = "1m"

GLOBAL_FIELDS = tuple(f.name for f in fields(RuleSettings) if f.name not in ("targets", "crypto"))
CRYPTO_FIELDS = tuple(f.name for f in fields(AssetClassRule))
SYMBOL_FIELDS = tuple(f.name for f in fields(SymbolRule))


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _num(v: object) -> object:
    """Decimals from the API become the floats the engine works in; ints and bools stay."""
    return float(v) if isinstance(v, Decimal) else v


def add_steps_done(items: Iterable[Transaction | CorporateAction]) -> int:
    """Buys added since the current position started, from one symbol's replay order
    (`ledger.timeline`). The first buy of a position is not a step. A sell that empties the
    position ends it, so the next buy starts counting afresh; confirmed splits scale the
    quantity so a post-split sell closes the position exactly as the ledger sees it."""
    qty, buys = ZERO, 0
    for item in items:
        if isinstance(item, CorporateAction):
            if item.kind == ActionKind.SPLIT and qty > ZERO:
                qty = split_quantity(qty, item.value)
            continue
        if item.side == Side.BUY:
            if qty == ZERO:
                buys = 0
            buys += 1
            qty += item.quantity
        else:
            qty = max(qty - item.quantity, ZERO)
            if qty == ZERO:
                buys = 0
    return max(buys - 1, 0)


class RuleService:
    def __init__(
        self,
        db: Session,
        market: MarketDataService,
        portfolio: PortfolioService,
        settings: Settings | None = None,
        forecasts: ForecastService | None = None,
        today: Callable[[], date] = date.today,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.db = db
        self.market = market
        self.portfolio = portfolio
        self.settings = settings or get_settings()
        self.forecasts = forecasts
        self.today = today
        self.now = now
        self.limits = RiskLimits.from_settings(self.settings)

    # --- settings --------------------------------------------------------------------------

    def defaults(self) -> RuleSettings:
        return RuleSettings.from_config(self.settings)

    def _row(self) -> RuleSettingsRow | None:
        return self.db.get(RuleSettingsRow, 1)

    def get_settings(self) -> RuleSettings:
        """The stored rules, or the `AM_RULES_*` defaults while nothing is stored."""
        row = self._row()
        return self.defaults() if row is None else self._from_row(row)

    def _from_row(self, row: RuleSettingsRow) -> RuleSettings:
        defaults = self.defaults()
        stored = dict(row.global_json or {})
        kwargs = {k: getattr(defaults, k) for k in GLOBAL_FIELDS}
        kwargs.update({k: v for k, v in stored.items() if k in GLOBAL_FIELDS})
        crypto_stored = stored.get("crypto")
        crypto = (
            defaults.crypto
            if crypto_stored is None
            else AssetClassRule(**{k: v for k, v in crypto_stored.items() if k in CRYPTO_FIELDS})
        )
        targets = {
            s: SymbolRule(**{k: v for k, v in (t or {}).items() if k in SYMBOL_FIELDS})
            for s, t in (row.targets_json or {}).items()
        }
        try:
            return RuleSettings(**kwargs, crypto=crypto, targets=targets)
        except (TypeError, ValueError) as exc:
            # A stored value the current engine rejects (its constraints changed, or the row
            # was edited by hand): say so instead of quietly falling back to the defaults.
            raise DomainError(
                f"저장된 규칙 설정을 적용할 수 없습니다 ({exc}). 규칙 페이지에서 다시 저장하세요.",
                code="invalid_rule_settings",
            ) from exc

    def settings_payload(self) -> dict:
        row = self._row()
        current = self.get_settings()
        defaults = self.defaults()
        return {
            "global": _global_dict(current),
            "crypto": asdict(current.crypto),
            "targets": {s: asdict(r) for s, r in current.targets.items()},
            "defaults": {"global": _global_dict(defaults), "crypto": asdict(defaults.crypto)},
            "warnings": list(current.validate_notes()),
            "updated_at": row.updated_at if row is not None else None,
            "live_trading": self.settings.live_trading,
        }

    def update_settings(
        self,
        global_values: Mapping[str, object],
        crypto_values: Mapping[str, object] | None,
        targets: Mapping[str, Mapping[str, object]],
    ) -> dict:
        """Validate through the engine (`RuleSettings.__post_init__`) and store. Symbols are
        normalized to their dollar form (`KRW-BTC` → `BTC-USD`); an override whose fields are
        all empty is dropped, which means "use the global value"."""
        try:
            kwargs = {k: _num(global_values[k]) for k in GLOBAL_FIELDS}
            crypto = (
                self.defaults().crypto
                if crypto_values is None
                else AssetClassRule(**{k: _num(crypto_values.get(k)) for k in CRYPTO_FIELDS})
            )
            parsed: dict[str, SymbolRule] = {}
            for raw, over in targets.items():
                symbol = base_symbol(resolve_symbol(raw))
                values = {
                    k: _num(v) for k, v in over.items() if k in SYMBOL_FIELDS and v is not None
                }
                if not values:
                    continue
                if symbol in parsed:
                    raise ValueError(f"{symbol} 규칙이 두 번 들어왔습니다")
                parsed[symbol] = SymbolRule(**values)
            rules = RuleSettings(**kwargs, crypto=crypto, targets=parsed)
        except (TypeError, ValueError, KeyError) as exc:
            raise DomainError(
                f"규칙 설정이 잘못되었습니다: {exc}", code="invalid_rule_settings"
            ) from exc

        row = self._row()
        if row is None:
            row = RuleSettingsRow(id=1, global_json={}, targets_json={})
            self.db.add(row)
        row.global_json = _global_dict(rules) | {"crypto": asdict(rules.crypto)}
        row.targets_json = {
            s: {k: v for k, v in asdict(r).items() if v is not None}
            for s, r in rules.targets.items()
        }
        row.updated_at = self.now()
        self.db.commit()
        return self.settings_payload()

    # --- kill switch -----------------------------------------------------------------------

    def reset_kill_switch(self, detail: str = "") -> KillState:
        """Resume paper trading after a trip. The actor is always the user (D-033 §7): the
        system trips, only the user resets. Already off: nothing is written, the state is
        returned as is, so a double click does not add a second reset event."""
        switch = KillSwitch(self.db, clock=self.now)
        if switch.state().tripped:
            switch.reset(actor="user", detail=detail)
        return switch.state()

    # --- checks ----------------------------------------------------------------------------

    def check_all(self) -> dict:
        rules = self.get_settings()
        kill = KillSwitch(self.db).state()
        limits = LimitState(
            limits=self.limits,
            kill_switch_tripped=kill.tripped,
            kill_switch_reason=kill.reason_code,
        )
        holdings = [h for h in self.portfolio.holdings() if h.quantity > ZERO]
        # Total equity in each pricing currency, for the loss-at-stop share. Real holdings
        # have no cash record, so equity is the holdings' value (same base as `weight`).
        equity_usd = float(sum((h.market_value for h in holdings), ZERO))
        equity_krw = float(sum((h.market_value_krw for h in holdings), ZERO))
        txs = list(self.db.scalars(select(Transaction)))
        splits = [e for e in confirmed_events(self.db) if e.kind == ActionKind.SPLIT]
        today = self.today()

        checks: list[dict] = []
        skipped: list[dict] = []
        for h in holdings:
            steps = add_steps_done(
                timeline(
                    [t for t in txs if t.symbol == h.symbol],
                    [e for e in splits if e.symbol == h.symbol],
                )
            )
            krw = h.currency == Currency.KRW
            try:
                checks.append(
                    self._check(h, steps, rules, limits, today, equity_krw if krw else equity_usd)
                )
            except ValueError as exc:
                # The engine fails closed on input it cannot judge (e.g. a zero average cost
                # from a trade without an FX rate). Report it rather than invent a status.
                skipped.append({"symbol": h.symbol, "reason": str(exc)})
        # Loss if every stop-loss were hit, as a share of total equity. Each check's share is
        # already against the equity in its own pricing currency, and the won and dollar
        # totals are the same holdings at today's rate, so the shares simply add up.
        shares = [c["risk_pct_equity"] for c in checks if c["risk_pct_equity"] is not None]
        return {
            "checks": checks,
            "skipped": skipped,
            "total_risk_pct_equity": sum(shares) if shares else None,
            "kill_switch": kill_switch_payload(kill),
            "live_trading": self.settings.live_trading,
            "labels": {
                "status": dict(STATUS_LABELS),
                "block": dict(BLOCK_LABELS),
                "prob_caveat": PROB_CAVEAT_KO,
            },
            "settings_notes": list(rules.validate_notes()),
            "checked_at": self.now(),
        }

    def _check(
        self,
        h: Holding,
        steps: int,
        rules: RuleSettings,
        limits: LimitState,
        today: date,
        equity: float,
    ) -> dict:
        # Everything in the position's pricing currency: Upbit won for KRW coins (their
        # average cost is exact in won), dollars otherwise.
        krw = h.currency == Currency.KRW
        price = float(h.price_krw if krw else h.price)
        avg_cost = float(h.avg_cost_krw if krw else h.avg_cost)
        asset_class: AssetClass = "crypto" if h.asset_type == AssetType.CRYPTO else "stock"
        bars, history_error = self._bars(quote_symbol(h.symbol, h.currency), today)
        position = PositionView(
            symbol=h.symbol,
            asset_class=asset_class,
            quantity=float(h.quantity),
            avg_cost=avg_cost,
            price=price,
            weight_pct=float(h.weight),
            add_steps_done=steps,
        )
        has_bars = bars is not None and not bars.empty
        check = evaluate(
            position,
            bars,
            rules,
            limits,
            as_of=None if has_bars else today,
            equity=equity if equity > 0 else None,
        )
        prob, prob_label, forecast_status = self._cut_prob(h, check.levels.cut_price, krw)
        return {
            "symbol": h.symbol,
            "asset_type": h.asset_type,
            "currency": h.currency,
            "status": check.status,
            "label_ko": check.label_ko,
            "chip_ko": check.chip_ko,
            "triggers": [asdict(t) for t in check.triggers],
            "levels": asdict(check.levels),
            "rule": asdict(rules.resolve(h.symbol, asset_class)),
            "price": price,
            "avg_cost": avg_cost,
            "quantity": float(h.quantity),
            "weight_pct": float(h.weight),
            "add_steps_done": steps,
            "cut_distance_pct": check.cut_distance_pct,
            "add_distance_pct": check.add_distance_pct,
            "blocked_by": list(check.blocked_by),
            "blocked_labels": [BLOCK_LABELS.get(c, c) for c in check.blocked_by],
            "add_cap_krw": check.add_cap_krw,
            "risk_pct_equity": check.risk_pct_equity,
            "weight_room_pt": check.weight_room_pt,
            "notes": list(check.notes),
            "as_of": check.as_of,
            "bars": int(len(bars)) if has_bars else 0,
            "history_error": history_error,
            "cut_prob_1m": prob,
            "cut_prob_1m_label": prob_label,
            "forecast_status": forecast_status,
        }

    def _bars(self, qsym: str, today: date) -> tuple[pd.DataFrame | None, str | None]:
        """Final daily bars of the pricing symbol, or None with the reason they are missing.
        No synthetic fallback: the check then runs on the price alone and says so."""
        try:
            rows = self.market.get_history(qsym, today - BARS_LOOKBACK, final_only=True)
        except SymbolNotFoundError:
            return None, f"{qsym}: 시세를 찾을 수 없습니다"
        except MarketDataError as exc:
            return None, f"{qsym}: 시세를 받지 못했습니다 ({type(exc).__name__})"
        if not rows:
            return None, f"{qsym}: 확정된 일봉이 없습니다"
        frame = pd.DataFrame(
            {
                "date": [r.date for r in rows],
                "close": [r.close for r in rows],
                "high": [r.high for r in rows],
            }
        )
        return frame, None

    def _cut_prob(
        self, h: Holding, cut_price: float, krw: bool
    ) -> tuple[float | None, str | None, str]:
        """Reference only: how likely the 1-month forecast range puts the close below the
        stop-loss price. The forecast is in dollars; a won level is converted with the
        forecast's premium-included rate (`krw_rate`) or, failing that, today's USD/KRW."""
        if self.forecasts is None:
            return None, None, "unavailable"
        try:
            fc = self.forecasts.forecast(h.symbol)
        except DomainError as exc:
            # not_trained / insufficient_history / not a held symbol: shown as the reason.
            return None, None, exc.code or "unavailable"
        except Exception as exc:  # inference touches the market cache and model files
            log.warning("Forecast reference for %s failed: %s", h.symbol, type(exc).__name__)
            return None, None, f"error:{type(exc).__name__}"
        horizon = next((x for x in fc["horizons"] if x["horizon"] == REFERENCE_HORIZON), None)
        if horizon is None:
            return None, None, "no_1m_horizon"
        level = cut_price
        if krw:
            rate = fc.get("krw_rate")
            if rate is None:
                rate = float(self.market.usd_krw().price)
            level = cut_price / rate
        args = (level, horizon["base_price"], horizon["p10"], horizon["p50"], horizon["p90"])
        p = prob_below(*args)
        if p is None:
            return None, None, "invalid_quantiles"
        return p, prob_below_label(*args), "ok"


def _global_dict(rules: RuleSettings) -> dict:
    return {k: getattr(rules, k) for k in GLOBAL_FIELDS}


def kill_switch_payload(state: KillState) -> dict:
    """`KillSwitchOut` fields from the engine's state."""
    return {
        "tripped": state.tripped,
        "reason_code": state.reason_code,
        "detail": state.detail,
        "since": state.since,
    }
