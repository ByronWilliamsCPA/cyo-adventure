"""Integration tests for POST /story-requests/{id}/authoring-plan."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from cyo_adventure.db.models import GenerationJob, ProviderModelAllowlist
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio

_CREATE = "/api/v1/story-requests"


@pytest_asyncio.fixture(autouse=True)
async def _seed_allowlist(sessions: async_sessionmaker[AsyncSession]) -> None:
    """Seed one enabled allowlist row so automated_provider requests validate.

    Every test in this module either exercises mechanism='automated_provider'
    (which now requires an enabled allowlist pair) or is unaffected by the
    allowlist (mechanism='skill'); seeding one canonical row here keeps every
    existing test body's literal provider/model working without a per-test
    insert.
    """
    async with sessions() as session:
        session.add(
            ProviderModelAllowlist(
                provider="anthropic", model_id="claude-sonnet-4-6", enabled=True
            )
        )
        await session.commit()


async def _approved_request_id(client: AsyncClient, seed: Seed, text: str) -> str:
    created = await client.post(
        _CREATE,
        json={"profile_id": str(seed.child_profile_id), "request_text": text},
        headers=auth(seed.guardian_token),
    )
    req_id = created.json()["id"]
    approved = await client.post(
        f"{_CREATE}/{req_id}/approve",
        headers=auth(seed.admin_token),
        # WS-B: approve requires a confirmation body; band matches the
        # seeded profile's own band (conftest.Seed's profile_a, "10-13").
        json={"age_band": "10-13", "length": "medium", "narrative_style": "prose"},
    )
    assert approved.status_code == 200, approved.text
    return req_id


@asynccontextmanager
async def _session_ctx(
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Wrap a session from the factory in a context manager."""
    session = sessions()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def _make_session_factory(
    sessions: async_sessionmaker[AsyncSession],
):  # type: ignore[return]
    """Return a callable session factory compatible with worker's session_factory."""

    def factory():  # type: ignore[return-value]
        return _session_ctx(sessions)

    return factory


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
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
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


async def test_skeleton_fill_automated_provider_enqueues(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Plan 2: automated skeleton-fill prep is now supported and queued."""
    req_id = await _approved_request_id(client, seed, "a quiet library")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "skeleton_fill",
            "mechanism": "automated_provider",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "queued"
    assert body["skeleton_slug"]

    async with sessions() as session:
        job = await session.get(GenerationJob, uuid.UUID(body["job_id"]))
        assert job is not None
        assert job.status == "queued"
        assert job.authoring_metadata is not None


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
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
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
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
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
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
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
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
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
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 404, res.text


async def test_skeleton_fill_automated_provider_runs_end_to_end(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The full automated skeleton_fill path: authoring-plan -> worker -> storybook.

    Runs the worker function directly (as api/generation.py's own tests do
    for the fresh_generation path) rather than through RQ, since RQ/Redis are
    not part of the integration test harness.
    """
    req_id = await _approved_request_id(client, seed, "a curious fox and a lantern")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "skeleton_fill",
            "mechanism": "automated_provider",
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
            "prep_model": "mock",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 201, res.text
    job_id = res.json()["job_id"]

    # #ASSUME: external-resources: this test runs the worker against an
    # explicitly-injected mock provider so it stays hermetic (no network). The
    # request body sets provider="anthropic", and the worker now honors that
    # per-job override over the settings default; passing a non-None provider
    # here intentionally bypasses that override so the test does not need a real
    # ANTHROPIC_API_KEY. The override-read path itself is unit-tested in
    # test_worker.py::test_effective_provider_reads_job_authoring_override. A
    # mock provider cannot produce a schema-valid filled skeleton from a real
    # prompt, so this test only asserts the job REACHES a terminal status
    # (passed/needs_review/failed), not that it passes cleanly.
    # #VERIFY: if the injected provider is ever removed, this test starts making
    # a real network call instead of reaching a terminal status hermetically.
    from cyo_adventure.generation.provider import _CANNED_STORY_JSON, MockProvider
    from cyo_adventure.generation.worker import run_generation_job

    await run_generation_job(
        uuid.UUID(job_id),
        session_factory=_make_session_factory(sessions),
        provider=MockProvider(responses=[_CANNED_STORY_JSON] * 8),
    )

    res = await client.get(
        f"/api/v1/generation-jobs/{job_id}", headers=auth(seed.guardian_token)
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] in {"passed", "needs_review", "failed"}


async def test_automated_provider_unallowlisted_model_is_422(
    client: AsyncClient, seed: Seed
) -> None:
    """A provider/model pair with no enabled allowlist row is rejected."""
    req_id = await _approved_request_id(client, seed, "a stray comet")
    res = await client.post(
        f"{_CREATE}/{req_id}/authoring-plan",
        json={
            "method": "fresh_generation",
            "mechanism": "automated_provider",
            "provider": "anthropic",
            "model": "not-a-real-model",
            "prep_model": "openrouter/some-model",
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422
