"""Tests for W2.2 tone derivation (story_requests/tone.py, D5/D18)."""

from __future__ import annotations

from cyo_adventure.story_requests.tone import (
    DEFAULT_TONE,
    TONE_VOCABULARY,
    derive_tone,
)
from cyo_adventure.storybook.models import AgeBand

# ---------------------------------------------------------------------------
# Default and no-match behavior
# ---------------------------------------------------------------------------


def test_default_tone_is_gentle() -> None:
    assert DEFAULT_TONE == "gentle"


def test_no_keyword_match_defaults_to_gentle() -> None:
    tone = derive_tone("a story about visiting grandma's garden", AgeBand.BAND_8_11)
    assert tone == "gentle"


def test_derived_tone_always_in_vocabulary() -> None:
    for band in AgeBand:
        for text in ("a scary story", "something funny", "a sad tale", ""):
            assert derive_tone(text, band) in TONE_VOCABULARY


# ---------------------------------------------------------------------------
# Positive keyword detection, one per tone, at a band that offers it
# ---------------------------------------------------------------------------


def test_funny_keyword_detected_at_3_5() -> None:
    assert derive_tone("a silly story about a goofy dog", AgeBand.BAND_3_5) == "funny"


def test_exciting_keyword_detected_at_3_5() -> None:
    assert (
        derive_tone("a thrilling adventure on a pirate ship", AgeBand.BAND_3_5)
        == "exciting"
    )


def test_gentle_keyword_detected_explicitly() -> None:
    assert derive_tone("a cozy bedtime story", AgeBand.BAND_3_5) == "gentle"


def test_mysterious_keyword_detected_at_5_8() -> None:
    assert derive_tone("a mystery with a hidden clue", AgeBand.BAND_5_8) == "mysterious"


def test_a_little_spooky_keyword_detected_at_8_11() -> None:
    assert (
        derive_tone("a spooky story about a haunted house", AgeBand.BAND_8_11)
        == "a_little_spooky"
    )


def test_scary_keyword_detected_at_13_16() -> None:
    assert derive_tone("a truly terrifying horror story", AgeBand.BAND_13_16) == "scary"


def test_sad_keyword_detected_at_13_16() -> None:
    assert (
        derive_tone("a bittersweet, heartbreaking story", AgeBand.BAND_13_16) == "sad"
    )


# ---------------------------------------------------------------------------
# The cap ladder (D5: a requested tone can narrow but never widen the band)
# ---------------------------------------------------------------------------


def test_scary_at_8_11_caps_to_a_little_spooky() -> None:
    """The plan's own worked example."""
    assert derive_tone("a scary story", AgeBand.BAND_8_11) == "a_little_spooky"


def test_scary_at_5_8_caps_to_mysterious() -> None:
    assert derive_tone("a scary story", AgeBand.BAND_5_8) == "mysterious"


def test_scary_at_3_5_caps_to_gentle() -> None:
    assert derive_tone("a scary story", AgeBand.BAND_3_5) == "gentle"


def test_scary_available_unclamped_at_13_16_and_up() -> None:
    assert derive_tone("a scary story", AgeBand.BAND_13_16) == "scary"
    assert derive_tone("a scary story", AgeBand.BAND_16_PLUS) == "scary"


def test_a_little_spooky_at_5_8_caps_to_mysterious() -> None:
    assert derive_tone("a spooky ghost story", AgeBand.BAND_5_8) == "mysterious"


def test_a_little_spooky_at_3_5_caps_to_gentle() -> None:
    assert derive_tone("a spooky ghost story", AgeBand.BAND_3_5) == "gentle"


def test_mysterious_at_3_5_caps_to_gentle() -> None:
    assert derive_tone("a mystery with a puzzle", AgeBand.BAND_3_5) == "gentle"


def test_sad_at_8_11_caps_to_gentle_no_intermediate_step() -> None:
    """sad has no lesser sibling in the P-B vocabulary; it steps straight to
    gentle rather than through a_little_spooky/mysterious."""
    assert (
        derive_tone("a heartbreaking, tearjerker story", AgeBand.BAND_8_11) == "gentle"
    )


def test_funny_and_exciting_never_capped() -> None:
    for band in AgeBand:
        assert derive_tone("a silly, funny story", band) == "funny"
        assert derive_tone("a thrilling adventure", band) == "exciting"


# ---------------------------------------------------------------------------
# Detection priority when multiple tones' keywords are present
# ---------------------------------------------------------------------------


def test_scary_keyword_wins_over_funny_when_both_present() -> None:
    text = "a funny but truly terrifying story"
    assert derive_tone(text, AgeBand.BAND_16_PLUS) == "scary"


def test_case_insensitive_matching() -> None:
    assert derive_tone("A SCARY STORY", AgeBand.BAND_16_PLUS) == "scary"
