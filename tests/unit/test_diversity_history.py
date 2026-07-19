"""Unit tests for diversity.history: the impure family-history loader.

Uses a minimal mock AsyncSession, mirroring the ``_FakeSession``/``_FakeResult``
pattern in ``tests/unit/test_authoring_plan.py`` (which backs
``generation.skeleton_match.recent_skeleton_usage`` the same way). No real
database or network access.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest

from cyo_adventure.diversity.history import load_family_history, load_version_blob

_Row = tuple[str, int, str | None, datetime, object, object]


class _FakeResult:
    """A canned result for the family-history query."""

    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows

    def all(self) -> list[_Row]:
        return self._rows


class _FakeSession:
    """Minimal async session double for load_family_history."""

    def __init__(self, rows: list[_Row]) -> None:
        self._rows = rows

    async def execute(self, statement: Any) -> _FakeResult:
        """Return the canned rows regardless of the compiled statement."""
        _ = statement
        return _FakeResult(self._rows)


class _FakeGetSession:
    """Minimal async session double for load_version_blob's session.get."""

    def __init__(self, row: Any) -> None:
        self._row = row

    async def get(self, model: Any, ident: Any) -> Any:
        """Return the canned row regardless of the requested model/ident."""
        _ = (model, ident)
        return self._row


@pytest.mark.unit
@pytest.mark.asyncio
async def test_family_none_returns_empty() -> None:
    """A family-less (admin/catalog) request never issues a query and gets []."""
    session = _FakeSession(rows=[])
    result = await load_family_history(session, None)  # type: ignore[arg-type]
    assert result == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_load_family_history_extracts_themes_without_full_blob() -> None:
    """A well-formed row yields a HistoryEntry with a populated theme signature."""
    created = datetime(2026, 7, 1, tzinfo=UTC)
    rows: list[_Row] = [
        (
            "book-1",
            1,
            "the-cave-of-echoes",
            created,
            {"metadata": {"themes": ["Dragon", "Courage"]}},
            {"premise": "a dragon who lost his fire"},
        ),
    ]
    session = _FakeSession(rows=rows)
    entries = await load_family_history(session, uuid.uuid4())  # type: ignore[arg-type]

    assert len(entries) == 1
    entry = entries[0]
    assert entry.storybook_id == "book-1"
    assert entry.version == 1
    assert entry.skeleton_slug == "the-cave-of-echoes"
    assert entry.created_at == created
    assert "dragon" in entry.theme_sig
    assert "courage" in entry.theme_sig


@pytest.mark.unit
@pytest.mark.asyncio
async def test_malformed_blob_degrades_to_empty_signature_not_error() -> None:
    """Missing/malformed themes or brief degrade to an empty signature, never raise."""
    created = datetime(2026, 7, 2, tzinfo=UTC)
    rows: list[_Row] = [
        ("book-2", 1, None, created, "not-a-mapping", None),
        ("book-3", 2, None, created, {"metadata": "not-a-mapping"}, {"premise": 123}),
        ("book-4", 3, None, created, {"metadata": {"themes": "not-a-list"}}, None),
        ("book-5", 4, None, created, {}, {"no_premise_field": "x"}),
    ]
    session = _FakeSession(rows=rows)
    entries = await load_family_history(session, uuid.uuid4())  # type: ignore[arg-type]

    assert len(entries) == 4
    for entry in entries:
        assert entry.theme_sig == frozenset()


class _VersionRow:
    """Minimal stand-in for a StorybookVersion row exposing only ``blob``."""

    def __init__(self, blob: dict[str, object]) -> None:
        self.blob = blob


@pytest.mark.unit
@pytest.mark.asyncio
async def test_load_version_blob_returns_blob() -> None:
    """A present row's blob is returned as-is."""
    blob = {"id": "book-1", "nodes": []}
    session = _FakeGetSession(row=_VersionRow(blob))

    result = await load_version_blob(session, "book-1", 1)  # type: ignore[arg-type]

    assert result == blob


@pytest.mark.unit
@pytest.mark.asyncio
async def test_load_version_blob_missing_row_returns_none() -> None:
    """A missing (storybook_id, version) row returns None, never raises."""
    session = _FakeGetSession(row=None)

    result = await load_version_blob(session, "book-missing", 7)  # type: ignore[arg-type]

    assert result is None
