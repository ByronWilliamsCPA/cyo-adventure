"""Integration tests for JIT guardian onboarding (P6-03).

Exercises ``POST /api/v1/onboarding`` end-to-end against a real Postgres:
first-login provisioning, idempotent retry, admin non-provisioning, email
capture, and the auth boundary (missing bearer, child session token).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from sqlalchemy import func, select

from cyo_adventure.api import deps, onboarding
from cyo_adventure.api.deps import OnboardingIdentity
from cyo_adventure.app import app
from cyo_adventure.core.child_session import mint_child_session_token
from cyo_adventure.db.models import Family, User

from .conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_ONBOARDING = "/api/v1/onboarding"


async def _count(sessions: async_sessionmaker[AsyncSession], model: type) -> int:
    async with sessions() as session:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def test_first_login_creates_family_and_guardian(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A verified subject with no user row provisions a family + guardian (201).

    The row starts 'awaiting_approval', not 'active' (the self-signup
    approval track): an admin must approve it before anything else
    authenticates for this subject.
    """
    _ = seed  # seed builds the schema/rows the app queries against
    families_before = await _count(sessions, Family)

    resp = await client.post(_ONBOARDING, headers=auth("brand-new-guardian"), json={})

    assert resp.status_code == 201
    payload = cast("dict[str, object]", resp.json())
    assert payload["created"] is True
    assert payload["role"] == "guardian"
    assert payload["status"] == "awaiting_approval"
    assert payload["family_id"]
    assert payload["user_id"]
    assert await _count(sessions, Family) == families_before + 1

    async with sessions() as session:
        user = await session.scalar(
            select(User).where(User.authn_subject == "brand-new-guardian")
        )
    assert user is not None
    assert user.role == "guardian"
    assert user.status == "awaiting_approval"
    # Local dev seam supplies no email claim, so the contact column is null.
    assert user.email is None


async def test_self_signup_guardian_cannot_authenticate_until_approved(
    client: AsyncClient, seed: Seed
) -> None:
    """A freshly self-signed-up guardian's GET /v1/me fails until admin approval.

    require_principal rejects any non-'active' status with the same
    "unknown subject" message as a nonexistent one (api/deps.py); this pins
    that the self-signup track actually blocks access, not just that the
    row is tagged correctly.
    """
    _ = seed
    onboard_resp = await client.post(
        _ONBOARDING, headers=auth("unapproved-guardian"), json={}
    )
    assert onboard_resp.status_code == 201

    me_resp = await client.get("/api/v1/me", headers=auth("unapproved-guardian"))
    assert me_resp.status_code == 401


async def test_admin_approves_self_signup_guardian(
    client: AsyncClient, seed: Seed
) -> None:
    """An admin approving a self-signed-up guardian lets them authenticate.

    End-to-end: self-signup (awaiting_approval) -> PATCH .../approve
    (active) -> GET /v1/me succeeds.
    """
    onboard_resp = await client.post(
        _ONBOARDING, headers=auth("soon-approved-guardian"), json={}
    )
    assert onboard_resp.status_code == 201
    user_id = onboard_resp.json()["user_id"]

    approve_resp = await client.patch(
        f"/api/v1/admin/users/{user_id}",
        json={"status": "active"},
        headers=auth(seed.admin_token),
    )
    assert approve_resp.status_code == 200, approve_resp.text
    assert approve_resp.json()["status"] == "active"

    me_resp = await client.get("/api/v1/me", headers=auth("soon-approved-guardian"))
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "guardian"


async def test_admin_denies_self_signup_guardian(
    client: AsyncClient, seed: Seed
) -> None:
    """An admin denying a self-signed-up guardian keeps them locked out."""
    onboard_resp = await client.post(
        _ONBOARDING, headers=auth("denied-guardian"), json={}
    )
    assert onboard_resp.status_code == 201
    user_id = onboard_resp.json()["user_id"]

    deny_resp = await client.patch(
        f"/api/v1/admin/users/{user_id}",
        json={"status": "deactivated"},
        headers=auth(seed.admin_token),
    )
    assert deny_resp.status_code == 200, deny_resp.text
    assert deny_resp.json()["status"] == "deactivated"

    me_resp = await client.get("/api/v1/me", headers=auth("denied-guardian"))
    assert me_resp.status_code == 401


