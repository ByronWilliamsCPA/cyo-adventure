"""Sentry error-tracking initialization for the backend.

``init_sentry()`` is a documented no-op unless a DSN is configured
(``Settings.sentry_dsn``, read from the unprefixed ``SENTRY_DSN`` env var per
``.env.example``). Call it once from ``app.py::create_app()``, before the
FastAPI app is constructed, so the FastAPI/Starlette integration installs its
instrumentation before any route is registered. This module intentionally
does not touch structlog/``utils/logging.py`` configuration: Sentry's SDK
hooks the stdlib ``logging`` module (breadcrumbs) independently of the
structlog processor chain, so the two coexist without either fighting the
other's handlers.

#CRITICAL: security: this is a kids' reading app. Sentry must never receive
personally identifying data (child names, guardian emails, request/response
bodies, raw IP addresses). ``send_default_pii`` is hardcoded ``False`` below
and is deliberately not exposed as a ``Settings`` field, so no future config
change can silently turn it on.
#VERIFY: tests/unit/test_observability.py::test_init_sentry_disables_pii
asserts every ``sentry_sdk.init`` call passes ``send_default_pii=False``.
"""

from __future__ import annotations

from importlib import metadata
from typing import TYPE_CHECKING

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from cyo_adventure.core.config import Settings

logger = get_logger(__name__)

# Matches [project.name] in pyproject.toml; used only to resolve a release
# tag, never logged or sent anywhere but the Sentry init call itself.
_PACKAGE_NAME = "cyo-adventure"


def _resolve_release() -> str | None:
    """Best-effort package version for Sentry's release tag.

    #ASSUME: external resources: ``importlib.metadata.version`` raises
    ``PackageNotFoundError`` when running from a source checkout with no
    installed distribution metadata (some CI/dev invocations do this);
    Sentry then simply gets no release tag rather than the process failing
    to start over an observability nicety.
    #VERIFY: tests/unit/test_observability.py covers both the resolved and
    unresolved-version paths.

    Returns:
        str | None: The installed package version, or None if it cannot be
            resolved.
    """
    try:
        return metadata.version(_PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return None


def init_sentry(settings: Settings) -> None:
    """Initialize Sentry error tracking if a DSN is configured.

    A documented no-op when ``settings.sentry_dsn`` is unset (local dev, CI,
    and any deployment that has not opted in): ``sentry_sdk.init()`` is never
    called in that case, so this function is safe to call unconditionally
    from ``create_app()`` regardless of environment.

    Args:
        settings: The application ``Settings`` instance (``core/config.py``).
    """
    if not settings.sentry_dsn:
        logger.info("sentry_disabled", reason="no_dsn_configured")
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=_resolve_release(),
        traces_sample_rate=settings.sentry_traces_sample_rate,
        # #CRITICAL: security: never send PII (child names/emails, request or
        # response bodies, raw client IPs) from a kids' app to a third-party
        # error tracker. This must stay hardcoded False; see the module
        # docstring #VERIFY note.
        send_default_pii=False,
        integrations=[StarletteIntegration(), FastApiIntegration()],
    )
    logger.info(
        "sentry_enabled",
        environment=settings.environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
    )
