"""Configuration settings for CYO Adventure.

Settings are loaded from environment variables with the prefix 'CYO_ADVENTURE_'.
Pydantic-settings handles the parsing and validation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from cyo_adventure.core.exceptions import ConfigurationError

# Localhost-only development default. Kept as a module constant so the fail-fast
# validator below can detect when it leaks into a non-local environment.
_DEV_DATABASE_URL = (
    "postgresql+asyncpg://postgres:postgres@localhost:5432/cyo_adventure"
)


class Settings(BaseSettings):
    """
    Configuration settings for the application, loaded from environment variables.

    Attributes:
        model_config: Pydantic settings configuration (env prefix and parsing).
        environment: Deployment stage; gates the database_url fail-fast check.
        log_level: The logging level for the application.
        json_logs: Flag to enable or disable JSON formatted logs.
        include_timestamp: Flag to include timestamps in logs.
        database_url: Async SQLAlchemy connection URL for PostgreSQL.
        redis_url: Redis connection URL for the RQ task queue.
        generation_provider: Which LLM provider to use for story generation.
    """

    model_config = SettingsConfigDict(
        env_prefix="cyo_adventure_",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Literal["local", "dev", "staging", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    json_logs: bool = False
    include_timestamp: bool = True
    # #CRITICAL: security: this default embeds plaintext credentials
    # (postgres:postgres) and resolves as the live DSN whenever
    # CYO_ADVENTURE_DATABASE_URL is unset, including in CI. It is a localhost-only
    # development default and must never reach staging or production.
    # #VERIFY: enforced by _reject_dev_database_url_outside_local below.
    database_url: str = _DEV_DATABASE_URL
    # Development default for local Redis; safe to leave unset in non-production
    # environments where no queue is configured. Production must override via
    # CYO_ADVENTURE_REDIS_URL.
    redis_url: str = "redis://localhost:6379/0"
    # Phase 2 stand-in: only "mock" is operational; real providers are deferred
    # to Phase 2b. Setting any other value raises ConfigurationError at
    # build_provider() call time, not at startup, so the app can start without
    # a live LLM backend.
    generation_provider: Literal["mock", "claude", "ollama", "openrouter"] = "mock"

    @model_validator(mode="after")
    def _reject_dev_database_url_outside_local(self) -> Settings:
        """Fail fast if the dev default DSN leaks into a non-local environment.

        Raises:
            ConfigurationError: when ``environment`` is not ``local`` but
                ``database_url`` is still the plaintext-credential dev default,
                which means ``CYO_ADVENTURE_DATABASE_URL`` was not provided.
        """
        if self.environment != "local" and self.database_url == _DEV_DATABASE_URL:
            msg = (
                "CYO_ADVENTURE_DATABASE_URL must be set in non-local environments; "
                f"refusing to start in '{self.environment}' with the development "
                "default database URL (plaintext localhost credentials)."
            )
            raise ConfigurationError(msg)
        return self


# A single, global instance of the settings
settings = Settings()
