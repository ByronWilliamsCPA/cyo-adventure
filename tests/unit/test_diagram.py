"""Unit tests for the skeleton-to-PlantUML diagram transform."""

from __future__ import annotations

import pytest

from cyo_adventure.generation.diagram import _parse_fill, skeleton_to_plantuml


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
def test_output_never_leaks_fill_or_beats() -> None:
    out = skeleton_to_plantuml(_tiny_skeleton())
    assert "<<FILL" not in out
    assert "beats=" not in out
    assert "start'" not in out  # beats prose content


@pytest.mark.unit
def test_transform_is_deterministic() -> None:
    skel = _tiny_skeleton()
    assert skeleton_to_plantuml(skel) == skeleton_to_plantuml(skel)
