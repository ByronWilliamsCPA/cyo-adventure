"""Integration tests for admin guardian/admin account management (WS-J).

Exercises ``/api/v1/admin/users`` end-to-end: the 403 gate, invite creation,
the duplicate-pending-email conflict, the onboarding email-match bind, the
deactivated-account auth rejection, the self-lockout guard, and the
role='admin' -> is_admin=True invariant.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy import select

from cyo_adventure.api import deps
from cyo_adventure.api.deps import OnboardingIdentity
from cyo_adventure.app import app
from cyo_adventure.db.models import User

from .conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_USERS = "/api/v1/admin/users"
_ONBOARDING = "/api/v1/onboarding"


async def test_guardian_gets_403_on_every_verb(client: AsyncClient, seed: Seed) -> None:
    """A non-admin guardian is refused list/create/update (403), never a 500."""
    list_resp = await client.get(_USERS, headers=auth(seed.guardian_token))
    assert list_resp.status_code == 403

    create_resp = await client.post(
        _USERS,
        headers=auth(seed.guardian_token),
        json={
            "email": "new-guardian@example.com",
            "family_id": str(seed.family_id),
            "role": "guardian",
        },
    )
    assert create_resp.status_code == 403

    update_resp = await client.patch(
        f"{_USERS}/{seed.admin_user_id}",
        headers=auth(seed.guardian_token),
        json={"status": "deactivated"},
    )
    assert update_resp.status_code == 403


async def test_create_invite_then_admin_lists_it(
    client: AsyncClient, seed: Seed
) -> None:
    """A created invite is 'pending', never a child role, and is listed."""
    resp = await client.post(
        _USERS,
        headers=auth(seed.admin_token),
        json={
            "email": "invitee@example.com",
            "family_id": str(seed.family_id),
            "role": "guardian",
        },
    )
    assert resp.status_code == 201, resp.text
    body = cast("dict[str, object]", resp.json())
    assert body["status"] == "pending"
    assert body["role"] == "guardian"
    assert body["is_admin"] is False
    assert "authn_subject" not in body

    list_resp = await client.get(
        _USERS,
        params={"family_id": str(seed.family_id), "status": "pending"},
        headers=auth(seed.admin_token),
    )
    assert list_resp.status_code == 200
    emails = [row["email"] for row in list_resp.json()["users"]]
    assert "invitee@example.com" in emails


async def test_role_admin_forces_is_admin_true(client: AsyncClient, seed: Seed) -> None:
    """Inviting role='admin' always stores is_admin=True, even if unset."""
    resp = await client.post(
        _USERS,
        headers=auth(seed.admin_token),
        json={
            "email": "new-admin@example.com",
            "family_id": str(seed.family_id),
            "role": "admin",
            "is_admin": False,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["is_admin"] is True


async def test_duplicate_pending_invite_email_is_409(
    client: AsyncClient, seed: Seed
) -> None:
    """A second pending invite for the same email is rejected (409).

    Two pending rows sharing an email would make onboarding's email-match
    scalar() lookup ambiguous on that person's first login.
    """
    body = {
        "email": "duplicate@example.com",
        "family_id": str(seed.family_id),
        "role": "guardian",
    }
    first = await client.post(_USERS, headers=auth(seed.admin_token), json=body)
    assert first.status_code == 201

    second = await client.post(_USERS, headers=auth(seed.admin_token), json=body)
    assert second.status_code == 409


async def test_pending_invite_binds_on_first_login_by_email(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """Onboarding binds a pending invite to the verified subject by email match.

    No new family is created; the pending row becomes active in place.
    """
    invite = await client.post(
        _USERS,
        headers=auth(seed.admin_token),
        json={
            "email": "bind-me@example.com",
            "family_id": str(seed.family_id),
            "role": "guardian",
        },
    )
    assert invite.status_code == 201
    invited_user_id = invite.json()["id"]

    def _identity_with_email() -> OnboardingIdentity:
        return OnboardingIdentity(
            subject="new-real-subject", email="bind-me@example.com"
        )

    app.dependency_overrides[deps.require_onboarding_identity] = _identity_with_email
    try:
        resp = await client.post(_ONBOARDING, json={})
    finally:
        del app.dependency_overrides[deps.require_onboarding_identity]

    assert resp.status_code == 200, resp.text
    payload = cast("dict[str, object]", resp.json())
    assert payload["created"] is False
    assert payload["user_id"] == invited_user_id
    assert payload["family_id"] == str(seed.family_id)

    async with sessions() as session:
        user = await session.get(User, invited_user_id)
    assert user is not None
    assert user.status == "active"
    assert user.authn_subject == "new-real-subject"


async def test_deactivated_guardian_cannot_authenticate(
    client: AsyncClient, seed: Seed
) -> None:
    """A deactivated guardian's token is rejected with the unknown-subject 401.

    Uses ``GET /api/v1/me`` (a plain ``require_principal``-gated endpoint)
    rather than onboarding: onboarding's identity dependency
    (``require_onboarding_identity``) deliberately never loads the ``User``
    row at all (it is the provisioning path), so it would not exercise the
    status check this test targets.
    """
    resp = await client.patch(
        f"{_USERS}/{seed.admin_user_id}",
        headers=auth(seed.dual_token),
        json={"status": "deactivated"},
    )
    assert resp.status_code == 200

    # Note: the target here is the SEED admin (admin-a), deactivated by a
    # different admin (dual-a) to avoid the self-lockout guard.
    me_resp = await client.get("/api/v1/me", headers=auth(seed.admin_token))
    assert me_resp.status_code == 401


async def test_admin_cannot_edit_own_account(client: AsyncClient, seed: Seed) -> None:
    """An admin targeting their own id via PATCH is refused (403), not applied."""
    resp = await client.patch(
        f"{_USERS}/{seed.admin_user_id}",
        headers=auth(seed.admin_token),
        json={"status": "deactivated"},
    )
    assert resp.status_code == 403


async def test_status_transition_through_pending_is_rejected(
    client: AsyncClient, seed: Seed
) -> None:
    """PATCH cannot set status to or from 'pending' directly (422)."""
    invite = await client.post(
        _USERS,
        headers=auth(seed.admin_token),
        json={
            "email": "still-pending@example.com",
            "family_id": str(seed.family_id),
            "role": "guardian",
        },
    )
    pending_id = invite.json()["id"]

    resp = await client.patch(
        f"{_USERS}/{pending_id}",
        headers=auth(seed.admin_token),
        json={"status": "active"},
    )
    assert resp.status_code == 422


async def test_status_transition_into_awaiting_approval_is_rejected(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """PATCH cannot set status to 'awaiting_approval' directly (422).

    That status is reachable only via a guardian's own self-signup JIT
    provisioning (api/onboarding.py); an admin cannot fabricate it for an
    existing, already-active account. Targets family B's guardian (a
    different account than the caller, and already 'active', so this
    isolates the awaiting_approval guard from the separate self-edit and
    'pending' guards).
    """
    async with sessions() as session:
        other_guardian = await session.scalar(
            select(User).where(User.authn_subject == "guardian-b")
        )
    assert other_guardian is not None

    resp = await client.patch(
        f"{_USERS}/{other_guardian.id}",
        headers=auth(seed.admin_token),
        json={"status": "awaiting_approval"},
    )
    assert resp.status_code == 422


async def test_list_users_never_includes_child_rows(
    client: AsyncClient, seed: Seed
) -> None:
    """The seed family's child-a row never appears in the admin roster."""
    resp = await client.get(
        _USERS,
        params={"family_id": str(seed.family_id)},
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 200
    roles = {row["role"] for row in resp.json()["users"]}
    assert "child" not in roles


async def test_reassign_family_id(client: AsyncClient, seed: Seed) -> None:
    """PATCH can move a guardian to a different family."""
    other = await client.post(
        "/api/v1/admin/families",
        headers=auth(seed.admin_token),
        json={"name": "New Home"},
    )
    assert other.status_code == 201
    new_family_id = other.json()["id"]

    resp = await client.patch(
        f"{_USERS}/{seed.admin_user_id}",
        headers=auth(seed.dual_token),
        json={"family_id": new_family_id},
    )
    assert resp.status_code == 200
    assert resp.json()["family_id"] == new_family_id
