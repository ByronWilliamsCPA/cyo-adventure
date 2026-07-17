"""Unit tests for the generation API handlers (no DB, no Redis, no ASGI stack).

These call the route functions directly with a fake session and a constructed
principal, so they run in the Docker-less compatibility matrix where the
testcontainers integration suite skips. They lock in the PR-6 review fixes:
creator provenance on a concept, a malformed UUID path param mapping to a 422
``ValidationError`` (not a 500), and the best-effort enqueue being scheduled as
a background task (after the commit, off the event loop).
"""

from __future__ import annotations

import logging
import uuid

import pytest
from fastapi import BackgroundTasks
from rq.exceptions import DuplicateJobError

from cyo_adventure.api.deps import Principal, RequestContext
from cyo_adventure.api.generation import (
    MAX_ACTIVE_JOBS_PER_FAMILY,
    _enqueue_safely,
    create_concept,
    enqueue_concept_generation,
    force_fail_generation_job,
    get_generation_job,
    validate_storybook_version,
)
from cyo_adventure.api.schemas import ConceptCreateRequest
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
from cyo_adventure.db.models import (
    Concept,
    GenerationJob,
    Storybook,
    StorybookVersion,
)
from cyo_adventure.generation.concept import ConceptBrief
from cyo_adventure.generation.provider import _CANNED_STORY

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


class _FakeScalars:
    """Stand-in for the iterable returned by ``session.scalars``."""

    def __init__(self, values: list[str]) -> None:
        self._values = values

    def all(self) -> list[str]:
        """Return the seeded scalar values."""
        return self._values


class _FakeSession:
    """Minimal async session double for the generation API handlers."""

    def __init__(
        self,
        *,
        get_result: object | None = None,
        results: dict[type[object], object] | None = None,
        child_names: list[str] | None = None,
        scalar_result: int = 0,
    ) -> None:
        self._get_result = get_result
        self._results = results or {}
        self._child_names = child_names or []
        self._scalar_result = scalar_result
        self.added: list[object] = []
        self.flush_count = 0

    async def scalars(self, statement: object) -> _FakeScalars:
        """Return the seeded child display names."""
        _ = statement
        return _FakeScalars(self._child_names)

    async def scalar(self, statement: object) -> int:
        """Return the seeded scalar count (used by the per-family job throttle)."""
        _ = statement
        return self._scalar_result

    async def get(self, model: type[object], key: object) -> object | None:
        """Return the per-model seeded row, falling back to a single result."""
        _ = key
        if model in self._results:
            return self._results[model]
        return self._get_result

    def add(self, obj: object) -> None:
        """Record an added ORM instance."""
        self.added.append(obj)

    async def flush(self) -> None:
        """Count flushes (no-op persistence)."""
        self.flush_count += 1


def _principal(role: str, family_id: uuid.UUID, user_id: uuid.UUID) -> Principal:
    """Build a Principal for the given role and family."""
    return Principal(
        subject="sub",
        user_id=user_id,
        role=role,
        family_id=family_id,
        profile_ids=frozenset(),
    )


