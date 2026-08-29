"""Tests for cyo_adventure.core.config module.

Covers:
- Settings with default values (environment='local')
- The _reject_dev_database_url_outside_local model_validator: raises
  ConfigurationError when environment is non-local and database_url is the
  dev default.
- Happy path for non-local environments when a real database_url is supplied.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest

if TYPE_CHECKING:
    from pathlib import Path

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
# The four values needed before any KWS API call can be made. Not real
# credentials: the ids are placeholder UUIDs and the host is the documented
# one, so a secrets scanner has nothing to match.
_KWS_CREDS = {
    "kws_organization_id": "00000000-0000-4000-8000-000000000001",
    "kws_api_origin": "https://api.kidswebservices.com",
    "kws_client_id": "00000000-0000-4000-8000-000000000002",
    "kws_api_key": "test-kws-api-key-not-a-real-secret",
}
# The two methods currently switched on in the Control Panel, and the only two
# a configured integration can be constructed with (an empty declaration is
# refused; see _require_declared_kws_methods_when_configured).
_KWS_METHODS = ["credit_card", "debit_card"]


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


class TestRetiredOllamaSettings:
    """The OLLAMA_* config surface is gone and must not come back silently."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "field",
        [
            "ollama_model",
            "ollama_base_url",
            "ollama_auth",
            "ollama_ca_bundle",
            "ollama_timeout_seconds",
            "review_ollama_model",
        ],
    )
    def test_ollama_settings_are_removed(self, field: str) -> None:
        """No Ollama field survives on Settings.

        A stale OLLAMA_* entry in a deploy's env is now inert rather than
        half-wired, and reintroducing one of these names by accident (say by
        reviving a deleted block during a merge) fails here instead of
        shipping a setting nothing reads.
        """
        from cyo_adventure.core.config import Settings

        assert field not in Settings.model_fields

    @pytest.mark.unit
    def test_ollama_is_not_a_valid_generation_provider(self) -> None:
        """The retired backend is rejected at the Settings boundary."""
        from pydantic import ValidationError as PydanticValidationError

        from cyo_adventure.core.config import Settings

        with pytest.raises(PydanticValidationError):
            Settings(generation_provider="ollama")  # type: ignore[arg-type]

    @pytest.mark.unit
    def test_ollama_is_not_a_valid_review_provider(self) -> None:
        """The retired review backend is rejected at the Settings boundary."""
        from pydantic import ValidationError as PydanticValidationError

        from cyo_adventure.core.config import Settings

        with pytest.raises(PydanticValidationError):
            Settings(review_provider="ollama")  # type: ignore[arg-type]


class TestModalLegConfigured:
    """modal_leg_configured gates whether the cascade gets its third leg."""

    @pytest.mark.unit
    def test_both_fields_set_is_configured(self) -> None:
        """The predicate is true only when a leg could actually be built."""
        from cyo_adventure.core.config import Settings

        settings = Settings(
            modal_base_url="https://example--cyo.modal.run/v1",
            modal_model="google/gemma-4-26b-a4b-it",
        )
        assert settings.modal_leg_configured is True

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("base_url", "model"),
        [
            (None, None),
            ("https://example--cyo.modal.run/v1", None),
            (None, "google/gemma-4-26b-a4b-it"),
            ("", "google/gemma-4-26b-a4b-it"),
            ("https://example--cyo.modal.run/v1", ""),
        ],
    )
    def test_missing_or_empty_half_is_not_configured(
        self, base_url: str | None, model: str | None
    ) -> None:
        """Anything build_modal_leg would reject must read as unconfigured.

        The two must agree exactly: if this predicate said "configured" for a
        state build_modal_leg raises on, build_provider would raise inside the
        cascade path and take down generation in every such environment.
        """
        from cyo_adventure.core.config import Settings

        settings = Settings(modal_base_url=base_url, modal_model=model)
        assert settings.modal_leg_configured is False


class TestModalProxyCredentialPairing:
    """A half-set Modal proxy pair is rejected at startup, not at job time."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("key", "secret"),
        [
            ("only-key", None),
            (None, "only-secret"),
            ("only-key", ""),
            ("", "only-secret"),
        ],
    )
    def test_half_set_pair_is_rejected(
        self, key: str | None, secret: str | None
    ) -> None:
        """Either half alone fails fast.

        build_modal_leg would also reject this, but only once a job actually
        built the leg. Since Modal became the default cascade's third leg that
        raise would fire on every generation job, so catching it at startup is
        what keeps the misconfiguration from reaching a serving deploy.
        """
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError, match="MODAL_PROXY"):
            Settings(modal_proxy_key=key, modal_proxy_secret=secret)

    @pytest.mark.unit
    @pytest.mark.parametrize(
        ("key", "secret"),
        [(None, None), ("a-key", "a-secret")],
    )
    def test_coherent_pair_is_accepted(
        self, key: str | None, secret: str | None
    ) -> None:
        """Neither set (no proxy auth) and both set are both valid states."""
        from cyo_adventure.core.config import Settings

        settings = Settings(modal_proxy_key=key, modal_proxy_secret=secret)
        assert settings.modal_proxy_key == key

    @pytest.mark.unit
    def test_pairing_does_not_affect_modal_leg_configured(self) -> None:
        """The credential check is separate from the "can a leg be built" check.

        modal_leg_configured must not treat a credential problem as "no leg":
        that would silently drop the cascade's backstop for an operator typo,
        which is the opposite of the loud failure this pairing rule exists for.
        """
        from cyo_adventure.core.config import Settings

        settings = Settings(
            modal_base_url="https://example--cyo.modal.run/v1",
            modal_model="google/gemma-4-26b-a4b-it",
            modal_proxy_key="a-key",
            modal_proxy_secret="a-secret",
        )
        assert settings.modal_leg_configured is True


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
            # Unrelated to this test's own invariant (database_url); the
            # default review_provider="mock" outside environment="local"
            # now requires this hatch (_require_real_reviewer_outside_local).
            allow_mock_review=True,
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
            allow_mock_review=True,
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
            allow_mock_review=True,
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

    @pytest.mark.unit
    def test_non_mock_review_with_only_perspective_key_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A Perspective-only deployment no longer satisfies the classifier gate.

        Perspective sunsets 2026-12-31, after which the key still parses but the
        API returns nothing. Counting it as a satisfying classifier would let a
        live reviewer run over children's content with no working pre-filter.
        """
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ConfigurationError):
            Settings(review_provider="openrouter", perspective_api_key="k")

    @pytest.mark.unit
    def test_classifier_requirement_error_names_the_required_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ConfigurationError names OPENAI_API_KEY so the fix is unambiguous."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("PERSPECTIVE_API_KEY", raising=False)
        with pytest.raises(ConfigurationError) as excinfo:
            Settings(review_provider="openrouter")
        assert "OPENAI_API_KEY" in str(excinfo.value)


