"""Tests for the freeze-split normalizer (2026-08-21 ruling, section 8.2).

Each test reproduces a frozen-field mutation class the 2026-08-21 live round
measured on real one-shot fills (`AL-499`): a story id rewrite, a
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
    filled["nodes"][0]["body"] = "You climb the lane at dusk."  # type: ignore[index]
    filled["nodes"][0]["choices"][0]["label"] = "Open the dome."  # type: ignore[index]
    filled["nodes"][1]["body"] = "The comet holds still on the plate."  # type: ignore[index]
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
            "name": "slides",
            "type": "int",
            "min": 0,
            "max": 5,
            "initial": 5,
            "description": "Unexposed glass slides remaining in the carrier.",
        }
    ]
    filled["nodes"][1]["ending"] = {  # type: ignore[index]
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
    variable = doc["variables"][0]  # type: ignore[index]
    assert variable["name"] == "plates"
    assert variable["max"] == 3
    assert variable["initial"] == 3
    assert variable["description"] == (
        "Unexposed glass slides remaining in the carrier."
    )
    ending = doc["nodes"][1]["ending"]  # type: ignore[index]
    assert ending["id"] == "e1"
    assert ending["kind"] == "completion"
    assert ending["valence"] == "positive"
    assert ending["title"] == "The Tide Kept"
    assert any("story.id" in note for note in result.restored)
    assert any("metadata" in note for note in result.restored)
    assert any("ending.kind" in note for note in result.restored)
    assert any("variables[0].name" in note for note in result.restored)


def test_choice_targets_are_restored_and_labels_kept() -> None:
    """A reply that moves a choice target keeps its label, loses the move."""
    filled = _obedient_fill()
    filled["nodes"][0]["choices"][0]["target"] = "n1"  # type: ignore[index]

    result = normalize_filled_story(_skeleton(), filled)
    choice = result.document["nodes"][0]["choices"][0]  # type: ignore[index]
    assert choice["target"] == "n2"
    assert choice["label"] == "Open the dome."
    assert any("choice.target" in note for note in result.restored)


def test_a_fill_with_a_different_node_count_is_not_normalized() -> None:
    """Overlaying leaves onto a different graph would fabricate a book."""
    filled = _obedient_fill()
    filled["nodes"] = filled["nodes"][:1]  # type: ignore[index]

    result = normalize_filled_story(_skeleton(), filled)
    assert result.skipped_reason is not None
    assert result.document == filled


def test_a_dropped_body_keeps_the_skeleton_directive_for_the_gate() -> None:
    """A missing body is left as the directive so PL-27 still blocks it."""
    filled = _obedient_fill()
    filled["nodes"][0]["body"] = ""  # type: ignore[index]

    result = normalize_filled_story(_skeleton(), filled)
    assert result.document["nodes"][0]["body"] == "<<FILL body>>"  # type: ignore[index]
