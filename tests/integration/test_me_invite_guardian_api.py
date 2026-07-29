"""Integration tests for guardian self-service co-parent invites (G14).

Exercises ``POST /api/v1/me/family/invite-guardian``: the guardian-only role
gate, the happy path (a ``status="pending_guardian_invite"`` row scoped to the
caller's own family), the hard family-scoping guarantee (no ``family_id`` is
ever client-suppliable), the never-admin invariant, and the
duplicate-pending-email conflict shared with ``POST /admin/users`` (WS-J) via
``api/admin_users.py::create_pending_invite``.

The security core of this module is the family-capture suite at the bottom.
A guardian can name ANY email address, so a guardian-created invite is
vetted by nobody; it therefore carries its own status
(``pending_guardian_invite``) and binds to ``awaiting_approval``, never
straight to ``active`` the way an admin-created ``pending`` invite does.
Without that split, guardian Mallory could invite ``victim@example.com``,
wait for the real owner to sign up normally, and have them silently bound
into Mallory's family as an ACTIVE guardian, exposing that family's child
profiles. There is no invite expiry and no revoke surface, so the admin
approval gate is the only thing standing in the way.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.api import deps
from cyo_adventure.api.deps import OnboardingIdentity
from cyo_adventure.app import app
from cyo_adventure.db.models import User

from .conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient, Response
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_INVITE = "/api/v1/me/family/invite-guardian"
_USERS = "/api/v1/admin/users"
_ONBOARDING = "/api/v1/onboarding"
_ME = "/api/v1/me"
_GUARDIAN_INVITE_STATUS = "pending_guardian_invite"


async def _onboard_as(client: AsyncClient, *, subject: str, email: str) -> Response:
    """Run first-login onboarding for a verified (subject, email) identity.

    Mirrors ``test_admin_users_api.py``'s override pattern: the local dev
    auth seam carries no email claim, and the whole invite-bind path keys on
    the verified email, so the identity has to be supplied directly.
    """

    def _identity() -> OnboardingIdentity:
        return OnboardingIdentity(subject=subject, email=email)

    app.dependency_overrides[deps.require_onboarding_identity] = _identity
    try:
        return await client.post(_ONBOARDING, json={})
    finally:
        del app.dependency_overrides[deps.require_onboarding_identity]


async def _load_user(
    sessions: async_sessionmaker[AsyncSession], user_id: str
) -> User | None:
    async with sessions() as session:
        return await session.get(User, user_id)


async def test_invite_guardian_happy_path(client: AsyncClient, seed: Seed) -> None:
    """A guardian invites a co-parent by email; an unvetted invite row is created.

    The status is ``pending_guardian_invite``, NOT the admin path's
    ``pending``: the two bind differently and must stay distinguishable at
    rest.
    """
    resp = await client.post(
        _INVITE,
        headers=auth(seed.guardian_token),
        json={"email": "co-parent@example.com"},
    )
    assert resp.status_code == 201, resp.text
    body = cast("dict[str, object]", resp.json())
    assert body["status"] == _GUARDIAN_INVITE_STATUS
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
        params={"status": _GUARDIAN_INVITE_STATUS},
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


async def test_guardian_invite_then_admin_invite_same_email_is_409(
    client: AsyncClient, seed: Seed
) -> None:
    """The duplicate-invite guard spans both kinds in BOTH directions.

    The reverse of the test above. The guard matches on
    ``User.status.in_(USER_PENDING_INVITE_STATUSES)``, not on the caller's
    own status value: a guardian invite followed by an admin invite for the
    same address must still 409, or two unbound rows would share one email
    and ``_bind_pending_invite``'s ``scalar()`` would raise
    MultipleResultsFound (a 500) on that person's first sign-in.
    """
    email = "guardian-invited-first@example.com"
    guardian_created = await client.post(
        _INVITE, headers=auth(seed.guardian_token), json={"email": email}
    )
    assert guardian_created.status_code == 201, guardian_created.text

    admin_attempt = await client.post(
        _USERS,
        headers=auth(seed.admin_token),
        json={"email": email, "family_id": str(seed.family_id), "role": "guardian"},
    )
    assert admin_attempt.status_code == 409, admin_attempt.text


# ---------------------------------------------------------------------------
# Family-capture regression suite: a guardian-created invite must NOT bind
# its invitee into the inviting family as an active guardian.
# ---------------------------------------------------------------------------


async def test_guardian_invited_user_binds_to_awaiting_approval_not_active(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """The end-to-end capture attempt: invite an email, then let its owner sign up.

    Guardian Mallory invites ``victim@example.com``; weeks later the real
    owner completes normal first-login onboarding. ``_bind_pending_invite``
    runs before ``_provision_guardian``, so the row IS bound, but it lands on
    ``awaiting_approval``, not ``active``, and ``require_principal`` refuses
    every authenticated call for it. Mallory gains nothing until an admin
    signs off.
    """
    email = "capture-victim@example.com"
    invite = await client.post(
        _INVITE, headers=auth(seed.guardian_token), json={"email": email}
    )
    assert invite.status_code == 201, invite.text
    invited_user_id = cast("str", invite.json()["id"])

    resp = await _onboard_as(client, subject="capture-victim-subject", email=email)

    assert resp.status_code == 200, resp.text
    payload = cast("dict[str, object]", resp.json())
    # Bound (not newly provisioned), into the inviting family, as a guardian.
    assert payload["created"] is False
    assert payload["user_id"] == invited_user_id
    assert payload["family_id"] == str(seed.family_id)
    assert payload["role"] == "guardian"
    # ...but gated. This single assertion is the vulnerability's regression
    # pin: "active" here is the family-capture bug.
    assert payload["status"] == "awaiting_approval"

    user = await _load_user(sessions, invited_user_id)
    assert user is not None
    assert user.status == "awaiting_approval"
    assert user.authn_subject == "capture-victim-subject"

    # The gate is real, not just a label: nothing authenticates for them.
    me_resp = await client.get(_ME, headers=auth("capture-victim-subject"))
    assert me_resp.status_code == 401


async def test_guardian_invited_user_authenticates_only_after_admin_approval(
    client: AsyncClient, seed: Seed
) -> None:
    """The approval gate is a gate, not a wall: an admin can still let them in.

    Completes the flow the test above stops halfway through, so the split
    cannot be "fixed" by simply making guardian invites permanently
    unusable.
    """
    email = "approved-coparent@example.com"
    invite = await client.post(
        _INVITE, headers=auth(seed.guardian_token), json={"email": email}
    )
    assert invite.status_code == 201, invite.text
    invited_user_id = cast("str", invite.json()["id"])

    bound = await _onboard_as(client, subject="approved-coparent-subject", email=email)
    assert bound.status_code == 200, bound.text
    assert bound.json()["status"] == "awaiting_approval"

    approve = await client.patch(
        f"{_USERS}/{invited_user_id}",
        json={"status": "active"},
        headers=auth(seed.admin_token),
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "active"

    me_resp = await client.get(_ME, headers=auth("approved-coparent-subject"))
    assert me_resp.status_code == 200, me_resp.text
    assert me_resp.json()["role"] == "guardian"


async def test_admin_invited_user_still_binds_to_active(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """The admin invite path is unchanged: it still binds straight to 'active'.

    The counterweight to the capture test above. Splitting the two invite
    kinds must not regress the vetted admin path into needing a second
    approval step it never had.
    """
    email = "admin-vetted-coparent@example.com"
    invite = await client.post(
        _USERS,
        headers=auth(seed.admin_token),
        json={"email": email, "family_id": str(seed.family_id), "role": "guardian"},
    )
    assert invite.status_code == 201, invite.text
    assert invite.json()["status"] == "pending"
    invited_user_id = cast("str", invite.json()["id"])

    resp = await _onboard_as(client, subject="admin-vetted-subject", email=email)

    assert resp.status_code == 200, resp.text
    payload = cast("dict[str, object]", resp.json())
    assert payload["created"] is False
    assert payload["user_id"] == invited_user_id
    assert payload["family_id"] == str(seed.family_id)
    assert payload["status"] == "active"

    user = await _load_user(sessions, invited_user_id)
    assert user is not None
    assert user.status == "active"

    # No admin approval step: they authenticate immediately.
    me_resp = await client.get(_ME, headers=auth("admin-vetted-subject"))
    assert me_resp.status_code == 200, me_resp.text


async def test_guardian_invite_status_cannot_be_patched_to_pending(
    client: AsyncClient, seed: Seed
) -> None:
    """An admin cannot launder an unvetted invite into a vetted one (422).

    ``pending_guardian_invite`` -> ``pending`` would restore the exact
    bind-to-'active' behaviour this split removes, so
    ``_apply_status_transition`` rejects transitions into or out of EITHER
    invite status.
    """
    invite = await client.post(
        _INVITE,
        headers=auth(seed.guardian_token),
        json={"email": "no-laundering@example.com"},
    )
    assert invite.status_code == 201, invite.text
    invited_user_id = cast("str", invite.json()["id"])

    for attempted in ("pending", "active"):
        resp = await client.patch(
            f"{_USERS}/{invited_user_id}",
            json={"status": attempted},
            headers=auth(seed.admin_token),
        )
        assert resp.status_code == 422, f"{attempted}: {resp.text}"


async def test_guardian_invite_row_cannot_authenticate_before_binding(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """An unbound guardian invite cannot authenticate even with its real subject.

    Belt and braces around the status gate. The row's ``authn_subject`` is
    the synthetic ``pending-invite:<uuid>`` placeholder that no real verified
    JWT can carry; the local dev auth seam takes the bearer token AS the
    subject, so replaying the stored placeholder here is the strongest
    available probe. ``require_principal``'s ``!= "active"`` check refuses
    it with the same "unknown subject" 401 as a nonexistent account, so the
    status gate holds even when the subject matches.
    """
    invite = await client.post(
        _INVITE,
        headers=auth(seed.guardian_token),
        json={"email": "unbound-invite@example.com"},
    )
    assert invite.status_code == 201, invite.text
    invited_user_id = cast("str", invite.json()["id"])

    user = await _load_user(sessions, invited_user_id)
    assert user is not None
    assert user.authn_subject.startswith("pending-invite:")

    me_resp = await client.get(_ME, headers=auth(user.authn_subject))
    assert me_resp.status_code == 401
