"""Admin CRUD for directional cross-family recommendation opt-ins (WS-J).

A row means "family_id has opted in to seeing recommendations sourced from
connected_family_id"; the relationship is deliberately one-way (admin
decision), so mutual visibility between two families is two rows, not one.
No recommendation engine reads this table yet: WS-J only builds the admin
allowlist (see ``db.models.FamilyConnection``'s docstring). Connections are a
permission edge, not identity data, so unlike guardians/admins/kids/families
they are hard-deleted rather than soft-deactivated (mirrors
``ProviderModelAllowlist`` rows, which are also truly deleted).
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from cyo_adventure.api.deps import Context, parse_uuid
from cyo_adventure.api.schemas import (
    FamilyConnectionCreateBody,
    FamilyConnectionListView,
    FamilyConnectionView,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
from cyo_adventure.db.models import Family, FamilyConnection
from cyo_adventure.events import ADMIN_ACTOR_ROLE, Actor, EventType, record_event

router = APIRouter(prefix="/api/v1", tags=["family-connections"])


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


@router.post("/admin/family-connections", status_code=201)
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


@router.delete("/admin/family-connections/{connection_id}", status_code=204)
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
