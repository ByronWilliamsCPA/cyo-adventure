"""Unit test for resume_manual_fill's Stage 1 violation recording."""

from __future__ import annotations

import uuid

import pytest

from cyo_adventure.core.exceptions import ResourceNotFoundError, ValidationError
from cyo_adventure.db.models import Concept, GenerationJob
from cyo_adventure.generation import import_story
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.theme_contract import SlotScope, SlotSpec, ThemeContract

pytestmark = pytest.mark.asyncio

# A minimal, schema-valid WS-2 theme contract shared by the parameterized-
# skeleton tests below: one GLOBAL slot, HERO, with a default_binding that
# satisfies ThemeContract's own cross-field invariant (its keys must exactly
# match the declared slot ids).
_CONTRACT = ThemeContract(
    contract_version=1,
    skeleton_slug="x",
    age_band=AgeBand.BAND_8_11,
    default_binding={"HERO": "the fox"},
    slots=[SlotSpec(id="HERO", scope=SlotScope.GLOBAL, meaning="the hero's species")],
)


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

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, {"id": "s_x", "nodes": []}
    )

    assert story_id == "s_x"
    assert status == "needs_review"
    assert job.status == "needs_review"
    assert job.error is not None
    assert "word count" in job.error
    # Item 2: a Stage 1 violation must not orphan the job row from the story
    # import_filled_story already persisted moments earlier.
    assert job.storybook_id == "s_x"
    assert job.version == import_story._FIRST_VERSION


async def test_missing_skeleton_downgrades_instead_of_stranding_job(
    monkeypatch,
) -> None:
    """A skeleton that cannot be loaded degrades to needs_review, not a stuck job.

    Closes #128: the matched skeleton library file may be moved, renamed, or
    removed at any point in the job's lifetime, including before this call
    even starts. run_stage1_gate must not even be attempted in that case (no
    original document to compare against); the job still completes instead of
    being left at "awaiting_manual_fill" with a real, already-persisted story
    orphaned from it.
    """
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

    def _raise_missing(_path):
        raise ResourceNotFoundError(
            "skeleton file not found", resource_type="Skeleton", resource_id="x"
        )

    stage1_called = False

    async def _fake_run_stage1_gate(*args, **kwargs):
        nonlocal stage1_called
        stage1_called = True
        return []

    monkeypatch.setattr(import_story, "import_filled_story", _fake_import_filled_story)
    monkeypatch.setattr(import_story, "run_stage1_gate", _fake_run_stage1_gate)
    monkeypatch.setattr(import_story, "load_skeleton", _raise_missing)

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, {"id": "s_x", "nodes": []}
    )

    assert story_id == "s_x"
    assert status == "needs_review"
    assert job.status == "needs_review"
    assert job.error is not None
    assert job.storybook_id == "s_x"
    assert job.version == import_story._FIRST_VERSION
    assert not stage1_called, "run_stage1_gate must not be called with no original doc"


async def test_review_model_overrides_are_threaded_through_resume(
    monkeypatch,
) -> None:
    """Both review_stage1_model and review_stage2_model reach their callees.

    Item 1: the automated_provider mechanism (generation/worker.py) already
    read both overrides out of authoring_metadata; resume_manual_fill (the
    skill mechanism) used to hardcode review_stage1_model=None and had no way
    to pass review_stage2_model at all.
    """
    concept = Concept(id=uuid.uuid4(), family_id=uuid.uuid4(), brief={})
    job = GenerationJob(
        id=uuid.uuid4(),
        concept_id=concept.id,
        status="awaiting_manual_fill",
        authoring_metadata={
            "skeleton_slug": "x",
            "theme_brief": {},
            "review_stage1_model": "stage1-override-model",
            "review_stage2_model": "stage2-override-model",
        },
    )
    session = _FakeSession(job=job, concept=concept)

    captured_request = {}

    async def _fake_import_filled_story(_session, request):
        captured_request["review_model_override"] = request.review_model_override
        return "s_x"

    captured_stage1_kwargs = {}

    async def _fake_run_stage1_gate(*args, **kwargs):
        captured_stage1_kwargs.update(kwargs)
        return []

    monkeypatch.setattr(import_story, "import_filled_story", _fake_import_filled_story)
    monkeypatch.setattr(import_story, "run_stage1_gate", _fake_run_stage1_gate)
    monkeypatch.setattr(import_story, "load_skeleton", lambda _path: {"nodes": []})

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, {"id": "s_x", "nodes": []}
    )

    assert story_id == "s_x"
    assert status == "passed"
    assert job.status == "passed"
    assert captured_request["review_model_override"] == "stage2-override-model"
    assert captured_stage1_kwargs["review_stage1_model"] == "stage1-override-model"


