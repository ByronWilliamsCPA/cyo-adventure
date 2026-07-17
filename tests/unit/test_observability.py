"""Tests for cyo_adventure.core.observability.

Covers init_sentry's no-op path (no DSN configured), the DSN-configured path
(sentry_sdk.init called with the right kwargs), the hardcoded send_default_pii
False, the environment tag, and _resolve_release's version-lookup fallback.

sentry_sdk.init is always mocked: these are unit tests and must never make a
real network call to Sentry's ingest endpoint (tests/CLAUDE.md test-isolation
rule).
"""

from __future__ import annotations

from importlib import metadata
from unittest.mock import patch

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.core.observability import init_sentry


def _settings(**overrides: object) -> Settings:
    """Build a Settings instance for observability tests.

    Uses the real Settings class (not a Mock(spec=...)): tests/CLAUDE.md
    warns that patching a pydantic model instance as `spec=` trips a
    deprecated-property escalation under this project's `filterwarnings =
    ["error"]`; constructing a real instance sidesteps that entirely and
    exercises the actual field validation.

    Args:
        **overrides: Field overrides passed to Settings().

    Returns:
        Settings: A Settings instance with environment="local" (so none of
            the outside-local fail-fast validators fire) unless overridden.
    """
    defaults: dict[str, object] = {"environment": "local"}
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# No-op path
# ---------------------------------------------------------------------------


class TestInitSentryNoOp:
    """init_sentry must be a true no-op when sentry_dsn is unset."""

    @pytest.mark.unit
    def test_init_sentry_does_not_call_sdk_init_without_dsn(self) -> None:
        """No DSN configured: sentry_sdk.init is never called."""
        settings = _settings(sentry_dsn=None)

        with patch("cyo_adventure.core.observability.sentry_sdk.init") as mock_init:
            init_sentry(settings)

        mock_init.assert_not_called()

    @pytest.mark.unit
    def test_init_sentry_no_dsn_does_not_raise(self) -> None:
        """Calling init_sentry with no DSN is safe to do unconditionally."""
        settings = _settings(sentry_dsn=None)

        with patch("cyo_adventure.core.observability.sentry_sdk.init"):
            init_sentry(settings)  # should not raise


# ---------------------------------------------------------------------------
# DSN-configured path
# ---------------------------------------------------------------------------


class TestInitSentryWithDsn:
    """init_sentry initializes the SDK exactly once when a DSN is configured."""

    @pytest.mark.unit
    def test_init_sentry_calls_sdk_init_with_dsn(self) -> None:
        """A configured DSN reaches sentry_sdk.init as the dsn kwarg."""
        dsn = "https://examplePublicKey@o0.ingest.sentry.io/0"
        settings = _settings(sentry_dsn=dsn)

        with patch("cyo_adventure.core.observability.sentry_sdk.init") as mock_init:
            init_sentry(settings)

        mock_init.assert_called_once()
        assert mock_init.call_args.kwargs["dsn"] == dsn

    @pytest.mark.unit
    def test_init_sentry_sets_environment_tag(self) -> None:
        """The environment kwarg mirrors settings.environment."""
        settings = _settings(
            sentry_dsn="https://examplePublicKey@o0.ingest.sentry.io/0",
            environment="staging",
            database_url="postgresql+asyncpg://user:pw@staging-db:5432/cyo_adventure",
            oidc_issuer="https://issuer.example.com",
            oidc_jwks_url="https://issuer.example.com/jwks.json",
            child_session_secret="a" * 32,
            device_grant_secret="b" * 32,
        )

        with patch("cyo_adventure.core.observability.sentry_sdk.init") as mock_init:
            init_sentry(settings)

        assert mock_init.call_args.kwargs["environment"] == "staging"

    @pytest.mark.unit
    def test_init_sentry_passes_configured_traces_sample_rate(self) -> None:
        """traces_sample_rate is forwarded from settings, not hardcoded."""
        settings = _settings(
            sentry_dsn="https://examplePublicKey@o0.ingest.sentry.io/0",
            sentry_traces_sample_rate=0.42,
        )

        with patch("cyo_adventure.core.observability.sentry_sdk.init") as mock_init:
            init_sentry(settings)

        assert mock_init.call_args.kwargs["traces_sample_rate"] == pytest.approx(0.42)

    @pytest.mark.unit
    def test_init_sentry_default_traces_sample_rate_is_low(self) -> None:
        """The default sample rate is low (this is error tracking, not full APM)."""
        settings = _settings(
            sentry_dsn="https://examplePublicKey@o0.ingest.sentry.io/0"
        )

        with patch("cyo_adventure.core.observability.sentry_sdk.init") as mock_init:
            init_sentry(settings)

        assert mock_init.call_args.kwargs["traces_sample_rate"] == pytest.approx(0.1)

    @pytest.mark.unit
    def test_init_sentry_includes_fastapi_and_starlette_integrations(self) -> None:
        """The FastAPI/Starlette integrations are passed so requests are captured."""
        settings = _settings(
            sentry_dsn="https://examplePublicKey@o0.ingest.sentry.io/0"
        )

        with patch("cyo_adventure.core.observability.sentry_sdk.init") as mock_init:
            init_sentry(settings)

        integrations = mock_init.call_args.kwargs["integrations"]
        integration_types = {type(i).__name__ for i in integrations}
        assert integration_types == {"StarletteIntegration", "FastApiIntegration"}


