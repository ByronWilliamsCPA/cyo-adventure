"""Unit test for resume_manual_fill's Stage 1 violation recording."""

from __future__ import annotations

import uuid

import pytest

from cyo_adventure.db.models import Concept, GenerationJob
from cyo_adventure.generation import import_story

pytestmark = pytest.mark.asyncio


class _FakeSession:
    def __init__(self, *, job: GenerationJob, concept: Concept) -> None:
        self._job = job
        self._concept = concept
        self.commits = 0

    async def get(self, model: type[object], key: object) -> object | None:
        _ = key
        if model is GenerationJob:
            return self._job
        if model is Concept:
            return self._concept
        return None

    async def commit(self) -> None:
        self.commits += 1


async def test_stage1_violations_are_recorded_on_the_job(monkeypatch) -> None:
    """A Stage 1 violation is appended to the job's report, not silently dropped."""
    concept = Concept(id=uuid.uuid4(), family_id=uuid.uuid4(), brief={})
    job = GenerationJob(
        id=uuid.uuid4(),
        concept_id=concept.id,
        status="awaiting_manual_fill",
        authoring_metadata={"skeleton_slug": "x", "theme_brief": {}},
    )
    session = _FakeSession(job=job, concept=concept)

    async def _fake_import_filled_story(_session, _request):
        return "s_x"

    async def _fake_run_stage1_gate(*args, **kwargs):
        return ["node 'n1' word count 3 outside [6, 14] for target 10"]

    monkeypatch.setattr(import_story, "import_filled_story", _fake_import_filled_story)
    monkeypatch.setattr(import_story, "run_stage1_gate", _fake_run_stage1_gate)
    # NOTE: import_story does `from cyo_adventure.generation.skeleton import
    # load_skeleton` (a bare-name import), so it holds its own binding in
    # import_story's module namespace. Patching the origin module's attribute
    # (cyo_adventure.generation.skeleton.load_skeleton) does not affect that
    # already-bound name; the patch target must be import_story itself.
    monkeypatch.setattr(import_story, "load_skeleton", lambda _path: {"nodes": []})

    story_id = await import_story.resume_manual_fill(
        session, job.id, {"id": "s_x", "nodes": []}
    )

    assert story_id == "s_x"
    assert job.status == "needs_review"
    assert job.error is not None
    assert "word count" in job.error
