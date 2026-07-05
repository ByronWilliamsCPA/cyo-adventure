"""Unit tests for resuming a skill-authored skeleton fill."""

from __future__ import annotations

import uuid

import pytest

from cyo_adventure.core.exceptions import (
    ResourceNotFoundError,
    StateTransitionError,
)
from cyo_adventure.db.models import Concept, GenerationJob
from cyo_adventure.generation.import_story import resume_manual_fill

pytestmark = pytest.mark.asyncio


class _FakeSession:
    """Minimal async session double for resume_manual_fill.

    Only implements what this module's code path touches: session.get for the
    job and concept lookups, and session.commit as a no-op recorder.
    """

    def __init__(self, *, job: GenerationJob | None, concept: Concept | None) -> None:
        self._job = job
        self._concept = concept
        self.commits = 0

    async def get(self, model: type[object], key: object) -> object | None:
        """Return the seeded job or concept by model type, ignoring the key."""
        _ = key
        if model is GenerationJob:
            return self._job
        if model is Concept:
            return self._concept
        return None

    async def commit(self) -> None:
        """Count commits without touching a real transaction."""
        self.commits += 1


async def test_resume_missing_job_is_not_found() -> None:
    """Resuming an unknown job id raises 404, not a crash."""
    session = _FakeSession(job=None, concept=None)
    with pytest.raises(ResourceNotFoundError):
        await resume_manual_fill(session, uuid.uuid4(), {"id": "s_x"})


async def test_resume_wrong_status_is_conflict() -> None:
    """A job that is not awaiting_manual_fill cannot be resumed."""
    job = GenerationJob(id=uuid.uuid4(), concept_id=uuid.uuid4(), status="queued")
    session = _FakeSession(job=job, concept=None)
    with pytest.raises(StateTransitionError):
        await resume_manual_fill(session, job.id, {"id": "s_x"})


async def test_resume_missing_concept_is_not_found() -> None:
    """A job whose concept has vanished raises 404 before importing anything."""
    job = GenerationJob(
        id=uuid.uuid4(), concept_id=uuid.uuid4(), status="awaiting_manual_fill"
    )
    session = _FakeSession(job=job, concept=None)
    with pytest.raises(ResourceNotFoundError):
        await resume_manual_fill(session, job.id, {"id": "s_x"})
