"""Unit tests for resume_manual_fill's pre-persist Variant A sentinel check.

Task 6b: `check_sentinel_integrity` (Variant A, the full pre-fill-vs-filled
check) runs on the cyo-author import/resume path BEFORE `import_filled_story`
(and thus before its `persist_storybook` call), not only inside
`_finalize_resume` afterward. A dropped sentinel is invisible to both the
Task 6a at-rest backstop (Variant B, blob-only) and a human reviewer, so only
this full check, run pre-persist, closes the gap. These tests use a legacy
(unparameterized) skeleton -- `load_contract_for` returns `None`, so the
Stage 1 reference is the raw pre-fill skeleton unchanged, exactly like
`test_legacy_skeleton_resume_reference_is_unchanged` in the sibling Stage 1
test module -- so no `ThemeContract` fixture is needed to exercise the
pre-persist check itself.
"""

from __future__ import annotations

import uuid

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import Concept, GenerationJob
from cyo_adventure.generation import import_story
from cyo_adventure.storybook.sentinels import wrap

pytestmark = pytest.mark.asyncio

_HERO = wrap("HERO", "Explorer")


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


def _job(concept_id: uuid.UUID) -> GenerationJob:
    return GenerationJob(
        id=uuid.uuid4(),
        concept_id=concept_id,
        status="awaiting_manual_fill",
        authoring_metadata={"skeleton_slug": "x", "theme_brief": {}},
    )


def _wire_legacy(
    monkeypatch: pytest.MonkeyPatch, original_skeleton: dict[str, object]
) -> None:
    """Patch load_skeleton/load_contract_for for the legacy (no-contract) path.

    ``load_contract_for`` returning ``None`` means ``_stage1_reference_skeleton``
    hands back ``original_skeleton`` unchanged (mirroring
    ``test_legacy_skeleton_resume_reference_is_unchanged``): this is the
    simplest fixture that lets the pre-persist sentinel check run without a
    full WS-2 ``ThemeContract``.
    """
    monkeypatch.setattr(import_story, "load_skeleton", lambda _path: original_skeleton)
    monkeypatch.setattr(
        import_story, "load_contract_for", lambda _path, _skeleton: None
    )


async def test_resume_dropped_sentinel_rejected_pre_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fill that drops a declared sentinel is rejected before persist.

    import_filled_story (and thus persist_storybook) must never be called;
    the job is marked failed with the violations recorded, and the raised
    ValidationError carries them under sentinel_integrity_violations.
    """
    concept = Concept(id=uuid.uuid4(), family_id=uuid.uuid4(), brief={})
    job = _job(concept.id)
    session = _FakeSession(job=job, concept=concept)

    original_skeleton: dict[str, object] = {
        "nodes": [
            {
                "id": "n_a",
                "body": f"<<FILL beats='{_HERO} walks.'>>",
                "choices": [],
                "ending": {"id": "e_a", "title": "Fixed"},
            }
        ]
    }
    _wire_legacy(monkeypatch, original_skeleton)

    import_called = False

    async def _fake_import_filled_story(
        _session: object, _request: object, **_kwargs: object
    ) -> str:
        nonlocal import_called
        import_called = True
        return "s_x"

    monkeypatch.setattr(import_story, "import_filled_story", _fake_import_filled_story)

    dropped_blob = {
        "id": "s_x",
        "nodes": [
            {
                "id": "n_a",
                "body": "The hero walked generically.",
                "choices": [],
                "ending": {"id": "e_a", "title": "Fixed"},
            }
        ],
    }

    with pytest.raises(ValidationError) as exc_info:
        await import_story.resume_manual_fill(session, job.id, dropped_blob)

    assert not import_called, "a dropped sentinel must never reach persist_storybook"
    assert exc_info.value.details["field"] == "sentinel_integrity"
    violations = exc_info.value.details["sentinel_integrity_violations"]
    assert violations
    assert any(v["kind"] == "dropped" for v in violations)
    assert job.status == "failed"
    assert job.error is not None
    assert session.commits == 1


async def test_resume_forged_sentinel_rejected_pre_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fill that forges an undeclared sentinel is also rejected before persist."""
    concept = Concept(id=uuid.uuid4(), family_id=uuid.uuid4(), brief={})
    job = _job(concept.id)
    session = _FakeSession(job=job, concept=concept)

    original_skeleton: dict[str, object] = {
        "nodes": [
            {
                "id": "n_a",
                "body": "<<FILL beats='The hero walks.'>>",
                "choices": [],
                "ending": {"id": "e_a", "title": "Fixed"},
            }
        ]
    }
    _wire_legacy(monkeypatch, original_skeleton)

    import_called = False

    async def _fake_import_filled_story(
        _session: object, _request: object, **_kwargs: object
    ) -> str:
        nonlocal import_called
        import_called = True
        return "s_x"

    monkeypatch.setattr(import_story, "import_filled_story", _fake_import_filled_story)

    forged_blob = {
        "id": "s_x",
        "nodes": [
            {
                "id": "n_a",
                "body": f"{_HERO} walked generically.",
                "choices": [],
                "ending": {"id": "e_a", "title": "Fixed"},
            }
        ],
    }

    with pytest.raises(ValidationError) as exc_info:
        await import_story.resume_manual_fill(session, job.id, forged_blob)

    assert not import_called, "a forged sentinel must never reach persist_storybook"
    violations = exc_info.value.details["sentinel_integrity_violations"]
    assert any(v["kind"] == "forged" for v in violations)
    assert job.status == "failed"


