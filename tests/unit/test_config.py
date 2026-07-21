"""Tests for cyo_adventure.core.config module.

Covers:
- Settings with default values (environment='local')
- The _reject_dev_database_url_outside_local model_validator: raises
  ConfigurationError when environment is non-local and database_url is the
  dev default.
- Happy path for non-local environments when a real database_url is supplied.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from cyo_adventure.core.config import Settings

# The dev-default DSN that the validator guards against leaking.
_DEV_DB_URL = "postgresql+asyncpg://localhost/cyo_adventure"
_PROD_DB_URL = "postgresql+asyncpg://appuser:testpass@db.example.com/cyo_adventure"
# RFC 2606 reserved example.com domain (not a real Supabase hostname), so a
# secrets scanner does not mistake this test fixture for a live credential.
_POOLER_DB_URL = (
    "postgresql+asyncpg://appuser:testpass@pooler.example.com:6543/postgres"
)
# A >=32-byte child-session signing secret, required alongside OIDC config in
# every non-local environment (see the _require_child_session_secret validator).
_CHILD_SECRET = "test-child-session-secret-0123456789abcd"
# A >=32-byte device-grant signing secret, required alongside OIDC config in
# every non-local environment (see the _require_device_grant_secret_outside_local
# validator, ADR-014). Must be distinct from _CHILD_SECRET.
_DEVICE_SECRET = "test-device-grant-secret-0123456789abcdef"


class TestSettingsDefaults:
    """Tests for Settings default values."""

    @pytest.mark.unit
    def test_settings_environment_default_is_local(self) -> None:
        """Settings defaults to environment='local'."""
        from cyo_adventure.core.config import Settings

        s = Settings()

        assert s.environment == "local"

    @pytest.mark.unit
    def test_settings_database_url_default_is_dev_url(self) -> None:
        """Settings default database_url matches the dev localhost DSN."""
        from cyo_adventure.core.config import Settings

        s = Settings()

        assert s.database_url == _DEV_DB_URL

    @pytest.mark.unit
    def test_settings_local_with_dev_url_does_not_raise(self) -> None:
        """Settings(environment='local') with the dev db url is valid."""
        from cyo_adventure.core.config import Settings

        # Must not raise ConfigurationError even with the unset default URL
        s = Settings(environment="local")

        assert s.environment == "local"
        assert s.database_url == _DEV_DB_URL


class TestOllamaProviderSettings:
    """Ollama endpoint/credential settings: defaults and unprefixed env aliases."""

    @pytest.mark.unit
    def test_ollama_model_default_is_fast_valid_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The default ollama_model is qwen2.5:14b (fast and structurally valid live)."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("CYO_ADVENTURE_OLLAMA_MODEL", raising=False)
        assert Settings().ollama_model == "qwen2.5:14b"

    @pytest.mark.unit
    def test_ollama_timeout_seconds_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The Ollama leg gets its own longer default timeout (cold start + queue)."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("CYO_ADVENTURE_OLLAMA_TIMEOUT_SECONDS", raising=False)
        assert Settings().ollama_timeout_seconds == 300

    @pytest.mark.unit
    def test_ollama_auth_default_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With no OLLAMA_AUTH set, ollama_auth is None (no credential sent)."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("OLLAMA_AUTH", raising=False)
        assert Settings().ollama_auth is None

    @pytest.mark.unit
    def test_ollama_ca_bundle_default_is_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no OLLAMA_CA_BUNDLE set, ollama_ca_bundle is None (system CAs)."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("OLLAMA_CA_BUNDLE", raising=False)
        assert Settings().ollama_ca_bundle is None

    @pytest.mark.unit
    def test_ollama_ca_bundle_reads_unprefixed_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ollama_ca_bundle is read from the unprefixed OLLAMA_CA_BUNDLE var."""
        from cyo_adventure.core.config import Settings

        monkeypatch.setenv("OLLAMA_CA_BUNDLE", "certs/homelab-ca.pem")
        assert Settings().ollama_ca_bundle == "certs/homelab-ca.pem"

    @pytest.mark.unit
    def test_ollama_base_url_default_is_localhost(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no override, ollama_base_url is the local-dev default."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
        monkeypatch.delenv("CYO_ADVENTURE_OLLAMA_BASE_URL", raising=False)
        assert Settings().ollama_base_url == "http://localhost:11434"

    @pytest.mark.unit
    def test_ollama_base_url_reads_unprefixed_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ollama_base_url is read from the unprefixed OLLAMA_BASE_URL var."""
        from cyo_adventure.core.config import Settings

        monkeypatch.setenv("OLLAMA_BASE_URL", "https://ollama.williamshome.family")
        assert Settings().ollama_base_url == "https://ollama.williamshome.family"

    @pytest.mark.unit
    def test_ollama_auth_reads_unprefixed_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ollama_auth is read from the unprefixed OLLAMA_AUTH var."""
        from cyo_adventure.core.config import Settings

        monkeypatch.setenv("OLLAMA_AUTH", "testservice:testcred")
        assert Settings().ollama_auth == "testservice:testcred"


class TestValidatorRejectDevUrlOutsideLocal:
    """Tests for the _reject_dev_database_url_outside_local model_validator."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "environment",
        ["dev", "staging", "production"],
    )
    def test_non_local_environment_with_dev_url_raises_configuration_error(
        self, environment: str
    ) -> None:
        """Settings raises ConfigurationError when env is non-local with dev db url."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError):
            Settings(environment=environment, database_url=_DEV_DB_URL)

    @pytest.mark.unit
    def test_error_message_mentions_environment(self) -> None:
        """ConfigurationError message includes the problematic environment name."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError) as exc_info:
            Settings(environment="production", database_url=_DEV_DB_URL)

        assert "production" in str(exc_info.value)

    @pytest.mark.unit
    def test_error_message_mentions_database_url_env_var(self) -> None:
        """ConfigurationError message guides the user to set CYO_ADVENTURE_DATABASE_URL."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError) as exc_info:
            Settings(environment="staging", database_url=_DEV_DB_URL)

        assert "CYO_ADVENTURE_DATABASE_URL" in str(exc_info.value)

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "environment",
        ["dev", "staging", "production"],
    )
    def test_non_local_environment_with_real_url_is_valid(
        self, environment: str
    ) -> None:
        """Settings does not raise when a non-default database_url is provided."""
        from cyo_adventure.core.config import Settings

        settings = Settings(
            environment=environment,
            database_url=_PROD_DB_URL,
            oidc_issuer="https://project.supabase.co/auth/v1",
            oidc_jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
            child_session_secret=_CHILD_SECRET,
            device_grant_secret=_DEVICE_SECRET,
        )
        assert settings.database_url == _PROD_DB_URL
        assert settings.environment == environment


