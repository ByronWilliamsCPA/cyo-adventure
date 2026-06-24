"""Unit tests for rating request schema validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cyo_adventure.api.schemas import RatingBody


def test_rating_body_accepts_valid() -> None:
    body = RatingBody(profile_id="p", storybook_id="s", value=3)
    assert body.value == 3


def test_rating_body_rejects_zero() -> None:
    with pytest.raises(ValidationError):
        RatingBody(profile_id="p", storybook_id="s", value=0)


def test_rating_body_rejects_above_five() -> None:
    with pytest.raises(ValidationError):
        RatingBody(profile_id="p", storybook_id="s", value=6)


def test_rating_body_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RatingBody(profile_id="p", storybook_id="s", value=3, surprise="x")
