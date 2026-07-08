"""Validation tests for the WS-B approve confirmation body."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.api.schemas import (
    StoryRequestApproveBody,
    StoryRequestAuthoredCreateBody,
    StoryRequestView,
)
from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle


def test_defaults_style_to_prose() -> None:
    body = StoryRequestApproveBody(age_band=AgeBand.BAND_8_11, length=Length.SHORT)
    assert body.narrative_style is NarrativeStyle.PROSE


def test_gamebook_allowed_for_teen_bands() -> None:
    body = StoryRequestApproveBody(
        age_band=AgeBand.BAND_13_16,
        length=Length.LONG,
        narrative_style=NarrativeStyle.GAMEBOOK,
    )
    assert body.narrative_style is NarrativeStyle.GAMEBOOK


def test_gamebook_rejected_below_teen_bands() -> None:
    with pytest.raises(PydanticValidationError, match="gamebook"):
        StoryRequestApproveBody(
            age_band=AgeBand.BAND_8_11,
            length=Length.SHORT,
            narrative_style=NarrativeStyle.GAMEBOOK,
        )


def test_length_is_required() -> None:
    with pytest.raises(PydanticValidationError):
        StoryRequestApproveBody(age_band=AgeBand.BAND_8_11)  # type: ignore[call-arg]


def test_authored_body_requires_band_length_and_text() -> None:
    with pytest.raises(PydanticValidationError):
        StoryRequestAuthoredCreateBody.model_validate({"request_text": "a turtle tale"})


def test_authored_body_rejects_gamebook_below_teen_bands() -> None:
    with pytest.raises(PydanticValidationError, match="gamebook"):
        StoryRequestAuthoredCreateBody.model_validate(
            {
                "request_text": "a turtle tale",
                "age_band": "5-8",
                "length": "short",
                "narrative_style": "gamebook",
            }
        )


def test_authored_body_accepts_optional_profile_and_family() -> None:
    body = StoryRequestAuthoredCreateBody.model_validate(
        {"request_text": "a turtle tale", "age_band": "13-16", "length": "medium"}
    )
    assert body.profile_id is None
    assert body.family_id is None
    assert body.narrative_style is NarrativeStyle.PROSE


def test_authored_body_forbids_unknown_fields() -> None:
    with pytest.raises(PydanticValidationError):
        StoryRequestAuthoredCreateBody.model_validate(
            {
                "request_text": "a turtle tale",
                "age_band": "5-8",
                "length": "short",
                "status": "approved",
            }
        )


def test_story_request_view_allows_null_profile_id() -> None:
    view = StoryRequestView.model_validate(
        {
            "id": "r1",
            "profile_id": None,
            "status": "approved",
            "request_text": "t",
            "moderation_flags": [],
            "created_at": "2026-07-08T00:00:00Z",
            "initiator_role": "guardian",
            "age_band": "5-8",
            "length": "short",
            "narrative_style": "prose",
        }
    )
    assert view.profile_id is None