class TestValidatorRequirePreparedCacheForPoolerDsn:
    """Tests for the _require_prepared_cache_disabled_for_pooler_dsn model_validator."""

    @pytest.mark.unit
    def test_pooler_dsn_with_flag_false_raises_configuration_error(self) -> None:
        """Port 6543 with the cache-disabling flag off must fail fast."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError):
            Settings(database_url=_POOLER_DB_URL, database_disable_prepared_cache=False)

    @pytest.mark.unit
    def test_pooler_dsn_with_flag_true_is_valid(self) -> None:
        """Port 6543 with the cache-disabling flag on must not raise."""
        from cyo_adventure.core.config import Settings

        # Must not raise
        settings = Settings(
            database_url=_POOLER_DB_URL, database_disable_prepared_cache=True
        )
        assert settings.database_disable_prepared_cache is True

    @pytest.mark.unit
    def test_non_pooler_dsn_with_flag_false_is_valid(self) -> None:
        """A direct connection (no port 6543) with the flag off must not raise."""
        from cyo_adventure.core.config import Settings

        # Must not raise
        settings = Settings(
            database_url=_PROD_DB_URL, database_disable_prepared_cache=False
        )
        assert settings.database_disable_prepared_cache is False

    @pytest.mark.unit
    def test_error_message_mentions_port_and_env_var_names(self) -> None:
        """ConfigurationError message names the port and both relevant env vars."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError) as exc_info:
            Settings(database_url=_POOLER_DB_URL, database_disable_prepared_cache=False)

        message = str(exc_info.value)
        assert "6543" in message
        assert "CYO_ADVENTURE_DATABASE_URL" in message
        assert "CYO_ADVENTURE_DATABASE_DISABLE_PREPARED_CACHE" in message


class TestEnvironmentAlias:
    """Tests for the unprefixed ENVIRONMENT alias on Settings.environment."""

    @pytest.mark.unit
    def test_environment_reads_from_unprefixed_env_var(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ENVIRONMENT (no cyo_adventure_ prefix) populates settings.environment."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("CYO_ADVENTURE_ENVIRONMENT", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "staging")
        s = Settings(
            database_url=_PROD_DB_URL,
            oidc_issuer="https://project.supabase.co/auth/v1",
            oidc_jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
            child_session_secret=_CHILD_SECRET,
            device_grant_secret=_DEVICE_SECRET,
        )
        assert s.environment == "staging"

    @pytest.mark.unit
    def test_environment_env_var_overrides_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Setting ENVIRONMENT=production causes settings.environment == 'production'."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("CYO_ADVENTURE_ENVIRONMENT", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")
        s = Settings(
            database_url=_PROD_DB_URL,
            oidc_issuer="https://project.supabase.co/auth/v1",
            oidc_jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
            child_session_secret=_CHILD_SECRET,
            device_grant_secret=_DEVICE_SECRET,
        )
        assert s.environment == "production"

    @pytest.mark.unit
    def test_environment_defaults_to_local_when_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no ENVIRONMENT var set, environment defaults to 'local'."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("CYO_ADVENTURE_ENVIRONMENT", raising=False)
        s = Settings()
        assert s.environment == "local"


