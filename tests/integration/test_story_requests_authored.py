"""Authored (guardian/admin) story-request creation: WS-B PR 2 contract."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import Concept, StoryRequest
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

AUTHORED = "/api/v1/story-requests/authored"

BODY = {
    "request_text": "a story about a patient turtle",
    "age_band": "5-8",
    "length": "short",
}


async def test_guardian_authored_create_is_approved_with_concept(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    res = await client.post(AUTHORED, json=BODY, headers=auth(seed.guardian_token))
    assert res.status_code == 201
    payload = res.json()
    assert payload["status"] == "approved"
    assert payload["concept_id"]
    async with sessions() as session:
        row = await session.get(StoryRequest, uuid.UUID(payload["id"]))
        assert row is not None
        assert row.initiator_role == "guardian"
        assert row.age_band == "5-8"
        assert row.length == "short"
        assert row.narrative_style == "prose"
        assert row.profile_id is None
        assert row.reviewed_by is not None
        concept = await session.get(Concept, row.concept_id)
        assert concept is not None
        assert concept.family_id == seed.family_id


async def test_guardian_authored_create_accepts_own_profile(
    client: AsyncClient, seed: Seed
) -> None:
    body = {**BODY, "profile_id": str(seed.child_profile_id)}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.guardian_token))
    assert res.status_code == 201


async def test_guardian_rejects_cross_family_profile(
    client: AsyncClient, seed: Seed
) -> None:
    body = {**BODY, "profile_id": str(seed.other_child_profile_id)}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.guardian_token))
    assert res.status_code == 403


async def test_guardian_must_omit_family_id(client: AsyncClient, seed: Seed) -> None:
    body = {**BODY, "family_id": str(seed.family_id)}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.guardian_token))
    assert res.status_code == 422


async def test_child_cannot_author(client: AsyncClient, seed: Seed) -> None:
    res = await client.post(AUTHORED, json=BODY, headers=auth(seed.child_token))
    assert res.status_code == 403


async def test_admin_requires_family_id(client: AsyncClient, seed: Seed) -> None:
    res = await client.post(AUTHORED, json=BODY, headers=auth(seed.admin_token))
    assert res.status_code == 422


async def test_admin_authored_create_targets_named_family(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    body = {**BODY, "family_id": str(seed.family_id)}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.admin_token))
    assert res.status_code == 201
    async with sessions() as session:
        row = await session.get(StoryRequest, uuid.UUID(res.json()["id"]))
        assert row is not None
        assert row.initiator_role == "admin"
        assert row.family_id == seed.family_id


async def test_admin_unknown_family_is_404(client: AsyncClient, seed: Seed) -> None:
    body = {**BODY, "family_id": "00000000-0000-0000-0000-000000000000"}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.admin_token))
    assert res.status_code == 404


async def test_authored_missing_length_is_422(client: AsyncClient, seed: Seed) -> None:
    res = await client.post(
        AUTHORED,
        json={"request_text": "a turtle tale", "age_band": "5-8"},
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 422


async def test_authored_gamebook_below_teen_band_is_422(
    client: AsyncClient, seed: Seed
) -> None:
    res = await client.post(
        AUTHORED,
        json={**BODY, "narrative_style": "gamebook"},
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 422


async def test_blocked_screening_persists_blocked_row_without_concept(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    # PII guard blocks text naming a family child; read the seeded child's
    # display name from the DB rather than hardcoding the fixture value.
    async with sessions() as session:
        from cyo_adventure.db.models import ChildProfile

        profile = await session.get(ChildProfile, seed.child_profile_id)
        assert profile is not None
        child_name = profile.display_name
    body = {**BODY, "request_text": f"a story starring {child_name} the brave"}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.guardian_token))
    assert res.status_code == 201
    payload = res.json()
    assert payload["status"] == "blocked"
    assert payload["concept_id"] is None
    async with sessions() as session:
        row = await session.get(StoryRequest, uuid.UUID(payload["id"]))
        assert row is not None
        assert row.concept_id is None


async def test_authored_request_lists_with_null_profile_id(
    client: AsyncClient, seed: Seed
) -> None:
    created = await client.post(AUTHORED, json=BODY, headers=auth(seed.guardian_token))
    request_id = created.json()["id"]
    res = await client.get("/api/v1/story-requests", headers=auth(seed.guardian_token))
    target = next(r for r in res.json()["requests"] if r["id"] == request_id)
    assert target["profile_id"] is None


async def test_admin_lists_families_guardian_forbidden(
    client: AsyncClient, seed: Seed
) -> None:
    res = await client.get("/api/v1/admin/families", headers=auth(seed.admin_token))
    assert res.status_code == 200
    ids = [f["id"] for f in res.json()["families"]]
    assert str(seed.family_id) in ids
    forbidden = await client.get(
        "/api/v1/admin/families", headers=auth(seed.guardian_token)
    )
    assert forbidden.status_code == 403
