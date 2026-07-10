"""Unit tests for anchor-context extraction (WS-B PR 3)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.story_requests.anchoring import (
    _protagonist_names,
    anchor_context_from_blob,
    load_anchor_context,
)


def _blob() -> dict[str, object]:
    return {
        "title": "The Fox and the Map",
        "nodes": [
            {"id": "n1", "body": "You set off.", "is_ending": False},
            {
                "id": "n2",
                "body": "You find the treasure and share it with the village.",
                "is_ending": True,
                "ending": {"id": "e1", "title": "Treasure shared"},
            },
            {
                "id": "n3",
                "body": "You head home for supper.",
                "is_ending": True,
                "ending": {"id": "e2", "title": "Home again"},
            },
        ],
    }


def test_extracts_title_names_and_ending_excerpts() -> None:
    ctx = anchor_context_from_blob(_blob(), character_names=["Robin"])
    assert ctx.title == "The Fox and the Map"
    assert ctx.character_names == ["Robin"]
    assert "Treasure shared: You find the treasure" in ctx.ending_summary
    assert "Home again" in ctx.ending_summary


def test_caps_excerpt_count_and_length() -> None:
    """Pins the 3-excerpt count cap via the " | " separator count.

    The per-excerpt 150-char cap is pinned independently by
    test_single_ending_excerpt_is_capped_at_150_chars; this test only needs to
    prove the _MAX_ENDING_EXCERPTS=3 cap holds when more than 3 ending nodes
    are present.
    """
    blob = _blob()
    nodes = blob["nodes"]
    assert isinstance(nodes, list)
    for i in range(5):
        nodes.append(
            {
                "id": f"x{i}",
                "body": "y" * 500,
                "is_ending": True,
                "ending": {"id": f"ex{i}", "title": "Long"},
            }
        )
    ctx = anchor_context_from_blob(blob, character_names=[])
    # 3 excerpts joined by " | " means exactly 2 separators; pins the count
    # cap independent of the per-excerpt cap (pinned separately above).
    assert ctx.ending_summary.count(" | ") == 2
    # With per-excerpt caps of 150 chars and at most 3 excerpts, the maximum
    # possible summary length is 3 * 150 + 2 * len(" | ") = 456, well under
    # the outer 600-char slice. The outer 600 cap is a defensive backstop
    # that cannot fire under the current constants, so this pins the real,
    # reachable bound instead of fabricating a scenario for the unreachable
    # outer cap.
    assert len(ctx.ending_summary) <= 456


def test_single_ending_excerpt_is_capped_at_150_chars() -> None:
    """A single long ending pins the 150-char per-excerpt cap on its own.

    With only one excerpt the " | " join contributes nothing and the outer
    600-char slice never engages (150 < 600), so a summary length of exactly
    150 can only be explained by the per-excerpt cap firing.
    """
    blob = {
        "title": "T",
        "nodes": [
            {
                "id": "n1",
                "body": "m" * 144 + "OVERFLOW",
                "is_ending": True,
                "ending": {"id": "e1", "title": "Long"},
            }
        ],
    }
    ctx = anchor_context_from_blob(blob, character_names=[])
    assert ctx.ending_summary == "Long: " + "m" * 144
    assert len(ctx.ending_summary) == 150
    assert "OVERFLOW" not in ctx.ending_summary


def test_malformed_blob_degrades_to_defaults() -> None:
    ctx = anchor_context_from_blob(
        {"title": 7, "nodes": "not-a-list"}, character_names=[]
    )
    assert ctx.title == "Untitled story"
    assert ctx.ending_summary == ""


def _mock_session() -> AsyncSession:
    """Build an AsyncSession double via spec= so async methods auto-mock.

    ``MagicMock(spec=AsyncSession)`` produces ``AsyncMock`` instances for the
    async members (``get``, ``scalar``) automatically, so ``await
    mock_session.scalar(...)`` is awaitable without hand-wiring each method.
    """
    return MagicMock(spec=AsyncSession)


@pytest.mark.asyncio
async def test_load_anchor_context_storybook_missing_returns_none() -> None:
    """A None session.get result (no such storybook) degrades to None."""
    session = _mock_session()
    session.get = AsyncMock(return_value=None)

    result = await load_anchor_context(session, "s_missing")

    assert result is None


@pytest.mark.asyncio
async def test_load_anchor_context_no_published_version_returns_none() -> None:
    """A storybook with no current_published_version degrades to None."""
    session = _mock_session()
    storybook = SimpleNamespace(id="s_1", current_published_version=None)
    session.get = AsyncMock(return_value=storybook)

    result = await load_anchor_context(session, "s_1")

    assert result is None


@pytest.mark.asyncio
async def test_load_anchor_context_version_row_missing_returns_none() -> None:
    """A published version pointer with no matching version row degrades to None."""
    session = _mock_session()
    storybook = SimpleNamespace(id="s_1", current_published_version=1)
    session.get = AsyncMock(return_value=storybook)
    session.scalar = AsyncMock(return_value=None)

    result = await load_anchor_context(session, "s_1")

    assert result is None


@pytest.mark.asyncio
async def test_load_anchor_context_non_dict_blob_returns_none() -> None:
    """A version row whose blob is not a dict degrades to None."""
    session = _mock_session()
    storybook = SimpleNamespace(id="s_1", current_published_version=1)
    version = SimpleNamespace(blob="not-a-dict")
    session.get = AsyncMock(return_value=storybook)
    session.scalar = AsyncMock(return_value=version)

    result = await load_anchor_context(session, "s_1")

    assert result is None


@pytest.mark.asyncio
async def test_load_anchor_context_happy_path_returns_context() -> None:
    """A valid published anchor with a dict blob builds a real AnchorContext.

    The two sequential ``session.scalar`` calls (version lookup inside
    ``load_anchor_context``, then the concept-brief lookup inside its own
    ``_protagonist_names`` call) are ordered via ``side_effect``.
    """
    session = _mock_session()
    storybook = SimpleNamespace(id="s_1", current_published_version=1)
    version = SimpleNamespace(blob=_blob())
    session.get = AsyncMock(return_value=storybook)
    session.scalar = AsyncMock(
        side_effect=[version, {"protagonist": {"name": "Robin"}}]
    )

    result = await load_anchor_context(session, "s_1")

    assert result is not None
    assert result.title == "The Fox and the Map"
    assert result.character_names == ["Robin"]


@pytest.mark.asyncio
async def test_protagonist_names_brief_not_dict_returns_empty() -> None:
    """A non-dict (or missing) concept brief degrades to an empty list."""
    session = _mock_session()
    session.scalar = AsyncMock(return_value=None)

    names = await _protagonist_names(session, "s_1")

    assert names == []


@pytest.mark.asyncio
async def test_protagonist_names_protagonist_not_dict_returns_empty() -> None:
    """A brief whose 'protagonist' key is not a dict degrades to an empty list."""
    session = _mock_session()
    session.scalar = AsyncMock(return_value={"protagonist": "not-a-dict"})

    names = await _protagonist_names(session, "s_1")

    assert names == []


@pytest.mark.asyncio
async def test_protagonist_names_name_key_missing_returns_empty() -> None:
    """A protagonist dict with no 'name' key degrades to an empty list."""
    session = _mock_session()
    session.scalar = AsyncMock(return_value={"protagonist": {}})

    names = await _protagonist_names(session, "s_1")

    assert names == []


@pytest.mark.asyncio
async def test_protagonist_names_empty_name_returns_empty() -> None:
    """A protagonist dict with an empty-string name degrades to an empty list."""
    session = _mock_session()
    session.scalar = AsyncMock(return_value={"protagonist": {"name": ""}})

    names = await _protagonist_names(session, "s_1")

    assert names == []


@pytest.mark.asyncio
async def test_protagonist_names_valid_name_returns_single_name() -> None:
    """A protagonist dict with a valid non-empty name returns that name."""
    session = _mock_session()
    session.scalar = AsyncMock(return_value={"protagonist": {"name": "Zara"}})

    names = await _protagonist_names(session, "s_1")

    assert names == ["Zara"]


def test_extracts_variable_names_from_blob() -> None:
    blob = _blob()
    blob["variables"] = [
        {"name": "courage", "type": "int", "initial": 0, "min": 0, "max": 5},
        {"name": "has_lantern", "type": "bool", "initial": False},
    ]
    ctx = anchor_context_from_blob(blob, character_names=[])
    assert ctx.variable_names == ["courage", "has_lantern"]


def test_variable_names_default_empty_when_absent() -> None:
    ctx = anchor_context_from_blob(_blob(), character_names=[])
    assert ctx.variable_names == []


def test_malformed_variables_degrade_not_raise() -> None:
    blob = _blob()
    blob["variables"] = [
        "not_a_dict",
        {"name": 7},
        {"name": ""},
        {"type": "int"},
        {"name": "kindness", "type": "int", "initial": 1},
    ]
    ctx = anchor_context_from_blob(blob, character_names=[])
    assert ctx.variable_names == ["kindness"]


def test_variable_names_capped_at_ten() -> None:
    blob = _blob()
    blob["variables"] = [
        {"name": f"var_{i:02d}", "type": "bool", "initial": False} for i in range(12)
    ]
    ctx = anchor_context_from_blob(blob, character_names=[])
    assert len(ctx.variable_names) == 10
    assert ctx.variable_names[0] == "var_00"


def test_overlong_variable_name_is_truncated_not_rejected() -> None:
    """A malformed blob must degrade, not raise: 200 chars is _BoundedText's cap."""
    blob = _blob()
    blob["variables"] = [{"name": "x" * 500, "type": "bool", "initial": False}]
    ctx = anchor_context_from_blob(blob, character_names=[])
    assert ctx.variable_names == ["x" * 200]
