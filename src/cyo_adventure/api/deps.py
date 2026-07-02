"""Request dependencies: the DB session unit-of-work and the auth seam.

The auth seam resolves a bearer token to a :class:`Principal` (role, family, and
the set of child profiles it may act on). In the ``local`` environment it is a
*seam*: the dev/test stub treats the bearer token as the already-verified OIDC
subject, with no signature/issuer/expiry check. Outside ``local`` the token is
a real Supabase-issued JWT (ADR-009), verified against a cached JWKS
(signature, issuer, audience, expiry) before its ``sub`` claim is trusted; the
authorization logic below does not change either way.

Authorization rules (docs/planning/authorization-matrix.md):
- A guardian may act on any child profile within its own family.
- A child may act only on its own assigned profile.
- Family ownership is checked on every resource, independent of role.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated

import jwt
from fastapi import Depends, Header
from sqlalchemy import select

from cyo_adventure.core.config import settings
from cyo_adventure.core.database import get_session
from cyo_adventure.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
)
from cyo_adventure.db.models import ChildProfile, User

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession


class Role(StrEnum):
    """The closed set of authenticated principal roles.

    Coercing the ORM ``user.role`` string through ``Role(...)`` at the auth
    boundary rejects any value the database holds outside this set
    (closed-world): an unmodeled role raises rather than silently authorizing.
    """

    GUARDIAN = "guardian"
    CHILD = "child"
    ADMIN = "admin"


_BEARER_PREFIX = "bearer "

# #CRITICAL: security: this module contains a dev/test auth seam (_extract_subject)
# that treats any bearer token as a verified OIDC subject with NO signature,
# issuer, or expiry validation. It must never be active outside local development.
# #VERIFY: ConfigurationError raised at import time when environment != "local"
# and no real OIDC verification config (oidc_issuer + oidc_jwks_url) is present,
# so uvicorn fails to start in staging/production unless real Supabase JWT
# verification (_verify_oidc_jwt below) is actually configured to take over.
if settings.environment != "local" and not (
    settings.oidc_issuer and settings.oidc_jwks_url
):
    _env = settings.environment
    msg = (
        f"The dev auth stub in api/deps.py cannot run in the {_env!r} environment "
        "and no OIDC verification is configured. Set OIDC_ISSUER and "
        "OIDC_JWKS_URL (ADR-009: Supabase Auth), or run with environment='local'."
    )
    raise ConfigurationError(msg)


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller and the profiles it may act on.

    Attributes:
        subject: The verified token subject (OIDC ``sub`` in production).
        user_id: The resolved ``User.id`` for the subject, used to stamp
            creator provenance (``created_by``) on rows this principal writes.
        role: ``"guardian"``, ``"child"``, or ``"admin"``.
        family_id: The family the principal belongs to.
        profile_ids: The child-profile ids this principal may read or write.
    """

    subject: str
    user_id: uuid.UUID
    role: Role
    family_id: uuid.UUID
    profile_ids: frozenset[uuid.UUID]

    @property
    def is_guardian(self) -> bool:
        """Return whether the principal holds the guardian role."""
        return self.role == Role.GUARDIAN

    @property
    def is_admin(self) -> bool:
        """Return whether the principal holds the global admin (approver) role."""
        return self.role == Role.ADMIN

    def can_access_profile(self, profile_id: uuid.UUID) -> bool:
        """Return whether the principal may act on the given profile.

        Args:
            profile_id: The child profile being accessed.

        Returns:
            bool: ``True`` if the profile is in the principal's allowed set.
        """
        return profile_id in self.profile_ids


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session, committing on success.

    Handlers never call ``commit`` directly (see the package CLAUDE.md); this
    unit-of-work commits when the request succeeds and rolls back on error.

    Yields:
        AsyncSession: The session for the request.
    """
    # #CRITICAL: data integrity: the unit-of-work commits exactly once at request
    # end; a handler that needs partial durability must flush, not commit.
    # #VERIFY: handlers raise on failure so the except path rolls back.
    session = get_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


DbSession = Annotated["AsyncSession", Depends(get_db_session)]


def _extract_subject(authorization: str | None) -> str:
    """Extract the token subject from an Authorization header.

    Args:
        authorization: The raw ``Authorization`` header value.

    Returns:
        str: The bearer token, treated as the verified subject (dev stub).

    Raises:
        AuthenticationError: If the header is missing or malformed.
    """
    # #CRITICAL: security: dev/test seam only. Treats the bearer token as the
    # verified OIDC subject WITHOUT signature/issuer/expiry verification.
    # #VERIFY: _resolve_subject routes non-local callers to _verify_oidc_jwt
    # instead; never ship this unverified path to staging or production.
    if not authorization or not authorization.lower().startswith(_BEARER_PREFIX):
        msg = "missing or malformed bearer token"
        raise AuthenticationError(msg)
    token = authorization[len(_BEARER_PREFIX) :].strip()
    if not token:
        msg = "empty bearer token"
        raise AuthenticationError(msg)
    return token


# #CRITICAL: external-resources: PyJWKClient fetches and caches the JWKS by URL
# internally (its own TTL cache); constructing it lazily at first non-local
# request (never at import time) means local/test imports never touch the
# network, and this module-level singleton avoids a JWKS refetch per request.
# #VERIFY: test_oidc_verification.py monkeypatches _jwks_client, not the
# network, so PyJWKClient's own caching is never exercised in the suite.
_jwks_client_cache: jwt.PyJWKClient | None = None


def _jwks_client() -> jwt.PyJWKClient:
    """Return the lazily-constructed, process-wide JWKS client.

    Returns:
        jwt.PyJWKClient: The client backing OIDC signature verification.
    """
    global _jwks_client_cache  # noqa: PLW0603
    if _jwks_client_cache is None:
        if settings.oidc_jwks_url is None:
            msg = "OIDC_JWKS_URL is not configured; cannot verify OIDC tokens"
            raise ConfigurationError(msg)
        # #CRITICAL: security: an http:// JWKS URL allows on-path key
        # substitution -> token forgery.
        # #VERIFY: reject non-https oidc_jwks_url outside local.
        if settings.environment != "local" and not settings.oidc_jwks_url.startswith(
            "https://"
        ):
            msg = (
                "OIDC_JWKS_URL must use https outside local; an http JWKS URL lets "
                "an on-path attacker swap signing keys and forge tokens"
            )
            raise ConfigurationError(msg)
        _jwks_client_cache = jwt.PyJWKClient(settings.oidc_jwks_url)
    return _jwks_client_cache


def _verify_oidc_jwt(token: str) -> str:
    """Verify a Supabase-issued JWT and return its subject.

    Verifies signature (via the cached JWKS), issuer, audience, and expiry.
    Only ``RS256``/``ES256`` are accepted; an explicit algorithm allowlist is
    what defeats an ``alg=none`` or HS256-confusion forgery attempt, since
    PyJWT never falls back to a caller-supplied algorithm.

    Args:
        token: The raw bearer token (a JWT, not the dev-stub's opaque string).

    Returns:
        str: The verified ``sub`` claim.

    Raises:
        AuthenticationError: If the token is malformed, unsigned, expired, or
            fails signature, issuer, or audience verification. The underlying
            PyJWT/JWKS error is never included in the message.
    """
    # #CRITICAL: security: this is the real verification path (ADR-009 P6-01).
    # A failure here must never fall back to trusting the token unverified.
    # #VERIFY: test_oidc_verification.py covers expired/wrong-issuer/
    # wrong-audience/tampered-signature/alg-none, each asserting AuthenticationError.
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,  # pyright: ignore[reportAny]
            algorithms=["RS256", "ES256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.PyJWKClientError as exc:
        msg = "unable to fetch signing key for token verification"
        raise AuthenticationError(msg) from exc
    except jwt.PyJWTError as exc:
        msg = "token failed verification"
        raise AuthenticationError(msg) from exc
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        msg = "token is missing a subject claim"
        raise AuthenticationError(msg)
    return subject


def _resolve_subject(token: str) -> str:
    """Resolve the verified subject from a bearer token.

    In ``local`` this trusts the token as-is (the dev/test auth seam,
    documented at module level). Everywhere else it verifies the token as a
    real Supabase JWT.

    Args:
        token: The raw bearer token.

    Returns:
        str: The verified (or, in ``local``, trusted) subject.
    """
    # #CRITICAL: security: the local branch trusts the bearer token as the
    # subject with NO verification; it is reachable only when
    # environment == "local".
    # #VERIFY: test_resolve_subject_verifies_outside_local asserts non-local
    # routes to _verify_oidc_jwt.
    if settings.environment == "local":
        return token
    return _verify_oidc_jwt(token)


async def require_principal(
    session: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    """Resolve the request's :class:`Principal` from the bearer token.

    Args:
        session: The request database session.
        authorization: The ``Authorization`` header.

    Returns:
        Principal: The authenticated principal.

    Raises:
        AuthenticationError: If the token is missing, fails OIDC verification
            outside ``local``, or the subject is unknown.
    """
    subject = _resolve_subject(_extract_subject(authorization))
    user = await session.scalar(select(User).where(User.authn_subject == subject))
    if user is None:
        msg = "unknown subject"
        raise AuthenticationError(msg)
    profile_ids = await _resolve_profiles(session, user)
    # #CRITICAL: security: coerce the ORM role string to the closed Role enum at
    # the auth boundary; an unmodeled DB role raises ValueError -> 500 rather
    # than producing a principal with an unrecognized (and unauthorized) role.
    # #VERIFY: the ck_user_role CHECK constraint keeps the column within the set,
    # so this coercion only fails on a corrupted or hand-edited row.
    return Principal(
        subject=subject,
        user_id=user.id,
        role=Role(user.role),
        family_id=user.family_id,
        profile_ids=profile_ids,
    )


async def _resolve_profiles(session: AsyncSession, user: User) -> frozenset[uuid.UUID]:
    """Return the set of child profiles the user may act on.

    Args:
        session: The database session.
        user: The resolved user row.

    Returns:
        frozenset[uuid.UUID]: All family profiles for a guardian; the single
            assigned profile for a child; empty if a child has none.
    """
    if user.role == Role.GUARDIAN:
        rows = await session.scalars(
            select(ChildProfile.id).where(ChildProfile.family_id == user.family_id)
        )
        return frozenset(rows.all())
    if user.child_profile_id is not None:
        return frozenset({user.child_profile_id})
    return frozenset()


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Bundle of the authenticated principal and the request session.

    Injecting one context keeps route handlers within the project's argument
    limit while still giving them both dependencies.

    Attributes:
        principal: The authenticated principal.
        session: The request database session (unit-of-work).
    """

    principal: Principal
    session: AsyncSession


def get_context(principal: CurrentPrincipal, session: DbSession) -> RequestContext:
    """Provide the combined request context dependency.

    Args:
        principal: The authenticated principal.
        session: The request session.

    Returns:
        RequestContext: The bundled context.
    """
    return RequestContext(principal=principal, session=session)


Context = Annotated[RequestContext, Depends(get_context)]


def authorize_profile(principal: Principal, profile_id: uuid.UUID) -> None:
    """Raise if the principal may not act on the given profile.

    Args:
        principal: The authenticated principal.
        profile_id: The child profile being accessed.

    Raises:
        AuthorizationError: If the profile is not in the allowed set.
    """
    if not principal.can_access_profile(profile_id):
        msg = "profile is not accessible to this principal"
        raise AuthorizationError(msg, resource=str(profile_id))


def authorize_family(principal: Principal, owner_family_id: uuid.UUID) -> None:
    """Raise if a resource belongs to a different family.

    Args:
        principal: The authenticated principal.
        owner_family_id: The family that owns the resource.

    Raises:
        AuthorizationError: If the resource is owned by another family.
    """
    if principal.family_id != owner_family_id:
        msg = "resource belongs to another family"
        raise AuthorizationError(msg)


CurrentPrincipal = Annotated[Principal, Depends(require_principal)]
