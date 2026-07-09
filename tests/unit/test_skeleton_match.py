"""Unit tests for cell-aware skeleton matching (WS-C PR2)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from cyo_adventure.generation import skeleton_match
from cyo_adventure.generation.skeleton_match import (
    candidates_for_cell,
    find_skeleton_metadata,
    skeleton_matches_cell,
)
from cyo_adventure.storybook.models import AgeBand, NarrativeStyle, StoryMetadata

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_candidates_for_cell_matches_real_library_singleton_cell() -> None:
    """10-13/medium/prose has exactly one production skeleton on disk today."""
    assert candidates_for_cell("10-13", "medium", "prose") == ["the-hollow-lighthouse"]


def test_candidates_for_cell_excludes_non_eligible_and_length_mismatch() -> None:
    """10-13/short/prose excludes the non-eligible clocktower-cipher (which has no
    length/style at all) and every other length in the band."""
    assert candidates_for_cell("10-13", "short", "prose") == ["the-midnight-museum"]


def test_candidates_for_cell_matches_style_for_teen_band() -> None:
    """13-16/medium: prose and gamebook are different cells (style-aware band)."""
    assert candidates_for_cell("13-16", "medium", "prose") == [
        "the-signal-in-the-static"
    ]
    assert candidates_for_cell("13-16", "medium", "gamebook") == ["the-sunspire-ascent"]


def test_candidates_for_cell_ignores_style_below_teen_band() -> None:
    """8-11 is not style-aware: a "gamebook" request still matches the prose skeleton."""
    assert candidates_for_cell("8-11", "short", "gamebook") == ["the-cave-of-echoes"]


def test_candidates_for_cell_returns_empty_for_unknown_band() -> None:
    assert candidates_for_cell("99-100", "short", "prose") == []


def test_candidates_for_cell_returns_empty_for_no_matching_cell() -> None:
    """5-8 has no "long" skeleton at any style (only short and medium exist)."""
    assert candidates_for_cell("5-8", "long", "gamebook") == []


def test_candidates_for_cell_skips_malformed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A corrupt JSON file must be skipped, not crash the scan (mirrors the
    old select_skeleton_for_band contract)."""
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    (band_dir / "aaa-broken.json").write_text("{ not valid json", encoding="utf-8")
    good = {
        "metadata": {
            "age_band": "8-11",
            "reading_level": {"target": 3.0},
            "tier": 1,
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": "time_cave",
            "length": "short",
            "narrative_style": "prose",
        }
    }
    (band_dir / "zzz-good.json").write_text(json.dumps(good), encoding="utf-8")
    monkeypatch.setattr(skeleton_match, "_SKELETON_ROOT", tmp_path)

    assert candidates_for_cell("8-11", "short", "prose") == ["zzz-good"]


def test_find_skeleton_metadata_scans_every_band() -> None:
    """The override lookup is not scoped to any one band directory."""
    metadata = find_skeleton_metadata("the-sunspire-ascent")
    assert metadata is not None
    assert metadata.age_band == AgeBand.BAND_13_16
    assert metadata.narrative_style == NarrativeStyle.GAMEBOOK


def test_find_skeleton_metadata_returns_none_for_unknown_slug() -> None:
    assert find_skeleton_metadata("does-not-exist-anywhere") is None


def test_skeleton_matches_cell_true_for_exact_match() -> None:
    metadata = StoryMetadata.model_validate(
        {
            "age_band": "13-16",
            "reading_level": {"target": 8.0},
            "tier": 1,
            "estimated_minutes": 20,
            "ending_count": 2,
            "topology": "time_cave",
            "length": "long",
            "narrative_style": "gamebook",
        }
    )
    assert skeleton_matches_cell(
        metadata, band="13-16", length="long", style="gamebook"
    )


def test_skeleton_matches_cell_false_for_style_mismatch_in_teen_band() -> None:
    metadata = StoryMetadata.model_validate(
        {
            "age_band": "13-16",
            "reading_level": {"target": 8.0},
            "tier": 1,
            "estimated_minutes": 20,
            "ending_count": 2,
            "topology": "time_cave",
            "length": "long",
            "narrative_style": "gamebook",
        }
    )
    assert not skeleton_matches_cell(
        metadata, band="13-16", length="long", style="prose"
    )


def test_skeleton_matches_cell_ignores_style_below_teen_band() -> None:
    metadata = StoryMetadata.model_validate(
        {
            "age_band": "8-11",
            "reading_level": {"target": 3.0},
            "tier": 1,
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": "time_cave",
            "length": "short",
            "narrative_style": "prose",
        }
    )
    assert skeleton_matches_cell(
        metadata, band="8-11", length="short", style="gamebook"
    )
