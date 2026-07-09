"""Integration tests for the generation worker (testcontainers Postgres).

Skips cleanly when Docker is unavailable. Uses the Postgres harness from
tests/integration/conftest.py and injects MockProvider directly so tests
are deterministic and do not depend on Redis or a live LLM.

Test cases:
4. Passing run: job.status == "passed", StorybookVersion created with blob and
   validation_report, job.storybook_id and job.version set.
5. needs_review run (injected provider returns a story that fails gate even
   after repairs): job.status == "needs_review", no StorybookVersion created.
6. authoring_metadata routing (Task 8): a queued job carrying authoring_metadata
   runs fill_skeleton + the Stage 1 fidelity gate instead of generate_story.
7. No authoring_metadata: the pre-existing generate_story path is unaffected.
"""

from __future__ import annotations

import copy
import json
import uuid  # noqa: TC003 -- uuid.UUID used at runtime in test bodies
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
import pytest_asyncio
from sqlalchemy import select

from cyo_adventure.db.models import (
    ChildProfile,
    Concept,
    Family,
    GenerationJob,
    Storybook,
    StorybookVersion,
    User,
)
from cyo_adventure.generation import worker as worker_module
from cyo_adventure.generation.fidelity import parse_fill_directive
from cyo_adventure.generation.orchestrator import GenerationOutcome
from cyo_adventure.generation.provider import _CANNED_STORY_JSON, MockProvider
from cyo_adventure.generation.skeleton import load_skeleton
from cyo_adventure.generation.worker import run_generation_job

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A structurally invalid story JSON that fails the gate on every attempt.
# The gate requires 'nodes' to be non-empty and each non-ending node to have
# choices; this dict has a non-ending node with no choices, which triggers L1.
_INVALID_STORY_JSON = json.dumps(
    {
        "schema_version": "2.0",
        "id": "s_bad_story",
        "version": 1,
        "title": "Bad Story",
        "metadata": {
            "age_band": "8-11",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 3.0,
                "tolerance": 1.0,
            },
            "tier": 1,
            "themes": [],
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": "branch_and_bottleneck",
            "content_flags": {
                "violence": "none",
                "scariness": "none",
                "peril": "none",
            },
        },
        "variables": [],
        "start_node": "n_start",
        "nodes": [
            # Non-ending node with NO choices: gate will block with L1 error.
            {
                "id": "n_start",
                "body": "You are stuck.",
                "is_ending": False,
                "choices": [],  # invalid: must have at least one choice
            }
        ],
    }
)

# A real, production skeleton library file (ADR-011). worker.py resolves the
# authoring_metadata.skeleton_slug through Path("skeletons") / age_band / f"{slug}.json"
# relative to the process cwd, so this must be a path that already exists on
# disk under the repo root (where pytest is invoked from), not a test fixture.
_SKELETON_SLUG = "the-cave-of-echoes"
_SKELETON_AGE_BAND = "8-11"
_SKELETON_PATH = (
    Path(__file__).resolve().parents[2]
    / "skeletons"
    / _SKELETON_AGE_BAND
    / f"{_SKELETON_SLUG}.json"
)

# A real 13-16 skeleton (a different band from _SKELETON_AGE_BAND above), used
# by the cross-band override test below (WS-C PR2 final review C1).
_CROSS_BAND_SKELETON_SLUG = "the-sunspire-ascent"
_CROSS_BAND_SKELETON_BAND = "13-16"
_CROSS_BAND_SKELETON_PATH = (
    Path(__file__).resolve().parents[2]
    / "skeletons"
    / _CROSS_BAND_SKELETON_BAND
    / f"{_CROSS_BAND_SKELETON_SLUG}.json"
)