class TestReviewBatchSize:
    """Tests for review_batch_size (design doc 2.2 item 2, Stage B2)."""

    @pytest.mark.unit
    def test_review_batch_size_defaults_to_eight(self) -> None:
        """The default is 8, ratified by the Gate 3 recall comparison (two
        identical owner runs on 2026-08-01; artifact
        docs/planning/safety/batch-sweep-results-2026-08-01.json): zero
        recall regression vs size 1 and zero structural collapses."""
        from cyo_adventure.core.config import Settings

        assert Settings().review_batch_size == 8

    @pytest.mark.unit
    def test_review_batch_size_reads_from_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from cyo_adventure.core.config import Settings

        monkeypatch.setenv("CYO_ADVENTURE_REVIEW_BATCH_SIZE", "10")
        assert Settings().review_batch_size == 10

    @pytest.mark.unit
    @pytest.mark.parametrize("value", [0, 51], ids=["below_min", "above_max"])
    def test_review_batch_size_out_of_bounds_raises(self, value: int) -> None:
        from pydantic import ValidationError as PydanticValidationError

        from cyo_adventure.core.config import Settings

        with pytest.raises(PydanticValidationError):
            Settings(review_batch_size=value)

    @pytest.mark.unit
    @pytest.mark.parametrize("value", [1, 50], ids=["lower_bound", "upper_bound"])
    def test_review_batch_size_at_boundary_does_not_raise(self, value: int) -> None:
        from cyo_adventure.core.config import Settings

        assert Settings(review_batch_size=value).review_batch_size == value


