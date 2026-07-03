"""Unit tests for the per-band policy profile."""

from cyo_adventure.storybook.models import AgeBand, ContentFlagLevel, EndingKind
from cyo_adventure.validator.band_profile import (
    _PROFILES,
    MVP_MAX_NODES,
    MVP_MIN_NODES,
    BandProfile,
    breadth_scaled_floors,
    is_offered_cell,
    min_complete_floor,
    mvp_node_budget,
    offered_cells,
    production_cell_budget,
    profile_for,
    words_per_node_profile,
)


def test_every_band_has_a_profile():
    for band in ("3-5", "5-8", "8-11", "10-13", "13-16", "16+"):
        assert isinstance(profile_for(band), BandProfile)


def test_profiles_match_age_band_enum_exactly():
    """Every AgeBand has a profile and vice versa (guards the fail-open gate).

    validate_policy fails open (skips all PL-15/16/17 checks) for a band with
    no profile; this lockstep assertion makes that branch unreachable for any
    valid, enum-constrained age_band.
    """
    assert set(_PROFILES) == {band.value for band in AgeBand}
    for band in AgeBand:
        assert isinstance(profile_for(band.value), BandProfile)


def test_unknown_band_returns_none():
    assert profile_for("99-100") is None


def test_young_bands_forbid_death_and_capture():
    for band in ("3-5", "5-8"):
        forbidden = profile_for(band).forbidden_ending_kinds
        assert EndingKind.DEATH in forbidden
        assert EndingKind.CAPTURE in forbidden


def test_budget_triple_matches_legacy_values():
    p = profile_for("10-13")
    assert (p.min_nodes, p.max_nodes, p.max_depth) == (25, 50, 8)


def test_oldest_band_allows_intense_peril():
    assert profile_for("16+").content_ceiling["peril"] is ContentFlagLevel.INTENSE


def test_mvp_node_budget_is_band_independent_with_band_depth():
    """The MVP node envelope is the same for every band; depth stays band-anchored."""
    for band in ("3-5", "5-8", "8-11", "10-13", "13-16", "16+"):
        profile = profile_for(band)
        assert profile is not None
        assert mvp_node_budget(band) == (
            MVP_MIN_NODES,
            MVP_MAX_NODES,
            profile.max_depth,
        )


def test_mvp_node_budget_unknown_band_is_none():
    """An unknown band has no MVP budget (keeps the depth cap band-anchored)."""
    assert mvp_node_budget("99-100") is None


def test_production_cell_budget_matches_adr_envelopes():
    """The per-cell node envelopes match the ADR-011 master-cell table."""
    assert production_cell_budget("8-11", "short", "prose") == (60, 100, 23)
    assert production_cell_budget("10-13", "long", "prose") == (220, 340, 43)
    assert production_cell_budget("16+", "long", "gamebook") == (475, 750, 93)


def test_production_cell_budget_off_matrix_is_none():
    """Off-matrix combinations have no cell and fall back to the band budget."""
    assert production_cell_budget("3-5", "long", "prose") is None
    assert production_cell_budget("8-11", "short", "gamebook") is None
    assert production_cell_budget("13-16", "short", "prose") is None


def test_words_per_node_profile_matches_adr():
    """The words-per-node envelopes match the ADR-011 section 3 table."""
    assert words_per_node_profile("8-11", "prose") == (100, 70, 135, 220)
    assert words_per_node_profile("16+", "gamebook") == (80, 55, 110, 175)


def test_words_per_node_profile_young_gamebook_falls_back_to_prose():
    """A young-band gamebook has no cell; the wall guard uses the prose envelope."""
    assert words_per_node_profile("8-11", "gamebook") == words_per_node_profile(
        "8-11", "prose"
    )


def test_words_per_node_profile_unknown_band_is_none():
    """An unknown band has no words-per-node envelope."""
    assert words_per_node_profile("99-100", "prose") is None


def test_min_complete_floor_matches_adr():
    """The fastest-finish arc floors match the ADR-011 master-cell table."""
    assert min_complete_floor("8-11", "short", "prose") == 9
    assert min_complete_floor("16+", "long", "gamebook") == 37


def test_min_complete_floor_off_matrix_is_none():
    """Off-matrix combinations have no arc floor."""
    assert min_complete_floor("3-5", "long", "prose") is None
    assert min_complete_floor("8-11", "short", "gamebook") is None


def test_breadth_scaled_floors_prose():
    """Prose floors scale at 15% endings and 8% decisions of node count."""
    # 100 nodes: ceil(100*0.15)=15 endings, ceil(100*0.08)=8 decisions.
    assert breadth_scaled_floors(100, "prose") == (15, 8)


def test_breadth_scaled_floors_gamebook_endings_higher():
    """Gamebook floors scale endings at 25% (few wins, many fail terminals)."""
    # 200 nodes: ceil(200*0.25)=50 endings, ceil(200*0.08)=16 decisions.
    assert breadth_scaled_floors(200, "gamebook") == (50, 16)


def test_breadth_scaled_floors_unknown_style_uses_prose():
    """An unknown style falls back to the prose ending fraction."""
    assert breadth_scaled_floors(100, "mystery") == breadth_scaled_floors(100, "prose")


def test_offered_cells_matches_production_cells():
    """The coverage grid enumerates exactly the production-cell keys."""
    cells = offered_cells()
    assert ("8-11", "short", "prose") in cells
    assert ("16+", "long", "gamebook") in cells
    # Off-matrix combinations are absent from the grid.
    assert ("3-5", "long", "prose") not in cells
    assert ("8-11", "short", "gamebook") not in cells
    assert len(cells) == 18


def test_is_offered_cell():
    """is_offered_cell agrees with the coverage grid membership."""
    assert is_offered_cell("8-11", "medium", "prose")
    assert is_offered_cell("13-16", "long", "gamebook")
    assert not is_offered_cell("3-5", "long", "prose")
    assert not is_offered_cell("8-11", "short", "gamebook")
    assert not is_offered_cell("13-16", "short", "prose")
