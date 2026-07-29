"""Admin CRUD for guardian/admin accounts across every family (WS-J).

Creating a user here always creates a ``status="pending"`` invite (a
synthetic placeholder ``authn_subject``, no real login yet); it becomes
``active`` when that email signs in via Supabase for the first time
(``api/onboarding.py::_bind_pending_invite``). That immediate promotion to
``active`` is sound ONLY because an admin created the row and thereby vetted
the invitee. This module never touches ``role="child"`` rows: those are the
synthetic accounts ``api/child_sessions.py`` provisions for a
``ChildProfile``, and are excluded from every read/write here.

``create_pending_invite`` and ``user_view`` are exported (no leading
underscore) so ``api/me.py``'s guardian-scoped self-invite endpoint
(``POST /me/family/invite-guardian``, G14) can reuse the exact same invite-row
creation and duplicate-email guard instead of re-implementing it; that
endpoint hard-scopes ``family_id`` to the calling guardian's own family
before calling in, so this module's cross-family reach never leaks to it.

The two callers are NOT interchangeable, and ``create_pending_invite``'s
``invited_by_admin`` flag is what keeps them apart: an admin-created invite
carries ``status="pending"`` and binds to ``active``; a guardian-created one
carries ``status="pending_guardian_invite"`` and binds to
``awaiting_approval``, so nobody is pulled into a stranger's family without
an admin's approval. See ``db/models.py``'s ``_USER_STATUS_VALUES`` comment.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

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
from cyo_adventure.db.models import (
    USER_PENDING_INVITE_STATUSES,
    USER_STATUS_ADMIN_INVITE,
    USER_STATUS_GUARDIAN_INVITE,
    Family,
    User,
)
from cyo_adventure.events import ADMIN_ACTOR_ROLE, Actor, EventType, record_event

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

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


def user_view(row: User) -> UserView:
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


async def create_pending_invite(
    session: AsyncSession,
    *,
    family_id: uuid.UUID,
    role: AdminManagedRole,
    is_admin: bool,
    email: str,
    invited_by_admin: bool,
) -> User:
    """Create an unbound invite row (shared by the admin and guardian paths).

    Extracted from ``create_user`` so ``api/me.py``'s guardian self-invite
    endpoint reuses the exact same pending-row shape and duplicate-email
    guard; the caller is responsible for resolving and validating
    ``family_id`` (an admin from the request body, a guardian from their own
    principal) and for recording its own audit event afterward.

    Args:
        session: The request unit-of-work session.
        family_id: The family this invite belongs to (already validated to
            exist by the caller).
        role: ``"guardian"`` or ``"admin"``.
        is_admin: Only meaningful with ``role="guardian"``; ``role="admin"``
            always implies ``True`` regardless of what is passed here,
            mirroring the DB CHECK ``ck_user_admin_role_flag``.
        email: The invitee's email (already validated by the caller's
            Pydantic body).
        invited_by_admin: ``True`` for ``POST /admin/users`` (an admin has
            vetted the invitee), ``False`` for the guardian self-service
            path. This picks the row's status, and therefore whether
            onboarding's bind lands the invitee on ``'active'`` or on
            ``'awaiting_approval'``.

    Returns:
        User: The created invite row, ``status="pending"`` when
        ``invited_by_admin`` else ``status="pending_guardian_invite"``.

    Raises:
        StateTransitionError: If an unbound invite of EITHER kind already
            exists for this email (409) -- onboarding's email-match bind
            (``select(...).scalar()``) requires at most one unbound row per
            email, so a second is rejected rather than left ambiguous.
    """
    # #CRITICAL: security: the caller does NOT get to name the status. An
    # admin-created invite binds straight to 'active' on first sign-in, which
    # is only sound because an admin vetted it; a guardian-created one must
    # bind to 'awaiting_approval' instead, or any guardian could pre-claim an
    # arbitrary email and capture its real owner into their family. Deriving
    # the status here, from a single boolean the two routers pass, keeps that
    # decision in one place instead of trusting each call site.
    # #VERIFY: tests/integration/test_me_invite_guardian_api.py::
    # test_guardian_invited_user_binds_to_awaiting_approval_not_active and
    # test_admin_invited_user_still_binds_to_active.
    status = (
        USER_STATUS_ADMIN_INVITE if invited_by_admin else USER_STATUS_GUARDIAN_INVITE
    )
    # #CRITICAL: data-integrity: two unbound invite rows sharing an email
    # would make api/onboarding.py::_bind_pending_invite's scalar() lookup
    # ambiguous (MultipleResultsFound) on that person's first login. The
    # guard spans BOTH invite kinds, not just the caller's own kind: a
    # guardian invite followed by an admin invite for the same address would
    # otherwise slip through. Rejected here, at creation time, rather than
    # left to surface as a 500 later.
    # #VERIFY: tests/integration/test_admin_users_api.py::
    # test_duplicate_pending_invite_email_is_409; tests/integration/
    # test_me_invite_guardian_api.py::test_duplicate_pending_invite_email_is_409,
    # test_guardian_invite_then_admin_invite_same_email_is_409.
    existing_pending = await session.scalar(
        select(User).where(
            User.status.in_(USER_PENDING_INVITE_STATUSES), User.email == email
        )
    )
    if existing_pending is not None:
        msg = f"a pending invite already exists for '{email}'"
        raise StateTransitionError(msg)
    # role='admin' always implies is_admin=True (mirrors ck_user_admin_role_flag).
    resolved_is_admin = True if role == "admin" else is_admin
    user = User(
        family_id=family_id,
        role=role,
        is_admin=resolved_is_admin,
        authn_subject=f"{_PENDING_SUBJECT_PREFIX}{uuid.uuid4()}",
        email=email,
        status=status,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user, ["created_at"])
    return user


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
    return UserListView(users=[user_view(row) for row in rows])


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
    user = await create_pending_invite(
        ctx.session,
        family_id=family_uuid,
        role=body.role,
        is_admin=body.is_admin,
        email=body.email,
        invited_by_admin=True,
    )
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal, acting_role=ADMIN_ACTOR_ROLE),
        entity_type="user",
        entity_id=str(user.id),
        event_type=EventType.USER_MANAGED,
        payload={"action": "invited", "role": body.role, "status": user.status},
    )
    return user_view(user)


def _apply_status_transition(user: User, new_status: UserStatus | None) -> str:
    """Validate and apply a status change, returning the audit-event action label.

    Extracted from ``update_user`` to stay within this repo's cyclomatic
    complexity budget (C901/PLR0912).

    Args:
        user: The row being updated (mutated in place on a valid transition).
        new_status: The requested status, or ``None`` for no status change.

    Returns:
        str: ``"updated"`` when no status change was requested; otherwise
        ``"deactivated"``, ``"denied"``, ``"approved"``, or ``"reactivated"``
        describing what happened, for the ``USER_MANAGED`` audit event.

    Raises:
        ValidationError: If the transition is into/from either invite status
            (``'pending'`` or ``'pending_guardian_invite'``) (422), or
            directly into ``'awaiting_approval'`` (422).
    """
    if new_status is None or new_status == user.status:
        return "updated"
    # #CRITICAL: security: BOTH invite states are reachable only via an
    # invite endpoint and left only via onboarding's email-match bind; a
    # direct PATCH into or out of either would fabricate an unusable
    # synthetic-subject account or silently discard an in-flight invite. The
    # guard must name both kinds: allowing 'pending_guardian_invite' ->
    # 'pending' would convert an unvetted guardian-created invite into a
    # vetted admin-created one and restore the exact bind-to-'active'
    # capture this split exists to prevent.
    # #VERIFY: tests/integration/test_admin_users_api.py::
    # test_status_transition_through_pending_is_rejected; tests/integration/
    # test_me_invite_guardian_api.py::
    # test_guardian_invite_status_cannot_be_patched_to_pending.
    if (
        new_status in USER_PENDING_INVITE_STATUSES
        or user.status in USER_PENDING_INVITE_STATUSES
    ):
        msg = "status cannot be set to or from an invite status directly"
        raise ValidationError(msg, field="status", value=new_status)
    # #CRITICAL: security: 'awaiting_approval' is reachable only via a
    # guardian's own self-signup JIT provisioning
    # (onboarding.py::_provision_guardian); an admin PATCHing a row INTO
    # this status would fabricate a fake "pending self-signup" for an
    # account an admin is actively managing, which makes no sense for any
    # existing row. Only leaving it (approve -> 'active', deny ->
    # 'deactivated') is a real admin action.
    # #VERIFY: tests/integration/test_admin_users_api.py::
    # test_status_transition_into_awaiting_approval_is_rejected.
    if new_status == "awaiting_approval":
        msg = "status cannot be set to 'awaiting_approval' directly"
        raise ValidationError(msg, field="status", value=new_status)
    previous_status = user.status
    user.status = new_status
    if new_status == "deactivated":
        return "denied" if previous_status == "awaiting_approval" else "deactivated"
    if previous_status == "awaiting_approval":
        return "approved"
    return "reactivated"


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
        ValidationError: If a ``status`` transition through/from either
            invite status ('pending', 'pending_guardian_invite') is
            requested, or into 'awaiting_approval' directly, or
            ``family_id`` is not a valid UUID (422).
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

    action = _apply_status_transition(user, body.status)

    await ctx.session.flush()
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal, acting_role=ADMIN_ACTOR_ROLE),
        entity_type="user",
        entity_id=str(parsed),
        event_type=EventType.USER_MANAGED,
        payload={"action": action, "role": user.role, "status": user.status},
    )
    return user_view(user)