class TestValidatorRequireRealReviewerOutsideLocal:
    """Tests for the _require_real_reviewer_outside_local model_validator.

    Design doc section 2.4 (moderation review redesign, Stage A): the mock
    reviewer runs no real safety review, so booting with it outside
    environment="local" must fail fast unless the operator explicitly opts
    in via allow_mock_review / CYO_ADVENTURE_ALLOW_MOCK_REVIEW.
    """

    _OIDC_KWARGS: ClassVar[dict[str, str]] = {
        "oidc_issuer": "https://project.supabase.co/auth/v1",
        "oidc_jwks_url": "https://project.supabase.co/auth/v1/.well-known/jwks.json",
        "child_session_secret": _CHILD_SECRET,
        "device_grant_secret": _DEVICE_SECRET,
    }

    @pytest.mark.unit
    def test_local_environment_with_mock_review_is_valid(self) -> None:
        """The default posture (local + mock) boots without the hatch."""
        from cyo_adventure.core.config import Settings

        settings = Settings()
        assert settings.environment == "local"
        assert settings.review_provider == "mock"
        assert settings.allow_mock_review is False

    @pytest.mark.unit
    @pytest.mark.parametrize("environment", ["dev", "staging", "production"])
    def test_non_local_environment_with_mock_review_without_hatch_raises(
        self, environment: str
    ) -> None:
        """A non-local process defaulting to the mock reviewer refuses to boot."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError) as excinfo:
            Settings(
                environment=environment,
                database_url=_PROD_DB_URL,
                review_provider="mock",
                **self._OIDC_KWARGS,
            )
        message = str(excinfo.value)
        assert environment in message
        assert "CYO_ADVENTURE_ALLOW_MOCK_REVIEW" in message

    @pytest.mark.unit
    def test_non_local_environment_with_mock_review_and_hatch_boots(self) -> None:
        """The explicit escape hatch allows the same combination to boot."""
        from cyo_adventure.core.config import Settings

        settings = Settings(
            environment="staging",
            database_url=_PROD_DB_URL,
            review_provider="mock",
            allow_mock_review=True,
            **self._OIDC_KWARGS,
        )
        assert settings.review_provider == "mock"
        assert settings.allow_mock_review is True

    @pytest.mark.unit
    def test_non_local_environment_with_real_reviewer_and_no_hatch_is_valid(
        self,
    ) -> None:
        """A real (non-mock) reviewer never needs the hatch outside local."""
        from cyo_adventure.core.config import Settings

        settings = Settings(
            environment="production",
            database_url=_PROD_DB_URL,
            review_provider="openrouter",
            openai_api_key="k",
            **self._OIDC_KWARGS,
        )
        assert settings.review_provider == "openrouter"
        assert settings.allow_mock_review is False


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
            allow_mock_review=True,
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
        # Unrelated to what each caller's test actually varies; the default
        # review_provider="mock" outside environment="local" now requires
        # this hatch (_require_real_reviewer_outside_local). A caller
        # testing an earlier-declared validator's raise path is unaffected:
        # that validator still fires first regardless of this value.
        "allow_mock_review": True,
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


class TestRateLimitRedisBounds:
    """Lower bounds on the two rate-limit Redis knobs (issue #516 follow-up).

    Both settings were inert until add_security_middleware started passing
    them, so a bad value used to do nothing. The cooldown now arms a circuit
    breaker as ``current_time + cooldown_seconds``; a negative value lands
    that deadline in the PAST, so the breaker never suppresses a retry and a
    sustained Redis outage pays the socket timeout on every request. That is
    exactly the cost the field's own #CRITICAL note says the breaker exists
    to avoid, which is why the bound belongs at parse time rather than at the
    first Redis call.
    """

    @pytest.mark.unit
    def test_rate_limit_redis_bounds_reject_negative(self) -> None:
        """A negative timeout or cooldown fails the ge=0.0 bound."""
        from pydantic import ValidationError

        from cyo_adventure.core.config import Settings

        with pytest.raises(ValidationError):
            Settings(rate_limit_redis_timeout_seconds=-1.0)

        with pytest.raises(ValidationError):
            Settings(rate_limit_redis_cooldown_seconds=-1.0)

    @pytest.mark.unit
    def test_rate_limit_redis_bounds_accept_zero(self) -> None:
        """0 stays legal for both.

        It is how a deployment opts out of the wait entirely, and
        _resolve_rate_limit_redis_config preserves it (``is not None``, not
        ``or``), so the bound must not quietly promote 0 into a default.
        """
        from cyo_adventure.core.config import Settings

        timeout_settings = Settings(rate_limit_redis_timeout_seconds=0.0)
        cooldown_settings = Settings(rate_limit_redis_cooldown_seconds=0.0)

        assert timeout_settings.rate_limit_redis_timeout_seconds == 0.0
        assert cooldown_settings.rate_limit_redis_cooldown_seconds == 0.0


class TestKwsSettings:
    """Tests for the Parent Verification Service (KWS, Epic; ADR-018) settings.

    KWS verifies that an adult is an adult. It is not, by Epic's own
    documentation, a COPPA consent or direct-notice mechanism, so nothing here
    asserts anything about 16 CFR 312.5 being satisfied; these tests cover the
    configuration invariants only.
    """

    @pytest.fixture(autouse=True)
    def _clear_kws_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Keep a developer's own KWS_* exports out of these assertions."""
        for name in (
            "KWS_ENVIRONMENT",
            "KWS_ENVIRONMENT_LABEL",
            "KWS_ORGANIZATION_ID",
            "KWS_PRODUCT_ID",
            "KWS_API_ORIGIN",
            "KWS_AUTH_ORIGIN",
            "KWS_CLIENT_ID",
            "KWS_API_KEY",
            "KWS_USER_AGENT",
            "KWS_WEBHOOK_SECRET",
            "KWS_VERIFICATION_SECRET",
            "KWS_WEBHOOK_MAX_SKEW_SECONDS",
            "KWS_ENABLED_METHODS",
        ):
            monkeypatch.delenv(name, raising=False)

    @pytest.mark.unit
    def test_kws_environment_defaults_to_test(self) -> None:
        """The default is the sandbox, because the failure modes are asymmetric."""
        from cyo_adventure.core.config import Settings

        assert Settings().kws_environment == "test"

    @pytest.mark.unit
    def test_unconfigured_by_default(self) -> None:
        """No credentials means no KWS call is ever made; there is no enable flag."""
        from cyo_adventure.core.config import Settings

        assert Settings().kws_configured is False

    @pytest.mark.unit
    def test_complete_kws_credentials_are_accepted(self) -> None:
        """All four present is the only configured state."""
        from cyo_adventure.core.config import Settings

        assert Settings(kws_enabled_methods=_KWS_METHODS, **_KWS_CREDS).kws_configured

    @pytest.mark.unit
    @pytest.mark.parametrize("omitted", list(_KWS_CREDS))
    def test_partial_kws_credentials_are_rejected(self, omitted: str) -> None:
        """Omitting any one of the four fails at startup, naming the gap.

        Every single-omission case is covered rather than one representative,
        because the point of the validator is that no partial set boots.
        """
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        partial = {k: v for k, v in _KWS_CREDS.items() if k != omitted}

        with pytest.raises(ConfigurationError, match="partially configured"):
            Settings(**partial)

    @pytest.mark.unit
    def test_empty_string_kws_credentials_count_as_unset(self) -> None:
        """Compose injects "" for an unset variable; that must read as absent.

        ``${KWS_API_KEY:-}`` interpolates to an empty string rather than
        leaving the variable unset, so an all-empty set is a fully
        unconfigured integration, not four configured-but-empty credentials.
        """
        from cyo_adventure.core.config import Settings

        settings = Settings(**dict.fromkeys(_KWS_CREDS, ""))

        assert settings.kws_configured is False

    @pytest.mark.unit
    def test_one_empty_string_credential_is_still_partial(self) -> None:
        """An empty value among three real ones is the partial case, not opt-out."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError, match="KWS_API_KEY"):
            Settings(**{**_KWS_CREDS, "kws_api_key": ""})

    @pytest.mark.unit
    def test_empty_kws_user_agent_falls_back_to_the_default(self) -> None:
        """An empty override must not defeat the non-empty constraint.

        This is the deployment case, not a theoretical one: ``${VAR:-}`` is the
        house compose idiom for an optional variable and injects ``""``. With
        ``min_length=1`` and no coercion, that string is a ValidationError at
        settings construction, so the container never starts. Falling back to
        the default keeps a real User-Agent on the wire, which KWS requires:
        an empty one is answered with 403 "Request blocked".
        """
        from cyo_adventure.core.config import Settings

        assert Settings(kws_user_agent="").kws_user_agent == "cyo-adventure"

    @pytest.mark.unit
    def test_empty_kws_skew_seconds_falls_back_to_the_default(self) -> None:
        """Same idiom, same failure: "" is not an int and would refuse to boot."""
        from cyo_adventure.core.config import Settings

        assert (
            Settings(kws_webhook_max_skew_seconds="").kws_webhook_max_skew_seconds
            == 300
        )

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "field",
        [
            "kws_environment_label",
            "kws_organization_id",
            "kws_product_id",
            "kws_api_origin",
            "kws_client_id",
        ],
    )
    def test_empty_kws_identifier_is_unset_not_a_value(self, field: str) -> None:
        """``""`` must be indistinguishable from unset for every identifier.

        The same ``${VAR:-}`` idiom that would refuse to boot on a constrained
        field fails silently on these: they default to None to mean "not pinned
        yet", and their consumers test that with ``is None``. An empty string
        is not None, so the escape hatch closes and the field becomes a value
        nothing can ever equal.

        That is not hypothetical. On 2026-08-10 a correctly signed, one-second-
        old ``parent-verified`` delivery was ignored with ``200 handled=False``
        because ``kws_product_id`` was ``""`` and ``_product_matches`` compared
        against it instead of skipping the check. Nothing raised and nothing
        retried, so ``is None`` is asserted here rather than falsiness: only
        the former is what the consumers actually branch on.
        """
        from cyo_adventure.core.config import Settings

        assert getattr(Settings(**{field: ""}), field) is None

    @pytest.mark.unit
    def test_a_real_kws_user_agent_override_still_wins(self) -> None:
        """The fallback must be scoped to emptiness, not swallow real values."""
        from cyo_adventure.core.config import Settings

        assert Settings(kws_user_agent="cyo/1.2").kws_user_agent == "cyo/1.2"

    @pytest.mark.unit
    def test_a_real_kws_product_id_still_pins_the_check(self) -> None:
        """Normalising emptiness must not disable the guard it protects.

        The point of tolerating ``""`` is to keep the *unpinned* state
        reachable, not to make the pinned state unreachable. A real value has
        to survive, or the fix would trade a guard that never passes for one
        that never fires.
        """
        from cyo_adventure.core.config import Settings

        assert Settings(kws_product_id="prod-1").kws_product_id == "prod-1"

    @pytest.mark.unit
    def test_a_real_kws_skew_override_still_wins(self) -> None:
        """A configured window must survive the empty-string coercion."""
        from cyo_adventure.core.config import Settings

        assert (
            Settings(kws_webhook_max_skew_seconds=120).kws_webhook_max_skew_seconds
            == 120
        )

    @pytest.mark.unit
    def test_production_kws_environment_rejected_from_a_local_app(self) -> None:
        """A developer machine must not mint records indistinguishable from real ones."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError, match="KWS_ENVIRONMENT='production'"):
            Settings(
                environment="local",
                kws_environment="production",
                kws_enabled_methods=_KWS_METHODS,
                **_KWS_CREDS,
            )

    @pytest.mark.unit
    def test_test_kws_environment_allowed_in_a_deployed_tier(self) -> None:
        """The guard is one-directional: staging against the sandbox is normal."""
        from cyo_adventure.core.config import Settings

        settings = Settings(
            environment="staging",
            kws_environment="test",
            database_url=_PROD_DB_URL,
            oidc_issuer="https://project.supabase.co/auth/v1",
            oidc_jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
            child_session_secret=_CHILD_SECRET,
            device_grant_secret=_DEVICE_SECRET,
            allow_mock_review=True,
            kws_enabled_methods=_KWS_METHODS,
            **_KWS_CREDS,
        )

        assert settings.kws_environment == "test"

    @pytest.mark.unit
    def test_kws_secrets_are_secretstr(self) -> None:
        """The API key must not surface in a repr, log line, or error message."""
        from cyo_adventure.core.config import Settings

        settings = Settings(kws_enabled_methods=_KWS_METHODS, **_KWS_CREDS)
        api_key = settings.kws_api_key

        assert api_key is not None
        assert api_key.get_secret_value() == _KWS_CREDS["kws_api_key"]
        assert _KWS_CREDS["kws_api_key"] not in repr(settings)

    @pytest.mark.unit
    def test_kws_user_agent_defaults_non_empty(self) -> None:
        """KWS answers 403 "Request blocked" to a missing or empty user-agent.

        Defaulting rather than leaving it None means that failure mode cannot
        be reached by omission.
        """
        from cyo_adventure.core.config import Settings

        assert Settings().kws_user_agent

    @pytest.mark.unit
    def test_the_resolved_kws_user_agent_is_never_empty(self) -> None:
        """The durable invariant: an empty user-agent never reaches KWS.

        This test previously asserted that ``kws_user_agent=""`` raises, which
        enforced the same invariant by refusing to construct settings at all.
        That was changed deliberately: the empty string's realistic source is
        ``${KWS_USER_AGENT:-}`` in compose, not an operator typing an empty
        value, and refusing to boot over an optional variable with a perfectly
        good default trades a 403 on one API call for a dead container. The
        property being protected is unchanged and is what this asserts: the
        field cannot HOLD an empty value by any route.
        """
        from cyo_adventure.core.config import Settings

        assert Settings().kws_user_agent
        assert Settings(kws_user_agent="").kws_user_agent
        assert Settings(kws_user_agent="   ").kws_user_agent

    @pytest.mark.unit
    def test_every_kws_setting_tolerates_an_empty_override(self) -> None:
        """Enumerate the KWS block instead of pinning a list of field names.

        The empty-override validator is opt-in per field, so the real defect is
        not any single omission but the fact that adding a KWS setting and
        forgetting the decorator is silent: no tier passes
        ``${KWS_OPEN_ATTEMPT_MINUTES:-}`` today, so the container that dies is
        the next one, on a machine nobody is watching. Four fields were already
        missing when this test was written (the two rate-limit ints and the two
        booleans), plus ``kws_environment`` and ``kws_auth_origin``.

        Enumerating ``model_fields`` makes the next omission fail here rather
        than at boot. The two carve-outs are the ones the validator's docstring
        justifies, and naming them explicitly means widening the exclusion set
        is a visible edit rather than a quiet one.
        """
        from cyo_adventure.core.config import Settings

        deliberately_unnormalised = {
            # Credentials: "" already counts as missing where it is read.
            "kws_api_key",
            "kws_webhook_secret",
            "kws_verification_secret",
            # Evidence, not configuration: refusal to boot IS the control.
            "kws_enabled_methods",
        }
        kws_fields = [
            name
            for name in Settings.model_fields
            if name.startswith("kws_") and name not in deliberately_unnormalised
        ]

        assert kws_fields, "the KWS block moved; this test is now vacuous"

        # Compare against a bare Settings() rather than FieldInfo.get_default(),
        # which returns PydanticUndefined for any default_factory field and
        # would fail a future addition for the wrong reason. The observable
        # property is "an empty override behaves exactly like no override".
        baseline = Settings()

        for name in kws_fields:
            assert getattr(Settings(**{name: ""}), name) == getattr(baseline, name), (
                f"{name} is missing from _empty_kws_override_means_unset; "
                f"a ${{{name.upper()}:-}} override would not fall back"
            )

    @pytest.mark.unit
    def test_auth_origin_defaults_to_the_documented_keycloak_host(self) -> None:
        """The token endpoint is on a different host from the service API.

        Pinning the documented default keeps a single-base-URL assumption from
        being reintroduced; the two hosts are genuinely distinct.
        """
        from cyo_adventure.core.config import Settings

        settings = Settings()

        assert settings.kws_auth_origin == "https://auth.kidswebservices.com"
        assert settings.kws_auth_origin != settings.kws_api_origin


class TestKwsEnabledMethods:
    """Tests for the declared KWS verification-method set.

    The declaration is evidence rather than a preference: the parent-verified
    webhook reports no method, so the enabled set at the time of verification
    is the only bound on which method could have run, and it cannot be
    reconstructed afterwards.
    """

    @pytest.fixture(autouse=True)
    def _clear_kws_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Keep a developer's own KWS_* exports out of these assertions."""
        for name in ("KWS_ENABLED_METHODS", "KWS_ORGANIZATION_ID", "KWS_API_ORIGIN"):
            monkeypatch.delenv(name, raising=False)

    @pytest.mark.unit
    def test_defaults_to_empty(self) -> None:
        """Unconfigured means nothing to declare."""
        from cyo_adventure.core.config import Settings

        assert Settings().kws_enabled_methods == []

    @pytest.mark.unit
    def test_parsed_from_a_comma_separated_env_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Operators mirror the Control Panel, not a JSON array.

        NoDecode is what makes this work; without it pydantic-settings would
        try to json.loads the value and fail on a bare comma-separated list.
        """
        from cyo_adventure.core.config import Settings

        monkeypatch.setenv("KWS_ENABLED_METHODS", "credit_card, debit_card")

        assert Settings().kws_enabled_methods == ["credit_card", "debit_card"]

    @pytest.mark.unit
    def test_canonicalized_by_dedupe_and_sort(self) -> None:
        """Two spellings of the same declaration must compare equal."""
        from cyo_adventure.core.config import Settings

        one = Settings(kws_enabled_methods=["debit_card", "credit_card"])
        two = Settings(kws_enabled_methods=["credit_card", "debit_card", "credit_card"])

        assert one.kws_enabled_methods == two.kws_enabled_methods
        assert one.kws_enabled_methods == ["credit_card", "debit_card"]

    @pytest.mark.unit
    def test_unknown_method_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A typo is a startup error, not a silently wrong claim on a record."""
        from pydantic import ValidationError

        from cyo_adventure.core.config import Settings

        monkeypatch.setenv("KWS_ENABLED_METHODS", "credit_card,creditcard")

        with pytest.raises(ValidationError):
            Settings()

    @pytest.mark.unit
    def test_configured_kws_requires_declared_methods(self) -> None:
        """Credentials without a declaration would write unbounded records."""
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError, match="KWS_ENABLED_METHODS is empty"):
            Settings(**_KWS_CREDS)

    @pytest.mark.unit
    def test_configured_kws_with_declared_methods_accepted(self) -> None:
        """The complete, declared configuration is the one that boots."""
        from cyo_adventure.core.config import Settings

        settings = Settings(kws_enabled_methods=_KWS_METHODS, **_KWS_CREDS)

        assert settings.kws_configured is True
        assert settings.kws_enabled_methods == ["credit_card", "debit_card"]

    @pytest.mark.unit
    def test_unconfigured_kws_may_declare_nothing(self) -> None:
        """The requirement is scoped to a configured integration, not to every boot."""
        from cyo_adventure.core.config import Settings

        settings = Settings()

        assert settings.kws_configured is False
        assert settings.kws_enabled_methods == []


