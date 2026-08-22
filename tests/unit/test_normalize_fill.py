"""Tests for the freeze-split normalizer (2026-08-21 ruling, section 8.2).

Each test reproduces a frozen-field mutation class the 2026-08-21 live round
measured on real one-shot fills (`AL-515`): a story id rewrite, a
`metadata.themes` retheme, ending kind/valence drift, and a variable whose
machine fields moved while its description was legitimately rethemed. The
normalizer restores the frozen side and keeps the writable side.
"""

from __future__ import annotations

import copy

import pytest

from cyo_adventure.generation.normalize_fill import normalize_filled_story

pytestmark = pytest.mark.unit


def _skeleton() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "id": "sk_test",
        "version": 1,
        "title": "The Glass Comet",
        "metadata": {"age_band": "10-13", "tier": 2, "themes": ["astronomy"]},
        "start_node": "n1",
        "variables": [
            {
                "name": "plates",
                "type": "int",
                "min": 0,
                "max": 3,
                "initial": 3,
                "description": "Unexposed photographic plates remaining.",
            }
        ],
        "nodes": [
            {
                "id": "n1",
                "body": "<<FILL body>>",
                "is_ending": False,
                "choices": [
                    {"id": "c1", "label": "<<FILL label>>", "target": "n2"},
                ],
            },
            {
                "id": "n2",
                "body": "<<FILL body>>",
                "is_ending": True,
                "ending": {
                    "id": "e1",
                    "kind": "completion",
                    "valence": "positive",
                    "title": "Home Safe",
                },
            },
        ],
    }


def _obedient_fill() -> dict[str, object]:
    filled = copy.deepcopy(_skeleton())
    filled["nodes"][0]["body"] = "You climb the lane at dusk."  # pyright: ignore[reportIndexIssue]
    filled["nodes"][0]["choices"][0]["label"] = "Open the dome."  # pyright: ignore[reportIndexIssue]
    filled["nodes"][1]["body"] = "The comet holds still on the plate."  # pyright: ignore[reportIndexIssue]
    return filled


def test_an_obedient_fill_normalizes_to_itself() -> None:
    """No drift means no restorations and an identical document."""
    result = normalize_filled_story(_skeleton(), _obedient_fill())
    assert result.skipped_reason is None
    assert result.restored == ()
    assert result.document == _obedient_fill()


