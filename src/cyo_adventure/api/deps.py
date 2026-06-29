"""Request dependencies: the DB session unit-of-work and the auth seam.

The auth seam resolves a bearer token to a :class:`Principal` (role, family, and
the set of child profiles it may act on). It is a *seam*: the dev/test stub
treats the bearer token as the already-verified OIDC subject. Real Authentik OIDC
verification (issuer, audience, signature, expiry) replaces ``_extract_subject``
in a later phase; the authorization logic below does not change.

Authorization rules (docs/planning/authorization-matrix.md):
- A guardian may act on any child profile within its own family.
- A child may act only on its own assigned profile.
- Family ownership is checked on every resource, independent of role.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

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

ROLE_GUARDIAN = "guardian"
ROLE_CHILD = "child"

_BEARER_PREFIX = "bearer "

# #CRITICAL: security: this module contains a dev/test auth seam (_extract_subject)
# that treats any bearer token as a verified OIDC subject with NO signature,
# issuer, or expiry validation. It must never be active outside local development.
# #VERIFY: ConfigurationError raised at import time when environment != "local",
# so uvicorn fails to start in staging/production if this stub is still wired in.
if settings.environment != "local":
    _env = settings.environment
    msg = (
        f"The dev auth stub in api/deps.py is active in the {_env!r} environment. "
        "Replace _extract_subject with real Authentik JWT validation before any "
        "non-local deployment."
    )
    raise ConfigurationError(msg)


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller and the profiles it may act on.

    Attributes:
        subject: The verified token subject (OIDC ``sub`` in production).
        user_id: The resolved ``User.id`` for the subject, used to stamp
            creator provenance (``created_by``) on rows this principal writes.
        role: ``"guardian"`` or ``"child"``.
        family_id: The family the principal belongs to.
        profile_ids: The child-profile ids this principal may read or write.
    """

    subject: str
    user_id: uuid.UUID
    role: str
    family_id: uuid.UUID
    profile_ids: frozenset[uuid.UUID]

    @property
    def is_guardian(self) -> bool:
        """Return whether the principal holds the guardian role."""
        return self.role == ROLE_GUARDIAN

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
    # #VERIFY: replace with real Authentik JWT validation before any non-local
    # deployment; never ship this stub to staging or production.
    if not authorization or not authorization.lower().startswith(_BEARER_PREFIX):
        msg = "missing or malformed bearer token"
        raise AuthenticationError(msg)
    token = authorization[len(_BEARER_PREFIX) :].strip()
    if not token:
        msg = "empty bearer token"
        raise AuthenticationError(msg)
    return token


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
        AuthenticationError: If the token is missing or the subject is unknown.
    """
    subject = _extract_subject(authorization)
    user = await session.scalar(select(User).where(User.authn_subject == subject))
    if user is None:
        msg = "unknown subject"
        raise AuthenticationError(msg)
    profile_ids = await _resolve_profiles(session, user)
    return Principal(
        subject=subject,
        user_id=user.id,
        role=user.role,
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
    if user.role == ROLE_GUARDIAN:
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
