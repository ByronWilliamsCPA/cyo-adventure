"""Branch-coverage tests for the anti-clone floors module (WS-5 D7 follow-up).

Targets the branches of ``mutation/floors.py`` that ``test_mutation_floors.py``
does not reach: the missing-baseline conservative fallback in
``_load_thresholds``, the ``_matches_cell`` band-mismatch short-circuit, and the
``load_in_cell_catalog`` skip branches (no metadata, incomplete cell, absent band
directory, unreadable/malformed sibling files). The catalog-scan skips are driven
by a synthetic band directory under a monkeypatched skeleton root so the on-disk
error paths are exercised without touching the committed catalog.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from cyo_adventure.mutation import floors
from cyo_adventure.mutation.floors import (
    _FALLBACK_TAU_CELL,  # pyright: ignore[reportPrivateUsage]
    _FALLBACK_TAU_STATE,  # pyright: ignore[reportPrivateUsage]
    _FALLBACK_TAU_STRUCT,  # pyright: ignore[reportPrivateUsage]
    _load_thresholds,  # pyright: ignore[reportPrivateUsage]
    _matches_cell,  # pyright: ignore[reportPrivateUsage]
    load_in_cell_catalog,
    structural_floor_reason,
)
from cyo_adventure.storybook.models import StoryMetadata

_VALID_META: dict[str, object] = {
    "age_band": "10-13",
    "reading_level": {"scheme": "flesch_kincaid", "target": 5.0},
    "tier": 1,
    "estimated_minutes": 5,
    "ending_count": 2,
    "topology": "open_map",
    "length": "medium",
    "narrative_style": "prose",
    "production_eligible": True,
}


# --- The missing-baseline conservative fallback ---


@pytest.mark.unit
def test_load_thresholds_falls_back_when_the_baseline_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An absent baseline file degrades to the documented conservative floors."""
    monkeypatch.setattr(
        floors, "_BASELINE_PATH", Path("/nonexistent/ws5_floor_baseline.json")
    )
    tau_struct, tau_cell, tau_state = _load_thresholds()
    assert (tau_struct, tau_cell, tau_state) == (
        _FALLBACK_TAU_STRUCT,
        _FALLBACK_TAU_CELL,
        _FALLBACK_TAU_STATE,
    )


# --- _matches_cell band short-circuit ---


@pytest.mark.unit
def test_matches_cell_rejects_a_different_band() -> None:
    """A sibling in another band never matches the candidate's cell."""
    metadata = StoryMetadata.model_validate(_VALID_META)
    assert _matches_cell(metadata, band="8-11", length="medium", style="prose") is False
    assert _matches_cell(metadata, band="10-13", length="medium", style="prose") is True


# --- load_in_cell_catalog early skips ---


@pytest.mark.unit
def test_load_in_cell_catalog_returns_empty_without_a_declared_cell() -> None:
    """A missing/off-type metadata or an incomplete cell yields no siblings."""
    assert load_in_cell_catalog({"metadata": "not-a-dict"}, "p") == []
    assert load_in_cell_catalog({"metadata": {"age_band": "10-13"}}, "p") == []


@pytest.mark.unit
def test_load_in_cell_catalog_returns_empty_for_an_absent_band_dir() -> None:
    """A candidate whose band has no catalog directory has no in-cell cohort."""
    candidate: dict[str, object] = {
        "metadata": {
            "age_band": "99-100",
            "length": "medium",
            "narrative_style": "prose",
        }
    }
    assert load_in_cell_catalog(candidate, "p") == []


@pytest.mark.unit
def test_load_in_cell_catalog_skips_unreadable_and_malformed_siblings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Bad JSON, non-dict metadata, invalid metadata, sidecars, and seeds are skipped."""
    band_dir = tmp_path / "10-13"
    band_dir.mkdir()
    (band_dir / "aaa_valid.json").write_text(
        f'{{"metadata": {StoryMetadata.model_validate(_VALID_META).model_dump_json()}}}',
        encoding="utf-8",
    )
    (band_dir / "bad.json").write_text("not valid json {{{", encoding="utf-8")
    (band_dir / "nondict.json").write_text('{"metadata": 5}', encoding="utf-8")
    (band_dir / "invalid.json").write_text(
        '{"metadata": {"age_band": "10-13"}}', encoding="utf-8"
    )
    seed_meta = {**_VALID_META, "production_eligible": False}
    (band_dir / "seed.json").write_text(
        f'{{"metadata": {StoryMetadata.model_validate(seed_meta).model_dump_json()}}}',
        encoding="utf-8",
    )
    (band_dir / "parent.json").write_text(
        f'{{"metadata": {StoryMetadata.model_validate(_VALID_META).model_dump_json()}}}',
        encoding="utf-8",
    )
    (band_dir / "aaa_valid.contract.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(floors, "_SKELETON_ROOT", tmp_path)
    candidate: dict[str, object] = {
        "metadata": {
            "age_band": "10-13",
            "length": "medium",
            "narrative_style": "prose",
        }
    }
    siblings = load_in_cell_catalog(candidate, "parent")
    # Only the single valid, production-eligible, non-parent sibling survives.
    assert len(siblings) == 1


@pytest.mark.unit
def test_structural_floor_passes_when_a_non_cloning_sibling_is_present() -> None:
    """A far-from-parent mutant clears clause 3 when the sibling is not a clone."""
    root = Path(__file__).resolve().parents[2] / "skeletons"

    def _load(rel: str) -> dict[str, object]:
        return cast(
            "dict[str, object]", json.loads((root / rel).read_text(encoding="utf-8"))
        )

    parent = _load("10-13/the-cinderwick-exchange.json")
    candidate = _load("10-13/the-flooded-quarter.json")
    # A structurally unrelated sibling: the loop runs but no clause-3 clone fires.
    sibling = _load("8-11/the-cave-of-echoes.json")
    assert structural_floor_reason(parent, candidate, [sibling]) is None
