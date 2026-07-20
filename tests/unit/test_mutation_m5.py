"""Tests for the M5 state-variation operator family (WS-5 D6).

Covers the operator (retune, rename, gate-choice, add-route, relocate-effect) on
the-flooded-quarter Tier-2 fixture and small stateful fixtures, the section 5.3
acceptance checks (ending coverage, clock re-proof) and the 5.4 state-signature
floor as pure functions, the L2 regression pins (a stranding or dead-branch move
is discarded at the unchanged gate), determinism, and the safety property that no
M5 output ever changes the ending multiset (design section 12 D6).
"""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from typing import cast

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation.acceptance import Stage, run_acceptance
from cyo_adventure.mutation.ops import OpParams
from cyo_adventure.mutation.state_ops import (
    M5,
    M5_OP_ID,
    _assert_endings_untouched,  # pyright: ignore[reportPrivateUsage]
    ending_coverage_gap,
    state_distance,
    state_signature,
    walk_fastest_satisfying_finish,
)
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.walk import walk_configurations

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"
_FLOODED_QUARTER = _SKELETONS_ROOT / "10-13" / "the-flooded-quarter.json"


def _flooded_quarter() -> dict[str, object]:
    """Return the-flooded-quarter Tier-2 skeleton as a raw document."""
    return cast(
        "dict[str, object]",
        json.loads(_FLOODED_QUARTER.read_text(encoding="utf-8")),
    )


def _ending_multiset(story: dict[str, object]) -> list[tuple[str, str, str]]:
    """Return the sorted ``(ending_id, kind, valence)`` multiset of a document."""
    entries: list[tuple[str, str, str]] = []
    for raw_node in cast("list[object]", story["nodes"]):
        node = cast("dict[str, object]", raw_node)
        if node.get("is_ending") is not True:
            continue
        ending = cast("dict[str, object]", node["ending"])
        entries.append(
            (
                cast("str", ending["id"]),
                cast("str", ending["kind"]),
                cast("str", ending["valence"]),
            )
        )
    return sorted(entries)


def _tiny_tier2(initial: int = 2, maximum: int = 2) -> dict[str, object]:
    """Return a small, schema-valid Tier-2 story for pure-helper tests.

    The story is intentionally below the gate's node budget: it exists to exercise
    the pure walk-derived helpers, not the full gate.

    Args:
        initial: The ``oil`` variable's initial value.
        maximum: The ``oil`` variable's max bound.

    Returns:
        dict[str, object]: The raw story document.
    """
    return {
        "schema_version": "2.0",
        "id": "tiny",
        "version": 1,
        "title": "Tiny",
        "start_node": "s",
        "metadata": {
            "age_band": "10-13",
            "reading_level": {"scheme": "flesch_kincaid", "target": 5.0},
            "tier": 2,
            "estimated_minutes": 1,
            "ending_count": 2,
            "topology": "open_map",
            "length": "medium",
            "narrative_style": "prose",
        },
        "variables": [
            {"name": "oil", "type": "int", "initial": initial, "min": 0, "max": maximum}
        ],
        "nodes": [
            {
                "id": "s",
                "body": "b",
                "choices": [
                    {
                        "id": "c1",
                        "label": "go deep",
                        "target": "e_deep",
                        "condition": {">=": [{"var": "oil"}, 2]},
                    },
                    {"id": "c2", "label": "go safe", "target": "e_safe"},
                ],
            },
            {
                "id": "e_deep",
                "body": "b",
                "is_ending": True,
                "ending": {
                    "id": "end_deep",
                    "valence": "positive",
                    "kind": "discovery",
                    "title": "Deep",
                },
            },
            {
                "id": "e_safe",
                "body": "b",
                "is_ending": True,
                "ending": {
                    "id": "end_safe",
                    "valence": "positive",
                    "kind": "success",
                    "title": "Safe",
                },
            },
        ],
    }