class TestModerationReviewSettings:
    """Tests for slice-2 moderation settings and the classifier validator."""

    @pytest.mark.unit
    def test_review_defaults_to_mock_and_requires_no_classifier(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """review_provider defaults to mock; no classifier key required."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("PERSPECTIVE_API_KEY", raising=False)
        settings = Settings()
        assert settings.review_provider == "mock"
        assert settings.openai_api_key is None
        assert settings.perspective_api_key is None

    @pytest.mark.unit
    def test_non_mock_review_without_any_classifier_key_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-mock review without any classifier key raises ConfigurationError."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("PERSPECTIVE_API_KEY", raising=False)
        with pytest.raises(ConfigurationError):
            Settings(review_provider="openrouter")

    @pytest.mark.unit
    def test_non_mock_review_with_one_classifier_key_is_allowed(self) -> None:
        """Non-mock review with at least one classifier key is allowed."""
        from cyo_adventure.core.config import Settings

        settings = Settings(review_provider="openrouter", openai_api_key="k")
        assert settings.review_provider == "openrouter"


class TestModalGenerationSettings:
    """Tests for the experimental Modal generation-leg settings (ADR-010)."""

    @pytest.mark.unit
    def test_generation_provider_accepts_modal(self) -> None:
        """generation_provider accepts the new 'modal' literal value."""
        from cyo_adventure.core.config import Settings

        settings = Settings(generation_provider="modal")
        assert settings.generation_provider == "modal"

    @pytest.mark.unit
    def test_modal_settings_default_to_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """modal_base_url, modal_model, modal_proxy_key, and modal_proxy_secret
        default to None.
        """
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("MODAL_BASE_URL", raising=False)
        monkeypatch.delenv("MODAL_MODEL", raising=False)
        monkeypatch.delenv("MODAL_PROXY_KEY", raising=False)
        monkeypatch.delenv("MODAL_PROXY_SECRET", raising=False)
        settings = Settings()
        assert settings.modal_base_url is None
        assert settings.modal_model is None
        assert settings.modal_proxy_key is None
        assert settings.modal_proxy_secret is None

    @pytest.mark.unit
    def test_modal_timeout_seconds_default_exceeds_llm_timeout(self) -> None:
        """modal_timeout_seconds defaults higher than llm_timeout_seconds (cold starts)."""
        from cyo_adventure.core.config import Settings

        settings = Settings()
        assert settings.modal_timeout_seconds > settings.llm_timeout_seconds

    @pytest.mark.unit
    def test_modal_base_url_reads_unprefixed_env_var(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """MODAL_BASE_URL (unprefixed) populates modal_base_url."""
        from cyo_adventure.core.config import Settings

        monkeypatch.setenv("MODAL_BASE_URL", "https://example--cyo.modal.run/v1")
        settings = Settings()
        assert settings.modal_base_url == "https://example--cyo.modal.run/v1"


class TestUnprefixedOperatorAliases:
    """log_level, json_logs, database_url, and redis_url read the unprefixed
    names that docker-compose and docs/guides/configuration.md actually set,
    while each also keeps its prefixed CYO_ADVENTURE_ contract working."""

    @pytest.mark.unit
    def test_log_level_reads_unprefixed_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """log_level is read from the unprefixed LOG_LEVEL var (compose/docs)."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("CYO_ADVENTURE_LOG_LEVEL", raising=False)
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        assert Settings().log_level == "DEBUG"

    @pytest.mark.unit
    def test_json_logs_reads_unprefixed_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """json_logs is read from the unprefixed JSON_LOGS var (compose/docs)."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("CYO_ADVENTURE_JSON_LOGS", raising=False)
        monkeypatch.setenv("JSON_LOGS", "true")
        assert Settings().json_logs is True

    @pytest.mark.unit
    def test_database_url_reads_unprefixed_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """database_url is read from the unprefixed DATABASE_URL var (compose)."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("CYO_ADVENTURE_DATABASE_URL", raising=False)
        monkeypatch.setenv("DATABASE_URL", _PROD_DB_URL)
        # environment stays "local", so the dev-url validator does not fire.
        assert Settings().database_url == _PROD_DB_URL

    @pytest.mark.unit
    def test_database_url_still_reads_prefixed_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The tested CYO_ADVENTURE_DATABASE_URL contract keeps working."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("CYO_ADVENTURE_DATABASE_URL", _PROD_DB_URL)
        assert Settings().database_url == _PROD_DB_URL

    @pytest.mark.unit
    def test_database_url_prefixed_wins_when_both_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When both names are set, the explicit CYO_ADVENTURE_ prefix wins."""
        from cyo_adventure.core.config import Settings

        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unprefixed/db")
        monkeypatch.setenv("CYO_ADVENTURE_DATABASE_URL", _PROD_DB_URL)
        assert Settings().database_url == _PROD_DB_URL

    @pytest.mark.unit
    def test_redis_url_reads_unprefixed_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """redis_url is read from the unprefixed REDIS_URL var (compose, ADR-021)."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("CYO_ADVENTURE_REDIS_URL", raising=False)
        monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
        assert Settings().redis_url == "redis://redis:6379/0"

    @pytest.mark.unit
    def test_redis_url_still_reads_prefixed_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The established CYO_ADVENTURE_REDIS_URL contract keeps working."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("CYO_ADVENTURE_REDIS_URL", "redis://prefixed:6379/0")
        assert Settings().redis_url == "redis://prefixed:6379/0"

    @pytest.mark.unit
    def test_redis_url_prefixed_wins_when_both_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When both names are set, the explicit CYO_ADVENTURE_ prefix wins."""
        from cyo_adventure.core.config import Settings

        monkeypatch.setenv("REDIS_URL", "redis://unprefixed:6379/0")
        monkeypatch.setenv("CYO_ADVENTURE_REDIS_URL", "redis://prefixed:6379/0")
        assert Settings().redis_url == "redis://prefixed:6379/0"

    @pytest.mark.unit
    def test_log_level_still_reads_prefixed_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """log_level keeps reading the prefixed CYO_ADVENTURE_LOG_LEVEL name."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.setenv("CYO_ADVENTURE_LOG_LEVEL", "WARNING")
        assert Settings().log_level == "WARNING"

    @pytest.mark.unit
    def test_log_level_prefixed_wins_when_both_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When both names are set, the explicit CYO_ADVENTURE_ prefix wins."""
        from cyo_adventure.core.config import Settings

        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("CYO_ADVENTURE_LOG_LEVEL", "ERROR")
        assert Settings().log_level == "ERROR"

    @pytest.mark.unit
    def test_json_logs_still_reads_prefixed_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """json_logs keeps reading the prefixed CYO_ADVENTURE_JSON_LOGS name."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("JSON_LOGS", raising=False)
        monkeypatch.setenv("CYO_ADVENTURE_JSON_LOGS", "true")
        assert Settings().json_logs is True

    @pytest.mark.unit
    def test_json_logs_prefixed_wins_when_both_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When both names are set, the explicit CYO_ADVENTURE_ prefix wins."""
        from cyo_adventure.core.config import Settings

        monkeypatch.setenv("JSON_LOGS", "false")
        monkeypatch.setenv("CYO_ADVENTURE_JSON_LOGS", "true")
        assert Settings().json_logs is True


class TestValidatorRequireOidcConfigOutsideLocal:
    """Tests for the _require_oidc_config_outside_local model_validator."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "environment",
        ["dev", "staging", "production"],
    )
    def test_non_local_environment_without_oidc_config_raises(
        self, environment: str
    ) -> None:
        """Settings raises ConfigurationError when non-local with no OIDC config."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError):
            Settings(environment=environment, database_url=_PROD_DB_URL)

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("oidc_issuer", "oidc_jwks_url"),
        [
            (None, "https://project.supabase.co/auth/v1/.well-known/jwks.json"),
            ("https://project.supabase.co/auth/v1", None),
        ],
    )
    def test_non_local_environment_with_partial_oidc_config_raises(
        self, oidc_issuer: str | None, oidc_jwks_url: str | None
    ) -> None:
        """Settings raises when only one of oidc_issuer/oidc_jwks_url is set."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError):
            Settings(
                environment="production",
                database_url=_PROD_DB_URL,
                oidc_issuer=oidc_issuer,
                oidc_jwks_url=oidc_jwks_url,
            )

    @pytest.mark.unit
    def test_error_message_mentions_environment_and_oidc_vars(self) -> None:
        """ConfigurationError message names the environment and required env vars."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError) as exc_info:
            Settings(environment="production", database_url=_PROD_DB_URL)

        message = str(exc_info.value)
        assert "production" in message
        assert "OIDC_ISSUER" in message
        assert "OIDC_JWKS_URL" in message

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "environment",
        ["dev", "staging", "production"],
    )
    def test_non_local_environment_with_full_oidc_config_is_valid(
        self, environment: str
    ) -> None:
        """Settings does not raise when both oidc_issuer and oidc_jwks_url are set."""
        from cyo_adventure.core.config import Settings

        settings = Settings(
            environment=environment,
            database_url=_PROD_DB_URL,
            oidc_issuer="https://project.supabase.co/auth/v1",
            oidc_jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
            child_session_secret=_CHILD_SECRET,
            device_grant_secret=_DEVICE_SECRET,
        )
        assert settings.oidc_issuer == "https://project.supabase.co/auth/v1"
        assert (
            settings.oidc_jwks_url
            == "https://project.supabase.co/auth/v1/.well-known/jwks.json"
        )

    @pytest.mark.unit
    def test_local_environment_without_oidc_config_is_valid(self) -> None:
        """Local environment does not require OIDC config (dev auth stub)."""
        from cyo_adventure.core.config import Settings

        # Must not raise
        settings = Settings(environment="local")
        assert settings.oidc_issuer is None
        assert settings.oidc_jwks_url is None


class TestExplicitEnvironmentWhenDeployed:
    """Tests for the _require_explicit_environment_when_deployed validator.

    A deployment that sets OIDC config but forgets ENVIRONMENT would default to
    "local", silently trusting the dev auth stub and disabling the in-memory
    rate limiter. The validator converts that fail-open into a startup error,
    keyed on OIDC config as the deployment marker (never set by local dev, CI,
    or the integration/e2e suites).
    """

    _OIDC_ISSUER = "https://project.supabase.co/auth/v1"
    _OIDC_JWKS_URL = "https://project.supabase.co/auth/v1/.well-known/jwks.json"

    @pytest.mark.unit
    def test_unset_environment_with_oidc_config_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OIDC configured but ENVIRONMENT never set raises ConfigurationError."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        # The field must be genuinely unset: an inherited shell ENVIRONMENT would
        # land in model_fields_set and mask the fail-open this guard exists for.
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("CYO_ADVENTURE_ENVIRONMENT", raising=False)

        with pytest.raises(ConfigurationError) as exc_info:
            Settings(
                oidc_issuer=self._OIDC_ISSUER,
                oidc_jwks_url=self._OIDC_JWKS_URL,
            )
        assert "ENVIRONMENT" in str(exc_info.value)

    @pytest.mark.unit
    def test_explicit_local_with_oidc_config_is_valid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicitly setting ENVIRONMENT=local is honoured even with OIDC set."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("CYO_ADVENTURE_ENVIRONMENT", raising=False)

        # Must not raise: explicit local is a deliberate choice, not a silent
        # default, so environment lands in model_fields_set and the guard passes.
        settings = Settings(
            environment="local",
            oidc_issuer=self._OIDC_ISSUER,
            oidc_jwks_url=self._OIDC_JWKS_URL,
        )
        assert settings.environment == "local"

    @pytest.mark.unit
    def test_unset_environment_without_oidc_config_is_valid(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Plain local dev (no ENVIRONMENT, no OIDC markers) is unaffected."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("CYO_ADVENTURE_ENVIRONMENT", raising=False)
        monkeypatch.delenv("OIDC_ISSUER", raising=False)
        monkeypatch.delenv("OIDC_JWKS_URL", raising=False)

        settings = Settings()
        assert settings.environment == "local"
        assert settings.oidc_issuer is None


def _non_local_settings(**overrides: object) -> Settings:
    """Build a non-local Settings with valid OIDC + db, overriding as needed.

    Centralizes the OIDC-config-plus-prod-db boilerplate every child-session
    validator test needs so each case varies only child_session_secret. The
    OIDC validator runs before the child-session validator, so without valid
    OIDC config every case would raise for the wrong reason.
    """
    from cyo_adventure.core.config import Settings

    kwargs: dict[str, object] = {
        "environment": "production",
        "database_url": _PROD_DB_URL,
        "oidc_issuer": "https://project.supabase.co/auth/v1",
        "oidc_jwks_url": ("https://project.supabase.co/auth/v1/.well-known/jwks.json"),
        "child_session_secret": _CHILD_SECRET,
        "device_grant_secret": _DEVICE_SECRET,
    }
    kwargs.update(overrides)
    return Settings(**kwargs)  # type: ignore[arg-type]


class TestValidatorRequireChildSessionSecretOutsideLocal:
    """Tests for the _require_child_session_secret_outside_local validator.

    Presence alone is insufficient: an empty secret 500s every mint, and a
    short or placeholder secret signs forgeable child tokens. The validator is
    the only runtime guard (PyJWT's InsecureKeyLengthWarning does not error
    outside pytest), so these cases pin the forgery boundary.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize("environment", ["dev", "staging", "production"])
    def test_non_local_without_child_secret_raises(self, environment: str) -> None:
        """Missing child_session_secret outside local raises ConfigurationError."""
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError):
            _non_local_settings(environment=environment, child_session_secret=None)

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "secret",
        [
            "",  # empty: SecretStr("") slips past a bare is-None check
            "   ",  # whitespace only
            "short-key",  # non-empty but under the 32-byte HS256 floor
            "0123456789abcdef0123456789abcde",  # 31 bytes: one short of the floor
            "REPLACE_ME",  # placeholder shipped in .env.staging.example
            "changeme",  # common placeholder
            "SECRET",  # placeholder (casefolded match)
            # The docker-compose.yml local-dev defaults: long enough to pass
            # the byte floor, so they must be rejected by exact value outside
            # local (repository-known HMAC keys sign forgeable tokens).
            "local-dev-child-session-secret-not-for-production",
            "local-dev-device-grant-secret-not-for-production",
        ],
    )
    def test_non_local_with_weak_child_secret_raises(self, secret: str) -> None:
        """Empty, short, or placeholder secrets are rejected outside local."""
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError):
            _non_local_settings(child_session_secret=secret)

    @pytest.mark.unit
    def test_error_message_never_echoes_the_secret(self) -> None:
        """The failure message must not leak the (weak) secret value."""
        from cyo_adventure.core.exceptions import ConfigurationError

        canary = "sekret-leak-canary"  # 18 bytes: fails the length check
        with pytest.raises(ConfigurationError) as exc_info:
            _non_local_settings(child_session_secret=canary)

        message = str(exc_info.value)
        assert canary not in message
        assert "CHILD_SESSION_SECRET" in message
        assert "production" in message

    @pytest.mark.unit
    @pytest.mark.parametrize("environment", ["dev", "staging", "production"])
    def test_non_local_with_strong_child_secret_is_valid(
        self, environment: str
    ) -> None:
        """A >=32-byte non-placeholder secret is accepted outside local."""
        settings = _non_local_settings(environment=environment)
        assert settings.child_session_secret is not None

    @pytest.mark.unit
    def test_local_environment_without_child_secret_is_valid(self) -> None:
        """Local environment does not require a child-session secret (dev stub)."""
        from cyo_adventure.core.config import Settings

        settings = Settings(environment="local")
        assert settings.child_session_secret is None

    @pytest.mark.unit
    def test_non_local_rejects_compose_dev_device_secret(self) -> None:
        """The compose dev device-grant default is refused outside local.

        The docker-compose.yml default is a repository-known HMAC key; if a
        non-local process ever starts with it, device grants become forgeable,
        so the validator must reject the exact value despite its length.
        """
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError):
            _non_local_settings(
                device_grant_secret="local-dev-device-grant-secret-not-for-production"
            )