def _parameterized_job(
    concept_id: uuid.UUID, *, slot_bindings: dict[str, str] | None = None
) -> GenerationJob:
    """Return a parked job whose authoring_metadata matches a WS-2 skeleton_slug."""
    authoring_metadata: dict[str, object] = {"skeleton_slug": "x", "theme_brief": {}}
    if slot_bindings is not None:
        authoring_metadata["slot_bindings"] = slot_bindings
    return GenerationJob(
        id=uuid.uuid4(),
        concept_id=concept_id,
        status="awaiting_manual_fill",
        authoring_metadata=authoring_metadata,
    )


def _wire_common(monkeypatch) -> None:
    """Patch the two calls resume_manual_fill makes outside Stage 1 itself."""

    async def _fake_import_filled_story(_session, _request):
        return "s_x"

    monkeypatch.setattr(import_story, "import_filled_story", _fake_import_filled_story)
    monkeypatch.setattr(
        import_story, "load_skeleton", lambda _path: {"nodes": [], "raw": True}
    )


async def test_parameterized_skeleton_uses_bound_skeleton_as_stage1_reference(
    monkeypatch,
) -> None:
    """A contract-bearing skeleton's Stage 1 reference is the BOUND skeleton.

    The raw skeleton loaded from disk still carries {SLOT} tokens (WS-2
    design section 5.1); resume_manual_fill must hand run_stage1_gate the
    output of render_bound_skeleton, not the raw document, or every
    parameterized skill fill would be compared against literal placeholder
    text and false-flagged.
    """
    concept = Concept(id=uuid.uuid4(), family_id=uuid.uuid4(), brief={})
    job = _parameterized_job(concept.id)
    session = _FakeSession(job=job, concept=concept)
    _wire_common(monkeypatch)

    bound_skeleton = {"nodes": [], "bound": True}
    render_calls: list[tuple[object, object]] = []

    def _fake_load_contract_for(_path, _skeleton):
        return _CONTRACT

    def _fake_render_bound_skeleton(skeleton, bindings):
        render_calls.append((skeleton, bindings))
        return bound_skeleton

    captured_reference: dict[str, object] = {}

    async def _fake_run_stage1_gate(original, _filled, **_kwargs):
        captured_reference["original"] = original
        return []

    monkeypatch.setattr(import_story, "load_contract_for", _fake_load_contract_for)
    monkeypatch.setattr(
        import_story, "render_bound_skeleton", _fake_render_bound_skeleton
    )
    monkeypatch.setattr(import_story, "run_stage1_gate", _fake_run_stage1_gate)

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, {"id": "s_x", "nodes": []}
    )

    assert story_id == "s_x"
    assert status == "passed"
    assert captured_reference["original"] is bound_skeleton
    # No slot_bindings were recorded on the job, so the contract's
    # default_binding (the classic-story reference) must have been used.
    assert render_calls == [({"nodes": [], "raw": True}, _CONTRACT.default_binding)]


async def test_recorded_slot_bindings_are_preferred_over_default_binding(
    monkeypatch,
) -> None:
    """A job's recorded slot_bindings win over the contract's default_binding."""
    recorded = {"HERO": "the wolf"}
    concept = Concept(id=uuid.uuid4(), family_id=uuid.uuid4(), brief={})
    job = _parameterized_job(concept.id, slot_bindings=recorded)
    session = _FakeSession(job=job, concept=concept)
    _wire_common(monkeypatch)

    render_calls: list[tuple[object, object]] = []

    def _fake_render_bound_skeleton(skeleton, bindings):
        render_calls.append((skeleton, bindings))
        return {"nodes": [], "bound": True}

    async def _fake_run_stage1_gate(*_args, **_kwargs):
        return []

    monkeypatch.setattr(
        import_story, "load_contract_for", lambda _path, _skeleton: _CONTRACT
    )
    monkeypatch.setattr(
        import_story, "render_bound_skeleton", _fake_render_bound_skeleton
    )
    monkeypatch.setattr(import_story, "run_stage1_gate", _fake_run_stage1_gate)

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, {"id": "s_x", "nodes": []}
    )

    assert story_id == "s_x"
    assert status == "passed"
    assert render_calls == [({"nodes": [], "raw": True}, recorded)]


