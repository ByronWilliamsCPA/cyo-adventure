"""Unit tests for the skeleton-to-PlantUML diagram transform."""

from __future__ import annotations

from typing import cast

import pytest

from cyo_adventure.generation.diagram import (
    _parse_fill,
    _require_node_id,
    _sanitize_text,
    nodes_of,
    skeleton_to_plantuml,
    valence_split,
)


@pytest.mark.unit
def test_parse_fill_extracts_role_and_words() -> None:
    body = "<<FILL role=setup words=85 beats='Pip looks for a mitten'>>"
    assert _parse_fill(body) == ("setup", 85)


@pytest.mark.unit
def test_parse_fill_handles_completion_role() -> None:
    body = "<<FILL role=completion words=80 beats='a cozy resolution'>>"
    assert _parse_fill(body) == ("completion", 80)


@pytest.mark.unit
def test_parse_fill_returns_none_for_non_fill_body() -> None:
    assert _parse_fill("Once upon a time the fox was warm.") == (None, None)


@pytest.mark.unit
@pytest.mark.parametrize("data", [{}, {"nodes": "not-a-list"}])
def test_nodes_of_returns_empty_list_when_nodes_missing_or_not_a_list(
    data: dict[str, object],
) -> None:
    assert nodes_of(data) == []


def _tiny_skeleton() -> dict[str, object]:
    """A minimal valid-shaped skeleton dict (not gate-validated; transform is pure)."""
    return {
        "title": "Tiny Tale",
        "start_node": "n_start",
        "metadata": {
            "age_band": "3-5",
            "tier": 1,
            "estimated_minutes": 5,
            "topology": "loop_and_grow",
            "ending_count": 1,
        },
        "nodes": [
            {
                "id": "n_start",
                "body": "<<FILL role=setup words=85 beats='start'>>",
                "is_ending": False,
                "choices": [
                    {"id": "c_go", "label": "Go to the end.", "target": "n_end"},
                ],
            },
            {
                "id": "n_end",
                "body": "<<FILL role=completion words=80 beats='done'>>",
                "is_ending": True,
                "ending": {
                    "id": "e_end",
                    "valence": "positive",
                    "kind": "completion",
                    "title": "The End",
                },
            },
        ],
    }


@pytest.mark.unit
def test_transform_wraps_in_startuml_enduml() -> None:
    out = skeleton_to_plantuml(_tiny_skeleton())
    assert out.startswith("@startuml")
    assert out.rstrip().endswith("@enduml")


@pytest.mark.unit
def test_transform_emits_start_transition() -> None:
    out = skeleton_to_plantuml(_tiny_skeleton())
    assert "[*] --> n_start" in out


@pytest.mark.unit
def test_transform_emits_a_state_per_node() -> None:
    out = skeleton_to_plantuml(_tiny_skeleton())
    assert "state n_start" in out
    assert "state n_end" in out


@pytest.mark.unit
def test_transform_emits_labeled_choice_transition() -> None:
    out = skeleton_to_plantuml(_tiny_skeleton())
    assert "n_start --> n_end : Go to the end." in out


@pytest.mark.unit
def test_transform_truncates_long_choice_labels() -> None:
    skel = _tiny_skeleton()
    nodes = skel["nodes"]
    assert isinstance(nodes, list)
    first = nodes[0]
    assert isinstance(first, dict)
    choices = first["choices"]
    assert isinstance(choices, list)
    choice = choices[0]
    assert isinstance(choice, dict)
    choice["label"] = "x" * 80
    out = skeleton_to_plantuml(skel)
    assert ("x" * 40 + "...") in out
    assert ("x" * 41) not in out


@pytest.mark.unit
def test_transform_emits_terminal_transition_for_endings() -> None:
    out = skeleton_to_plantuml(_tiny_skeleton())
    assert "n_end --> [*]" in out


@pytest.mark.unit
def test_non_ending_node_shows_role_and_words() -> None:
    out = skeleton_to_plantuml(_tiny_skeleton())
    assert "n_start : setup · 85w" in out


@pytest.mark.unit
def test_ending_node_shows_kind_valence_and_title() -> None:
    out = skeleton_to_plantuml(_tiny_skeleton())
    assert "n_end : completion (positive)" in out
    assert 'n_end : "The End"' in out


