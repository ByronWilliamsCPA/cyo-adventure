"""Unit tests for the Storybook schema models (schema 2.0)."""

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.storybook.models import (
    ContentFlagLevel,
    Ending,
    EndingKind,
    SafetyScope,
    StoryMetadata,
    Topology,
    Valence,
    level_rank,
)


def test_new_enum_values():
    assert {v.value for v in Valence} == {"positive", "neutral", "negative"}
    assert {k.value for k in EndingKind} == {
        "success",
        "setback",
        "death",
        "capture",
        "completion",
        "discovery",
    }
    assert {t.value for t in Topology} == {
        "time_cave",
        "gauntlet",
        "branch_and_bottleneck",
        "loop_and_grow",
    }
    assert {s.value for s in SafetyScope} == {
        "peril",
        "scary_imagery",
        "conflict",
        "sad_moment",
    }


def test_content_flag_level_ordering():
    assert ContentFlagLevel.INTENSE.value == "intense"
    assert level_rank(ContentFlagLevel.NONE) < level_rank(ContentFlagLevel.MILD)
    assert level_rank(ContentFlagLevel.MILD) < level_rank(ContentFlagLevel.MODERATE)
    assert level_rank(ContentFlagLevel.MODERATE) < level_rank(ContentFlagLevel.INTENSE)


def test_ending_requires_valence_and_kind():
    ending = Ending(
        id="e1", valence=Valence.POSITIVE, kind=EndingKind.SUCCESS, title="Won"
    )
    assert ending.valence is Valence.POSITIVE
    assert ending.kind is EndingKind.SUCCESS


def test_ending_rejects_free_form_type():
    with pytest.raises(PydanticValidationError):
        Ending(id="e1", type="good", title="Won")  # type: ignore[call-arg]


def _meta_kwargs() -> dict[str, object]:
    return {
        "age_band": "10-13",
        "reading_level": {"scheme": "flesch_kincaid", "target": 4.0, "tolerance": 1.0},
        "tier": 2,
        "themes": [],
        "estimated_minutes": 5,
        "ending_count": 1,
        "content_flags": {"violence": "none", "scariness": "none", "peril": "none"},
        "topology": "branch_and_bottleneck",
    }


def test_story_metadata_requires_topology():
    meta = StoryMetadata.model_validate(_meta_kwargs())
    assert meta.topology is Topology.BRANCH_AND_BOTTLENECK
