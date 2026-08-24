"""Unit tests for the reading-state replay validator (Finding 2)."""

from __future__ import annotations

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.player import StoryEngine
from cyo_adventure.player.replay import _check_var_value, validate_reading_state
from cyo_adventure.storybook.models import Storybook, Variable, VariableType


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
    # validate_reading_state's documented contract is None on success (see
    # its docstring's Raises section); a clean return IS the pass signal.
    result = validate_reading_state(
        _blob(),
        current_node="n_start",
        var_state={"courage": 0},
        path=["n_start"],
        visit_set=["n_start"],
        choice_path=None,
        save_slots={},
        seed_var_state=None,
    )
    assert result is None


@pytest.mark.unit
def test_unknown_current_node_rejected() -> None:
    blob = _blob()
    with pytest.raises(
        ValidationError, match=r"current_node is not a node in this story version"
    ):
        validate_reading_state(
            blob,
            current_node="n_ghost",
            var_state={"courage": 0},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
            save_slots={},
            seed_var_state=None,
        )


@pytest.mark.unit
def test_unknown_path_node_rejected() -> None:
    blob = _blob()
    with pytest.raises(
        ValidationError, match=r"path references a node not in this story version"
    ):
        validate_reading_state(
            blob,
            current_node="n_start",
            var_state={"courage": 0},
            path=["n_start", "n_ghost"],
            visit_set=["n_start"],
            choice_path=None,
            save_slots={},
            seed_var_state=None,
        )


@pytest.mark.unit
def test_undeclared_var_key_rejected() -> None:
    blob = _blob()
    with pytest.raises(
        ValidationError, match=r"var_state contains an undeclared variable"
    ):
        validate_reading_state(
            blob,
            current_node="n_start",
            var_state={"courage": 0, "sneaky": 1},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
            save_slots={},
            seed_var_state=None,
        )


@pytest.mark.unit
def test_out_of_bounds_int_rejected() -> None:
    blob = _blob()
    with pytest.raises(ValidationError, match=r"is out of declared bounds"):
        validate_reading_state(
            blob,
            current_node="n_start",
            var_state={"courage": 99},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
            save_slots={},
            seed_var_state=None,
        )


@pytest.mark.unit
def test_replay_accepts_genuine_state() -> None:
    result = validate_reading_state(
        _blob(),
        current_node="n_end",
        var_state={"courage": 2},
        path=["n_start", "n_end"],
        visit_set=["n_start", "n_end"],
        choice_path=["c_go"],
        save_slots={},
        seed_var_state=None,
    )
    assert result is None


@pytest.mark.unit
def test_replay_rejects_forged_var_state() -> None:
    blob = _blob()
    with pytest.raises(
        ValidationError,
        match=r"submitted reading state does not match a replay of choice_path",
    ):
        validate_reading_state(
            blob,
            current_node="n_end",
            var_state={"courage": 5},  # replay yields 2, not 5
            path=["n_start", "n_end"],
            visit_set=["n_start", "n_end"],
            choice_path=["c_go"],
            save_slots={},
            seed_var_state=None,
        )


@pytest.mark.unit
def test_replay_rejects_illegal_choice_id() -> None:
    blob = _blob()
    with pytest.raises(
        ValidationError, match=r"choice_path contains an illegal choice"
    ):
        validate_reading_state(
            blob,
            current_node="n_end",
            var_state={"courage": 2},
            path=["n_start", "n_end"],
            visit_set=["n_start", "n_end"],
            choice_path=["c_nope"],
            save_slots={},
            seed_var_state=None,
        )


@pytest.mark.unit
def test_corrupt_blob_rejected_generically() -> None:
    with pytest.raises(
        ValidationError,
        match=r"story version failed schema validation \(corrupt, or no longer permitted\)",
    ):
        validate_reading_state(
            {"not": "a story"},
            current_node="n_start",
            var_state={},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
            save_slots={},
            seed_var_state=None,
        )


