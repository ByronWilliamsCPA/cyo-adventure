"""Unit tests for resume_manual_fill's pre-persist sentinel re-insertion (ADR-023 Stage R).

Originally Task 6b: `check_sentinel_integrity` (Variant A, the full
pre-fill-vs-filled prescriptive check) ran on the cyo-author import/resume
path BEFORE `import_filled_story` (and thus before its `persist_storybook`
call), not only inside `_finalize_resume` afterward. As of Task R3, that
prescriptive check no longer trusts the fill to have preserved a sentinel
wrapper verbatim (G1 measurement: only 3.3% survival); this module derives
the persisted blob from `reference_skeleton` via the deterministic
strip-all-then-reinsert transform (`reinsert_storybook`), verifies the
transform's own output against its own manifest, and re-scans for anything
sentinel-shaped left at rest, all before `import_filled_story` runs. These
tests use a legacy (unparameterized) skeleton -- `load_contract_for` returns
`None`, so the Stage 1 reference is the raw pre-fill skeleton unchanged,
exactly like `test_legacy_skeleton_resume_reference_is_unchanged` in the
sibling Stage 1 test module -- so no `ThemeContract` fixture is needed to
exercise the pre-persist step itself.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import Concept, GenerationJob
from cyo_adventure.generation import import_story
from cyo_adventure.storybook.sentinels import wrap

if TYPE_CHECKING:
    from cyo_adventure.generation.import_story import ImportRequest

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
    simplest fixture that lets the pre-persist reinsertion step run without a
    full WS-2 ``ThemeContract``. Note this does NOT wire up
    ``moderation.personalizable_slots``'s own skeleton loading (a separate
    module-level import), so `personalizable_slots` resolves
    `PERSONALIZABLE_SLOTS_UNRECOVERABLE` for every
    test in this file: the at-rest re-scan is gated on it being a real
    `frozenset` (Task 6c, M1) and is exercised, with that resolution
    controlled directly, in
    tests/unit/test_resume_manual_fill_personalizable_slots.py instead.
    """
    monkeypatch.setattr(import_story, "load_skeleton", lambda _path: original_skeleton)
    monkeypatch.setattr(
        import_story, "load_contract_for", lambda _path, _skeleton: None
    )


async def test_resume_dropped_sentinel_not_reinserted_pre_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fill that drops a declared sentinel is not reinserted; the job still persists.

    Under "derive, not prescribe" (Task R3), a dropped sentinel is no longer
    a fail-closed violation: `reinsert_storybook` re-scans the fill for the
    expected inner value ("Explorer") and, finding it nowhere in this node's
    prose, classifies the token ``"not_found"`` and leaves the plain text
    exactly as the fill produced it. There is nothing forged or dropped for
    `verify_manifest` to catch (the finished document has no sentinel of any
    kind), so the resume proceeds to `import_filled_story` and persists.
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
    imported_blob: dict[str, object] | None = None

    async def _fake_import_filled_story(
        _session: object, request: ImportRequest, **_kwargs: object
    ) -> str:
        nonlocal import_called, imported_blob
        import_called = True
        imported_blob = request.blob
        return "s_x"

    async def _fake_run_stage1_gate(*_args: object, **_kwargs: object) -> list[object]:
        return []

    monkeypatch.setattr(import_story, "import_filled_story", _fake_import_filled_story)
    monkeypatch.setattr(import_story, "run_stage1_gate", _fake_run_stage1_gate)

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

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, dropped_blob
    )

    assert import_called
    assert story_id == "s_x"
    assert status == "passed"
    assert job.status == "passed"
    assert imported_blob is not None
    nodes = cast("list[dict[str, object]]", imported_blob["nodes"])
    assert nodes[0]["body"] == "The hero walked generically."


async def test_resume_forged_sentinel_stripped_and_not_reinserted_pre_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fill that forges an undeclared sentinel has it stripped, never persisted as-is.

    The reference skeleton's body expects nothing at all (no ``{~...~}`` in
    its FILL beats), so `_expected_tokens_by_node` finds zero expected tokens
    for this node; the model-emitted `_HERO` sentinel is nonetheless stripped
    to its bare inner word by `reinsert_storybook`'s normalization pass
    (a forged sentinel is never trusted or counted as a match), and since
    nothing was expected there is nothing to wrap it back into. The result
    persists as plain, sentinel-free prose.
    """
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

    imported_blob: dict[str, object] | None = None

    async def _fake_import_filled_story(
        _session: object, request: ImportRequest, **_kwargs: object
    ) -> str:
        nonlocal imported_blob
        imported_blob = request.blob
        return "s_x"

    async def _fake_run_stage1_gate(*_args: object, **_kwargs: object) -> list[object]:
        return []

    monkeypatch.setattr(import_story, "import_filled_story", _fake_import_filled_story)
    monkeypatch.setattr(import_story, "run_stage1_gate", _fake_run_stage1_gate)

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

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, forged_blob
    )

    assert story_id == "s_x"
    assert status == "passed"
    assert job.status == "passed"
    assert imported_blob is not None
    nodes = cast("list[dict[str, object]]", imported_blob["nodes"])
    body = cast("str", nodes[0]["body"])
    assert body == "Explorer walked generically."
    assert _HERO not in body


async def test_resume_manifest_verification_failure_marks_job_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transform-bug `verify_manifest` failure still fails the job closed, pre-persist.

    `verify_manifest` passes by construction against the same
    `reinsert_storybook` call's own output, so a failure here means the
    transform itself is broken, not that the fill content is bad. This is
    the ONE way the pre-persist step can still fail closed under the new
    design; forced here via monkeypatch since the real transform cannot be
    made to fail its own manifest from a test fixture alone.
    """
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
    monkeypatch.setattr(import_story, "verify_manifest", lambda _doc, _manifest: False)

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

    with pytest.raises(ValidationError) as exc_info:
        await import_story.resume_manual_fill(session, job.id, clean_blob)

    assert not import_called, "a transform-bug blob must never reach persist_storybook"
    assert exc_info.value.details["field"] == "sentinel_integrity"
    assert exc_info.value.details["sentinel_integrity_violations"] == []
    assert job.status == "failed"
    assert job.error is not None
    assert session.commits == 1


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
    """Dormancy: a job with no skeleton_slug never reaches the reinsertion step.

    Regression pin for the existing skeleton-slug-less resume path (a
    standalone import with no skill provenance): `reinsert_storybook` must
    not even be called when there is no reference skeleton to derive
    expected tokens from.
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

    called = False
    real_reinsert = import_story.reinsert_storybook

    def _spy_reinsert(*args, **kwargs):
        nonlocal called
        called = True
        return real_reinsert(*args, **kwargs)

    monkeypatch.setattr(import_story, "import_filled_story", _fake_import_filled_story)
    monkeypatch.setattr(import_story, "reinsert_storybook", _spy_reinsert)

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, {"id": "s_x", "nodes": []}
    )

    assert story_id == "s_x"
    assert status == "passed"
    assert not called, "no skeleton_slug means no reference to derive tokens from"