@pytest.mark.unit
class TestKwsEvidenceSettings:
    """The two switches that decide what a verification is allowed to prove.

    Both default to the refusing value, and both tests below assert the
    DEFAULT rather than the mechanism, because the failure these settings
    guard against is an omission: a tier that never sets the variable at all.
    """

    @pytest.fixture(autouse=True)
    def _clear_kws_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Keep a developer's own KWS_* exports out of these assertions."""
        for name in (
            "KWS_ENVIRONMENT",
            "KWS_ACCEPT_TEST_EVIDENCE",
            "KWS_VERIFICATION_REQUIRED",
        ):
            monkeypatch.delenv(name, raising=False)

    @pytest.mark.unit
    def test_test_evidence_is_refused_by_default(self) -> None:
        """An unset variable must not let sandbox verifications count."""
        from cyo_adventure.core.config import Settings

        assert Settings().kws_accept_test_evidence is False

    @pytest.mark.unit
    def test_verification_is_not_required_by_default(self) -> None:
        """The gate lands switched off, so it cannot strand an existing tier."""
        from cyo_adventure.core.config import Settings

        assert Settings().kws_verification_required is False

    @pytest.mark.unit
    def test_accepting_test_evidence_against_production_kws_is_refused(self) -> None:
        """The combination can only be a staging variable in the wrong tier.

        Keyed on ``kws_environment``, not ``environment``: staging declares
        ``ENVIRONMENT=production`` so the app-level value cannot separate the
        two tiers, and a guard written against it would be inert exactly where
        it is needed.
        """
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError, match="KWS_ACCEPT_TEST_EVIDENCE"):
            Settings(
                environment="production",
                kws_environment="production",
                kws_accept_test_evidence=True,
                database_url=_PROD_DB_URL,
                oidc_issuer="https://project.supabase.co/auth/v1",
                oidc_jwks_url=(
                    "https://project.supabase.co/auth/v1/.well-known/jwks.json"
                ),
                child_session_secret=_CHILD_SECRET,
                device_grant_secret=_DEVICE_SECRET,
                allow_mock_review=True,
                kws_enabled_methods=_KWS_METHODS,
                **_KWS_CREDS,
            )

    @pytest.mark.unit
    def test_test_evidence_is_refused_on_production_kws_from_a_staging_app(
        self,
    ) -> None:
        """The case that tells ``kws_environment`` apart from ``environment``.

        The two tests either side of this one move both fields together:
        (production, production) refuses and (staging, test) allows. A guard
        written against ``environment`` passes both of them unchanged, so
        together they assert nothing about which field is load-bearing, which
        is precisely the claim the refusal test's docstring makes.

        This pair is the mismatched one. ``environment="staging"`` with
        ``kws_environment="production"`` must still raise, and an
        ``environment``-keyed guard cannot make it, because it would read
        "staging" and wave the combination through. That is the inert-guard
        failure the docstrings warn about, and it is reachable rather than
        theoretical: staging deploys with ``ENVIRONMENT=production`` today, so
        the app-level value is not a tier discriminator on this deployment at
        all.
        """
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError, match="KWS_ACCEPT_TEST_EVIDENCE"):
            Settings(
                environment="staging",
                kws_environment="production",
                kws_accept_test_evidence=True,
                database_url=_PROD_DB_URL,
                oidc_issuer="https://project.supabase.co/auth/v1",
                oidc_jwks_url=(
                    "https://project.supabase.co/auth/v1/.well-known/jwks.json"
                ),
                child_session_secret=_CHILD_SECRET,
                device_grant_secret=_DEVICE_SECRET,
                allow_mock_review=True,
                kws_enabled_methods=_KWS_METHODS,
                **_KWS_CREDS,
            )

    @pytest.mark.unit
    def test_accepting_test_evidence_against_test_kws_is_allowed(self) -> None:
        """Staging has to be able to rely on a Test verification, or it proves nothing.

        The counterpart to the refusal above: without this case the setting
        would have no legal use at all, so this pins that the guard is scoped
        to the Production environment rather than being a blanket ban.
        """
        from cyo_adventure.core.config import Settings

        settings = Settings(
            environment="staging",
            kws_environment="test",
            kws_accept_test_evidence=True,
            database_url=_PROD_DB_URL,
            oidc_issuer="https://project.supabase.co/auth/v1",
            oidc_jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
            child_session_secret=_CHILD_SECRET,
            device_grant_secret=_DEVICE_SECRET,
            allow_mock_review=True,
            kws_enabled_methods=_KWS_METHODS,
            **_KWS_CREDS,
        )

        assert settings.kws_accept_test_evidence is True

    @pytest.mark.unit
    def test_the_real_staging_shape_is_allowed_not_just_a_staging_label(self) -> None:
        """The allow-direction case that tells ``kws_environment`` from ``environment``.

        Two of the tests above move both values together
        (production/production and staging/test), so a guard rewritten to read
        ``self.environment`` passes both: the first still raises, the second
        still allows. That makes them unable to detect the exact regression
        the docstring on ``_refuse_test_evidence_against_production_kws`` says
        it exists to prevent.

        This case covers the allow direction, and
        ``test_test_evidence_is_refused_on_production_kws_from_a_staging_app``
        covers the refuse direction. Both are needed: this one alone still
        passes against a guard narrowed to require BOTH fields to read
        ``production``, and that narrowing is the dangerous failure, since it
        would accept sandbox evidence against Production KWS.

        This is the shape staging actually deploys, and the reason the guard
        was keyed on the KWS environment in the first place: ``ENVIRONMENT`` is
        the literal string ``production`` there (see
        ``docs/operations/runbook.md``), while KWS is the sandbox. An
        ``environment``-keyed guard raises here and takes staging down; the
        correct one allows it.
        """
        from cyo_adventure.core.config import Settings

        settings = Settings(
            environment="production",
            kws_environment="test",
            kws_accept_test_evidence=True,
            database_url=_PROD_DB_URL,
            oidc_issuer="https://project.supabase.co/auth/v1",
            oidc_jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
            child_session_secret=_CHILD_SECRET,
            device_grant_secret=_DEVICE_SECRET,
            allow_mock_review=True,
            kws_enabled_methods=_KWS_METHODS,
            **_KWS_CREDS,
        )

        assert settings.kws_accept_test_evidence is True
        assert settings.environment == "production"
        assert settings.kws_environment == "test"


