"""Unit tests for cell-aware skeleton matching (WS-C PR2)."""

from __future__ import annotations

import json
import random
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation import skeleton_match
from cyo_adventure.generation.skeleton_match import (
    candidates_for_cell,
    find_skeleton_metadata,
    resolve_skeleton_path,
    skeleton_matches_cell,
)
from cyo_adventure.storybook.models import AgeBand, NarrativeStyle, StoryMetadata

if TYPE_CHECKING:
    from pathlib import Path


def test_candidates_for_cell_matches_real_library_cell() -> None:
    """10-13/medium/prose returns every in-cell production skeleton, sorted."""
    assert candidates_for_cell("10-13", "medium", "prose") == [
        "the-envoy-of-three-courts",
        "the-flooded-quarter",
        "the-hollow-lighthouse",
    ]


def test_candidates_for_cell_excludes_non_eligible_and_length_mismatch() -> None:
    """10-13/short/prose excludes the non-eligible clocktower-cipher (which has no
    length/style at all) and every other length in the band."""
    assert candidates_for_cell("10-13", "short", "prose") == [
        "the-cinderwick-exchange",
        "the-glass-comet",
        "the-midnight-frequency",
        "the-midnight-museum",
    ]


def test_candidates_for_cell_matches_style_for_teen_band() -> None:
    """13-16/medium: prose and gamebook are different cells (style-aware band)."""
    assert candidates_for_cell("13-16", "medium", "prose") == [
        "the-conservatory-wars",
        "the-signal-in-the-static",
        "the-undertow-season",
    ]
    assert candidates_for_cell("13-16", "medium", "gamebook") == [
        "the-iron-spire-trial",
        "the-smugglers-cut",
        "the-sunspire-ascent",
    ]


def test_candidates_for_cell_ignores_style_below_teen_band() -> None:
    """8-11 is not style-aware: a "gamebook" request still matches the prose
    skeletons in the cell."""
    assert candidates_for_cell("8-11", "short", "gamebook") == [
        "the-cave-of-echoes",
        "the-locked-carousel",
        "the-robot-fair-sabotage",
    ]


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


