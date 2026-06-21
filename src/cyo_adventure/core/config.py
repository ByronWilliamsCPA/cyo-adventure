"""Configuration settings for CYO Adventure.

Settings are loaded from environment variables with the prefix 'CYO_ADVENTURE_'.
Pydantic-settings handles the parsing and validation.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuration settings for the application, loaded from environment variables.

    Attributes:
        model_config: Pydantic settings configuration (env prefix and parsing).
        log_level: The logging level for the application.
        json_logs: Flag to enable or disable JSON formatted logs.
        include_timestamp: Flag to include timestamps in logs.
        database_url: Async SQLAlchemy connection URL for PostgreSQL.
    """

    model_config = SettingsConfigDict(
        env_prefix="cyo_adventure_",
        case_sensitive=False,
        extra="ignore",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    json_logs: bool = False
    include_timestamp: bool = True
    # #CRITICAL: security: this default embeds plaintext credentials
    # (postgres:postgres) and resolves as the live DSN whenever
    # CYO_ADVENTURE_DATABASE_URL is unset, including in CI. It is a localhost-only
    # development default and must never reach staging or production.
    # #VERIFY: require CYO_ADVENTURE_DATABASE_URL in non-local environments and
    # fail fast at startup if this default value is detected outside dev.
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/cyo_adventure"
    )


# A single, global instance of the settings
settings = Settings()
