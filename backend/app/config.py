from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings, overridable via environment variables prefixed with AM_."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_prefix="AM_", extra="ignore"
    )

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'asset_manager.db').as_posix()}"
    artifacts_dir: Path = BACKEND_DIR / "artifacts"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:5174"]
    # Host header allow-list: blocks DNS-rebinding pages from reading the local API.
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "[::1]"]
    # "fake" serves deterministic synthetic prices without network access.
    market_provider: Literal["yfinance", "fake"] = "yfinance"
    # Screenshot import. Without a key the SDK falls back to ANTHROPIC_API_KEY or an
    # `ant auth login` profile.
    anthropic_api_key: SecretStr | None = None
    import_model: str = "claude-opus-5-5"
    # Who reads screenshots: "ollama" (free local vision model, default), "claude" (paid API),
    # or "fake" (a fixed sample statement for demos and UI work).
    import_extractor: Literal["ollama", "claude", "fake"] = "ollama"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5vl:7b"
    finnhub_api_key: SecretStr | None = None
    # Well-known investor holdings (services/gurus.py). SEC EDGAR rejects requests without a
    # declared User-Agent of the form "app-name contact@domain"; leave empty to skip 13F
    # investors (ARK needs nothing). The OpenFIGI key is optional and only raises rate limits.
    sec_user_agent: str = ""
    openfigi_api_key: str = ""
    # Comma-separated tickers my cash flows are replayed into (services/benchmarks.py).
    benchmarks: str = "ARKK,BRK-B,SPY,QQQ,BTC-USD"

    # Real orders. Only the user turns this on; until then strategies leave paper records only.
    live_trading: bool = False
    # Risk limits (DECISIONS.md D-002). The drawdown limit can only be tightened: strategies
    # whose drawdown exceeds 20% are never adopted, and no setting may loosen that rule.
    risk_max_drawdown: Decimal = Field(Decimal("0.20"), gt=0, le=Decimal("0.20"))
    # Loss versus the previous day's equity that trips the kill switch.
    risk_daily_loss_limit: Decimal = Field(Decimal("0.03"), gt=0, lt=1)
    # One buy order as a share of equity, and optionally an absolute cap in KRW (the
    # smaller one applies).
    risk_max_order_fraction: Decimal = Field(Decimal("0.05"), gt=0, le=1)
    risk_max_order_krw: Decimal | None = Field(None, gt=0)
    risk_max_position_weight: Decimal = Field(Decimal("0.20"), gt=0, le=1)
    # Broad index funds (risk.INDEX_FUNDS, SPY) instead of the symbol cap above: a 500-stock
    # fund has no single-issuer risk (D-025). Can only be tightened (0 < x <= 0.80).
    risk_max_index_fund_weight: Decimal = Field(Decimal("0.80"), gt=0, le=Decimal("0.80"))
    # Share of equity each asset class may hold (STRATEGIES.md S1, registered before any
    # backtest). Together at most 1: the rest stays in cash, never borrowed. Changing them
    # changes the strategy, so STRATEGY_CONFIGS_TRIED goes up.
    strategy_budget_stock: Decimal = Field(Decimal("0.80"), ge=0, le=1)
    strategy_budget_crypto: Decimal = Field(Decimal("0.20"), ge=0, le=1)
    # Virtual starting capital of the paper account; unrelated to real holdings.
    paper_initial_capital_krw: Decimal = Field(Decimal("10000000"), gt=0)

    # --- Buy-more / stop-loss rule checks (app/strategy/rules.py, DECISIONS.md D-027) ---
    # The user's own rules, not signals. Percentages are of the average cost (trailing stop:
    # of the recent high); day counts are final bars (calendar days for coins, trading days
    # for stocks). Per-symbol targets are stored by the app, not here.
    rules_cut_loss_pct: Decimal = Field(Decimal("15"), gt=0, lt=100)
    rules_trailing_lookback_days: int = Field(60, ge=1)
    rules_trailing_drop_pct: Decimal = Field(Decimal("20"), gt=0, lt=100)
    rules_below_ma_days: int = Field(5, ge=1)
    rules_ma_long: int = Field(60, ge=2)
    rules_ma_short: int = Field(20, ge=2)
    # Two steps of 5% keep every add price above the 15% stop-loss (D-027 follow-up).
    rules_add_step_pct: Decimal = Field(Decimal("5"), gt=0, lt=100)
    rules_add_max_steps: int = Field(2, ge=0)
    rules_add_requires_above_ma_short: bool = True
    rules_target_weight_gap_pt: Decimal = Field(Decimal("5"), ge=0, lt=100)
    # Asset-class layer for coins, which move several times as much as stocks. Empty in
    # .env means "use the global value".
    rules_crypto_cut_loss_pct: Decimal | None = Field(Decimal("25"), gt=0, lt=100)
    rules_crypto_trailing_drop_pct: Decimal | None = Field(Decimal("30"), gt=0, lt=100)
    rules_crypto_add_step_pct: Decimal | None = Field(Decimal("8"), gt=0, lt=100)
    # Loss at the stop-loss price as a share of total assets above which the check warns.
    rules_max_risk_pct: Decimal = Field(Decimal("2.0"), gt=0, lt=100)

    @field_validator(
        "rules_crypto_cut_loss_pct",
        "rules_crypto_trailing_drop_pct",
        "rules_crypto_add_step_pct",
        mode="before",
    )
    @classmethod
    def _rules_blank_is_global(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v

    # --- end of rule check settings ---

    @field_validator("anthropic_api_key", "finnhub_api_key", "risk_max_order_krw", mode="before")
    @classmethod
    def _blank_is_unset(cls, v: object) -> object:
        # `AM_FINNHUB_API_KEY=` left empty in .env means "not configured".
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("live_trading", mode="before")
    @classmethod
    def _strict_bool(cls, v: object) -> object:
        # pydantic would read "1", "yes", "on" or "t" as true; only the literal word counts,
        # so a typo fails at startup instead of switching real orders on.
        if isinstance(v, bool):
            return v
        if isinstance(v, str) and v.strip().lower() in ("true", "false"):
            return v.strip().lower() == "true"
        raise ValueError('AM_LIVE_TRADING must be "true" or "false"')

    @model_validator(mode="after")
    def _budgets_without_leverage(self) -> "Settings":
        if self.strategy_budget_stock + self.strategy_budget_crypto > 1:
            raise ValueError("AM_STRATEGY_BUDGET_STOCK + AM_STRATEGY_BUDGET_CRYPTO must be <= 1")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
