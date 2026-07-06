"""Unit tests for the authoring-plan service (validation, warnings, job creation)."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.api.schemas import AuthoringPlanRequest
from cyo_adventure.core.exceptions import StateTransitionError, ValidationError
from cyo_adventure.db.models import Concept, GenerationJob, StoryRequest
from cyo_adventure.story_requests.authoring_plan import (
    build_authoring_plan,
    eligibility_warnings,
)

pytestmark = pytest.mark.asyncio


class _FakeSession:
    """Minimal async session double for build_authoring_plan.

    Mirrors the _FakeSession pattern in tests/unit/test_story_requests.py,
    extended with a singular ``scalar`` for the idempotency lookup.
    """

    def __init__(self, *, existing_job: GenerationJob | None = None) -> None:
        self._existing_job = existing_job
        self.added: list[object] = []

    async def scalar(self, statement: object) -> GenerationJob | None:
        """Return the seeded existing job (or None), ignoring the statement."""
        _ = statement
        return self._existing_job

    def add(self, obj: object) -> None:
        """Record an added ORM instance."""
        self.added.append(obj)

    async def flush(self) -> None:
        """Assign a UUID to any tracked object still missing an id."""
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()  # pyright: ignore[reportAttributeAccessIssue]


def _concept(band: str = "8-11") -> Concept:
    return Concept(
        id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        brief={"age_band": band, "premise": "a fox finds a lantern"},
    )


def _request() -> StoryRequest:
    return StoryRequest(
        family_id=uuid.uuid4(),
        profile_id=uuid.uuid4(),
        request_text="a fox",
        status="approved",
    )


async def test_fresh_generation_automated_provider_creates_queued_job() -> None:
    """The unchanged path: a queued job, no skeleton, no warnings."""
    session = _FakeSession()
    concept = _concept()
    result = await build_authoring_plan(
        session,
        _request(),
        concept,
        AuthoringPlanRequest(
            method="fresh_generation",
            mechanism="automated_provider",
            prep_model="openrouter/some-model",
        ),
    )
    assert result.job.status == "queued"
    assert result.job.concept_id == concept.id
    assert result.skeleton_slug is None
    assert result.warnings == []


async def test_skeleton_fill_skill_parks_job_with_metadata() -> None:
    """The new path: an awaiting_manual_fill job carrying skeleton + theme_brief."""
    session = _FakeSession()
    concept = _concept("8-11")
    result = await build_authoring_plan(
        session,
        _request(),
        concept,
        AuthoringPlanRequest(
            method="skeleton_fill", mechanism="skill", prep_model="sonnet"
        ),
    )
    assert result.job.status == "awaiting_manual_fill"
    assert result.skeleton_slug == "the-cave-of-echoes"
    assert result.job.authoring_metadata == {
        "skeleton_slug": "the-cave-of-echoes",
        "theme_brief": concept.brief,
        "review_stage1_model": None,
        "review_stage2_model": None,
    }


def test_fresh_generation_with_skill_mechanism_is_rejected() -> None:
    """mechanism='skill' only makes sense with method='skeleton_fill'.

    The illegal pairing is now unrepresentable: the schema-level
    model_validator rejects it at construction (a pydantic ValidationError ->
    FastAPI 422), so it never reaches build_authoring_plan.
    """
    with pytest.raises(PydanticValidationError):
        AuthoringPlanRequest(
            method="fresh_generation", mechanism="skill", prep_model="sonnet"
        )


async def test_skeleton_fill_automated_provider_creates_queued_job_with_metadata() -> (
    None
):
    """Plan 2: automated skeleton-fill prep is now supported and queued."""
    session = _FakeSession()
    concept = _concept("8-11")
    plan = AuthoringPlanRequest(
        method="skeleton_fill",
        mechanism="automated_provider",
        prep_model="openrouter/some-model",
    )
    result = await build_authoring_plan(session, _request(), concept, plan)
    assert result.job.status == "queued"
    assert result.skeleton_slug == "the-cave-of-echoes"
    assert result.job.authoring_metadata == {
        "skeleton_slug": "the-cave-of-echoes",
        "theme_brief": concept.brief,
        "review_stage1_model": None,
        "review_stage2_model": None,
    }


async def test_unrecognized_skill_model_is_rejected() -> None:
    """prep_model must be a real Claude Code session model for mechanism='skill'."""
    session = _FakeSession()
    with pytest.raises(ValidationError):
        await build_authoring_plan(
            session,
            _request(),
            _concept(),
            AuthoringPlanRequest(
                method="skeleton_fill", mechanism="skill", prep_model="gpt-4o"
            ),
        )


async def test_existing_job_for_concept_is_conflict() -> None:
    """A second authoring-plan call for the same concept is a 409, not a duplicate job."""
    concept = _concept()
    existing = GenerationJob(id=uuid.uuid4(), concept_id=concept.id, status="queued")
    session = _FakeSession(existing_job=existing)
    with pytest.raises(StateTransitionError):
        await build_authoring_plan(
            session,
            _request(),
            concept,
            AuthoringPlanRequest(
                method="fresh_generation",
                mechanism="automated_provider",
                prep_model="openrouter/some-model",
            ),
        )


async def test_no_matching_skeleton_for_band_is_rejected() -> None:
    """A band with no skeleton directory at all yields a 422, not a crash."""
    session = _FakeSession()
    with pytest.raises(ValidationError):
        await build_authoring_plan(
            session,
            _request(),
            _concept("99-100"),
            AuthoringPlanRequest(
                method="skeleton_fill", mechanism="skill", prep_model="sonnet"
            ),
        )


def test_eligibility_warnings_flags_haiku_on_hard_band() -> None:
    """haiku + a 10-13/13-16/16+ band skeleton_fill gets a non-blocking warning."""
    warnings = eligibility_warnings("skeleton_fill", "skill", "13-16", "haiku")
    assert len(warnings) == 1
    assert "haiku" in warnings[0]


def test_eligibility_warnings_silent_for_stronger_model() -> None:
    """The same band with opus produces no warning."""
    assert eligibility_warnings("skeleton_fill", "skill", "13-16", "opus") == []


def test_eligibility_warnings_silent_for_easy_band() -> None:
    """haiku on an easy band (8-11) produces no warning."""
    assert eligibility_warnings("skeleton_fill", "skill", "8-11", "haiku") == []
