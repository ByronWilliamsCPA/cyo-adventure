"""Unit tests for skeleton band auto-match."""

from __future__ import annotations

from cyo_adventure.generation.skeleton_match import select_skeleton_for_band


def test_select_skeleton_for_band_returns_first_eligible_slug_alphabetically() -> None:
    """8-11 has three production-eligible skeletons; the first alphabetically wins."""
    assert select_skeleton_for_band("8-11") == "the-cave-of-echoes"


def test_select_skeleton_for_band_skips_non_eligible_skeleton() -> None:
    """10-13's alphabetically-first skeleton (the-clocktower-cipher) is
    non-eligible and must be skipped in favor of the next eligible one."""
    assert select_skeleton_for_band("10-13") == "the-hollow-lighthouse"


def test_select_skeleton_for_band_returns_none_for_unknown_band() -> None:
    """A band with no skeleton directory returns None, not an error."""
    assert select_skeleton_for_band("99-100") is None
