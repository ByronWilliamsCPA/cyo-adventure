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


@pytest.mark.unit
def test_corrupt_blob_error_does_not_leak_schema_detail() -> None:
    """CWE-209: the raised error must be a generic message, not the raw
    pydantic ValidationError detail (which would echo the corrupt payload).
    """
    with pytest.raises(ValidationError) as exc_info:
        validate_reading_state(
            {"not": "a story"},
            current_node="n_start",
            var_state={},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
        )
    detail = str(exc_info.value)
    assert (
        detail
        == "story version failed schema validation (corrupt, or no longer permitted)"
    )
    assert "not a story" not in detail
    assert "pydantic" not in detail.lower()


@pytest.mark.unit
def test_current_node_path_mismatch_rejected() -> None:
    """A forged current_node that is a real node id but not path[-1] must 422."""
    with pytest.raises(ValidationError):
        validate_reading_state(
            _blob(),
            current_node="n_start",
            var_state={"courage": 0},
            path=["n_start", "n_end"],
            visit_set=["n_start", "n_end"],
            choice_path=None,
        )


@pytest.mark.unit
def test_missing_declared_variable_rejected() -> None:
    """Omitting a declared variable must not fall back to its implicit default."""
    with pytest.raises(ValidationError):
        validate_reading_state(
            _blob(),
            current_node="n_start",
            var_state={},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
        )


@pytest.mark.unit
def test_unbounded_int_var_above_float64_safe_range_rejected() -> None:
    """A save value at or beyond 2**53 on an unbounded int variable is rejected.

    Python holds such ints exactly while the client's IEEE-754 doubles round
    them, so validator and player could disagree about a forged save; the
    structural floor caps magnitude at the float64-exact range.
    """
    blob = _blob()
    blob["variables"] = [{"name": "courage", "type": "int", "initial": 0}]
    with pytest.raises(ValidationError):
        validate_reading_state(
            blob,
            current_node="n_start",
            var_state={"courage": 2**53},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
        )


@pytest.mark.unit
def test_unbounded_int_var_at_float64_safe_bound_accepted() -> None:
    """A save value exactly at 2**53 - 1 on an unbounded int variable passes."""
    blob = _blob()
    blob["variables"] = [{"name": "courage", "type": "int", "initial": 0}]
    validate_reading_state(
        blob,
        current_node="n_start",
        var_state={"courage": 2**53 - 1},
        path=["n_start"],
        visit_set=["n_start"],
        choice_path=None,
    )


@pytest.mark.unit
def test_visit_set_only_forgery_rejected() -> None:
    """A visit_set entry that is a real node id but was never actually visited
    can only be caught by full replay, not the id-membership check alone.
    """
    with pytest.raises(ValidationError):
        validate_reading_state(
            _blob(),
            current_node="n_start",
            var_state={"courage": 0},
            path=["n_start"],
            visit_set=["n_start", "n_end"],
            choice_path=[],
        )


def _bool_blob() -> dict[str, object]:
    """Single-node ending story with one bool variable, no int variable."""
    return {
        "schema_version": "2.0",
        "id": "s_bool",
        "version": 1,
        "title": "Bool Synthetic",
        "metadata": _meta(),
        "variables": [{"name": "has_key", "type": "bool", "initial": False}],
        "start_node": "n_start",
        "nodes": [
            {
                "id": "n_start",
                "body": "Start here.",
                "on_enter": [],
                "is_ending": True,
                "ending": {
                    "id": "e_only",
                    "valence": "positive",
                    "kind": "success",
                    "title": "End",
                },
                "choices": [],
            }
        ],
    }


@pytest.mark.unit
def test_bool_variable_accepts_boolean_value() -> None:
    validate_reading_state(
        _bool_blob(),
        current_node="n_start",
        var_state={"has_key": True},
        path=["n_start"],
        visit_set=["n_start"],
        choice_path=None,
    )


@pytest.mark.unit
def test_bool_variable_rejects_non_boolean_value() -> None:
    with pytest.raises(ValidationError):
        validate_reading_state(
            _bool_blob(),
            current_node="n_start",
            var_state={"has_key": 1},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
        )


def _looping_blob() -> dict[str, object]:
    """A story with a loop: n_start <-> n_loop, then n_loop -> n_end."""
    return {
        "schema_version": "2.0",
        "id": "s_loop",
        "version": 1,
        "title": "Loop Synthetic",
        "metadata": _meta(),
        "variables": [],
        "start_node": "n_start",
        "nodes": [
            {
                "id": "n_start",
                "body": "Start.",
                "on_enter": [],
                "choices": [
                    {
                        "id": "c_advance",
                        "label": "Advance",
                        "target": "n_loop",
                        "effects": [],
                    }
                ],
            },
            {
                "id": "n_loop",
                "body": "Loop point.",
                "on_enter": [],
                "choices": [
                    {
                        "id": "c_back",
                        "label": "Back",
                        "target": "n_start",
                        "effects": [],
                    },
                    {
                        "id": "c_finish",
                        "label": "Finish",
                        "target": "n_end",
                        "effects": [],
                    },
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
def test_replay_accepts_looping_conformance_fixture() -> None:
    """A choice sequence that revisits n_start via n_loop before finishing must
    replay cleanly: path records every visit, visit_set only the distinct ids.
    """
    validate_reading_state(
        _looping_blob(),
        current_node="n_end",
        var_state={},
        path=["n_start", "n_loop", "n_start", "n_loop", "n_end"],
        visit_set=["n_start", "n_loop", "n_end"],
        choice_path=["c_advance", "c_back", "c_advance", "c_finish"],
    )
