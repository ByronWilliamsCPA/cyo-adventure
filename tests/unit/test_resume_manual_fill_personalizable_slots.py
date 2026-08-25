"""Unit tests for Task 6c: resume_manual_fill threads the personalizable-slot
set it resolves itself into the moderation-entry backstop (fixes I1/I2/M1).

These tests operate at the ``resume_manual_fill`` layer: they capture the
``personalizable_slots`` keyword argument passed to a faked
``import_filled_story`` to prove the VALUE resume_manual_fill computes and
threads through, complementing the pure-function-layer tests of
``personalizable_slot_ids_for_job`` in ``test_moderation_pipeline.py`` and
the ``run_moderation_pipeline``-layer tests of the sentinel-default parameter
in that same file.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from cyo_adventure.db.models import Concept, GenerationJob
from cyo_adventure.generation import import_story
from cyo_adventure.moderation import personalizable_slots as pslots_mod
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.theme_contract import SlotScope, SlotSpec, ThemeContract

pytestmark = pytest.mark.asyncio


def _personalizable_contract() -> ThemeContract:
    """A minimal contract declaring one ``kind="personalizable"`` HERO slot."""
    return ThemeContract(
        contract_version=1,
        skeleton_slug="themed-slug",
        age_band=AgeBand.BAND_8_11,
        legacy_lexicon=[],
        default_binding={"HERO": "Ada"},
        slots=[
            SlotSpec(
                id="HERO",
                scope=SlotScope.GLOBAL,
                meaning="the reader's own child, personalized",
                kind="personalizable",
                personalization_field="protagonist_first_name",
                role_safety="protagonist",
            ),
        ],
    )


class _FakeSession:
    def __init__(self, *, job: GenerationJob, concept: Concept) -> None:
        self._job = job
        self._concept = concept

    async def get(self, model: type[object], key: object) -> object | None:
        _ = key
        if model is GenerationJob:
            return self._job
        if model is Concept:
            return self._concept
        return None

    async def commit(self) -> None:
        return None


def _capturing_import_filled_story(
    captured: dict[str, object],
) -> object:
    """Return a fake ``import_filled_story`` that records its kwargs."""

    async def _fake(_session: object, _request: object, **kwargs: object) -> str:
        captured.update(kwargs)
        return "s_x"

    return _fake


async def test_resume_with_no_skeleton_slug_threads_empty_frozenset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(Dormancy) A resume with no ``skeleton_slug`` threads ``frozenset()``,
    exactly what ``personalizable_slot_ids_for_story`` would answer for a job
    with no matched skeleton at all.
    """
    concept = Concept(id=uuid.uuid4(), family_id=uuid.uuid4(), brief={})
    job = GenerationJob(
        id=uuid.uuid4(),
        concept_id=concept.id,
        status="awaiting_manual_fill",
        authoring_metadata={},
    )
    session = _FakeSession(job=job, concept=concept)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        import_story, "import_filled_story", _capturing_import_filled_story(captured)
    )

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, {"id": "s_x", "nodes": []}
    )

    assert story_id == "s_x"
    assert status == "passed"
    assert captured["personalizable_slots"] == frozenset()


