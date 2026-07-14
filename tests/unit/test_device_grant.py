"""Unit tests for backend-signed device grant tokens (ADR-014 phase 1).

Covers the mint/verify round-trip, every rejection path the trust model
promises (expired, tampered, wrong secret, wrong issuer, wrong audience,
algorithm confusion, and missing id claims), the ``require_principal``
routing branch (including the refuse-only guard on
``require_onboarding_identity``), and the config fail-fast validator.
Mirrors ``test_child_session.py``.
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
from cyo_adventure.core import device_grant
from cyo_adventure.core.child_session import unverified_audience
from cyo_adventure.core.config import Settings
from cyo_adventure.core.device_grant import (
    DEVICE_GRANT_AUDIENCE,
    DEVICE_GRANT_ISSUER,
    DeviceGrantClaims,
    mint_device_grant_token,
    verify_device_grant_token,
)
from cyo_adventure.core.exceptions import AuthenticationError, AuthorizationError
from cyo_adventure.core.exceptions import ConfigurationError as ConfigError

pytestmark = [pytest.mark.security]

# A >=32-byte secret: PyJWT warns (InsecureKeyLengthWarning) on shorter HMAC
# keys and the suite's filterwarnings=error would escalate that to a failure.
_SECRET = "unit-test-device-grant-secret-0123456789abcdef"
_OTHER_SECRET = "unit-test-OTHER-device-grant-secret-0123456789ab"

_FAMILY_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
_AUTHORIZED_BY = uuid.UUID("55555555-5555-4555-8555-555555555555")
_JTI = uuid.UUID("66666666-6666-4666-8666-666666666666")

_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def _configure_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the device-grant module's settings at a test signing secret."""
    monkeypatch.setattr(
        device_grant.settings, "device_grant_secret", SecretStr(_SECRET)
    )
    monkeypatch.setattr(device_grant.settings, "device_grant_ttl_seconds", 7_776_000)


def _mint(now: datetime | None = None) -> str:
    """Mint a token for the fixed test ids, returning only the compact JWT."""
    token, _ = mint_device_grant_token(
        family_id=_FAMILY_ID,
        authorized_by=_AUTHORIZED_BY,
        jti=_JTI,
        now=now,
    )
    return token


def _claims(**overrides: Any) -> dict[str, Any]:
    """Build a valid device-grant claim set with keyword overrides applied on top."""
    now = datetime.now(UTC)
    base: dict[str, Any] = {
        "sub": f"device:{_JTI}",
        "role": "device",
        "family_id": str(_FAMILY_ID),
        "authorized_by": str(_AUTHORIZED_BY),
        "jti": str(_JTI),
        "iss": DEVICE_GRANT_ISSUER,
        "aud": DEVICE_GRANT_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(days=90),
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
    token, expires_at = mint_device_grant_token(
        family_id=_FAMILY_ID, authorized_by=_AUTHORIZED_BY, jti=_JTI
    )
    claims = verify_device_grant_token(token)
    assert claims == DeviceGrantClaims(
        subject=f"device:{_JTI}",
        family_id=_FAMILY_ID,
        authorized_by=_AUTHORIZED_BY,
        jti=_JTI,
    )
    assert expires_at > datetime.now(UTC)


@pytest.mark.unit
def test_mint_expiry_reflects_configured_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """expires_at is issue-time plus the configured TTL (90d default here)."""
    monkeypatch.setattr(device_grant.settings, "device_grant_ttl_seconds", 3_600)
    issued = datetime(2026, 1, 1, tzinfo=UTC)
    _token, expires_at = mint_device_grant_token(
        family_id=_FAMILY_ID, authorized_by=_AUTHORIZED_BY, jti=_JTI, now=issued
    )
    assert expires_at == issued + timedelta(seconds=3_600)


# ---------------------------------------------------------------------------
# rejection paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_expired_token_rejected() -> None:
    """A token whose exp is in the past fails verification.

    The fixture's TTL is 90 days, so ``now`` must be pushed back further
    than that (100 days) for the minted token's ``exp`` to already be in
    the past; a 1-day offset (sufficient for the 12h child-session TTL)
    would still mint a token expiring ~89 days from now.
    """
    stale = datetime.now(UTC) - timedelta(days=100)
    with pytest.raises(AuthenticationError):
        verify_device_grant_token(_mint(now=stale))


@pytest.mark.unit
def test_tampered_signature_rejected() -> None:
    """Flipping a byte in the signature segment invalidates the token."""
    header, payload, signature = _mint().split(".")
    tampered = ("A" if signature[0] != "A" else "B") + signature[1:]
    with pytest.raises(AuthenticationError):
        verify_device_grant_token(f"{header}.{payload}.{tampered}")


@pytest.mark.unit
def test_wrong_secret_rejected() -> None:
    """A token signed with a different secret fails verification."""
    forged = _encode(_claims(), secret=_OTHER_SECRET)
    with pytest.raises(AuthenticationError):
        verify_device_grant_token(forged)


@pytest.mark.unit
def test_wrong_audience_rejected() -> None:
    """A correctly-signed token for another audience fails verification."""
    token = _encode(_claims(aud="cyo-child-session"))
    with pytest.raises(AuthenticationError):
        verify_device_grant_token(token)


@pytest.mark.unit
def test_wrong_issuer_rejected() -> None:
    """A correctly-signed token with the wrong issuer fails verification."""
    token = _encode(_claims(iss="https://attacker.example/auth/v1"))
    with pytest.raises(AuthenticationError):
        verify_device_grant_token(token)


@pytest.mark.unit
def test_rs256_token_in_device_path_rejected() -> None:
    """Algorithm confusion: an RS256 token cannot verify under HS256.

    The device-grant verifier pins ``algorithms=["HS256"]``, so a token
    signed with an asymmetric key and carrying the device audience is
    rejected before any signature comparison, defeating an RS256->HS256
    confusion attempt.
    """
    token = _encode(_claims(), alg="RS256")
    with pytest.raises(AuthenticationError):
        verify_device_grant_token(token)


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
        verify_device_grant_token(token)


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["family_id", "authorized_by", "jti"])
def test_missing_id_claim_rejected(missing: str) -> None:
    """A validly-signed token missing an id claim is rejected."""
    claims = _claims()
    del claims[missing]
    with pytest.raises(AuthenticationError):
        verify_device_grant_token(_encode(claims))


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["exp", "iat", "sub"])
def test_missing_required_standard_claim_rejected(missing: str) -> None:
    """A validly-signed token missing a required standard claim is rejected."""
    claims = _claims()
    del claims[missing]
    with pytest.raises(AuthenticationError):
        verify_device_grant_token(_encode(claims))