async def test_resume_clean_sentinel_free_import_persists_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dormancy: a sentinel-free fill is unaffected and still persists/passes."""
    concept = Concept(id=uuid.uuid4(), family_id=uuid.uuid4(), brief={})
    job = _job(concept.id)
    session = _FakeSession(job=job, concept=concept)

    original_skeleton: dict[str, object] = {
        "nodes": [
            {
                "id": "n_a",
                "body": "<<FILL beats='The hero walks.'>>",
                "choices": [],
                "ending": {"id": "e_a", "title": "Fixed"},
            }
        ]
    }
    _wire_legacy(monkeypatch, original_skeleton)

    async def _fake_import_filled_story(_session, _request, **_kwargs: object):
        return "s_x"

    async def _fake_run_stage1_gate(*_args, **_kwargs):
        return []

    monkeypatch.setattr(import_story, "import_filled_story", _fake_import_filled_story)
    monkeypatch.setattr(import_story, "run_stage1_gate", _fake_run_stage1_gate)

    clean_blob = {
        "id": "s_x",
        "nodes": [
            {
                "id": "n_a",
                "body": "The hero walked bravely.",
                "choices": [],
                "ending": {"id": "e_a", "title": "Fixed"},
            }
        ],
    }

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, clean_blob
    )

    assert story_id == "s_x"
    assert status == "passed"
    assert job.status == "passed"


async def test_resume_sentinel_check_skipped_when_no_skeleton_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dormancy: a job with no skeleton_slug never reaches the pre-persist check.

    Regression pin for the existing skeleton-slug-less resume path (a
    standalone import with no skill provenance): check_sentinel_integrity
    must not even be imported/called when there is no reference to check
    against.
    """
    concept = Concept(id=uuid.uuid4(), family_id=uuid.uuid4(), brief={})
    job = GenerationJob(
        id=uuid.uuid4(),
        concept_id=concept.id,
        status="awaiting_manual_fill",
        authoring_metadata={},
    )
    session = _FakeSession(job=job, concept=concept)

    async def _fake_import_filled_story(_session, _request, **_kwargs: object):
        return "s_x"

    checked = False
    real_check = import_story.check_sentinel_integrity

    def _spy_check(*args, **kwargs):
        nonlocal checked
        checked = True
        return real_check(*args, **kwargs)

    monkeypatch.setattr(import_story, "import_filled_story", _fake_import_filled_story)
    monkeypatch.setattr(import_story, "check_sentinel_integrity", _spy_check)

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, {"id": "s_x", "nodes": []}
    )

    assert story_id == "s_x"
    assert status == "passed"
    assert not checked, "no skeleton_slug means no reference to check against"
