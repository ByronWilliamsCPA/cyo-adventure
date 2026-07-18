"""Device grant management endpoints (ADR-014 phase 1).

A guardian (or admin) mints a durable, family-scoped device grant that lets a
shared device authorize a child to read without a live guardian Supabase
session; see ``core/device_grant.py`` for the trust model and
``api/deps.py::require_principal``'s third routing branch for the verifying
side. This module is management-only: minting, listing, and revoking a
grant. The resulting device principal is wired into the child-session mint
and the profiles endpoint as an additional authority in ``api/deps.py``;
a revocation set here is enforced online by that module's device branch,
which rejects a revoked grant before any handler runs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import func, select

from cyo_adventure.api.deps import Context, parse_uuid
from cyo_adventure.api.schemas import (
    DeviceGrantCreateBody,
    DeviceGrantListItem,
    DeviceGrantView,
    error_responses,
)
from cyo_adventure.core.device_grant import mint_device_grant_token
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import DeviceGrant, Family
from cyo_adventure.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1", tags=["device-grants"], responses=error_responses(401, 403)
)

# The role gate shared by every endpoint here: only a guardian (own family) or
# an admin may manage device grants. Defined once so the three endpoints cannot
# drift on the rejection message.
_ADULT_ROLE_REQUIRED = "guardian or admin role required"


@router.post("/device-grants", status_code=201, responses=error_responses(404))
async def create_device_grant(
    ctx: Context, body: DeviceGrantCreateBody | None = None
) -> DeviceGrantView:
    """Mint a device grant for a family (guardian or admin only).

    Args:
        ctx: The request context (principal and session).
        body: The optional target family id (admin only; a guardian must
            omit it) and an optional guardian-facing device label. Mirrors
            ``onboarding.py::onboard``'s ``body: OnboardingBody | None = None``
            pattern: every field is itself optional, so an entirely absent
            request body (no ``Content-Type``, not just ``{}``) is also
            valid, not just a 422.

    Returns:
        DeviceGrantView: The signed token, its expiry, and the grant record.
        The token is returned ONLY here; ``GET /device-grants`` never
        includes it.

    Raises:
        AuthorizationError: If a device or child principal reaches this
            endpoint, or a guardian names a family other than its own
            (-> 403).
        ResourceNotFoundError: If an admin-named family does not exist
            (-> 404).
        ValidationError: If an admin-only caller omits ``family_id``, or the
            supplied id is malformed (-> 422).
    """
    # #CRITICAL: security: only a guardian (own family) or an admin may mint
    # a device grant; a child or an already-authorized device principal must
    # never mint one for itself or anyone else (a device principal fails this
    # check because Role.DEVICE is neither guardian nor admin, and
    # Principal.__post_init__ force-clears is_admin for it). This role gate
    # runs before any lookup, so a disallowed token is rejected with an exact
    # 403.
    # #VERIFY: test_device_grants.py::test_device_cannot_mint_device_grant and
    # ::test_child_cannot_mint_device_grant assert 403.
    if not (ctx.principal.is_guardian or ctx.principal.is_admin):
        msg = _ADULT_ROLE_REQUIRED
        raise AuthorizationError(msg)

    # An absent body is equivalent to an empty one: every field is optional,
    # so a caller minting for its own family with no label needs to send
    # nothing at all (see the docstring's onboarding.py parallel).
    body = body or DeviceGrantCreateBody()
    family_id = await _resolve_target_family(ctx, body)

    # #CRITICAL: data integrity: the token's jti and the device_grants row's
    # jti must agree, since revocation is enforced by looking up this jti;
    # generating it once here and using it for both the mint and the insert
    # keeps them from ever drifting apart.
    # #VERIFY: test_device_grants.py::test_mint_persists_matching_jti.
    jti = uuid.uuid4()
    token, expires_at = mint_device_grant_token(
        family_id=family_id,
        authorized_by=ctx.principal.user_id,
        jti=jti,
    )
    # #CRITICAL: data integrity: persist the SAME expiry the token was signed
    # with (mint_device_grant_token returns it) so the row's expires_at and the
    # JWT's exp cannot drift; the active-device list relies on this column to
    # exclude expired-but-unrevoked ghosts (#252).
    # #VERIFY: test_device_grants.py::test_mint_persists_matching_jti asserts the
    # persisted expires_at is non-null and in the future.
    grant = DeviceGrant(
        family_id=family_id,
        authorized_by=ctx.principal.user_id,
        label=body.label,
        jti=jti,
        expires_at=expires_at,
    )
    ctx.session.add(grant)
    await ctx.session.flush()

    logger.info(
        "device_grant.minted",
        family_id=str(family_id),
        grant_id=str(grant.id),
    )
    return DeviceGrantView(
        id=str(grant.id),
        token=token,
        expires_at=expires_at,
        family_id=str(family_id),
        authorized_by=str(ctx.principal.user_id),
    )


async def _resolve_target_family(
    ctx: Context, body: DeviceGrantCreateBody
) -> uuid.UUID:
    """Resolve the family a device grant targets, enforcing the admin/guardian split.

    Mirrors ``story_requests.py``'s ``_resolve_target_family``: a guardian
    must omit ``family_id`` (it always resolves to their own family) and an
    admin-only caller must supply it (an admin has no family of its own to
    default to). A dual-role adult (guardian AND admin) may either omit it
    (own family) or name their own family explicitly.

    Args:
        ctx: The request context (principal and session).
        body: The create body.

    Returns:
        uuid.UUID: The resolved target family.

    Raises:
        AuthorizationError: If a caller without the admin capability names a
            family other than their own (-> 403).
        ResourceNotFoundError: If an admin-named family does not exist.
        ValidationError: If an admin-only caller omits ``family_id``, or the
            supplied id is malformed.
    """
    # #CRITICAL: security: a guardian without the admin capability can never
    # mint into another family: naming a foreign family_id is 403 outright
    # (existence is not probed first, so this is not a family-id oracle), and
    # an omitted family_id always resolves to the caller's own family.
    # #VERIFY: test_device_grants.py::test_guardian_foreign_family_is_403,
    # ::test_guardian_may_name_own_family, ::test_admin_requires_family_id.
    if body.family_id is None:
        if not ctx.principal.is_guardian:
            msg = "family_id is required for admin-initiated device grants"
            raise ValidationError(msg, field="family_id", value=None)
        return ctx.principal.family_id
    family_uuid = parse_uuid(body.family_id, "family_id")
    if family_uuid == ctx.principal.family_id and ctx.principal.is_guardian:
        return family_uuid
    if not ctx.principal.is_admin:
        msg = "family_id is not accessible to this principal"
        raise AuthorizationError(msg, resource=body.family_id)
    family = await ctx.session.get(Family, family_uuid)
    if family is None:
        msg = "family not found"
        raise ResourceNotFoundError(msg)
    return family_uuid


@router.get("/device-grants")
async def list_device_grants(ctx: Context) -> list[DeviceGrantListItem]:
    """List the caller's family's currently-active device grants.

    Never returns the token (it is returned only once, at mint time). Scoped
    to the caller's own family for both a guardian and an admin; unlike the
    mint endpoint, an admin does not get a cross-family override here (no
    ``family_id`` filter is accepted), since a device-list view is a
    per-family, guardian-facing surface, not a global admin one.

    Args:
        ctx: The request context (principal and session).

    Returns:
        list[DeviceGrantListItem]: The family's non-revoked device grants.

    Raises:
        AuthorizationError: If a device or child principal reaches this
            endpoint (-> 403).
    """
    # #CRITICAL: security: family-scoped read. The WHERE pins family_id to the
    # authenticated principal's own family (never a client-supplied value), and
    # an admin gets NO cross-family override here, so one family's device list
    # can never leak into another's.
    # #VERIFY: test_device_grants.py family-scoping + test_child_cannot_list.
    # #ASSUME: data-integrity: a grant is active iff revoked_at IS NULL AND it
    # has not yet expired, so the list reflects only grants the online path
    # would still honor: a revoked row drops out (deps.py::_device_principal
    # rejects it), and an expired-but-unrevoked ghost drops out too (its JWT no
    # longer verifies, so it can mint nothing), keeping "present == usable"
    # (#252). now() is the DB clock, matching created_at's server_default.
    # #VERIFY: test_device_grants.py "revoked grant is absent" + "expired
    # unrevoked grant is absent from the list".
    if not (ctx.principal.is_guardian or ctx.principal.is_admin):
        msg = _ADULT_ROLE_REQUIRED
        raise AuthorizationError(msg)
    rows = await ctx.session.scalars(
        select(DeviceGrant)
        .where(
            DeviceGrant.family_id == ctx.principal.family_id,
            DeviceGrant.revoked_at.is_(None),
            DeviceGrant.expires_at > func.now(),
        )
        .order_by(DeviceGrant.created_at.desc())
    )
    return [
        DeviceGrantListItem(
            id=str(row.id),
            label=row.label,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.delete(
    "/device-grants/{grant_id}", status_code=204, responses=error_responses(404)
)
async def revoke_device_grant(grant_id: uuid.UUID, ctx: Context) -> None:
    """Revoke a device grant belonging to the caller's family.

    Sets ``revoked_at``; the row is kept (not deleted) so the jti stays a
    stable revocation record. Revocation is enforced only on the online path
    (``deps.py::_device_principal`` rejects a grant whose ``revoked_at`` is
    set before building the principal); an already-offline device is not
    affected until it reconnects (ADR-014, "Negative / risks").

    Args:
        grant_id: The device grant's id (path).
        ctx: The request context (principal and session).

    Raises:
        AuthorizationError: If a device or child principal reaches this
            endpoint (-> 403).
        ResourceNotFoundError: If no grant with ``grant_id`` exists in the
            caller's own family (-> 404). Deliberately the same 404 whether
            the id does not exist at all or belongs to another family, so
            this is not a cross-family existence oracle.
    """
    # #CRITICAL: security: this endpoint arms the ONLY enforced revocation path.
    # Setting revoked_at is what makes deps.py::_device_principal reject the
    # grant on its next online use; until then an offline device keeps working
    # (ADR-014 accepted risk). The family_id check ties the target to the
    # caller's own family and returns the SAME 404 for "no such grant" and
    # "another family's grant", so this is not a cross-family existence oracle.
    # #VERIFY: test_device_grants.py revoke-then-401 + cross-family 404 tests.
    if not (ctx.principal.is_guardian or ctx.principal.is_admin):
        msg = _ADULT_ROLE_REQUIRED
        raise AuthorizationError(msg)
    grant = await ctx.session.get(DeviceGrant, grant_id)
    if grant is None or grant.family_id != ctx.principal.family_id:
        msg = "device grant not found"
        raise ResourceNotFoundError(msg)
    # #CRITICAL: data-integrity: only stamp revoked_at on the FIRST revoke. A
    # duplicate or double-submitted DELETE must be an idempotent no-op that
    # preserves the original revocation instant, which is the stable record
    # this column exists to hold; without the guard a re-revoke silently moves
    # the timestamp forward and loses when the grant was actually revoked. The
    # response stays 204 either way, so revoke remains idempotent.
    # #VERIFY: test_device_grants.py double-revoke preserves the first timestamp.
    if grant.revoked_at is None:
        grant.revoked_at = datetime.now(UTC)
        logger.info(
            "device_grant.revoked",
            family_id=str(ctx.principal.family_id),
            grant_id=str(grant_id),
        )
