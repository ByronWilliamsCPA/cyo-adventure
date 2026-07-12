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
    """A verified subject with no user row provisions a family + guardian (201)."""
    _ = seed  # seed builds the schema/rows the app queries against
    families_before = await _count(sessions, Family)

    resp = await client.post(_ONBOARDING, headers=auth("brand-new-guardian"), json={})

    assert resp.status_code == 201
    payload = cast("dict[str, object]", resp.json())
    assert payload["created"] is True
    assert payload["role"] == "guardian"
    assert payload["family_id"]
    assert payload["user_id"]
    assert await _count(sessions, Family) == families_before + 1

    async with sessions() as session:
        user = await session.scalar(
            select(User).where(User.authn_subject == "brand-new-guardian")
        )
    assert user is not None
    assert user.role == "guardian"
    # Local dev seam supplies no email claim, so the contact column is null.
    assert user.email is None


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


async def test_consent_seam_is_accepted_without_side_effect(
    client: AsyncClient, seed: Seed
) -> None:
    """A consent payload is accepted (P7-02 seam) and does not block provisioning."""
    _ = seed
    resp = await client.post(
        _ONBOARDING,
        headers=auth("consenting-guardian"),
        json={"consent": {"accepted": True, "policy_version": "2026-07"}},
    )
    assert resp.status_code == 201
    assert resp.json()["created"] is True


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
