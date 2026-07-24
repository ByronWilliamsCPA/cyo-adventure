"""Admin CRUD for child profiles across any family (WS-J admin user management).

Kept separate from the guardian-scoped ``api/profiles.py`` on purpose: that
module's authorization model is "any profile in MY family"
(``_require_guardian`` + the caller's own ``family_id``), while this one is
"any profile in ANY family" (admin only). Blending the two into one file
risked one guard silently widening into the other's scope.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import ColumnElement, select

from cyo_adventure.api.deps import Context, parse_uuid
from cyo_adventure.api.schemas import (
    AdminProfileCreateBody,
    AdminProfileListView,
    AdminProfileUpdateBody,
    AdminProfileView,
    error_responses,
)
from cyo_adventure.core.exceptions import AuthorizationError, ResourceNotFoundError
from cyo_adventure.core.pin import hash_pin
from cyo_adventure.db.models import ChildProfile, Family
from cyo_adventure.events import ADMIN_ACTOR_ROLE, Actor, EventType, record_event
from cyo_adventure.storybook.models import AgeBand

router = APIRouter(
    prefix="/api/v1", tags=["admin-profiles"], responses=error_responses(401, 403)
)

# Defensive ceiling mirroring families.py's _FAMILY_LIST_LIMIT convention.
_PROFILE_LIST_LIMIT = 200


def _require_admin(ctx: Context) -> None:
    """Reject non-admin callers before any read or write.

    Args:
        ctx: The request context (principal + session).

    Raises:
        AuthorizationError: If the caller is not an admin (403).
    """
    # #CRITICAL: security: this endpoint reaches ANY family's child profiles
    # (age band, reading cap, PIN); only the admin role may use it.
    # #VERIFY: tests/integration/test_admin_profiles_api.py::test_guardian_gets_403.
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg, required_permission="admin")


def _view(row: ChildProfile) -> AdminProfileView:
    """Build the response view from a ChildProfile row.

    Args:
        row: The ORM row.

    Returns:
        AdminProfileView: The wire-safe view.
    """
    # #CRITICAL: security: pin_hash is write-only credential material; the
    # view exposes only the derived has_pin bool, mirroring
    # api/profiles.py::_view.
    # #VERIFY: tests/integration/test_admin_profiles_api.py::
    # test_pin_hash_never_serialized.
    return AdminProfileView(
        id=str(row.id),
        family_id=str(row.family_id),
        display_name=row.display_name,
        age_band=AgeBand(row.age_band),
        reading_level_cap=row.reading_level_cap,
        avatar=row.avatar,
        tts_enabled=row.tts_enabled,
        has_pin=row.pin_hash is not None,
        status="deactivated" if row.deactivated_at is not None else "active",
        created_at=row.created_at,
    )


@router.get("/admin/profiles")
async def list_admin_profiles(
    ctx: Context, family_id: str | None = None
) -> AdminProfileListView:
    """List child profiles across families, optionally filtered (admin only).

    Args:
        ctx: The request context (principal + session).
        family_id: Optional family filter.

    Returns:
        AdminProfileListView: Up to ``_PROFILE_LIST_LIMIT`` matching profiles,
        including deactivated ones (the console needs to show and
        reactivate them).

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ValidationError: If ``family_id`` is not a valid UUID (422).
    """
    _require_admin(ctx)
    clauses: list[ColumnElement[bool]] = []
    if family_id is not None:
        clauses.append(ChildProfile.family_id == parse_uuid(family_id, "family_id"))
    # #EDGE: data-integrity: past _PROFILE_LIST_LIMIT matching rows the
    # console silently omits the tail; revisit with pagination before the
    # deployment outgrows a single table view.
    rows = (
        await ctx.session.scalars(
            select(ChildProfile)
            .where(*clauses)
            .order_by(ChildProfile.created_at.asc(), ChildProfile.id.asc())
            .limit(_PROFILE_LIST_LIMIT)
        )
    ).all()
    # #CRITICAL: security: this is a cross-family read of child-linked data
    # (age band, reading cap, PIN presence); unlike every other GET in this
    # API, it crosses a tenant boundary, so it is audited the same way a
    # write would be (GDPR Article 30 accountability, remediation plan
    # Phase 8a). One event per call, never one per row, so the log cannot
    # become a second copy of the data it audits access to.
    # #VERIFY: tests/integration/test_admin_profiles_api.py::
    # test_list_admin_profiles_records_profile_viewed_event.
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal, acting_role=ADMIN_ACTOR_ROLE),
        entity_type="child_profile",
        entity_id=family_id if family_id is not None else "all",
        event_type=EventType.PROFILE_VIEWED,
        payload={"family_id": family_id, "count": len(rows)},
    )
    return AdminProfileListView(profiles=[_view(row) for row in rows])


@router.post("/admin/profiles", status_code=201, responses=error_responses(404))
async def create_admin_profile(
    body: AdminProfileCreateBody, ctx: Context
) -> AdminProfileView:
    """Create a child profile in any family (admin only; WS-J).

    Args:
        body: The target family and the new profile's fields.
        ctx: The request context (principal + session).

    Returns:
        AdminProfileView: The stored profile.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ResourceNotFoundError: If the target family does not exist (404).
    """
    _require_admin(ctx)
    family_uuid = parse_uuid(body.family_id, "family_id")
    family = await ctx.session.get(Family, family_uuid)
    if family is None:
        msg = f"family '{body.family_id}' not found"
        raise ResourceNotFoundError(msg)
    row = ChildProfile(
        family_id=family_uuid,
        display_name=body.display_name,
        age_band=body.age_band.value,
        reading_level_cap=body.reading_level_cap,
        avatar=body.avatar,
        tts_enabled=body.tts_enabled,
    )
    ctx.session.add(row)
    await ctx.session.flush()
    await ctx.session.refresh(row, ["created_at"])
    return _view(row)


def _apply_non_pin_fields(row: ChildProfile, body: AdminProfileUpdateBody) -> None:
    """Apply every field except ``pin`` to the row (extracted for complexity).

    Args:
        row: The profile row to mutate in place.
        body: The requested changes.
    """
    fields = body.model_fields_set
    # #ASSUME: data-integrity: mirrors api/profiles.py::update_profile -- an
    # explicit null on the four non-avatar fields is a deliberate no-op, none
    # of them has a legitimate empty state.
    if body.display_name is not None:
        row.display_name = body.display_name
    if body.age_band is not None:
        row.age_band = body.age_band.value
    if body.reading_level_cap is not None:
        row.reading_level_cap = body.reading_level_cap
    if body.tts_enabled is not None:
        row.tts_enabled = body.tts_enabled
    if "avatar" in fields:
        row.avatar = body.avatar
    if body.status is not None:
        if body.status == "deactivated" and row.deactivated_at is None:
            row.deactivated_at = datetime.now(UTC)
        elif body.status == "active":
            row.deactivated_at = None


@router.patch("/admin/profiles/{profile_id}", responses=error_responses(404))
async def update_admin_profile(
    profile_id: str, body: AdminProfileUpdateBody, ctx: Context
) -> AdminProfileView:
    """Partially update a child profile in any family (admin only; WS-J).

    Args:
        profile_id: The profile to update (path).
        body: The fields to change; omitted fields are untouched. An explicit
            ``null`` clears only ``avatar`` and ``pin``; on the other fields
            it is a no-op (mirrors ``api/profiles.py::update_profile``).
        ctx: The request context (principal + session).

    Returns:
        AdminProfileView: The updated profile.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ResourceNotFoundError: If no profile with this id exists (404).
    """
    _require_admin(ctx)
    parsed = parse_uuid(profile_id, "profile_id")
    row = await ctx.session.get(ChildProfile, parsed)
    if row is None:
        msg = f"profile '{profile_id}' not found"
        raise ResourceNotFoundError(msg)
    _apply_non_pin_fields(row, body)
    if "pin" in body.model_fields_set:
        # #CRITICAL: timing: hash_pin runs 600k PBKDF2 iterations (100-300ms
        # of pure CPU); offloaded to a worker thread, mirroring
        # api/profiles.py::update_profile.
        if body.pin is not None:
            row.pin_hash = await asyncio.to_thread(hash_pin, body.pin)
        else:
            row.pin_hash = None
    await ctx.session.flush()
    return _view(row)