class TestValidatorRequireDeviceGrantSecretOutsideLocal:
    """Device-grant secret rejection shares the child-session helper (#254).

    Since ``_require_strong_token_secret`` backs both validators, these pin that
    the device-grant path keeps rejecting empty/short/placeholder secrets and
    never echoes the value, so the shared extraction did not weaken it.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize("environment", ["dev", "staging", "production"])
    def test_non_local_without_device_secret_raises(self, environment: str) -> None:
        """Missing device_grant_secret outside local raises ConfigurationError."""
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError):
            _non_local_settings(environment=environment, device_grant_secret=None)

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "secret",
        [
            "",
            "   ",
            "short-key",
            "0123456789abcdef0123456789abcde",  # 31 bytes: one short of the floor
            "REPLACE_ME",
            "changeme",
            "SECRET",
        ],
    )
    def test_non_local_with_weak_device_secret_raises(self, secret: str) -> None:
        """Empty, short, or placeholder device secrets are rejected outside local."""
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError):
            _non_local_settings(device_grant_secret=secret)

    @pytest.mark.unit
    def test_device_error_message_never_echoes_the_secret(self) -> None:
        """The failure message must not leak the (weak) device secret value."""
        from cyo_adventure.core.exceptions import ConfigurationError

        canary = "device-leak-canary"  # 18 bytes: fails the length check
        with pytest.raises(ConfigurationError) as exc_info:
            _non_local_settings(device_grant_secret=canary)

        message = str(exc_info.value)
        assert canary not in message
        assert "DEVICE_GRANT_SECRET" in message


class TestValidatorRequireDistinctTokenFamilies:
    """Tests for the _require_distinct_token_families validator (issue #251).

    The guardian/child/device branches stay separable only if their audiences
    are pairwise distinct and the two backend HS256 secrets differ; these pin
    that the previously-conventional invariant now fails closed at startup.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "colliding_audience", ["cyo-child-session", "cyo-device-grant"]
    )
    def test_oidc_audience_colliding_with_backend_audience_raises(
        self, colliding_audience: str
    ) -> None:
        """An OIDC_AUDIENCE equal to a backend token audience is rejected."""
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError):
            _non_local_settings(oidc_audience=colliding_audience)

    @pytest.mark.unit
    def test_identical_child_and_device_secret_raises(self) -> None:
        """Reusing one secret for both backend token families is rejected."""
        from cyo_adventure.core.exceptions import ConfigurationError

        shared = "shared-backend-secret-0123456789abcdef01"  # >= 32 bytes
        with pytest.raises(ConfigurationError) as exc_info:
            _non_local_settings(child_session_secret=shared, device_grant_secret=shared)
        # The secret value must never surface in the message.
        assert shared not in str(exc_info.value)

    @pytest.mark.unit
    def test_distinct_audiences_and_secrets_are_valid(self) -> None:
        """The shipped distinct defaults pass the invariant."""
        settings = _non_local_settings()
        assert settings.oidc_audience == "authenticated"

    @pytest.mark.unit
    def test_shipped_token_audiences_are_pairwise_distinct(self) -> None:
        """The three shipped audience values are pairwise distinct (issue #251).

        Pins the invariant the validator documents at the value level, so a
        future edit that made two ``TokenAudience`` members share a literal (or
        pointed OIDC_AUDIENCE at a backend value) is caught here as well as at
        startup.
        """
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.token_audience import TokenAudience

        audiences = {
            Settings(environment="local").oidc_audience,
            TokenAudience.CHILD_SESSION.value,
            TokenAudience.DEVICE_GRANT.value,
        }
        assert len(audiences) == 3

    @pytest.mark.unit
    def test_local_shares_no_secret_by_default_is_valid(self) -> None:
        """Local with both secrets unset does not trip the distinctness check."""
        from cyo_adventure.core.config import Settings

        settings = Settings(environment="local")
        assert settings.child_session_secret is None
        assert settings.device_grant_secret is None


