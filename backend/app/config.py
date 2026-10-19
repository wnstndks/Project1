from functools import lru_cache
from pathlib import Path

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
