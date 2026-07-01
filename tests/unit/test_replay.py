"""Unit tests for the reading-state replay validator (Finding 2)."""

from __future__ import annotations

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.player.replay import validate_reading_state


def _meta() -> dict[str, object]:
    return {
        "age_band": "10-13",
        "reading_level": {"scheme": "flesch_kincaid", "target": 4.0, "tolerance": 1.0},
        "tier": 2,
        "themes": [],
        "estimated_minutes": 5,
        "ending_count": 1,
        "topology": "branch_and_bottleneck",
        "content_flags": {"violence": "none", "scariness": "none", "peril": "none"},
    }


def _blob() -> dict[str, object]:
    """A two-node story: start -> (choice c_go) -> ending, one int var `courage`."""
    return {
        "schema_version": "2.0",
        "id": "s_syn",
        "version": 1,
        "title": "Synthetic",
        "metadata": _meta(),
        "variables": [
            {"name": "courage", "type": "int", "initial": 0, "min": 0, "max": 5}
        ],
        "start_node": "n_start",
        "nodes": [
            {
                "id": "n_start",
                "body": "Start here.",
                "on_enter": [],
                "choices": [
                    {
                        "id": "c_go",
                        "label": "Go",
                        "target": "n_end",
                        "effects": [{"op": "inc", "var": "courage", "value": 2}],
                    }
                ],
            },
            {
                "id": "n_end",
                "body": "Done.",
                "is_ending": True,
                "ending": {
                    "id": "e_end",
                    "valence": "positive",
                    "kind": "success",
                    "title": "End",
                },
                "choices": [],
            },
        ],
    }


@pytest.mark.unit
def test_structural_floor_accepts_start_state_without_choice_path() -> None:
    validate_reading_state(
        _blob(),
        current_node="n_start",
        var_state={"courage": 0},
        path=["n_start"],
        visit_set=["n_start"],
        choice_path=None,
    )


@pytest.mark.unit
def test_unknown_current_node_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_reading_state(
            _blob(),
            current_node="n_ghost",
            var_state={"courage": 0},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
        )


@pytest.mark.unit
def test_unknown_path_node_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_reading_state(
            _blob(),
            current_node="n_start",
            var_state={"courage": 0},
            path=["n_start", "n_ghost"],
            visit_set=["n_start"],
            choice_path=None,
        )


@pytest.mark.unit
def test_undeclared_var_key_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_reading_state(
            _blob(),
            current_node="n_start",
            var_state={"courage": 0, "sneaky": 1},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
        )


@pytest.mark.unit
def test_out_of_bounds_int_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_reading_state(
            _blob(),
            current_node="n_start",
            var_state={"courage": 99},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
        )


@pytest.mark.unit
def test_replay_accepts_genuine_state() -> None:
    validate_reading_state(
        _blob(),
        current_node="n_end",
        var_state={"courage": 2},
        path=["n_start", "n_end"],
        visit_set=["n_start", "n_end"],
        choice_path=["c_go"],
    )


@pytest.mark.unit
def test_replay_rejects_forged_var_state() -> None:
    with pytest.raises(ValidationError):
        validate_reading_state(
            _blob(),
            current_node="n_end",
            var_state={"courage": 5},  # replay yields 2, not 5
            path=["n_start", "n_end"],
            visit_set=["n_start", "n_end"],
            choice_path=["c_go"],
        )


@pytest.mark.unit
def test_replay_rejects_illegal_choice_id() -> None:
    with pytest.raises(ValidationError):
        validate_reading_state(
            _blob(),
            current_node="n_end",
            var_state={"courage": 2},
            path=["n_start", "n_end"],
            visit_set=["n_start", "n_end"],
            choice_path=["c_nope"],
        )


@pytest.mark.unit
def test_corrupt_blob_rejected_generically() -> None:
    with pytest.raises(ValidationError):
        validate_reading_state(
            {"not": "a story"},
            current_node="n_start",
            var_state={},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
        )