@pytest.mark.unit
def test_malformed_uuid_claim_rejected() -> None:
    """A non-UUID family_id claim is rejected even when validly signed."""
    with pytest.raises(AuthenticationError):
        verify_device_grant_token(_encode(_claims(family_id="not-a-uuid")))


@pytest.mark.unit
def test_non_device_role_claim_rejected() -> None:
    """A validly-signed token carrying a non-device role is refused."""
    with pytest.raises(AuthenticationError):
        verify_device_grant_token(_encode(_claims(role="guardian")))


@pytest.mark.unit
def test_mint_without_secret_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Minting with no configured secret raises ConfigurationError."""
    monkeypatch.setattr(device_grant.settings, "device_grant_secret", None)
    with pytest.raises(ConfigError):
        mint_device_grant_token(
            family_id=_FAMILY_ID, authorized_by=_AUTHORIZED_BY, jti=_JTI
        )


# ---------------------------------------------------------------------------
# routing helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unverified_audience_reads_device_token() -> None:
    """unverified_audience (shared with child_session) reads the device aud."""
    assert unverified_audience(_mint()) == DEVICE_GRANT_AUDIENCE


# ---------------------------------------------------------------------------
# require_principal branch
# ---------------------------------------------------------------------------


class _ExplodingSession:
    """A session double whose query methods must never be called.

    The device branch of require_principal is DB-free; if it ever queried,
    this surfaces the regression instead of silently passing.
    """

    async def scalar(self, _stmt: object) -> object:
        msg = "device branch must not touch the database"
        raise AssertionError(msg)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_require_principal_device_branch_builds_device_principal() -> None:
    """A device grant token resolves to a DEVICE principal with no profiles."""
    principal = await deps.require_principal(
        _ExplodingSession(),  # pyright: ignore[reportArgumentType]
        authorization=f"Bearer {_mint()}",
    )
    assert principal.role is deps.Role.DEVICE
    assert principal.profile_ids == frozenset()
    assert principal.family_id == _FAMILY_ID
    assert principal.user_id == _AUTHORIZED_BY
    assert principal.subject == f"device:{_JTI}"
    assert principal.is_admin is False
    assert principal.is_guardian is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_require_principal_rejects_forged_device_token() -> None:
    """A device-audience token signed with the wrong secret is rejected."""
    forged = _encode(_claims(), secret=_OTHER_SECRET)
    with pytest.raises(AuthenticationError):
        await deps.require_principal(
            _ExplodingSession(),  # pyright: ignore[reportArgumentType]
            authorization=f"Bearer {forged}",
        )


@pytest.mark.unit
def test_device_principal_never_carries_admin_capability() -> None:
    """Constructing a DEVICE Principal always force-clears is_admin.

    Defense in depth (deps.py Principal.__post_init__): even a maliciously
    or mistakenly constructed Principal(role=DEVICE, is_admin=True) must
    lose the capability, since a device grant has no DB row backing an
    ``is_admin`` column to check against (unlike CHILD, which is also
    backed by the ck_user_child_not_admin DB CHECK).
    """
    principal = deps.Principal(
        subject="device:x",
        user_id=_AUTHORIZED_BY,
        role=deps.Role.DEVICE,
        family_id=_FAMILY_ID,
        profile_ids=frozenset(),
        is_admin=True,
    )
    assert principal.is_admin is False


# ---------------------------------------------------------------------------
# require_onboarding_identity refuse-only guard
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_device_grant_cannot_onboard() -> None:
    """A device grant token cannot provision a guardian Family+User."""
    with pytest.raises(AuthorizationError):
        await deps.require_onboarding_identity(authorization=f"Bearer {_mint()}")


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
        "child_session_secret": SecretStr(
            "a-fine-32-plus-byte-child-session-secret-value"
        ),
    }


@pytest.mark.unit
def test_missing_device_grant_secret_outside_local_rejected() -> None:
    """A non-local Settings with no device-grant secret refuses to construct."""
    with pytest.raises(ConfigError, match="DEVICE_GRANT_SECRET"):
        Settings(**_base_nonlocal_kwargs(), device_grant_secret=None)


@pytest.mark.unit
@pytest.mark.parametrize(
    "weak",
    ["", "   ", "too-short", "REPLACE_ME", "changeme"],
)
def test_weak_device_grant_secret_outside_local_rejected(weak: str) -> None:
    """A short or placeholder device-grant secret refuses to construct."""
    with pytest.raises(ConfigError, match="DEVICE_GRANT_SECRET"):
        Settings(
            **_base_nonlocal_kwargs(),
            device_grant_secret=SecretStr(weak),
        )