@pytest.mark.unit
def test_ending_node_description_omits_kind_valence_line_when_kind_missing() -> None:
    """A title-only ending (no kind/valence) shows the title line but no
    "kind (valence)" line: the kind/valence isinstance guard is False."""
    skel = _tiny_skeleton()
    nodes = skel["nodes"]
    assert isinstance(nodes, list)
    ending_node = nodes[1]
    assert isinstance(ending_node, dict)
    ending_node["ending"] = {"id": "e_end", "title": "The End"}
    out = skeleton_to_plantuml(skel)
    desc_lines = [line for line in out.splitlines() if line.startswith("n_end : ")]
    assert desc_lines == ['n_end : "The End"']


@pytest.mark.unit
def test_ending_node_description_omits_title_line_when_title_missing() -> None:
    """A kind/valence-only ending (no title) shows the "kind (valence)" line
    but no quoted title line: the title isinstance guard is False."""
    skel = _tiny_skeleton()
    nodes = skel["nodes"]
    assert isinstance(nodes, list)
    ending_node = nodes[1]
    assert isinstance(ending_node, dict)
    ending_node["ending"] = {
        "id": "e_end",
        "valence": "positive",
        "kind": "completion",
    }
    out = skeleton_to_plantuml(skel)
    desc_lines = [line for line in out.splitlines() if line.startswith("n_end : ")]
    assert desc_lines == ["n_end : completion (positive)"]


@pytest.mark.unit
def test_non_ending_node_with_non_fill_body_has_no_description_line() -> None:
    """A non-ending node whose body isn't a FILL directive gets no
    "role · Nw" description line: _parse_fill returns (None, None)."""
    skel = _tiny_skeleton()
    nodes = skel["nodes"]
    assert isinstance(nodes, list)
    start_node = nodes[0]
    assert isinstance(start_node, dict)
    start_node["body"] = "Just some prose with no fill marker."
    out = skeleton_to_plantuml(skel)
    assert not any(line.startswith("n_start : ") for line in out.splitlines())


@pytest.mark.unit
def test_legend_carries_metadata() -> None:
    out = skeleton_to_plantuml(_tiny_skeleton())
    assert "legend right" in out
    assert "Tiny Tale" in out
    assert "Band 3-5" in out
    assert "Tier 1" in out
    assert "loop_and_grow" in out
    assert "endlegend" in out


@pytest.mark.unit
def test_legend_reports_node_and_ending_counts_with_valence_split() -> None:
    out = skeleton_to_plantuml(_tiny_skeleton())
    assert "2 nodes" in out
    assert "1 ending" in out
    assert "1+ / 0n / 0-" in out


@pytest.mark.unit
def test_legend_marks_mvp_tier_when_not_production_eligible() -> None:
    skel = _tiny_skeleton()
    cast("dict[str, object]", skel["metadata"])["production_eligible"] = False
    out = skeleton_to_plantuml(skel)
    assert "MVP/Test tier (not production-eligible)" in out


@pytest.mark.unit
def test_legend_marks_production_eligible_when_true() -> None:
    skel = _tiny_skeleton()
    cast("dict[str, object]", skel["metadata"])["production_eligible"] = True
    out = skeleton_to_plantuml(skel)
    assert "Production-eligible" in out


@pytest.mark.unit
def test_legend_marks_production_eligible_when_field_absent() -> None:
    """StoryMetadata.production_eligible defaults to True; an omitted field
    must render the same as an explicit True, not disappear silently."""
    out = skeleton_to_plantuml(_tiny_skeleton())
    assert "Production-eligible" in out
    assert "MVP/Test tier" not in out


@pytest.mark.unit
def test_legend_shows_scale_axis_when_length_and_style_set() -> None:
    skel = _tiny_skeleton()
    meta = cast("dict[str, object]", skel["metadata"])
    meta["length"] = "short"
    meta["narrative_style"] = "prose"
    out = skeleton_to_plantuml(skel)
    assert "Scale: short · prose" in out


@pytest.mark.unit
def test_legend_shows_scale_axis_with_placeholder_when_only_length_set() -> None:
    skel = _tiny_skeleton()
    cast("dict[str, object]", skel["metadata"])["length"] = "short"
    out = skeleton_to_plantuml(skel)
    assert "Scale: short · ?" in out


@pytest.mark.unit
def test_legend_shows_scale_axis_with_placeholder_when_only_style_set() -> None:
    skel = _tiny_skeleton()
    cast("dict[str, object]", skel["metadata"])["narrative_style"] = "prose"
    out = skeleton_to_plantuml(skel)
    assert "Scale: ? · prose" in out


