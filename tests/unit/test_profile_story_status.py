"""Unit tests for the W1.4 profile-picker "new story ready" pill projection.

Pure, DB-free tests for ``api/profiles.py::_build_story_status_view``, the
sole place that turns a caller-scoped profile id list and a "has a recent
assignment" set into the wire-ready, boolean-only response (mirrors the
``notifications/registry.py`` composer convention: no session, no ASGI).
Authorization scoping itself (which profiles the caller may see at all) is
covered by the integration suite (``tests/integration/test_profiles.py``,
``tests/integration/test_authz_matrix.py``), since it depends on the
database-backed ``_listable_profiles`` helper.
"""

from __future__ import annotations

import uuid

import pytest

from cyo_adventure.api.profiles import (  # pyright: ignore[reportPrivateUsage]
    _NEW_STORY_WINDOW,
    _build_story_status_view,
)
from cyo_adventure.api.schemas import ProfileStoryStatusView

_PROFILE_1 = uuid.uuid4()
_PROFILE_2 = uuid.uuid4()
_PROFILE_3 = uuid.uuid4()


@pytest.mark.unit
def test_new_story_window_is_seven_days() -> None:
    """Pin the fallback window at 7 days (matches the shelf's own NEW badge).

    #VERIFY: the frontend's independent constant
    (frontend/src/library/bookCardUtils.ts::NEW_BADGE_WINDOW_MS) is pinned by
    its own test suite; this only pins the backend side of the same choice.
    """
    assert _NEW_STORY_WINDOW.days == 7


@pytest.mark.unit
class TestBuildStoryStatusView:
    """Exercise the pure id-list/new-set -> view assembly directly."""

    def test_empty_profile_ids_returns_empty_statuses(self) -> None:
        result = _build_story_status_view([], set())
        assert result.statuses == []

    def test_profile_in_new_set_reads_true(self) -> None:
        result = _build_story_status_view([_PROFILE_1], {_PROFILE_1})
        assert result.statuses == [_view_of(profile_id=_PROFILE_1, has_new_story=True)]

    def test_profile_absent_from_new_set_reads_false(self) -> None:
        result = _build_story_status_view([_PROFILE_1], set())
        assert result.statuses == [_view_of(profile_id=_PROFILE_1, has_new_story=False)]

    def test_preserves_caller_order_and_mixes_true_and_false(self) -> None:
        result = _build_story_status_view(
            [_PROFILE_1, _PROFILE_2, _PROFILE_3], {_PROFILE_2}
        )
        assert [s.profile_id for s in result.statuses] == [
            str(_PROFILE_1),
            str(_PROFILE_2),
            str(_PROFILE_3),
        ]
        assert [s.has_new_story for s in result.statuses] == [False, True, False]

    def test_a_new_set_id_outside_profile_ids_is_never_surfaced(self) -> None:
        """A "new" id that is NOT in the caller-scoped list produces no row.

        #CRITICAL: security: this is the structural guarantee behind the
        endpoint's own #CRITICAL note (api/profiles.py) that a caller can
        never learn about a profile outside its own scoped set: the output
        is built by iterating ``profile_ids`` (the already-scoped input),
        never ``new_profile_ids``, so a stray id in the latter (which should
        never happen given the caller pre-filters its query, but this
        function makes no such assumption) cannot leak a phantom row.
        #VERIFY: this test.
        """
        result = _build_story_status_view([_PROFILE_1], {_PROFILE_1, _PROFILE_2})
        assert [s.profile_id for s in result.statuses] == [str(_PROFILE_1)]

    def test_response_shape_is_boolean_only(self) -> None:
        """Every view carries exactly profile_id and has_new_story, nothing else."""
        result = _build_story_status_view([_PROFILE_1], {_PROFILE_1})
        dumped = result.statuses[0].model_dump()
        assert set(dumped.keys()) == {"profile_id", "has_new_story"}


def _view_of(*, profile_id: uuid.UUID, has_new_story: bool) -> ProfileStoryStatusView:
    """Build the expected ``ProfileStoryStatusView`` for an equality assertion."""
    return ProfileStoryStatusView(
        profile_id=str(profile_id), has_new_story=has_new_story
    )
