"""Tests for the ConceptBrief intake model (WP7).

Verifies field validation, defaults, extra-field rejection, and range checks.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.generation.concept import (
    MAX_ENDING_COUNT,
    MAX_TARGET_NODE_COUNT,
    ConceptBrief,
    StructurePattern,
)
from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_PROTAGONIST: dict[str, Any] = {
    "name": "Captain Rosa",
    "age": 10,
    "role": "explorer",
}

VALID_BRIEF: dict[str, Any] = {
    "title": "The Lost Island",
    "premise": "A young sailor discovers a mysterious island.",
    "protagonist": VALID_PROTAGONIST,
    "point_of_view": "second",
    "age_band": AgeBand.BAND_8_11,
    "reading_level_target": 4.5,
    "tier": 1,
    "tone": "adventurous",
    "themes_allowed": ["friendship", "courage"],
    "content_nogo": ["violence"],
    "target_node_count": 12,
    "ending_count": 3,
    "structure_pattern": StructurePattern.QUEST,
    "desired_variables": [],
    "special_constraints": [],
}


# ---------------------------------------------------------------------------
# Test 1: A fully-specified valid brief parses without error.
# ---------------------------------------------------------------------------


def test_valid_brief_parses() -> None:
    """A fully-specified ConceptBrief with all fields set parses successfully."""
    brief = ConceptBrief(**VALID_BRIEF)
    assert brief.premise == "A young sailor discovers a mysterious island."
    assert brief.title == "The Lost Island"
    assert brief.tier == 1
    assert brief.age_band == AgeBand.BAND_8_11
    assert brief.structure_pattern == StructurePattern.QUEST
    assert brief.protagonist.name == "Captain Rosa"
    assert brief.protagonist.age == 10
    assert brief.protagonist.role == "explorer"


# ---------------------------------------------------------------------------
# Test 2: Unknown field is rejected (extra="forbid").
# ---------------------------------------------------------------------------


def test_unknown_field_rejected() -> None:
    """A ConceptBrief with an unknown field raises a Pydantic ValidationError."""
    bad = dict(VALID_BRIEF)
    bad["unexpected_field"] = "surprise"
    with pytest.raises(PydanticValidationError):
        ConceptBrief(**bad)


def test_unknown_protagonist_field_rejected() -> None:
    """A Protagonist with an unknown field raises a Pydantic ValidationError."""
    bad_protagonist = dict(VALID_PROTAGONIST)
    bad_protagonist["real_name"] = "actual child"
    bad = dict(VALID_BRIEF)
    bad["protagonist"] = bad_protagonist
    with pytest.raises(PydanticValidationError):
        ConceptBrief(**bad)


# ---------------------------------------------------------------------------
# Test 3: Out-of-range tier values and invalid structure_pattern are rejected.
# ---------------------------------------------------------------------------


def test_tier_zero_rejected() -> None:
    """tier=0 is below the allowed range (ge=1) and raises ValidationError."""
    bad = dict(VALID_BRIEF)
    bad["tier"] = 0
    with pytest.raises(PydanticValidationError):
        ConceptBrief(**bad)


def test_tier_three_rejected() -> None:
    """tier=3 is above the allowed range (le=2) and raises ValidationError."""
    bad = dict(VALID_BRIEF)
    bad["tier"] = 3
    with pytest.raises(PydanticValidationError):
        ConceptBrief(**bad)


def test_invalid_structure_pattern_rejected() -> None:
    """An unknown structure_pattern value raises a Pydantic ValidationError."""
    bad = dict(VALID_BRIEF)
    bad["structure_pattern"] = "star_shaped"
    with pytest.raises(PydanticValidationError):
        ConceptBrief(**bad)


def test_protagonist_age_negative_rejected() -> None:
    """Protagonist.age < 0 is rejected (ge=0)."""
    bad = dict(VALID_BRIEF)
    bad["protagonist"] = {**VALID_PROTAGONIST, "age": -1}
    with pytest.raises(PydanticValidationError):
        ConceptBrief(**bad)


def test_protagonist_age_over_limit_rejected() -> None:
    """Protagonist.age > 18 is rejected (le=18)."""
    bad = dict(VALID_BRIEF)
    bad["protagonist"] = {**VALID_PROTAGONIST, "age": 19}
    with pytest.raises(PydanticValidationError):
        ConceptBrief(**bad)


def test_empty_premise_rejected() -> None:
    """An empty premise string violates min_length=1 and raises ValidationError."""
    bad = dict(VALID_BRIEF)
    bad["premise"] = ""
    with pytest.raises(PydanticValidationError):
        ConceptBrief(**bad)


def test_reading_level_negative_rejected() -> None:
    """reading_level_target < 0 is rejected (ge=0)."""
    bad = dict(VALID_BRIEF)
    bad["reading_level_target"] = -0.1
    with pytest.raises(PydanticValidationError):
        ConceptBrief(**bad)


def test_target_node_count_zero_rejected() -> None:
    """target_node_count < 1 is rejected (ge=1)."""
    bad = dict(VALID_BRIEF)
    bad["target_node_count"] = 0
    with pytest.raises(PydanticValidationError):
        ConceptBrief(**bad)


def test_ending_count_zero_rejected() -> None:
    """ending_count < 1 is rejected (ge=1)."""
    bad = dict(VALID_BRIEF)
    bad["ending_count"] = 0
    with pytest.raises(PydanticValidationError):
        ConceptBrief(**bad)


def test_target_node_count_at_max_accepted() -> None:
    """target_node_count exactly at the ADR-011 matrix ceiling is accepted."""
    ok = dict(VALID_BRIEF)
    ok["target_node_count"] = MAX_TARGET_NODE_COUNT
    brief = ConceptBrief(**ok)
    assert brief.target_node_count == MAX_TARGET_NODE_COUNT


def test_target_node_count_over_max_rejected() -> None:
    """target_node_count one over the ADR-011 matrix ceiling is rejected (le=)."""
    bad = dict(VALID_BRIEF)
    bad["target_node_count"] = MAX_TARGET_NODE_COUNT + 1
    with pytest.raises(PydanticValidationError):
        ConceptBrief(**bad)


def test_ending_count_at_max_accepted() -> None:
    """ending_count exactly at the derived ceiling is accepted."""
    ok = dict(VALID_BRIEF)
    ok["ending_count"] = MAX_ENDING_COUNT
    brief = ConceptBrief(**ok)
    assert brief.ending_count == MAX_ENDING_COUNT


def test_ending_count_over_max_rejected() -> None:
    """ending_count one over the derived ceiling is rejected (le=)."""
    bad = dict(VALID_BRIEF)
    bad["ending_count"] = MAX_ENDING_COUNT + 1
    with pytest.raises(PydanticValidationError):
        ConceptBrief(**bad)


# ---------------------------------------------------------------------------
# Test 4: Default values are applied correctly.
# ---------------------------------------------------------------------------


def test_defaults_applied() -> None:
    """Omitting optional fields applies the documented defaults."""
    minimal: dict[str, Any] = {
        "premise": "A quiet adventure.",
        "protagonist": VALID_PROTAGONIST,
        "age_band": AgeBand.BAND_10_13,
        "reading_level_target": 5.0,
        "tier": 2,
        "tone": "cosy",
        "target_node_count": 8,
        "ending_count": 2,
        "structure_pattern": StructurePattern.GAUNTLET,
    }
    brief = ConceptBrief(**minimal)
    assert brief.title is None
    assert brief.point_of_view == "second"
    assert brief.themes_allowed == []
    assert brief.content_nogo == []
    assert brief.desired_variables == []
    assert brief.special_constraints == []
    # A brief with no declared scale is not scale-classified (band budget).
    assert brief.length is None
    assert brief.narrative_style is NarrativeStyle.PROSE


def test_scale_fields_accepted() -> None:
    """A brief may declare an ADR-011 length and narrative style."""
    brief = ConceptBrief(
        **{
            **VALID_BRIEF,
            "length": Length.MEDIUM,
            "narrative_style": NarrativeStyle.GAMEBOOK,
        }
    )
    assert brief.length is Length.MEDIUM
    assert brief.narrative_style is NarrativeStyle.GAMEBOOK


def test_all_structure_patterns_valid() -> None:
    """All five StructurePattern values are accepted by ConceptBrief."""
    for pattern in StructurePattern:
        brief = ConceptBrief(**{**VALID_BRIEF, "structure_pattern": pattern})
        assert brief.structure_pattern == pattern


def test_all_age_bands_valid() -> None:
    """All AgeBand values are accepted by ConceptBrief."""
    for band in AgeBand:
        brief = ConceptBrief(**{**VALID_BRIEF, "age_band": band})
        assert brief.age_band == band


# ---------------------------------------------------------------------------
# Test 5: Control-character stripping at concept intake (F24/#64).
#
# The module docstring documents that the API layer strips control
# characters before a brief reaches the generation prompt; safety-eval
# Finding 5 found no such strip existed anywhere. These tests drive the
# intake-side implementation of that documented mitigation.
# ---------------------------------------------------------------------------


def test_premise_control_chars_stripped() -> None:
    """Control characters embedded in premise are stripped at intake."""
    bad = dict(VALID_BRIEF)
    bad["premise"] = "A quiet\x00\x01 adventure\x07 begins.\x1f"
    brief = ConceptBrief(**bad)
    assert brief.premise == "A quiet adventure begins."


def test_protagonist_name_control_chars_stripped() -> None:
    """Control characters embedded in protagonist.name are stripped at intake."""
    bad = dict(VALID_BRIEF)
    bad["protagonist"] = {**VALID_PROTAGONIST, "name": "Captain\x00 Rosa\x7f"}
    brief = ConceptBrief(**bad)
    assert brief.protagonist.name == "Captain Rosa"


def test_title_control_chars_stripped() -> None:
    """Control characters embedded in title are stripped at intake."""
    bad = dict(VALID_BRIEF)
    bad["title"] = "The\x0bLost\x0cIsland"
    brief = ConceptBrief(**bad)
    assert brief.title == "TheLostIsland"


def test_themes_allowed_list_items_control_chars_stripped() -> None:
    """Control characters in list-typed free-text fields are stripped too."""
    bad = dict(VALID_BRIEF)
    bad["themes_allowed"] = ["friend\x00ship", "cour\x1bage"]
    brief = ConceptBrief(**bad)
    assert brief.themes_allowed == ["friendship", "courage"]


def test_printable_text_unaffected_by_control_char_strip() -> None:
    """Ordinary printable text (including newlines/tabs are NOT stripped)."""
    bad = dict(VALID_BRIEF)
    # \t and \n are control chars but excluded from the strip range per the
    # documented pattern (only \x00-\x08, \x0b, \x0c, \x0e-\x1f, \x7f).
    bad["premise"] = "Line one\nLine two\twith a tab."
    brief = ConceptBrief(**bad)
    assert brief.premise == "Line one\nLine two\twith a tab."
