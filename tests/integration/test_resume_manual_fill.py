"""Integration tests for resuming a skill-authored skeleton fill (DB-backed)."""

from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import Concept, GenerationJob
from cyo_adventure.generation.import_story import resume_manual_fill

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from tests.integration.conftest import Seed

pytestmark = pytest.mark.asyncio

_FILLED = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "storybook"
    / "valid"
    / "03_tier2_lantern.json"
)


async def _parked_job(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> tuple[str, dict[str, object]]:
    async with sessions() as session:
        concept = Concept(
            family_id=seed.family_id, brief={"age_band": "8-11", "premise": "x"}
        )
        session.add(concept)
        await session.flush()
        job = GenerationJob(
            concept_id=concept.id,
            status="awaiting_manual_fill",
            model="sonnet",
            authoring_metadata={
                "skeleton_slug": "the-cave-of-echoes",
                "theme_brief": {},
            },
        )
        session.add(job)
        await session.commit()
        job_id = str(job.id)
    blob = json.loads(_FILLED.read_text(encoding="utf-8"))
    return job_id, blob


async def test_resume_success_marks_job_passed(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A valid filled blob passes the gate; the job is marked passed and linked."""
    job_id, blob = await _parked_job(sessions, seed)
    blob = dict(blob)
    blob["id"] = f"s_resume_{job_id}"

    async with sessions() as session:
        story_id = await resume_manual_fill(session, uuid.UUID(job_id), blob)
        await session.commit()

    async with sessions() as session:
        job = await session.get(GenerationJob, uuid.UUID(job_id))
        assert job is not None
        assert job.status == "passed"
        assert job.storybook_id == story_id
        assert job.version == 1


async def test_resume_gate_block_marks_job_failed(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A structurally-broken blob is blocked by the gate; job is marked failed."""
    job_id, blob = await _parked_job(sessions, seed)
    broken = copy.deepcopy(blob)
    broken["nodes"] = []  # an empty node list fails the gate's structural checks

    async with sessions() as session:
        with pytest.raises(ValidationError):
            await resume_manual_fill(session, uuid.UUID(job_id), broken)

    async with sessions() as session:
        job = await session.get(GenerationJob, uuid.UUID(job_id))
        assert job is not None
        assert job.status == "failed"
        assert job.error is not None
