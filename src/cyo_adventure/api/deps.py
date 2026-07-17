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

import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any

import jwt
from fastapi import Depends, Header
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from cyo_adventure.core.child_session import (
    CHILD_SESSION_AUDIENCE,
    unverified_audience,
    verify_child_session_token,
)
from cyo_adventure.core.config import settings
from cyo_adventure.core.database import get_session
from cyo_adventure.core.device_grant import (
    DEVICE_GRANT_AUDIENCE,
    verify_device_grant_token,
)
from cyo_adventure.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    ValidationError,
)
from cyo_adventure.db.models import ChildProfile, DeviceGrant, User

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession


class Role(StrEnum):
    """The closed set of authenticated base personas.

    Coercing the ORM ``user.role`` string through ``Role(...)`` at the auth
    boundary rejects any value the database holds outside this set
    (closed-world): an unmodeled role raises rather than silently authorizing.

    ``role`` is the single base persona; the global admin capability is the
    orthogonal ``is_admin`` flag on :class:`Principal` (backed by
    ``User.is_admin``), so one adult can be a guardian, an admin, or both.
    ``ADMIN`` as a base role means an admin-only adult with no family
    guardianship; it implies the capability regardless of the stored flag.

    ``DEVICE`` (ADR-014 phase 1) is a token-only role: it never corresponds
    to a ``User`` row (the ``ck_user_role`` DB CHECK does not include it), so
    ``Role("device")`` only ever appears on a :class:`Principal` built from a
    verified device grant token (``_device_principal``), never from the
    ``select(User)`` branch of ``require_principal``.
    """

    GUARDIAN = "guardian"
    CHILD = "child"
    ADMIN = "admin"
    DEVICE = "device"


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
            For a ``DEVICE`` principal this is the minting guardian's
            ``User.id`` (the token's ``authorized_by`` claim), not a real
            device account, mirroring how a ``CHILD`` principal carries the
            child's own provisioned ``User.id``.
        role: The base persona: ``"guardian"``, ``"child"``, ``"admin"``, or
            ``"device"`` (ADR-014 phase 1; a device grant, never a login).
        family_id: The family the principal belongs to.
        profile_ids: The child-profile ids this principal may read or write.
            Always empty for a ``DEVICE`` principal: a device grant mints a
            child session and lists a family's profiles, but is never itself
            scoped to a profile, so ``__post_init__`` force-clears this set
            for the device role (symmetric with the ``is_admin`` invariant).
        is_admin: Whether the principal holds the global admin (approver)
            capability. Orthogonal to ``role`` so one adult can be a guardian,
            an admin, or both: a ``(role=guardian, is_admin=True)`` principal
            passes both guardian-only and admin-only gates. ``__post_init__``
            derives it for the ``admin`` base role, so a legacy admin-only
            user (or a hand-built test principal) never loses the capability.
    """

    subject: str
    user_id: uuid.UUID
    role: Role
    family_id: uuid.UUID
    profile_ids: frozenset[uuid.UUID]
    is_admin: bool = False

    def __post_init__(self) -> None:
        """Normalize the role and reconcile the admin capability.

        # #CRITICAL: security: the invariant "base role ADMIN implies the
        # admin capability" is enforced here at construction, not left to
        # every caller; a Principal(role=Role.ADMIN) with the flag unset
        # would otherwise be a half-admin that fails admin gates. The
        # Role(...) coercion also rejects any unmodeled role string a
        # caller passes (closed-world), instead of authorizing nothing
        # and nobody noticing. A CHILD or DEVICE principal can never hold
        # the admin capability: the flag is force-cleared here (defense in
        # depth behind the ck_user_child_not_admin DB CHECK for CHILD; DEVICE
        # has no DB row at all, so this is the ONLY enforcement point) so a
        # mistakenly constructed Principal(role=CHILD/DEVICE, is_admin=True)
        # never escalates.
        # #VERIFY: tests/unit/test_api_deps.py pins role=ADMIN -> is_admin
        # and role=CHILD -> not is_admin; test_device_grant.py pins
        # role=DEVICE -> not is_admin.
        """
        object.__setattr__(self, "role", Role(self.role))
        if self.role in (Role.CHILD, Role.DEVICE):
            object.__setattr__(self, "is_admin", False)
        elif self.role == Role.ADMIN and not self.is_admin:
            object.__setattr__(self, "is_admin", True)
        # #CRITICAL: security: a DEVICE principal is never profile-scoped; the
        # grant authorizes a child-session mint and a profile listing, not any
        # per-profile read/write. Force-clearing profile_ids here is the
        # structural counterpart to the is_admin invariant above, so a
        # mistakenly constructed Principal(role=DEVICE, profile_ids={...}) can
        # never pass authorize_profile for a profile it was handed in error.
        # #VERIFY: test_device_grant.py pins role=DEVICE -> profile_ids empty
        # even when a non-empty set is passed to the constructor.
        if self.role == Role.DEVICE:
            object.__setattr__(self, "profile_ids", frozenset())

    @property
    def is_guardian(self) -> bool:
        """Return whether the principal holds the guardian base role."""
        return self.role == Role.GUARDIAN

    def acting_role(self, target_family_id: uuid.UUID) -> Role:
        """Return the capacity in which this principal acts on a family.

        Audit stamps (``initiator_role``, ``actor_role``) record the role
        that AUTHORIZED an action, not merely the base persona: a dual-role
        adult acting outside their own family can only be doing so via the
        admin capability, so the stamp says ``admin``; the same adult acting
        within their own family is stamped with their base role.

        Args:
            target_family_id: The family the action operates on.

        Returns:
            Role: ``Role.ADMIN`` for a cross-family action by an admin;
            the base ``role`` otherwise.
        """
        if self.is_admin and target_family_id != self.family_id:
            return Role.ADMIN
        return self.role

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


async def _decode_oidc_payload(token: str) -> dict[str, Any]:
    """Verify a Supabase-issued JWT and return its full verified payload.

    Verifies signature (via the cached JWKS), issuer, audience, and expiry.
    Only algorithms on the configured allowlist are accepted
    (``settings.oidc_allowed_algs``, default ``RS256``/``ES256``); an explicit
    allowlist is what defeats an ``alg=none`` or HS256-confusion forgery
    attempt, since PyJWT never falls back to a caller-supplied algorithm. The
    allowlist is config-driven (ADR-013: hybrid PQC readiness) so a future
    post-quantum JOSE algorithm is an env change; the Settings validator
    guarantees it is non-empty and never contains ``none`` or ``HS*``.

    This is the single decode path shared by ``_verify_oidc_jwt`` (subject
    only, used by ``require_principal``) and ``_verify_oidc_identity`` (subject
    plus the optional ``email`` contact claim, used by onboarding). Sharing one
    decode keeps the two callers from drifting on the security-critical claim
    checks.

    Args:
        token: The raw bearer token (a JWT, not the dev-stub's opaque string).

    Returns:
        dict[str, Any]: The verified claim payload.

    Raises:
        AuthenticationError: If the token is malformed, unsigned, expired, or
            fails signature, issuer, or audience verification. The underlying
            PyJWT/JWKS error is never included in the message.
    """
    # #CRITICAL: security: this is the real verification path (ADR-009 P6-01).
    # A failure here must never fall back to trusting the token unverified.
    # #VERIFY: test_oidc_verification.py covers expired/wrong-issuer/
    # wrong-audience/tampered-signature/alg-none, each asserting AuthenticationError.
    # #CRITICAL: timing-dependencies: get_signing_key_from_jwt does a blocking
    # urllib fetch on a JWKS cache miss/refresh; run inline it would stall the
    # event loop for every in-flight request for the duration of that fetch.
    # The threadpool offload keeps the async request path responsive; the
    # jwt.decode that follows is CPU-cheap and stays inline.
    # #VERIFY: test_oidc_verification.py exercises this path end-to-end (await).
    try:
        signing_key = await run_in_threadpool(
            _jwks_client().get_signing_key_from_jwt, token
        )
        return jwt.decode(
            token,
            signing_key.key,  # pyright: ignore[reportAny]
            algorithms=list(settings.oidc_allowed_algs),
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


def _require_subject(payload: dict[str, Any]) -> str:
    """Return the verified ``sub`` claim, rejecting an absent or empty one.

    Args:
        payload: A signature-verified OIDC claim payload.

    Returns:
        str: The non-empty subject.

    Raises:
        AuthenticationError: If ``sub`` is missing or not a non-empty string.
    """
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        msg = "token is missing a subject claim"
        raise AuthenticationError(msg)
    return subject


async def _verify_oidc_jwt(token: str) -> str:
    """Verify a Supabase-issued JWT and return its subject.

    Args:
        token: The raw bearer token (a JWT, not the dev-stub's opaque string).

    Returns:
        str: The verified ``sub`` claim.

    Raises:
        AuthenticationError: If the token fails verification or carries no
            subject claim.
    """
    payload = await _decode_oidc_payload(token)
    return _require_subject(payload)


async def _verify_oidc_identity(token: str) -> tuple[str, str | None]:
    """Verify a Supabase JWT and return its subject plus optional email.

    Used only by the onboarding provisioning path, which needs the email
    contact claim in addition to the subject. The email is contact data only,
    never an identity key; the subject remains the sole key.

    Args:
        token: The raw bearer token (a Supabase JWT).

    Returns:
        tuple[str, str | None]: The verified subject and the ``email`` claim
        (``None`` when absent or not a non-empty string).

    Raises:
        AuthenticationError: If the token fails verification or carries no
            subject claim.
    """
    # #ASSUME: data integrity: the ``email`` claim is optional and free-form;
    # Supabase may omit it or supply an Apple private-relay address. It is
    # captured for receipts/consent only, never trusted for authorization or
    # used as a key, so an absent or oddly-shaped value degrades to ``None``
    # rather than raising.
    # #VERIFY: test_oidc_verification.py covers the capture
    # (test_verify_oidc_identity_captures_email_when_present, ..._email_none_when_absent,
    # ..._email_none_when_blank).
    payload = await _decode_oidc_payload(token)
    subject = _require_subject(payload)
    email = payload.get("email")
    return subject, (email if isinstance(email, str) and email else None)


async def _resolve_subject(token: str) -> str:
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
    return await _verify_oidc_jwt(token)


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
        AuthenticationError: If the token is missing, fails OIDC or child-session
            verification, or the subject is unknown.
    """
    token = _extract_subject(authorization)
    # #CRITICAL: security: the verification branch is selected by the token's
    # UNVERIFIED audience claim, which is safe ONLY because each branch then
    # fully verifies the signature and its own claims before any principal is
    # built. The child branch pins HS256 + the child audience/issuer against
    # the backend secret; the device-grant branch pins HS256 + the device
    # audience/issuer against a DIFFERENT backend secret
    # (settings.device_grant_secret); the guardian branch pins RS256/ES256 +
    # the Supabase audience/issuer via JWKS. A token can therefore only ever
    # verify through the branch that minted it: any token routed to a branch
    # it wasn't minted for fails on audience (and, for the guardian branch,
    # on algorithm too). Routing on unverified data widens nothing; it only
    # picks which verifier runs.
    # #VERIFY: test_child_session.py exercises alg-confusion in both directions,
    # wrong-audience, wrong-issuer, and a forged child token; test_device_grant.py
    # covers the same matrix for the device-grant branch, including a child
    # token routed here and a device token routed to the child branch.
    aud = unverified_audience(token)
    if aud == CHILD_SESSION_AUDIENCE:
        return _child_principal(token)
    if aud == DEVICE_GRANT_AUDIENCE:
        return await _device_principal(session, token)
    subject = await _resolve_subject(token)
    user = await session.scalar(select(User).where(User.authn_subject == subject))
    if user is None:
        msg = "unknown subject"
        raise AuthenticationError(msg)
    # #CRITICAL: security: a 'pending' row's authn_subject is a synthetic
    # placeholder (api/admin_users.py) that no real verified subject can ever
    # match, so this branch exists purely as defense in depth; 'deactivated'
    # is the reachable case (WS-J admin user management), and it MUST be
    # rejected with the same message as an unknown subject so status is never
    # a distinguishable oracle for a caller probing authn_subject validity.
    # #VERIFY: tests/integration/test_admin_users_api.py::
    # test_deactivated_guardian_cannot_authenticate.
    if user.status != "active":
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
        # The stored capability flag; __post_init__ additionally derives it
        # for the admin base role, so a legacy (role='admin', is_admin=false)
        # row keeps its capability without a data backfill. bool() coerces an
        # unflushed row's None (ORM column defaults apply at flush) to False.
        is_admin=bool(user.is_admin),
    )


def _child_principal(token: str) -> Principal:
    """Build a CHILD :class:`Principal` from a verified child session token.

    No database round-trip: a child session token is backend-signed and
    self-contained (guardian-minted, with every id in the signed claims), so
    verification alone yields the principal. This keeps the child auth path
    independent of a live database read, matching the offline-session design
    (the token is valid for its full lifetime and cannot be refreshed). The
    embedded ``user_id`` is a real ``User.id`` resolved at mint time, so the
    resulting principal is still attributable on the append-only pipeline_event
    log without a lookup here.

    Args:
        token: The raw bearer token, already routed here by its child audience.

    Returns:
        Principal: A ``Role.CHILD`` principal scoped to exactly one profile.

    Raises:
        AuthenticationError: If the token fails child-session verification.
    """
    claims = verify_child_session_token(token)
    # #CRITICAL: security: a child principal is scoped to EXACTLY its one
    # profile; profile_ids is the singleton from the signed claim, never a
    # family-wide set, so authorize_profile confines every downstream read to
    # that single profile (a child cannot reach a sibling's library/reading).
    # #VERIFY: test_child_session.py::test_require_principal_child_branch_scopes
    # asserts profile_ids is the singleton; the integration suite asserts a
    # child token is 403/404 on another profile's resource.
    return Principal(
        subject=claims.subject,
        user_id=claims.user_id,
        role=Role.CHILD,
        family_id=claims.family_id,
        profile_ids=frozenset({claims.profile_id}),
    )


async def _device_principal(session: AsyncSession, token: str) -> Principal:
    """Build a DEVICE :class:`Principal` from a verified, unrevoked device grant.

    Unlike the child-session path (self-contained, deliberately DB-free), this
    performs one database read to enforce revocation. A device grant is a
    long-lived (90-day) authorization for a shared device, and its whole
    reason to be revocable (ADR-014) is to cut off a lost or stolen tablet
    before that TTL elapses. Revocation is server-authoritative state a
    self-contained token cannot carry, so the online consuming path MUST
    consult it; verifying the signature alone would let a revoked grant keep
    minting child sessions and enumerating a family's profiles until ``exp``.
    Enforcing it here, at principal resolution, means every device-consuming
    endpoint (the child-session mint, the profiles listing, and any future
    one) inherits the check and no handler can forget it.

    Args:
        session: The request database session, used for the revocation lookup.
        token: The raw bearer token, already routed here by its device
            grant audience.

    Returns:
        Principal: A ``Role.DEVICE`` principal scoped to no profiles, with
        ``user_id`` set to the minting guardian's id (the ``authorized_by``
        claim) so the principal is attributable without a further lookup,
        mirroring the child session path's ``user_id`` convention.

    Raises:
        AuthenticationError: If the token fails device-grant verification, or
            its grant row is absent (never minted, or the token predates a
            row now deleted) or carries a non-null ``revoked_at``.
    """
    claims = verify_device_grant_token(token)
    # #CRITICAL: security: revocation is enforced here, online, on the jti the
    # verified token carries. A missing row (unknown/deleted jti) or a non-null
    # revoked_at is rejected as an authentication failure BEFORE any principal
    # is built, so a revoked device cannot mint a child session or list family
    # profiles. Same-message rejection for missing vs revoked avoids a probe
    # oracle. An offline device is unaffected until it reconnects; the exposure
    # is bounded by the 90-day TTL (ADR-014, "Negative / risks").
    # #VERIFY: test_device_grants.py asserts a revoked grant yields 401 on the
    # child-session mint and the profiles listing, and an unknown jti yields 401.
    grant = await session.scalar(
        select(DeviceGrant).where(DeviceGrant.jti == claims.jti)
    )
    if grant is None or grant.revoked_at is not None:
        msg = "device grant token failed verification"
        raise AuthenticationError(msg)
    # #CRITICAL: security: a device principal carries NO profile_ids and can
    # never be admin (Principal.__post_init__ force-clears both for the DEVICE
    # role as defense in depth), so this token can never pass a guardian-only
    # or admin-only gate, and cannot pass authorize_profile for any profile.
    # #VERIFY: test_device_grant.py's require_principal routing tests assert
    # profile_ids is empty and is_admin is False, and that the guardian-only
    # dependency refuses a device token with 403.
    return Principal(
        subject=claims.subject,
        user_id=claims.authorized_by,
        role=Role.DEVICE,
        family_id=claims.family_id,
        profile_ids=frozenset(),
    )


async def _resolve_profiles(session: AsyncSession, user: User) -> frozenset[uuid.UUID]:
    """Return the set of child profiles the user may act on.

    Args:
        session: The database session.
        user: The resolved user row.

    Returns:
        frozenset[uuid.UUID]: All family profiles for a guardian (including a
            guardian who also holds the admin capability); the single assigned
            profile for a child; empty for an admin-only adult or a child
            with no assigned profile.
    """
    if user.role == Role.GUARDIAN:
        # #ASSUME: data-integrity: a deactivated kid profile (WS-J) is
        # excluded here so it disappears from every surface that derives its
        # profile set from the auth boundary (the picker, the guardian
        # console), without touching the row's history.
        # #VERIFY: tests/integration/test_admin_profiles_api.py::
        # test_deactivated_profile_excluded_from_guardian_listing.
        rows = await session.scalars(
            select(ChildProfile.id).where(
                ChildProfile.family_id == user.family_id,
                ChildProfile.deactivated_at.is_(None),
            )
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


def parse_uuid(raw: str, field: str) -> uuid.UUID:
    """Parse a UUID path or body field, raising a 422-mapped error on bad input.

    Args:
        raw: The raw string supplied by the client.
        field: The field name to report in the validation error.

    Returns:
        uuid.UUID: The parsed UUID.

    Raises:
        ValidationError: If ``raw`` is not a valid UUID.
    """
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        msg = f"{field} must be a UUID"
        raise ValidationError(msg, field=field, value=raw) from exc


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


# The single cross-family authorization message. Exported so callers that must
# make a nonexistent resource indistinguishable from a foreign-family one (e.g.
# the device-grant child-session mint, issue #249) can raise the IDENTICAL body
# without duplicating the literal and risking drift.
CROSS_FAMILY_MESSAGE = "resource belongs to another family"


def authorize_family(principal: Principal, owner_family_id: uuid.UUID) -> None:
    """Raise if a resource belongs to a different family.

    Args:
        principal: The authenticated principal.
        owner_family_id: The family that owns the resource.

    Raises:
        AuthorizationError: If the resource is owned by another family.
    """
    if principal.family_id != owner_family_id:
        raise AuthorizationError(CROSS_FAMILY_MESSAGE)


CurrentPrincipal = Annotated[Principal, Depends(require_principal)]


@dataclass(frozen=True, slots=True)
class OnboardingIdentity:
    """A fully-verified guardian identity that may not yet have a ``User`` row.

    ``require_principal`` rejects a verified token whose subject has no user row
    (``"unknown subject"`` -> 401); that is correct for every endpoint except
    first-login provisioning, which must accept exactly that case to create the
    row. This value type carries only what onboarding needs: the verified
    subject (the key) and the optional email contact claim.

    Attributes:
        subject: The verified OIDC subject (the sole identity key).
        email: The optional email contact claim (may be an Apple private-relay
            address), or ``None``. Never an identity key.
    """

    subject: str
    email: str | None


async def require_onboarding_identity(
    authorization: Annotated[str | None, Header()] = None,
) -> OnboardingIdentity:
    """Resolve a verified guardian identity for first-login provisioning.

    Unlike ``require_principal`` this does NOT require a ``User`` row to exist
    for the subject: onboarding is precisely the path that creates it. It still
    fully verifies the token (real Supabase JWT outside ``local``; trusted
    dev-stub subject in ``local``) before returning any identity, so an
    unverified or forged token is rejected exactly as elsewhere.

    Args:
        authorization: The ``Authorization`` header.

    Returns:
        OnboardingIdentity: The verified subject and optional email claim.

    Raises:
        AuthenticationError: If the token is missing, malformed, or fails OIDC
            verification (-> 401).
        AuthorizationError: If the token is a child session token; a child
            session is a reading credential, never an account-creation one, so
            it may not provision a guardian family (-> 403).
    """
    token = _extract_subject(authorization)
    # #CRITICAL: security: a child session token or a device grant must never
    # provision a guardian Family+User. Routing on the UNVERIFIED audience is
    # safe here because both branches only ever REFUSE: any token claiming
    # the child or device-grant audience is rejected outright, never used to
    # build or create anything, so reading the unverified claim cannot widen
    # access (mirrors the require_principal routing note). Guardians and
    # admins carry the Supabase audience and fall through to real
    # verification below.
    # #VERIFY: test_onboarding_identity.py::test_child_session_token_cannot_onboard
    # (unit) and test_onboarding_api.py::test_child_session_token_cannot_onboard
    # (integration) cover a child session token onboarding -> 403;
    # test_device_grant.py covers the device-grant equivalent.
    aud = unverified_audience(token)
    if aud == CHILD_SESSION_AUDIENCE:
        msg = "a child session cannot onboard a guardian account"
        raise AuthorizationError(msg)
    if aud == DEVICE_GRANT_AUDIENCE:
        msg = "a device grant cannot onboard a guardian account"
        raise AuthorizationError(msg)
    # #CRITICAL: security: the local branch trusts the bearer token as the
    # subject with NO verification and yields no email; it is reachable only
    # when environment == "local" (the dev/test auth seam documented at module
    # level). Everywhere else the token is verified as a real Supabase JWT.
    # #VERIFY: the ConfigurationError guard at import time blocks a non-local
    # process without OIDC config from ever reaching the local branch.
    if settings.environment == "local":
        return OnboardingIdentity(subject=token, email=None)
    subject, email = await _verify_oidc_identity(token)
    return OnboardingIdentity(subject=subject, email=email)


OnboardingIdentityDep = Annotated[
    OnboardingIdentity, Depends(require_onboarding_identity)
]
