"""Authored (guardian/admin) story-request creation: WS-B PR 2 contract."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.api.families import _FAMILY_LIST_LIMIT
from cyo_adventure.db.models import Concept, Family, StoryRequest
from tests.integration.conftest import Seed, Stranger, auth

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


async def test_guardian_may_name_own_family(client: AsyncClient, seed: Seed) -> None:
    """Naming your own family is a harmless self-reference, not an error.

    The pre-dual-role contract 422'd any guardian-supplied family_id; the
    optional-family contract accepts the caller's own id.
    """
    body = {**BODY, "family_id": str(seed.family_id)}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.guardian_token))
    assert res.status_code == 201


async def test_guardian_foreign_family_is_403(client: AsyncClient, seed: Seed) -> None:
    """A guardian without the admin capability cannot author into another family.

    403 outright, before any existence lookup, so the endpoint is not a
    family-id oracle: a nonexistent id and a real foreign family's id must
    be indistinguishable to a plain guardian.
    """
    body = {**BODY, "family_id": str(uuid.uuid4())}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.guardian_token))
    assert res.status_code == 403


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


async def test_admin_cross_family_profile_is_403(
    client: AsyncClient, seed: Seed
) -> None:
    body = {
        **BODY,
        "family_id": str(seed.family_id),
        "profile_id": str(seed.other_child_profile_id),
    }
    res = await client.post(AUTHORED, json=body, headers=auth(seed.admin_token))
    assert res.status_code == 403


async def test_admin_unknown_family_is_404(client: AsyncClient, seed: Seed) -> None:
    body = {**BODY, "family_id": "00000000-0000-0000-0000-000000000000"}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.admin_token))
    assert res.status_code == 404


async def test_guardian_real_foreign_family_is_403(
    client: AsyncClient, seed: Seed, stranger: Stranger
) -> None:
    """A real foreign family id gets the same 403 as a nonexistent one."""
    body = {**BODY, "family_id": str(stranger.family_id)}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.guardian_token))
    assert res.status_code == 403


async def test_dual_role_omitted_family_targets_own(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A dual-role adult omitting family_id authors into their own family.

    The row is stamped in the guardian capacity: acting within your own
    family never needs (and never records) the admin capability.
    """
    res = await client.post(AUTHORED, json=BODY, headers=auth(seed.dual_token))
    assert res.status_code == 201
    async with sessions() as session:
        row = await session.get(StoryRequest, uuid.UUID(res.json()["id"]))
        assert row is not None
        assert row.family_id == seed.family_id
        assert row.initiator_role == "guardian"


async def test_dual_role_foreign_family_is_stamped_admin(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    stranger: Stranger,
) -> None:
    """A dual-role adult authoring into a foreign family acts as admin.

    Only the admin capability can authorize the cross-family write, so the
    audit stamp records admin, not the guardian base persona.
    """
    body = {**BODY, "family_id": str(stranger.family_id)}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.dual_token))
    assert res.status_code == 201
    async with sessions() as session:
        row = await session.get(StoryRequest, uuid.UUID(res.json()["id"]))
        assert row is not None
        assert row.family_id == stranger.family_id
        assert row.initiator_role == "admin"


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


async def test_blocked_authored_row_is_terminal(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A blocked authored row rejects approve, decline, and authoring-plan (409)."""
    async with sessions() as session:
        from cyo_adventure.db.models import ChildProfile

        profile = await session.get(ChildProfile, seed.child_profile_id)
        assert profile is not None
        child_name = profile.display_name
    body = {**BODY, "request_text": f"a story starring {child_name} the brave"}
    created = await client.post(AUTHORED, json=body, headers=auth(seed.guardian_token))
    assert created.status_code == 201
    request_id = created.json()["id"]
    assert created.json()["status"] == "blocked"

    confirmation = {"age_band": "5-8", "length": "short", "narrative_style": "prose"}
    approve = await client.post(
        f"/api/v1/story-requests/{request_id}/approve",
        json=confirmation,
        headers=auth(seed.admin_token),
    )
    assert approve.status_code == 409

    decline = await client.post(
        f"/api/v1/story-requests/{request_id}/decline",
        headers=auth(seed.admin_token),
    )
    assert decline.status_code == 409

    plan = await client.post(
        f"/api/v1/story-requests/{request_id}/authoring-plan",
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.admin_token),
    )
    assert plan.status_code == 409


async def test_guardian_unknown_profile_is_403(client: AsyncClient, seed: Seed) -> None:
    """A guardian posting a nonexistent profile_id gets 403, not 404."""
    body = {**BODY, "profile_id": str(uuid.uuid4())}
    res = await client.post(AUTHORED, json=body, headers=auth(seed.guardian_token))
    assert res.status_code == 403


async def test_admin_families_list_is_name_ordered_and_capped(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """The admin family list is name-ascending; the list cap is documented."""
    async with sessions() as session:
        session.add_all([Family(name="Aardvark Family"), Family(name="Zzyxx Family")])
        await session.commit()

    res = await client.get("/api/v1/admin/families", headers=auth(seed.admin_token))
    assert res.status_code == 200
    families = res.json()["families"]
    names = [f["name"] for f in families]
    assert names == sorted(names)
    assert "Aardvark Family" in names
    assert "Zzyxx Family" in names

    # Documents the cap contract without seeding _FAMILY_LIST_LIMIT + 1 rows.
    assert _FAMILY_LIST_LIMIT == 50
    assert len(families) <= _FAMILY_LIST_LIMIT
