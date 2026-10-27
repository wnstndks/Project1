"""Buy-more / stop-loss rule checks and the user's rule settings (plan G, DECISIONS.md D-027).

A rule check is not a trading signal: it is the result of the user's own rules against
their positions. The forecaster enters only as a reference probability.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import AssetType, Currency

# --- settings ---------------------------------------------------------------------------


class SymbolRuleIn(BaseModel):
    """Per-symbol overrides; a null field keeps the asset-class or global value. Numbers may
    arrive as strings and are parsed as exact decimals. Ranges are checked by the rule engine
    (`RuleSettings`), which answers 422 naming the field."""

    target_weight_pct: Decimal | None = None
    cut_loss_pct: Decimal | None = None
    trailing_drop_pct: Decimal | None = None
    add_step_pct: Decimal | None = None
    add_max_steps: int | None = None


class CryptoRuleIn(BaseModel):
    """Asset-class layer for coins between the global values and the symbol overrides; a
    null field keeps the global value."""

    cut_loss_pct: Decimal | None = None
    trailing_drop_pct: Decimal | None = None
    add_step_pct: Decimal | None = None


class RuleGlobalIn(BaseModel):
    cut_loss_pct: Decimal
    trailing_lookback_days: int
    trailing_drop_pct: Decimal
    below_ma_days: int
    ma_long: int
    ma_short: int
    add_step_pct: Decimal
    add_max_steps: int
    add_requires_above_ma_short: bool
    target_weight_gap_pt: Decimal
    max_risk_pct: Decimal


class RuleSettingsIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    global_: RuleGlobalIn = Field(alias="global")
    # Omitted: the `AM_RULES_CRYPTO_*` defaults.
    crypto: CryptoRuleIn | None = None
    targets: dict[str, SymbolRuleIn] = {}


class SymbolRuleOut(BaseModel):
    target_weight_pct: float | None = None
    cut_loss_pct: float | None = None
    trailing_drop_pct: float | None = None
    add_step_pct: float | None = None
    add_max_steps: int | None = None


class CryptoRuleOut(BaseModel):
    cut_loss_pct: float | None = None
    trailing_drop_pct: float | None = None
    add_step_pct: float | None = None


class RuleGlobalOut(BaseModel):
    cut_loss_pct: float
    trailing_lookback_days: int
    trailing_drop_pct: float
    below_ma_days: int
    ma_long: int
    ma_short: int
    add_step_pct: float
    add_max_steps: int
    add_requires_above_ma_short: bool
    target_weight_gap_pt: float
    max_risk_pct: float


class RuleDefaultsOut(BaseModel):
    """The `AM_RULES_*` values, for the settings page's reset button."""

    model_config = ConfigDict(populate_by_name=True)

    global_: RuleGlobalOut = Field(alias="global")
    crypto: CryptoRuleOut


class RuleSettingsOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    global_: RuleGlobalOut = Field(alias="global")
    crypto: CryptoRuleOut
    targets: dict[str, SymbolRuleOut]
    defaults: RuleDefaultsOut
    # Legal but self-defeating combinations (a buy-more step below the stop-loss), as text
    # (`RuleSettings.validate_notes()`); shown on the settings screen after a save.
    warnings: list[str]
    # None while no row is stored (the defaults apply).
    updated_at: datetime | None
    # Real orders are off unless the user set AM_LIVE_TRADING; shown here, never changed.
    live_trading: bool


# --- checks -----------------------------------------------------------------------------


class RuleTriggerOut(BaseModel):
    code: str
    label_ko: str
    detail: str
    kind: str  # cut | add | info


class RuleLevelsOut(BaseModel):
    """Prices in the position's currency (`RuleCheckOut.currency`)."""

    cut_price: float
    cut_loss_price: float
    trailing_high: float
    trailing_stop_price: float
    add_price: float | None
    next_add_step: int | None
    ma_short: float | None
    ma_long: float | None
    target_weight_pct: float | None
    # Loss if the stop-loss price is hit from here, in the position's currency.
    risk_amount: float


class ResolvedRuleOut(BaseModel):
    """The values that applied to this symbol: global → asset class → symbol overrides."""

    cut_loss_pct: float
    trailing_lookback_days: int
    trailing_drop_pct: float
    below_ma_days: int
    ma_long: int
    ma_short: int
    add_step_pct: float
    add_max_steps: int
    add_requires_above_ma_short: bool
    target_weight_gap_pt: float
    target_weight_pct: float | None


class RuleCheckOut(BaseModel):
    symbol: str
    asset_type: AssetType
    # Currency of `price`, `avg_cost` and every level: USD, or KRW for coins held on Upbit.
    currency: Currency
    status: str  # cut | add | hold
    # What the review is, by what fired (손절 검토 / 이익 보전 검토 / 추세 이탈 · 매도 검토 /
    # 추매 검토 / 관망); `chip_ko` is the short form for the holdings list.
    label_ko: str
    chip_ko: str
    triggers: list[RuleTriggerOut]
    levels: RuleLevelsOut
    rule: ResolvedRuleOut
    price: float
    avg_cost: float
    quantity: float
    weight_pct: float
    # Buys added since the current position started (the first buy is not a step).
    add_steps_done: int
    # Move from the current price to the level, in percent (negative = below the price).
    cut_distance_pct: float
    add_distance_pct: float | None
    # Why a buy would not be allowed now, as codes and Korean labels.
    blocked_by: list[str]
    blocked_labels: list[str]
    add_cap_krw: float | None
    # Loss at the stop as a share of total equity, in percent.
    risk_pct_equity: float | None
    # Weight the symbol may still add before its cap, in percentage points.
    weight_room_pt: float | None
    notes: list[str]
    # Date of the last final bar the bar-based conditions used.
    as_of: date
    bars: int
    # Why bars are missing, when they are. Never replaced by synthetic data.
    history_error: str | None
    # Reference only (D-027): chance the 1-month forecast range puts the close below the
    # stop-loss price, as a number and as the rounded text the UI shows.
    cut_prob_1m: float | None
    cut_prob_1m_label: str | None
    # ok | not_trained | insufficient_history | no_1m_horizon | unavailable | error:<Type>
    forecast_status: str


class SkippedCheckOut(BaseModel):
    symbol: str
    reason: str


class KillSwitchOut(BaseModel):
    tripped: bool
    reason_code: str | None
    detail: str
    since: datetime | None


class KillSwitchResetIn(BaseModel):
    """Optional note kept with the reset event. The actor is never taken from the request:
    a reset over HTTP is always the user's."""

    detail: str = Field("", max_length=200)


class RuleLabelsOut(BaseModel):
    status: dict[str, str]
    block: dict[str, str]
    # Shown next to every probability figure.
    prob_caveat: str


class RuleCheckAllOut(BaseModel):
    checks: list[RuleCheckOut]
    # Holdings the engine refused (invalid input); reported, not silently dropped.
    skipped: list[SkippedCheckOut]
    # Loss if every stop-loss were hit at once, as a share of total equity in percent
    # (the sum of each check's `risk_pct_equity`); None when no check had an equity.
    total_risk_pct_equity: float | None
    kill_switch: KillSwitchOut
    live_trading: bool
    labels: RuleLabelsOut
    # Self-defeating rule combinations from the current settings.
    settings_notes: list[str]
    checked_at: datetime
