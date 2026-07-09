"""Integration tests: every lifecycle transition writes exactly one pipeline_event."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import GenerationJob
from cyo_adventure.generation.provider import _CANNED_STORY_JSON, MockProvider
from cyo_adventure.generation.worker import run_generation_job
from tests.integration._event_assertions import assert_single_event
from tests.integration.conftest import Seed, auth
from tests.integration.test_generation_worker import (
    _make_session_factory,
    gen_seed,  # noqa: F401 -- imported for pytest fixture discovery
)

if TYPE_CHECKING:
    import uuid

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


async def test_generation_run_writes_started_and_finished_system_events(
    sessions: async_sessionmaker[AsyncSession],
    gen_seed: dict[str, object],  # noqa: F811 -- pytest fixture, not the import
) -> None:
    """A full worker run writes exactly one generation_started and one
    generation_finished event, both attributed to the system actor.

    Reuses the ``gen_seed`` fixture and session-factory helper from
    test_generation_worker.py (seeded queued job + injected MockProvider)
    rather than building a new worker-test arrangement.
    """
    job_id: uuid.UUID = gen_seed["job_id"]  # type: ignore[assignment]

    provider = MockProvider(responses=[_CANNED_STORY_JSON] * 8)

    await run_generation_job(
        job_id,
        provider=provider,
        session_factory=_make_session_factory(sessions),
    )

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "passed", f"Expected passed, got {job.status}"

    await assert_single_event(
        sessions,
        event_type="generation_started",
        entity_type="generation_job",
        to_state="running",
        actor_is_system=True,
    )
    await assert_single_event(
        sessions,
        event_type="generation_finished",
        entity_type="generation_job",
        to_state="passed",
        actor_is_system=True,
    )