class TestChildSessionTtlSetting:
    """Tests for child_session_ttl_seconds env binding and its ge=1 bound.

    The field declares validation_alias=AliasChoices(prefixed, unprefixed);
    without it the unprefixed CHILD_SESSION_TTL_SECONDS the .env templates
    document is silently ignored and every deploy keeps the 12h default.
    """

    @pytest.mark.unit
    def test_ttl_defaults_to_twelve_hours(self) -> None:
        """child_session_ttl_seconds defaults to 43200 (12h) when unset."""
        from cyo_adventure.core.config import Settings

        assert Settings(environment="local").child_session_ttl_seconds == 43_200

    @pytest.mark.unit
    def test_ttl_reads_unprefixed_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """child_session_ttl_seconds reads the unprefixed CHILD_SESSION_TTL_SECONDS."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("CYO_ADVENTURE_CHILD_SESSION_TTL_SECONDS", raising=False)
        monkeypatch.setenv("CHILD_SESSION_TTL_SECONDS", "3600")
        assert Settings(environment="local").child_session_ttl_seconds == 3_600

    @pytest.mark.unit
    def test_ttl_reads_prefixed_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The prefixed CYO_ADVENTURE_CHILD_SESSION_TTL_SECONDS name also binds."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("CHILD_SESSION_TTL_SECONDS", raising=False)
        monkeypatch.setenv("CYO_ADVENTURE_CHILD_SESSION_TTL_SECONDS", "1800")
        assert Settings(environment="local").child_session_ttl_seconds == 1_800

    @pytest.mark.unit
    def test_ttl_prefixed_wins_when_both_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When both names are set, the explicit CYO_ADVENTURE_ prefix wins."""
        from cyo_adventure.core.config import Settings

        monkeypatch.setenv("CHILD_SESSION_TTL_SECONDS", "3600")
        monkeypatch.setenv("CYO_ADVENTURE_CHILD_SESSION_TTL_SECONDS", "1800")
        assert Settings(environment="local").child_session_ttl_seconds == 1_800

    @pytest.mark.unit
    @pytest.mark.parametrize("ttl", ["0", "-1"])
    def test_ttl_non_positive_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, ttl: str
    ) -> None:
        """A zero/negative TTL fails the ge=1 bound at construction time."""
        from pydantic import ValidationError

        from cyo_adventure.core.config import Settings

        monkeypatch.setenv("CHILD_SESSION_TTL_SECONDS", ttl)
        with pytest.raises(ValidationError):
            Settings(environment="local")


