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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_stamps_skeleton_slug_when_provided() -> None:
    session = _FakeSession()
    params = StorybookParams(
        story_id="s_demo2",
        blob={"id": "ignored", "title": "T", "nodes": []},
        family_id=uuid.uuid4(),
        provider="mock",
        skeleton_slug="the-cave-of-echoes",
    )
    await persist_storybook(session, params)

    versions = _added(session, StorybookVersion)
    assert versions[0].skeleton_slug == "the-cave-of-echoes"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_skeleton_slug_defaults_to_none() -> None:
    session = _FakeSession()
    params = StorybookParams(
        story_id="s_demo3",
        blob={"id": "ignored", "title": "T", "nodes": []},
        family_id=uuid.uuid4(),
        provider="mock",
    )
    await persist_storybook(session, params)

    versions = _added(session, StorybookVersion)
    assert versions[0].skeleton_slug is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_records_the_sentinel_manifest() -> None:
    """The manifest reaches the column; this is its only write path."""
    session = _FakeSession()
    manifest = {
        "tokens": {"n1": [{"slot_id": "hero", "value": "Explorer", "count": 2}]}
    }
    params = StorybookParams(
        story_id="s_manifest",
        blob={"id": "ignored", "title": "T", "nodes": []},
        family_id=uuid.uuid4(),
        provider="mock",
        sentinel_manifest=manifest,
    )
    await persist_storybook(session, params)

    versions = _added(session, StorybookVersion)
    assert versions[0].sentinel_manifest == manifest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_sentinel_manifest_defaults_to_none() -> None:
    """A path that ran no transform stores NULL, not an empty manifest.

    The distinction is load-bearing: NULL means "no transform ran here",
    while ``{"tokens": {}}`` would claim the transform ran and re-inserted
    nothing, which is a different fact about the document.
    """
    session = _FakeSession()
    params = StorybookParams(
        story_id="s_no_manifest",
        blob={"id": "ignored", "title": "T", "nodes": []},
        family_id=uuid.uuid4(),
        provider="mock",
    )
    await persist_storybook(session, params)

    versions = _added(session, StorybookVersion)
    assert versions[0].sentinel_manifest is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_rejects_oversized_sentinel_manifest() -> None:
    """The manifest is byte-budgeted like the other two JSONB payloads."""
    session = _FakeSession()
    oversized = {"tokens": {"n1": "x" * (_MAX_BLOB_BYTES + 1)}}
    params = StorybookParams(
        story_id="s_big_manifest",
        blob={"id": "ignored", "title": "T", "nodes": []},
        family_id=uuid.uuid4(),
        provider="mock",
        sentinel_manifest=oversized,
    )
    with pytest.raises(ValidationError, match="sentinel_manifest"):
        await persist_storybook(session, params)

    assert session.added == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_records_personalization_eligible() -> None:
    """The caller-computed eligibility flag reaches the column verbatim.

    ADR-023 Task D4: this is the ONLY write path to
    ``storybook_version.personalization_eligible``; the boolean itself is
    computed by the caller (worker.py / import_story.py), not here.
    """
    session = _FakeSession()
    params = StorybookParams(
        story_id="s_eligible",
        blob={"id": "ignored", "title": "T", "nodes": []},
        family_id=uuid.uuid4(),
        provider="mock",
        sentinel_manifest={"tokens": {}},
        personalization_eligible=True,
    )
    await persist_storybook(session, params)

    versions = _added(session, StorybookVersion)
    assert versions[0].personalization_eligible is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_personalization_eligible_defaults_to_false() -> None:
    """A caller that never sets the flag persists False, matching the column default."""
    session = _FakeSession()
    params = StorybookParams(
        story_id="s_not_eligible",
        blob={"id": "ignored", "title": "T", "nodes": []},
        family_id=uuid.uuid4(),
        provider="mock",
    )
    await persist_storybook(session, params)

    versions = _added(session, StorybookVersion)
    assert versions[0].personalization_eligible is False
