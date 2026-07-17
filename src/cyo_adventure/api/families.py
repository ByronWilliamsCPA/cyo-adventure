"""Admin-only family management (WS-B PR 2; WS-J admin user management).

The original listing endpoint powers the required family selector on the
admin authored-request form (decision B3: admin-initiated requests must name
a family). WS-J adds create/rename/deactivate so an admin can manage the
family roster from the new `/admin/users` console without going through the
Supabase JIT onboarding path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter
from sqlalchemy import func, select

from cyo_adventure.api.deps import Context, parse_uuid
from cyo_adventure.api.schemas import (
    FamilyCreateBody,
    FamilyListView,
    FamilyUpdateBody,
    FamilyView,
)
from cyo_adventure.core.exceptions import AuthorizationError, ResourceNotFoundError
from cyo_adventure.db.models import ChildProfile, Family, User
from cyo_adventure.events import ADMIN_ACTOR_ROLE, Actor, EventType, record_event

if TYPE_CHECKING:
    import uuid

router = APIRouter(prefix="/api/v1", tags=["families"])

# Defensive ceiling mirroring generation.py's _JOB_LIST_LIMIT convention: the
# admin form renders every row into one <select>, so an unbounded roster would
# degrade both the query and the DOM as tenants grow.
_FAMILY_LIST_LIMIT = 50

_MEMBER_ROLES = ("guardian", "admin")


def _require_admin(ctx: Context) -> None:
    """Reject non-admin callers before any read or write.

    Args:
        ctx: The request context (principal + session).

    Raises:
        AuthorizationError: If the caller is not an admin (403).
    """
    # #CRITICAL: security: the full family roster (and any mutation of it) is
    # cross-tenant data/action; only the admin role may reach it.
    # #VERIFY: test_admin_lists_families_guardian_forbidden asserts 403 for a
    # guardian token; test_families_api.py mirrors it for the new routes.
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg)


async def _counts_for(
    ctx: Context, family_ids: list[uuid.UUID]
) -> tuple[dict[uuid.UUID, int], dict[uuid.UUID, int]]:
    """Return (guardian+admin count, kid-profile count) per family id.

    Counts every member row regardless of status/deactivation, so an admin
    reviewing the roster sees the family's full membership, not just its
    currently-active slice.

    Args:
        ctx: The request context (principal + session).
        family_ids: The families to count members for.

    Returns:
        tuple[dict, dict]: Two family_id -> count maps (guardians/admins,
        kid profiles); a family with zero members is simply absent from the
        relevant map (the caller treats a missing key as zero).
    """
    if not family_ids:
        return {}, {}
    guardian_rows = await ctx.session.execute(
        select(User.family_id, func.count(User.id))
        .where(User.family_id.in_(family_ids), User.role.in_(_MEMBER_ROLES))
        .group_by(User.family_id)
    )
    kid_rows = await ctx.session.execute(
        select(ChildProfile.family_id, func.count(ChildProfile.id))
        .where(ChildProfile.family_id.in_(family_ids))
        .group_by(ChildProfile.family_id)
    )
    guardian_counts = {row[0]: row[1] for row in guardian_rows.all()}
    kid_counts = {row[0]: row[1] for row in kid_rows.all()}
    return guardian_counts, kid_counts


def _view(family: Family, *, guardian_count: int, kid_count: int) -> FamilyView:
    """Build the response view for one family row.

    Args:
        family: The ORM row.
        guardian_count: Precomputed member count (guardians + admins).
        kid_count: Precomputed member count (child profiles).

    Returns:
        FamilyView: The wire-safe view.
    """
    return FamilyView(
        id=str(family.id),
        name=family.name,
        status="deactivated" if family.deactivated_at is not None else "active",
        guardian_count=guardian_count,
        kid_count=kid_count,
        created_at=family.created_at,
    )


@router.get("/admin/families")
async def list_families(ctx: Context) -> FamilyListView:
    """List families (name order, capped) for the admin console.

    Args:
        ctx: The request context (principal and session).

    Returns:
        FamilyListView: Up to ``_FAMILY_LIST_LIMIT`` families ordered by name.

    Raises:
        AuthorizationError: If the caller is not an admin (-> 403).
    """
    _require_admin(ctx)
    # #EDGE: data-integrity: past _FAMILY_LIST_LIMIT families the selector
    # silently omits the tail; revisit with pagination or search before the
    # deployment outgrows a single dropdown.
    # #VERIFY: test_admin_families_list_is_name_ordered_and_capped.
    rows = (
        await ctx.session.scalars(
            select(Family)
            .order_by(Family.name.asc(), Family.id.asc())
            .limit(_FAMILY_LIST_LIMIT)
        )
    ).all()
    guardian_counts, kid_counts = await _counts_for(ctx, [f.id for f in rows])
    return FamilyListView(
        families=[
            _view(
                f,
                guardian_count=guardian_counts.get(f.id, 0),
                kid_count=kid_counts.get(f.id, 0),
            )
            for f in rows
        ]
    )


@router.post("/admin/families", status_code=201)
async def create_family(body: FamilyCreateBody, ctx: Context) -> FamilyView:
    """Create a family (admin only; WS-J).

    Args:
        body: The new family's name.
        ctx: The request context (principal and session).

    Returns:
        FamilyView: The stored family (zero members).

    Raises:
        AuthorizationError: If the caller is not an admin (-> 403).
    """
    _require_admin(ctx)
    family = Family(name=body.name)
    ctx.session.add(family)
    await ctx.session.flush()
    await ctx.session.refresh(family, ["created_at"])
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal, acting_role=ADMIN_ACTOR_ROLE),
        entity_type="family",
        entity_id=str(family.id),
        event_type=EventType.FAMILY_MANAGED,
        payload={"action": "created", "status": "active"},
    )
    return _view(family, guardian_count=0, kid_count=0)


@router.patch("/admin/families/{family_id}")
async def update_family(
    family_id: str, body: FamilyUpdateBody, ctx: Context
) -> FamilyView:
    """Rename and/or change a family's active/deactivated status (WS-J).

    Deactivating a family cascades: every member ``User`` (guardian or admin)
    and ``ChildProfile`` in it is deactivated in the same transaction, so the
    auth boundary (``api/deps.py::require_principal``) only ever needs to
    check ``User.status`` and never a family join. Reactivating a family does
    **not** auto-reactivate its members; an admin reactivates people
    individually (deliberate asymmetry).

    Args:
        family_id: The family to update (path).
        body: The fields to change; omitted fields are untouched.
        ctx: The request context (principal and session).

    Returns:
        FamilyView: The updated family with refreshed member counts.

    Raises:
        AuthorizationError: If the caller is not an admin (-> 403).
        ResourceNotFoundError: If no family with this id exists (-> 404).
    """
    _require_admin(ctx)
    parsed = parse_uuid(family_id, "family_id")
    family = await ctx.session.get(Family, parsed)
    if family is None:
        msg = f"family '{family_id}' not found"
        raise ResourceNotFoundError(msg)

    action = "updated"
    if body.name is not None:
        family.name = body.name
    if body.status == "deactivated" and family.deactivated_at is None:
        now = datetime.now(UTC)
        family.deactivated_at = now
        action = "deactivated"
        # #CRITICAL: data-integrity: cascading here (rather than teaching
        # every family-scoped query to also check family.deactivated_at) is
        # what keeps require_principal's hot path a single-column check.
        # Loaded and mutated per-row (never a bulk Core UPDATE) so any
        # already-loaded ORM object for a member of this family elsewhere in
        # the same unit of work stays in sync rather than going stale.
        # #VERIFY: tests/integration/test_families_api.py::
        # test_deactivate_family_cascades_to_members_and_blocks_login.
        members = await ctx.session.scalars(
            select(User).where(User.family_id == parsed, User.status != "deactivated")
        )
        for member in members:
            member.status = "deactivated"
        kids = await ctx.session.scalars(
            select(ChildProfile).where(
                ChildProfile.family_id == parsed,
                ChildProfile.deactivated_at.is_(None),
            )
        )
        for kid in kids:
            kid.deactivated_at = now
    elif body.status == "active" and family.deactivated_at is not None:
        family.deactivated_at = None
        action = "reactivated"
    await ctx.session.flush()
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal, acting_role=ADMIN_ACTOR_ROLE),
        entity_type="family",
        entity_id=str(parsed),
        event_type=EventType.FAMILY_MANAGED,
        payload={
            "action": action,
            "status": "deactivated" if family.deactivated_at is not None else "active",
        },
    )
    guardian_counts, kid_counts = await _counts_for(ctx, [parsed])
    return _view(
        family,
        guardian_count=guardian_counts.get(parsed, 0),
        kid_count=kid_counts.get(parsed, 0),
    )