def _filled_skeleton_json_for(skeleton_path: Path) -> str:
    """Return a JSON string: the given skeleton with every FILL body replaced.

    Each node's FILL directive is swapped for placeholder prose sized to the
    directive's declared word target; every other field (ids, choices minus
    label, top-level metadata) is left untouched. This satisfies both the
    structural gate (run_gate) fill_skeleton itself applies and the Stage 1
    fidelity pure-code checks (generation/fidelity.py::structure_violations,
    has_unfilled_directives, word-count tolerance) the worker runs afterward.
    """
    skeleton = load_skeleton(skeleton_path)
    filled = copy.deepcopy(skeleton)
    for node in cast("list[dict[str, object]]", filled["nodes"]):
        body = node.get("body")
        directive = parse_fill_directive(body) if isinstance(body, str) else None
        if directive is not None:
            words = max(int(directive["words"]), 1)
            node["body"] = " ".join(["word"] * words)
    return json.dumps(filled)


def _filled_skeleton_json() -> str:
    """Return a JSON string: the real 8-11 skeleton with every FILL body replaced."""
    return _filled_skeleton_json_for(_SKELETON_PATH)


@asynccontextmanager
async def _session_ctx(
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Wrap a session from the factory in a context manager."""
    session = sessions()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def _make_session_factory(
    sessions: async_sessionmaker[AsyncSession],
):  # type: ignore[return]
    """Return a callable session factory compatible with worker's session_factory."""

    def factory():  # type: ignore[return-value]
        return _session_ctx(sessions)

    return factory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def gen_seed(sessions: async_sessionmaker[AsyncSession]) -> dict[str, object]:
    """Seed the minimal rows needed by the worker: Family, User, Concept, Job."""
    async with sessions() as session:
        fam = Family(name="Test Family")
        session.add(fam)
        await session.flush()

        guardian = User(
            family_id=fam.id, role="guardian", authn_subject="guardian-gen-test"
        )
        child_profile = ChildProfile(
            family_id=fam.id,
            display_name="TestKid",
            age_band="8-11",
        )
        session.add_all([guardian, child_profile])
        await session.flush()

        concept = Concept(
            family_id=fam.id,
            created_by=guardian.id,
            brief={
                "premise": "A brave explorer discovers a hidden garden.",
                "protagonist": {
                    "name": "Captain Rosa",
                    "age": 9,
                    "role": "young explorer",
                },
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
            },
        )
        session.add(concept)
        await session.flush()

        job = GenerationJob(
            concept_id=concept.id,
            status="queued",
        )
        session.add(job)
        await session.commit()

        return {
            "job_id": job.id,
            "concept_id": concept.id,
            "family_id": fam.id,
        }


@pytest_asyncio.fixture
async def gen_seed_authoring(
    sessions: async_sessionmaker[AsyncSession],
) -> dict[str, object]:
    """Seed rows for a skeleton_fill job: Family, User, Concept, and a Job
    carrying authoring_metadata (method="skeleton_fill", mechanism="automated_provider";
    see story_requests/authoring_plan.py::build_authoring_plan).

    Otherwise identical to ``gen_seed``; only the job row differs.
    """
    async with sessions() as session:
        fam = Family(name="Test Family")
        session.add(fam)
        await session.flush()

        guardian = User(
            family_id=fam.id,
            role="guardian",
            authn_subject="guardian-gen-test-authoring",
        )
        child_profile = ChildProfile(
            family_id=fam.id,
            display_name="TestKid",
            age_band="8-11",
        )
        session.add_all([guardian, child_profile])
        await session.flush()

        concept = Concept(
            family_id=fam.id,
            created_by=guardian.id,
            brief={
                "premise": "A brave explorer discovers a hidden garden.",
                "protagonist": {
                    "name": "Captain Rosa",
                    "age": 9,
                    "role": "young explorer",
                },
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
            },
        )
        session.add(concept)
        await session.flush()

        job = GenerationJob(
            concept_id=concept.id,
            status="queued",
            authoring_metadata={
                "skeleton_slug": _SKELETON_SLUG,
                "theme_brief": {
                    "premise": "A brave explorer discovers a hidden garden."
                },
            },
        )
        session.add(job)
        await session.commit()

        return {
            "job_id": job.id,
            "concept_id": concept.id,
            "family_id": fam.id,
        }


@pytest_asyncio.fixture
async def gen_seed_cross_band_authoring(
    sessions: async_sessionmaker[AsyncSession],
) -> dict[str, object]:
    """Seed a skeleton_fill job whose concept is 8-11 but whose authoring_metadata
    carries a CROSS-BAND override (WS-C PR2 final review C1): skeleton_slug
    names a real 13-16 skeleton, and skeleton_band records that skeleton's
    real band. The concept's own brief.age_band stays "8-11" (the request's
    own band) so this fixture only passes if the fill path resolves the
    skeleton path from the stored skeleton_band, not the concept's band.
    """
    async with sessions() as session:
        fam = Family(name="Test Family")
        session.add(fam)
        await session.flush()

        guardian = User(
            family_id=fam.id,
            role="guardian",
            authn_subject="guardian-gen-test-cross-band",
        )
        child_profile = ChildProfile(
            family_id=fam.id,
            display_name="TestKid",
            age_band="8-11",
        )
        session.add_all([guardian, child_profile])
        await session.flush()

        concept = Concept(
            family_id=fam.id,
            created_by=guardian.id,
            brief={
                "premise": "A young astronomer maps a sunspire.",
                "protagonist": {
                    "name": "Jules",
                    "age": 9,
                    "role": "young astronomer",
                },
                "point_of_view": "second",
                "age_band": "8-11",
                "reading_level_target": 3.0,
                "tier": 1,
                "tone": "adventurous",
                "themes_allowed": ["exploration"],
                "content_nogo": [],
                "target_node_count": 4,
                "ending_count": 1,
                "structure_pattern": "time_cave",
                "desired_variables": [],
                "special_constraints": [],
            },
        )
        session.add(concept)
        await session.flush()

        job = GenerationJob(
            concept_id=concept.id,
            status="queued",
            authoring_metadata={
                "skeleton_slug": _CROSS_BAND_SKELETON_SLUG,
                "skeleton_band": _CROSS_BAND_SKELETON_BAND,
                "theme_brief": {"premise": "A young astronomer maps a sunspire."},
            },
        )
        session.add(job)
        await session.commit()

        return {
            "job_id": job.id,
            "concept_id": concept.id,
            "family_id": fam.id,
        }


# ---------------------------------------------------------------------------
# Test 4: Passing run produces StorybookVersion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_passing_run_creates_storybook_version(
    sessions: async_sessionmaker[AsyncSession],
    gen_seed: dict[str, object],
) -> None:
    """A passing run creates Storybook + StorybookVersion; job links to them."""
    job_id: uuid.UUID = gen_seed["job_id"]  # type: ignore[assignment]

    # Inject a mock provider that returns valid canned story for Stage A + B.
    provider = MockProvider(responses=[_CANNED_STORY_JSON] * 8)

    await run_generation_job(
        job_id,
        provider=provider,
        session_factory=_make_session_factory(sessions),
    )

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "passed", f"Expected passed, got {job.status}"
        assert job.storybook_id is not None
        assert job.version == 1
        assert job.report is not None
        assert job.provider is not None
        assert job.prompt_version is not None

        # Verify Storybook row exists.
        # After the Phase 3 slice-2 moderation pipeline, a clean story advances
        # from draft to in_review (ready for guardian/admin review).
        story = await session.get(Storybook, job.storybook_id)
        assert story is not None
        assert story.status == "in_review"

        # Verify StorybookVersion row exists with blob and report.
        sv = await session.get(StorybookVersion, (job.storybook_id, 1))
        assert sv is not None
        assert sv.blob is not None
        assert sv.validation_report is not None
        # F18/#63: the version's provider matches the job's, stamped at
        # persist time from the same effective_provider.
        assert sv.provider == job.provider
        # WS-C PR2: gen_seed's job carries no authoring_metadata (fresh
        # generation), so the threaded skeleton_slug is None. The real
        # slug-threading case (a skeleton_fill job, whose authoring_metadata
        # carries skeleton_slug) is covered deterministically by
        # test_stage1_downgraded_needs_review_still_persists_storybook below,
        # which persists via gen_seed_authoring without MockProvider response
        # non-determinism.
        assert sv.skeleton_slug is None


