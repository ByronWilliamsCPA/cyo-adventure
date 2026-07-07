"""Unit tests for the reusable persist_storybook helper.

Verifies that the helper creates exactly one Storybook row and one
StorybookVersion row, stamps the story id onto the blob, and returns
the story id. Uses a minimal fake session so no database is required.
"""

from __future__ import annotations

import json
import uuid

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.generation.persistence import (
    _MAX_BLOB_BYTES,
    StorybookParams,
    persist_storybook,
)


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

    params = StorybookParams(
        story_id="s_demo",
        blob=blob,
        family_id=family_id,
        model="opus-4.8",
        prompt_version="skeleton-fill-v1",
        provider="anthropic",
    )
    story_id = await persist_storybook(session, params)

    assert story_id == "s_demo"
    books = _added(session, Storybook)
    versions = _added(session, StorybookVersion)
    assert len(books) == 1
    assert books[0].id == "s_demo"
    assert books[0].family_id == family_id
    assert books[0].status == "draft"
    assert len(versions) == 1
    assert versions[0].storybook_id == "s_demo"
    assert versions[0].version == 1
    assert versions[0].blob["id"] == "s_demo"
    assert versions[0].model == "opus-4.8"
    assert versions[0].prompt_version == "skeleton-fill-v1"
    assert versions[0].provider == "anthropic"


# ---------------------------------------------------------------------------
# Byte-size guard on the stored blob/report (audit Finding 12)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_rejects_oversized_blob() -> None:
    """A blob whose stamped serialized size exceeds the cap is rejected."""
    session = _FakeSession()
    blob = {
        "id": "ignored",
        "title": "T",
        "nodes": [],
        "pad": "x" * (_MAX_BLOB_BYTES + 1),
    }
    params = StorybookParams(story_id="s_big", blob=blob, family_id=uuid.uuid4())

    with pytest.raises(ValidationError):
        await persist_storybook(session, params)
    # No row must be added ahead of the size check.
    assert session.added == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_accepts_blob_at_byte_limit() -> None:
    """A blob whose stamped serialized size is exactly at the cap is accepted."""
    session = _FakeSession()
    story_id = "s_ok"
    skeleton = {"id": story_id, "title": "T", "nodes": [], "pad": ""}
    base_size = len(json.dumps(skeleton))
    padding = "x" * (_MAX_BLOB_BYTES - base_size)
    blob = {"id": "ignored", "title": "T", "nodes": [], "pad": padding}
    params = StorybookParams(story_id=story_id, blob=blob, family_id=uuid.uuid4())

    result = await persist_storybook(session, params)

    assert result == story_id
    versions = _added(session, StorybookVersion)
    assert len(json.dumps(versions[0].blob)) == _MAX_BLOB_BYTES


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_rejects_oversized_validation_report() -> None:
    """A validation_report over the byte cap is rejected before any row is added."""
    session = _FakeSession()
    blob = {"id": "ignored", "title": "T", "nodes": []}
    params = StorybookParams(
        story_id="s_report",
        blob=blob,
        family_id=uuid.uuid4(),
        validation_report={"pad": "x" * (_MAX_BLOB_BYTES + 1)},
    )

    with pytest.raises(ValidationError):
        await persist_storybook(session, params)
    assert session.added == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_accepts_validation_report_at_byte_limit() -> None:
    """A validation_report exactly at the byte cap is accepted."""
    session = _FakeSession()
    skeleton = {"pad": ""}
    base_size = len(json.dumps(skeleton))
    padding = "x" * (_MAX_BLOB_BYTES - base_size)
    params = StorybookParams(
        story_id="s_report_ok",
        blob={"id": "ignored", "title": "T", "nodes": []},
        family_id=uuid.uuid4(),
        validation_report={"pad": padding},
    )

    result = await persist_storybook(session, params)

    assert result == "s_report_ok"
