"""Integration tests for GET /api/v1/me."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cyo_adventure.core.config import settings
from cyo_adventure.db.models import KwsVerification, User
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_returns_guardian_identity(client: AsyncClient, seed: Seed) -> None:
    """A guardian's /me reflects its role and its family's profile ids."""
    resp = await client.get("/api/v1/me", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subject"] == seed.guardian_token
    assert body["role"] == "guardian"
    assert body["is_admin"] is False
    assert body["family_id"] == str(seed.family_id)
    assert str(seed.child_profile_id) in body["profile_ids"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_returns_child_identity_scoped_to_own_profile(
    client: AsyncClient, seed: Seed
) -> None:
    """A child's /me lists only its own assigned profile, not its sibling's."""
    resp = await client.get("/api/v1/me", headers=auth(seed.child_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "child"
    assert body["profile_ids"] == [str(seed.child_profile_id)]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_returns_admin_identity(client: AsyncClient, seed: Seed) -> None:
    """An admin-only adult's /me reflects the admin base role and capability."""
    resp = await client.get("/api/v1/me", headers=auth(seed.admin_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "admin"
    assert body["is_admin"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_returns_dual_role_identity(client: AsyncClient, seed: Seed) -> None:
    """A dual-role adult's /me carries the guardian persona AND the capability.

    The frontend picks the guardian shell from ``role`` and shows the admin
    console entry from ``is_admin``; both must be present on one identity.
    """
    resp = await client.get("/api/v1/me", headers=auth(seed.dual_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "guardian"
    assert body["is_admin"] is True
    assert body["family_id"] == str(seed.family_id)
    assert str(seed.child_profile_id) in body["profile_ids"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_requires_authentication(client: AsyncClient) -> None:
    """No bearer token yields 401, not a 500 or an anonymous identity."""
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_reports_no_verification_state_while_the_flag_is_off(
    client: AsyncClient, seed: Seed
) -> None:
    """Both ADR-018 D1 fields are present and inert on a tier that does not verify.

    Present, so the frontend can branch on one contract rather than on whether
    a key exists; inert, because routing an adult to a verification screen on
    a tier where nothing gates on verification would strand them.
    """
    resp = await client.get("/api/v1/me", headers=auth(seed.guardian_token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verification_required"] is False
    assert body["verification_status"] == "none"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_me_reports_a_verification_once_one_is_usable(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The counterpart: with the flag on, a usable row reads back as verified.

    Without this the test above would pass just as well against a field
    hard-coded to ``"none"``, which is the failure mode a flag-off assertion
    cannot distinguish on its own.
    """
    monkeypatch.setattr(settings, "kws_verification_required", True)
    monkeypatch.setattr(settings, "kws_environment", "test")
    monkeypatch.setattr(settings, "kws_accept_test_evidence", True)
    now = datetime.now(UTC)
    async with sessions() as session:
        user_id = await session.scalar(
            select(User.id).where(User.authn_subject == "guardian-a")
        )
        assert user_id is not None
        session.add(
            KwsVerification(
                id=uuid.uuid4(),
                user_id=user_id,
                kws_environment="test",
                status="verified",
                requested_at=now,
                resolved_at=now,
                enabled_methods=["credit_card"],
                location="US",
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/me", headers=auth(seed.guardian_token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["verification_required"] is True
    assert body["verification_status"] == "verified"
