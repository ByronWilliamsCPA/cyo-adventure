"""Backend-signed, guardian-minted device grant tokens (ADR-014 phase 1).

A device grant is a durable (90-day, revocable), family-scoped authorization
artifact a guardian mints once per shared device. It is NOT a login and it is
NOT a Supabase identity (ADR-009 keeps guardians on Supabase); it is the third
token type in the trust table at the top of ADR-014, sitting between the
guardian's short-lived Supabase JWT and the child session:

- Supabase JWT: "a grown-up is present now" (short-lived, RS256/ES256, JWKS).
- Device grant (this module): "a grown-up authorized this device for their
  family" (90 days, revocable, HS256).
- Child session (``core/child_session.py``): "this profile is reading" (12h,
  no refresh, HS256).

This module mints and verifies the grant; ``api/device_grants.py`` lists and
revokes it; and the ``api/deps.py`` routing branch turns a presented token
into a revocation-checked ``DEVICE`` principal. That principal is an
additional authority alongside the guardian/admin Supabase bearer on the
child-session mint and the profiles endpoint (never a guardian/admin gate).

Trust model
-----------
- HS256, signed with ``settings.device_grant_secret`` (a backend secret the
  browser never sees; distinct from both the Supabase JWKS used for guardians
  and the ``child_session_secret`` used for child sessions).
- A fixed, app-specific issuer and a DISTINCT audience (``cyo-device-grant``)
  so a device grant can never be verified as a Supabase guardian token or a
  child session token, or vice versa, independent of the algorithm pin.
- Verification pins ``algorithms=["HS256"]`` and checks issuer, audience, and
  expiry, mirroring ``verify_child_session_token``: a token can only ever
  verify through the branch that minted it.
- Revocation is enforced online only (the embedded ``jti`` is checked against
  the ``device_grants`` table's ``revoked_at`` column by the endpoints/deps
  routing that consume it); an offline device cannot see a revocation until it
  reconnects. This is an accepted limitation bounded by the 90-day TTL
  (ADR-014, "Negative / risks").

#CRITICAL: security: the device principal built from this token (Phase 1's
``api/deps.py::_device_principal``) must never be granted guardian or admin
scope. It carries only ``family_id`` and ``authorized_by``; it has no
``profile_ids`` and no admin capability, so it cannot pass a guardian-only or
admin-only gate regardless of the claims in the token.
#VERIFY: test_device_grant.py's require_principal routing tests assert a
device token is refused on guardian-only and admin-only dependencies.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import AuthenticationError, ConfigurationError

# Fixed, app-specific token markers. The audience is deliberately DISTINCT
# from both the guardian OIDC audience (settings.oidc_audience,
# "authenticated") and the child-session audience
# (core.child_session.CHILD_SESSION_AUDIENCE, "cyo-child-session") so all
# three token families are non-interchangeable: routing any token into the
# wrong verification branch fails on audience, on top of each branch's own
# algorithm pin.
DEVICE_GRANT_ISSUER = "cyo-adventure"
DEVICE_GRANT_AUDIENCE = "cyo-device-grant"

_DEVICE_ROLE = "device"
_ALGORITHM = "HS256"


@dataclass(frozen=True, slots=True)
class DeviceGrantClaims:
    """The verified identity carried by a device grant token.

    Attributes:
        subject: The token ``sub`` claim (``"device:{jti}"``).
        family_id: The family this device is authorized to act on behalf of.
        authorized_by: The guardian ``User.id`` who minted this grant.
        jti: The token's unique id. Matched against ``device_grants.jti`` for
            revocation lookups; embedded here (rather than requiring a
            database read to discover it) so a caller holding only the
            verified claims can still look up or revoke its own grant.
    """

    subject: str
    family_id: uuid.UUID
    authorized_by: uuid.UUID
    jti: uuid.UUID


def _secret() -> str:
    """Return the configured signing secret, or raise if it is unset.

    Returns:
        str: The device-grant signing secret.

    Raises:
        ConfigurationError: If ``device_grant_secret`` is not configured.
    """
    # #CRITICAL: security: the signing secret is required to mint or verify a
    # device grant; refusing when it is unset prevents a silently-unsigned or
    # unverifiable token path. Outside local the config validator already
    # makes it mandatory; this guards the local/test path where it may be
    # unset.
    # #VERIFY: test_mint_without_secret_raises asserts the ConfigurationError.
    if settings.device_grant_secret is None:
        msg = (
            "DEVICE_GRANT_SECRET is not configured; cannot mint or verify "
            "device grant tokens"
        )
        raise ConfigurationError(msg)
    return settings.device_grant_secret.get_secret_value()


def mint_device_grant_token(
    *,
    family_id: uuid.UUID,
    authorized_by: uuid.UUID,
    jti: uuid.UUID,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    """Mint a signed, family-scoped device grant token.

    Args:
        family_id: The family this device is authorized for.
        authorized_by: The minting guardian's ``User.id`` (embedded so the
            grant is attributable without a database read).
        jti: The grant's unique id. The caller (``api/device_grants.py``)
            generates this and persists a matching ``device_grants`` row in
            the same unit of work, so the token and its revocation record
            always agree on the id.
        now: Injection point for the issue time (tests); defaults to the
            current UTC time.

    Returns:
        tuple[str, datetime]: The signed compact JWT and its expiry time.
    """
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(seconds=settings.device_grant_ttl_seconds)
    claims: dict[str, object] = {
        "sub": f"{_DEVICE_ROLE}:{jti}",
        "role": _DEVICE_ROLE,
        "family_id": str(family_id),
        "authorized_by": str(authorized_by),
        "jti": str(jti),
        "iss": DEVICE_GRANT_ISSUER,
        "aud": DEVICE_GRANT_AUDIENCE,
        "iat": issued_at,
        "exp": expires_at,
    }
    token = jwt.encode(claims, _secret(), algorithm=_ALGORITHM)
    return token, expires_at


def verify_device_grant_token(token: str) -> DeviceGrantClaims:
    """Verify a device grant token and return its claims.

    Pins ``algorithms=["HS256"]`` and checks issuer, audience, and expiry, and
    requires ``exp``/``iat``/``sub`` to be present. Any failure raises
    ``AuthenticationError`` with no underlying PyJWT detail leaked, mirroring
    ``verify_child_session_token``.

    This verifies the SIGNATURE and standard claims only; it does not check
    ``device_grants.revoked_at``. Revocation is a database-backed, online-only
    check performed by the caller (Phase 1's ``api/deps.py`` routing and
    ``api/device_grants.py`` endpoints), not by this module, so this function
    stays self-contained and DB-free like ``verify_child_session_token``.

    Args:
        token: The raw bearer token believed to be a device grant JWT.

    Returns:
        DeviceGrantClaims: The verified family/authorizer/jti identity.

    Raises:
        AuthenticationError: If the token is malformed, unsigned, expired,
            signed with the wrong secret, uses a non-HS256 algorithm, carries
            the wrong issuer/audience, or is missing a required claim.
        ConfigurationError: If the signing secret is not configured.
    """
    # #CRITICAL: security: this is the device-grant counterpart to the child
    # session and OIDC verification paths. The HS256 pin plus the fixed
    # audience/issuer is what defeats an alg=none forgery, an RS256/HS256
    # confusion, and an audience-substitution from a guardian or child token.
    # A failure here must never fall back to trusting the token unverified.
    # #VERIFY: test_device_grant.py covers expired/tampered/wrong-secret/
    # wrong-issuer/wrong-audience/missing-claim.
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[_ALGORITHM],
            audience=DEVICE_GRANT_AUDIENCE,
            issuer=DEVICE_GRANT_ISSUER,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        msg = "device grant token failed verification"
        raise AuthenticationError(msg) from exc
    return _claims_from_payload(payload)


def _claims_from_payload(payload: dict[str, object]) -> DeviceGrantClaims:
    """Project a verified JWT payload to typed claims, rejecting bad shapes.

    Args:
        payload: The signature-verified claim dict from ``jwt.decode``.

    Returns:
        DeviceGrantClaims: The parsed identity.

    Raises:
        AuthenticationError: If the subject/role is absent or wrong, or any
            id claim is missing or not a valid UUID.
    """
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        msg = "device grant token is missing a subject claim"
        raise AuthenticationError(msg)
    if payload.get("role") != _DEVICE_ROLE:
        # A valid signature over a non-device role is still refused here:
        # this branch only ever produces a DEVICE principal, so anything else
        # is a misissued token, not a role escalation vector.
        msg = "device grant token does not carry the device role"
        raise AuthenticationError(msg)
    return DeviceGrantClaims(
        subject=subject,
        family_id=_uuid_claim(payload, "family_id"),
        authorized_by=_uuid_claim(payload, "authorized_by"),
        jti=_uuid_claim(payload, "jti"),
    )


def _uuid_claim(payload: dict[str, object], name: str) -> uuid.UUID:
    """Parse a required UUID claim, raising an auth error on absence/bad shape.

    Args:
        payload: The verified claim dict.
        name: The claim key to read.

    Returns:
        uuid.UUID: The parsed id.

    Raises:
        AuthenticationError: If the claim is absent, not a string, or not a
            valid UUID.
    """
    raw = payload.get(name)
    if not isinstance(raw, str):
        msg = f"device grant token is missing the {name} claim"
        raise AuthenticationError(msg)
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        msg = f"device grant token has a malformed {name} claim"
        raise AuthenticationError(msg) from exc