def _request() -> ConceptCreateRequest:
    """Build a valid ConceptCreateRequest."""
    return ConceptCreateRequest(brief=ConceptBrief.model_validate(_VALID_BRIEF))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_concept_stamps_created_by() -> None:
    """A guardian-created concept carries the principal's user id as created_by."""
    family_id = uuid.uuid4()
    user_id = uuid.uuid4()
    session = _FakeSession(child_names=[])
    ctx = RequestContext(
        principal=_principal("guardian", family_id, user_id), session=session
    )

    resp = await create_concept(_request(), ctx)

    assert resp is not None
    concepts = [obj for obj in session.added if isinstance(obj, Concept)]
    assert len(concepts) == 1
    assert concepts[0].created_by == user_id
    assert concepts[0].family_id == family_id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_concept_child_token_forbidden() -> None:
    """A child principal cannot create a concept (-> 403)."""
    session = _FakeSession()
    ctx = RequestContext(
        principal=_principal("child", uuid.uuid4(), uuid.uuid4()), session=session
    )
    with pytest.raises(AuthorizationError):
        await create_concept(_request(), ctx)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_concept_pii_in_brief_rejected() -> None:
    """A brief embedding a real child's name is rejected (-> 422)."""
    session = _FakeSession(child_names=["Captain Rosa"])
    ctx = RequestContext(
        principal=_principal("guardian", uuid.uuid4(), uuid.uuid4()), session=session
    )
    with pytest.raises(ValidationError):
        await create_concept(_request(), ctx)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enqueue_schedules_background_task() -> None:
    """Enqueue returns 202 data and schedules the enqueue as a background task."""
    family_id = uuid.uuid4()
    concept = Concept(family_id=family_id, brief=_VALID_BRIEF)
    session = _FakeSession(get_result=concept)
    ctx = RequestContext(
        principal=_principal("guardian", family_id, uuid.uuid4()), session=session
    )
    background = BackgroundTasks()

    resp = await enqueue_concept_generation(str(uuid.uuid4()), ctx, background)

    assert resp.status == "queued"
    assert any(isinstance(obj, GenerationJob) for obj in session.added)
    # The enqueue runs as a background task (after commit, off the event loop).
    assert len(background.tasks) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enqueue_cross_family_forbidden() -> None:
    """A guardian cannot enqueue generation for another family's concept (-> 403)."""
    concept = Concept(family_id=uuid.uuid4(), brief=_VALID_BRIEF)
    session = _FakeSession(get_result=concept)
    ctx = RequestContext(
        principal=_principal("guardian", uuid.uuid4(), uuid.uuid4()), session=session
    )
    with pytest.raises(AuthorizationError):
        await enqueue_concept_generation(str(uuid.uuid4()), ctx, BackgroundTasks())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enqueue_family_at_cap_rejected() -> None:
    """A family already at the active-job cap is refused with 409 (audit F9)."""
    family_id = uuid.uuid4()
    concept = Concept(family_id=family_id, brief=_VALID_BRIEF)
    session = _FakeSession(get_result=concept, scalar_result=MAX_ACTIVE_JOBS_PER_FAMILY)
    ctx = RequestContext(
        principal=_principal("guardian", family_id, uuid.uuid4()), session=session
    )

    with pytest.raises(StateTransitionError):
        await enqueue_concept_generation(str(uuid.uuid4()), ctx, BackgroundTasks())
    assert not any(isinstance(obj, GenerationJob) for obj in session.added)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enqueue_family_under_cap_allowed() -> None:
    """A family under the active-job cap may still enqueue (audit F9)."""
    family_id = uuid.uuid4()
    concept = Concept(family_id=family_id, brief=_VALID_BRIEF)
    session = _FakeSession(
        get_result=concept, scalar_result=MAX_ACTIVE_JOBS_PER_FAMILY - 1
    )
    ctx = RequestContext(
        principal=_principal("guardian", family_id, uuid.uuid4()), session=session
    )

    resp = await enqueue_concept_generation(str(uuid.uuid4()), ctx, BackgroundTasks())

    assert resp.status == "queued"
    assert any(isinstance(obj, GenerationJob) for obj in session.added)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enqueue_missing_concept_not_found() -> None:
    """Enqueue against a missing concept raises ResourceNotFoundError (-> 404)."""
    session = _FakeSession(get_result=None)
    ctx = RequestContext(
        principal=_principal("guardian", uuid.uuid4(), uuid.uuid4()), session=session
    )
    with pytest.raises(ResourceNotFoundError):
        await enqueue_concept_generation(str(uuid.uuid4()), ctx, BackgroundTasks())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enqueue_bad_uuid_is_validation_error() -> None:
    """A non-UUID concept_id maps to a 422 ValidationError, not a 500."""
    session = _FakeSession()
    ctx = RequestContext(
        principal=_principal("guardian", uuid.uuid4(), uuid.uuid4()), session=session
    )
    with pytest.raises(ValidationError):
        await enqueue_concept_generation("not-a-uuid", ctx, BackgroundTasks())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_generation_job_bad_uuid_is_validation_error() -> None:
    """A non-UUID job_id maps to a 422 ValidationError, not a 500."""
    session = _FakeSession()
    ctx = RequestContext(
        principal=_principal("guardian", uuid.uuid4(), uuid.uuid4()), session=session
    )
    with pytest.raises(ValidationError):
        await get_generation_job("not-a-uuid", ctx)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_generation_job_child_token_forbidden() -> None:
    """A child principal cannot read a generation job (-> 403)."""
    session = _FakeSession()
    ctx = RequestContext(
        principal=_principal("child", uuid.uuid4(), uuid.uuid4()), session=session
    )
    with pytest.raises(AuthorizationError):
        await get_generation_job(str(uuid.uuid4()), ctx)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_generation_job_returns_status() -> None:
    """A guardian reads their own family's job and gets its status payload."""
    family_id = uuid.uuid4()
    concept = Concept(family_id=family_id, brief=_VALID_BRIEF)
    job = GenerationJob(concept_id=uuid.uuid4(), status="passed")
    job.storybook_id = "s_abc"
    job.version = 1
    session = _FakeSession(results={GenerationJob: job, Concept: concept})
    ctx = RequestContext(
        principal=_principal("guardian", family_id, uuid.uuid4()), session=session
    )

    resp = await get_generation_job(str(uuid.uuid4()), ctx)

    assert resp.status == "passed"
    assert resp.storybook_id == "s_abc"
    assert resp.version == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_generation_job_missing_job_not_found() -> None:
    """A job id with no matching row raises ResourceNotFoundError (-> 404)."""
    session = _FakeSession(results={GenerationJob: None})
    ctx = RequestContext(
        principal=_principal("guardian", uuid.uuid4(), uuid.uuid4()), session=session
    )

    with pytest.raises(ResourceNotFoundError, match="not found"):
        await get_generation_job(str(uuid.uuid4()), ctx)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_generation_job_missing_concept_not_found() -> None:
    """A job whose concept row is gone raises ResourceNotFoundError (-> 404).

    This is the IDOR-guard load order: the job resolves, but the concept it
    points to (used for the family-ownership check) does not.
    """
    job = GenerationJob(concept_id=uuid.uuid4(), status="queued")
    session = _FakeSession(results={GenerationJob: job, Concept: None})
    ctx = RequestContext(
        principal=_principal("guardian", uuid.uuid4(), uuid.uuid4()), session=session
    )

    with pytest.raises(ResourceNotFoundError, match="not found"):
        await get_generation_job(str(uuid.uuid4()), ctx)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_storybook_version_runs_gate() -> None:
    """The validate endpoint re-runs the gate on the stored blob for its family."""
    family_id = uuid.uuid4()
    book = Storybook(id="s_mock_generated", family_id=family_id, status="draft")
    version = StorybookVersion(
        storybook_id="s_mock_generated", version=1, blob=dict(_CANNED_STORY)
    )
    session = _FakeSession(results={Storybook: book, StorybookVersion: version})
    ctx = RequestContext(
        principal=_principal("guardian", family_id, uuid.uuid4()), session=session
    )

    resp = await validate_storybook_version("s_mock_generated", 1, ctx)

    assert resp.blocked is False
    assert isinstance(resp.report, dict)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_storybook_cross_family_forbidden() -> None:
    """A guardian cannot validate another family's storybook (-> 403)."""
    book = Storybook(id="s_x", family_id=uuid.uuid4(), status="draft")
    session = _FakeSession(results={Storybook: book})
    ctx = RequestContext(
        principal=_principal("guardian", uuid.uuid4(), uuid.uuid4()), session=session
    )
    with pytest.raises(AuthorizationError):
        await validate_storybook_version("s_x", 1, ctx)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_storybook_not_found() -> None:
    """Validating a missing storybook raises ResourceNotFoundError (-> 404)."""
    session = _FakeSession(results={Storybook: None})
    ctx = RequestContext(
        principal=_principal("guardian", uuid.uuid4(), uuid.uuid4()), session=session
    )
    with pytest.raises(ResourceNotFoundError):
        await validate_storybook_version("missing", 1, ctx)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_storybook_version_missing() -> None:
    """A missing version of an existing storybook raises ResourceNotFoundError."""
    family_id = uuid.uuid4()
    book = Storybook(id="s_y", family_id=family_id, status="draft")
    session = _FakeSession(results={Storybook: book, StorybookVersion: None})
    ctx = RequestContext(
        principal=_principal("guardian", family_id, uuid.uuid4()), session=session
    )
    with pytest.raises(ResourceNotFoundError):
        await validate_storybook_version("s_y", 99, ctx)


