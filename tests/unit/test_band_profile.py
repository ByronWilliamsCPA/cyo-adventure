"""Unit tests for the per-band policy profile."""

from cyo_adventure.storybook.models import ContentFlagLevel, EndingKind
from cyo_adventure.validator.band_profile import BandProfile, profile_for


def test_every_band_has_a_profile():
    for band in ("3-5", "5-8", "8-11", "10-13", "13-16", "16+"):
        assert isinstance(profile_for(band), BandProfile)


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