class TestKwsStartOverride:
    """The escape hatch that re-opens the start endpoint on an ungated tier.

    ``POST /v1/consent/kws/start`` is gated on ``kws_verification_required``,
    because that is the flag ADR-018 D1 names as the control and the endpoint
    discloses an adult's email address to Epic. Staging still has to be able
    to exercise that endpoint and its screens before the gate flips, so that
    one case gets its own setting rather than a wider reading of
    ``kws_configured``, and refusal to boot is what keeps it off production.
    """

    @pytest.fixture(autouse=True)
    def _clear_kws_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Keep a developer's own KWS_* exports out of these assertions."""
        for name in (
            "KWS_ENVIRONMENT",
            "KWS_VERIFICATION_REQUIRED",
            "KWS_ALLOW_START_WHILE_NOT_REQUIRED",
        ):
            monkeypatch.delenv(name, raising=False)

    @pytest.mark.unit
    def test_the_start_override_is_off_by_default(self) -> None:
        """An unset variable must not widen the endpoint."""
        from cyo_adventure.core.config import Settings

        assert Settings().kws_allow_start_while_not_required is False

    @pytest.mark.unit
    def test_the_start_override_is_refused_against_production_kws(self) -> None:
        """Real parents' addresses must not be disclosed for a flow that gates nothing.

        The combination has no legitimate reading against Production KWS, and
        it is exactly what a copied staging env file produces, so the process
        refuses to start rather than quietly re-opening the endpoint.
        """
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(
            ConfigurationError, match="KWS_ALLOW_START_WHILE_NOT_REQUIRED"
        ):
            Settings(
                environment="production",
                kws_environment="production",
                kws_allow_start_while_not_required=True,
                database_url=_PROD_DB_URL,
                oidc_issuer="https://project.supabase.co/auth/v1",
                oidc_jwks_url=(
                    "https://project.supabase.co/auth/v1/.well-known/jwks.json"
                ),
                child_session_secret=_CHILD_SECRET,
                device_grant_secret=_DEVICE_SECRET,
                allow_mock_review=True,
                kws_enabled_methods=_KWS_METHODS,
                **_KWS_CREDS,
            )

    @pytest.mark.unit
    def test_the_start_override_is_allowed_against_test_kws(self) -> None:
        """The staging shape must boot, and it is the shape that pins the keying.

        Deliberately the MISMATCHED pair: ``environment="production"`` with
        ``kws_environment="test"``, which is what staging actually deploys
        (``docs/operations/runbook.md``). A guard rewritten against
        ``self.environment`` would raise here and take staging down, and no
        lockstep pair of tests could tell. Without this case the setting would
        also have no legal use at all.
        """
        from cyo_adventure.core.config import Settings

        settings = Settings(
            environment="production",
            kws_environment="test",
            kws_allow_start_while_not_required=True,
            database_url=_PROD_DB_URL,
            oidc_issuer="https://project.supabase.co/auth/v1",
            oidc_jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
            child_session_secret=_CHILD_SECRET,
            device_grant_secret=_DEVICE_SECRET,
            allow_mock_review=True,
            kws_enabled_methods=_KWS_METHODS,
            **_KWS_CREDS,
        )

        assert settings.kws_allow_start_while_not_required is True
        assert settings.environment == "production"
        assert settings.kws_environment == "test"


