"""Integration tests: every lifecycle transition writes exactly one pipeline_event."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.integration._event_assertions import assert_single_event
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio

_CREATE = "/api/v1/story-requests"


async def test_kid_create_writes_request_created(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    resp = await client.post(
        _CREATE,
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a story about a brave fox",
        },
    )
    assert resp.status_code in (200, 201), resp.text
    await assert_single_event(
        sessions,
        event_type="request_created",
        entity_type="story_request",
        actor_role="child",
    )


async def test_decline_writes_request_declined(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    create = await client.post(
        _CREATE,
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a story about a brave fox",
        },
    )
    request_id = create.json()["id"]
    resp = await client.post(
        f"{_CREATE}/{request_id}/decline",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 200, resp.text
    await assert_single_event(
        sessions,
        event_type="request_declined",
        entity_type="story_request",
        to_state="declined",
        actor_role="guardian",
    )


async def test_approve_writes_request_approved(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    create = await client.post(
        _CREATE,
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a story about a brave fox",
        },
    )
    request_id = create.json()["id"]
    resp = await client.post(
        f"{_CREATE}/{request_id}/approve",
        headers=auth(seed.guardian_token),
        # WS-B: approve requires a confirmation body; band matches the
        # seeded profile's own band (conftest.Seed's profile_a, "10-13").
        json={"age_band": "10-13", "length": "medium", "narrative_style": "prose"},
    )
    assert resp.status_code == 200, resp.text
    await assert_single_event(
        sessions,
        event_type="request_approved",
        entity_type="story_request",
        to_state="approved",
        actor_role="guardian",
    )


async def test_authoring_plan_writes_plan_assigned(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    create = await client.post(
        _CREATE,
        headers=auth(seed.child_token),
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a story about a brave fox",
        },
    )
    request_id = create.json()["id"]
    approved = await client.post(
        f"{_CREATE}/{request_id}/approve",
        headers=auth(seed.guardian_token),
        # WS-B: approve requires a confirmation body; band matches the
        # seeded profile's own band (conftest.Seed's profile_a, "10-13").
        json={"age_band": "10-13", "length": "medium", "narrative_style": "prose"},
    )
    assert approved.status_code == 200, approved.text
    resp = await client.post(
        f"{_CREATE}/{request_id}/authoring-plan",
        headers=auth(seed.admin_token),
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "prep_model": "openrouter/some-model",
        },
    )
    assert resp.status_code == 201, resp.text
    await assert_single_event(
        sessions,
        event_type="plan_assigned",
        entity_type="generation_job",
        actor_role="admin",
    )
