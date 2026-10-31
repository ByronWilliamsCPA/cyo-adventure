"""Unit tests for the ring-2 subject guard in the personalization values route.

``_book_subject_ring2_view`` has two defensive branches the integration suite
cannot reach through the database: a subject row that the FK should have
cleared, and a subject who already lives in the caller's household.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from cyo_adventure.api import personalization as api


def _book(*, family_id: uuid.UUID, subject_id: uuid.UUID | None) -> Any:
    return SimpleNamespace(
        id="story_1",
        family_id=family_id,
        personalization_subject_profile_id=subject_id,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ring2_view_missing_subject_row_falls_back_and_logs() -> None:
    """A dangling subject id (FK absent from the schema) yields no ring-2 view."""
    session = AsyncMock()
    session.get.return_value = None
    book = _book(family_id=uuid.uuid4(), subject_id=uuid.uuid4())

    with patch.object(api, "_logger") as logger:
        result = await api._book_subject_ring2_view(
            cast("Any", session), book, uuid.uuid4()
        )

    assert result is None
    logger.warning.assert_called_once()
    assert logger.warning.call_args.args[0] == "personalization.subject_profile_missing"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ring2_view_subject_in_callers_household_is_not_ring2() -> None:
    """A subject who moved into the caller's family is not a ring-2 disclosure."""
    caller_family = uuid.uuid4()
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(family_id=caller_family)
    book = _book(family_id=uuid.uuid4(), subject_id=uuid.uuid4())

    with patch.object(api, "_resolve_ring2_view", new=AsyncMock()) as resolve:
        result = await api._book_subject_ring2_view(
            cast("Any", session), book, caller_family
        )

    assert result is None
    resolve.assert_not_called()