class TestKwsStartLimits:
    """The two anti-automation bounds on ``POST /api/v1/consent/kws/start``.

    That endpoint sits OUTSIDE the admin approval gate by construction: a
    guardian must verify before an admin approves them, so the caller is an
    unapproved account. Its limits are therefore the only thing standing
    between a stolen-but-valid token and an unmetered mailer pointed at
    whatever address the IdP issued.
    """

    @pytest.fixture(autouse=True)
    def _clear_kws_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Keep a developer's own KWS_* exports out of these assertions."""
        for name in ("KWS_OPEN_ATTEMPT_MINUTES", "KWS_START_MAX_ATTEMPTS_PER_HOUR"):
            monkeypatch.delenv(name, raising=False)

    @pytest.mark.unit
    def test_the_open_attempt_window_and_hourly_cap_have_conservative_defaults(
        self,
    ) -> None:
        """Both must bound a tier that never sets either variable.

        Asserted as bounds rather than as exact equalities: the numbers are a
        judgement call and may be retuned, but a default that let a caller
        send again immediately, or that allowed a large hourly burst, would
        make the endpoint's own configuration the vulnerability.
        """
        from cyo_adventure.core.config import Settings

        defaults = Settings()

        assert 1 <= defaults.kws_open_attempt_minutes <= 60
        assert 1 <= defaults.kws_start_max_attempts_per_hour <= 5

    @pytest.mark.unit
    def test_neither_limit_can_be_configured_away(self) -> None:
        """``ge=1`` on both, so no deployment can set a limit to "unbounded".

        A zero window would let every request send, and a zero cap would
        refuse every request; both are configuration mistakes that should
        fail at startup rather than at the first parent to try to verify.
        """
        from pydantic import ValidationError

        from cyo_adventure.core.config import Settings

        with pytest.raises(ValidationError):
            Settings(kws_open_attempt_minutes=0)
        with pytest.raises(ValidationError):
            Settings(kws_start_max_attempts_per_hour=0)


