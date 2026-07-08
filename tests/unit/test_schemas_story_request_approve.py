"""Validation tests for the WS-B approve confirmation body."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.api.schemas import StoryRequestApproveBody
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
