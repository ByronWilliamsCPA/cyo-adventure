"""Unit tests for the generation worker's persistence logic (no DB, no Redis).

These exercise ``run_generation_job`` against an in-memory fake session, so they
run in every CI leg (including the Docker-less compatibility matrix where the
testcontainers integration suite skips). They also lock in the PR-6 review
fixes: per-job storybook ids (no primary-key collision), a non-null model label
on the production path, the actual provider/model recorded, and a committed
failure record when the concept is missing.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.core.exceptions import ResourceNotFoundError
from cyo_adventure.db.models import Concept, GenerationJob, Storybook, StorybookVersion
from cyo_adventure.generation.orchestrator import GenerationOutcome
from cyo_adventure.generation.provider import _CANNED_STORY_JSON, MockProvider
from cyo_adventure.generation.worker import (
    _model_label,
    _provider_label,
    run_generation_job,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

# A valid ConceptBrief payload (mirrors the integration worker seed).
_VALID_BRIEF: dict[str, object] = {
    "premise": "A brave explorer discovers a hidden garden.",
    "protagonist": {"name": "Captain Rosa", "age": 9, "role": "young explorer"},
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
}


class _FakeResult:
    """Stand-in for a SQLAlchemy Result yielding one-tuples of child names."""

    def __init__(self, names: list[str]) -> None:
        self._names = names

    def all(self) -> list[tuple[str]]:
        """Return rows as one-tuples, matching ``select(column)`` results."""
        return [(name,) for name in self._names]


class _FakeSession:
    """Minimal async session double for the worker's call surface."""

    def __init__(
        self,
        *,
        job: GenerationJob | None,
        concept: Concept | None,
        child_names: list[str] | None = None,
    ) -> None:
        self._job = job
        self._concept = concept
        self._child_names = child_names or []
        self.added: list[object] = []
        self.commit_count = 0
        self.flush_count = 0

    async def get(self, model: type[object], key: object) -> object | None:
        """Return the seeded row for the requested model (ignores the key)."""
        _ = key
        if model is GenerationJob:
            return self._job
        if model is Concept:
            return self._concept
        return None

    async def execute(self, statement: object) -> _FakeResult:
        """Return the seeded child names as a result set."""
        _ = statement
        return _FakeResult(self._child_names)

    def add(self, obj: object) -> None:
        """Record an added ORM instance."""
        self.added.append(obj)

    async def flush(self) -> None:
        """Count flushes (no-op persistence)."""
        self.flush_count += 1

    async def commit(self) -> None:
        """Count commits (no-op persistence)."""
        self.commit_count += 1


def _factory_for(session: _FakeSession) -> Callable[[], object]:
    """Return a session_factory yielding ``session`` as an async context manager."""

    @asynccontextmanager
    async def _ctx() -> AsyncIterator[_FakeSession]:
        yield session

    def factory() -> object:
        return _ctx()

    return factory


def _job_and_concept() -> tuple[GenerationJob, Concept]:
    """Build an unsaved queued job and its concept with a valid brief."""
    concept = Concept(family_id=uuid.uuid4(), brief=_VALID_BRIEF)
    concept.created_by = uuid.uuid4()
    job = GenerationJob(concept_id=uuid.uuid4(), status="queued")
    return job, concept


