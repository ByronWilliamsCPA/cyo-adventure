"""Admin CRUD, plus guardian consent, for directional family connections.

A row means "family_id has opted in to seeing recommendations sourced from
connected_family_id"; the relationship is deliberately one-way (admin
decision), so mutual visibility between two families is two rows, not one.
Connections are a permission edge, not identity data, so unlike guardians/
admins/kids/families they are hard-deleted rather than soft-deactivated
(mirrors ``ProviderModelAllowlist`` rows, which are also truly deleted).

ADR-016 (register G17) adds the guardian consent half the admin CRUD above
deliberately withheld: an admin-created row is a permission edge only, never
consent, so ``api/recommendations.py`` (K17) must not read it until BOTH the
viewer-side and sharer-side guardian have actively consented. The consent
endpoints below let either side's guardian set or revoke their own side;
admin action never substitutes for either (register A15).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from cyo_adventure.api.deps import Context, parse_uuid
from cyo_adventure.api.schemas import (
    FamilyConnectionCreateBody,
    FamilyConnectionListView,
    FamilyConnectionMineItem,
    FamilyConnectionMineListView,
    FamilyConnectionView,
    error_responses,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
from cyo_adventure.db.models import Family, FamilyConnection
from cyo_adventure.events import ADMIN_ACTOR_ROLE, Actor, EventType, record_event

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/api/v1",
    tags=["family-connections"],
    responses=error_responses(401, 403),
)


def _require_admin(ctx: Context) -> None:
    """Reject non-admin callers before any read or write.

    Args:
        ctx: The request context (principal + session).

    Raises:
        AuthorizationError: If the caller is not an admin (403).
    """
    # #CRITICAL: security: a connection controls which family's stories may be
    # recommended to another; only the admin role may curate it.
    # #VERIFY: tests/integration/test_family_connections_api.py::
    # test_guardian_gets_403.
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg, required_permission="admin")


@router.get("/admin/family-connections")
async def list_family_connections(ctx: Context) -> FamilyConnectionListView:
    """List every directional family connection, with both family names.

    Args:
        ctx: The request context (principal + session).

    Returns:
        FamilyConnectionListView: Every connection row, ordered for stable
        display.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
    """
    _require_admin(ctx)
    viewer = aliased(Family)
    source = aliased(Family)
    rows = await ctx.session.execute(
        select(FamilyConnection, viewer.name, source.name)
        .join(viewer, viewer.id == FamilyConnection.family_id)
        .join(source, source.id == FamilyConnection.connected_family_id)
        .order_by(viewer.name.asc(), source.name.asc(), FamilyConnection.id.asc())
    )
    return FamilyConnectionListView(
        connections=[
            FamilyConnectionView(
                id=str(conn.id),
                family_id=str(conn.family_id),
                family_name=family_name,
                connected_family_id=str(conn.connected_family_id),
                connected_family_name=connected_family_name,
                created_at=conn.created_at,
            )
            for conn, family_name, connected_family_name in rows.all()
        ]
    )


@router.post(
    "/admin/family-connections", status_code=201, responses=error_responses(404, 409)
)
async def create_family_connection(
    body: FamilyConnectionCreateBody, ctx: Context
) -> FamilyConnectionView:
    """Opt one family in to another's recommendations (admin only; WS-J).

    Args:
        body: The viewer family and the recommendation-source family.
        ctx: The request context (principal + session).

    Returns:
        FamilyConnectionView: The created connection.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ValidationError: If either id is not a UUID, or they are equal (422).
        ResourceNotFoundError: If either family does not exist (404).
        StateTransitionError: If this exact directional pair already exists
            (409).
    """
    _require_admin(ctx)
    family_uuid = parse_uuid(body.family_id, "family_id")
    connected_uuid = parse_uuid(body.connected_family_id, "connected_family_id")
    if family_uuid == connected_uuid:
        msg = "a family cannot connect to itself"
        raise ValidationError(msg, field="connected_family_id", value=body.family_id)
    family = await ctx.session.get(Family, family_uuid)
    if family is None:
        msg = f"family_id '{family_uuid}' not found"
        raise ResourceNotFoundError(msg)
    connected_family = await ctx.session.get(Family, connected_uuid)
    if connected_family is None:
        msg = f"connected_family_id '{connected_uuid}' not found"
        raise ResourceNotFoundError(msg)
    existing = await ctx.session.scalar(
        select(FamilyConnection).where(
            FamilyConnection.family_id == family_uuid,
            FamilyConnection.connected_family_id == connected_uuid,
        )
    )
    if existing is not None:
        msg = "this connection already exists"
        raise StateTransitionError(msg)
    row = FamilyConnection(
        family_id=family_uuid,
        connected_family_id=connected_uuid,
        created_by=ctx.principal.user_id,
    )
    ctx.session.add(row)
    # #CRITICAL: concurrency: the pre-check above can be raced; the
    # uq_family_connection_pair unique constraint is the real guard. Map its
    # IntegrityError to the same 409 the pre-check returns, mirroring
    # provider_allowlist.py's add_allowlist_entry.
    # #VERIFY: tests/integration/test_family_connections_api.py::
    # test_duplicate_connection_race_is_409.
    try:
        await ctx.session.flush()
    except IntegrityError as exc:
        msg = "this connection already exists"
        raise StateTransitionError(msg) from exc
    await ctx.session.refresh(row, ["created_at"])
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal, acting_role=ADMIN_ACTOR_ROLE),
        entity_type="family_connection",
        entity_id=str(row.id),
        event_type=EventType.FAMILY_CONNECTION_CHANGED,
        payload={"action": "created", "connected_family_id": str(connected_uuid)},
    )
    return FamilyConnectionView(
        id=str(row.id),
        family_id=str(family_uuid),
        family_name=family.name,
        connected_family_id=str(connected_uuid),
        connected_family_name=connected_family.name,
        created_at=row.created_at,
    )


@router.delete(
    "/admin/family-connections/{connection_id}",
    status_code=204,
    responses=error_responses(404),
)
async def delete_family_connection(connection_id: str, ctx: Context) -> None:
    """Hard-delete a family connection (admin only; WS-J).

    Unlike a guardian/admin/kid/family removal, this is a real delete: a
    connection is a permission edge, not identity data with history worth
    preserving (mirrors ``provider_allowlist``'s DELETE route).

    Args:
        connection_id: The connection to delete (path).
        ctx: The request context (principal + session).

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ResourceNotFoundError: If no connection with this id exists (404).
    """
    _require_admin(ctx)
    parsed = parse_uuid(connection_id, "connection_id")
    row = await ctx.session.get(FamilyConnection, parsed)
    if row is None:
        msg = f"family connection '{connection_id}' not found"
        raise ResourceNotFoundError(msg)
    connected_family_id = str(row.connected_family_id)
    await ctx.session.delete(row)
    await ctx.session.flush()
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal, acting_role=ADMIN_ACTOR_ROLE),
        entity_type="family_connection",
        entity_id=connection_id,
        event_type=EventType.FAMILY_CONNECTION_CHANGED,
        payload={"action": "removed", "connected_family_id": connected_family_id},
    )


# ---------------------------------------------------------------------------
# Guardian consent (ADR-016, register G17). Below this point every route is
# scoped to the caller's OWN family via ctx.principal.family_id; there is no
# path/query id that lets one family read or act on another's consent state.
# ---------------------------------------------------------------------------


def _require_guardian(ctx: Context) -> None:
    """Reject non-guardian callers before any consent read or write.

    Args:
        ctx: The request context (principal + session).

    Raises:
        AuthorizationError: If the caller does not hold the guardian base
            role (403).
    """
    # #CRITICAL: security: ADR-016 requires ACTIVE GUARDIAN approval on both
    # sides; an admin-only adult (even one who created the row) may not stand
    # in for a family's guardian, so this is a base-role gate, not an
    # is_admin bypass (mirrors profiles.py rejecting admin-only from
    # guardian-scoped family actions).
    # #VERIFY: tests/unit/test_family_connections_consent_unit.py::
    # test_admin_only_principal_is_rejected_from_consent.
    if not ctx.principal.is_guardian:
        msg = "guardian role required"
        raise AuthorizationError(msg, required_permission="guardian")


def _resolve_side(
    connection: FamilyConnection, family_id: uuid.UUID
) -> Literal["viewer", "sharer"]:
    """Return which side of a directional connection the caller's family is.

    Args:
        connection: The connection row.
        family_id: The caller's own family id (``ctx.principal.family_id``).

    Returns:
        Literal["viewer", "sharer"]: ``"viewer"`` when the caller's family is
        ``connection.family_id`` (it would see the counterpart's
        recommendations); ``"sharer"`` when it is ``connected_family_id``.

    Raises:
        AuthorizationError: If the caller's family is on neither side (403).
    """
    # #CRITICAL: security: this is the sole cross-family gate on the three
    # consent routes below; a family that is neither the viewer nor the
    # sharer of a connection id it guesses must get exactly 403, never a
    # state mutation or another family's consent detail.
    # #VERIFY: tests/unit/test_family_connections_consent_unit.py::
    # test_unrelated_family_gets_403_on_consent.
    if connection.family_id == family_id:
        return "viewer"
    if connection.connected_family_id == family_id:
        return "sharer"
    msg = "connection does not belong to your family"
    raise AuthorizationError(msg)


async def _mine_item(
    session: AsyncSession, connection: FamilyConnection, family_id: uuid.UUID
) -> FamilyConnectionMineItem:
    """Build one ``FamilyConnectionMineItem`` from the caller's side of a row.

    Args:
        session: The request session.
        connection: The connection row.
        family_id: The caller's own family id.

    Returns:
        FamilyConnectionMineItem: The row's counterpart name, the caller's
        own consent state, and whether the connection is active (both sides
        consented).
    """
    side = _resolve_side(connection, family_id)
    counterpart_id = (
        connection.connected_family_id if side == "viewer" else connection.family_id
    )
    counterpart = await session.get(Family, counterpart_id)
    # #ASSUME: data integrity: counterpart_id is FK-enforced (ck_* / the
    # family_connection_*_fkey constraints), so this should always resolve; a
    # defensive fallback avoids a 500 over a hand-edited or racing delete.
    # #VERIFY: tests/unit/test_family_connections_consent_unit.py::
    # test_missing_counterpart_family_degrades_gracefully.
    counterpart_name = counterpart.name if counterpart is not None else "Unknown family"
    my_consent = (
        connection.consented_by_viewer_user_id is not None
        if side == "viewer"
        else connection.consented_by_sharer_user_id is not None
    )
    active = _is_active(connection)
    return FamilyConnectionMineItem(
        id=str(connection.id),
        direction=side,
        counterpart_family_id=str(counterpart_id),
        counterpart_family_name=counterpart_name,
        my_consent=my_consent,
        active=active,
        created_at=connection.created_at,
    )


def _is_active(connection: FamilyConnection) -> bool:
    """Return whether a connection is ACTIVE (ADR-016: both sides consented).

    Args:
        connection: The connection row.

    Returns:
        bool: ``True`` only when both ``consented_by_viewer_user_id`` and
        ``consented_by_sharer_user_id`` are set. This is deliberately
        recomputed here rather than stored, so a revoked side (set back to
        ``None``) deactivates the connection the instant it is read, with no
        separate flag that could fall out of sync.
    """
    return (
        connection.consented_by_viewer_user_id is not None
        and connection.consented_by_sharer_user_id is not None
    )


@router.get("/family-connections/mine")
async def list_my_family_connections(ctx: Context) -> FamilyConnectionMineListView:
    """List every connection touching the caller's family, from their side.

    Args:
        ctx: The request context (principal + session).

    Returns:
        FamilyConnectionMineListView: One item per connection where the
        caller's family is the viewer or the sharer.

    Raises:
        AuthorizationError: If the caller does not hold the guardian role
            (403).
    """
    _require_guardian(ctx)
    family_id = ctx.principal.family_id
    rows = await ctx.session.scalars(
        select(FamilyConnection)
        .where(
            or_(
                FamilyConnection.family_id == family_id,
                FamilyConnection.connected_family_id == family_id,
            )
        )
        .order_by(FamilyConnection.created_at.asc(), FamilyConnection.id.asc())
    )
    items = [await _mine_item(ctx.session, row, family_id) for row in rows]
    return FamilyConnectionMineListView(connections=items)


@router.post("/family-connections/{connection_id}/consent")
async def consent_family_connection(
    connection_id: str, ctx: Context
) -> FamilyConnectionMineItem:
    """Record the caller's guardian consent for their side of a connection.

    Args:
        connection_id: The connection to consent to (path).
        ctx: The request context (principal + session).

    Returns:
        FamilyConnectionMineItem: The connection's updated state from the
        caller's side.

    Raises:
        AuthorizationError: If the caller does not hold the guardian role, or
            their family is on neither side of the connection (403).
        ResourceNotFoundError: If no connection with this id exists (404).
    """
    _require_guardian(ctx)
    parsed = parse_uuid(connection_id, "connection_id")
    row = await ctx.session.get(FamilyConnection, parsed)
    if row is None:
        msg = f"family connection '{connection_id}' not found"
        raise ResourceNotFoundError(msg)
    side = _resolve_side(row, ctx.principal.family_id)
    now = datetime.now(UTC)
    if side == "viewer":
        row.consented_by_viewer_user_id = ctx.principal.user_id
        row.consented_by_viewer_at = now
    else:
        row.consented_by_sharer_user_id = ctx.principal.user_id
        row.consented_by_sharer_at = now
    await ctx.session.flush()
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal),
        entity_type="family_connection",
        entity_id=connection_id,
        event_type=EventType.FAMILY_CONNECTION_CHANGED,
        payload={
            "action": "consent_granted",
            "connected_family_id": str(row.connected_family_id),
            "role": side,
            "active": _is_active(row),
        },
    )
    return await _mine_item(ctx.session, row, ctx.principal.family_id)


@router.delete("/family-connections/{connection_id}/consent")
async def revoke_family_connection_consent(
    connection_id: str, ctx: Context
) -> FamilyConnectionMineItem:
    """Revoke the caller's guardian consent for their side of a connection.

    ADR-016: revoking either side deactivates the connection immediately.
    ``api/recommendations.py`` (K17) re-derives ``active`` from these same
    two columns on every read (never a cached flag), so the deactivation is
    visible on the very next recommendation fetch, not after some delay.

    Args:
        connection_id: The connection to revoke consent on (path).
        ctx: The request context (principal + session).

    Returns:
        FamilyConnectionMineItem: The connection's updated state from the
        caller's side.

    Raises:
        AuthorizationError: If the caller does not hold the guardian role, or
            their family is on neither side of the connection (403).
        ResourceNotFoundError: If no connection with this id exists (404).
    """
    _require_guardian(ctx)
    parsed = parse_uuid(connection_id, "connection_id")
    row = await ctx.session.get(FamilyConnection, parsed)
    if row is None:
        msg = f"family connection '{connection_id}' not found"
        raise ResourceNotFoundError(msg)
    side = _resolve_side(row, ctx.principal.family_id)
    if side == "viewer":
        row.consented_by_viewer_user_id = None
        row.consented_by_viewer_at = None
    else:
        row.consented_by_sharer_user_id = None
        row.consented_by_sharer_at = None
    await ctx.session.flush()
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal),
        entity_type="family_connection",
        entity_id=connection_id,
        event_type=EventType.FAMILY_CONNECTION_CHANGED,
        payload={
            "action": "consent_revoked",
            "connected_family_id": str(row.connected_family_id),
            "role": side,
            "active": False,
        },
    )
    return await _mine_item(ctx.session, row, ctx.principal.family_id)
