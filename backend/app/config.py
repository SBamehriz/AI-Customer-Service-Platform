"""Application settings."""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# This file sits in backend/app, so the parent of its parent is backend.
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"


DEFAULT_PUBLIC_URL = "http://localhost:8000"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Unified Customer Service Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    DATABASE_URL: str = f"sqlite+aiosqlite:///{DATA_DIR / 'ucsp.db'}"

    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    SECRET_KEY_IS_EPHEMERAL: bool = False
    ACCESS_TOKEN_TTL_MINUTES: int = 60 * 12

    RATE_LIMIT_SIGN_IN_PER_ADDRESS: int = 60
    RATE_LIMIT_SIGN_IN_PER_ACCOUNT: int = 10
    RATE_LIMIT_SIGN_IN_WINDOW_SECONDS: int = 300
    RATE_LIMIT_REGISTRATIONS: int = 10
    RATE_LIMIT_REGISTRATIONS_WINDOW_SECONDS: int = 3600

    LLM_PROVIDER: str = "none"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""
    LLM_BASE_URL: str = ""
    LLM_TIMEOUT_SECONDS: float = 30.0
    EMBEDDING_MODEL: str = ""

    PUBLIC_URL: str = DEFAULT_PUBLIC_URL

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    WIDGET_ALLOW_ANY_ORIGIN: bool = True

    SEED_DEMO_DATA: bool = False

    BACKUP_INTERVAL_HOURS: int = 24

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept both a JSON array and a plain comma separated string."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped.startswith("["):
                return [o.strip() for o in stripped.split(",") if o.strip()]
        return value

    @field_validator("LLM_PROVIDER", mode="before")
    @classmethod
    def _normalise_provider(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower() or "none"
        return value

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def llm_enabled(self) -> bool:
        return self.LLM_PROVIDER != "none" and bool(self.LLM_API_KEY or self.LLM_BASE_URL)


@lru_cache
def get_settings() -> Settings:
    import os

    configured = bool(os.environ.get("SECRET_KEY"))
    instance = Settings()
    if not configured:
        object.__setattr__(instance, "SECRET_KEY_IS_EPHEMERAL", True)
    return instance


settings = get_settings()