@pytest.mark.unit
def test_corrupt_blob_error_does_not_leak_schema_detail() -> None:
    """CWE-209: the raised error must be a generic message, not the raw
    pydantic ValidationError detail (which would echo the corrupt payload).
    """
    with pytest.raises(
        ValidationError,
        match=r"story version failed schema validation \(corrupt, or no longer permitted\)",
    ) as exc_info:
        validate_reading_state(
            {"not": "a story"},
            current_node="n_start",
            var_state={},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
            save_slots={},
            seed_var_state=None,
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
    blob = _blob()
    with pytest.raises(
        ValidationError, match=r"current_node must be the last entry of path"
    ):
        validate_reading_state(
            blob,
            current_node="n_start",
            var_state={"courage": 0},
            path=["n_start", "n_end"],
            visit_set=["n_start", "n_end"],
            choice_path=None,
            save_slots={},
            seed_var_state=None,
        )


@pytest.mark.unit
def test_missing_declared_variable_rejected() -> None:
    """Omitting a declared variable must not fall back to its implicit default."""
    blob = _blob()
    with pytest.raises(
        ValidationError, match=r"var_state is missing a declared variable"
    ):
        validate_reading_state(
            blob,
            current_node="n_start",
            var_state={},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
            save_slots={},
            seed_var_state=None,
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
    with pytest.raises(
        ValidationError, match=r"exceeds the float64-safe integer range"
    ):
        validate_reading_state(
            blob,
            current_node="n_start",
            var_state={"courage": 2**53},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
            save_slots={},
            seed_var_state=None,
        )


@pytest.mark.unit
def test_unbounded_int_var_at_float64_safe_bound_accepted() -> None:
    """A save value exactly at 2**53 - 1 on an unbounded int variable passes."""
    blob = _blob()
    blob["variables"] = [{"name": "courage", "type": "int", "initial": 0}]
    result = validate_reading_state(
        blob,
        current_node="n_start",
        var_state={"courage": 2**53 - 1},
        path=["n_start"],
        visit_set=["n_start"],
        choice_path=None,
        save_slots={},
        seed_var_state=None,
    )
    assert result is None


@pytest.mark.unit
def test_visit_set_only_forgery_rejected() -> None:
    """A visit_set entry that is a real node id but was never actually visited
    can only be caught by full replay, not the id-membership check alone.
    """
    blob = _blob()
    with pytest.raises(
        ValidationError,
        match=r"submitted reading state does not match a replay of choice_path",
    ):
        validate_reading_state(
            blob,
            current_node="n_start",
            var_state={"courage": 0},
            path=["n_start"],
            visit_set=["n_start", "n_end"],
            choice_path=[],
            save_slots={},
            seed_var_state=None,
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
    result = validate_reading_state(
        _bool_blob(),
        current_node="n_start",
        var_state={"has_key": True},
        path=["n_start"],
        visit_set=["n_start"],
        choice_path=None,
        save_slots={},
        seed_var_state=None,
    )
    assert result is None


@pytest.mark.unit
def test_bool_variable_rejects_non_boolean_value() -> None:
    blob = _bool_blob()
    with pytest.raises(ValidationError, match=r"requires a boolean value"):
        validate_reading_state(
            blob,
            current_node="n_start",
            var_state={"has_key": 1},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
            save_slots={},
            seed_var_state=None,
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
    result = validate_reading_state(
        _looping_blob(),
        current_node="n_end",
        var_state={},
        path=["n_start", "n_loop", "n_start", "n_loop", "n_end"],
        visit_set=["n_start", "n_loop", "n_end"],
        choice_path=["c_advance", "c_back", "c_advance", "c_finish"],
        save_slots={},
        seed_var_state=None,
    )
    assert result is None


# ---------------------------------------------------------------------------
# Seed-aware replay: _check_replay must begin from the server-held seed, not
# from declared initials (see player/replay.py::_check_replay).
# ---------------------------------------------------------------------------


def _seeded_story_blob() -> dict[str, object]:
    """A two-node story declaring `might` int 0..2, initial 0, one choice, one ending."""
    return {
        "schema_version": "2.0",
        "id": "s_seeded",
        "version": 1,
        "title": "Seeded Synthetic",
        "metadata": _meta(),
        "variables": [
            {"name": "might", "type": "int", "initial": 0, "min": 0, "max": 2}
        ],
        "start_node": "n_start",
        "nodes": [
            {
                "id": "n_start",
                "body": "Start here.",
                "on_enter": [],
                "choices": [
                    {
                        "id": "c_press_on",
                        "label": "Press on",
                        "target": "n_end",
                        "effects": [],
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
def test_replay_of_a_seeded_read_starts_from_the_seed() -> None:
    """A seeded read replayed from declared initials reproduces nothing.

    Before this change, _check_replay always called engine.start(), so a
    read seeded with might=2 replayed as might=0. Every downstream
    comparison then failed, and the child's legitimate save was rejected
    as tampered.
    """
    blob = _seeded_story_blob()  # declares might int 0..2, initial 0
    story = Storybook.model_validate(blob)
    engine = StoryEngine(story)
    state = engine.start_continuation({"might": 2})
    state = engine.choose(state, "c_press_on")

    validate_reading_state(
        blob,
        current_node=state.current_node,
        var_state=dict(state.var_state),
        path=list(state.path),
        visit_set=sorted(state.visit_set),
        choice_path=["c_press_on"],
        save_slots={},
        seed_var_state={"might": 2},
    )  # must not raise


@pytest.mark.unit
def test_replay_rejects_a_state_claiming_a_seed_it_was_not_given() -> None:
    """The seed is server-held, so a mismatched claim is the tamper case.

    This is the assertion that keeps seeding from becoming a
    client-controlled way to set arbitrary variables: replaying with the
    seed the SERVER recorded must fail when the submitted state was
    reached with a different one.
    """
    blob = _seeded_story_blob()
    story = Storybook.model_validate(blob)
    engine = StoryEngine(story)
    state = engine.choose(engine.start_continuation({"might": 2}), "c_press_on")
    # Precomputed outside the `with` block: check_pytest_raises_scope.py (S5778)
    # allows exactly one non-safe call in a pytest.raises body, and
    # validate_reading_state is the call under test.
    visit_set = sorted(state.visit_set)

    with pytest.raises(ValidationError, match="does not match a replay"):
        validate_reading_state(
            blob,
            current_node=state.current_node,
            var_state=dict(state.var_state),
            path=list(state.path),
            visit_set=visit_set,
            choice_path=["c_press_on"],
            save_slots={},
            seed_var_state=None,
        )


@pytest.mark.unit
def test_an_unseeded_replay_is_unchanged() -> None:
    """The existing behaviour is the seed_var_state=None case, exactly."""
    result = validate_reading_state(
        _blob(),
        current_node="n_end",
        var_state={"courage": 2},
        path=["n_start", "n_end"],
        visit_set=["n_start", "n_end"],
        choice_path=["c_go"],
        save_slots={},
        seed_var_state=None,
    )
    assert result is None


# ---------------------------------------------------------------------------
# B1: save_slots was the one persisted field this gate did not cover
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_empty_save_slots_accepted() -> None:
    """The only value any real client sends today."""
    result = validate_reading_state(
        _blob(),
        current_node="n_start",
        var_state={"courage": 0},
        path=["n_start"],
        visit_set=["n_start"],
        choice_path=None,
        save_slots={},
        seed_var_state=None,
    )
    assert result is None


@pytest.mark.unit
def test_non_empty_save_slots_rejected() -> None:
    """A slot must not be persisted while nothing can validate or consume one.

    save_slots was client-writable, assigned straight onto the JSONB column, and
    the only reading-state field this gate omitted, which defeated the
    anti-forgery intent stated two lines above the call site. No producer or
    consumer exists, so the field was attack surface with no function.
    """
    blob = _blob()
    with pytest.raises(ValidationError, match="save_slots must be empty"):
        validate_reading_state(
            blob,
            current_node="n_start",
            var_state={"courage": 0},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
            save_slots={"checkpoint": {"current_node": "n_start"}},
            seed_var_state=None,
        )


@pytest.mark.unit
def test_save_slots_rejection_names_the_offending_slot() -> None:
    """The error identifies a slot, so a client can tell which key was refused."""
    blob = _blob()
    with pytest.raises(ValidationError) as excinfo:
        validate_reading_state(
            blob,
            current_node="n_start",
            var_state={"courage": 0},
            path=["n_start"],
            visit_set=["n_start"],
            choice_path=None,
            save_slots={"zulu": {}, "alpha": {}},
            seed_var_state=None,
        )
    assert excinfo.value.details["field"] == "save_slots"
    # Deterministically the first key in sorted order, so the message is stable.
    assert excinfo.value.details["value"] == "alpha"


@pytest.mark.unit
def test_a_forged_slot_is_refused_before_the_structural_floor_runs() -> None:
    """Slot refusal precedes the node/variable checks.

    Ordering matters for the error a client sees: a body that forges both a slot
    and a bad node should be told about the slot, since that is the field with no
    legitimate non-empty value at all.
    """
    blob = _blob()
    with pytest.raises(ValidationError, match="save_slots must be empty"):
        validate_reading_state(
            blob,
            current_node="does_not_exist",
            var_state={"courage": 0},
            path=["does_not_exist"],
            visit_set=["does_not_exist"],
            choice_path=None,
            save_slots={"forged": {}},
            seed_var_state=None,
        )


# ---------------------------------------------------------------------------
# Boundary and branch cover for `_check_var_value`.
#
# Exercised directly rather than through `validate_reading_state`: this is a
# pure, total function over (key, value, var), and driving it straight lets a
# test name the exact boundary it pins. Going through the public entry point
# would need a whole blob per case and could still only reach one side of each
# comparison.
#
# Written against the 2026-08-15 mutation run, which left 30 surviving mutants
# in this function (the single largest cluster in `player/replay.py`) while
# every one of its error MESSAGES was already asserted elsewhere in this file.
# That combination is the signature of untested comparison boundaries: an
# `is out of declared bounds` test that passes `min - 5` kills nothing that
# `min - 1` does not, and says nothing about `<` versus `<=`. Each case below
# is therefore paired: the last accepted value and the first rejected one.
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckVarValueBoundaries:
    """Exact accept/reject boundaries for a declared variable's value."""

    @staticmethod
    def _int_var(*, minimum: int | None = None, maximum: int | None = None) -> Variable:
        return Variable(
            name="courage", type=VariableType.INT, initial=0, min=minimum, max=maximum
        )

    # Bind this to a local BEFORE a `pytest.raises` block, never call it
    # inside one. S5778 allows exactly one invocation in the body, and the
    # reason is not style: a block holding both `_int_var()` and
    # `_check_var_value(...)` passes if `_int_var` is the thing that raised,
    # so the boundary the test names would go unproven. Every rejection case
    # below therefore reads `var = ...` first.

    def test_value_equal_to_declared_min_is_accepted(self) -> None:
        # Pins `<` rather than `<=`: at exactly the minimum the value is legal.
        _check_var_value("courage", -3, self._int_var(minimum=-3, maximum=3))

    def test_value_one_below_declared_min_is_rejected(self) -> None:
        var = self._int_var(minimum=-3, maximum=3)
        with pytest.raises(ValidationError, match=r"is out of declared bounds"):
            _check_var_value("courage", -4, var)

    def test_value_equal_to_declared_max_is_accepted(self) -> None:
        _check_var_value("courage", 3, self._int_var(minimum=-3, maximum=3))

    def test_value_one_above_declared_max_is_rejected(self) -> None:
        var = self._int_var(minimum=-3, maximum=3)
        with pytest.raises(ValidationError, match=r"is out of declared bounds"):
            _check_var_value("courage", 4, var)

    def test_only_a_min_is_enforced_when_max_is_absent(self) -> None:
        # Pins the `var.max is not None` guard: with no declared max, a large
        # value must pass rather than be compared against `None`.
        var = self._int_var(minimum=0)
        _check_var_value("courage", 10**6, var)
        with pytest.raises(ValidationError, match=r"is out of declared bounds"):
            _check_var_value("courage", -1, var)

    def test_only_a_max_is_enforced_when_min_is_absent(self) -> None:
        var = self._int_var(maximum=0)
        _check_var_value("courage", -(10**6), var)
        with pytest.raises(ValidationError, match=r"is out of declared bounds"):
            _check_var_value("courage", 1, var)

    def test_unbounded_variable_accepts_any_in_range_value(self) -> None:
        _check_var_value("courage", 0, self._int_var())

    def test_float64_safe_boundary_is_inclusive(self) -> None:
        # `> _MAX_FLOAT64_SAFE_INT`, not `>=`: 2**53 - 1 is exactly
        # representable and must be accepted.
        _check_var_value("courage", 2**53 - 1, self._int_var())

    def test_one_past_the_float64_safe_boundary_is_rejected(self) -> None:
        var = self._int_var()
        with pytest.raises(
            ValidationError, match=r"exceeds the float64-safe integer range"
        ):
            _check_var_value("courage", 2**53, var)

    def test_the_float64_check_is_on_magnitude_not_sign(self) -> None:
        # Pins the `abs()`: without it a large NEGATIVE value slips through,
        # which is the half a positive-only test never reaches.
        var = self._int_var()
        _check_var_value("courage", -(2**53 - 1), var)
        with pytest.raises(
            ValidationError, match=r"exceeds the float64-safe integer range"
        ):
            _check_var_value("courage", -(2**53), var)

    def test_bool_is_not_accepted_for_an_int_variable(self) -> None:
        # `isinstance(True, int)` is True in Python, so the explicit bool
        # rejection is load-bearing; both bools are checked because only one
        # of them is falsy.
        var = self._int_var()
        for value in (True, False):
            with pytest.raises(ValidationError, match=r"requires an integer value"):
                _check_var_value("courage", value, var)

    def test_non_integer_is_rejected_for_an_int_variable(self) -> None:
        var = self._int_var()
        for value in ("3", 3.0, None):
            with pytest.raises(ValidationError, match=r"requires an integer value"):
                _check_var_value("courage", value, var)

    def test_bool_variable_accepts_only_real_bools(self) -> None:
        var = Variable(name="has_key", type=VariableType.BOOL, initial=False)
        # Passed through a name, not as a bare literal: ruff's FBT003 flags a
        # boolean positional argument, and both values matter here because
        # only one of them is falsy.
        for accepted in (True, False):
            _check_var_value("has_key", accepted, var)
        for value in (1, 0, "true"):
            with pytest.raises(ValidationError, match=r"requires a boolean value"):
                _check_var_value("has_key", value, var)

    def test_the_raised_error_carries_field_and_value_context(self) -> None:
        # The message alone is asserted throughout this file; the structured
        # context is what an API caller actually reads back. Both land in
        # `details` (ValidationError folds `field`/`value` in there), and the
        # value is stringified on the way.
        var = self._int_var(maximum=3)
        with pytest.raises(ValidationError) as excinfo:
            _check_var_value("courage", 99, var)
        assert excinfo.value.details["field"] == "var_state"
        assert excinfo.value.details["value"] == "99"