class TestAnthropicGenerationSettings:
    """Tests for the direct-Anthropic settings (WS-C PR1)."""

    @pytest.mark.unit
    def test_generation_provider_accepts_anthropic(self) -> None:
        """generation_provider accepts the renamed 'anthropic' literal value."""
        from cyo_adventure.core.config import Settings

        settings = Settings(generation_provider="anthropic")
        assert settings.generation_provider == "anthropic"

    @pytest.mark.unit
    def test_generation_provider_rejects_claude(self) -> None:
        """The dead 'claude' literal is gone; no back-compat shim (spec decision)."""
        from pydantic import ValidationError as PydanticValidationError

        from cyo_adventure.core.config import Settings

        with pytest.raises(PydanticValidationError):
            Settings(generation_provider="claude")

    @pytest.mark.unit
    def test_anthropic_settings_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """anthropic_api_key defaults to None; base_url/model have code defaults."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        settings = Settings()
        assert settings.anthropic_api_key is None
        assert settings.anthropic_base_url == "https://api.anthropic.com"
        assert settings.anthropic_model == "claude-sonnet-4-6"

    @pytest.mark.unit
    def test_anthropic_api_key_reads_unprefixed_env_var(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ANTHROPIC_API_KEY (unprefixed) populates anthropic_api_key."""
        from cyo_adventure.core.config import Settings

        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        settings = Settings()
        assert settings.anthropic_api_key == "sk-ant-test"


