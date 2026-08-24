"""Unit tests for cyo_adventure.moderation.personalizable_slots.

Covers `personalizable_slot_fields_for_story` (ADR-023 Stage C, Task C0c):
the story-scoped slot-id-to-personalization-field resolver the
personalization-values route needs. It shares its provenance chain
(`GenerationJob` by `storybook_id`, then `resolve_skeleton_path` plus
`load_skeleton` plus `load_contract_for`, via the `_contract_for_job` helper
extracted for this task) with the existing `personalizable_slot_ids_for_story`.

SUBSTITUTION (ADR-023 Stage C, Task C0a step 3): this plan named
`tests/unit/test_personalizable_slots.py` as a guess for this module's
filename, and it did not exist. It also did not exist as an indirect home
for `personalizable_slot_ids_for_story` coverage: that function is exercised
only via tests/unit/test_moderation_pipeline.py (its `personalizable_slot_ids_for_job`
cases and the `run_moderation_pipeline`-layer resolver-spy cases) and
tests/unit/test_resume_manual_fill_personalizable_slots.py (the resume path).
Per the plan's own fallback instruction, this file is created fresh and
mirrors those two donor modules' patterns rather than seeding a real
skeleton-with-personalizable-contract through a live database: no `session`
fixture backed by a real `AsyncSession`/Postgres exists in this test tier
(org testing standard 4.2/4.3, restated in test_moderation_pipeline.py's own
module docstring: "the DB session (spec'd AsyncMock; no live database in
unit tests)"). The `GenerationJob` SELECT here is doubled with the shared
spec'd `mock_async_session` fixture (tests/unit/conftest.py); where a real
contract is needed, `resolve_skeleton_path`/`load_skeleton` are monkeypatched
onto this module while `load_contract_for` is left real, reading an actual
sidecar written to `tmp_path` -- this mirrors
test_moderation_pipeline.py's `_wire_personalizable_job` helper exactly.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from cyo_adventure.db.models import GenerationJob, StorybookVersion
from cyo_adventure.moderation import personalizable_slots as pslots_mod
from cyo_adventure.moderation.personalizable_slots import (
    personalizable_slot_fields_for_story,
    personalizable_slot_ids_for_version,
)
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.theme_contract import SlotScope, SlotSpec, ThemeContract

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.asyncio

_PERSONALIZABLE_SLUG = "themed-slug"


def _personalizable_contract() -> ThemeContract:
    """A minimal contract declaring one ``kind="personalizable"`` HERO slot.

    Same fixture shape as
    tests/unit/test_moderation_pipeline.py::_personalizable_contract and
    tests/unit/test_resume_manual_fill_personalizable_slots.py::_personalizable_contract;
    duplicated rather than imported because neither module exports it as a
    public, cross-module fixture.
    """
    return ThemeContract(
        contract_version=1,
        skeleton_slug=_PERSONALIZABLE_SLUG,
        age_band=AgeBand.BAND_8_11,
        legacy_lexicon=[],
        default_binding={"HERO": "Ada"},
        slots=[
            SlotSpec(
                id="HERO",
                scope=SlotScope.GLOBAL,
                meaning="the reader's own child, personalized",
                kind="personalizable",
                personalization_field="protagonist_first_name",
                role_safety="protagonist",
            ),
        ],
    )


def _wire_job_lookup(session: AsyncMock, job: GenerationJob | None) -> None:
    """Wire ``session.execute(...).scalar_one_or_none()`` to answer ``job``.

    `personalizable_slot_fields_for_story` (like `personalizable_slot_ids_for_story`)
    issues exactly one SELECT, the `GenerationJob` lookup by `storybook_id`;
    unlike test_moderation_pipeline.py's `_load`, which distinguishes two
    concurrent SELECT targets on the shared pipeline session, a single
    unconditional return is correct for this narrower resolver.
    """
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    session.execute = AsyncMock(return_value=result)


def _seed_story_with_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, session: AsyncMock
) -> str:
    """Wire ``session`` to a ``GenerationJob`` whose contract declares HERO.

    Writes a real contract sidecar to ``tmp_path`` and monkeypatches
    ``resolve_skeleton_path``/``load_skeleton`` onto this module so no real
    skeleton catalog entry is needed; ``load_contract_for`` is left real,
    genuinely reading the sidecar (mirrors
    test_moderation_pipeline.py::_wire_personalizable_job).

    Returns:
        str: the storybook id the wired job resolves to.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / f"{_PERSONALIZABLE_SLUG}.json"
    contract_path = skeleton_path.with_name(f"{_PERSONALIZABLE_SLUG}.contract.json")
    contract_path.write_bytes(
        _personalizable_contract().model_dump_json().encode("utf-8")
    )
    monkeypatch.setattr(
        pslots_mod, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    monkeypatch.setattr(
        pslots_mod,
        "load_skeleton",
        lambda _path: {
            "nodes": [
                {
                    "id": "n_start",
                    "body": (
                        "<<FILL role=setup words=40 beats='The hero, {HERO}, "
                        "arrives and must choose a path.'>>"
                    ),
                    "choices": [],
                },
            ],
        },
    )
    story_id = "s1"
    job = GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id=story_id,
        authoring_metadata={
            "skeleton_slug": _PERSONALIZABLE_SLUG,
            "skeleton_band": "8-11",
        },
    )
    _wire_job_lookup(session, job)
    return story_id


def _seed_story_without_job(session: AsyncMock) -> str:
    """Wire ``session`` so the ``GenerationJob`` SELECT finds no row."""
    _wire_job_lookup(session, None)
    return "s_no_job"


