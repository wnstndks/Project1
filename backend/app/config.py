from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings, overridable via environment variables prefixed with AM_."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_prefix="AM_", extra="ignore"
    )

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'asset_manager.db').as_posix()}"
    artifacts_dir: Path = BACKEND_DIR / "artifacts"
    cors_origins: list[str] = ["http://localhost:5173"]
    # "fake" serves deterministic synthetic prices without network access.
    market_provider: Literal["yfinance", "fake"] = "yfinance"
    # Screenshot import. Without a key the SDK falls back to ANTHROPIC_API_KEY or an
    # `ant auth login` profile.
    anthropic_api_key: SecretStr | None = None
    import_model: str = "claude-opus-5-5"
    # "fake" returns a fixed sample statement: for demos and UI work without an API key.
    import_extractor: Literal["claude", "fake"] = "claude"
    finnhub_api_key: SecretStr | None = None

    @field_validator("anthropic_api_key", "finnhub_api_key", mode="before")
    @classmethod
    def _blank_is_unset(cls, v: object) -> object:
        # `AM_FINNHUB_API_KEY=` left empty in .env means "not configured".
        return None if isinstance(v, str) and not v.strip() else v


@lru_cache
def get_settings() -> Settings:
    return Settings()