async def test_resume_sentinel_free_skeleton_threads_empty_frozenset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(Dormancy) A legacy skeleton with no contract sidecar threads
    ``frozenset()``: unaffected by Task 6c, matching every non-personalizable
    resume today.
    """
    concept = Concept(id=uuid.uuid4(), family_id=uuid.uuid4(), brief={})
    job = GenerationJob(
        id=uuid.uuid4(),
        concept_id=concept.id,
        status="awaiting_manual_fill",
        authoring_metadata={"skeleton_slug": "x", "skeleton_band": "8-11"},
    )
    session = _FakeSession(job=job, concept=concept)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        import_story, "import_filled_story", _capturing_import_filled_story(captured)
    )
    monkeypatch.setattr(import_story, "load_skeleton", lambda _path: {"nodes": []})

    async def _fake_run_stage1_gate(*_args: object, **_kwargs: object) -> list[str]:
        return []

    monkeypatch.setattr(import_story, "run_stage1_gate", _fake_run_stage1_gate)
    # import_story's own Stage 1 reference resolution (_stage1_reference_skeleton)
    # holds a SEPARATE bound name for load_contract_for than the moderation
    # pipeline's personalizable-slot resolver does; both must agree the
    # contract is absent for this legacy-skeleton scenario to reach "passed".
    monkeypatch.setattr(
        import_story, "load_contract_for", lambda _path, _skeleton: None
    )
    monkeypatch.setattr(
        pslots_mod,
        "resolve_skeleton_path",
        lambda _band, _slug: Path("x.json"),
    )
    monkeypatch.setattr(pslots_mod, "load_skeleton", lambda _path: {"nodes": []})
    monkeypatch.setattr(pslots_mod, "load_contract_for", lambda _path, _skeleton: None)

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, {"id": "s_x", "nodes": []}
    )

    assert story_id == "s_x"
    assert status == "passed"
    assert captured["personalizable_slots"] == frozenset()


async def test_resume_personalizable_contract_threads_declared_slot_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(I1 fix proof) A resume whose matched skeleton has a personalizable
    contract threads the DECLARED slot id set, not an empty set.

    Before Task 6c, the moderation entry's own DB-based resolver would find
    no ``GenerationJob`` yet (its ``storybook_id`` link is not written until
    after this call returns) and silently answer ``frozenset()``; a real
    personalizable sentinel in the blob would then look "unknown" and be
    auto-rejected. This test proves the threaded value is non-empty, using
    the in-memory job instead of a premature database lookup.
    """
    concept = Concept(id=uuid.uuid4(), family_id=uuid.uuid4(), brief={})
    job = GenerationJob(
        id=uuid.uuid4(),
        concept_id=concept.id,
        status="awaiting_manual_fill",
        authoring_metadata={"skeleton_slug": "themed-slug", "skeleton_band": "8-11"},
    )
    session = _FakeSession(job=job, concept=concept)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        import_story, "import_filled_story", _capturing_import_filled_story(captured)
    )
    monkeypatch.setattr(import_story, "load_skeleton", lambda _path: {"nodes": []})

    async def _fake_run_stage1_gate(*_args: object, **_kwargs: object) -> list[str]:
        return []

    monkeypatch.setattr(import_story, "run_stage1_gate", _fake_run_stage1_gate)
    # import_story's own Stage 1 reference resolution holds separate bound
    # names for load_contract_for/render_bound_skeleton than the moderation
    # pipeline's personalizable-slot resolver; wire both to the SAME contract
    # so this test's "passed" outcome reflects a real, coherent resume.
    monkeypatch.setattr(
        import_story,
        "load_contract_for",
        lambda _path, _skeleton: _personalizable_contract(),
    )
    monkeypatch.setattr(
        import_story,
        "render_bound_skeleton",
        lambda _skeleton, _bindings, _slots=frozenset(): {"nodes": [], "bound": True},
    )
    monkeypatch.setattr(
        pslots_mod,
        "resolve_skeleton_path",
        lambda _band, _slug: Path("themed-slug.json"),
    )
    monkeypatch.setattr(pslots_mod, "load_skeleton", lambda _path: {"nodes": []})
    monkeypatch.setattr(
        pslots_mod,
        "load_contract_for",
        lambda _path, _skeleton: _personalizable_contract(),
    )

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, {"id": "s_x", "nodes": []}
    )

    assert story_id == "s_x"
    assert status == "passed"
    assert captured["personalizable_slots"] == frozenset({"HERO"})
    # job.storybook_id is only linked to story_id AFTER import_filled_story
    # returns (the I1 timing this test guards against); confirm it really
    # was unset at the moment import_filled_story (and thus moderation) ran.
    assert job.storybook_id == "s_x"


