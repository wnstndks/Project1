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
    # Share of equity each asset class may hold (STRATEGIES.md S1, registered before any
    # backtest). Together at most 1: the rest stays in cash, never borrowed. Changing them
    # changes the strategy, so STRATEGY_CONFIGS_TRIED goes up.
    strategy_budget_stock: Decimal = Field(Decimal("0.80"), ge=0, le=1)
    strategy_budget_crypto: Decimal = Field(Decimal("0.20"), ge=0, le=1)
    # Virtual starting capital of the paper account; unrelated to real holdings.
    paper_initial_capital_krw: Decimal = Field(Decimal("10000000"), gt=0)

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