@pytest.mark.unit
def test_legend_omits_scale_axis_when_length_and_style_both_absent() -> None:
    out = skeleton_to_plantuml(_tiny_skeleton())
    assert "Scale:" not in out


@pytest.mark.unit
def test_output_never_leaks_fill_or_beats() -> None:
    out = skeleton_to_plantuml(_tiny_skeleton())
    assert "<<FILL" not in out
    assert "beats=" not in out
    assert "start'" not in out  # beats prose content


@pytest.mark.unit
def test_transform_is_deterministic() -> None:
    skel = _tiny_skeleton()
    # Two separate renders, bound to names rather than compared inline: the
    # point is that repeated calls agree, and naming them makes that intent
    # explicit and lets pytest report which render diverged. Comparing the
    # calls inline reads as a tautology to static analysis (SonarCloud
    # python:S5863) even though the calls are independent.
    first = skeleton_to_plantuml(skel)
    second = skeleton_to_plantuml(skel)
    assert first == second


@pytest.mark.unit
def test_require_node_id_raises_on_missing_id() -> None:
    with pytest.raises(ValueError, match="missing a valid string id"):
        _require_node_id({"body": "no id here"})


@pytest.mark.unit
def test_require_node_id_raises_on_non_string_id() -> None:
    with pytest.raises(ValueError, match="missing a valid string id"):
        _require_node_id({"id": 42})


@pytest.mark.unit
def test_require_node_id_error_omits_body_prose() -> None:
    # The error must report node keys, not a full repr: a node's FILL
    # directive body can carry long author prose that should never be
    # dumped into logs or CI output.
    node = {"body": "<<FILL role=setup words=99 beats='a secret plot detail'>>"}
    with pytest.raises(ValueError, match="missing a valid string id") as exc_info:
        _require_node_id(node)
    assert "secret plot detail" not in str(exc_info.value)
    assert "keys=" in str(exc_info.value)


@pytest.mark.unit
def test_transform_raises_on_node_missing_id() -> None:
    skel = _tiny_skeleton()
    nodes = skel["nodes"]
    assert isinstance(nodes, list)
    first = nodes[0]
    assert isinstance(first, dict)
    del first["id"]
    with pytest.raises(ValueError, match="missing a valid string id"):
        skeleton_to_plantuml(skel)


@pytest.mark.unit
def test_sanitize_text_collapses_whitespace() -> None:
    assert _sanitize_text("a   b\n\tc") == "a b c"


@pytest.mark.unit
def test_sanitize_text_replaces_double_quotes() -> None:
    assert _sanitize_text('she said "hello"') == "she said 'hello'"


@pytest.mark.unit
def test_transform_escapes_double_quotes_in_ending_title() -> None:
    skel = _tiny_skeleton()
    nodes = skel["nodes"]
    assert isinstance(nodes, list)
    ending_node = nodes[1]
    assert isinstance(ending_node, dict)
    ending = ending_node["ending"]
    assert isinstance(ending, dict)
    ending["title"] = 'The "Best" End'
    out = skeleton_to_plantuml(skel)
    assert "n_end : \"The 'Best' End\"" in out
    assert '"The "Best" End"' not in out


@pytest.mark.unit
def test_valence_split_counts_each_bucket() -> None:
    nodes: list[dict[str, object]] = [
        {"is_ending": True, "ending": {"valence": "positive"}},
        {"is_ending": True, "ending": {"valence": "neutral"}},
        {"is_ending": True, "ending": {"valence": "negative"}},
        {"is_ending": True, "ending": {"valence": "negative"}},
    ]
    assert valence_split(nodes) == (1, 1, 2)


@pytest.mark.unit
def test_valence_split_tolerates_missing_valence() -> None:
    nodes: list[dict[str, object]] = [{"is_ending": True, "ending": {}}]
    assert valence_split(nodes) == (0, 0, 0)


@pytest.mark.unit
def test_valence_split_ignores_non_ending_nodes() -> None:
    nodes: list[dict[str, object]] = [
        {"is_ending": False, "ending": {"valence": "bogus"}}
    ]
    assert valence_split(nodes) == (0, 0, 0)


@pytest.mark.unit
def test_valence_split_raises_on_unrecognized_valence() -> None:
    nodes: list[dict[str, object]] = [
        {"is_ending": True, "ending": {"valence": "bittersweet"}}
    ]
    with pytest.raises(ValueError, match="unrecognized valence"):
        valence_split(nodes)