def _added_of(session: _FakeSession, model: type[object]) -> list[object]:
    """Return all added instances of a given model type."""
    return [obj for obj in session.added if isinstance(obj, model)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_passing_run_persists_unique_storybook() -> None:
    """A passing run mints a per-job storybook id and matching blob id."""
    job, concept = _job_and_concept()
    session = _FakeSession(job=job, concept=concept, child_names=["TestKid"])
    job_id = uuid.uuid4()
    provider = MockProvider(responses=[_CANNED_STORY_JSON] * 8)

    await run_generation_job(
        job_id, provider=provider, session_factory=_factory_for(session)
    )

    assert job.status == "passed"
    assert job.storybook_id == f"s_{job_id}"
    assert job.version == 1
    books = _added_of(session, Storybook)
    versions = _added_of(session, StorybookVersion)
    assert len(books) == 1
    assert books[0].id == f"s_{job_id}"
    assert books[0].created_by == concept.created_by
    assert len(versions) == 1
    # The mock blob's fixed "s_mock_generated" id must be overwritten so the
    # stored blob id matches the per-job DB row id.
    assert versions[0].blob["id"] == f"s_{job_id}"
    assert versions[0].storybook_id == f"s_{job_id}"
    assert session.commit_count >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_two_passing_runs_do_not_collide() -> None:
    """Successive passing jobs produce distinct storybook ids (no PK collision)."""
    story_ids: list[str] = []
    for _ in range(2):
        job, concept = _job_and_concept()
        session = _FakeSession(job=job, concept=concept)
        job_id = uuid.uuid4()
        provider = MockProvider(responses=[_CANNED_STORY_JSON] * 8)
        await run_generation_job(
            job_id, provider=provider, session_factory=_factory_for(session)
        )
        story_ids.append(_added_of(session, Storybook)[0].id)

    assert story_ids[0] != story_ids[1]
    assert "s_mock_generated" not in story_ids


@pytest.mark.unit
@pytest.mark.asyncio
async def test_production_path_records_mock_model_not_none() -> None:
    """With provider=None (production), the mock still records model='mock'."""
    job, concept = _job_and_concept()
    session = _FakeSession(job=job, concept=concept)

    # provider=None exercises the production path: the worker builds the mock
    # from settings (generation_provider defaults to "mock").
    await run_generation_job(uuid.uuid4(), session_factory=_factory_for(session))

    assert job.status == "passed"
    assert job.model == "mock"
    assert job.provider == "mock"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_missing_job_raises_not_found() -> None:
    """A missing GenerationJob row raises ResourceNotFoundError."""
    session = _FakeSession(job=None, concept=None)
    with pytest.raises(ResourceNotFoundError):
        await run_generation_job(uuid.uuid4(), session_factory=_factory_for(session))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_missing_concept_records_failure_and_commits() -> None:
    """A missing Concept records a committed failure before raising."""
    job = GenerationJob(concept_id=uuid.uuid4(), status="queued")
    session = _FakeSession(job=job, concept=None)

    with pytest.raises(ResourceNotFoundError):
        await run_generation_job(uuid.uuid4(), session_factory=_factory_for(session))

    assert job.status == "failed"
    assert job.error is not None
    assert session.commit_count >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_needs_review_creates_no_storybook(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A needs_review outcome records the job but creates no storybook rows."""
    job, concept = _job_and_concept()
    session = _FakeSession(job=job, concept=concept)

    async def _fake_generate(*_args: object, **_kwargs: object) -> GenerationOutcome:
        return GenerationOutcome(
            status="needs_review",
            storybook=None,
            report={"ok": False},
            attempts=3,
            stage_log=["stage_a:blocked"],
        )

    monkeypatch.setattr(
        "cyo_adventure.generation.worker.generate_story", _fake_generate
    )

    await run_generation_job(
        uuid.uuid4(),
        provider=MockProvider(responses=[]),
        session_factory=_factory_for(session),
    )

    assert job.status == "needs_review"
    assert _added_of(session, Storybook) == []
    assert _added_of(session, StorybookVersion) == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pipeline_exception_records_failure_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pipeline exception is recorded as failed, committed, then re-raised."""
    job, concept = _job_and_concept()
    session = _FakeSession(job=job, concept=concept)

    async def _boom(*_args: object, **_kwargs: object) -> GenerationOutcome:
        msg = "provider exploded"
        raise RuntimeError(msg)

    monkeypatch.setattr("cyo_adventure.generation.worker.generate_story", _boom)

    with pytest.raises(RuntimeError, match="provider exploded"):
        await run_generation_job(
            uuid.uuid4(),
            provider=MockProvider(responses=[]),
            session_factory=_factory_for(session),
        )

    assert job.status == "failed"
    assert job.error == "provider exploded"
    assert job.provider == "mock"
    assert session.commit_count >= 1


@pytest.mark.unit
def test_model_label_falls_back_to_mock() -> None:
    """_model_label returns 'mock' for a provider with no model attribute."""
    assert _model_label(MockProvider(responses=[])) == "mock"


@pytest.mark.unit
def test_provider_label_falls_back_to_settings() -> None:
    """_provider_label returns the configured provider for a nameless provider."""
    assert _provider_label(MockProvider(responses=[])) == "mock"