async def test_slot_fields_for_story_returns_the_contract_map(
    mock_async_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A story whose job resolves a contract yields that contract's field map."""
    story_id = _seed_story_with_job(monkeypatch, tmp_path, mock_async_session)

    fields = await personalizable_slot_fields_for_story(mock_async_session, story_id)

    assert fields == {"HERO": "protagonist_first_name"}


async def test_slot_fields_for_story_is_empty_without_a_job(
    mock_async_session: AsyncMock,
) -> None:
    """No GenerationJob means no reachable contract: empty, not fail-closed None.

    Same reasoning as `personalizable_slot_ids_for_story`: seeded and
    directly-imported stories legitimately have no job row, and returning
    None would make every such story look uncomputable to a caller that
    treats None as "refuse".
    """
    story_id = _seed_story_without_job(mock_async_session)

    result = await personalizable_slot_fields_for_story(mock_async_session, story_id)

    assert result == {}


async def test_slot_fields_for_story_degrades_to_empty_when_the_skeleton_is_missing(
    mock_async_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A slug pointing at a vanished skeleton yields {} with a traceable warning.

    The documented contract (this function's Returns section) is that an
    unrecoverable contract is a DEGRADE case, not a fail-closed one: the map
    only feeds sentinel-value lookups, so empty is already the fail-safe
    outcome. What must not degrade silently is the log line: it has to carry
    the slug and band (structured attributes on `_ContractForJobError`, not a
    substring of the loader's message) or the operator cannot tell WHICH
    skeleton went missing. `load_skeleton` is left real here so the raw
    ``FileNotFoundError`` genuinely fires and is wrapped by
    `_contract_for_job` (mirrors test_moderation_pipeline.py::
    test_repair_contract_file_missing_is_discarded_and_routes_to_human_review).
    """
    missing_path = tmp_path / f"{_PERSONALIZABLE_SLUG}.json"
    monkeypatch.setattr(
        pslots_mod, "resolve_skeleton_path", lambda _band, _slug: missing_path
    )
    story_id = "s_missing_skeleton"
    job = GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id=story_id,
        authoring_metadata={
            "skeleton_slug": _PERSONALIZABLE_SLUG,
            "skeleton_band": "8-11",
        },
    )
    _wire_job_lookup(mock_async_session, job)

    with caplog.at_level("WARNING"):
        result = await personalizable_slot_fields_for_story(
            mock_async_session, story_id
        )

    assert result == {}
    # structlog renders through stdlib logging here (same capture route as
    # test_cover_optimize.py), so the structured kv pairs land in the rendered
    # record text; ANSI color codes sit between key and value, so each token
    # is asserted on its own rather than as a "key=value" substring.
    assert "personalization.slot_fields_contract_unresolved" in caplog.text
    assert _PERSONALIZABLE_SLUG in caplog.text
    assert "8-11" in caplog.text
    assert story_id in caplog.text


# ---------------------------------------------------------------------------
# personalizable_slot_ids_for_version: the imported-book path, which has no job
# ---------------------------------------------------------------------------

# A real catalog skeleton whose contract declares a NON-EMPTY personalizable
# slot set, so the assertion below can tell "the contract loaded" apart from
# "no sidecar, empty set by default". Most catalog contracts declare no
# personalizable slot at all, and against one of those the test would pass with
# the contract chain entirely broken.
# Re-derive with: grep -l personalizable skeletons/*/*.contract.json
_REAL_SLUG = "the-midnight-museum"
_REAL_SLUG_SLOTS = frozenset({"HERO"})


async def test_version_resolution_needs_no_generation_job() -> None:
    """An imported book resolves a real slot set with no job row in sight.

    This is the production shape of all seventeen in_review books: provider
    'import', skeleton_slug set, zero generation_job rows. Routed through
    :func:`personalizable_slot_ids_for_story` they resolve the fail-closed
    ``None``, moderation/pipeline.py turns that into a
    sentinel_integrity_violation BLOCK, and a report describing absent
    provenance overwrites one that described the prose.
    """
    version_row = StorybookVersion(
        storybook_id="s1", version=1, blob={}, skeleton_slug=_REAL_SLUG
    )

    # Asserting the exact set, not merely `is not None`: an unresolvable
    # contract returns the EMPTY set on the no-sidecar arm, so `is not None`
    # would pass with the whole chain broken.
    assert personalizable_slot_ids_for_version(version_row) == _REAL_SLUG_SLOTS


async def test_version_without_a_slug_returns_the_empty_set() -> None:
    """No slug means no personalizable slot could exist: an empty set, not None.

    Distinct from the fail-closed ``None`` below, and the distinction is the
    whole tri-state. A fresh-generation version has no skeleton, so there is
    nothing a contract could declare; returning ``None`` here would manufacture
    a block for a book that is simply not skeleton-backed.
    """
    version_row = StorybookVersion(
        storybook_id="s1", version=1, blob={}, skeleton_slug=None
    )

    assert personalizable_slot_ids_for_version(version_row) == frozenset()


async def test_version_with_an_unlocatable_slug_fails_closed() -> None:
    """A slug naming no skeleton returns None, preserving the tri-state.

    The version claims skeleton provenance, so a contract may genuinely declare
    personalizable slots. Not finding it means the contract could not be
    recovered, which must still fail closed rather than guess an empty set and
    risk treating a real sentinel as forged.
    """
    version_row = StorybookVersion(
        storybook_id="s1", version=1, blob={}, skeleton_slug="no-such-skeleton-anywhere"
    )

    assert personalizable_slot_ids_for_version(version_row) is None