@pytest.mark.unit
def test_enqueue_safely_swallows_redis_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_enqueue_safely logs and swallows a failing enqueue (best-effort)."""

    def _boom(_job_id: str, _settings: object, *, rq_job_id: str | None = None) -> str:
        msg = "redis down"
        raise ConnectionError(msg)

    monkeypatch.setattr("cyo_adventure.api.generation.enqueue_generation", _boom)
    job_id = str(uuid.uuid4())

    with caplog.at_level(logging.ERROR, logger="cyo_adventure.api.generation"):
        result = _enqueue_safely(job_id)

    # _enqueue_safely's documented contract is None (best-effort, never raises);
    # the failure must still be observable via the logged exception.
    assert result is None
    assert any(
        job_id in record.getMessage()
        and "enqueue_generation failed" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.unit
def test_enqueue_safely_uses_row_id_as_rq_job_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_enqueue_safely passes rq_job_id=job_id so the sweep shares one identity.

    The original enqueue must reuse the row id as the RQ job id; otherwise the
    reclaim sweep's rq_job_id=row_id re-enqueue cannot dedupe against a
    still-queued original and the job runs twice.
    """
    seen: list[tuple[str, str | None]] = []

    def _ok(job_id: str, _settings: object, *, rq_job_id: str | None = None) -> str:
        seen.append((job_id, rq_job_id))
        return "rq-1"

    monkeypatch.setattr("cyo_adventure.api.generation.enqueue_generation", _ok)
    job_id = str(uuid.uuid4())
    _enqueue_safely(job_id)
    assert seen == [(job_id, job_id)]


