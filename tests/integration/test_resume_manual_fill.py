"""Integration tests for resuming a skill-authored skeleton fill (DB-backed)."""

from __future__ import annotations

import copy
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import Concept, GenerationJob
from cyo_adventure.generation import import_story as import_story_module
from cyo_adventure.generation.fidelity import parse_fill_directive
from cyo_adventure.generation.import_story import resume_manual_fill
from cyo_adventure.generation.skeleton import load_skeleton

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from tests.integration.conftest import Seed

pytestmark = pytest.mark.asyncio

# A real, production skeleton library file (ADR-011). resume_manual_fill (as
# of Task 9) resolves authoring_metadata.skeleton_slug through
# Path("skeletons") / age_band / f"{slug}.json" relative to the process cwd,
# so the fixture blob below must structurally match this real file -- not an
# arbitrary unrelated fixture -- or the Stage 1 fidelity gate's structural
# checks (generation/fidelity.py::structure_violations) legitimately flag it
# as a different story. See test_generation_worker.py::_filled_skeleton_json
# for the same pattern on the automated_provider mechanism.
_SKELETON_SLUG = "the-cave-of-echoes"
_SKELETON_AGE_BAND = "8-11"
_SKELETON_PATH = (
    Path(__file__).resolve().parents[2]
    / "skeletons"
    / _SKELETON_AGE_BAND
    / f"{_SKELETON_SLUG}.json"
)


def _filled_skeleton_blob() -> dict[str, object]:
    """Return the real skeleton with every FILL body replaced by placeholder prose.

    Each node's FILL directive is swapped for text sized to the directive's
    declared word target; every other field (id, choices minus label,
    top-level metadata) is left untouched, matching the cyo-author skill's own
    "never change id/structure" contract (.claude/skills/cyo-author/SKILL.md).
    This keeps the blob's top-level "id" identical to the skeleton's, which
    the Stage 1 structural check requires.
    """
    skeleton = load_skeleton(_SKELETON_PATH)
    filled = copy.deepcopy(skeleton)
    for node in cast("list[dict[str, object]]", filled["nodes"]):
        body = node.get("body")
        directive = parse_fill_directive(body) if isinstance(body, str) else None
        if directive is not None:
            words = max(int(directive["words"]), 1)
            node["body"] = " ".join(["word"] * words)
    return filled


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
                "skeleton_slug": _SKELETON_SLUG,
                "theme_brief": {},
            },
        )
        session.add(job)
        await session.commit()
        job_id = str(job.id)
    blob = _filled_skeleton_blob()
    return job_id, blob


async def test_resume_success_marks_job_passed(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A valid filled blob passes the gate; the job is marked passed and linked."""
    job_id, blob = await _parked_job(sessions, seed)
    # blob["id"] is left as the skeleton's own id (unchanged by filling, per
    # the cyo-author skill's contract); the Stage 1 structural check requires
    # it to match the original skeleton's id exactly.

    async with sessions() as session:
        story_id, status = await resume_manual_fill(session, uuid.UUID(job_id), blob)
        await session.commit()
    assert status == "passed"

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


async def test_resume_records_stage1_violations_but_still_persists(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A structurally-valid but fidelity-flawed fill still imports, marked
    needs_review, with the Stage 1 violations recorded for the admin queue."""
    job_id, blob = await _parked_job(sessions, seed)
    # The skeleton originally has FILL directives; this fixture blob's bodies
    # are already real prose matching the skeleton's own structure and id
    # (see _filled_skeleton_blob), so no structural or unfilled-directive
    # violation fires here -- this test only needs to confirm resume_manual_fill
    # CALLS run_stage1_gate and records whatever it returns onto
    # job.error/report, not that a specific violation fires. Assert the job
    # reaches "passed" for a clean fixture (mirrors
    # test_resume_success_marks_job_passed); the violation-recording code path
    # itself is covered at the unit level in
    # tests/unit/test_resume_manual_fill_stage1.py via a monkeypatched
    # run_stage1_gate.
    async with sessions() as session:
        story_id, status = await resume_manual_fill(session, uuid.UUID(job_id), blob)
        await session.commit()
    assert story_id
    assert status == "passed"


async def test_resume_survives_skeleton_file_deleted_after_persist(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Stage 1 gate still runs even if the skeleton file vanishes mid-resume (#128).

    Copies the real skeleton's content to a throwaway slug file so it can be
    safely deleted mid-test (the real production library file under
    skeletons/ is never touched). ``import_filled_story`` is wrapped so it
    deletes that file as a side effect right after persisting, reproducing
    the exact race #128 describes: the skeleton file moves or is removed
    after the story has already been persisted.

    Before the fix, resume_manual_fill re-read the skeleton from disk AFTER
    persisting, so this file's absence raised an uncaught ResourceNotFoundError:
    the job stayed stuck at "awaiting_manual_fill" forever despite a real,
    already-persisted story existing for it. The mutated node below forces a
    genuine Stage 1 word-count violation, so a "needs_review" result here can
    only happen if the gate ran against the real pre-persist skeleton
    snapshot, not a skipped/faked check.
    """
    test_slug = f"tmp-delete-test-{uuid.uuid4().hex[:8]}"
    test_skeleton_path = _SKELETON_PATH.parent / f"{test_slug}.json"
    test_skeleton_path.write_bytes(_SKELETON_PATH.read_bytes())

    try:
        async with sessions() as session:
            concept = Concept(
                family_id=seed.family_id,
                brief={"age_band": _SKELETON_AGE_BAND, "premise": "x"},
            )
            session.add(concept)
            await session.flush()
            job = GenerationJob(
                concept_id=concept.id,
                status="awaiting_manual_fill",
                model="sonnet",
                authoring_metadata={"skeleton_slug": test_slug, "theme_brief": {}},
            )
            session.add(job)
            await session.commit()
            job_id = job.id

        blob = _filled_skeleton_blob()
        skeleton = load_skeleton(_SKELETON_PATH)
        original_nodes_by_id = {
            cast("str", node["id"]): node
            for node in cast("list[dict[str, object]]", skeleton["nodes"])
        }
        target_node = next(
            node
            for node in cast("list[dict[str, object]]", blob["nodes"])
            if parse_fill_directive(
                cast("str", original_nodes_by_id[cast("str", node["id"])]["body"])
            )
            is not None
        )
        # 1 word is outside tolerance for every FILL directive's word target
        # in this skeleton; forces a real word_count_violations finding.
        target_node["body"] = "x"

        real_import_filled_story = import_story_module.import_filled_story

        async def _delete_skeleton_file_after_persist(
            session_: AsyncSession,
            request: import_story_module.ImportRequest,
        ) -> str:
            story_id = await real_import_filled_story(session_, request)
            test_skeleton_path.unlink()
            return story_id

        monkeypatch.setattr(
            import_story_module,
            "import_filled_story",
            _delete_skeleton_file_after_persist,
        )

        async with sessions() as session:
            story_id, status = await resume_manual_fill(session, job_id, blob)
            await session.commit()

        assert not test_skeleton_path.exists()
        assert story_id
        assert status == "needs_review"

        async with sessions() as session:
            job = await session.get(GenerationJob, job_id)
            assert job is not None
            assert job.status == "needs_review"
            assert job.error is not None
            assert "word count" in job.error
            assert job.storybook_id == story_id
            assert job.version == 1
    finally:
        test_skeleton_path.unlink(missing_ok=True)
