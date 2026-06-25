"""Integration tests for the generation worker (testcontainers Postgres).

Skips cleanly when Docker is unavailable. Uses the Postgres harness from
tests/integration/conftest.py and injects MockProvider directly so tests
are deterministic and do not depend on Redis or a live LLM.

Test cases:
4. Passing run: job.status == "passed", StorybookVersion created with blob and
   validation_report, job.storybook_id and job.version set.
5. needs_review run (injected provider returns a story that fails gate even
   after repairs): job.status == "needs_review", no StorybookVersion created.
"""

from __future__ import annotations

import json
import uuid  # noqa: TC003 -- uuid.UUID used at runtime in test bodies
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import select

from cyo_adventure.db.models import (
    ChildProfile,
    Concept,
    Family,
    GenerationJob,
    Storybook,
    StorybookVersion,
    User,
)
from cyo_adventure.generation.provider import _CANNED_STORY_JSON, MockProvider
from cyo_adventure.generation.worker import run_generation_job

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A structurally invalid story JSON that fails the gate on every attempt.
# The gate requires 'nodes' to be non-empty and each non-ending node to have
# choices; this dict has a non-ending node with no choices, which triggers L1.
_INVALID_STORY_JSON = json.dumps(
    {
        "schema_version": "2.0",
        "id": "s_bad_story",
        "version": 1,
        "title": "Bad Story",
        "metadata": {
            "age_band": "8-11",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 3.0,
                "tolerance": 1.0,
            },
            "tier": 1,
            "themes": [],
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": "branch_and_bottleneck",
            "content_flags": {
                "violence": "none",
                "scariness": "none",
                "peril": "none",
            },
        },
        "variables": [],
        "start_node": "n_start",
        "nodes": [
            # Non-ending node with NO choices: gate will block with L1 error.
            {
                "id": "n_start",
                "body": "You are stuck.",
                "is_ending": False,
                "choices": [],  # invalid: must have at least one choice
            }
        ],
    }
)


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def gen_seed(sessions: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    """Seed the minimal rows needed by the worker: Family, User, Concept, Job."""
    async with sessions() as session:
        fam = Family(name="Test Family")
        session.add(fam)
        await session.flush()

        guardian = User(
            family_id=fam.id, role="guardian", authn_subject="guardian-gen-test"
        )
        child_profile = ChildProfile(
            family_id=fam.id,
            display_name="TestKid",
            age_band="8-11",
        )
        session.add_all([guardian, child_profile])
        await session.flush()

        concept = Concept(
            family_id=fam.id,
            created_by=guardian.id,
            brief={
                "premise": "A brave explorer discovers a hidden garden.",
                "protagonist": {
                    "name": "Captain Rosa",
                    "age": 9,
                    "role": "young explorer",
                },
                "point_of_view": "second",
                "age_band": "8-11",
                "reading_level_target": 3.0,
                "tier": 1,
                "tone": "adventurous",
                "themes_allowed": ["exploration", "nature"],
                "content_nogo": [],
                "target_node_count": 4,
                "ending_count": 1,
                "structure_pattern": "time_cave",
                "desired_variables": [],
                "special_constraints": [],
            },
        )
        session.add(concept)
        await session.flush()

        job = GenerationJob(
            concept_id=concept.id,
            status="queued",
        )
        session.add(job)
        await session.commit()

        return {
            "job_id": job.id,
            "concept_id": concept.id,
            "family_id": fam.id,
        }


# ---------------------------------------------------------------------------
# Test 4: Passing run produces StorybookVersion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_passing_run_creates_storybook_version(
    sessions: async_sessionmaker[AsyncSession],
    gen_seed: dict[str, object],
) -> None:
    """A passing run creates Storybook + StorybookVersion; job links to them."""
    job_id: uuid.UUID = gen_seed["job_id"]  # type: ignore[assignment]

    # Inject a mock provider that returns valid canned story for Stage A + B.
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
        assert job.storybook_id is not None
        assert job.version == 1
        assert job.report is not None
        assert job.provider is not None
        assert job.prompt_version is not None

        # Verify Storybook row exists.
        story = await session.get(Storybook, job.storybook_id)
        assert story is not None
        assert story.status == "draft"

        # Verify StorybookVersion row exists with blob and report.
        sv = await session.get(StorybookVersion, (job.storybook_id, 1))
        assert sv is not None
        assert sv.blob is not None
        assert sv.validation_report is not None


# ---------------------------------------------------------------------------
# Test 5: needs_review run (failing story): no StorybookVersion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_needs_review_run_creates_no_storybook_version(
    sessions: async_sessionmaker[AsyncSession],
    gen_seed: dict[str, object],
) -> None:
    """A needs_review outcome creates no StorybookVersion; job records report."""
    job_id: uuid.UUID = gen_seed["job_id"]  # type: ignore[assignment]

    # Queue invalid story for all stages so the gate always blocks.
    # max_repairs defaults to 3; queue 8 copies to cover all attempts.
    provider = MockProvider(responses=[_INVALID_STORY_JSON] * 8)

    await run_generation_job(
        job_id,
        provider=provider,
        session_factory=_make_session_factory(sessions),
    )

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status in {
            "needs_review",
            "failed",
        }, f"Expected needs_review or failed, got {job.status}"
        assert job.storybook_id is None

        # Confirm no StorybookVersion exists for this job's family scope.
        result = await session.execute(
            select(StorybookVersion)
            .join(
                Storybook,
                Storybook.id == StorybookVersion.storybook_id,
            )
            .where(Storybook.family_id == gen_seed["family_id"])
        )
        assert result.first() is None, "StorybookVersion must not be created"
