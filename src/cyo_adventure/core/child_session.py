"""Backend-signed, guardian-minted child session tokens (G1 / P6-04).

The kid surface needs a first-class, child-scoped credential that is NOT a
Supabase user (ADR-009 keeps guardians on Supabase; children do not get
Supabase accounts). A guardian mints a short-lived, backend-signed JWT bound
to a single child profile, and ``api/deps.py``'s ``require_principal`` verifies
it in a second branch that mirrors the guardian OIDC branch's trust model.

The token is deliberately self-contained (all ids live in the claims) and
long-lived enough to cover one offline reading session, because a child
session cannot be refreshed (the debt-register offline-reading requirement):
it reads a downloaded story for the token's full lifetime.

Trust model
-----------
- HS256, signed with ``settings.child_session_secret`` (a backend secret the
  browser never sees; distinct from the Supabase JWKS used for guardians).
- A fixed, app-specific issuer and a DISTINCT audience
  (``cyo-child-session``) so a child token can never be verified as a Supabase
  guardian token, or vice versa, independent of the algorithm pin.
- Verification pins ``algorithms=["HS256"]`` and checks issuer, audience, and
  expiry, so neither an ``alg=none`` forgery nor an RS256/HS256 confusion can
  pass (this is the HS256 counterpart to ``_verify_oidc_jwt``'s RS256/ES256
  pin: a token can only ever verify through the branch that minted it).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import AuthenticationError, ConfigurationError
from cyo_adventure.core.token_audience import TokenAudience

# Fixed, app-specific token markers. The audience is deliberately DISTINCT from
# the guardian OIDC audience (settings.oidc_audience, "authenticated") so the
# two token families are non-interchangeable: a child token routed into the
# guardian JWKS path fails on audience, and a guardian token routed here fails
# on audience too, on top of each branch's own algorithm pin. The value is
# sourced from the central TokenAudience registry (issue #251), whose members
# core/config.py asserts are pairwise distinct at startup.
CHILD_SESSION_ISSUER = "cyo-adventure"
CHILD_SESSION_AUDIENCE = TokenAudience.CHILD_SESSION

_CHILD_ROLE = "child"
_ALGORITHM = "HS256"


@dataclass(frozen=True, slots=True)
class ChildSessionClaims:
    """The verified identity carried by a child session token.

    Attributes:
        subject: The token ``sub`` claim (``"child:{profile_id}"``).
        profile_id: The single child profile this session may act on.
        family_id: The owning family, carried so the principal needs no lookup.
        user_id: The child ``User.id``, embedded at mint so the resulting
            principal is attributable on the append-only pipeline_event log
            (its ``actor_id`` is a FK to ``user.id``) without a database read.
    """

    subject: str
    profile_id: uuid.UUID
    family_id: uuid.UUID
    user_id: uuid.UUID


def _secret() -> str:
    """Return the configured signing secret, or raise if it is unset.

    Returns:
        str: The child-session signing secret.

    Raises:
        ConfigurationError: If ``child_session_secret`` is not configured.
    """
    # #CRITICAL: security: the signing secret is required to mint or verify a
    # child token; refusing when it is unset prevents a silently-unsigned or
    # unverifiable token path. Outside local the config validator already makes
    # it mandatory; this guards the local/test path where it may be unset.
    # #VERIFY: test_mint_without_secret_raises asserts the ConfigurationError.
    if settings.child_session_secret is None:
        msg = (
            "CHILD_SESSION_SECRET is not configured; cannot mint or verify "
            "child session tokens"
        )
        raise ConfigurationError(msg)
    return settings.child_session_secret.get_secret_value()


def mint_child_session_token(
    *,
    profile_id: uuid.UUID,
    family_id: uuid.UUID,
    user_id: uuid.UUID,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    """Mint a signed, child-scoped session token for one profile.

    Args:
        profile_id: The single child profile the token is scoped to.
        family_id: The owning family (embedded in the claims).
        user_id: The child ``User.id`` (embedded so the principal is
            attributable without a database read; see ``ChildSessionClaims``).
        now: Injection point for the issue time (tests); defaults to the
            current UTC time.

    Returns:
        tuple[str, datetime]: The signed compact JWT and its expiry time.
    """
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(seconds=settings.child_session_ttl_seconds)
    claims: dict[str, object] = {
        "sub": f"{_CHILD_ROLE}:{profile_id}",
        "role": _CHILD_ROLE,
        "profile_id": str(profile_id),
        "family_id": str(family_id),
        "user_id": str(user_id),
        "iss": CHILD_SESSION_ISSUER,
        "aud": CHILD_SESSION_AUDIENCE,
        "iat": issued_at,
        "exp": expires_at,
    }
    token = jwt.encode(claims, _secret(), algorithm=_ALGORITHM)
    return token, expires_at


def unverified_audience(token: str) -> str | None:
    """Return a token's UNVERIFIED ``aud`` claim, or None if it is not a JWT.

    Used ONLY by ``require_principal`` to route a bearer token to the correct
    verification branch. The value is never trusted for authorization: the
    selected branch fully verifies the signature and every claim before any
    principal is built, so reading the audience unverified here cannot widen
    access (see the ``#CRITICAL`` note at the ``require_principal`` call site).

    Args:
        token: The raw bearer token (a child JWT, a guardian JWT, or the
            local dev-stub's opaque subject string).

    Returns:
        str | None: The ``aud`` claim if the token is a JWT carrying a string
        audience; ``None`` for a non-JWT opaque token or a missing/non-string
        audience.
    """
    try:
        # SonarCloud python:S5659 (JWT without signature verification) flags the
        # next line. It is a verified FALSE POSITIVE: this decode reads the `aud`
        # claim ONLY to route the token to a verifier (child vs guardian). The
        # value is never trusted; the selected branch (verify_child_session_token
        # / _verify_oidc_jwt) re-decodes with signature + alg + iss + aud + exp
        # fully enforced before any principal is built. Suppressing an intentional
        # unverified peek here does not weaken authorization. Do not add real
        # verification (there is no key to select yet, that selection is this
        # function's job).
        # Resolved in SonarCloud as Accepted (issue AZ9UaGUMldJHH9vRm8Sk). Note
        # for anyone re-resolving it: SonarQube Cloud merged "False Positive"
        # and "Won't Fix" into a single "Accept" action on the issue's status
        # dropdown, and "Mark Safe" is Security Hotspot wording for a surface
        # that is now deprecated, so neither of those labels exists to click.
        payload = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return None
    aud = payload.get("aud")
    return aud if isinstance(aud, str) else None


def verify_child_session_token(token: str) -> ChildSessionClaims:
    """Verify a child session token and return its claims.

    Pins ``algorithms=["HS256"]`` and checks issuer, audience, and expiry, and
    requires ``exp``/``iat``/``sub`` to be present. Any failure raises
    ``AuthenticationError`` with no underlying PyJWT detail leaked, mirroring
    ``_verify_oidc_jwt``.

    Args:
        token: The raw bearer token believed to be a child session JWT.

    Returns:
        ChildSessionClaims: The verified profile/family/user identity.

    Raises:
        AuthenticationError: If the token is malformed, unsigned, expired,
            signed with the wrong secret, uses a non-HS256 algorithm, carries
            the wrong issuer/audience, or is missing a required claim.
        ConfigurationError: If the signing secret is not configured.
    """
    # #CRITICAL: security: this is the child counterpart to the OIDC path. The
    # HS256 pin plus the fixed audience/issuer is what defeats an alg=none
    # forgery, an RS256/HS256 confusion (an RS256 token cannot verify under an
    # HS256-only allowlist), and an audience-substitution from a guardian token.
    # A failure here must never fall back to trusting the token unverified.
    # #VERIFY: test_child_session.py covers expired/tampered/wrong-secret/
    # wrong-issuer/wrong-audience/rs256-in-child-path/missing-claim.
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=[_ALGORITHM],
            audience=CHILD_SESSION_AUDIENCE,
            issuer=CHILD_SESSION_ISSUER,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWTError as exc:
        msg = "child session token failed verification"
        raise AuthenticationError(msg) from exc
    return _claims_from_payload(payload)


def _claims_from_payload(payload: dict[str, object]) -> ChildSessionClaims:
    """Project a verified JWT payload to typed claims, rejecting bad shapes.

    Args:
        payload: The signature-verified claim dict from ``jwt.decode``.

    Returns:
        ChildSessionClaims: The parsed identity.

    Raises:
        AuthenticationError: If the subject/role is absent or wrong, or any id
            claim is missing or not a valid UUID.
    """
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        msg = "child session token is missing a subject claim"
        raise AuthenticationError(msg)
    if payload.get("role") != _CHILD_ROLE:
        # A valid signature over a non-child role is still refused here: this
        # branch only ever produces a CHILD principal, so anything else is a
        # misissued token, not a role escalation vector.
        msg = "child session token does not carry the child role"
        raise AuthenticationError(msg)
    return ChildSessionClaims(
        subject=subject,
        profile_id=_uuid_claim(payload, "profile_id"),
        family_id=_uuid_claim(payload, "family_id"),
        user_id=_uuid_claim(payload, "user_id"),
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
        msg = f"child session token is missing the {name} claim"
        raise AuthenticationError(msg)
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        msg = f"child session token has a malformed {name} claim"
        raise AuthenticationError(msg) from exc