# ---------------------------------------------------------------------------
# Test 5: needs_review run (failing story): no StorybookVersion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_needs_review_run_creates_no_storybook_version(
    sessions: async_sessionmaker[AsyncSession],
    gen_seed: dict[str, object],
) -> None:
    """A needs_review outcome creates no StorybookVersion; job records report."""
    job_id: uuid.UUID = gen_seed["job_id"]  # type: ignore[assignment]

    # Queue invalid story for all stages so the gate always blocks.
    # max_repairs defaults to 3; queue 8 copies to cover all attempts.
    provider = MockProvider(responses=[_INVALID_STORY_JSON] * 8)

    await run_generation_job(
        job_id,
        provider=provider,
        session_factory=_make_session_factory(sessions),
    )

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status in {
            "needs_review",
            "failed",
        }, f"Expected needs_review or failed, got {job.status}"
        assert job.storybook_id is None

        # Confirm no StorybookVersion exists for this job's family scope.
        result = await session.execute(
            select(StorybookVersion)
            .join(
                Storybook,
                Storybook.id == StorybookVersion.storybook_id,
            )
            .where(Storybook.family_id == gen_seed["family_id"])
        )
        assert result.first() is None, "StorybookVersion must not be created"


# ---------------------------------------------------------------------------
# Test 6: authoring_metadata routes to fill_skeleton + Stage 1 fidelity gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_runs_fill_skeleton_for_authoring_metadata_jobs(
    sessions: async_sessionmaker[AsyncSession],
    gen_seed_authoring: dict[str, object],
) -> None:
    """A queued job carrying authoring_metadata runs fill_skeleton, not generate_story.

    Exactly two scripted responses are queued: one for the fill call itself
    (fill_skeleton makes a single provider call for a clean fill; no Stage A,
    unlike generate_story which always makes at least two: Stage A then Stage
    B), plus one for the moderation pipeline's guaranteed bounded auto-repair
    (the default "mock" review backend always returns an unparseable "{}"
    verdict, which soft-flags Stage 1 safety and triggers exactly one
    attempt_repair call against this same provider -- see
    test_passing_run_creates_storybook_version, which budgets for the same
    thing with headroom to spare).

    If the worker still routes through generate_story, Stage A and Stage B
    alone consume both queued responses, leaving none for the guaranteed
    repair call; MockProvider raises on that third call, so the job ends up
    "failed" instead of "passed"/"needs_review". This is what makes the
    assertion below a real signal of which pipeline ran, not just "did the
    run not crash".
    """
    job_id: uuid.UUID = gen_seed_authoring["job_id"]  # type: ignore[assignment]

    # A valid filled-skeleton JSON string (not a generate_story Stage-A/B
    # output), reused for both the fill call and the moderation repair call.
    provider = MockProvider(responses=[_filled_skeleton_json()] * 2)

    await run_generation_job(
        job_id,
        provider=provider,
        session_factory=_make_session_factory(sessions),
    )

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status in {
            "passed",
            "needs_review",
        }, f"Expected passed or needs_review, got {job.status}"
        assert job.report is not None