class TestD1RuledGenerationDefaults:
    """The legs D1 (ruled 2026-08-23, `UW-C346`) puts on the request path.

    The ruling is a decision about which model bills a family-triggered job, so
    it belongs in a test rather than only in a comment beside the default: a
    silent edit to either string changes what every kid's story is generated
    by and what it costs, and before these tests nothing in the suite read
    either value.
    """

    @pytest.mark.unit
    def test_the_fill_leg_default_is_the_ruled_model(self) -> None:
        """The production fill leg runs DeepSeek V4 Pro."""
        from cyo_adventure.core.config import Settings

        assert Settings().openrouter_model == "deepseek/deepseek-v4-pro"

    @pytest.mark.unit
    def test_the_review_leg_default_is_the_ruled_model(self) -> None:
        """The moderation review leg runs DeepSeek V4 Flash."""
        from cyo_adventure.core.config import Settings

        assert Settings().review_openrouter_model == "deepseek/deepseek-v4-flash"

    @pytest.mark.unit
    def test_both_ruled_defaults_are_fully_priced(self) -> None:
        """A default with no price row silently costs every job as unknown.

        `generation/worker.py::_stamp_provider_accounting` writes
        `cost_complete = false` for an unpriced pair rather than inventing a
        zero, so promoting a model with no `PRICES` entry would not fail: it
        would make every subsequent cost figure a lower bound of unknown
        tightness, which is exactly the state `UW-C239` closed. D3's unit-cost
        model reads these figures, so the ruling and the price table have to
        move together.
        """
        from cyo_adventure.core.config import Settings
        from cyo_adventure.core.pricing import price_for

        defaults = Settings()
        for model in (defaults.openrouter_model, defaults.review_openrouter_model):
            price = price_for("openrouter", model)
            assert price is not None, f"{model} has no price row"
            assert price.fully_priced, f"{model} is only half priced"

    @pytest.mark.unit
    def test_the_fallback_leg_is_a_different_vendor_family(self) -> None:
        """The cascade's second leg is deliberately NOT another DeepSeek model.

        D1's table rules on the fill and review legs and says nothing about the
        fallback, which exists for failure-domain coverage rather than for
        cost or quality. Keeping a different vendor family there is what makes
        the second leg useful when the first fails for a model-specific reason
        (a slug withdrawn, a guardrail change, an endpoint outage) rather than
        for an account-wide one.
        """
        from cyo_adventure.core.config import Settings

        defaults = Settings()

        assert (
            defaults.openrouter_fallback_model.split("/")[0]
            != (defaults.openrouter_model.split("/")[0])
        )


