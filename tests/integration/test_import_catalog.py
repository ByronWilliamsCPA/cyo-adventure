"""DB-backed integration tests for the catalog batch importer.

Uses a small, deliberately-chosen subset of the real 25-entry manifest (the
3 legacy-shape files, one plain current-shape file, and the 2 id_suffix
pilot variants) rather than the full batch, to keep the suite fast: several
manifest entries (Harrowstone Keep, Sunken Temple, Ashfall Expedition) are
500+ node gamebooks not needed to exercise this module's own logic.

``settings.generation_provider`` defaults to "mock" (core/config.py) and
nothing in this test suite overrides it, so ``import_filled_story``'s
internal ``run_moderation_pipeline`` call never makes a live LLM call here.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import cyo_adventure.generation.import_catalog as import_catalog_module
from cyo_adventure.db.models import CATALOG_FAMILY_ID, Storybook, StorybookVersion
from cyo_adventure.generation.import_catalog import (
    CATALOG_ENTRIES,
    CatalogEntry,
    ImportConfig,
    import_catalog,
)
from cyo_adventure.generation.import_story import ImportRequest
from cyo_adventure.generation.import_story import import_filled_story as _real_import

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _entry(title: str) -> CatalogEntry:
    """Return the CATALOG_ENTRIES row with the given title, or raise."""
    for entry in CATALOG_ENTRIES:
        if entry.title == title:
            return entry
    msg = f"no CATALOG_ENTRIES row titled {title!r}"
    raise AssertionError(msg)


_CLOVER = _entry("Clover and the Butterfly")
_LOST_MITTEN = _entry("The Lost Mitten")
_CLOCKTOWER_CIPHER = _entry("The Clocktower Cipher")
_SUNKEN_SIGNAL = _entry("The Sunken Signal")
_PILOT_DINO_DIG = _entry("The Cave of Echoes (dino-dig)")
_PILOT_SPACE_STATION = _entry("The Cave of Echoes (space-station)")


async def test_import_catalog_imports_a_small_entry_and_is_idempotent(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    config = ImportConfig(repo_root=_REPO_ROOT)

    first = await import_catalog(sessions, config, entries=(_CLOVER,))
    assert len(first) == 1
    assert first[0].outcome == "imported"
    assert first[0].story_id is not None

    async with sessions() as session:
        book = await session.get(Storybook, first[0].story_id)
        assert book is not None
        assert book.family_id == CATALOG_FAMILY_ID
        assert book.status in {"in_review", "needs_revision"}

    second = await import_catalog(sessions, config, entries=(_CLOVER,))
    assert len(second) == 1
    assert second[0].outcome == "skipped_existing"
    assert second[0].story_id == first[0].story_id


async def test_import_catalog_imports_all_three_legacy_entries_end_to_end(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The 3 documented legacy-shape files import cleanly through the full path.

    Regression for the normalization recipe (_normalize_legacy_fill): proves
    it survives not just run_gate() in isolation (see the unit-test
    parametrized coverage) but the entire import_filled_story path, including
    persistence and moderation, against the real files.
    """
    entries = (_LOST_MITTEN, _CLOCKTOWER_CIPHER, _SUNKEN_SIGNAL)
    config = ImportConfig(repo_root=_REPO_ROOT)

    outcomes = await import_catalog(sessions, config, entries=entries)

    assert len(outcomes) == 3
    for entry, outcome in zip(entries, outcomes, strict=True):
        assert outcome.outcome == "imported", (entry.title, outcome.detail)

    async with sessions() as session:
        for entry, outcome in zip(entries, outcomes, strict=True):
            book = await session.get(Storybook, outcome.story_id)
            assert book is not None, entry.title
            assert book.family_id == CATALOG_FAMILY_ID


