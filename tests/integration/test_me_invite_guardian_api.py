"""Integration tests for guardian self-service co-parent invites (G14).

Exercises ``POST /api/v1/me/family/invite-guardian``: the guardian-only role
gate, the happy path (a ``status="pending"`` row scoped to the caller's own
family), the hard family-scoping guarantee (no ``family_id`` is ever
client-suppliable), the never-admin invariant, and the duplicate-pending-email
conflict shared with ``POST /admin/users`` (WS-J) via
``api/admin_users.py::create_pending_invite``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from .conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_INVITE = "/api/v1/me/family/invite-guardian"
_USERS = "/api/v1/admin/users"


async def test_invite_guardian_happy_path(client: AsyncClient, seed: Seed) -> None:
    """A guardian invites a co-parent by email; a pending row is created."""
    resp = await client.post(
        _INVITE,
        headers=auth(seed.guardian_token),
        json={"email": "co-parent@example.com"},
    )
    assert resp.status_code == 201, resp.text
    body = cast("dict[str, object]", resp.json())
    assert body["status"] == "pending"
    assert body["role"] == "guardian"
    assert body["is_admin"] is False
    assert body["family_id"] == str(seed.family_id)
    assert "authn_subject" not in body


async def test_invite_guardian_is_hard_scoped_to_callers_own_family(
    client: AsyncClient, seed: Seed
) -> None:
    """The invited row always lands in the caller's own family.

    ``GuardianInviteBody`` carries no ``family_id`` field at all (``extra=
    "forbid"`` rejects one if sent), so there is no client-controlled input
    that could steer the invite into a different family.
    """
    resp = await client.post(
        _INVITE,
        headers=auth(seed.guardian_token),
        json={"email": "own-family-only@example.com"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["family_id"] == str(seed.family_id)

    # A family_id in the request body is rejected outright (extra="forbid"),
    # not silently ignored, so there is no way to even attempt steering it.
    rejected = await client.post(
        _INVITE,
        headers=auth(seed.guardian_token),
        json={
            "email": "attempted-cross-family@example.com",
            "family_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert rejected.status_code == 422


async def test_invite_guardian_two_families_stay_isolated(
    client: AsyncClient, seed: Seed
) -> None:
    """Family A's and Family B's guardians each land their invite in their own family."""
    resp_a = await client.post(
        _INVITE,
        headers=auth(seed.guardian_token),
        json={"email": "family-a-coparent@example.com"},
    )
    resp_b = await client.post(
        _INVITE,
        headers=auth(seed.other_guardian_token),
        json={"email": "family-b-coparent@example.com"},
    )
    assert resp_a.status_code == 201, resp_a.text
    assert resp_b.status_code == 201, resp_b.text
    family_a_id = resp_a.json()["family_id"]
    family_b_id = resp_b.json()["family_id"]
    assert family_a_id != family_b_id
    assert family_a_id == str(seed.family_id)

    # Cross-check via the admin roster: each invite is filed under the
    # inviting guardian's own family, never the other one.
    listing = await client.get(
        _USERS,
        params={"status": "pending"},
        headers=auth(seed.admin_token),
    )
    assert listing.status_code == 200
    rows = {row["email"]: row["family_id"] for row in listing.json()["users"]}
    assert rows["family-a-coparent@example.com"] == family_a_id
    assert rows["family-b-coparent@example.com"] == family_b_id


async def test_invite_guardian_created_row_is_never_admin(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian can never self-grant the admin capability through this path.

    ``GuardianInviteBody`` carries no ``role`` or ``is_admin`` field, so there
    is no request shape that produces anything but a plain guardian invite.
    """
    resp = await client.post(
        _INVITE,
        headers=auth(seed.guardian_token),
        json={"email": "never-admin@example.com", "is_admin": True, "role": "admin"},
    )
    # extra="forbid" rejects the unexpected fields outright.
    assert resp.status_code == 422


async def test_invite_guardian_rejects_non_guardian_roles(
    client: AsyncClient, seed: Seed
) -> None:
    """Admin-only and child callers are refused (403), never a 500."""
    admin_resp = await client.post(
        _INVITE,
        headers=auth(seed.admin_token),
        json={"email": "admin-cannot-use-this@example.com"},
    )
    assert admin_resp.status_code == 403

    child_resp = await client.post(
        _INVITE,
        headers=auth(seed.child_token),
        json={"email": "child-cannot-use-this@example.com"},
    )
    assert child_resp.status_code == 403


async def test_invite_guardian_dual_role_adult_can_still_invite(
    client: AsyncClient, seed: Seed
) -> None:
    """A dual-role adult (guardian base role + admin capability) still qualifies.

    The role gate checks the base role, not ``is_admin``: ``seed.dual_token``
    is ``(role="guardian", is_admin=True)`` and must pass the same guardian
    gate as a plain guardian.
    """
    resp = await client.post(
        _INVITE,
        headers=auth(seed.dual_token),
        json={"email": "dual-role-invited@example.com"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["family_id"] == str(seed.family_id)


async def test_duplicate_pending_invite_email_is_409(
    client: AsyncClient, seed: Seed
) -> None:
    """A second pending invite for the same email is rejected (409).

    Shares the exact duplicate-email guard ``POST /admin/users`` uses
    (``api/admin_users.py::create_pending_invite``), so the two invite paths
    can never together leave two pending rows for one email.
    """
    body = {"email": "dup-guardian-invite@example.com"}
    first = await client.post(_INVITE, headers=auth(seed.guardian_token), json=body)
    assert first.status_code == 201

    second = await client.post(_INVITE, headers=auth(seed.guardian_token), json=body)
    assert second.status_code == 409


async def test_duplicate_pending_invite_conflicts_with_admin_created_invite(
    client: AsyncClient, seed: Seed
) -> None:
    """The guardian self-invite path and the admin-invite path share one guard.

    An admin-created pending invite for an email blocks a guardian's
    self-service invite for that same email, and vice versa, since both
    write through the same ``create_pending_invite`` helper.
    """
    admin_created = await client.post(
        _USERS,
        headers=auth(seed.admin_token),
        json={
            "email": "admin-invited-first@example.com",
            "family_id": str(seed.family_id),
            "role": "guardian",
        },
    )
    assert admin_created.status_code == 201

    guardian_attempt = await client.post(
        _INVITE,
        headers=auth(seed.guardian_token),
        json={"email": "admin-invited-first@example.com"},
    )
    assert guardian_attempt.status_code == 409