class TestEngagementCorrelationAnalysis:
    """ADR-030 Decision 7: the kill switch and the working-tree refusal.

    The refusal test alone is not evidence. A validator that raised
    unconditionally would pass it while making the feature unusable, and one
    that never raised would pass an acceptance test alone; each pin below is
    therefore stated as a refuse/allow pair over the one property it pins.
    """

    @staticmethod
    def _settings(*, enabled: bool, output_dir: str) -> Settings:
        """Construct Settings with only the two engagement fields set.

        Args:
            enabled: The kill-switch value.
            output_dir: The configured output directory.

        Returns:
            Settings: The constructed settings.
        """
        from cyo_adventure.core.config import Settings

        return Settings(
            analysis_engagement_correlation_enabled=enabled,
            analysis_engagement_correlation_output_dir=output_dir,
        )

    @pytest.mark.unit
    def test_the_engagement_analysis_is_off_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ADR-030 is ``proposed``; the flag staying off is the mitigation."""
        from cyo_adventure.core.config import Settings

        monkeypatch.delenv("ANALYSIS_ENGAGEMENT_CORRELATION_ENABLED", raising=False)
        defaults = Settings()
        assert defaults.analysis_engagement_correlation_enabled is False
        assert defaults.analysis_engagement_correlation_output_dir == ""

    @pytest.mark.unit
    def test_an_empty_flag_value_is_off_rather_than_a_boot_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``${VAR:-}`` in a compose file must not stop the container booting.

        This project has already taken an outage from an empty env override
        reaching a constrained field.
        """
        monkeypatch.setenv("ANALYSIS_ENGAGEMENT_CORRELATION_ENABLED", "")
        from cyo_adventure.core.config import Settings

        assert Settings().analysis_engagement_correlation_enabled is False

    @pytest.mark.unit
    def test_an_empty_output_path_counts_as_unset_and_is_refused(self) -> None:
        """Empty is unset, not "the current directory", which is the repo.

        Without this pin, an operator who enabled the flag and forgot the path
        would get an artifact written into whatever directory the job was
        started from.
        """
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError):
            _ = self._settings(enabled=True, output_dir="")
        with pytest.raises(ConfigurationError):
            _ = self._settings(enabled=True, output_dir="   ")

    @pytest.mark.unit
    def test_an_output_path_inside_a_git_working_tree_is_refused(
        self, tmp_path: Path
    ) -> None:
        """The refusal half of the pair, several directories deep.

        Nested deliberately: a validator that checked only the configured
        directory for a ``.git`` entry, rather than walking every parent, would
        accept this path and pass a shallower test.
        """
        from cyo_adventure.core.exceptions import ConfigurationError

        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        target = repo / "var" / "analysis" / "reports"
        target.mkdir(parents=True)
        with pytest.raises(ConfigurationError):
            _ = self._settings(enabled=True, output_dir=str(target))

    @pytest.mark.unit
    def test_an_output_path_outside_a_git_working_tree_is_accepted(
        self, tmp_path: Path
    ) -> None:
        """The allow half of the pair.

        Cite it alongside the refusal: an unconditional raise satisfies every
        refusal test in this class and makes the job impossible to enable.
        """
        target = tmp_path / "outside" / "reports"
        target.mkdir(parents=True)
        constructed = self._settings(enabled=True, output_dir=str(target))
        assert constructed.analysis_engagement_correlation_enabled is True

    @pytest.mark.unit
    def test_a_worktree_marked_by_a_git_file_is_refused(self, tmp_path: Path) -> None:
        """This project's worktrees mark themselves with a ``.git`` FILE.

        ``.worktrees/<slug>/.git`` is a file containing a ``gitdir:`` pointer, so
        an ``is_dir()`` check would accept every path inside every worktree in
        this repository, which is where a concurrent session works.
        """
        from cyo_adventure.core.exceptions import ConfigurationError

        worktree = tmp_path / "worktree"
        target = worktree / "reports"
        target.mkdir(parents=True)
        _ = (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
        with pytest.raises(ConfigurationError):
            _ = self._settings(enabled=True, output_dir=str(target))

    @pytest.mark.unit
    def test_a_traversal_path_that_resolves_into_a_working_tree_is_refused(
        self, tmp_path: Path
    ) -> None:
        """``Path.resolve()`` before walking parents, pinned by a path that needs it.

        ``<tmp>/outside/../repo/reports`` has no ``.git`` in any of its literal
        parents, because those are ``<tmp>/outside/..``, ``<tmp>/outside`` and
        ``<tmp>``. It is inside the working tree all the same.
        """
        from cyo_adventure.core.exceptions import ConfigurationError

        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        (repo / "reports").mkdir()
        (tmp_path / "outside").mkdir()
        traversal = tmp_path / "outside" / ".." / "repo" / "reports"
        with pytest.raises(ConfigurationError):
            _ = self._settings(enabled=True, output_dir=str(traversal))

    @pytest.mark.unit
    def test_a_symlink_into_a_working_tree_is_refused(self, tmp_path: Path) -> None:
        """Resolution has to follow the link, not just normalise the text."""
        from cyo_adventure.core.exceptions import ConfigurationError

        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        (repo / "reports").mkdir()
        link = tmp_path / "link"
        link.symlink_to(repo / "reports", target_is_directory=True)
        with pytest.raises(ConfigurationError):
            _ = self._settings(enabled=True, output_dir=str(link))

    @pytest.mark.unit
    def test_this_repository_is_itself_a_refused_destination(self) -> None:
        """The concrete case the control exists for.

        The repository is public and a push is not retractable, so an aggregate
        over five families of real children stays reachable in history after any
        later deletion.
        """
        from pathlib import Path as _Path

        from cyo_adventure.core.exceptions import ConfigurationError

        repo_root = _Path(__file__).resolve().parents[2]
        with pytest.raises(ConfigurationError):
            _ = self._settings(enabled=True, output_dir=str(repo_root / "artifacts"))

    @pytest.mark.unit
    def test_the_path_is_only_checked_when_the_job_is_enabled(
        self, tmp_path: Path
    ) -> None:
        """Off must stay constructible everywhere, or every dev box fails to boot.

        The flag is off in every environment today, so a validator that ran
        unconditionally would refuse to construct Settings in this repository.
        """
        repo = tmp_path / "repo"
        (repo / ".git").mkdir(parents=True)
        constructed = self._settings(enabled=False, output_dir=str(repo / "reports"))
        assert constructed.analysis_engagement_correlation_enabled is False

    @pytest.mark.unit
    def test_the_refusal_message_names_no_path_component_it_did_not_receive(
        self,
    ) -> None:
        """The error is read by an operator and may be pasted into an issue.

        It may restate what was configured; it must not add anything else.
        """
        from cyo_adventure.core.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError) as caught:
            _ = self._settings(enabled=True, output_dir="")
        assert "ANALYSIS_ENGAGEMENT_CORRELATION_OUTPUT_DIR" in str(caught.value)
