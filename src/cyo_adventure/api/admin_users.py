"""Admin CRUD for guardian/admin accounts across every family (WS-J).

Creating a user here always creates a ``status="pending"`` invite (a
synthetic placeholder ``authn_subject``, no real login yet); it becomes
``active`` when that email signs in via Supabase for the first time
(``api/onboarding.py::_bind_pending_invite``). This module never touches
``role="child"`` rows: those are the synthetic accounts
``api/child_sessions.py`` provisions for a ``ChildProfile``, and are excluded
from every read/write here.
"""

from __future__ import annotations

import uuid
from typing import cast

from fastapi import APIRouter
from sqlalchemy import ColumnElement, select

from cyo_adventure.api.deps import Context, parse_uuid
from cyo_adventure.api.schemas import (
    AdminManagedRole,
    UserCreateBody,
    UserListView,
    UserStatus,
    UserUpdateBody,
    UserView,
    error_responses,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
from cyo_adventure.db.models import Family, User
from cyo_adventure.events import ADMIN_ACTOR_ROLE, Actor, EventType, record_event

router = APIRouter(
    prefix="/api/v1", tags=["admin-users"], responses=error_responses(401, 403)
)

# Deterministic, unique-per-invite placeholder subject: no real Supabase JWT
# can ever carry this shape, so a pending row can never accidentally
# authenticate before it is bound. Mirrors api/child_sessions.py's
# `_SUBJECT_PREFIX = "child-profile:"` precedent for a synthetic subject.
_PENDING_SUBJECT_PREFIX = "pending-invite:"

# Defensive ceiling mirroring families.py's _FAMILY_LIST_LIMIT convention.
_USER_LIST_LIMIT = 200

_MEMBER_ROLES = ("guardian", "admin")


def _require_admin(ctx: Context) -> None:
    """Reject non-admin callers before any read or write.

    Args:
        ctx: The request context (principal + session).

    Raises:
        AuthorizationError: If the caller is not an admin (403).
    """
    # #CRITICAL: security: this endpoint can create, reassign, or deactivate
    # ANY family's guardian/admin accounts; the role gate runs before any
    # query so a non-admin cannot even enumerate the cross-tenant roster.
    # #VERIFY: tests/integration/test_admin_users_api.py::test_guardian_gets_403.
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg, required_permission="admin")


def _view(row: User) -> UserView:
    """Map an ORM row to its response schema.

    Args:
        row: The ORM row (never a role='child' row; callers filter those out).

    Returns:
        UserView: The wire-safe view.
    """
    # #CRITICAL: security: authn_subject is never included; it is
    # bearer-adjacent identity material with no admin-console use (mirrors
    # why ProfileView never serializes pin_hash).
    # #VERIFY: tests/integration/test_admin_users_api.py::
    # test_user_view_never_serializes_authn_subject.
    return UserView(
        id=str(row.id),
        family_id=str(row.family_id),
        email=row.email,
        role=cast("AdminManagedRole", row.role),
        is_admin=row.is_admin,
        status=cast("UserStatus", row.status),
        created_at=row.created_at,
    )


@router.get("/admin/users")
async def list_users(
    ctx: Context,
    family_id: str | None = None,
    role: AdminManagedRole | None = None,
    status: UserStatus | None = None,
) -> UserListView:
    """List guardian/admin accounts, optionally filtered (admin only).

    Args:
        ctx: The request context (principal + session).
        family_id: Optional family filter.
        role: Optional role filter (guardian or admin).
        status: Optional status filter.

    Returns:
        UserListView: Up to ``_USER_LIST_LIMIT`` matching rows, created_at
        order; role='child' rows are always excluded.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ValidationError: If ``family_id`` is not a valid UUID (422).
    """
    _require_admin(ctx)
    # #CRITICAL: security: role='child' rows are always excluded, even
    # without an explicit role filter; a child's synthetic account is not
    # this console's concern and must never appear in a guardian/admin
    # roster.
    # #VERIFY: tests/integration/test_admin_users_api.py::
    # test_list_users_never_includes_child_rows.
    clauses: list[ColumnElement[bool]] = [User.role.in_(_MEMBER_ROLES)]
    if family_id is not None:
        clauses.append(User.family_id == parse_uuid(family_id, "family_id"))
    if role is not None:
        clauses.append(User.role == role)
    if status is not None:
        clauses.append(User.status == status)
    # #EDGE: data-integrity: past _USER_LIST_LIMIT matching rows the console
    # silently omits the tail; revisit with pagination before the deployment
    # outgrows a single table view.
    rows = (
        await ctx.session.scalars(
            select(User)
            .where(*clauses)
            .order_by(User.created_at.asc(), User.id.asc())
            .limit(_USER_LIST_LIMIT)
        )
    ).all()
    return UserListView(users=[_view(row) for row in rows])


