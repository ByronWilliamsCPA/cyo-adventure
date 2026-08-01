"""Unit tests for the GET /me/progress route handler (no DB, no ASGI).

Authorization plus the query-glue layer (``_build_progress_facts``); the
badge math itself is covered by ``tests/unit/test_progress_badges.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cyo_adventure.api.deps import Principal
from cyo_adventure.api.progress import _require_child_profile, get_my_progress
from cyo_adventure.core.exceptions import AuthorizationError
from cyo_adventure.db.models import Completion, Storybook, StorybookVersion

_T1 = datetime(2026, 1, 1, tzinfo=UTC)


class _FakeScalars:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows

    def __iter__(self) -> object:
        return iter(self._rows)


class _FakeSession:
    """Queue-based fake: session.scalars() drains an ordered list of results."""

    def __init__(self, queue: list[list[object]]) -> None:
        self._queue: list[list[object]] = [list(rows) for rows in queue]
        self.scalars_calls: list[object] = []

    async def scalars(self, stmt: object) -> _FakeScalars:
        self.scalars_calls.append(stmt)
        rows = self._queue.pop(0) if self._queue else []
        return _FakeScalars(rows)


def _child_principal(profile_id: uuid.UUID | None = None) -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="child",
        family_id=uuid.uuid4(),
        profile_ids=frozenset({profile_id or uuid.uuid4()}),
    )


def _guardian_principal() -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="guardian",
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
    )


def _admin_principal() -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="admin",
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
    )


@pytest.mark.unit
def test_require_child_profile_returns_singleton() -> None:
    profile_id = uuid.uuid4()
    assert _require_child_profile(_child_principal(profile_id)) == profile_id


@pytest.mark.unit
@pytest.mark.parametrize("build", [_guardian_principal, _admin_principal])
def test_require_child_profile_rejects_non_child(build: object) -> None:
    with pytest.raises(AuthorizationError):
        _require_child_profile(build())


@pytest.mark.unit
@pytest.mark.asyncio
class TestGetMyProgress:
    async def test_guardian_rejected(self) -> None:
        session = _FakeSession([])
        with pytest.raises(AuthorizationError):
            await get_my_progress(_guardian_principal(), session)

    async def test_empty_profile_returns_empty_projection(self) -> None:
        # completions, ratings, story_requests all empty -> no book/version
        # queries fire (book_ids/version_keys stay empty).
        session = _FakeSession([[], [], []])
        result = await get_my_progress(_child_principal(), session)
        assert result.badges == []
        assert result.books == []
        assert result.totals.books_finished == 0
        assert result.totals.endings_found == 0

    async def test_first_completion_earns_first_ending_badge(self) -> None:
        profile_id = uuid.uuid4()
        completion = Completion(
            child_profile_id=profile_id,
            storybook_id="story-a",
            version=1,
            ending_id="e1",
        )
        completion.found_at = _T1
        book = Storybook(id="story-a", family_id=uuid.uuid4())
        book.current_published_version = 1
        version = StorybookVersion(
            storybook_id="story-a",
            version=1,
            blob={
                "title": "Story A",
                "metadata": {"ending_count": 2},
                "nodes": [
                    {
                        "id": "n1",
                        "is_ending": True,
                        "ending": {
                            "id": "e1",
                            "valence": "positive",
                            "kind": "success",
                            "title": "Yay",
                        },
                    }
                ],
            },
        )
        # queue order: completions, ratings, story_requests, storybooks,
        # storybook_versions, (no series query: series_id is None)
        session = _FakeSession([[completion], [], [], [book], [version]])

        result = await get_my_progress(_child_principal(profile_id), session)

        badge_ids = {b.id for b in result.badges}
        assert "first_ending" in badge_ids
        assert result.books[0].storybook_id == "story-a"
        assert result.books[0].title == "Story A"
        assert result.books[0].total_endings == 2
        assert result.totals.books_finished == 1