@pytest.mark.unit
def test_enqueue_safely_swallows_duplicate_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A DuplicateJobError (row already queued under its id) is a no-op."""

    def _dupe(_job_id: str, _settings: object, *, rq_job_id: str | None = None) -> str:
        raise DuplicateJobError

    monkeypatch.setattr("cyo_adventure.api.generation.enqueue_generation", _dupe)
    # Must not raise.
    assert _enqueue_safely(str(uuid.uuid4())) is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_force_fail_requires_admin() -> None:
    """A guardian (non-admin) principal cannot force-fail a job (-> 403)."""
    session = _FakeSession()
    ctx = RequestContext(
        principal=_principal("guardian", uuid.uuid4(), uuid.uuid4()), session=session
    )
    with pytest.raises(AuthorizationError):
        await force_fail_generation_job(str(uuid.uuid4()), ctx)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_force_fail_missing_job_not_found() -> None:
    """Force-failing a nonexistent job raises ResourceNotFoundError (-> 404)."""
    session = _FakeSession(get_result=None)
    ctx = RequestContext(
        principal=_principal("admin", uuid.uuid4(), uuid.uuid4()), session=session
    )
    with pytest.raises(ResourceNotFoundError):
        await force_fail_generation_job(str(uuid.uuid4()), ctx)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_force_fail_rejects_terminal_job() -> None:
    """A job already terminal ('passed') cannot be force-failed (-> 409)."""
    job = GenerationJob(concept_id=uuid.uuid4(), status="passed")
    job.id = uuid.uuid4()
    session = _FakeSession(get_result=job)
    ctx = RequestContext(
        principal=_principal("admin", uuid.uuid4(), uuid.uuid4()), session=session
    )
    with pytest.raises(StateTransitionError):
        await force_fail_generation_job(str(job.id), ctx)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_force_fail_running_job_sets_failed_and_records_event() -> None:
    """A stuck 'running' job is force-failed and a finished event is recorded."""
    from cyo_adventure.db.models import PipelineEvent

    job = GenerationJob(concept_id=uuid.uuid4(), status="running")
    job.id = uuid.uuid4()
    session = _FakeSession(get_result=job)
    ctx = RequestContext(
        principal=_principal("admin", uuid.uuid4(), uuid.uuid4()), session=session
    )

    resp = await force_fail_generation_job(str(job.id), ctx)

    assert resp.status == "failed"
    assert resp.error == "interrupted: force-failed by admin"
    assert job.status == "failed"
    events = [obj for obj in session.added if isinstance(obj, PipelineEvent)]
    assert len(events) == 1
    assert events[0].to_state == "failed"
    assert events[0].from_state == "running"