async def test_legacy_skeleton_resume_reference_is_unchanged(monkeypatch) -> None:
    """A skeleton with no contract sidecar is unaffected (regression pin).

    load_contract_for returning None must leave the Stage 1 reference as the
    raw skeleton exactly as before WS-2, and render_bound_skeleton must never
    be called for it.
    """
    concept = Concept(id=uuid.uuid4(), family_id=uuid.uuid4(), brief={})
    job = _parameterized_job(concept.id)
    session = _FakeSession(job=job, concept=concept)
    _wire_common(monkeypatch)

    render_called = False

    def _fake_render_bound_skeleton(skeleton, bindings):
        nonlocal render_called
        render_called = True
        return skeleton

    captured_reference: dict[str, object] = {}

    async def _fake_run_stage1_gate(original, _filled, **_kwargs):
        captured_reference["original"] = original
        return []

    monkeypatch.setattr(
        import_story, "load_contract_for", lambda _path, _skeleton: None
    )
    monkeypatch.setattr(
        import_story, "render_bound_skeleton", _fake_render_bound_skeleton
    )
    monkeypatch.setattr(import_story, "run_stage1_gate", _fake_run_stage1_gate)

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, {"id": "s_x", "nodes": []}
    )

    assert story_id == "s_x"
    assert status == "passed"
    assert captured_reference["original"] == {"nodes": [], "raw": True}
    assert not render_called, "a legacy skeleton must never reach render_bound_skeleton"


async def test_contract_render_error_degrades_to_needs_review(monkeypatch) -> None:
    """A render/contract failure downgrades to needs_review, never a crash.

    Simulates a stale recorded slot_bindings that no longer validates
    against the contract: render_bound_skeleton's post-conditions raise
    ValidationError. resume_manual_fill must not let that exception
    propagate and roll back the already-persisted, already-moderated story;
    it must degrade exactly like the missing-skeleton-file branch does.
    """
    concept = Concept(id=uuid.uuid4(), family_id=uuid.uuid4(), brief={})
    job = _parameterized_job(concept.id, slot_bindings={"HERO": "stale value"})
    session = _FakeSession(job=job, concept=concept)
    _wire_common(monkeypatch)

    stage1_called = False

    async def _fake_run_stage1_gate(*_args, **_kwargs):
        nonlocal stage1_called
        stage1_called = True
        return []

    def _raise_render_error(_skeleton, _bindings):
        msg = "stale binding no longer satisfies its slot constraints"
        raise ValidationError(msg)

    monkeypatch.setattr(
        import_story, "load_contract_for", lambda _path, _skeleton: _CONTRACT
    )
    monkeypatch.setattr(import_story, "render_bound_skeleton", _raise_render_error)
    monkeypatch.setattr(import_story, "run_stage1_gate", _fake_run_stage1_gate)

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, {"id": "s_x", "nodes": []}
    )

    assert story_id == "s_x"
    assert status == "needs_review"
    assert job.status == "needs_review"
    assert job.error is not None
    assert "stale binding" in job.error
    # Item 2 (mirrored from the Stage 1 violation test above): storybook_id/
    # version must still be linked, never orphaned, even on this degrade path.
    assert job.storybook_id == "s_x"
    assert job.version == import_story._FIRST_VERSION
    assert not stage1_called, "run_stage1_gate must not run with no valid reference"


async def test_contract_load_error_degrades_to_needs_review(monkeypatch) -> None:
    """A load_contract_for failure (e.g. slot-token drift) also degrades cleanly.

    Covers the other half of _stage1_reference_skeleton's try/except: the
    contract cross-check itself (not just the render step) can raise
    ValidationError, and must be caught the same way.
    """
    concept = Concept(id=uuid.uuid4(), family_id=uuid.uuid4(), brief={})
    job = _parameterized_job(concept.id)
    session = _FakeSession(job=job, concept=concept)
    _wire_common(monkeypatch)

    def _raise_contract_error(_path, _skeleton):
        msg = "theme contract slot id set does not match the skeleton's tokens"
        raise ValidationError(msg)

    monkeypatch.setattr(import_story, "load_contract_for", _raise_contract_error)

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, {"id": "s_x", "nodes": []}
    )

    assert story_id == "s_x"
    assert status == "needs_review"
    assert job.error is not None
    assert "does not match" in job.error
