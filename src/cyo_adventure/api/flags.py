"""Kid flag endpoints (K15): a structured, no-free-text child feedback signal.

Feeds the admin moderation queue (A1) directly (``GET /admin/flags``) and,
downstream, the guardian alert feed (G10) as a ``pipeline_event`` projection
built separately from this module. Per ADR-016's no-free-text principle, a
flag carries no child-authored text: ``reason`` is a closed vocabulary
(``KidFlagReasonLiteral``), and the schema forbids any extra field a caller
might try to smuggle prose in under.

Submission is ownership-scoped like ``ratings.py``: a guardian or a child may
flag a profile they own (``authorize_profile``), not role-gated to child
only, mirroring how a guardian can also record a rating on a child's behalf.
The book must actually be assigned to the flagging profile (the same
visibility gate ``library.py``/``ratings.py`` use), and a per-profile open-flag
cap throttles abuse, mirroring ``story_requests/service.py``'s pending-request
cap. The two admin routes (list, resolve) require the admin capability.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from fastapi import APIRouter
from sqlalchemy import func, select

from cyo_adventure.api.deps import Context, authorize_profile, parse_uuid
from cyo_adventure.api.schemas import (
    KidFlagCreateBody,
    KidFlagCreatedView,
    KidFlagListView,
    KidFlagReasonLiteral,
    KidFlagResolutionLiteral,
    KidFlagResolveBody,
    KidFlagView,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    StateTransitionError,
)
from cyo_adventure.db.models import ChildProfile, KidFlag, StorybookAssignment
from cyo_adventure.events import ADMIN_ACTOR_ROLE, Actor, EventType, record_event

router = APIRouter(prefix="/api/v1", tags=["flags"])

# Max open (unresolved) flags per profile before a new submission is refused.
# Mirrors story_requests/service.py::MAX_PENDING_PER_PROFILE: an abuse
# throttle, not a correctness invariant, sized the same as that precedent.
MAX_OPEN_FLAGS_PER_PROFILE = 5


def _to_view(flag: KidFlag) -> KidFlagView:
    """Project a KidFlag row to its wire view."""
    return KidFlagView(
        id=str(flag.id),
        family_id=str(flag.family_id),
        profile_id=str(flag.profile_id),
        storybook_id=flag.storybook_id,
        version=flag.version,
        reason=cast("KidFlagReasonLiteral", flag.reason),
        node_id=flag.node_id,
        created_at=flag.created_at,
        resolved_by=str(flag.resolved_by) if flag.resolved_by is not None else None,
        resolved_at=flag.resolved_at,
        resolution=(
            cast("KidFlagResolutionLiteral", flag.resolution)
            if flag.resolution is not None
            else None
        ),
    )


async def _count_open_flags_for_profile(ctx: Context, profile_id: object) -> int:
    """Return the number of unresolved flags for a profile.

    Args:
        ctx: The request context.
        profile_id: The child profile id.

    Returns:
        int: Count of open (``resolved_at IS NULL``) rows for the profile.
    """
    # #CRITICAL: concurrency: two concurrent submits could both read count=N-1
    # and both insert (a benign one-over race). The cap is an abuse throttle,
    # not a correctness invariant, so an occasional off-by-one is accepted;
    # mirrors story_requests/service.py::count_pending_for_profile.
    # #VERIFY: a strict guarantee would need a partial unique index or
    # advisory lock; deferred as unnecessary here, same call as story_requests.
    total = await ctx.session.scalar(
        select(func.count())
        .select_from(KidFlag)
        .where(
            KidFlag.profile_id == profile_id,
            KidFlag.resolved_at.is_(None),
        )
    )
    return total or 0


@router.post("/flags", status_code=201)
async def create_flag(body: KidFlagCreateBody, ctx: Context) -> KidFlagCreatedView:
    """Submit a child's structured flag for a storybook passage.

    Args:
        body: The profile, storybook, version, reason, and optional node id.
        ctx: The request context (principal and session).

    Returns:
        KidFlagCreatedView: The new flag's id and reason.

    Raises:
        AuthorizationError: If the caller may not act on the profile, or the
            storybook is not assigned to it (-> 403).
        ResourceNotFoundError: If the profile does not exist (-> 404).
        StateTransitionError: If the profile is at its open-flag cap (-> 409).
        ValidationError: If ``profile_id`` is not a valid UUID (-> 422).
    """
    profile_uuid = parse_uuid(body.profile_id, "profile_id")
    # #CRITICAL: security: guardian may act on any family profile, a child only
    # on its own; admin/device have no profiles so cannot submit. 403 on
    # mismatch, mirroring ratings.py::record_rating.
    # #VERIFY: test_flags_api.py::test_create_flag_wrong_profile_is_403.
    authorize_profile(ctx.principal, profile_uuid)

    profile = await ctx.session.get(ChildProfile, profile_uuid)
    if profile is None:
        msg = "profile not found"
        raise ResourceNotFoundError(msg)

    # #CRITICAL: security: a flag may only be raised against a book actually
    # assigned to (visible to) this profile, the same gate library.py and
    # ratings.py use for a child-readable book; an unassigned storybook id is
    # rejected outright rather than silently accepted (IDOR / spam guard).
    # #VERIFY: test_flags_api.py::test_create_flag_unassigned_book_is_403.
    assigned = await ctx.session.scalar(
        select(StorybookAssignment.storybook_id).where(
            StorybookAssignment.storybook_id == body.storybook_id,
            StorybookAssignment.child_profile_id == profile_uuid,
        )
    )
    if assigned is None:
        msg = "storybook is not accessible to this profile"
        raise AuthorizationError(msg, resource=body.storybook_id)

    # #CRITICAL: concurrency: enforce the per-profile open-flag cap before
    # insert; see _count_open_flags_for_profile's #CRITICAL tag for the
    # accepted race.
    # #VERIFY: test_flags_api.py::test_create_flag_cap_returns_409.
    open_count = await _count_open_flags_for_profile(ctx, profile_uuid)
    if open_count >= MAX_OPEN_FLAGS_PER_PROFILE:
        msg = "too many open flags for this profile"
        raise StateTransitionError(msg)

    flag = KidFlag(
        family_id=profile.family_id,
        profile_id=profile_uuid,
        storybook_id=body.storybook_id,
        version=body.version,
        reason=body.reason,
        node_id=body.node_id,
    )
    ctx.session.add(flag)
    await ctx.session.flush()
    # #CRITICAL: privacy: K15 + ADR-016 no-free-text -- the payload carries
    # only the closed-vocabulary reason and the storybook id, never node_id
    # (a story-graph identifier is not PII, but it is also not part of the
    # allowlisted contract) or any child-authored text.
    # #VERIFY: events/writer.py::_PAYLOAD_ALLOWLIST[EventType.KID_FLAGGED]
    # rejects any other key; tests/unit/test_flags_api.py asserts the event.
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal),
        entity_type="kid_flag",
        entity_id=str(flag.id),
        event_type=EventType.KID_FLAGGED,
        payload={"reason": flag.reason, "storybook_id": flag.storybook_id},
    )
    return KidFlagCreatedView(
        id=str(flag.id), reason=cast("KidFlagReasonLiteral", flag.reason)
    )


@router.get("/admin/flags")
async def list_open_flags(ctx: Context) -> KidFlagListView:
    """List every open (unresolved) flag across families, newest first.

    The admin moderation queue surface (A1); no guardian equivalent exists
    yet (the guardian alert feed is G10, a separate ``pipeline_event``
    projection built by a sibling workstream).

    Args:
        ctx: The request context (principal and session).

    Returns:
        KidFlagListView: Every unresolved flag, newest first.

    Raises:
        AuthorizationError: If the caller lacks the admin capability (-> 403).
    """
    # #CRITICAL: security: the admin capability gates the global, cross-family
    # scope; this runs before any row is loaded so a non-admin gets an exact
    # 403, mirroring story_requests.py::list_story_requests_admin.
    # #VERIFY: test_authz_matrix.py pins GET /api/v1/admin/flags as admin-only.
    if not ctx.principal.is_admin:
        msg = "admin access required"
        raise AuthorizationError(msg)
    rows = await ctx.session.scalars(
        select(KidFlag)
        .where(KidFlag.resolved_at.is_(None))
        .order_by(KidFlag.created_at.desc())
    )
    return KidFlagListView(flags=[_to_view(row) for row in rows.all()])


@router.post("/admin/flags/{flag_id}/resolve")
async def resolve_flag(
    flag_id: str, body: KidFlagResolveBody, ctx: Context
) -> KidFlagView:
    """Resolve one open flag (admin only).

    Args:
        flag_id: The flag id from the path.
        body: The admin's resolution decision.
        ctx: The request context.

    Returns:
        KidFlagView: The resolved flag.

    Raises:
        AuthorizationError: If the caller lacks the admin capability (-> 403).
        ResourceNotFoundError: If the flag does not exist (-> 404).
        StateTransitionError: If the flag is already resolved (-> 409).
        ValidationError: If ``flag_id`` is not a valid UUID (-> 422).
    """
    if not ctx.principal.is_admin:
        msg = "admin access required"
        raise AuthorizationError(msg)
    flag_uuid = parse_uuid(flag_id, "flag_id")
    flag = await ctx.session.get(KidFlag, flag_uuid)
    if flag is None:
        msg = f"kid flag '{flag_id}' not found"
        raise ResourceNotFoundError(msg)
    # #CRITICAL: data integrity: resolved_by/resolved_at/resolution are set
    # together, never partially (the ck_kid_flag_resolved_pairing DB CHECK is
    # the at-rest backstop); a second resolve attempt on an already-resolved
    # flag is rejected as a state conflict rather than silently overwriting
    # who resolved it and when.
    # #VERIFY: test_flags_api.py::test_resolve_already_resolved_is_409.
    if flag.resolved_at is not None:
        msg = "flag is already resolved"
        raise StateTransitionError(msg)
    flag.resolved_by = ctx.principal.user_id
    flag.resolved_at = datetime.now(UTC)
    flag.resolution = body.resolution
    await ctx.session.flush()
    await record_event(
        ctx.session,
        # Admin-only endpoint: stamp the capacity that authorized the action,
        # not a dual-role caller's guardian base persona.
        Actor.from_principal(ctx.principal, acting_role=ADMIN_ACTOR_ROLE),
        entity_type="kid_flag",
        entity_id=str(flag.id),
        event_type=EventType.FLAG_RESOLVED,
        payload={"resolution": flag.resolution},
    )
    return _to_view(flag)