# ---------------------------------------------------------------------------
# Test 6b: a cross-band override resolves the STORED band, not the request's
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_cross_band_override_loads_stored_band(
    sessions: async_sessionmaker[AsyncSession],
    gen_seed_cross_band_authoring: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C1: _run_skeleton_fill builds the skeleton path from the stored
    ``authoring_metadata["skeleton_band"]`` ("13-16"), not the concept's own
    request band ("8-11", via ``gen_seed_cross_band_authoring``'s fixture).

    ``load_skeleton`` is wrapped (not replaced) to record every path it is
    called with; if C1.2 is reverted, the worker builds
    ``skeletons/8-11/the-sunspire-ascent.json`` (a file that does not exist),
    ``load_skeleton`` raises ``FileNotFoundError``, and the job ends up
    "failed" instead of "passed"/"needs_review" -- both assertions below
    would fail on a revert.
    """
    job_id: uuid.UUID = gen_seed_cross_band_authoring["job_id"]  # type: ignore[assignment]

    real_load_skeleton = worker_module.load_skeleton
    recorded_paths: list[Path] = []

    def _recording_load_skeleton(path: Path) -> dict[str, object]:
        recorded_paths.append(path)
        return real_load_skeleton(path)

    monkeypatch.setattr(worker_module, "load_skeleton", _recording_load_skeleton)

    provider = MockProvider(
        responses=[_filled_skeleton_json_for(_CROSS_BAND_SKELETON_PATH)] * 2
    )

    await run_generation_job(
        job_id,
        provider=provider,
        session_factory=_make_session_factory(sessions),
    )

    # worker.py builds a cwd-relative path (Path("skeletons") / band / ...),
    # not the absolute _CROSS_BAND_SKELETON_PATH test constant used to seed
    # the mock provider's fixture blob above; compare resolved paths so both
    # forms are equal regardless of which one each side started from.
    assert len(recorded_paths) == 1
    assert recorded_paths[0].resolve() == _CROSS_BAND_SKELETON_PATH.resolve()

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status in {
            "passed",
            "needs_review",
        }, f"Expected passed or needs_review, got {job.status} ({job.error})"
        assert job.report is not None


# ---------------------------------------------------------------------------
# Test 7: no authoring_metadata leaves the generate_story path unaffected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_still_runs_generate_story_when_no_authoring_metadata(
    sessions: async_sessionmaker[AsyncSession],
    gen_seed: dict[str, object],
) -> None:
    """A job with authoring_metadata=None (fresh_generation) is unaffected by Task 8.

    Mirrors test_passing_run_creates_storybook_version: documents (not changes)
    that the pre-existing generate_story path still runs when authoring_metadata
    is absent.
    """
    job_id: uuid.UUID = gen_seed["job_id"]  # type: ignore[assignment]

    provider = MockProvider(responses=[_CANNED_STORY_JSON] * 8)

    await run_generation_job(
        job_id,
        provider=provider,
        session_factory=_make_session_factory(sessions),
    )

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "passed", f"Expected passed, got {job.status}"
        assert job.storybook_id is not None
        assert job.report is not None


# ---------------------------------------------------------------------------
# Test 8 (Item 3): a Stage-1-downgraded automated_provider job still persists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stage1_downgraded_needs_review_still_persists_storybook(
    sessions: async_sessionmaker[AsyncSession],
    gen_seed_authoring: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Stage-1-downgraded needs_review still gets a real, queryable Storybook.

    Before this fix, run_generation_job's persist gate was
    ``outcome.status == "passed"``, so _run_skeleton_fill's Stage 1 downgrade
    (an otherwise-clean fill flagged by the fidelity gate) left the job
    needs_review with NO storybook at all -- worse than Item 2's skill-path
    orphaning, since here the story was never persisted in the first place.

    After the #133 rework the Stage 1 fidelity gate runs INSIDE
    orchestrator.fill_skeleton, so fill_skeleton itself emits the
    ``"stage1_fidelity_violations"`` report key on a budget-exhausted downgrade.
    Here fill_skeleton is monkeypatched (a bare-name import in worker.py) to
    return that exact needs_review-with-key outcome deterministically, isolating
    the behavior under test to worker.py's persist gate rather than depending on
    the mock review backend's own soft-flagging behavior (see
    test_worker_runs_fill_skeleton_for_authoring_metadata_jobs's docstring,
    which documents that ambiguity for the undowngraded case).
    """
    job_id: uuid.UUID = gen_seed_authoring["job_id"]  # type: ignore[assignment]
    filled = json.loads(_filled_skeleton_json())

    async def _fake_fill_skeleton(
        *_args: object, **_kwargs: object
    ) -> GenerationOutcome:
        return GenerationOutcome(
            status="needs_review",
            storybook=filled,
            report={
                "stage1_fidelity_violations": [
                    "node 'n1' word count 3 outside [6, 14] for target 10"
                ]
            },
            attempts=3,
            stage_log=[],
        )

    monkeypatch.setattr(worker_module, "fill_skeleton", _fake_fill_skeleton)

    # One response budgeted for the moderation pipeline's guaranteed bounded
    # auto-repair call (see test_worker_runs_fill_skeleton_for_authoring_metadata_jobs's
    # docstring); fill_skeleton itself is faked above and makes no provider call.
    provider = MockProvider(responses=[_filled_skeleton_json()])

    await run_generation_job(
        job_id,
        provider=provider,
        session_factory=_make_session_factory(sessions),
    )

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "needs_review", f"Expected needs_review, got {job.status}"
        assert job.storybook_id is not None
        assert job.version == 1

        story = await session.get(Storybook, job.storybook_id)
        assert story is not None

        sv = await session.get(StorybookVersion, (job.storybook_id, 1))
        assert sv is not None
        assert sv.blob is not None
        # WS-C PR2: the version's skeleton_slug matches the job's
        # authoring_metadata (gen_seed_authoring), threaded through at
        # persist time. This is a deterministic skeleton_fill persist path
        # (fill_skeleton is monkeypatched above), unlike
        # test_worker_runs_fill_skeleton_for_authoring_metadata_jobs whose
        # passed/needs_review outcome is ambiguous by design.
        assert sv.skeleton_slug == _SKELETON_SLUG


@pytest.mark.asyncio
async def test_non_stage1_needs_review_still_creates_no_storybook(
    sessions: async_sessionmaker[AsyncSession],
    gen_seed_authoring: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard: a needs_review from a DIFFERENT cause must not persist.

    Simulates orchestrator._build_outcome's own needs_review (safety-flagged,
    or gate-blocked-with-doc after exhausting repairs) by having fill_skeleton
    itself return needs_review with no "stage1_fidelity_violations" key. Item
    3's widened persist gate must not touch this pre-existing, non-Plan-2
    case: the job ends up needs_review with no Storybook created, exactly as
    before this fix.
    """
    job_id: uuid.UUID = gen_seed_authoring["job_id"]  # type: ignore[assignment]
    filled = json.loads(_filled_skeleton_json())

    async def _fake_fill_skeleton(
        *_args: object, **_kwargs: object
    ) -> GenerationOutcome:
        return GenerationOutcome(
            status="needs_review",
            storybook=filled,
            report={},
            attempts=3,
            stage_log=[],
        )

    monkeypatch.setattr(worker_module, "fill_skeleton", _fake_fill_skeleton)

    provider = MockProvider(responses=[_filled_skeleton_json()])

    await run_generation_job(
        job_id,
        provider=provider,
        session_factory=_make_session_factory(sessions),
    )

    async with sessions() as session:
        job = await session.get(GenerationJob, job_id)
        assert job is not None
        assert job.status == "needs_review", f"Expected needs_review, got {job.status}"
        assert job.storybook_id is None

        result = await session.execute(
            select(StorybookVersion)
            .join(
                Storybook,
                Storybook.id == StorybookVersion.storybook_id,
            )
            .where(Storybook.family_id == gen_seed_authoring["family_id"])
        )
        assert result.first() is None, "StorybookVersion must not be created"
