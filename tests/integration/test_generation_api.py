"""Integration tests for the guardian-only generation, concept, and validate endpoints.

All tests reuse the two-family seed from conftest.py (guardian_token,
child_token, other_guardian_token, other_child_token, family_id, etc.).

Redis / enqueue: tests do NOT require a live Redis instance. The generation
endpoints are designed so that a Redis connection failure is caught and
logged; the GenerationJob row is still created and 202 is returned.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import ChildProfile, Concept, GenerationJob
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


# ---------------------------------------------------------------------------
# Shared minimal ConceptBrief payload for happy-path tests.
# ---------------------------------------------------------------------------

_BRIEF_PAYLOAD = {
    "title": "The Dragon's Cave",
    "premise": "A young hero ventures into a mysterious cave to rescue a lost pet.",
    "protagonist": {
        "name": "Captain Rosa",
        "age": 10,
        "role": "young explorer",
    },
    "point_of_view": "second",
    "age_band": "8-11",
    "reading_level_target": 4.0,
    "tier": 1,
    "tone": "adventurous",
    "themes_allowed": ["friendship", "bravery"],
    "content_nogo": [],
    "target_node_count": 5,
    "ending_count": 2,
    "structure_pattern": "branch_and_bottleneck",
    "desired_variables": [],
    "special_constraints": [],
}


# ---------------------------------------------------------------------------
# Test 1: Guardian creates a concept
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardian_creates_concept(client: AsyncClient, seed: Seed) -> None:
    """Guardian can POST /concepts and receives a concept_id."""
    resp = await client.post(
        "/api/v1/concepts",
        json={"brief": _BRIEF_PAYLOAD},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "concept_id" in data
    # Must be a valid UUID string.
    uuid.UUID(data["concept_id"])


# ---------------------------------------------------------------------------
# Test 2: Child token is rejected on all four endpoints (403)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_token_rejected_on_concepts(
    client: AsyncClient, seed: Seed
) -> None:
    """Child token cannot POST /concepts -> 403."""
    resp = await client.post(
        "/api/v1/concepts",
        json={"brief": _BRIEF_PAYLOAD},
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_token_rejected_on_generate(
    client: AsyncClient, seed: Seed
) -> None:
    """Child token cannot POST /concepts/{id}/generate -> 403."""
    # Use a random UUID; the 403 must fire before the 404 would.
    fake_id = str(uuid.uuid4())
    resp = await client.post(
        f"/api/v1/concepts/{fake_id}/generate",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_token_rejected_on_generation_jobs(
    client: AsyncClient, seed: Seed
) -> None:
    """Child token cannot GET /generation-jobs/{id} -> 403."""
    fake_id = str(uuid.uuid4())
    resp = await client.get(
        f"/api/v1/generation-jobs/{fake_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_token_rejected_on_validate(
    client: AsyncClient,
    seed: Seed,
) -> None:
    """Child token cannot POST .../validate -> 403."""
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/validate",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Test 3: Guardian enqueues generation; job row exists
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardian_enqueues_generation(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Guardian can enqueue a job; 202 returned and row exists with status queued."""
    # First create a concept.
    concept_resp = await client.post(
        "/api/v1/concepts",
        json={"brief": _BRIEF_PAYLOAD},
        headers=auth(seed.guardian_token),
    )
    assert concept_resp.status_code == 201, concept_resp.text
    concept_id = concept_resp.json()["concept_id"]

    # Enqueue generation (Redis may be absent; should still return 202).
    enqueue_resp = await client.post(
        f"/api/v1/concepts/{concept_id}/generate",
        headers=auth(seed.guardian_token),
    )
    assert enqueue_resp.status_code == 202, enqueue_resp.text
    data = enqueue_resp.json()
    assert "job_id" in data
    job_id = data["job_id"]
    uuid.UUID(job_id)

    # Confirm the row exists and is owned by the right family.
    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        concept = await session.get(Concept, concept_id)
        assert concept is not None
        assert concept.family_id == seed.family_id


# ---------------------------------------------------------------------------
# Test 4: Cross-family access is blocked
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cross_family_cannot_read_generation_job(
    client: AsyncClient,
    seed: Seed,
) -> None:
    """Family B's guardian cannot read family A's generation job -> 403."""
    # Create a concept and job under family A's guardian.
    concept_resp = await client.post(
        "/api/v1/concepts",
        json={"brief": _BRIEF_PAYLOAD},
        headers=auth(seed.guardian_token),
    )
    assert concept_resp.status_code == 201, concept_resp.text
    concept_id = concept_resp.json()["concept_id"]

    enqueue_resp = await client.post(
        f"/api/v1/concepts/{concept_id}/generate",
        headers=auth(seed.guardian_token),
    )
    assert enqueue_resp.status_code == 202, enqueue_resp.text
    job_id = enqueue_resp.json()["job_id"]

    # Family B's guardian tries to read family A's job -> 403.
    cross_resp = await client.get(
        f"/api/v1/generation-jobs/{job_id}",
        headers=auth(seed.other_guardian_token),
    )
    assert cross_resp.status_code == 403, cross_resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cross_family_cannot_generate_on_other_concept(
    client: AsyncClient,
    seed: Seed,
) -> None:
    """Family B's guardian cannot enqueue generation for family A's concept -> 403."""
    concept_resp = await client.post(
        "/api/v1/concepts",
        json={"brief": _BRIEF_PAYLOAD},
        headers=auth(seed.guardian_token),
    )
    assert concept_resp.status_code == 201, concept_resp.text
    concept_id = concept_resp.json()["concept_id"]

    cross_resp = await client.post(
        f"/api/v1/concepts/{concept_id}/generate",
        headers=auth(seed.other_guardian_token),
    )
    assert cross_resp.status_code == 403, cross_resp.text


