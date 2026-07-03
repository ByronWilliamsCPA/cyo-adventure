"""Unit tests for the per-band policy profile."""

from cyo_adventure.storybook.models import AgeBand, ContentFlagLevel, EndingKind
from cyo_adventure.validator.band_profile import (
    _PROFILES,
    MVP_MAX_NODES,
    MVP_MIN_NODES,
    BandProfile,
    mvp_node_budget,
    profile_for,
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
