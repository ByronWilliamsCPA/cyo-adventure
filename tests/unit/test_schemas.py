"""Unit tests for cross-module invariants in cyo_adventure.api.schemas.

These pin drift between response-model type aliases and the DB CHECK
constraints they claim to mirror; the two are independently hand-maintained
and nothing else ties them together.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import get_args

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.api.schemas import (
    PATH_MAX_LENGTH,
    VISIT_SET_MAX_LENGTH,
    FindingView,
    FlaggedPassage,
    GuardianBookItem,
    JobStatusLiteral,
    ReadingStateBody,
    ReviewSurfaceView,
    StoryRequestStatus,
)
from cyo_adventure.db.models import (
    _GENERATION_JOB_STATUS_VALUES,  # pyright: ignore[reportPrivateUsage]
    _STORY_REQUEST_STATUS_VALUES,  # pyright: ignore[reportPrivateUsage]
)
from cyo_adventure.moderation.report import Source, Verdict


def _reading_state(**overrides: object) -> dict[str, object]:
    """Return a minimal valid ReadingStateBody payload, with overrides applied."""
    base: dict[str, object] = {
        "version": 1,
        "current_node": "n1",
        "state_revision": 0,
    }
    base.update(overrides)
    return base


def test_job_status_literal_matches_db_constraint() -> None:
    """JobStatusLiteral's values must match the ck_generation_job_status CHECK.

    ``_GENERATION_JOB_STATUS_VALUES`` is a single-quoted, comma-separated SQL
    fragment (e.g. ``"'queued', 'running', ..."``); parse it back into bare
    strings rather than duplicating the list a second time in this test.
    """
    db_values = {
        value.strip().strip("'") for value in _GENERATION_JOB_STATUS_VALUES.split(",")
    }
    literal_values = set(get_args(JobStatusLiteral))
    assert literal_values == db_values, (
        "JobStatusLiteral has drifted from the ck_generation_job_status CHECK "
        f"constraint: literal={literal_values!r} db={db_values!r}"
    )


def test_story_request_status_literal_matches_db_constraint() -> None:
    """StoryRequestStatus's values must match the ck_story_request_status CHECK.

    ``_STORY_REQUEST_STATUS_VALUES`` is a single-quoted, comma-separated SQL
    fragment (e.g. ``"'pending', 'approved', ..."``); parse it back into bare
    strings rather than duplicating the list a second time in this test.
    """
    db_values = {
        value.strip().strip("'") for value in _STORY_REQUEST_STATUS_VALUES.split(",")
    }
    literal_values = set(get_args(StoryRequestStatus))
    assert literal_values == db_values, (
        "StoryRequestStatus has drifted from the ck_story_request_status CHECK "
        f"constraint: literal={literal_values!r} db={db_values!r}"
    )


def test_generation_job_list_item_has_no_report_field() -> None:
    """The list item must not carry the raw report column (ADR-007 safety)."""
    from cyo_adventure.api.schemas import GenerationJobListItem

    assert "report" not in GenerationJobListItem.model_fields


def test_generation_job_list_item_round_trips() -> None:
    """A minimal list item serializes with the label fields and no report."""
    from cyo_adventure.api.schemas import GenerationJobListItem

    item = GenerationJobListItem(
        id="j1",
        status="queued",
        storybook_id=None,
        storybook_status=None,
        version=None,
        error=None,
        title="The Cave",
        premise_snippet="A hero enters a cave.",
        age_band="8-11",
        created_at="2026-07-02T00:00:00Z",
    )
    assert item.created_at == datetime(2026, 7, 2, tzinfo=UTC)
    dumped = item.model_dump()
    assert "report" not in dumped
    assert dumped["age_band"] == "8-11"


# ---------------------------------------------------------------------------
# ReadingStateBody resource bounds (audit Finding 8)
# ---------------------------------------------------------------------------


def test_path_at_max_length_accepted() -> None:
    """A path exactly at the cap is accepted."""
    body = ReadingStateBody(**_reading_state(path=["n"] * PATH_MAX_LENGTH))
    assert len(body.path) == PATH_MAX_LENGTH


def test_path_over_max_length_rejected() -> None:
    """A path one entry over the cap is rejected (422 at the API boundary)."""
    with pytest.raises(PydanticValidationError):
        ReadingStateBody(**_reading_state(path=["n"] * (PATH_MAX_LENGTH + 1)))


def test_visit_set_at_max_length_accepted() -> None:
    """A visit_set exactly at the cap is accepted."""
    body = ReadingStateBody(
        **_reading_state(visit_set=[f"n{i}" for i in range(VISIT_SET_MAX_LENGTH)])
    )
    assert len(body.visit_set) == VISIT_SET_MAX_LENGTH


def test_visit_set_over_max_length_rejected() -> None:
    """A visit_set one entry over the cap is rejected."""
    with pytest.raises(PydanticValidationError):
        ReadingStateBody(
            **_reading_state(
                visit_set=[f"n{i}" for i in range(VISIT_SET_MAX_LENGTH + 1)]
            )
        )


def test_save_slots_at_byte_budget_accepted() -> None:
    """A save_slots payload serializing to exactly the byte cap is accepted."""
    # Build a single string value that pads the serialized dict to exactly
    # 64_000 bytes so the boundary itself is exercised.
    skeleton = json.dumps({"pad": ""})
    padding = "x" * (64_000 - len(skeleton))
    body = ReadingStateBody(**_reading_state(save_slots={"pad": padding}))
    assert len(json.dumps(body.save_slots)) == 64_000


def test_save_slots_over_byte_budget_rejected() -> None:
    """A save_slots payload over the 64_000-byte cap is rejected."""
    with pytest.raises(PydanticValidationError):
        ReadingStateBody(**_reading_state(save_slots={"pad": "x" * 64_001}))


# ---------------------------------------------------------------------------
# GuardianBookItem._unscreened_has_no_flags (Task 2.2 redacted content badge)
# ---------------------------------------------------------------------------


def _guardian_book_item(**overrides: object) -> dict[str, object]:
    """Return a minimal valid GuardianBookItem payload, with overrides applied."""
    base: dict[str, object] = {
        "storybook_id": "sb1",
        "title": "The Cave",
        "version": 1,
        "age_band": "8-11",
        "screened": True,
        "flagged_count": 0,
        "assigned_profile_ids": [],
        "visibility": "family",
    }
    base.update(overrides)
    return base


def test_guardian_book_item_screened_with_flags_accepted() -> None:
    """A screened book reporting flagged passages is a valid, coherent badge."""
    item = GuardianBookItem(**_guardian_book_item(screened=True, flagged_count=3))
    assert item.screened is True
    assert item.flagged_count == 3


def test_guardian_book_item_unscreened_with_zero_flags_accepted() -> None:
    """An unscreened book reporting zero flags is the expected degrade state."""
    item = GuardianBookItem(**_guardian_book_item(screened=False, flagged_count=0))
    assert item.screened is False
    assert item.flagged_count == 0


def test_guardian_book_item_unscreened_with_flags_rejected() -> None:
    """An unscreened badge that also reports flagged passages is contradictory."""
    with pytest.raises(
        PydanticValidationError,
        match="an unscreened book cannot report flagged passages",
    ):
        GuardianBookItem(**_guardian_book_item(screened=False, flagged_count=1))


# ---------------------------------------------------------------------------
# ReviewSurfaceView._no_pass_verdict_leaks (C3-4 guardian review surface)
# ---------------------------------------------------------------------------


def _finding_view(**overrides: object) -> dict[str, object]:
    """Return a minimal valid FindingView payload, with overrides applied."""
    base: dict[str, object] = {
        "stage": 1,
        "source": Source.LLM_SAFETY,
        "category": "violence",
        "node_id": "n1",
        "verdict": Verdict.FLAG,
        "score": 0.6,
        "message": "flagged for review",
    }
    base.update(overrides)
    return base


def _review_surface_view(**overrides: object) -> dict[str, object]:
    """Return a minimal valid ReviewSurfaceView payload, with overrides applied."""
    base: dict[str, object] = {
        "storybook_id": "sb1",
        "version": 1,
        "status": "in_review",
        "blob": {},
        "screened": True,
        "summary": None,
        "flagged_passages": [],
        "story_level_findings": [],
    }
    base.update(overrides)
    return base


def test_review_surface_view_flag_verdicts_accepted() -> None:
    """A surface carrying only flag/block findings is a valid review surface."""
    passage = FlaggedPassage(
        node_id="n1",
        prose="Once upon a time.",
        findings=[FindingView(**_finding_view(verdict=Verdict.FLAG))],
    )
    view = ReviewSurfaceView(
        **_review_surface_view(
            flagged_passages=[passage],
            story_level_findings=[FindingView(**_finding_view(verdict=Verdict.BLOCK))],
        )
    )
    assert len(view.flagged_passages) == 1
    assert view.story_level_findings[0].verdict is Verdict.BLOCK


def test_review_surface_view_pass_verdict_in_passage_rejected() -> None:
    """A pass-verdict finding inside a flagged passage must not leak through."""
    passage = FlaggedPassage(
        node_id="n1",
        prose="Once upon a time.",
        findings=[FindingView(**_finding_view(verdict=Verdict.PASS))],
    )
    with pytest.raises(
        PydanticValidationError,
        match="review surface must not contain a pass-verdict finding",
    ):
        ReviewSurfaceView(**_review_surface_view(flagged_passages=[passage]))


def test_review_surface_view_pass_verdict_in_story_level_rejected() -> None:
    """A pass-verdict story-level finding must not leak through either."""
    with pytest.raises(
        PydanticValidationError,
        match="review surface must not contain a pass-verdict finding",
    ):
        ReviewSurfaceView(
            **_review_surface_view(
                story_level_findings=[
                    FindingView(**_finding_view(verdict=Verdict.PASS))
                ]
            )
        )
