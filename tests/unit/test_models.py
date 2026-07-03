"""Unit tests for the Storybook schema models (schema 2.0)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.storybook.models import (
    SCHEMA_VERSION,
    Choice,
    ContentFlagLevel,
    Ending,
    EndingKind,
    Node,
    SafetyScope,
    StoryMetadata,
    Topology,
    Valence,
    level_rank,
)
from cyo_adventure.storybook.schema_export import build_schema


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
        "open_map",
        "sorting_hat",
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


def test_node_safety_scope_defaults_empty_and_accepts_values():
    plain = Node(id="n1", body="x", choices=[Choice(id="c1", label="go", target="n2")])
    assert plain.safety_scope == []
    scoped = Node(
        id="n1",
        body="x",
        choices=[Choice(id="c1", label="go", target="n2")],
        safety_scope=[SafetyScope.PERIL],
    )
    assert scoped.safety_scope == [SafetyScope.PERIL]


def test_schema_version_is_2_0():
    assert SCHEMA_VERSION == "2.0"


def test_exported_schema_file_matches_model():
    path = Path(__file__).resolve().parents[2] / "schema" / "storybook.schema.json"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk == build_schema()
