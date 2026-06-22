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
    # Provider selection. "mock" remains the default so CI and local runs never
    # make live LLM calls; production/staging set this to "openrouter" (the
    # primary per ADR-003 as amended 2026-06-22). Live adapters are constructed
    # lazily in build_provider(), so an unset live key fails at call time, not
    # startup.
    generation_provider: Literal["mock", "claude", "ollama", "openrouter"] = "mock"

    # Model ids are pinned in config, not code (ADR-003): a model swap is a
    # config change. OpenRouter rosters churn weekly, so pin first-party families
    # (Anthropic, Google) that survive churn, and rely on the fallback below when
    # a pinned id 404s.
    # #ASSUME: external-resources: these ids must be currently reachable on the
    # selected provider; build_provider/adapters map an unavailable model to
    # ProviderError so the orchestrator can fall back.
    # #VERIFY: Phase 2b adapter raises ProviderError on HTTP 400/404 invalid-model.
    openrouter_model: str = "anthropic/claude-sonnet-4.6"
    openrouter_fallback_model: str = "google/gemma-4-31b-it:free"
    ollama_model: str = "qwen3"
    # No direct Anthropic SDK setting: Claude is reached via OpenRouter
    # (openrouter_model = anthropic/claude-sonnet-4.6). A direct-Anthropic adapter
    # is deferred; the GenerationProvider seam makes it a trivial future add if a
    # billed Anthropic API account is ever used directly (for Opus 4.8 / prompt
    # caching without the OpenRouter markup).
    #
    # Reasoning effort for live generation, forwarded to OpenRouter's `reasoning`
    # param (ignored by models that lack it). Generation is structured-JSON, not
    # deep reasoning, so default low to avoid billing thinking tokens at the
    # output rate; raise only if yield measurement shows it helps.
    llm_effort: Literal["low", "medium", "high"] = "low"

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