def _write_skeleton(band_dir: Path, stem: str, *, age_band: str) -> None:
    """Write a minimal valid skeleton JSON file under ``band_dir``."""
    band_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "age_band": age_band,
            "reading_level": {"target": 3.0},
            "tier": 1,
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": "time_cave",
            "length": "short",
            "narrative_style": "prose",
        }
    }
    (band_dir / f"{stem}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_find_skeleton_metadata_raises_on_ambiguous_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same stem in two band directories is ambiguous, not first-wins."""
    _write_skeleton(tmp_path / "5-8", "twin-slug", age_band="5-8")
    _write_skeleton(tmp_path / "8-11", "twin-slug", age_band="8-11")
    monkeypatch.setattr(skeleton_match, "_SKELETON_ROOT", tmp_path)

    with pytest.raises(ValidationError, match="ambiguous skeleton_slug 'twin-slug'"):
        find_skeleton_metadata("twin-slug")


def test_find_skeleton_metadata_raises_on_present_but_corrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slug that exists on disk but is corrupt is unreadable, not absent."""
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    (band_dir / "broken-slug.json").write_text("{ not valid json", encoding="utf-8")
    monkeypatch.setattr(skeleton_match, "_SKELETON_ROOT", tmp_path)

    with pytest.raises(
        ValidationError, match="skeleton_slug 'broken-slug' exists but is unreadable"
    ):
        find_skeleton_metadata("broken-slug")


def test_resolve_skeleton_path_rejects_traversing_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path-traversal slug must be rejected, never resolved to a real file."""
    monkeypatch.setattr(skeleton_match, "_SKELETON_ROOT", tmp_path)

    with pytest.raises(ValidationError, match="escapes the skeleton root"):
        resolve_skeleton_path("8-11", "../../../../etc/passwd")


def test_resolve_skeleton_path_returns_contained_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A normal band/slug resolves to a path under the skeleton root."""
    monkeypatch.setattr(skeleton_match, "_SKELETON_ROOT", tmp_path)

    resolved = resolve_skeleton_path("8-11", "the-cave-of-echoes")

    assert resolved == (tmp_path / "8-11" / "the-cave-of-echoes.json").resolve()


def test_find_skeleton_metadata_rejects_traversing_slug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The override lookup routes every slug through the containment guard."""
    (tmp_path / "8-11").mkdir()
    monkeypatch.setattr(skeleton_match, "_SKELETON_ROOT", tmp_path)

    with pytest.raises(ValidationError, match="escapes the skeleton root"):
        find_skeleton_metadata("../../../../etc/passwd")


def test_load_metadata_logs_warning_on_corrupt_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A corrupt file returns None but emits a structured WARNING (F1)."""
    warnings_seen: list[tuple[str, dict[str, object]]] = []

    class _CapturingLogger:
        def warning(self, event: str, **kwargs: object) -> None:
            warnings_seen.append((event, kwargs))

    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    bad = band_dir / "corrupt.json"
    bad.write_text("{ not valid json", encoding="utf-8")
    monkeypatch.setattr(skeleton_match, "logger", _CapturingLogger())

    assert skeleton_match._load_metadata(bad) is None
    assert len(warnings_seen) == 1
    event, kwargs = warnings_seen[0]
    assert event == "skeleton.unreadable"
    assert kwargs["path"] == str(bad)
    assert "error" in kwargs


def test_load_metadata_logs_warning_on_schema_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A schema-invalid metadata block returns None and emits a WARNING (F2)."""
    warnings_seen: list[tuple[str, dict[str, object]]] = []

    class _CapturingLogger:
        def warning(self, event: str, **kwargs: object) -> None:
            warnings_seen.append((event, kwargs))

    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    bad = band_dir / "schema-bad.json"
    # Valid JSON, but "metadata" fails StoryMetadata validation (bad age_band).
    bad.write_text(json.dumps({"metadata": {"age_band": "nope"}}), encoding="utf-8")
    monkeypatch.setattr(skeleton_match, "logger", _CapturingLogger())

    assert skeleton_match._load_metadata(bad) is None
    assert len(warnings_seen) == 1
    assert warnings_seen[0][0] == "skeleton.schema_invalid"


def test_load_metadata_logs_warning_on_missing_metadata_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file with no metadata dict returns None and emits a WARNING (F3)."""
    warnings_seen: list[tuple[str, dict[str, object]]] = []

    class _CapturingLogger:
        def warning(self, event: str, **kwargs: object) -> None:
            warnings_seen.append((event, kwargs))

    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    bad = band_dir / "no-meta.json"
    bad.write_text(json.dumps({"not_metadata": {}}), encoding="utf-8")
    monkeypatch.setattr(skeleton_match, "logger", _CapturingLogger())

    assert skeleton_match._load_metadata(bad) is None
    assert len(warnings_seen) == 1
    assert warnings_seen[0][0] == "skeleton.missing_metadata_block"


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


def test_skeleton_matches_cell_treats_null_length_as_wildcard() -> None:
    """A skeleton with no declared length matches any request length (a documented
    backward-compat state on StoryMetadata.length: Length | None)."""
    metadata = StoryMetadata.model_validate(
        {
            "age_band": "8-11",
            "reading_level": {"target": 3.0},
            "tier": 1,
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": "time_cave",
            # length omitted -> None
            "narrative_style": "prose",
        }
    )
    assert metadata.length is None
    assert skeleton_matches_cell(metadata, band="8-11", length="short", style="prose")
    assert skeleton_matches_cell(metadata, band="8-11", length="long", style="prose")


def test_weight_never_reaches_zero() -> None:
    """The inverse-frequency floor: however often a slug was used, its weight
    stays strictly positive, so it is never fully excluded from the draw."""
    assert skeleton_match._weight(0) == pytest.approx(1.0)
    assert skeleton_match._weight(1) == pytest.approx(0.5)
    assert skeleton_match._weight(1000) == pytest.approx(1.0 / 1001)


def test_select_skeleton_for_cell_is_deterministic_under_seeded_rng() -> None:
    """The same seed and inputs always produce the same pick."""
    candidates = ["cave-of-echoes", "clockwork-menagerie", "sky-ship-stowaway"]
    recent_usage = {
        "cave-of-echoes": 5,
        "clockwork-menagerie": 0,
        "sky-ship-stowaway": 0,
    }
    first = skeleton_match.select_skeleton_for_cell(
        candidates, recent_usage, random.Random(42)
    )
    second = skeleton_match.select_skeleton_for_cell(
        candidates, recent_usage, random.Random(42)
    )
    assert first.slug == second.slug == "sky-ship-stowaway"
    assert first.alternatives == tuple(candidates)


def test_select_skeleton_for_cell_uniform_fallback_when_recent_usage_empty() -> None:
    """No recency history (new family, or no family at all) is a uniform draw."""
    candidates = ["cave-of-echoes", "clockwork-menagerie", "sky-ship-stowaway"]
    selection = skeleton_match.select_skeleton_for_cell(
        candidates, {}, random.Random(7)
    )
    assert selection.slug == "cave-of-echoes"


def test_select_skeleton_for_cell_returns_full_candidate_list_as_alternatives() -> None:
    candidates = ["a", "b", "c"]
    selection = skeleton_match.select_skeleton_for_cell(
        candidates, {"a": 2}, random.Random(1)
    )
    assert selection.alternatives == ("a", "b", "c")
    assert selection.slug in candidates


def test_select_skeleton_for_cell_raises_on_empty_candidates() -> None:
    """An internal-invariant guard: the caller must check candidates_for_cell(...)
    for emptiness before calling this (mirrors the old None-check contract).

    Raises the project ValidationError (built-in exceptions are disallowed in
    this service module per src/CLAUDE.md)."""
    with pytest.raises(ValidationError, match="at least one candidate"):
        skeleton_match.select_skeleton_for_cell([], {}, random.Random(0))


def test_selection_rejects_empty_alternatives() -> None:
    """A Selection must always carry at least one alternative (finding H)."""
    with pytest.raises(ValidationError, match="at least one"):
        skeleton_match.Selection(slug="x", alternatives=())


def test_selection_allows_out_of_cell_slug() -> None:
    """An admin override slug need not appear in alternatives (out-of-cell pick)."""
    selection = skeleton_match.Selection(slug="out-of-cell", alternatives=("a", "b"))
    assert selection.slug == "out-of-cell"
    assert selection.alternatives == ("a", "b")


def test_blended_weight_matches_expected_values() -> None:
    """_blended_weight = 1 / (1 + recent + 3*similar) (WS-4); pins the exact
    formula documented in docs/planning/story-flexibility-plan.md."""
    assert skeleton_match._blended_weight(0, 0) == pytest.approx(1.0)
    assert skeleton_match._blended_weight(0, 1) == pytest.approx(0.25)
    assert skeleton_match._blended_weight(2, 0) == pytest.approx(1 / 3)
    assert skeleton_match._blended_weight(1, 1) == pytest.approx(0.2)


def test_blended_weight_never_reaches_zero() -> None:
    """The novelty floor also holds for the blended (similarity-aware) weight."""
    assert skeleton_match._blended_weight(1000, 1000) > 0.0


def test_select_skeleton_for_cell_similar_usage_none_matches_legacy_pick() -> None:
    """similar_usage=None (the default) reproduces the pre-WS-4 pick exactly
    under the same seeded RNG and recent_usage, pinning backward compat."""
    candidates = ["cave-of-echoes", "clockwork-menagerie", "sky-ship-stowaway"]
    recent_usage = {
        "cave-of-echoes": 5,
        "clockwork-menagerie": 0,
        "sky-ship-stowaway": 0,
    }
    legacy = skeleton_match.select_skeleton_for_cell(
        candidates, recent_usage, random.Random(42)
    )
    explicit_none = skeleton_match.select_skeleton_for_cell(
        candidates, recent_usage, random.Random(42), similar_usage=None
    )
    assert legacy.slug == explicit_none.slug == "sky-ship-stowaway"


def test_select_skeleton_for_cell_similar_usage_deweights_saturated_slug() -> None:
    """A slug with a heavy similar-theme count is drawn far less often than an
    equally-recent-count slug with no similar-theme history."""
    candidates = ["saturated", "fresh"]
    recent_usage = {"saturated": 0, "fresh": 0}
    similar_usage = {"saturated": 5, "fresh": 0}
    picks = [
        skeleton_match.select_skeleton_for_cell(
            candidates, recent_usage, random.Random(seed), similar_usage=similar_usage
        ).slug
        for seed in range(200)
    ]
    fresh_count = picks.count("fresh")
    saturated_count = picks.count("saturated")
    assert fresh_count > saturated_count
    # Never fully excluded: the novelty floor still lets "saturated" be drawn.
    assert saturated_count > 0


def test_select_skeleton_for_cell_similar_usage_all_saturated_still_picks() -> None:
    """Every candidate similar>0 still yields a pick (the novelty floor holds
    even under maximal theme-reuse pressure)."""
    candidates = ["a", "b", "c"]
    recent_usage = {"a": 3, "b": 3, "c": 3}
    similar_usage = {"a": 2, "b": 2, "c": 2}
    selection = skeleton_match.select_skeleton_for_cell(
        candidates, recent_usage, random.Random(0), similar_usage=similar_usage
    )
    assert selection.slug in candidates
