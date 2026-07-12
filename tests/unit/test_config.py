"""Tests for cyo_adventure.core.config module.

Covers:
- Settings with default values (environment='local')
- The _reject_dev_database_url_outside_local model_validator: raises
  ConfigurationError when environment is non-local and database_url is the
  dev default.
- Happy path for non-local environments when a real database_url is supplied.
"""

from __future__ import annotations

import pytest

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
    """log_level, json_logs, and database_url read the unprefixed names that
    docker-compose and docs/guides/configuration.md actually set, while
    database_url keeps its prefixed CYO_ADVENTURE_DATABASE_URL contract."""

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


def _non_local_settings(**overrides: object) -> object:
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
        assert settings.child_session_secret is not None  # type: ignore[attr-defined]

    @pytest.mark.unit
    def test_local_environment_without_child_secret_is_valid(self) -> None:
        """Local environment does not require a child-session secret (dev stub)."""
        from cyo_adventure.core.config import Settings

        settings = Settings(environment="local")
        assert settings.child_session_secret is None


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