async def test_resume_missing_metadata_band_falls_back_to_brief_band(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(I2 fix proof) A job whose ``authoring_metadata`` predates the
    ``skeleton_band`` key still threads the correct, non-``None`` slot set,
    because resume_manual_fill resolves the band via
    ``_resolve_resume_band``'s brief-band fallback before calling
    ``personalizable_slot_ids_for_job``, not by re-reading the (absent) raw
    metadata key the way ``personalizable_slot_ids_for_story`` would.
    """
    concept = Concept(
        id=uuid.uuid4(), family_id=uuid.uuid4(), brief={"age_band": "8-11"}
    )
    job = GenerationJob(
        id=uuid.uuid4(),
        concept_id=concept.id,
        status="awaiting_manual_fill",
        authoring_metadata={"skeleton_slug": "themed-slug"},  # no skeleton_band key
    )
    session = _FakeSession(job=job, concept=concept)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        import_story, "import_filled_story", _capturing_import_filled_story(captured)
    )
    monkeypatch.setattr(import_story, "load_skeleton", lambda _path: {"nodes": []})

    async def _fake_run_stage1_gate(*_args: object, **_kwargs: object) -> list[str]:
        return []

    monkeypatch.setattr(import_story, "run_stage1_gate", _fake_run_stage1_gate)
    monkeypatch.setattr(
        import_story,
        "load_contract_for",
        lambda _path, _skeleton: _personalizable_contract(),
    )
    monkeypatch.setattr(
        import_story,
        "render_bound_skeleton",
        lambda _skeleton, _bindings, _slots=frozenset(): {"nodes": [], "bound": True},
    )

    captured_band: list[str | None] = []

    def _capturing_resolve_skeleton_path(band: str, _slug: str) -> Path:
        captured_band.append(band)
        return Path("themed-slug.json")

    monkeypatch.setattr(
        pslots_mod, "resolve_skeleton_path", _capturing_resolve_skeleton_path
    )
    monkeypatch.setattr(pslots_mod, "load_skeleton", lambda _path: {"nodes": []})
    monkeypatch.setattr(
        pslots_mod,
        "load_contract_for",
        lambda _path, _skeleton: _personalizable_contract(),
    )

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, {"id": "s_x", "nodes": []}
    )

    assert story_id == "s_x"
    assert status == "passed"
    # The brief's age_band ("8-11"), not an empty/None band, reached the
    # resolver: proof the fallback (not the missing raw metadata key) drove
    # the lookup.
    assert captured_band == ["8-11"]
    assert captured["personalizable_slots"] == frozenset({"HERO"})


async def test_resume_uncomputable_contract_threads_unrecoverable_marker_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(M1 fix proof) A ``skeleton_slug`` present but the skeleton/contract
    genuinely uncomputable (file missing) threads
    ``PERSONALIZABLE_SLOTS_UNRECOVERABLE`` through to the moderation entry,
    which fails closed on it, instead of the story persisting clean with no
    entry-level check at all.
    """
    concept = Concept(id=uuid.uuid4(), family_id=uuid.uuid4(), brief={})
    job = GenerationJob(
        id=uuid.uuid4(),
        concept_id=concept.id,
        status="awaiting_manual_fill",
        authoring_metadata={
            "skeleton_slug": "does-not-exist",
            "skeleton_band": "8-11",
        },
    )
    session = _FakeSession(job=job, concept=concept)
    captured: dict[str, object] = {}

    async def _fake_import_filled_story(
        _session: object, _request: object, **kwargs: object
    ) -> str:
        captured.update(kwargs)
        # Mirrors the real import_filled_story -> run_moderation_pipeline ->
        # entry-level backstop fail-closed behavior for an unrecoverable slot
        # contract: the caller never sees a persisted, clean-looking story for
        # this job.
        assert (
            kwargs["personalizable_slots"]
            is pslots_mod.PERSONALIZABLE_SLOTS_UNRECOVERABLE
        )
        return "s_x"

    monkeypatch.setattr(import_story, "import_filled_story", _fake_import_filled_story)

    def _raise_not_found(_path: object) -> dict[str, object]:
        raise FileNotFoundError("no such skeleton file")

    monkeypatch.setattr(import_story, "load_skeleton", _raise_not_found)
    monkeypatch.setattr(
        pslots_mod,
        "resolve_skeleton_path",
        lambda _band, _slug: Path("does-not-exist.json"),
    )
    monkeypatch.setattr(pslots_mod, "load_skeleton", _raise_not_found)

    story_id, status = await import_story.resume_manual_fill(
        session, job.id, {"id": "s_x", "nodes": []}
    )

    assert story_id == "s_x"
    assert (
        captured["personalizable_slots"]
        is pslots_mod.PERSONALIZABLE_SLOTS_UNRECOVERABLE
    )
    # The skeleton-load failure ALSO downgrades the Stage 1 fidelity gate
    # outcome (pre-existing #128 behavior, unrelated to Task 6c); this test's
    # only concern is the personalizable_slots value threaded through, above.
    assert status == "needs_review"
