"""Unit tests for backend-signed child session tokens (G1 / P6-04).

Covers the mint/verify round-trip, every rejection path the trust model
promises (expired, tampered, wrong secret, wrong issuer, wrong audience,
algorithm confusion in both directions, and missing id claims), the
``require_principal`` routing branch, and the config fail-fast validator.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr

from cyo_adventure.api import deps
from cyo_adventure.core import child_session
from cyo_adventure.core.child_session import (
    CHILD_SESSION_AUDIENCE,
    CHILD_SESSION_ISSUER,
    ChildSessionClaims,
    mint_child_session_token,
    unverified_audience,
    verify_child_session_token,
)
from cyo_adventure.core.config import Settings
from cyo_adventure.core.exceptions import AuthenticationError, ConfigurationError

pytestmark = [pytest.mark.security]

# A >=32-byte secret: PyJWT warns (InsecureKeyLengthWarning) on shorter HMAC
# keys and the suite's filterwarnings=error would escalate that to a failure.
_SECRET = "unit-test-child-session-secret-0123456789abcdef"
_OTHER_SECRET = "unit-test-OTHER-child-session-secret-0123456789ab"

_PROFILE_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
_FAMILY_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
_USER_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")

_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def _configure_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the child-session module's settings at a test signing secret."""
    monkeypatch.setattr(
        child_session.settings, "child_session_secret", SecretStr(_SECRET)
    )
    monkeypatch.setattr(child_session.settings, "child_session_ttl_seconds", 43_200)


def _mint(now: datetime | None = None) -> str:
    """Mint a token for the fixed test ids, returning only the compact JWT."""
    token, _ = mint_child_session_token(
        profile_id=_PROFILE_ID,
        family_id=_FAMILY_ID,
        user_id=_USER_ID,
        now=now,
    )
    return token