# ---------------------------------------------------------------------------
# Test 5: PII in brief premise -> 422
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pii_in_brief_rejected(client: AsyncClient, seed: Seed) -> None:
    """A concept brief whose premise contains a real child's display name -> 422.

    The seeded child profile for family A has display_name "Reader A".
    Embedding that name in the premise must trip the PII guard.
    """
    pii_brief = {
        **_BRIEF_PAYLOAD,
        # Embed the seeded child's exact display name in the free-text field.
        "premise": "Reader A ventures into a mysterious cave.",
    }
    resp = await client.post(
        "/api/v1/concepts",
        json={"brief": pii_brief},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# Test 6: Validate endpoint
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_validate_storybook_version(client: AsyncClient, seed: Seed) -> None:
    """Guardian can validate an existing storybook version; response has report + blocked."""
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/validate",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "blocked" in data
    assert isinstance(data["blocked"], bool)
    assert "report" in data
    assert "findings" in data["report"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_validate_cross_family_blocked(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Family B's guardian cannot validate family A's storybook version -> 403."""
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/validate",
        headers=auth(seed.other_guardian_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_validate_storybook_version_not_found(
    client: AsyncClient, seed: Seed
) -> None:
    """Validating a non-existent version returns 404."""
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/9999/validate",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_validate_storybook_not_found(client: AsyncClient, seed: Seed) -> None:
    """Validating a non-existent storybook returns 404."""
    resp = await client.post(
        "/api/v1/storybooks/no-such-story/versions/1/validate",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Test 7: GET /generation-jobs/{job_id} happy path
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_generation_job(
    client: AsyncClient,
    seed: Seed,
) -> None:
    """Guardian can fetch a generation job they own, and gets None for the
    skeleton/theme fields since this job has no authoring_metadata."""
    concept_resp = await client.post(
        "/api/v1/concepts",
        json={"brief": _BRIEF_PAYLOAD},
        headers=auth(seed.guardian_token),
    )
    assert concept_resp.status_code == 201, concept_resp.text
    concept_id = concept_resp.json()["concept_id"]

    enqueue_resp = await client.post(
        f"/api/v1/concepts/{concept_id}/generate",
        headers=auth(seed.guardian_token),
    )
    assert enqueue_resp.status_code == 202, enqueue_resp.text
    job_id = enqueue_resp.json()["job_id"]

    job_resp = await client.get(
        f"/api/v1/generation-jobs/{job_id}",
        headers=auth(seed.guardian_token),
    )
    assert job_resp.status_code == 200, job_resp.text
    data = job_resp.json()
    assert data["id"] == job_id
    assert data["status"] in {"queued", "running", "passed", "needs_review", "failed"}
    assert data["skeleton_slug"] is None
    assert data["theme_brief"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_job_exposes_skeleton_and_theme_brief_when_parked(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """An awaiting_manual_fill job's GET response carries skeleton_slug and
    theme_brief so a human (or Plan 2's automated path) knows what to fill."""
    async with sessions() as session:
        concept = Concept(
            family_id=seed.family_id,
            brief={"age_band": "8-11", "premise": "a fox finds a lantern"},
        )
        session.add(concept)
        await session.flush()
        job = GenerationJob(
            concept_id=concept.id,
            status="awaiting_manual_fill",
            model="sonnet",
            authoring_metadata={
                "skeleton_slug": "the-cave-of-echoes",
                "theme_brief": concept.brief,
            },
        )
        session.add(job)
        await session.commit()
        job_id = str(job.id)

    res = await client.get(
        f"/api/v1/generation-jobs/{job_id}", headers=auth(seed.guardian_token)
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["skeleton_slug"] == "the-cave-of-echoes"
    assert body["theme_brief"] == {
        "age_band": "8-11",
        "premise": "a fox finds a lantern",
    }


# ---------------------------------------------------------------------------
# Test 8: GET /generation-jobs list endpoint
# ---------------------------------------------------------------------------


async def _seed_job(
    sessions: async_sessionmaker[AsyncSession],
    *,
    family_id: uuid.UUID,
    status: str,
    created_at: datetime,
    storybook_id: str | None = None,
    report: dict[str, object] | None = None,
    error: str | None = None,
) -> str:
    """Insert a Concept + GenerationJob for a family and return the job id."""
    async with sessions() as session:
        concept = Concept(family_id=family_id, brief=dict(_BRIEF_PAYLOAD))
        session.add(concept)
        await session.flush()
        job = GenerationJob(
            concept_id=concept.id,
            status=status,
            created_at=created_at,
            storybook_id=storybook_id,
            report=report,
            error=error,
        )
        session.add(job)
        await session.commit()
        return str(job.id)


async def _other_family_id(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> uuid.UUID:
    """Resolve Family B's id via its seeded child profile.

    The Seed dataclass does not carry Family B's family_id directly; the
    other_child_profile_id row does.
    """
    async with sessions() as session:
        profile = await session.get(ChildProfile, seed.other_child_profile_id)
        assert profile is not None
        return profile.family_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_jobs_child_token_rejected(client: AsyncClient, seed: Seed) -> None:
    """A child token cannot list generation jobs -> 403."""
    resp = await client.get("/api/v1/generation-jobs", headers=auth(seed.child_token))
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_jobs_is_family_scoped(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Family B's guardian sees Family B's jobs and never Family A's."""
    a_job = await _seed_job(
        sessions,
        family_id=seed.family_id,
        status="queued",
        created_at=datetime(2026, 7, 2, 10, 0, tzinfo=UTC),
    )
    b_job = await _seed_job(
        sessions,
        family_id=await _other_family_id(sessions, seed),
        status="queued",
        created_at=datetime(2026, 7, 2, 10, 30, tzinfo=UTC),
    )
    resp = await client.get(
        "/api/v1/generation-jobs", headers=auth(seed.other_guardian_token)
    )
    assert resp.status_code == 200, resp.text
    ids = {row["id"] for row in resp.json()["jobs"]}
    assert b_job in ids
    assert a_job not in ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_jobs_newest_first(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Jobs are returned newest-first by created_at."""
    older = await _seed_job(
        sessions,
        family_id=seed.family_id,
        status="queued",
        created_at=datetime(2026, 7, 1, 9, 0, tzinfo=UTC),
    )
    newer = await _seed_job(
        sessions,
        family_id=seed.family_id,
        status="queued",
        created_at=datetime(2026, 7, 2, 9, 0, tzinfo=UTC),
    )
    resp = await client.get(
        "/api/v1/generation-jobs", headers=auth(seed.guardian_token)
    )
    assert resp.status_code == 200, resp.text
    ids = [row["id"] for row in resp.json()["jobs"]]
    assert ids.index(newer) < ids.index(older)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_jobs_surfaces_storybook_status(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A passed job linked to the published seed storybook reports its status.

    A job with no linked storybook must report storybook_status None, so a
    hardcoded "published" cannot satisfy this test.
    """
    job_id = await _seed_job(
        sessions,
        family_id=seed.family_id,
        status="passed",
        created_at=datetime(2026, 7, 2, 11, 0, tzinfo=UTC),
        storybook_id=seed.storybook_id,
    )
    unlinked_id = await _seed_job(
        sessions,
        family_id=seed.family_id,
        status="queued",
        created_at=datetime(2026, 7, 2, 11, 30, tzinfo=UTC),
        storybook_id=None,
    )
    resp = await client.get(
        "/api/v1/generation-jobs", headers=auth(seed.guardian_token)
    )
    assert resp.status_code == 200, resp.text
    rows = {r["id"]: r for r in resp.json()["jobs"]}
    row = rows[job_id]
    assert row["storybook_status"] == "published"
    assert row["age_band"] == _BRIEF_PAYLOAD["age_band"]
    assert rows[unlinked_id]["storybook_status"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_jobs_never_exposes_report(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The raw report column must never appear in the list payload."""
    await _seed_job(
        sessions,
        family_id=seed.family_id,
        status="failed",
        created_at=datetime(2026, 7, 2, 12, 0, tzinfo=UTC),
        report={"leak_marker": "raw-model-output"},
        error="pipeline blew up",
    )
    resp = await client.get(
        "/api/v1/generation-jobs", headers=auth(seed.guardian_token)
    )
    assert resp.status_code == 200, resp.text
    assert "leak_marker" not in resp.text
    for row in resp.json()["jobs"]:
        assert "report" not in row


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_jobs_caps_at_50(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The list caps at 50 rows and truncates the oldest job first.

    Seed 51 jobs with strictly increasing created_at; the response must hold
    exactly 50 rows and the oldest (first-seeded) job must be the one dropped,
    which also re-pins newest-first ordering under truncation.
    """
    base = datetime(2026, 6, 1, 8, 0, tzinfo=UTC)
    job_ids = [
        await _seed_job(
            sessions,
            family_id=seed.family_id,
            status="queued",
            created_at=base + timedelta(minutes=i),
        )
        for i in range(51)
    ]
    oldest = job_ids[0]
    resp = await client.get(
        "/api/v1/generation-jobs", headers=auth(seed.guardian_token)
    )
    assert resp.status_code == 200, resp.text
    jobs = resp.json()["jobs"]
    assert len(jobs) == 50
    ids = {row["id"] for row in jobs}
    assert oldest not in ids
