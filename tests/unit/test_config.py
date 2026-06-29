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

        # Must not raise
        s = Settings(environment=environment, database_url=_PROD_DB_URL)

        assert s.environment == environment
        assert s.database_url == _PROD_DB_URL

    @pytest.mark.unit
    def test_local_environment_with_real_url_is_valid(self) -> None:
        """Settings(environment='local') accepts a non-default database_url without error."""
        from cyo_adventure.core.config import Settings

        s = Settings(environment="local", database_url=_PROD_DB_URL)

        assert s.database_url == _PROD_DB_URL
