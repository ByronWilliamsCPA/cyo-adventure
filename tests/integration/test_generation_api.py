"""Integration tests for the guardian-only generation, concept, and validate endpoints.

All tests reuse the two-family seed from conftest.py (guardian_token,
child_token, other_guardian_token, other_child_token, family_id, etc.).

Redis / enqueue: tests do NOT require a live Redis instance. The generation
endpoints are designed so that a Redis connection failure is caught and
logged; the GenerationJob row is still created and 202 is returned.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import Concept, GenerationJob
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
    """Guardian can fetch a generation job they own."""
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