def _apply(op_params: OpParams) -> dict[str, object]:
    """Apply M5 to the-flooded-quarter and return the candidate document."""
    parent = _flooded_quarter()
    return M5.apply(parent, op_params, random.Random(0)).candidate


# --- Operator identity and mode dispatch ---


@pytest.mark.unit
def test_m5_is_registered_under_its_op_id() -> None:
    """M5 exposes the stable ``M5`` op id."""
    assert M5.op_id == M5_OP_ID == "M5"


@pytest.mark.unit
def test_m5_rejects_an_unknown_mode_at_preconditions() -> None:
    """A missing or unknown ``mode`` fails preconditions."""
    report = M5.preconditions(_flooded_quarter(), OpParams.of(mode="nope"))
    assert report.satisfied is False


# --- Parent-level preconditions (Tier-2 and stateful band only) ---


@pytest.mark.unit
def test_m5_rejects_a_tier1_parent_at_preconditions() -> None:
    """M5 is Tier-2 only: a Tier-1 skeleton is refused before any apply."""
    tier1 = cast(
        "dict[str, object]",
        json.loads(
            (_SKELETONS_ROOT / "8-11" / "the-cave-of-echoes.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    report = M5.preconditions(
        tier1, OpParams.of(mode="retune", variable="x", initial=1)
    )
    assert report.satisfied is False
    assert any("Tier-2" in reason for reason in report.failures)


@pytest.mark.unit
def test_m5_rejects_a_stateless_band_parent_at_preconditions() -> None:
    """A Tier-2 story in a band that does not permit stateful loops is refused."""
    story = _tiny_tier2()
    cast("dict[str, object]", story["metadata"])["age_band"] = "5-8"
    report = M5.preconditions(
        story, OpParams.of(mode="retune", variable="oil", initial=1)
    )
    assert report.satisfied is False
    assert any("permits stateful loops" in reason for reason in report.failures)


# --- M5a retune / rename ---


@pytest.mark.unit
def test_m5_retune_widening_a_bound_is_held_not_promotable() -> None:
    """A real retune clears every stage and the state floor, and is held on reguide."""
    parent = _flooded_quarter()
    params = OpParams.of(
        mode="retune", variable="oil", max=4, description="Lantern oil, now roomier."
    )
    result = run_acceptance(M5, parent, params, seed=0, parent_slug="fq")
    assert result.discarded_at_stage is None
    assert result.held is True
    assert result.promotable is False
    assert result.reguide_outstanding > 0
    assert any(o.stage is Stage.TIER2_STATE and o.passed for o in result.stages)


@pytest.mark.unit
def test_m5_retune_is_byte_deterministic_for_a_fixed_seed() -> None:
    """Same parent, params, and seed produce a byte-identical candidate."""
    params = OpParams.of(mode="retune", variable="oil", max=4)
    first = _apply(params)
    second = _apply(params)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


@pytest.mark.unit
def test_m5_cosmetic_retune_fails_the_state_floor() -> None:
    """A retune that changes nothing observable (oil initial 3 -> 3) is not a mutant."""
    parent = _flooded_quarter()
    params = OpParams.of(mode="retune", variable="oil", initial=3)
    result = run_acceptance(M5, parent, params, seed=0, parent_slug="fq")
    assert result.discarded_at_stage is Stage.TIER2_STATE
    assert "state-signature distance" in result.discard_reason


@pytest.mark.unit
def test_m5_alpha_rename_is_signature_neutral_and_fails_the_floor_alone() -> None:
    """A pure alpha-rename leaves the state signature identical and floor-fails."""
    parent = _flooded_quarter()
    result = run_acceptance(
        M5,
        parent,
        OpParams.of(mode="rename", variable="oil", new_name="fuel"),
        seed=0,
        parent_slug="fq",
    )
    assert result.discarded_at_stage is Stage.TIER2_STATE
    assert "distance 0.0000" in result.discard_reason


@pytest.mark.unit
def test_m5_alpha_rename_state_distance_is_exactly_zero() -> None:
    """The signature is alpha-invariant: rename yields a zero state distance."""
    parent = _flooded_quarter()
    renamed = _apply(OpParams.of(mode="rename", variable="oil", new_name="fuel"))
    parent_sb = Storybook.model_validate(parent)
    renamed_sb = Storybook.model_validate(renamed)
    parent_sig = state_signature(parent_sb, walk_configurations(parent_sb))
    renamed_sig = state_signature(renamed_sb, walk_configurations(renamed_sb))
    assert state_distance(parent_sig, renamed_sig) == 0.0


# --- M5b gate-choice / add-route / relocate-effect ---


@pytest.mark.unit
def test_m5_gate_choice_with_a_surviving_sibling_is_held() -> None:
    """Gating one of a node's several unconditioned choices is accepted and held."""
    parent = _flooded_quarter()
    params = OpParams.of(
        mode="gate-choice",
        choice="c_n_hub_1",
        gate_var="oil",
        gate_op=">=",
        gate_value=1,
    )
    result = run_acceptance(M5, parent, params, seed=0, parent_slug="fq")
    assert result.discarded_at_stage is None
    assert result.held is True


@pytest.mark.unit
def test_m5_gate_choice_without_a_sibling_needs_a_justification() -> None:
    """Gating a node's lone unconditioned exit is refused without a justification."""
    parent = _flooded_quarter()
    report = M5.preconditions(
        parent,
        OpParams.of(
            mode="gate-choice",
            choice="c_n_start_1",
            gate_var="oil",
            gate_op=">=",
            gate_value=1,
        ),
    )
    assert report.satisfied is False
    assert any("justification" in reason for reason in report.failures)


@pytest.mark.unit
def test_m5_gate_choice_that_creates_a_dead_branch_is_discarded_at_the_gate() -> None:
    """A gate no reachable state satisfies is an L2-11 dead branch, caught by the gate."""
    parent = _flooded_quarter()
    params = OpParams.of(
        mode="gate-choice",
        choice="c_n_hub_1",
        gate_var="oil",
        gate_op=">=",
        gate_value=99,
    )
    result = run_acceptance(M5, parent, params, seed=0, parent_slug="fq")
    assert result.discarded_at_stage is Stage.GATE
    gate_stage = next(o for o in result.stages if o.stage is Stage.GATE)
    assert "L2-11" in gate_stage.rule_ids


@pytest.mark.unit
def test_m5_gate_choice_that_strands_a_config_is_discarded_at_the_gate() -> None:
    """Gating a lone exit (bypassing the precondition) strands a config: L2-9 at gate."""
    parent = _flooded_quarter()
    params = OpParams.of(
        mode="gate-choice",
        choice="c_n_start_1",
        gate_var="oil",
        gate_op=">=",
        gate_value=99,
        justification="asserted",
    )
    result = run_acceptance(M5, parent, params, seed=0, parent_slug="fq")
    assert result.discarded_at_stage is Stage.GATE
    gate_stage = next(o for o in result.stages if o.stage is Stage.GATE)
    assert "L2-9" in gate_stage.rule_ids


@pytest.mark.unit
def test_m5_add_route_on_a_two_choice_decision_is_held() -> None:
    """Adding a gated back-edge route on an open_map decision node is accepted."""
    parent = _flooded_quarter()
    params = OpParams.of(
        mode="add-route",
        host="bk_row2",
        target="n_hub",
        gate_var="oil",
        gate_op=">=",
        gate_value=1,
    )
    result = run_acceptance(M5, parent, params, seed=0, parent_slug="fq")
    assert result.discarded_at_stage is None
    assert result.held is True


@pytest.mark.unit
def test_m5_add_route_past_the_choice_cap_is_refused_at_preconditions() -> None:
    """Adding a fourth choice to an already-3-choice node is refused before apply."""
    parent = _flooded_quarter()
    report = M5.preconditions(
        parent,
        OpParams.of(
            mode="add-route",
            host="n_hub",
            target="e_steady",
            gate_var="oil",
            gate_op=">=",
            gate_value=1,
        ),
    )
    assert report.satisfied is False
    assert any("choice cap" in reason for reason in report.failures)


@pytest.mark.unit
def test_m5_relocate_effect_is_held() -> None:
    """Moving an on_enter effect to a different node is accepted and held."""
    parent = _flooded_quarter()
    params = OpParams.of(
        mode="relocate-effect", from_node="bk_done", to_node="n_hub"
    )
    result = run_acceptance(M5, parent, params, seed=0, parent_slug="fq")
    assert result.discarded_at_stage is None
    assert result.held is True


# --- The safety property: M5 never touches an ending (design 12 D6) ---


@pytest.mark.unit
@pytest.mark.security
@pytest.mark.parametrize(
    "params",
    [
        OpParams.of(mode="retune", variable="oil", max=4),
        OpParams.of(mode="rename", variable="oil", new_name="fuel"),
        OpParams.of(
            mode="gate-choice",
            choice="c_n_hub_1",
            gate_var="oil",
            gate_op=">=",
            gate_value=1,
        ),
        OpParams.of(
            mode="add-route",
            host="bk_row2",
            target="n_hub",
            gate_var="oil",
            gate_op=">=",
            gate_value=1,
        ),
        OpParams.of(mode="relocate-effect", from_node="bk_done", to_node="n_hub"),
    ],
)
def test_m5_never_changes_the_ending_multiset(params: OpParams) -> None:
    """Every M5 mode leaves the ending multiset byte-identical."""
    parent = _flooded_quarter()
    before = _ending_multiset(parent)
    candidate = _apply(params)
    assert _ending_multiset(candidate) == before


@pytest.mark.unit
@pytest.mark.security
def test_assert_endings_untouched_trips_on_a_tampered_ending() -> None:
    """The type-level guarantee: a changed ending kind is rejected."""
    parent = _flooded_quarter()
    tampered = copy.deepcopy(parent)
    for raw_node in cast("list[object]", tampered["nodes"]):
        node = cast("dict[str, object]", raw_node)
        if node.get("is_ending") is True:
            cast("dict[str, object]", node["ending"])["id"] = "tampered_ending_id"
            break
    with pytest.raises(ValidationError, match="must not change any ending"):
        _assert_endings_untouched(parent, tampered)


# --- Pure section-5.3 helpers on small stateful fixtures ---


@pytest.mark.unit
def test_ending_coverage_gap_detects_a_stranded_ending() -> None:
    """A retune that severs a gated ending is caught by the coverage check."""
    covered = Storybook.model_validate(_tiny_tier2(initial=2, maximum=2))
    assert ending_coverage_gap(covered, walk_configurations(covered)) == set()
    # oil starts and caps at 1: the oil>=2 route into e_deep is never satisfiable.
    stranded = Storybook.model_validate(_tiny_tier2(initial=1, maximum=1))
    gap = ending_coverage_gap(stranded, walk_configurations(stranded))
    assert gap == {"e_deep"}


@pytest.mark.unit
def test_walk_fastest_satisfying_finish_counts_config_path_nodes() -> None:
    """The clock re-proof counts config-path nodes to the nearest satisfying finish."""
    story = Storybook.model_validate(_tiny_tier2())
    finish = walk_fastest_satisfying_finish(story, walk_configurations(story))
    # start config -> the success ending config is a two-node config path.
    assert finish == 2


@pytest.mark.unit
def test_state_distance_zero_for_identity_and_positive_for_a_real_retune() -> None:
    """The state distance is zero for an unchanged story and positive for a retune."""
    base = Storybook.model_validate(_tiny_tier2(initial=2, maximum=2))
    base_sig = state_signature(base, walk_configurations(base))
    assert state_distance(base_sig, base_sig) == 0.0
    retuned = Storybook.model_validate(_tiny_tier2(initial=1, maximum=1))
    retuned_sig = state_signature(retuned, walk_configurations(retuned))
    assert state_distance(base_sig, retuned_sig) > 0.0
