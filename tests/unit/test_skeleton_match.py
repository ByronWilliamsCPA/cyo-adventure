"""Unit tests for cell-aware skeleton matching (WS-C PR2)."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation import skeleton_match
from cyo_adventure.generation.skeleton import is_sidecar
from cyo_adventure.generation.skeleton_match import (
    candidates_for_cell,
    find_skeleton_metadata,
    is_continuation_skeleton,
    request_theme_signature,
    resolve_skeleton_path,
    select_skeleton_for_cell,
    skeleton_matches_cell,
    theme_overlap_for_candidates,
)
from cyo_adventure.storybook.models import AgeBand, NarrativeStyle, StoryMetadata


def _cell_members_from_disk(band: str, length: str, style: str) -> list[str]:
    """Recompute a cell's membership straight from the skeleton files.

    Deliberately an independent reimplementation rather than a call to
    `candidates_for_cell`, which would make the assertions tautological. It reads
    the same three metadata fields the selector keys on, from the same directory,
    and sorts by filename as the selector does.

    Exists because these tests used to freeze the expected slug list. Every
    skeleton authored into a covered cell then broke them, which taxed the
    project's central activity: the 2026-08-18 fan-out added fourteen books and
    broke four tests that had no defect in them (`UW-C304`).
    """
    import json
    from pathlib import Path

    members: list[str] = []
    for path in sorted(Path("skeletons").glob(f"{band}/*.json")):
        if path.name.endswith((".contract.json", ".lineage.json", ".narrative.json")):
            continue
        try:
            doc = json.loads(path.read_text())
        except (ValueError, OSError):
            continue
        meta = doc.get("metadata") or {}
        if not isinstance(meta, dict):
            continue
        if meta.get("production_eligible") is False:
            continue
        if meta.get("series") is not None:
            continue
        if meta.get("length") != length or meta.get("narrative_style") != style:
            continue
        if meta.get("age_band") != band:
            continue
        members.append(path.stem)
    return members


def test_candidates_for_cell_matches_real_library_cell() -> None:
    """10-13/medium/prose returns every in-cell production skeleton, sorted.

    Checked against an independent read of the skeleton files rather than a
    frozen slug list, so authoring into this cell cannot break a test that has
    no defect in it.
    """
    expected = _cell_members_from_disk("10-13", "medium", "prose")
    assert expected, "fixture guard: the cell must have members for this to test"
    assert candidates_for_cell("10-13", "medium", "prose") == expected


def test_candidates_for_cell_excludes_non_eligible_and_length_mismatch() -> None:
    """10-13/short/prose excludes the non-eligible clocktower-cipher (which has no
    length/style at all) and every other length in the band."""
    assert candidates_for_cell("10-13", "short", "prose") == [
        "the-blackout-week",
        "the-cinderwick-exchange",
        "the-glass-comet",
        "the-midnight-frequency",
        "the-midnight-museum",
    ]


def test_candidates_for_cell_matches_style_for_teen_band() -> None:
    """13-16/medium: prose and gamebook are different cells (style-aware band).

    The property is the SPLIT, not the membership: no slug may appear in both
    lists, and each must match an independent read of the files. Freezing the
    membership made authoring into either cell break this test.
    """
    prose = candidates_for_cell("13-16", "medium", "prose")
    gamebook = candidates_for_cell("13-16", "medium", "gamebook")
    assert prose == _cell_members_from_disk("13-16", "medium", "prose")
    assert gamebook == _cell_members_from_disk("13-16", "medium", "gamebook")
    assert prose, "fixture guard: the prose cell must have members"
    assert gamebook, "fixture guard: the gamebook cell must have members"
    assert not set(prose) & set(gamebook)


def test_candidates_for_cell_ignores_style_below_teen_band() -> None:
    """8-11 is not style-aware: a "gamebook" request still matches the prose
    skeletons in the cell."""
    assert candidates_for_cell("8-11", "short", "gamebook") == [
        "the-cave-of-echoes",
        "the-half-hour-call",
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


def test_production_candidates_ignores_contract_json_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A WS-2 `<slug>.contract.json` sidecar is skipped: no candidate, no warning.

    Without the `.contract.json` skip in `_production_candidates`, the
    `*.json` glob would treat this sidecar as a skeleton missing its
    `metadata` block (it has none) and log one spurious
    `skeleton.missing_metadata_block` warning per contract on every scan
    (WS-2 design section 2.1). This sidecar is authoring-time data, never a
    selectable skeleton.
    """
    warnings_seen: list[tuple[str, dict[str, object]]] = []

    class _CapturingLogger:
        def warning(self, event: str, **kwargs: object) -> None:
            warnings_seen.append((event, kwargs))

    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    # A contract sidecar carries no top-level "metadata" block of its own; if
    # treated as a skeleton candidate it would log skeleton.missing_metadata_block.
    (band_dir / "themed-slug.contract.json").write_text(
        json.dumps({"contract_version": 1, "skeleton_slug": "themed-slug"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(skeleton_match, "_SKELETON_ROOT", tmp_path)
    monkeypatch.setattr(skeleton_match, "logger", _CapturingLogger())

    candidates = skeleton_match._production_candidates("8-11")

    assert candidates == []
    assert warnings_seen == []


def test_production_candidates_ignores_lineage_json_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A WS-5 `<slug>.lineage.json` sidecar is skipped: no candidate, no warning.

    ADR-020 decision 2 / OQ-1 adds lineage as a second sidecar class in
    `skeletons/<band>/`. The generalized `is_sidecar` skip must treat it exactly
    like a contract sidecar: never a selectable skeleton, and never a spurious
    `skeleton.missing_metadata_block` warning.
    """
    warnings_seen: list[tuple[str, dict[str, object]]] = []

    class _CapturingLogger:
        def warning(self, event: str, **kwargs: object) -> None:
            warnings_seen.append((event, kwargs))

    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    # A lineage sidecar carries no top-level "metadata" block; if treated as a
    # skeleton candidate it would log skeleton.missing_metadata_block.
    (band_dir / "mutant-slug.lineage.json").write_text(
        json.dumps({"lineage_version": 1, "mutant_slug": "mutant-slug"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(skeleton_match, "_SKELETON_ROOT", tmp_path)
    monkeypatch.setattr(skeleton_match, "logger", _CapturingLogger())

    candidates = skeleton_match._production_candidates("8-11")

    assert candidates == []
    assert warnings_seen == []


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
    rng = random.Random(0)
    with pytest.raises(ValidationError, match="at least one candidate"):
        skeleton_match.select_skeleton_for_cell([], {}, rng)


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


# ---------------------------------------------------------------------------
# Continuation books are not standalone candidates (AL-045)
# ---------------------------------------------------------------------------


def _series_metadata(book_index: int | None) -> StoryMetadata:
    """Build 16+ gamebook metadata, optionally declaring a series position."""
    payload: dict[str, object] = {
        "age_band": "16+",
        "reading_level": {"target": 9.5},
        "tier": 2,
        "estimated_minutes": 14,
        "ending_count": 2,
        "topology": "branch_and_bottleneck",
        "length": "medium",
        "narrative_style": "gamebook",
    }
    if book_index is not None:
        payload["series"] = {
            "series_id": "chain",
            "book_index": book_index,
            "series_entry_node": "n_start",
            "is_final": False,
            "carries_state": True,
        }
    return StoryMetadata.model_validate(payload)


@pytest.mark.unit
def test_is_continuation_skeleton_only_flags_book_two_and_later() -> None:
    """book_index 1 and a series-less skeleton are both valid entry points."""
    assert is_continuation_skeleton(_series_metadata(None)) is False
    assert is_continuation_skeleton(_series_metadata(1)) is False
    assert is_continuation_skeleton(_series_metadata(2)) is True
    assert is_continuation_skeleton(_series_metadata(3)) is True


@pytest.mark.unit
def test_continuation_book_does_not_match_its_own_cell() -> None:
    """A mid-series book must never be drawn for an ordinary themed request.

    A continuation opens on state it did not earn (its variables declare the
    previous book's artifacts already held, and its opening beats name them), so
    serving it standalone hands the reader a protagonist from a story they have
    never seen and makes the fill render those beats against an unrelated theme.
    """
    cell = {"band": "16+", "length": "medium", "style": "gamebook"}
    assert skeleton_matches_cell(_series_metadata(1), **cell), (
        "book 1 of a series is a legitimate standalone entry point"
    )
    assert not skeleton_matches_cell(_series_metadata(2), **cell)
    assert not skeleton_matches_cell(_series_metadata(3), **cell)


@pytest.mark.unit
def test_no_catalog_continuation_book_is_offered_for_any_cell() -> None:
    """Integration guard over the live catalog, active once series books exist."""
    continuations = [
        (band_dir.name, path.stem)
        for band_dir in (Path(__file__).resolve().parents[2] / "skeletons").iterdir()
        if band_dir.is_dir()
        for path in sorted(band_dir.glob("*.json"))
        if not is_sidecar(path)
        and (meta := find_skeleton_metadata(path.stem)) is not None
        and is_continuation_skeleton(meta)
    ]
    if not continuations:
        pytest.skip("no continuation books in the catalog yet")
    for band, slug in continuations:
        for length in ("short", "medium", "long"):
            for style in ("prose", "gamebook"):
                assert slug not in candidates_for_cell(band, length, style), (
                    f"{slug} is a continuation book but is offered for "
                    f"({band}, {length}, {style})"
                )


# ---------------------------------------------------------------------------
# W2.2: theme-aware skeleton selection
# ---------------------------------------------------------------------------


def _themed_metadata(themes: list[str]) -> StoryMetadata:
    """Build minimal 10-13/medium/prose metadata declaring the given themes."""
    return StoryMetadata.model_validate(
        {
            "age_band": "10-13",
            "reading_level": {"target": 6.0},
            "tier": 1,
            "themes": themes,
            "estimated_minutes": 8,
            "ending_count": 3,
            "topology": "branch_and_bottleneck",
        }
    )


def test_request_theme_signature_maps_recognized_premise_words() -> None:
    tags = request_theme_signature("a story about a dragon hiding in a cave")
    assert {"dragon", "cave"} <= tags


def test_request_theme_signature_empty_for_unrecognized_premise() -> None:
    """A premise with no vocabulary hits yields an empty signature (the
    zero-overlap case that must leave every candidate's bonus at 0.0)."""
    assert request_theme_signature("xyzzy plugh quux") == frozenset()


def test_theme_overlap_bonus_full_containment() -> None:
    metadata = _themed_metadata(["dragon"])
    bonus = skeleton_match._theme_overlap_bonus(frozenset({"dragon"}), metadata)
    assert bonus == pytest.approx(1.0)


def test_theme_overlap_bonus_no_overlap_is_zero() -> None:
    metadata = _themed_metadata(["courage"])
    bonus = skeleton_match._theme_overlap_bonus(frozenset({"dragon"}), metadata)
    assert bonus == 0.0


def test_theme_overlap_bonus_empty_request_is_zero() -> None:
    """containment(empty, story) == 0.0: nothing was asked for, so nothing
    can be "covered" (mirrors diversity.normalize.containment's own contract)."""
    metadata = _themed_metadata(["dragon"])
    bonus = skeleton_match._theme_overlap_bonus(frozenset(), metadata)
    assert bonus == 0.0


def test_theme_overlap_for_candidates_matches_real_catalog_cell() -> None:
    """10-13/medium/prose: a river-themed request scores 'the-flooded-quarter'
    (declared theme 'the river') above its cell-mates, which declare no
    subject tag the request premise mentions."""
    candidates = candidates_for_cell("10-13", "medium", "prose")
    assert "the-flooded-quarter" in candidates
    overlap = theme_overlap_for_candidates(
        "a story about a great river adventure", "10-13", candidates
    )
    assert overlap["the-flooded-quarter"] > 0.0
    for slug in candidates:
        if slug != "the-flooded-quarter":
            assert overlap.get(slug, 0.0) <= overlap["the-flooded-quarter"]


def test_theme_overlap_for_candidates_zero_overlap_premise_is_all_zero() -> None:
    candidates = candidates_for_cell("10-13", "medium", "prose")
    overlap = theme_overlap_for_candidates("xyzzy plugh quux", "10-13", candidates)
    assert all(bonus == 0.0 for bonus in overlap.values())


def test_select_skeleton_for_cell_matching_candidate_reliably_wins() -> None:
    """A theme-matching candidate outdraws a non-matching one over many seeds,
    with recency/similarity held equal between them."""
    candidates = ["matching", "plain"]
    recent_usage = {"matching": 0, "plain": 0}
    theme_overlap = {"matching": 1.0, "plain": 0.0}
    picks = [
        select_skeleton_for_cell(
            candidates,
            recent_usage,
            random.Random(seed),
            theme_overlap=theme_overlap,
        ).slug
        for seed in range(200)
    ]
    matching_count = picks.count("matching")
    plain_count = picks.count("plain")
    assert matching_count > plain_count
    # Never fully excluded: "plain" is still drawable (bonus only scales
    # weight, never zeroes it, mirroring the C-4 novelty floor).
    assert plain_count > 0


def test_select_skeleton_for_cell_theme_overlap_none_matches_legacy_pick() -> None:
    """theme_overlap=None (the default) reproduces the pre-W2.2 pick exactly
    under the same seeded RNG, pinning backward compatibility."""
    candidates = ["cave-of-echoes", "clockwork-menagerie", "sky-ship-stowaway"]
    recent_usage = {
        "cave-of-echoes": 5,
        "clockwork-menagerie": 0,
        "sky-ship-stowaway": 0,
    }
    legacy = select_skeleton_for_cell(candidates, recent_usage, random.Random(42))
    explicit_none = select_skeleton_for_cell(
        candidates, recent_usage, random.Random(42), theme_overlap=None
    )
    assert legacy.slug == explicit_none.slug == "sky-ship-stowaway"


def test_select_skeleton_for_cell_zero_overlap_keeps_recency_weighting() -> None:
    """Every candidate at bonus 0.0 (a request the vocabulary did not
    recognize) reproduces the recency-only pick exactly: today's behavior is
    unchanged for a zero-overlap request."""
    candidates = ["cave-of-echoes", "clockwork-menagerie", "sky-ship-stowaway"]
    recent_usage = {
        "cave-of-echoes": 5,
        "clockwork-menagerie": 0,
        "sky-ship-stowaway": 0,
    }
    zero_overlap = dict.fromkeys(candidates, 0.0)
    legacy = select_skeleton_for_cell(candidates, recent_usage, random.Random(42))
    with_zero_overlap = select_skeleton_for_cell(
        candidates, recent_usage, random.Random(42), theme_overlap=zero_overlap
    )
    assert legacy.slug == with_zero_overlap.slug == "sky-ship-stowaway"


def test_select_skeleton_for_cell_band_and_cell_filtering_unchanged() -> None:
    """Theme-aware selection never widens or narrows candidates_for_cell's own
    band/length/style filtering; it only re-weights within it."""
    band, length, style = "10-13", "medium", "prose"
    candidates = candidates_for_cell(band, length, style)
    overlap = theme_overlap_for_candidates("a great river adventure", band, candidates)
    selection = select_skeleton_for_cell(
        candidates, {}, random.Random(0), theme_overlap=overlap
    )
    assert selection.slug in candidates
    assert set(selection.alternatives) == set(candidates)


def _write_sized_skeleton(band_dir: Path, stem: str, *, fill_words: int) -> None:
    """Write a skeleton whose declared fill target is *fill_words* words."""
    band_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "age_band": "5-8",
            "reading_level": {"target": 3.0},
            "tier": 1,
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": "time_cave",
            "length": "short",
            "narrative_style": "prose",
        },
        "nodes": [
            {
                "id": "n0",
                "body": f"<<FILL role=rising words={fill_words} beats='x'>>",
                "is_ending": False,
                "choices": [],
            }
        ],
    }
    (band_dir / f"{stem}.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.unit
def test_an_over_cap_skeleton_is_not_a_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Selection must not offer a skeleton the one-shot fill cannot emit.

    `fill_skeleton` has no chunking, so an over-cap skeleton does not degrade,
    it truncates: nothing parses, the orchestrator burns its whole repair
    budget, and the job fails deterministically on every retry, forever.

    This was observe-only while the cap was 32,000, because enforcing then
    would have emptied the 13-16 and 16+ bands. At 131,072 it excludes nothing
    in the current catalog, so it guards future skeletons rather than filtering
    today's. UW-C07 / AL-046.
    """
    _write_sized_skeleton(tmp_path / "5-8", "too-big", fill_words=999_999)
    monkeypatch.setattr(skeleton_match, "_SKELETON_ROOT", tmp_path)

    with caplog.at_level("WARNING"):
        candidates = skeleton_match._production_candidates("5-8")  # pyright: ignore[reportPrivateUsage]

    assert candidates == []
    assert "skeleton.fill_infeasible" in caplog.text


@pytest.mark.unit
def test_a_within_cap_skeleton_is_still_a_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The screen must refuse only what cannot fit, not narrow the catalog."""
    _write_sized_skeleton(tmp_path / "5-8", "fits", fill_words=500)
    monkeypatch.setattr(skeleton_match, "_SKELETON_ROOT", tmp_path)

    slugs = [slug for slug, _ in skeleton_match._production_candidates("5-8")]  # pyright: ignore[reportPrivateUsage]

    assert slugs == ["fits"]


# `is_fill_feasible` allows `cap * 0.8 / 2.0` declared words (the 0.8 margin is
# applied inside it, and `_TOKENS_PER_FILL_WORD` is 2.0). At the 131,072 default
# that is 52,428 words; at `anthropic/claude-haiku-4.5`'s 64,000 ceiling it is
# 25,600. 30,000 words therefore sits BETWEEN the two caps.
_BETWEEN_CAPS_WORDS = 30_000


@pytest.mark.unit
def test_a_bound_skeleton_over_a_models_cap_is_still_a_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Selection screens the model-independent default for BOTH fill paths.

    This is a guard against re-narrowing, and it is worth the words because
    narrowing looks obviously right. `UW-C302` was that a BOUND fill (one whose
    skeleton carries a `.contract.json` sidecar) could not be chunked, so a bound
    skeleton over the serving model's ceiling truncated and burned its whole
    repair budget; the tempting fix is to screen bound skeletons at that ceiling
    here. That fix was written and measured: at the lowest live ceiling it drops
    7 skeletons and narrows 6 of the 28 populated cells, 16+/long worst at 4
    candidates to 2. It was not shipped, because the actual repair is to let a
    bound fill chunk (``fill_subset_bound.md``), after which the bound and
    unbound paths meet the same limit and this screen is correct for both.

    A model-dependent screen would also make the catalog a child can be offered
    depend on which backend happens to be configured, so swapping models would
    silently change the library rather than the plumbing.
    """
    band_dir = tmp_path / "5-8"
    _write_sized_skeleton(band_dir, "bound-and-big", fill_words=_BETWEEN_CAPS_WORDS)
    # A contract sidecar is what makes a fill bound (`worker.py`'s
    # `load_contract_for` returns None without one), and it must not itself be
    # scanned as a skeleton.
    (band_dir / "bound-and-big.contract.json").write_text(
        json.dumps({"contract_version": 1, "skeleton_slug": "bound-and-big"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(skeleton_match, "_SKELETON_ROOT", tmp_path)

    slugs = [slug for slug, _ in skeleton_match._production_candidates("5-8")]  # pyright: ignore[reportPrivateUsage]

    assert slugs == ["bound-and-big"]


@pytest.mark.unit
def test_a_deprecated_skeleton_is_not_a_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-011 D11: a retired skeleton stops being drawn for new stories.

    Retirement is not deletion. The file stays in the catalog as a mutation
    parent, as provenance for the books already filled from it, and as history;
    it simply leaves the selection pool.
    """
    _write_skeleton(tmp_path / "3-5", "retired", age_band="3-5")
    path = tmp_path / "3-5" / "retired.json"
    payload = json.loads(path.read_text())
    payload["metadata"]["deprecated"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(skeleton_match, "_SKELETON_ROOT", tmp_path)

    assert skeleton_match._production_candidates("3-5") == []  # pyright: ignore[reportPrivateUsage]


@pytest.mark.unit
def test_a_live_skeleton_in_the_same_band_still_selects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Retiring one skeleton must not empty its band."""
    _write_skeleton(tmp_path / "3-5", "live", age_band="3-5")
    _write_skeleton(tmp_path / "3-5", "retired", age_band="3-5")
    path = tmp_path / "3-5" / "retired.json"
    payload = json.loads(path.read_text())
    payload["metadata"]["deprecated"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(skeleton_match, "_SKELETON_ROOT", tmp_path)

    slugs = [slug for slug, _ in skeleton_match._production_candidates("3-5")]  # pyright: ignore[reportPrivateUsage]

    assert slugs == ["live"]


def test_a_skeleton_that_is_not_valid_utf8_is_skipped_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mis-encoded file must be skipped like any other corrupt one.

    Both readers open with ``encoding="utf-8"``, and on invalid bytes
    ``read_text`` raises ``UnicodeDecodeError``: a ``ValueError``, so neither
    ``OSError`` nor ``json.JSONDecodeError`` caught it and the scan crashed the
    way a corrupt file was specifically meant not to. This scan runs
    synchronously inside POST /authoring-plan, so the escape surfaced as a 500
    on a guardian request rather than as one skipped skeleton (`AL-438`).
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    # 0x80 is a continuation byte with no lead byte: never valid UTF-8.
    (band_dir / "aaa-mis-encoded.json").write_bytes(b'{"metadata": "\x80\x81"}')
    _write_skeleton(band_dir, "zzz-good", age_band="8-11")
    monkeypatch.setattr(skeleton_match, "_SKELETON_ROOT", tmp_path)

    assert candidates_for_cell("8-11", "short", "prose") == ["zzz-good"]


# ---------------------------------------------------------------------------
# Per-family reuse cap (UW-C315 ruling, 2026-08-21)
# ---------------------------------------------------------------------------
#
# Measured: two fills of one skeleton from deliberately distant briefs share
# 96.3 four-grams per 1000 leaf words against a budget of 4.0, and neither
# candidate lever (the differentiation directive at 110.7, skeleton mutation at
# 108.1) moves it. The ruling that follows is a product policy, not a weight:
# until a lever reaches the bar, a family is not served two books off the same
# skeleton. That is a HARD exclusion, and it deliberately overrides decision
# C-4's never-zero novelty floor for this one case, because a floor that keeps
# a used skeleton drawable at 1/(1+n) still ships the near-duplicate, just less
# often.


def test_a_skeleton_the_family_already_used_is_not_drawn_again() -> None:
    """The cap, stated directly. No seed may reach a used slug."""
    candidates = ["used", "fresh"]
    picks = {
        skeleton_match.select_skeleton_for_cell(
            candidates, {"used": 1}, random.Random(seed)
        ).slug
        for seed in range(200)
    }
    assert picks == {"fresh"}


def test_one_prior_use_is_enough_to_exclude() -> None:
    """A single reuse is the whole defect; the cap does not wait for a count.

    96.3 per 1000 is the score of the FIRST pair, so any count threshold above
    one would ship the very books that produced the measurement. A slug used
    exactly once is gone from the draw while unused siblings remain.
    """
    candidates = ["used", "a", "b"]
    picks = {
        skeleton_match.select_skeleton_for_cell(
            candidates, {"used": 1}, random.Random(seed)
        ).slug
        for seed in range(200)
    }
    assert picks == {"a", "b"}


def test_the_cap_relaxes_rather_than_leaving_the_family_with_no_story() -> None:
    """A cell whose every candidate is used still yields a pick.

    Refusing would make a family's Nth request in a small cell fail outright,
    which trades a diversity defect for an availability outage. The relaxation
    is recorded on the Selection instead, so the compromise is visible rather
    than silent.
    """
    candidates = ["a", "b"]
    selection = skeleton_match.select_skeleton_for_cell(
        candidates, {"a": 1, "b": 4}, random.Random(0)
    )
    assert selection.slug in candidates
    assert selection.reuse_cap_relaxed is True


def test_the_relaxed_draw_still_prefers_the_least_used_skeleton() -> None:
    """When every candidate is used, the old inverse-frequency weighting is
    exactly what should decide, so the least-repeated book wins most often."""
    candidates = ["once", "many"]
    picks = [
        skeleton_match.select_skeleton_for_cell(
            candidates, {"once": 1, "many": 20}, random.Random(seed)
        ).slug
        for seed in range(200)
    ]
    # A bare `>` passes at 101/99, which the weighting does not predict:
    # 1/(1+1) against 1/(1+20) is roughly a 91/9 split. Assert a margin
    # loose enough for sampling noise over 200 draws and tight enough to
    # fail if the weighting flattens.
    assert picks.count("once") > 3 * picks.count("many")


def test_a_lone_unused_candidate_is_drawn_with_the_cap_intact() -> None:
    """A one-skeleton cell is the smallest pool the cap can run over.

    The boundary matters because the relaxation branch triggers on an empty
    result, and a pool of one is where "filtered to nothing" and "filtered to
    everything" are one element apart.
    """
    selection = skeleton_match.select_skeleton_for_cell(["only"], {}, random.Random(0))
    assert selection.slug == "only"
    assert selection.reuse_cap_relaxed is False


def test_a_lone_used_candidate_relaxes_rather_than_failing() -> None:
    """The other half of the boundary: the only candidate is already read.

    Excluding it would leave `rng.choices` an empty population, which raises,
    so a family's second request in a single-skeleton cell would 500 rather
    than serve a repeat. The repeat is the correct trade, and the relaxation
    flag is what keeps it visible.
    """
    selection = skeleton_match.select_skeleton_for_cell(
        ["only"], {"only": 3}, random.Random(0)
    )
    assert selection.slug == "only"
    assert selection.reuse_cap_relaxed is True


def test_a_selection_that_honored_the_cap_says_so() -> None:
    """The flag distinguishes "cap held" from "cap could not be applied"."""
    selection = skeleton_match.select_skeleton_for_cell(
        ["used", "fresh"], {"used": 3}, random.Random(0)
    )
    assert selection.reuse_cap_relaxed is False


def test_the_cap_never_hides_a_candidate_from_the_admin() -> None:
    """``alternatives`` is the admin's view of the cell, not the draw pool.

    An excluded slug must still be listed, or the reviewer cannot see that an
    out-of-cell override is available to them.
    """
    selection = skeleton_match.select_skeleton_for_cell(
        ["used", "fresh"], {"used": 2}, random.Random(0)
    )
    assert selection.alternatives == ("used", "fresh")


def test_a_family_with_no_history_is_unaffected_by_the_cap() -> None:
    """An empty usage map excludes nothing and stays a uniform draw."""
    candidates = ["cave-of-echoes", "clockwork-menagerie", "sky-ship-stowaway"]
    selection = skeleton_match.select_skeleton_for_cell(
        candidates, {}, random.Random(7)
    )
    assert selection.slug == "cave-of-echoes"
    assert selection.reuse_cap_relaxed is False


def test_theme_overlap_cannot_buy_a_used_skeleton_back_into_the_draw() -> None:
    """The cap outranks the W2.2 overlap bonus.

    Overlap multiplies a weight; it must not resurrect an excluded slug, or a
    request whose premise matches the family's last book would reliably draw
    that same book.
    """
    candidates = ["used", "fresh"]
    picks = {
        skeleton_match.select_skeleton_for_cell(
            candidates,
            {"used": 1},
            random.Random(seed),
            theme_overlap={"used": 1.0, "fresh": 0.0},
        ).slug
        for seed in range(100)
    }
    assert picks == {"fresh"}


# ---------------------------------------------------------------------------
# find_skeleton_band: recovering the band a StorybookVersion does not store
# ---------------------------------------------------------------------------


def test_find_skeleton_band_returns_the_matching_directory() -> None:
    """The band comes from the directory that holds the file.

    ``moderation/personalizable_slots.py::personalizable_slot_ids_for_version``
    resolves a theme contract from a ``StorybookVersion``, which carries a
    ``skeleton_slug`` and no band. Deriving the band from the metadata's
    declared ``age_band`` instead would resolve to a path that does not exist
    whenever a skeleton is filed under one band while declaring another, and
    fail closed to the very block that resolver exists to avoid.
    """
    assert skeleton_match.find_skeleton_band("the-cave-of-echoes") == "8-11"


def test_find_skeleton_band_returns_none_for_an_absent_slug() -> None:
    """An absent slug is None, not an exception: the caller fails closed itself."""
    assert skeleton_match.find_skeleton_band("no-such-skeleton-anywhere") is None


def test_find_skeleton_band_rejects_a_traversing_slug() -> None:
    """resolve_skeleton_path's containment check still applies to this entry point."""
    with pytest.raises(ValidationError):
        skeleton_match.find_skeleton_band("../../etc/passwd")