async def test_retry_is_idempotent_same_ids(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A second onboarding for the same subject returns 200 with identical ids."""
    _ = seed
    first = await client.post(_ONBOARDING, headers=auth("retry-guardian"), json={})
    assert first.status_code == 201
    first_body = cast("dict[str, object]", first.json())

    second = await client.post(_ONBOARDING, headers=auth("retry-guardian"), json={})
    assert second.status_code == 200
    second_body = cast("dict[str, object]", second.json())

    assert second_body["created"] is False
    assert second_body["family_id"] == first_body["family_id"]
    assert second_body["user_id"] == first_body["user_id"]
    # Exactly one guardian row and one family exist for the retried subject.
    async with sessions() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.authn_subject == "retry-guardian")
        )
    assert count == 1


async def test_admin_token_does_not_create_family(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """An admin already has a row: onboarding returns it and creates no family."""
    families_before = await _count(sessions, Family)

    resp = await client.post(_ONBOARDING, headers=auth(seed.admin_token), json={})

    assert resp.status_code == 200
    payload = cast("dict[str, object]", resp.json())
    assert payload["created"] is False
    assert payload["role"] == "admin"
    assert payload["user_id"] == str(seed.admin_user_id)
    # No family was minted for the admin (admin is not a provisioned member).
    assert await _count(sessions, Family) == families_before


async def test_existing_guardian_is_idempotent(client: AsyncClient, seed: Seed) -> None:
    """A seeded guardian onboarding again returns its own row with 200."""
    resp = await client.post(_ONBOARDING, headers=auth(seed.guardian_token), json={})
    assert resp.status_code == 200
    payload = cast("dict[str, object]", resp.json())
    assert payload["created"] is False
    assert payload["role"] == "guardian"
    assert payload["family_id"] == str(seed.family_id)


async def test_missing_bearer_is_unauthorized(client: AsyncClient, seed: Seed) -> None:
    """Onboarding without a bearer token is rejected 401, never anonymous."""
    _ = seed
    resp = await client.post(_ONBOARDING, json={})
    assert resp.status_code == 401


async def test_child_session_token_cannot_onboard(
    client: AsyncClient, seed: Seed
) -> None:
    """A child session token is refused (403); it cannot provision a guardian."""
    token, _expires = mint_child_session_token(
        profile_id=seed.child_profile_id,
        family_id=seed.family_id,
        user_id=seed.admin_user_id,
    )
    resp = await client.post(_ONBOARDING, headers=auth(token), json={})
    assert resp.status_code == 403


async def test_empty_body_is_accepted(client: AsyncClient, seed: Seed) -> None:
    """Onboarding accepts a request with no body at all (identity is the token)."""
    _ = seed
    resp = await client.post(_ONBOARDING, headers=auth("bodyless-guardian"))
    assert resp.status_code == 201
    assert resp.json()["created"] is True


async def test_onboarding_without_consent_still_provisions(
    client: AsyncClient, seed: Seed
) -> None:
    """Omitting consent entirely still provisions the guardian; nothing is gated here.

    Phase 2 / ADR-018 D1's gate lives at POST /api/v1/profiles
    (api/profiles.py::_require_consent), not at onboarding itself: a
    guardian may finish sign-in and look around before completing consent,
    they simply cannot create a child profile until they do.
    """
    _ = seed
    resp = await client.post(
        _ONBOARDING, headers=auth("no-consent-guardian"), json={}
    )
    assert resp.status_code == 201
    assert resp.json()["created"] is True


async def test_consent_requires_policy_version_and_signer_name(
    client: AsyncClient, seed: Seed
) -> None:
    """accepted=True with no signer_name is rejected (422), not silently dropped."""
    _ = seed
    resp = await client.post(
        _ONBOARDING,
        headers=auth("half-consenting-guardian"),
        json={"consent": {"accepted": True, "policy_version": "2026-07"}},
    )
    assert resp.status_code == 422


async def test_onboarding_records_consent_once_and_is_idempotent(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A valid consent payload is persisted onto the guardian's own User row.

    A second onboarding call with a DIFFERENT consent payload does not
    overwrite the first: consent is written once, matching
    api/onboarding.py::_record_consent's idempotency contract.
    """
    _ = seed
    subject = "consenting-guardian"
    first = await client.post(
        _ONBOARDING,
        headers=auth(subject),
        json={
            "consent": {
                "accepted": True,
                "policy_version": "2026-07",
                "signer_name": "Jane A. Guardian",
            }
        },
    )
    assert first.status_code == 201

    async with sessions() as session:
        user = await session.scalar(
            select(User).where(User.authn_subject == subject)
        )
    assert user is not None
    assert user.consent_accepted_at is not None
    assert user.consent_policy_version == "2026-07"
    assert user.consent_signer_name == "Jane A. Guardian"
    assert user.consent_ip is not None
    first_recorded_at = user.consent_accepted_at

    second = await client.post(
        _ONBOARDING,
        headers=auth(subject),
        json={
            "consent": {
                "accepted": True,
                "policy_version": "2027-01",
                "signer_name": "Someone Else",
            }
        },
    )
    assert second.status_code == 200

    async with sessions() as session:
        user = await session.scalar(
            select(User).where(User.authn_subject == subject)
        )
    assert user is not None
    assert user.consent_accepted_at == first_recorded_at
    assert user.consent_policy_version == "2026-07"
    assert user.consent_signer_name == "Jane A. Guardian"


async def test_onboarding_race_recovers_winner(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """The first-login race recovers via a real unique-index conflict.

    Simulates the loser's timeline: its pre-insert SELECT saw no row (so the
    handler proceeded to provision), but the winner's row is already committed
    when the loser's INSERT hits the unique ``ix_user_authn_subject`` index.
    The real ``IntegrityError`` unwinds the savepoint (undoing the loser's
    Family insert too) and the loser returns the winner's row, leaving exactly
    one user and one family for the subject.
    """
    _ = seed
    subject = "raced-first-login"
    families_before = await _count(sessions, Family)

    # The "winner": another device's committed first login.
    async with sessions() as session:
        family = Family(name="Winner Family")
        session.add(family)
        await session.flush()
        winner = User(family_id=family.id, role="guardian", authn_subject=subject)
        session.add(winner)
        await session.commit()
        winner_id = winner.id
        winner_family_id = family.id

    # The "loser": drive the savepoint provisioning step directly (its
    # pre-read already returned None before the winner committed) against the
    # real index. The conflicting writes run INSIDE begin_nested, so only the
    # savepoint unwinds and the outer transaction stays usable for the
    # recovery re-read.
    async with sessions() as session:
        user, created = await onboarding._provision_guardian(
            session, OnboardingIdentity(subject=subject, email=None)
        )
        assert created is False
        assert user.id == winner_id
        assert user.family_id == winner_family_id
        await session.commit()

    # Exactly one user row for the subject, and only the winner's family was
    # created: the loser's partial Family insert was unwound with the savepoint.
    async with sessions() as session:
        count = await session.scalar(
            select(func.count()).select_from(User).where(User.authn_subject == subject)
        )
    assert count == 1
    assert await _count(sessions, Family) == families_before + 1


async def test_email_claim_persisted_when_present(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """The email contact claim is stored on the created user when the token has one.

    The local dev seam carries no email, so the verified-identity dependency is
    overridden here to inject one (as a real Supabase token would), proving the
    endpoint persists it. The child-session-secret autouse fixture and the DB
    override from the ``client`` fixture remain in force.
    """
    _ = seed
    relay = "abc123@privaterelay.appleid.com"

    def _identity_with_email() -> OnboardingIdentity:
        return OnboardingIdentity(subject="apple-guardian", email=relay)

    app.dependency_overrides[deps.require_onboarding_identity] = _identity_with_email
    try:
        resp = await client.post(_ONBOARDING, json={})
    finally:
        del app.dependency_overrides[deps.require_onboarding_identity]

    assert resp.status_code == 201
    async with sessions() as session:
        user = await session.scalar(
            select(User).where(User.authn_subject == "apple-guardian")
        )
    assert user is not None
    # Contact data only: stored, but authn_subject remains the sole key.
    assert user.email == relay