async def test_import_catalog_isolates_a_bad_entry_from_the_rest(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    bad_entry = CatalogEntry(
        "Nonexistent Story",
        "out/does-not-exist.filled.json",
        "8-11",
        "does-not-exist",
    )
    config = ImportConfig(repo_root=_REPO_ROOT)

    outcomes = await import_catalog(sessions, config, entries=(bad_entry, _CLOVER))

    assert len(outcomes) == 2
    assert outcomes[0].outcome == "error"
    assert outcomes[0].story_id is None
    assert outcomes[1].outcome == "imported"

    async with sessions() as session:
        book = await session.get(Storybook, outcomes[1].story_id)
        assert book is not None


async def test_import_catalog_survives_an_integrity_error_and_continues(
    sessions: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A PK-violation IntegrityError on one entry is reported, not fatal.

    Regression for the #CRITICAL/#ASSUME notes on _persist_and_classify and
    _import_one: a concurrent second run of this batch script could pass the
    pre-check ``session.get(Storybook, story_id)`` None check and then race
    on the Storybook PK insert, raising sqlalchemy.exc.IntegrityError (not a
    ProjectBaseError). Before the fix, that exception was uncaught and
    propagated out of import_catalog(), aborting the whole batch before
    _print_summary ever ran. A genuine concurrent race is not deterministic
    to reproduce, so this forces the same failure mode directly: patches
    import_filled_story (as import_catalog.py imports it) to raise
    IntegrityError for exactly one entry, delegating to the real
    implementation for every other call, and asserts the batch still
    completes and classifies the failed entry as "error" while the
    following entry still imports normally.
    """
    raised = {"count": 0}

    async def _flaky_import(session: AsyncSession, request: ImportRequest) -> str:
        raised["count"] += 1
        if raised["count"] == 1:
            raise IntegrityError(
                "INSERT INTO storybook (id, family_id, status) VALUES (...)",
                {},
                Exception(
                    'duplicate key value violates unique constraint "storybook_pkey"'
                ),
            )
        return await _real_import(session, request)

    monkeypatch.setattr(import_catalog_module, "import_filled_story", _flaky_import)

    config = ImportConfig(repo_root=_REPO_ROOT)
    outcomes = await import_catalog(sessions, config, entries=(_CLOVER, _LOST_MITTEN))

    assert len(outcomes) == 2
    assert outcomes[0].outcome == "error"
    assert "duplicate key" in outcomes[0].detail
    assert outcomes[1].outcome == "imported"

    async with sessions() as session:
        # The failed entry must not have left a partial row behind.
        assert outcomes[0].story_id is not None
        assert await session.get(Storybook, outcomes[0].story_id) is None
        book = await session.get(Storybook, outcomes[1].story_id)
        assert book is not None


async def test_import_catalog_threads_family_and_skeleton_slug(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    config = ImportConfig(repo_root=_REPO_ROOT)

    outcomes = await import_catalog(sessions, config, entries=(_CLOVER,))
    story_id = outcomes[0].story_id
    assert story_id is not None

    async with sessions() as session:
        book = await session.get(Storybook, story_id)
        assert book is not None
        assert book.family_id == CATALOG_FAMILY_ID

        version = await session.scalar(
            select(StorybookVersion).where(
                StorybookVersion.storybook_id == story_id,
                StorybookVersion.version == 1,
            )
        )
        assert version is not None
        assert version.skeleton_slug == _CLOVER.skeleton_slug
        assert version.model == config.model
        assert version.prompt_version == config.prompt_version


async def test_import_catalog_pilot_variants_get_distinct_story_ids(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    config = ImportConfig(repo_root=_REPO_ROOT)

    outcomes = await import_catalog(
        sessions, config, entries=(_PILOT_DINO_DIG, _PILOT_SPACE_STATION)
    )

    assert len(outcomes) == 2
    assert outcomes[0].outcome == "imported"
    assert outcomes[1].outcome == "imported"
    assert outcomes[0].story_id == "sk_cave_of_echoes__dino-dig"
    assert outcomes[1].story_id == "sk_cave_of_echoes__space-station"
    assert outcomes[0].story_id != outcomes[1].story_id

    async with sessions() as session:
        first = await session.get(Storybook, outcomes[0].story_id)
        second = await session.get(Storybook, outcomes[1].story_id)
        assert first is not None
        assert second is not None
        assert first.id != second.id