class TestOidcAllowedAlgs:
    """The config-driven JWT signature-algorithm allowlist (ADR-013).

    The allowlist moved from a hardcoded list in api/deps.py into Settings so
    a future post-quantum JOSE algorithm (e.g. ML-DSA) is an env change, not a
    code change. The validator must keep that agility from reopening the
    classic JWT forgeries: empty list, alg=none, and the symmetric HS* family
    are all startup failures.
    """

    @pytest.mark.unit
    def test_oidc_allowed_algs_default_is_rs256_es256(self) -> None:
        """The default allowlist matches what Supabase issues today."""
        from cyo_adventure.core.config import Settings

        assert Settings().oidc_allowed_algs == ["RS256", "ES256"]

    @pytest.mark.unit
    def test_oidc_allowed_algs_empty_list_raises(self) -> None:
        """An empty allowlist would make every token unverifiable; fail fast."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError):
            Settings(oidc_allowed_algs=[])

    @pytest.mark.unit
    @pytest.mark.parametrize("alg", ["none", "None", "NONE", " none "])
    def test_oidc_allowed_algs_none_algorithm_raises(self, alg: str) -> None:
        """alg=none in the allowlist would accept unsigned tokens; fail fast."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError):
            Settings(oidc_allowed_algs=["RS256", alg])

    @pytest.mark.unit
    @pytest.mark.parametrize("alg", ["HS256", "hs384", "HS512", " HS256 "])
    def test_oidc_allowed_algs_symmetric_hs_family_raises(self, alg: str) -> None:
        """HS* in the allowlist reopens public-key-as-HMAC-secret confusion."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError):
            Settings(oidc_allowed_algs=[alg])

    @pytest.mark.unit
    def test_oidc_allowed_algs_accepts_future_pqc_algorithm(self) -> None:
        """A post-quantum JOSE alg name passes validation (the ADR-013 point).

        The validator is a denylist (none/HS*), not an allowlist of known
        names, precisely so a finalized ML-DSA JOSE registration can be
        enabled by env var without touching this code.
        """
        from cyo_adventure.core.config import Settings

        settings = Settings(oidc_allowed_algs=["ES256", "ML-DSA-44"])
        assert settings.oidc_allowed_algs == ["ES256", "ML-DSA-44"]

    @pytest.mark.unit
    def test_oidc_allowed_algs_reads_unprefixed_env_var(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """OIDC_ALLOWED_ALGS (unprefixed, JSON list) populates the allowlist."""
        from cyo_adventure.core.config import Settings

        monkeypatch.setenv("OIDC_ALLOWED_ALGS", '["ES256"]')
        assert Settings().oidc_allowed_algs == ["ES256"]

    @pytest.mark.unit
    def test_oidc_allowed_algs_strips_surrounding_whitespace(self) -> None:
        """A padded but valid alg is normalized, not silently left unusable.

        Regression guard: the validator must return the stripped form, not the
        raw input. Returning " ES256 " unchanged would pass startup and then
        fail PyJWT's exact-string registry match on every request, breaking
        auth in production while the process still boots healthy (ADR-013).
        """
        from cyo_adventure.core.config import Settings

        settings = Settings(oidc_allowed_algs=[" ES256 ", "RS256\t"])
        assert settings.oidc_allowed_algs == ["ES256", "RS256"]


class TestWorkerDatabaseUrlEffectiveProperty:
    """Tests for worker_database_url_effective (ADR-021)."""

    @pytest.mark.unit
    def test_none_falls_back_to_database_url(self) -> None:
        """An unset worker_database_url falls back to database_url."""
        from cyo_adventure.core.config import Settings

        settings = Settings(database_url=_PROD_DB_URL, worker_database_url=None)

        assert settings.worker_database_url_effective == _PROD_DB_URL

    @pytest.mark.unit
    def test_empty_string_falls_back_to_database_url(self) -> None:
        """An explicitly empty worker_database_url also falls back.

        Regression guard: compose interpolation of an unset variable
        (${WORKER_DATABASE_URL:-}) injects "" rather than leaving the
        variable unset, so "" must be treated the same as None, not as a
        configured-but-empty DSN.
        """
        from cyo_adventure.core.config import Settings

        settings = Settings(database_url=_PROD_DB_URL, worker_database_url="")

        assert settings.worker_database_url_effective == _PROD_DB_URL

    @pytest.mark.unit
    def test_explicit_value_is_used_as_is(self) -> None:
        """A configured worker_database_url is returned unchanged, not merged."""
        from cyo_adventure.core.config import Settings

        worker_url = (
            "postgresql+asyncpg://cyo_worker:testpass@db.example.com/cyo_adventure"
        )
        settings = Settings(database_url=_PROD_DB_URL, worker_database_url=worker_url)

        assert settings.worker_database_url_effective == worker_url

    @pytest.mark.unit
    def test_worker_database_url_reads_unprefixed_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """WORKER_DATABASE_URL (unprefixed) binds, matching DATABASE_URL's convention."""
        from cyo_adventure.core.config import Settings

        worker_url = (
            "postgresql+asyncpg://cyo_worker:testpass@db.example.com/cyo_adventure"
        )
        monkeypatch.setenv("WORKER_DATABASE_URL", worker_url)

        assert Settings().worker_database_url_effective == worker_url

    @pytest.mark.unit
    def test_worker_database_url_reads_prefixed_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CYO_ADVENTURE_WORKER_DATABASE_URL also binds."""
        from cyo_adventure.core.config import Settings

        worker_url = (
            "postgresql+asyncpg://cyo_worker:testpass@db.example.com/cyo_adventure"
        )
        monkeypatch.setenv("CYO_ADVENTURE_WORKER_DATABASE_URL", worker_url)

        assert Settings().worker_database_url_effective == worker_url

    @pytest.mark.unit
    def test_worker_database_url_prefixed_wins_when_both_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The CYO_ADVENTURE_-prefixed form wins over the unprefixed alias."""
        from cyo_adventure.core.config import Settings

        prefixed_url = "postgresql+asyncpg://cyo_worker:testpass@prefixed.example.com/x"
        unprefixed_url = (
            "postgresql+asyncpg://cyo_worker:testpass@unprefixed.example.com/x"
        )
        monkeypatch.setenv("CYO_ADVENTURE_WORKER_DATABASE_URL", prefixed_url)
        monkeypatch.setenv("WORKER_DATABASE_URL", unprefixed_url)

        assert Settings().worker_database_url_effective == prefixed_url