def test_frozen_drift_is_restored_and_writable_retheming_is_kept() -> None:
    """The four measured mutation classes in one document.

    The fill rewrites the story id, rethemes `metadata.themes`, swaps the
    ending kind, moves a variable's bounds, AND legitimately rethemes the
    variable description, the titles, the body, and the label. Frozen fields
    come back from the skeleton; every writable rewrite survives.
    """
    filled = _obedient_fill()
    filled["id"] = "sk_last_codex"
    filled["title"] = "The Tidefall Slides"
    filled["metadata"] = {"age_band": "10-13", "tier": 2, "themes": ["oceanography"]}
    filled["variables"] = [
        {
            "name": "plates",
            "type": "int",
            "min": 0,
            "max": 5,
            "initial": 5,
            "description": "Unexposed glass slides remaining in the carrier.",
        }
    ]
    filled["nodes"][1]["ending"] = {  # pyright: ignore[reportIndexIssue]
        "id": "e_other",
        "kind": "success",
        "valence": "negative",
        "title": "The Tide Kept",
    }

    result = normalize_filled_story(_skeleton(), filled)
    doc = result.document
    assert result.skipped_reason is None
    assert doc["id"] == "sk_test"
    assert doc["title"] == "The Tidefall Slides"
    metadata = doc["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["themes"] == ["astronomy"]
    variable = doc["variables"][0]  # pyright: ignore[reportIndexIssue, reportUnknownVariableType]
    assert variable["name"] == "plates"
    assert variable["max"] == 3
    assert variable["initial"] == 3
    assert variable["description"] == (
        "Unexposed glass slides remaining in the carrier."
    )
    ending = doc["nodes"][1]["ending"]  # pyright: ignore[reportIndexIssue, reportUnknownVariableType]
    assert ending["id"] == "e1"
    assert ending["kind"] == "completion"
    assert ending["valence"] == "positive"
    assert ending["title"] == "The Tide Kept"
    assert any("story.id" in note for note in result.restored)
    assert any("metadata" in note for note in result.restored)
    assert any("ending.kind" in note for note in result.restored)
    assert any("'plates'.max restored" in note for note in result.restored)


def test_choice_targets_are_restored_and_labels_kept() -> None:
    """A reply that moves a choice target keeps its label, loses the move."""
    filled = _obedient_fill()
    filled["nodes"][0]["choices"][0]["target"] = "n1"  # pyright: ignore[reportIndexIssue]

    result = normalize_filled_story(_skeleton(), filled)
    choice = result.document["nodes"][0]["choices"][0]  # pyright: ignore[reportIndexIssue, reportUnknownVariableType]
    assert choice["target"] == "n2"
    assert choice["label"] == "Open the dome."
    assert any(".target restored" in note for note in result.restored)


def test_a_fill_with_a_different_node_count_is_not_normalized() -> None:
    """Overlaying leaves onto a different graph would fabricate a book."""
    filled = _obedient_fill()
    filled["nodes"] = filled["nodes"][:1]  # pyright: ignore[reportIndexIssue]

    result = normalize_filled_story(_skeleton(), filled)
    assert result.skipped_reason is not None
    assert result.document == filled


def test_reordered_nodes_keep_their_prose_on_the_right_graph_positions() -> None:
    """A reordered-but-correct fill is normalized by id, not by position.

    PR #737 review, finding C2: the positional zip transplanted each body
    onto the wrong node while "restoring" the ids, producing a structurally
    perfect document with inverted prose that no downstream gate can catch.
    """
    filled = _obedient_fill()
    filled["nodes"] = list(reversed(filled["nodes"]))  # type: ignore[arg-type]

    result = normalize_filled_story(_skeleton(), filled)
    assert result.skipped_reason is None
    nodes = result.document["nodes"]
    assert nodes[0]["id"] == "n1"  # type: ignore[index]
    assert nodes[0]["body"] == "You climb the lane at dusk."  # type: ignore[index]
    assert nodes[1]["id"] == "n2"  # type: ignore[index]
    assert nodes[1]["body"] == "The comet holds still on the plate."  # type: ignore[index]


def test_reordered_choices_keep_their_labels_on_the_right_targets() -> None:
    """Choice labels follow their choice id, never their list position.

    The reviewer's repro: skeleton offers c1 -> safe_room and c2 -> dark_pit;
    the model returns the same ids reordered. A positional overlay put "climb
    down into the pit" on the safe-room target.
    """
    skeleton: dict[str, object] = {
        "id": "sk_two_choices",
        "title": "Two Doors",
        "metadata": {"age_band": "8-11", "tier": 1},
        "start_node": "fork",
        "nodes": [
            {
                "id": "fork",
                "body": "<<FILL body>>",
                "is_ending": False,
                "choices": [
                    {"id": "c1", "label": "<<FILL label>>", "target": "safe_room"},
                    {"id": "c2", "label": "<<FILL label>>", "target": "dark_pit"},
                ],
            },
            {"id": "safe_room", "body": "<<FILL body>>", "is_ending": True},
            {"id": "dark_pit", "body": "<<FILL body>>", "is_ending": True},
        ],
    }
    filled = copy.deepcopy(skeleton)
    filled["nodes"][0]["body"] = "The tunnel splits."  # type: ignore[index]
    filled["nodes"][0]["choices"] = [  # type: ignore[index]
        {"id": "c2", "label": "Climb down into the pit.", "target": "dark_pit"},
        {"id": "c1", "label": "Stay in the safe room.", "target": "safe_room"},
    ]
    filled["nodes"][1]["body"] = "Safe at last."  # type: ignore[index]
    filled["nodes"][2]["body"] = "Down you go."  # type: ignore[index]

    result = normalize_filled_story(skeleton, filled)
    assert result.skipped_reason is None
    choices = result.document["nodes"][0]["choices"]  # type: ignore[index]
    by_id = {c["id"]: c for c in choices}
    assert by_id["c1"]["target"] == "safe_room"
    assert by_id["c1"]["label"] == "Stay in the safe room."
    assert by_id["c2"]["target"] == "dark_pit"
    assert by_id["c2"]["label"] == "Climb down into the pit."


def test_reordered_variables_keep_their_descriptions() -> None:
    """Variable descriptions follow the variable name, never the position."""
    skeleton = _skeleton()
    skeleton["variables"] = [
        {
            "name": "plates",
            "type": "int",
            "min": 0,
            "max": 3,
            "initial": 3,
            "description": "Plates left.",
        },
        {
            "name": "lamps",
            "type": "int",
            "min": 0,
            "max": 2,
            "initial": 2,
            "description": "Lamps lit.",
        },
    ]
    filled = copy.deepcopy(skeleton)
    filled["nodes"][0]["body"] = "Prose."  # type: ignore[index]
    filled["nodes"][0]["choices"][0]["label"] = "Go."  # type: ignore[index]
    filled["nodes"][1]["body"] = "Done."  # type: ignore[index]
    filled["variables"] = [
        {
            "name": "lamps",
            "type": "int",
            "min": 0,
            "max": 2,
            "initial": 2,
            "description": "Storm lanterns still burning.",
        },
        {
            "name": "plates",
            "type": "int",
            "min": 0,
            "max": 3,
            "initial": 3,
            "description": "Unexposed plates in the satchel.",
        },
    ]

    result = normalize_filled_story(skeleton, filled)
    variables = {v["name"]: v for v in result.document["variables"]}  # type: ignore[union-attr]
    assert variables["plates"]["description"] == "Unexposed plates in the satchel."
    assert variables["lamps"]["description"] == "Storm lanterns still burning."


def test_a_fill_with_renamed_node_ids_is_not_normalized() -> None:
    """A renamed id makes the pairing ambiguous; the gate judges as written."""
    filled = _obedient_fill()
    filled["nodes"][0]["id"] = "n1_renamed"  # type: ignore[index]

    result = normalize_filled_story(_skeleton(), filled)
    assert result.skipped_reason is not None
    # The reason must name BOTH sides of the mismatch. "ids do not align" alone
    # sends the reader back to the raw fill to work out which id moved.
    assert "node ids differ" in result.skipped_reason
    assert "n1" in result.skipped_reason
    assert "n1_renamed" in result.skipped_reason
    assert result.document == filled


def test_a_fill_with_non_object_node_entries_is_not_normalized() -> None:
    """Malformed entries are judged as written, never filtered into alignment.

    The right number of node OBJECTS plus stray strings must not pass the
    count check with the garbage silently discarded: that would launder
    malformed output into a valid-looking book (PR #737 review finding).
    """
    filled = _obedient_fill()
    filled["nodes"] = [*filled["nodes"], "stray", "entries"]  # pyright: ignore[reportGeneralTypeIssues]

    result = normalize_filled_story(_skeleton(), filled)
    assert result.skipped_reason is not None
    assert "not JSON objects" in result.skipped_reason
    assert result.document == filled


def test_a_dropped_body_keeps_the_skeleton_directive_for_the_gate() -> None:
    """A missing body is left as the directive so PL-27 still blocks it."""
    filled = _obedient_fill()
    filled["nodes"][0]["body"] = ""  # pyright: ignore[reportIndexIssue]

    result = normalize_filled_story(_skeleton(), filled)
    assert result.document["nodes"][0]["body"] == "<<FILL body>>"  # pyright: ignore[reportIndexIssue]


def _branching_skeleton() -> dict[str, object]:
    """Return a skeleton whose start node has two distinguishable branches."""
    return {
        "schema_version": "2.0",
        "id": "sk_branch",
        "version": 1,
        "title": "The Lantern and the Pit",
        "metadata": {"age_band": "10-13", "tier": 2, "themes": ["caves"]},
        "start_node": "n1",
        "variables": [
            {
                "name": "lantern",
                "type": "int",
                "min": 0,
                "max": 2,
                "initial": 2,
                "description": "Hours of lantern oil remaining.",
            },
            {
                "name": "rope",
                "type": "bool",
                "initial": False,
                "description": "Whether the rope is tied off at the rim.",
            },
        ],
        "nodes": [
            {
                "id": "n1",
                "body": "<<FILL body>>",
                "is_ending": False,
                "choices": [
                    {"id": "c1", "label": "<<FILL label>>", "target": "dark_pit"},
                    {"id": "c2", "label": "<<FILL label>>", "target": "safe_room"},
                ],
            },
            {
                "id": "dark_pit",
                "body": "<<FILL body>>",
                "is_ending": True,
                "ending": {
                    "id": "e_pit",
                    "kind": "setback",
                    "valence": "negative",
                    "title": "Down in the Dark",
                },
            },
            {
                "id": "safe_room",
                "body": "<<FILL body>>",
                "is_ending": True,
                "ending": {
                    "id": "e_safe",
                    "kind": "completion",
                    "valence": "positive",
                    "title": "Home Safe",
                },
            },
        ],
    }


def _branching_fill() -> dict[str, object]:
    """Return an obedient fill of `_branching_skeleton`, in skeleton order."""
    filled = copy.deepcopy(_branching_skeleton())
    nodes = filled["nodes"]
    assert isinstance(nodes, list)
    nodes[0]["body"] = "The shaft breathes cold air up at you."
    nodes[0]["choices"][0]["label"] = "Climb down into the pit"
    nodes[0]["choices"][1]["label"] = "Stay in the safe room"
    nodes[1]["body"] = "The dark closes over the last rung."
    nodes[2]["body"] = "The safe room's stove is still warm."
    return filled


def _bodies_by_node_id(document: dict[str, object]) -> dict[object, object]:
    """Return each node's body keyed by that node's id."""
    nodes = document["nodes"]
    assert isinstance(nodes, list)
    return {node["id"]: node["body"] for node in nodes}  # pyright: ignore[reportUnknownVariableType]


def _labels_by_target(
    document: dict[str, object], node_id: str
) -> dict[object, object]:
    """Return one node's choice labels keyed by the target each routes to."""
    nodes = document["nodes"]
    assert isinstance(nodes, list)
    node = next(n for n in nodes if n["id"] == node_id)  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    return {choice["target"]: choice["label"] for choice in node["choices"]}


def test_reordered_nodes_keep_each_body_with_its_own_node_id() -> None:
    """A fill that reorders the node list must not move prose between nodes.

    Same count, same id set, different order: matching by position would give
    every node someone else's body, and the document would still be
    structurally valid, so no downstream gate could catch it.
    """
    skeleton = _branching_skeleton()
    filled = _branching_fill()
    nodes = filled["nodes"]
    assert isinstance(nodes, list)
    filled["nodes"] = [nodes[2], nodes[0], nodes[1]]

    result = normalize_filled_story(skeleton, filled)
    assert result.skipped_reason is None
    assert _bodies_by_node_id(result.document) == {
        "n1": "The shaft breathes cold air up at you.",
        "dark_pit": "The dark closes over the last rung.",
        "safe_room": "The safe room's stove is still warm.",
    }


def test_reordered_choices_keep_each_label_with_its_own_target() -> None:
    """A fill that reverses a node's choices must not swap label and target.

    This is the child-facing case: a mis-paired label sends a reader who chose
    to stay in the safe room down into the pit, and the document is valid
    enough that the deterministic gate has nothing to fail on.
    """
    skeleton = _branching_skeleton()
    filled = _branching_fill()
    nodes = filled["nodes"]
    assert isinstance(nodes, list)
    choices = nodes[0]["choices"]  # pyright: ignore[reportUnknownVariableType]
    nodes[0]["choices"] = [choices[1], choices[0]]

    result = normalize_filled_story(skeleton, filled)
    assert result.skipped_reason is None
    assert _labels_by_target(result.document, "n1") == {
        "dark_pit": "Climb down into the pit",
        "safe_room": "Stay in the safe room",
    }


def test_reordered_variables_keep_each_description_with_its_own_variable() -> None:
    """Descriptions follow the variable NAME, not the position in the list."""
    skeleton = _branching_skeleton()
    filled = _branching_fill()
    filled["variables"] = [
        {
            "name": "rope",
            "type": "bool",
            "initial": False,
            "description": "Whether the tide line is roped off.",
        },
        {
            "name": "lantern",
            "type": "int",
            "min": 0,
            "max": 2,
            "initial": 2,
            "description": "Hours of whale-oil light left in the lamp.",
        },
    ]

    result = normalize_filled_story(skeleton, filled)
    assert result.skipped_reason is None
    variables = result.document["variables"]
    assert isinstance(variables, list)
    assert {v["name"]: v["description"] for v in variables} == {
        "lantern": "Hours of whale-oil light left in the lamp.",
        "rope": "Whether the tide line is roped off.",
    }


def test_a_filled_node_id_absent_from_the_skeleton_is_not_normalized() -> None:
    """An unknown node id cannot be matched, so the fill is judged as written."""
    skeleton = _branching_skeleton()
    filled = _branching_fill()
    nodes = filled["nodes"]
    assert isinstance(nodes, list)
    nodes[2]["id"] = "cellar"

    result = normalize_filled_story(skeleton, filled)
    assert result.skipped_reason is not None
    assert "node ids differ" in result.skipped_reason
    assert result.document == filled


def test_a_fill_with_a_different_choice_count_is_not_normalized() -> None:
    """A node whose choice set differs is not normalized, it is handed on.

    Keeping the skeleton's label for a choice the fill never wrote would ship
    a `<<FILL ...>>` directive dressed as prose; discarding an extra choice
    would hide that the fill described different branches.
    """
    skeleton = _branching_skeleton()
    filled = _branching_fill()
    nodes = filled["nodes"]
    assert isinstance(nodes, list)
    nodes[0]["choices"] = nodes[0]["choices"][:1]

    result = normalize_filled_story(skeleton, filled)
    assert result.skipped_reason is not None
    assert "choice ids on node 'n1' differ" in result.skipped_reason
    assert result.document == filled