def _claims(**overrides: Any) -> dict[str, Any]:
    """Build a valid child claim set with keyword overrides applied on top."""
    now = datetime.now(UTC)
    base: dict[str, Any] = {
        "sub": f"child:{_PROFILE_ID}",
        "role": "child",
        "profile_id": str(_PROFILE_ID),
        "family_id": str(_FAMILY_ID),
        "user_id": str(_USER_ID),
        "iss": CHILD_SESSION_ISSUER,
        "aud": CHILD_SESSION_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    base.update(overrides)
    return base


def _encode(
    claims: dict[str, Any], *, secret: str = _SECRET, alg: str = "HS256"
) -> str:
    """Encode a claim set into a compact JWT for the rejection-path tests."""
    key: object = _RSA_KEY if alg == "RS256" else secret
    return jwt.encode(claims, key, algorithm=alg)  # pyright: ignore[reportArgumentType]


# ---------------------------------------------------------------------------
# mint / verify round-trip
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_mint_and_verify_roundtrip_yields_claims() -> None:
    """A freshly minted token verifies back to its embedded ids."""
    token, expires_at = mint_child_session_token(
        profile_id=_PROFILE_ID, family_id=_FAMILY_ID, user_id=_USER_ID
    )
    claims = verify_child_session_token(token)
    assert claims == ChildSessionClaims(
        subject=f"child:{_PROFILE_ID}",
        profile_id=_PROFILE_ID,
        family_id=_FAMILY_ID,
        user_id=_USER_ID,
    )
    assert expires_at > datetime.now(UTC)


@pytest.mark.unit
def test_mint_expiry_reflects_configured_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """expires_at is issue-time plus the configured TTL (12h default here)."""
    monkeypatch.setattr(child_session.settings, "child_session_ttl_seconds", 3_600)
    issued = datetime(2026, 1, 1, tzinfo=UTC)
    _token, expires_at = mint_child_session_token(
        profile_id=_PROFILE_ID, family_id=_FAMILY_ID, user_id=_USER_ID, now=issued
    )
    assert expires_at == issued + timedelta(seconds=3_600)


# ---------------------------------------------------------------------------
# rejection paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_expired_token_rejected() -> None:
    """A token whose exp is in the past fails verification."""
    stale = datetime.now(UTC) - timedelta(days=1)
    with pytest.raises(AuthenticationError):
        verify_child_session_token(_mint(now=stale))


@pytest.mark.unit
def test_tampered_signature_rejected() -> None:
    """Flipping a byte in the signature segment invalidates the token."""
    header, payload, signature = _mint().split(".")
    tampered = ("A" if signature[0] != "A" else "B") + signature[1:]
    with pytest.raises(AuthenticationError):
        verify_child_session_token(f"{header}.{payload}.{tampered}")


@pytest.mark.unit
def test_wrong_secret_rejected() -> None:
    """A token signed with a different secret fails verification."""
    forged = _encode(_claims(), secret=_OTHER_SECRET)
    with pytest.raises(AuthenticationError):
        verify_child_session_token(forged)


@pytest.mark.unit
def test_wrong_audience_rejected() -> None:
    """A correctly-signed token for another audience fails verification."""
    token = _encode(_claims(aud="authenticated"))
    with pytest.raises(AuthenticationError):
        verify_child_session_token(token)


@pytest.mark.unit
def test_wrong_issuer_rejected() -> None:
    """A correctly-signed token with the wrong issuer fails verification."""
    token = _encode(_claims(iss="https://attacker.example/auth/v1"))
    with pytest.raises(AuthenticationError):
        verify_child_session_token(token)


@pytest.mark.unit
def test_rs256_token_in_child_path_rejected() -> None:
    """Algorithm confusion (1/2): an RS256 token cannot verify under HS256.

    The child verifier pins ``algorithms=["HS256"]``, so a token signed with
    an asymmetric key and carrying the child audience is rejected before any
    signature comparison, defeating an RS256->HS256 confusion attempt.
    """
    token = _encode(_claims(), alg="RS256")
    with pytest.raises(AuthenticationError):
        verify_child_session_token(token)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_child_token_rejected_by_guardian_oidc_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Algorithm confusion (2/2): a child HS256 token fails the OIDC verifier.

    The guardian path pins RS256/ES256 and the Supabase audience, so an HS256
    child token routed there (were the audience routing ever bypassed) is
    rejected on both algorithm and audience.
    """

    class _FakeSigningKey:
        key: object = _RSA_KEY.public_key()

    class _FakeJwksClient:
        def get_signing_key_from_jwt(self, _token: str) -> _FakeSigningKey:
            return _FakeSigningKey()

    monkeypatch.setattr(deps.settings, "oidc_issuer", "https://example.supabase.co")
    monkeypatch.setattr(deps.settings, "oidc_audience", "authenticated")
    monkeypatch.setattr(deps.settings, "oidc_jwks_url", "https://example/jwks")
    monkeypatch.setattr(deps, "_jwks_client", _FakeJwksClient)
    with pytest.raises(AuthenticationError):
        await deps._verify_oidc_jwt(_mint())


def _b64url(data: bytes) -> str:
    """Base64url-encode without padding, as JWT segments require."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@pytest.mark.unit
def test_algorithm_none_rejected() -> None:
    """An unsigned alg=none token is rejected by the HS256 allowlist."""
    payload_claims = {
        k: (v.timestamp() if isinstance(v, datetime) else v)
        for k, v in _claims().items()
    }
    header = _b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps(payload_claims).encode())
    token = f"{header}.{payload}."
    with pytest.raises(AuthenticationError):
        verify_child_session_token(token)


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["profile_id", "family_id", "user_id"])
def test_missing_id_claim_rejected(missing: str) -> None:
    """A validly-signed token missing an id claim is rejected."""
    claims = _claims()
    del claims[missing]
    with pytest.raises(AuthenticationError):
        verify_child_session_token(_encode(claims))


@pytest.mark.unit
def test_malformed_uuid_claim_rejected() -> None:
    """A non-UUID profile_id claim is rejected even when validly signed."""
    with pytest.raises(AuthenticationError):
        verify_child_session_token(_encode(_claims(profile_id="not-a-uuid")))