class TestValidatorPreparedCacheAppliesToWorkerUrl:
    """Tests that the pooler-port validator (ADR-021) also checks the worker DSN."""

    @pytest.mark.unit
    def test_worker_pooler_dsn_with_flag_false_raises(self) -> None:
        """A worker DSN on the Supavisor pooler port must fail fast too."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError):
            Settings(
                database_url=_PROD_DB_URL,
                worker_database_url=_POOLER_DB_URL,
                database_disable_prepared_cache=False,
            )

    @pytest.mark.unit
    def test_worker_pooler_dsn_with_flag_true_is_valid(self) -> None:
        """A worker DSN on the pooler port with the flag on must not raise."""
        from cyo_adventure.core.config import Settings

        settings = Settings(
            database_url=_PROD_DB_URL,
            worker_database_url=_POOLER_DB_URL,
            database_disable_prepared_cache=True,
        )
        assert settings.worker_database_url_effective == _POOLER_DB_URL

    @pytest.mark.unit
    def test_worker_url_falling_back_to_pooler_primary_still_raises(self) -> None:
        """An unset worker_database_url that falls back to a pooler primary DSN
        still fails fast (the fallback is evaluated, not skipped)."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError):
            Settings(
                database_url=_POOLER_DB_URL,
                worker_database_url=None,
                database_disable_prepared_cache=False,
            )

    @pytest.mark.unit
    def test_error_message_for_worker_dsn_mentions_worker_env_var_name(self) -> None:
        """The worker-DSN failure message names the worker env var, not just the API one."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError) as exc_info:
            Settings(
                database_url=_PROD_DB_URL,
                worker_database_url=_POOLER_DB_URL,
                database_disable_prepared_cache=False,
            )

        message = str(exc_info.value)
        assert "6543" in message
        assert "CYO_ADVENTURE_WORKER_DATABASE_URL" in message


class TestDatabasePoolBounds:
    """Tests for database_pool_size / database_max_overflow (ADR-021)."""

    @pytest.mark.unit
    def test_pool_size_defaults_to_five(self) -> None:
        """database_pool_size defaults to 5, matching SQLAlchemy's prior implicit default."""
        from cyo_adventure.core.config import Settings

        assert Settings().database_pool_size == 5

    @pytest.mark.unit
    def test_max_overflow_defaults_to_ten(self) -> None:
        """database_max_overflow defaults to 10, matching SQLAlchemy's prior implicit default."""
        from cyo_adventure.core.config import Settings

        assert Settings().database_max_overflow == 10

    @pytest.mark.unit
    def test_pool_size_zero_is_rejected(self) -> None:
        """A pool size of 0 would starve every connection request; reject it."""
        from pydantic import ValidationError

        from cyo_adventure.core.config import Settings

        with pytest.raises(ValidationError):
            Settings(database_pool_size=0)

    @pytest.mark.unit
    def test_max_overflow_zero_is_accepted(self) -> None:
        """A max_overflow of 0 (no bursting past pool_size) is a valid, if strict, choice."""
        from cyo_adventure.core.config import Settings

        settings = Settings(database_max_overflow=0)

        assert settings.database_max_overflow == 0

    @pytest.mark.unit
    def test_max_overflow_negative_is_rejected(self) -> None:
        """A negative max_overflow is nonsensical; reject it."""
        from pydantic import ValidationError

        from cyo_adventure.core.config import Settings

        with pytest.raises(ValidationError):
            Settings(database_max_overflow=-1)