@router.post("/admin/users", status_code=201, responses=error_responses(404, 409))
async def create_user(body: UserCreateBody, ctx: Context) -> UserView:
    """Invite a guardian or admin into a family (admin only; WS-J).

    Args:
        body: The invitee's email, target family, role, and dual-role flag.
        ctx: The request context (principal + session).

    Returns:
        UserView: The created ``status="pending"`` row.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ValidationError: If ``family_id`` is not a valid UUID (422).
        ResourceNotFoundError: If the target family does not exist (404).
        StateTransitionError: If a pending invite already exists for this
            email (409) -- onboarding's email-match bind
            (``select(...).scalar()``) requires at most one pending row per
            email, so a second is rejected rather than left ambiguous.
    """
    _require_admin(ctx)
    family_uuid = parse_uuid(body.family_id, "family_id")
    family = await ctx.session.get(Family, family_uuid)
    if family is None:
        msg = f"family '{body.family_id}' not found"
        raise ResourceNotFoundError(msg)
    # #CRITICAL: data-integrity: two 'pending' rows sharing an email would
    # make api/onboarding.py::_bind_pending_invite's scalar() lookup
    # ambiguous (MultipleResultsFound) on that person's first login. Rejected
    # here, at creation time, rather than left to surface as a 500 later.
    # #VERIFY: tests/integration/test_admin_users_api.py::
    # test_duplicate_pending_invite_email_is_409.
    existing_pending = await ctx.session.scalar(
        select(User).where(User.status == "pending", User.email == body.email)
    )
    if existing_pending is not None:
        msg = f"a pending invite already exists for '{body.email}'"
        raise StateTransitionError(msg)
    # role='admin' always implies is_admin=True (mirrors ck_user_admin_role_flag).
    is_admin = True if body.role == "admin" else body.is_admin
    user = User(
        family_id=family_uuid,
        role=body.role,
        is_admin=is_admin,
        authn_subject=f"{_PENDING_SUBJECT_PREFIX}{uuid.uuid4()}",
        email=body.email,
        status="pending",
    )
    ctx.session.add(user)
    await ctx.session.flush()
    await ctx.session.refresh(user, ["created_at"])
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal, acting_role=ADMIN_ACTOR_ROLE),
        entity_type="user",
        entity_id=str(user.id),
        event_type=EventType.USER_MANAGED,
        payload={"action": "invited", "role": body.role, "status": "pending"},
    )
    return _view(user)


@router.patch("/admin/users/{user_id}", responses=error_responses(404))
async def update_user(user_id: str, body: UserUpdateBody, ctx: Context) -> UserView:
    """Reassign, re-role, or activate/deactivate a guardian/admin (WS-J).

    An admin may not edit their own row through this endpoint (self-lockout
    guard): every field here (family, role, capability, status) could strand
    the caller without admin access, and this console has no "who else is an
    admin" recovery path, so self-editing is refused outright rather than
    reasoned about field-by-field.

    Args:
        user_id: The account to update (path).
        body: The fields to change; omitted fields are untouched.
        ctx: The request context (principal + session).

    Returns:
        UserView: The updated account.

    Raises:
        AuthorizationError: If the caller is not an admin, or targets their
            own account (403).
        ResourceNotFoundError: If no guardian/admin row with this id exists
            (404; a role='child' row 404s here too, see the module docstring).
        ValidationError: If a ``status`` transition through/from 'pending' is
            requested, or ``family_id`` is not a valid UUID (422).
    """
    _require_admin(ctx)
    parsed = parse_uuid(user_id, "user_id")
    # #CRITICAL: security: refusing ANY self-edit (not just self-deactivation)
    # is the simplest guard against an admin accidentally locking themselves
    # out (demoting their own role, dropping is_admin, deactivating
    # themselves). A system-wide "last admin" check is deliberately out of
    # scope (an edge case this guard does not cover), so this is the one
    # enforced safeguard.
    # #VERIFY: tests/integration/test_admin_users_api.py::
    # test_admin_cannot_edit_own_account.
    if parsed == ctx.principal.user_id:
        msg = "cannot manage your own account through this endpoint"
        raise AuthorizationError(msg)
    user = await ctx.session.get(User, parsed)
    if user is None or user.role not in _MEMBER_ROLES:
        msg = f"user '{user_id}' not found"
        raise ResourceNotFoundError(msg)

    if body.family_id is not None:
        target_family_uuid = parse_uuid(body.family_id, "family_id")
        target_family = await ctx.session.get(Family, target_family_uuid)
        if target_family is None:
            msg = f"family '{body.family_id}' not found"
            raise ResourceNotFoundError(msg)
        user.family_id = target_family_uuid
    if body.role is not None:
        user.role = body.role
    if body.is_admin is not None:
        user.is_admin = body.is_admin
    # role='admin' always implies is_admin=True regardless of what was sent
    # above, mirroring ck_user_admin_role_flag (same rule as create_user).
    if user.role == "admin":
        user.is_admin = True

    action = "updated"
    if body.status is not None and body.status != user.status:
        # #ASSUME: data-integrity: 'pending' is reachable only via
        # create_user and left only via onboarding's email-match bind; a
        # direct PATCH into or out of it here would either fabricate an
        # unusable synthetic-subject account or silently discard an
        # in-flight invite, so both are rejected.
        # #VERIFY: tests/integration/test_admin_users_api.py::
        # test_status_transition_through_pending_is_rejected.
        if body.status == "pending" or user.status == "pending":
            msg = "status cannot be set to or from 'pending' directly"
            raise ValidationError(msg, field="status", value=body.status)
        user.status = body.status
        action = "deactivated" if body.status == "deactivated" else "reactivated"

    await ctx.session.flush()
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal, acting_role=ADMIN_ACTOR_ROLE),
        entity_type="user",
        entity_id=str(parsed),
        event_type=EventType.USER_MANAGED,
        payload={"action": action, "role": user.role, "status": user.status},
    )
    return _view(user)