# ---------------------------------------------------------------------------
# PII: must always be off (#CRITICAL: security)
# ---------------------------------------------------------------------------


class TestInitSentryDisablesPii:
    """send_default_pii must always be False; this is a kids' app.

    #VERIFY (mirrors core/observability.py's module docstring): this is the
    test that would fail if a future change ever let send_default_pii
    default to True or become settings-driven.
    """

    @pytest.mark.unit
    def test_init_sentry_never_sends_pii(self) -> None:
        """send_default_pii=False is passed on every sentry_sdk.init call."""
        settings = _settings(
            sentry_dsn="https://examplePublicKey@o0.ingest.sentry.io/0"
        )

        with patch("cyo_adventure.core.observability.sentry_sdk.init") as mock_init:
            init_sentry(settings)

        assert mock_init.call_args.kwargs["send_default_pii"] is False


# ---------------------------------------------------------------------------
# _resolve_release
# ---------------------------------------------------------------------------


class TestResolveRelease:
    """Tests for the release-tag resolution helper."""

    @pytest.mark.unit
    def test_resolve_release_returns_resolved_version(self) -> None:
        """A resolvable package version is forwarded as the release kwarg."""
        from cyo_adventure.core.observability import _resolve_release

        with patch(
            "cyo_adventure.core.observability.metadata.version",
            return_value="0.7.0",
        ):
            assert _resolve_release() == "0.7.0"

    @pytest.mark.unit
    def test_resolve_release_returns_none_when_package_not_found(self) -> None:
        """An unresolvable version (source checkout) yields None, not a raise."""
        from cyo_adventure.core.observability import _resolve_release

        with patch(
            "cyo_adventure.core.observability.metadata.version",
            side_effect=metadata.PackageNotFoundError("cyo-adventure"),
        ):
            assert _resolve_release() is None

    @pytest.mark.unit
    def test_init_sentry_forwards_resolved_release(self) -> None:
        """init_sentry passes _resolve_release()'s value through as release."""
        settings = _settings(
            sentry_dsn="https://examplePublicKey@o0.ingest.sentry.io/0"
        )

        with (
            patch("cyo_adventure.core.observability.sentry_sdk.init") as mock_init,
            patch(
                "cyo_adventure.core.observability._resolve_release",
                return_value="1.2.3",
            ),
        ):
            init_sentry(settings)

        assert mock_init.call_args.kwargs["release"] == "1.2.3"
