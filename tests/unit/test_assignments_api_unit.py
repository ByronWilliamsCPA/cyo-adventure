"""Unit tests for the assignments API handlers and schemas (no DB, no ASGI)."""

from __future__ import annotations

import pytest

from cyo_adventure.api.schemas import AssignmentCreateBody, AssignmentListView


class TestAssignmentSchemas:
    @pytest.mark.unit
    def test_create_body_requires_at_least_one_profile(self) -> None:
        """An empty profile_ids list is rejected."""
        with pytest.raises(ValueError, match="profile_ids"):
            AssignmentCreateBody(profile_ids=[])

    @pytest.mark.unit
    def test_create_body_forbids_extra_fields(self) -> None:
        """Unknown fields are rejected (extra='forbid')."""
        with pytest.raises(ValueError, match="Extra inputs"):
            AssignmentCreateBody.model_validate({"profile_ids": ["a"], "surprise": 1})

    @pytest.mark.unit
    def test_list_view_round_trips(self) -> None:
        """The list view carries the storybook id and profile ids."""
        view = AssignmentListView(storybook_id="s1", profile_ids=["p1", "p2"])
        assert view.storybook_id == "s1"
        assert view.profile_ids == ["p1", "p2"]
