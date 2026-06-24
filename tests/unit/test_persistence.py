"""Unit tests for the reusable persist_storybook helper.

Verifies that the helper creates exactly one Storybook row and one
StorybookVersion row, stamps the story id onto the blob, and returns
the story id. Uses a minimal fake session so no database is required.
"""

from __future__ import annotations

import uuid

import pytest

from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.generation.persistence import persist_storybook


class _FakeSession:
    """Captures rows added; flush is a no-op (mirrors test_worker_persistence)."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, row: object) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        return None


def _added(session: _FakeSession, kind: type) -> list[object]:
    return [r for r in session.added if isinstance(r, kind)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_creates_storybook_and_version() -> None:
    session = _FakeSession()
    family_id = uuid.uuid4()
    blob = {"id": "ignored", "title": "T", "nodes": []}

    story_id = await persist_storybook(
        session,
        story_id="s_demo",
        blob=blob,
        family_id=family_id,
        model="opus-4.8",
        prompt_version="skeleton-fill-v1",
    )

    assert story_id == "s_demo"
    books = _added(session, Storybook)
    versions = _added(session, StorybookVersion)
    assert len(books) == 1
    assert books[0].id == "s_demo"
    assert books[0].family_id == family_id
    assert len(versions) == 1
    assert versions[0].storybook_id == "s_demo"
    assert versions[0].version == 1
    assert versions[0].blob["id"] == "s_demo"
    assert versions[0].model == "opus-4.8"
