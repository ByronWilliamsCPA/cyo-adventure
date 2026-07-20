"""Unit tests for the onboarding identity dependency (P6-03).

``require_onboarding_identity`` is the only auth seam that accepts a verified
token whose subject has no ``User`` row yet. These tests cover its local-trust
branch and its refusal of a child session token, without a database.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import jwt
import pytest

from cyo_adventure.api import deps
from cyo_adventure.core.child_session import CHILD_SESSION_AUDIENCE
from cyo_adventure.core.exceptions import AuthenticationError, AuthorizationError

if TYPE_CHECKING:
    from fastapi import Request

pytestmark = [pytest.mark.unit, pytest.mark.security]

# A minimal Request stand-in: require_onboarding_identity reads only
# request.client.host (via OnboardingIdentity.client_ip), which these tests
# do not assert on, so a real ASGI scope is unnecessary here.
_FAKE_REQUEST = cast("Request", SimpleNamespace(client=None))


@pytest.mark.asyncio
async def test_local_trusts_token_as_subject_with_no_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In local the bearer token is the subject and carries no email claim."""
    monkeypatch.setattr(deps.settings, "environment", "local")
    identity = await deps.require_onboarding_identity(
        _FAKE_REQUEST, "Bearer new-guardian-sub"
    )
    assert identity.subject == "new-guardian-sub"
    assert identity.email is None


@pytest.mark.asyncio
async def test_client_ip_is_captured_when_request_client_is_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real client host is threaded through onto OnboardingIdentity.client_ip.

    Phase 2 / ADR-018 D1: consent_ip is sourced from this field, so the
    request.client.host is not None branch (the counterpart to
    _FAKE_REQUEST's client=None case above) must be independently exercised.
    """
    monkeypatch.setattr(deps.settings, "environment", "local")
    request_with_client = cast(
        "Request", SimpleNamespace(client=SimpleNamespace(host="203.0.113.7"))
    )
    identity = await deps.require_onboarding_identity(
        request_with_client, "Bearer new-guardian-sub"
    )
    assert identity.client_ip == "203.0.113.7"


@pytest.mark.asyncio
async def test_missing_bearer_raises_authentication_error() -> None:
    """A missing Authorization header is a 401, not a silent anonymous onboard."""
    with pytest.raises(AuthenticationError):
        await deps.require_onboarding_identity(_FAKE_REQUEST, None)


@pytest.mark.asyncio
async def test_child_session_token_cannot_onboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A token carrying the child audience is refused before any provisioning.

    A child session is a reading credential, never an account-creation one, so
    it must not provision a guardian family. The refusal keys off the routing
    audience and happens regardless of signature validity.
    """
    monkeypatch.setattr(deps.settings, "environment", "local")
    # #EDGE: security: unverified_audience reads only the aud claim, so this
    # HS256-signed token (throwaway secret; the signature is never checked)
    # carrying the child audience proves the refusal fires ahead of any
    # verification.
    # #VERIFY: the assertion below expects AuthorizationError (the refusal),
    # not a signature/verification failure, confirming the child-audience
    # check runs before any verification path.
    child_like = jwt.encode(
        {"aud": CHILD_SESSION_AUDIENCE, "sub": "child:abc"},
        "irrelevant-secret-padded-to-thirty-two-plus-bytes",
        algorithm="HS256",
    )
    with pytest.raises(AuthorizationError):
        await deps.require_onboarding_identity(_FAKE_REQUEST, f"Bearer {child_like}")
