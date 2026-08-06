"""Unit tests for the per-band policy profile."""

from cyo_adventure.storybook.models import AgeBand, ContentFlagLevel, EndingKind
from cyo_adventure.validator.band_profile import (
    _PROFILES,
    ARC_CEILING_MULTIPLE,
    ESTABLISHING_STOP_DEPTH,
    MVP_MAX_NODES,
    MVP_MIN_NODES,
    BandProfile,
    breadth_scaled_floors,
    first_decision_window,
    is_offered_cell,
    min_complete_floor,
    mvp_node_budget,
    nodes_per_decision_ceiling,
    offered_cells,
    production_cell_budget,
    profile_for,
    words_per_node_profile,
)


def test_every_band_has_a_profile():
    for band in ("3-5", "5-8", "8-11", "10-13", "13-16", "16+"):
        assert isinstance(profile_for(band), BandProfile)


def test_profiles_match_age_band_enum_exactly():
    """Every AgeBand has a profile and vice versa (defense in depth).

    validate_policy now fails CLOSED (emits a blocking PL-22 finding instead
    of silently skipping PL-15/16/17) for a band with no profile, so an
    unconfigured band can never reach a human reviewer unvalidated. This
    lockstep assertion is kept as a second, independent guard: it makes the
    PL-22 branch unreachable for any valid, enum-constrained age_band in the
    first place. See test_policy.py::test_validate_policy_fails_closed_when_profile_is_none
    for the runtime proof of the fail-closed behavior itself.
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
            profile.max_depth + ESTABLISHING_STOP_DEPTH,
        )


def test_mvp_depth_budget_admits_the_opening_stop_pl25_requires():
    """L1-7 and PL-25 must not contradict each other on the MVP path.

    PL-25's floor puts the first decision no earlier than the second node, so
    every compliant story spends one node of branch depth establishing itself.
    The band-level max_depth predates that rule; without the allowance, an MVP
    shell authored to its band cap becomes unpublishable the moment it obeys
    the opening rule. This is the regression guard for that interaction, caught
    live on the-clocktower-cipher and the-sunken-signal (AL-087).
    """
    for band in AgeBand:
        profile = profile_for(band.value)
        budget = mvp_node_budget(band.value)
        window = first_decision_window(band.value)
        assert profile is not None
        assert budget is not None
        assert window is not None
        # Depth headroom over the legacy band cap must cover the floor's cost:
        # a floor of N puts the first decision N nodes in, i.e. N-1 lead-in
        # stops, of which the legacy cap assumed none.
        assert budget[2] - profile.max_depth >= window[0] - 1, band.value


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


# --- PL-25 first-decision window and PL-26 density window ---------------------

# Adams, Beckelhymer and Marr, Journal of Humanistic Mathematics 9(2), 2019
# (DOI 10.5642/jhummath.201902.05), Table 4: pages to the first decision across
# the 40-book corpus have a median of 4 and a range of 2 to 8.25.
JHM_FIRST_DECISION_MEDIAN = 4
JHM_FIRST_DECISION_MAX = 8.25

# Same table: pages between decisions have a mean of 3.28 corpus-wide. Note the
# scope: corpus-wide, not along any one path. PL-26 measures a shortest path, so
# this anchors its ceiling only; see _NODES_PER_DECISION_CEILING on why the
# low side of that comparison does not hold.
JHM_PAGES_BETWEEN_DECISIONS = 3.28


def test_first_decision_window_covers_every_band():
    """Every configured band has a PL-25 window (the band_profile #VERIFY)."""
    for band in AgeBand:
        assert first_decision_window(band.value) is not None, band.value


def test_first_decision_window_is_ordered():
    """Each window's floor must not exceed its ceiling."""
    for band in AgeBand:
        window = first_decision_window(band.value)
        assert window is not None
        floor, ceiling = window
        assert floor <= ceiling, band.value


def test_first_decision_ceiling_never_below_the_corpus_median():
    """No band may block first-decision pacing the source corpus calls typical.

    A ceiling under the JHM median of 4 would make median-paced storytelling a
    PL-25 ERROR, which is miscalibrated by construction. This assertion is the
    guard that caught exactly that mistake in the table's first draft, where the
    3-5 and 5-8 ceilings sat at 3 and 4.
    """
    for band in AgeBand:
        window = first_decision_window(band.value)
        assert window is not None
        assert window[1] > JHM_FIRST_DECISION_MEDIAN, band.value


def test_first_decision_measured_bands_span_the_corpus_range():
    """The bands the JHM corpus covers admit its full measured range."""
    for band in ("8-11", "10-13"):
        window = first_decision_window(band)
        assert window is not None
        floor, ceiling = window
        assert floor <= 2, band
        assert ceiling >= JHM_FIRST_DECISION_MAX, band


def test_unknown_band_has_no_first_decision_window():
    """An unconfigured band yields None so PL-25 skips rather than guesses."""
    assert first_decision_window("not-a-band") is None


def test_nodes_per_decision_ceilings_are_positive():
    """Both style ceilings are well formed."""
    for style in ("prose", "gamebook"):
        assert nodes_per_decision_ceiling(style) > 0, style


def test_prose_density_ceiling_sits_above_the_measured_anchor():
    """A story at the JHM 3.28 mean pages-between-decisions must not warn.

    The calibration invariant from AL-081 applied to PL-26: a threshold that
    fires on corpus-median pacing is miscalibrated by construction.
    """
    assert nodes_per_decision_ceiling("prose") > JHM_PAGES_BETWEEN_DECISIONS


def test_gamebook_density_ceiling_is_tighter_than_prose():
    """A gamebook steers more often by genre, so its corridor bar sits lower.

    Guards the direction of the style split: judging a numbered-section gamebook
    against the prose ceiling would let a genuine gamebook corridor pass.
    """
    assert nodes_per_decision_ceiling("gamebook") < nodes_per_decision_ceiling("prose")


def test_unknown_style_density_falls_back_to_prose():
    """An unrecognised style is judged as prose rather than skipped."""
    assert nodes_per_decision_ceiling("interpretive-dance") == (
        nodes_per_decision_ceiling("prose")
    )


def test_arc_ceiling_multiple_matches_the_measured_playthrough_ratio():
    """JHM records a longest playthrough of 27.5 pages against a shortest of 11."""
    assert ARC_CEILING_MULTIPLE == 27.5 / 11