@pytest.mark.unit
def test_non_child_role_claim_rejected() -> None:
    """A validly-signed token carrying a non-child role is refused."""
    with pytest.raises(AuthenticationError):
        verify_child_session_token(_encode(_claims(role="guardian")))


@pytest.mark.unit
def test_mint_without_secret_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Minting with no configured secret raises ConfigurationError."""
    monkeypatch.setattr(child_session.settings, "child_session_secret", None)
    with pytest.raises(ConfigurationError):
        mint_child_session_token(
            profile_id=_PROFILE_ID, family_id=_FAMILY_ID, user_id=_USER_ID
        )


# ---------------------------------------------------------------------------
# routing helper + require_principal branch
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unverified_audience_reads_child_token() -> None:
    """unverified_audience returns the child audience for a minted token."""
    assert unverified_audience(_mint()) == CHILD_SESSION_AUDIENCE


@pytest.mark.unit
@pytest.mark.parametrize("opaque", ["guardian-a", "child-a", "not-a-jwt"])
def test_unverified_audience_none_for_opaque_token(opaque: str) -> None:
    """A non-JWT opaque dev-stub token yields no audience (guardian branch)."""
    assert unverified_audience(opaque) is None


class _ExplodingSession:
    """A session double whose query methods must never be called.

    The child branch of require_principal is DB-free; if it ever queried, this
    surfaces the regression instead of silently passing.
    """

    async def scalar(self, _stmt: object) -> object:
        msg = "child branch must not touch the database"
        raise AssertionError(msg)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_require_principal_child_branch_scopes_to_single_profile() -> None:
    """A child token resolves to a CHILD principal scoped to one profile."""
    principal = await deps.require_principal(
        _ExplodingSession(),  # pyright: ignore[reportArgumentType]
        authorization=f"Bearer {_mint()}",
    )
    assert principal.role is deps.Role.CHILD
    assert principal.profile_ids == frozenset({_PROFILE_ID})
    assert principal.family_id == _FAMILY_ID
    assert principal.user_id == _USER_ID
    assert principal.subject == f"child:{_PROFILE_ID}"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_require_principal_rejects_forged_child_token() -> None:
    """A child-audience token signed with the wrong secret is rejected."""
    forged = _encode(_claims(), secret=_OTHER_SECRET)
    with pytest.raises(AuthenticationError):
        await deps.require_principal(
            _ExplodingSession(),  # pyright: ignore[reportArgumentType]
            authorization=f"Bearer {forged}",
        )


# ---------------------------------------------------------------------------
# config fail-fast validator
# ---------------------------------------------------------------------------


def _base_nonlocal_kwargs() -> dict[str, Any]:
    """Settings kwargs that satisfy the other non-local validators."""
    return {
        "environment": "staging",
        "database_url": "postgresql+asyncpg://u:p@db.example/app",
        "oidc_issuer": "https://ref.supabase.co/auth/v1",
        "oidc_jwks_url": "https://ref.supabase.co/auth/v1/jwks",
    }


@pytest.mark.unit
def test_missing_child_secret_outside_local_rejected() -> None:
    """A non-local Settings with no child-session secret refuses to construct."""
    with pytest.raises(ConfigurationError, match="CHILD_SESSION_SECRET"):
        Settings(**_base_nonlocal_kwargs(), child_session_secret=None)


@pytest.mark.unit
def test_child_secret_present_outside_local_ok() -> None:
    """A non-local Settings with the secret set constructs successfully."""
    settings = Settings(
        **_base_nonlocal_kwargs(), child_session_secret=SecretStr(_SECRET)
    )
    assert settings.child_session_secret is not None
    assert settings.child_session_ttl_seconds == 43_200


@pytest.mark.unit
def test_local_needs_no_child_secret() -> None:
    """Local development constructs with no child-session secret."""
    settings = Settings(environment="local")
    assert settings.child_session_secret is None
