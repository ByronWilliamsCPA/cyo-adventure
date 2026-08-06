"""Unit tests for the Storybook schema models (schema 2.0)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from cyo_adventure.storybook.models import (
    SCHEMA_MAJOR,
    SCHEMA_MINOR,
    SCHEMA_VERSION,
    Choice,
    ContentFlagLevel,
    Ending,
    EndingKind,
    Node,
    SafetyScope,
    Storybook,
    StoryMetadata,
    Topology,
    Valence,
    is_supported_schema_version,
    level_rank,
    parse_schema_version,
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


def test_schema_version_is_composed_from_major_and_minor():
    assert f"{SCHEMA_MAJOR}.{SCHEMA_MINOR}" == SCHEMA_VERSION


def test_parse_schema_version_splits_major_and_minor():
    assert parse_schema_version("2.0") == (2, 0)
    assert parse_schema_version("2.7") == (2, 7)


@pytest.mark.parametrize(
    "value",
    ["2", "2.0.1", "2.x", "", "v2.0", "2. 0", "-1.0", "2.-1", "2.0\n"],
)
def test_parse_schema_version_rejects_malformed(value: str):
    with pytest.raises(ValueError, match="malformed schema_version"):
        parse_schema_version(value)


def test_supported_version_accepts_current_and_earlier_minors():
    assert is_supported_schema_version("2.0", major=2, minor=2)
    assert is_supported_schema_version("2.1", major=2, minor=2)
    assert is_supported_schema_version("2.2", major=2, minor=2)


def test_supported_version_rejects_a_newer_minor():
    # The rolling-deploy rule in ADR-025 decision 5: an old replica must never
    # be asked to parse a newer minor.
    assert not is_supported_schema_version("2.3", major=2, minor=2)


def test_supported_version_rejects_a_different_major():
    assert not is_supported_schema_version("3.0", major=2, minor=2)
    assert not is_supported_schema_version("1.9", major=2, minor=2)


def test_supported_version_rejects_malformed_without_raising():
    assert not is_supported_schema_version("banana", major=2, minor=2)


_VALID_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "storybook"
    / "valid"
    / "01_hello_world.json"
)


def _story_data_at(schema_version: str) -> dict[str, object]:
    """Load the smallest valid fixture and restamp its schema version.

    Args:
        schema_version: The version string to write into the document.

    Returns:
        dict[str, object]: The parsed fixture with ``schema_version`` replaced.
    """
    data = json.loads(_VALID_FIXTURE.read_text(encoding="utf-8"))
    data["schema_version"] = schema_version
    return data


def test_storybook_accepts_the_current_schema_version():
    story = Storybook.model_validate(_story_data_at(SCHEMA_VERSION))
    assert story.schema_version == SCHEMA_VERSION


def test_storybook_rejects_a_newer_minor():
    newer = f"{SCHEMA_MAJOR}.{SCHEMA_MINOR + 1}"
    data = _story_data_at(newer)
    with pytest.raises(PydanticValidationError, match="unsupported schema_version"):
        Storybook.model_validate(data)


def test_storybook_rejects_a_different_major():
    data = _story_data_at("3.0")
    with pytest.raises(PydanticValidationError, match="unsupported schema_version"):
        Storybook.model_validate(data)


def test_storybook_rejects_a_malformed_version():
    data = _story_data_at("two-point-oh")
    with pytest.raises(PydanticValidationError, match="unsupported schema_version"):
        Storybook.model_validate(data)


def test_unsupported_version_message_names_the_accepted_range():
    data = _story_data_at("3.0")
    with pytest.raises(PydanticValidationError) as excinfo:
        Storybook.model_validate(data)
    assert f"{SCHEMA_MAJOR}.0 through {SCHEMA_VERSION}" in str(excinfo.value)
