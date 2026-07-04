"""Unit tests for cross-module invariants in cyo_adventure.api.schemas.

These pin drift between response-model type aliases and the DB CHECK
constraints they claim to mirror; the two are independently hand-maintained
and nothing else ties them together.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import get_args

from cyo_adventure.api.schemas import JobStatusLiteral, StoryRequestStatus
from cyo_adventure.db.models import (
    _GENERATION_JOB_STATUS_VALUES,  # pyright: ignore[reportPrivateUsage]
    _STORY_REQUEST_STATUS_VALUES,  # pyright: ignore[reportPrivateUsage]
)


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
