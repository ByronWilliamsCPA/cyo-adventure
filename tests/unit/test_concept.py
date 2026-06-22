"""Tests for the ConceptBrief intake model (WP7).

Verifies field validation, defaults, extra-field rejection, and range checks.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.generation.concept import ConceptBrief, StructurePattern
from cyo_adventure.storybook.models import AgeBand

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
