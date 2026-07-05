"""Integration tests for POST /story-requests/{id}/authoring-plan."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import GenerationJob
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio

_CREATE = "/api/v1/story-requests"


async def _approved_request_id(client: AsyncClient, seed: Seed, text: str) -> str:
    created = await client.post(
        _CREATE,
        json={"profile_id": str(seed.child_profile_id), "request_text": text},
        headers=auth(seed.guardian_token),
    )
    req_id = created.json()["id"]
    approved = await client.post(
        f"{_CREATE}/{req_id}/approve", headers=auth(seed.admin_token)
    )
    assert approved.status_code == 200, approved.text
    return req_id


async def test_fresh_generation_automated_provider_enqueues(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The unchanged path: admin picks fresh_generation, job is queued."""
    req_id = await _approved_request_id(client, seed, "a curious otter")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "queued"
    assert body["skeleton_slug"] is None
    assert body["warnings"] == []

    async with sessions() as session:
        job = await session.get(GenerationJob, uuid.UUID(body["job_id"]))
        assert job is not None
        assert job.status == "queued"


async def test_skeleton_fill_skill_parks_job(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """skeleton_fill + skill parks the job with skeleton + theme_brief metadata."""
    req_id = await _approved_request_id(client, seed, "a lighthouse keeper")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={"method": "skeleton_fill", "mechanism": "skill", "prep_model": "sonnet"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "awaiting_manual_fill"
    assert body["skeleton_slug"]

    async with sessions() as session:
        job = await session.get(GenerationJob, uuid.UUID(body["job_id"]))
        assert job is not None
        assert job.authoring_metadata is not None
        assert job.authoring_metadata["skeleton_slug"] == body["skeleton_slug"]


async def test_fresh_generation_with_skill_mechanism_is_422(
    client: AsyncClient, seed: Seed
) -> None:
    """Invalid combo: fresh_generation can never use mechanism='skill'."""
    req_id = await _approved_request_id(client, seed, "a stubborn goat")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "fresh_generation",
            "mechanism": "skill",
            "prep_model": "sonnet",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422, res.text


async def test_skeleton_fill_automated_provider_is_422(
    client: AsyncClient, seed: Seed
) -> None:
    """Plan 1 restriction: automated skeleton-fill prep is not yet supported."""
    req_id = await _approved_request_id(client, seed, "a quiet library")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "skeleton_fill",
            "mechanism": "automated_provider",
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422, res.text


async def test_unrecognized_skill_model_is_422(client: AsyncClient, seed: Seed) -> None:
    """A model outside SKILL_MECHANISM_MODELS is rejected for mechanism='skill'.

    Note: the task brief this test was drafted from expected 400 here. The
    service layer (story_requests/authoring_plan.py, already complete and
    fully unit-tested from Task 7) raises the same ValidationError for this
    case as it does for the two invalid method/mechanism combos above, and
    app.py's ``_status_for`` maps every ValidationError to 422 (there is no
    branch that yields 400 for this exception type). 422 is therefore the
    actual, verified behavior; see task-8-report.md for the full analysis.
    """
    req_id = await _approved_request_id(client, seed, "a shy dragon")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={"method": "skeleton_fill", "mechanism": "skill", "prep_model": "gpt-4o"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422, res.text


async def test_not_yet_approved_is_409(client: AsyncClient, seed: Seed) -> None:
    """A still-pending request cannot get an authoring plan."""
    created = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a pending fox",
        },
        headers=auth(seed.guardian_token),
    )
    req_id = created.json()["id"]
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 409, res.text


async def test_duplicate_authoring_plan_is_409(client: AsyncClient, seed: Seed) -> None:
    """A second authoring-plan call for the same request conflicts."""
    req_id = await _approved_request_id(client, seed, "a determined snail")
    body = {
        "method": "fresh_generation",
        "mechanism": "automated_provider",
        "prep_model": "openrouter/some-model",
    }
    first = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan", json=body, headers=auth(seed.admin_token)
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan", json=body, headers=auth(seed.admin_token)
    )
    assert second.status_code == 409, second.text


async def test_guardian_forbidden(client: AsyncClient, seed: Seed) -> None:
    """Only an admin may create an authoring plan, per the design decision."""
    req_id = await _approved_request_id(client, seed, "a guardian-approved tale")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 403, res.text


async def test_child_forbidden(client: AsyncClient, seed: Seed) -> None:
    """A child token must never reach the authoring-plan endpoint."""
    req_id = await _approved_request_id(client, seed, "a child-visible tale")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.child_token),
    )
    assert res.status_code == 403, res.text


async def test_unknown_request_is_404(client: AsyncClient, seed: Seed) -> None:
    """A nonexistent request id is 404 even for an admin (global scope)."""
    res = await client.post(
        f"{_CREATE}/{uuid.uuid4()}/authoring-plan",
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 404, res.text
