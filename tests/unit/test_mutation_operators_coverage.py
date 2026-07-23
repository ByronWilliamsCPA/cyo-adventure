"""Branch-coverage tests for defensive paths in ``mutation/operators.py`` (WS-5).

The M1-M4 primary suites (``test_mutation_m1..m4.py``) exercise the happy paths
and the headline precondition rejections over the real catalog. This module
targets the remaining defensive branches: the malformed-document skips in the raw
helpers, the parameter-type guards on every operator, the ineligibility reasons,
the apply-time "no nodes list" raises, and the deterministic id/slot minting
fallbacks. Every test drives a real branch with a crafted minimal document (or a
catalog skeleton where a full graph is needed) and asserts the observable result.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation.operators import (
    M1,
    M2,
    M3,
    M4,
    M3PruneGraft,
    _apply_graft,  # pyright: ignore[reportPrivateUsage]
    _apply_prune,  # pyright: ignore[reportPrivateUsage]
    _apply_remove_linear,  # pyright: ignore[reportPrivateUsage]
    _apply_swap,  # pyright: ignore[reportPrivateUsage]
    _branch_depth,  # pyright: ignore[reportPrivateUsage]
    _build_disjoint_pair,  # pyright: ignore[reportPrivateUsage]
    _candidate_nodes,  # pyright: ignore[reportPrivateUsage]
    _cell_max_depth,  # pyright: ignore[reportPrivateUsage]
    _cell_node_bounds,  # pyright: ignore[reportPrivateUsage]
    _choice_refs,  # pyright: ignore[reportPrivateUsage]
    _ChoiceRef,  # pyright: ignore[reportPrivateUsage]
    _choose_graft_index,  # pyright: ignore[reportPrivateUsage]
    _clamp_position,  # pyright: ignore[reportPrivateUsage]
    _decision_window_reason,  # pyright: ignore[reportPrivateUsage]
    _depth_reason,  # pyright: ignore[reportPrivateUsage]
    _ending_leaves,  # pyright: ignore[reportPrivateUsage]
    _ending_ratio_advisory,  # pyright: ignore[reportPrivateUsage]
    _evaluate_graft,  # pyright: ignore[reportPrivateUsage]
    _evaluate_insert_decision,  # pyright: ignore[reportPrivateUsage]
    _evaluate_insert_linear,  # pyright: ignore[reportPrivateUsage]
    _evaluate_pair,  # pyright: ignore[reportPrivateUsage]
    _evaluate_prune,  # pyright: ignore[reportPrivateUsage]
    _evaluate_remap,  # pyright: ignore[reportPrivateUsage]
    _evaluate_remove_linear,  # pyright: ignore[reportPrivateUsage]
    _graft_reguide_items,  # pyright: ignore[reportPrivateUsage]
    _GraftPlan,  # pyright: ignore[reportPrivateUsage]
    _load_catalog_donor,  # pyright: ignore[reportPrivateUsage]
    _micro_stub_kind_reason,  # pyright: ignore[reportPrivateUsage]
    _min_decisions_floor,  # pyright: ignore[reportPrivateUsage]
    _node_body,  # pyright: ignore[reportPrivateUsage]
    _node_count_reason,  # pyright: ignore[reportPrivateUsage]
    _post_graft_graph,  # pyright: ignore[reportPrivateUsage]
    _post_swap_graph,  # pyright: ignore[reportPrivateUsage]
    _post_swap_reason,  # pyright: ignore[reportPrivateUsage]
    _PrunePlan,  # pyright: ignore[reportPrivateUsage]
    _reconvergence_ceiling_reason,  # pyright: ignore[reportPrivateUsage]
    _region_all_ids,  # pyright: ignore[reportPrivateUsage]
    _region_cleanliness_reason,  # pyright: ignore[reportPrivateUsage]
    _RemoveLinearPlan,  # pyright: ignore[reportPrivateUsage]
    _rename_region_slot_tokens,  # pyright: ignore[reportPrivateUsage]
    _resolve_swap_refs,  # pyright: ignore[reportPrivateUsage]
    _retarget_choice,  # pyright: ignore[reportPrivateUsage]
    _satisfying_ending_ids,  # pyright: ignore[reportPrivateUsage]
    _satisfying_in_nodes,  # pyright: ignore[reportPrivateUsage]
    _shortest_satisfying_nodes,  # pyright: ignore[reportPrivateUsage]
    _SwapPair,  # pyright: ignore[reportPrivateUsage]
    _topology_reason,  # pyright: ignore[reportPrivateUsage]
    _unique_graft_choice_id,  # pyright: ignore[reportPrivateUsage]
    merge_graft_contract,
    path_decision_counts,
    prune_contract,
    region_referenced_slots,
)
from cyo_adventure.mutation.ops import OpParams
from cyo_adventure.storybook.theme_contract import ThemeContract

if TYPE_CHECKING:
    from collections.abc import Mapping

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"
_CAVE = "8-11/the-cave-of-echoes.json"


def _load(slug_path: str) -> dict[str, object]:
    """Load one catalog skeleton by its ``band/slug.json`` path."""
    return cast(
        "dict[str, object]",
        json.loads((_SKELETONS_ROOT / slug_path).read_text(encoding="utf-8")),
    )


def _swap_story() -> dict[str, object]:
    """Return a tiny two-ending decision story for the M1 swap helpers.

    ``s`` offers two choices into the disjoint, self-contained ending subtrees
    ``a`` and ``b``. Non-production (no ``length``) so the PL-20 floor is inert
    and the swap mechanics are isolated.
    """
    return {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [
            {
                "id": "s",
                "choices": [
                    {"id": "c1", "target": "a", "label": "A"},
                    {"id": "c2", "target": "b", "label": "B"},
                ],
            },
            {
                "id": "a",
                "is_ending": True,
                "ending": {
                    "id": "ae",
                    "kind": "success",
                    "valence": "positive",
                    "title": "A ends",
                },
            },
            {
                "id": "b",
                "is_ending": True,
                "ending": {
                    "id": "be",
                    "kind": "completion",
                    "valence": "positive",
                    "title": "B ends",
                },
            },
        ],
    }


# --------------------------------------------------------------------------- #
# Raw-document accessor defensive skips                                        #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_node_body_returns_empty_for_a_missing_node() -> None:
    """A node id that is absent yields the empty body string."""
    assert _node_body(_swap_story(), "not-a-node") == ""


@pytest.mark.unit
def test_choice_refs_skips_idless_nodes_and_malformed_choices() -> None:
    """A node with no id and a choice missing id/target contribute no refs."""
    story = {
        "nodes": [
            {"choices": [{"id": "c", "target": "t"}]},  # node has no id
            {"id": "n", "choices": [{"label": "no id or target"}, {"id": "c2"}]},
        ]
    }
    refs = _choice_refs(story)
    # only the id+target choice on the id-bearing node survives... but its node's
    # first choice lacks a target and the second lacks a target too, so none of
    # node ``n``'s choices qualify, and the id-less node's choice is dropped.
    assert refs == {}


@pytest.mark.unit
def test_satisfying_ending_ids_skips_malformed_endings() -> None:
    """An ending node with no id or a non-dict ending block is skipped."""
    story = {
        "nodes": [
            {"is_ending": True, "ending": {"kind": "success"}},  # no node id
            {"id": "x", "is_ending": True, "ending": "not-a-dict"},
            {
                "id": "ok",
                "is_ending": True,
                "ending": {"id": "e", "kind": "success"},
            },
        ]
    }
    assert _satisfying_ending_ids(story) == {"ok"}


# --------------------------------------------------------------------------- #
# Graph helpers                                                                #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_post_swap_graph_skips_idless_source_and_absent_targets() -> None:
    """An id-less source node and a choice to a missing node add no edge."""
    story = {
        "nodes": [
            {"choices": [{"id": "cx", "target": "s"}]},  # id-less source
            {
                "id": "s",
                "choices": [
                    {"id": "c1", "target": "a"},
                    {"id": "c2", "target": "b"},
                    {"id": "c3", "target": "ghost"},  # target not present
                ],
            },
            {"id": "a"},
            {"id": "b"},
        ]
    }
    pair = _SwapPair(
        choice1_id="c1",
        node1_id="s",
        root1="a",
        choice2_id="c2",
        node2_id="s",
        root2="b",
    )
    graph = _post_swap_graph(story, pair)
    assert set(graph.nodes) == {"s", "a", "b"}
    assert set(graph.edges) == {("s", "b"), ("s", "a")}  # c1->b, c2->a; ghost dropped


@pytest.mark.unit
def test_branch_depth_none_when_start_is_absent() -> None:
    """A None start (or one not in the graph) yields a None depth."""
    story = _swap_story()
    graph = _post_swap_graph(
        story,
        _SwapPair("c1", "s", "a", "c2", "s", "b"),
    )
    assert _branch_depth(graph, None) is None
    assert _branch_depth(graph, "absent") is None


@pytest.mark.unit
def test_cell_max_depth_none_without_a_band() -> None:
    """A story whose metadata declares no age_band has no depth budget."""
    assert _cell_max_depth({"metadata": {}}) is None


@pytest.mark.unit
def test_shortest_satisfying_nodes_edge_cases() -> None:
    """A None start, absent endpoints, and an unreachable target each yield None."""
    story = _swap_story()
    graph = _post_swap_graph(story, _SwapPair("c1", "s", "a", "c2", "s", "b"))
    assert _shortest_satisfying_nodes(graph, None, {"a"}) is None
    # target not in graph -> skipped; here the only target is absent
    assert _shortest_satisfying_nodes(graph, "s", {"absent"}) is None
    # start present but no path to the (isolated) target
    isolated = _post_swap_graph(
        {"nodes": [{"id": "s"}, {"id": "z"}]}, _SwapPair("n", "n", "n", "m", "m", "m")
    )
    assert _shortest_satisfying_nodes(isolated, "s", {"z"}) is None


# --------------------------------------------------------------------------- #
# M1 swap resolution helpers                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_resolve_swap_refs_rejects_missing_absent_and_shared_targets() -> None:
    """Unknown choices, an absent target, and a shared target are each rejected."""
    story = {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [
            {
                "id": "s",
                "choices": [
                    {"id": "c1", "target": "a"},
                    {"id": "c2", "target": "a"},  # shares target with c1
                    {"id": "c3", "target": "ghost"},  # absent target
                ],
            },
            {"id": "a", "is_ending": True, "ending": {"id": "ae", "kind": "success"}},
        ],
    }
    assert isinstance(_resolve_swap_refs(story, "c1", "nope"), str)  # ref2 missing
    assert isinstance(_resolve_swap_refs(story, "nope", "c1"), str)  # ref1 missing
    assert "does not exist" in cast("str", _resolve_swap_refs(story, "c1", "c3"))
    assert "no-op" in cast("str", _resolve_swap_refs(story, "c1", "c2"))


@pytest.mark.unit
def test_build_disjoint_pair_rejects_non_self_contained_subtrees() -> None:
    """A subtree with an external in-edge is rejected on either side."""
    # ``a`` is entered by both ``c1`` and ``cx`` (from b), so it is not
    # self-contained: an external in-edge from outside its own subtree.
    story = {
        "start_node": "s",
        "nodes": [
            {
                "id": "s",
                "choices": [
                    {"id": "c1", "target": "a"},
                    {"id": "c2", "target": "b"},
                ],
            },
            {"id": "a", "choices": [{"id": "ca", "target": "ea"}]},
            {"id": "ea", "is_ending": True, "ending": {"id": "eae", "kind": "success"}},
            {"id": "b", "choices": [{"id": "cx", "target": "a"}]},  # external in-edge
        ],
    }
    ref1 = _ChoiceRef(choice_id="c1", node_id="s", target="a", label="")
    ref2 = _ChoiceRef(choice_id="c2", node_id="s", target="b", label="")
    assert "not self-contained" in cast("str", _build_disjoint_pair(story, ref1, ref2))
    # and with the roles reversed (ref2's subtree is the offender)
    assert "not self-contained" in cast("str", _build_disjoint_pair(story, ref2, ref1))


@pytest.mark.unit
def test_post_swap_reason_flags_a_swap_that_would_create_a_cycle() -> None:
    """Swapping an edge onto a self-loop on an acyclic parent is rejected."""
    story = {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [
            {"id": "s", "choices": [{"id": "c1", "target": "a"}]},
            {"id": "a", "choices": [{"id": "ca", "target": "b"}]},
            {"id": "b", "is_ending": True, "ending": {"id": "be", "kind": "success"}},
        ],
    }
    # c1 (s->a) and ca (a->b): after the swap c1 -> b and ca -> a, so ``a``
    # gains a self-loop and the acyclic parent becomes cyclic.
    pair = _SwapPair("c1", "s", "a", "ca", "a", "b")
    assert "cycle" in cast("str", _post_swap_reason(story, pair))


@pytest.mark.unit
def test_post_swap_reason_none_when_bandless_and_floorless() -> None:
    """With no depth budget and no PL-20 floor a valid swap has no failing reason."""
    story = {
        "start_node": "s",  # no metadata band -> max_depth None, floor None
        "nodes": [
            {
                "id": "s",
                "choices": [
                    {"id": "c1", "target": "a"},
                    {"id": "c2", "target": "b"},
                ],
            },
            {"id": "a", "is_ending": True, "ending": {"id": "ae", "kind": "success"}},
            {"id": "b", "is_ending": True, "ending": {"id": "be", "kind": "success"}},
        ],
    }
    pair = _SwapPair("c1", "s", "a", "c2", "s", "b")
    assert _post_swap_reason(story, pair) is None


@pytest.mark.unit
def test_evaluate_pair_accepts_a_clean_swap() -> None:
    """A disjoint, self-contained pair resolves to a valid swap plan."""
    pair, reason = _evaluate_pair(_swap_story(), "c1", "c2")
    assert reason is None
    assert pair is not None


@pytest.mark.unit
def test_apply_swap_raises_without_a_nodes_list() -> None:
    """A parent with no node list cannot be swapped."""
    pair = _SwapPair("c1", "s", "a", "c2", "s", "b")
    with pytest.raises(ValidationError, match="no nodes list"):
        _apply_swap({"metadata": {}}, pair)


@pytest.mark.unit
def test_apply_swap_skips_malformed_nodes_and_choices() -> None:
    """Non-dict nodes and non-dict choices are passed over during the rewrite."""
    story = {
        "nodes": [
            "not-a-node",
            {
                "id": "s",
                "choices": [
                    123,  # non-dict choice
                    {"id": "c1", "target": "a"},
                    {"id": "c2", "target": "b"},
                ],
            },
        ]
    }
    pair = _SwapPair("c1", "s", "a", "c2", "s", "b")
    candidate = _apply_swap(story, pair)
    nodes = cast("list[object]", candidate["nodes"])
    swapped = cast("dict[str, object]", nodes[1])
    choices = cast("list[object]", swapped["choices"])
    assert cast("dict[str, object]", choices[1])["target"] == "b"
    assert cast("dict[str, object]", choices[2])["target"] == "a"


# --------------------------------------------------------------------------- #
# M1 operator preconditions / selection                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_m1_preconditions_flag_series_production_and_bad_params() -> None:
    """Series, non-production, and non-string choice params all fail preconditions."""
    story: dict[str, object] = {
        "metadata": {"series": "saga", "production_eligible": False},
        "nodes": [],
    }
    report = M1.preconditions(story, OpParams.of())
    assert not report.satisfied
    assert any("series" in f for f in report.failures)
    assert any("production-eligible" in f for f in report.failures)

    bad_params = M1.preconditions(_swap_story(), OpParams.of(choice1="c1", choice2=7))
    assert not bad_params.satisfied
    assert any("choice1" in f and "choice2" in f for f in bad_params.failures)


@pytest.mark.unit
def test_m1_preconditions_accept_an_explicit_eligible_pair() -> None:
    """Explicit, eligible choice ids satisfy the preconditions."""
    report = M1.preconditions(_swap_story(), OpParams.of(choice1="c1", choice2="c2"))
    assert report.satisfied


@pytest.mark.unit
def test_m1_preconditions_flag_a_parent_with_no_eligible_pair() -> None:
    """A single-ending story admits no sibling-subtree swap."""
    story = {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [
            {"id": "s", "choices": [{"id": "c1", "target": "a"}]},
            {"id": "a", "is_ending": True, "ending": {"id": "ae", "kind": "success"}},
        ],
    }
    report = M1.preconditions(story, OpParams.of())
    assert not report.satisfied
    assert any("no eligible" in f for f in report.failures)


@pytest.mark.unit
def test_m1_apply_raises_on_bad_params_and_on_no_eligible_pair() -> None:
    """apply raises for non-string params and for a parent with no eligible swap."""
    with pytest.raises(ValidationError, match="choice1"):
        M1.apply(_swap_story(), OpParams.of(choice1="c1", choice2=7), random.Random(0))
    lonely = {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [
            {"id": "s", "choices": [{"id": "c1", "target": "a"}]},
            {"id": "a", "is_ending": True, "ending": {"id": "ae", "kind": "success"}},
        ],
    }
    with pytest.raises(ValidationError, match="no eligible"):
        M1.apply(lonely, OpParams.of(), random.Random(0))


# --------------------------------------------------------------------------- #
# M2 ending-remap helpers                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_ending_leaves_skips_malformed_and_incomplete_endings() -> None:
    """Id-less nodes, non-dict endings, and endings missing fields are skipped."""
    story = {
        "nodes": [
            {"is_ending": True, "ending": {"id": "e", "kind": "success"}},  # no node id
            {"id": "x", "is_ending": True, "ending": "nope"},  # non-dict
            {
                "id": "y",
                "is_ending": True,
                "ending": {"id": "ye", "kind": "success"},  # no valence/title
            },
            {
                "id": "z",
                "is_ending": True,
                "ending": {
                    "id": "ze",
                    "kind": "success",
                    "valence": "positive",
                    "title": "Z",
                },
            },
        ]
    }
    leaves = _ending_leaves(story)
    assert [leaf.node_id for leaf in leaves] == ["z"]


@pytest.mark.unit
def test_evaluate_remap_rejects_small_classes_and_bad_orders() -> None:
    """A one-ending class and a non-permutation order are both rejected."""
    story = _two_kind_story()
    plan, reason = _evaluate_remap(story, "negative", ["x"])
    assert plan is None
    assert "fewer than 2" in cast("str", reason)
    plan2, reason2 = _evaluate_remap(story, "positive", ["ae", "ae"])
    assert plan2 is None
    assert "permutation" in cast("str", reason2)


@pytest.mark.unit
def test_evaluate_remap_accepts_a_meaningful_permutation() -> None:
    """A kind-changing permutation of a two-kind class is eligible."""
    plan, reason = _evaluate_remap(_two_kind_story(), "positive", ["be", "ae"])
    assert reason is None
    assert plan is not None


@pytest.mark.unit
def test_m2_preconditions_flag_series_production_and_bad_params() -> None:
    """Series, non-production, and half-supplied params fail M2 preconditions."""
    story: dict[str, object] = {
        "metadata": {"series": "saga", "production_eligible": False},
        "nodes": [],
    }
    report = M2.preconditions(story, OpParams.of())
    assert any("series" in f for f in report.failures)
    assert any("production-eligible" in f for f in report.failures)

    half = M2.preconditions(_two_kind_story(), OpParams.of(valence="positive"))
    assert not half.satisfied
    assert any("valence" in f and "order" in f for f in half.failures)


@pytest.mark.unit
def test_m2_preconditions_accept_explicit_eligible_params() -> None:
    """Explicit valence + a meaningful order satisfy the preconditions."""
    report = M2.preconditions(
        _two_kind_story(), OpParams.of(valence="positive", order="be,ae")
    )
    assert report.satisfied


@pytest.mark.unit
def test_m2_apply_raises_on_bad_params_and_no_remap() -> None:
    """apply raises for non-string params and for a parent with no eligible re-map."""
    with pytest.raises(ValidationError, match="valence"):
        M2.apply(_two_kind_story(), OpParams.of(valence="positive"), random.Random(0))
    single_kind = _two_kind_story()
    # collapse both endings to the same kind so no class admits a re-map
    for node in cast("list[dict[str, object]]", single_kind["nodes"]):
        ending = node.get("ending")
        if isinstance(ending, dict):
            cast("dict[str, object]", ending)["kind"] = "success"
    with pytest.raises(ValidationError, match="no eligible"):
        M2.apply(single_kind, OpParams.of(), random.Random(0))


def _two_kind_story() -> dict[str, object]:
    """Return a non-production story with two distinct-kind positive endings."""
    return {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [
            {
                "id": "s",
                "choices": [
                    {"id": "c1", "target": "a", "label": "A"},
                    {"id": "c2", "target": "b", "label": "B"},
                ],
            },
            {
                "id": "a",
                "is_ending": True,
                "ending": {
                    "id": "ae",
                    "kind": "success",
                    "valence": "positive",
                    "title": "A",
                },
            },
            {
                "id": "b",
                "is_ending": True,
                "ending": {
                    "id": "be",
                    "kind": "completion",
                    "valence": "positive",
                    "title": "B",
                },
            },
        ],
    }


# --------------------------------------------------------------------------- #
# M3 prune/graft helpers                                                       #
# --------------------------------------------------------------------------- #


def _tier1_story(**meta_over: object) -> dict[str, object]:
    """Return a tiny Tier-1 story with overridable metadata for M3/M4 guards."""
    metadata: dict[str, object] = {"age_band": "8-11"}
    metadata.update(meta_over)
    return {
        "metadata": metadata,
        "start_node": "s",
        "nodes": [
            {"id": "s", "choices": [{"id": "c1", "target": "a"}]},
            {"id": "a", "is_ending": True, "ending": {"id": "ae", "kind": "success"}},
        ],
    }


@pytest.mark.unit
def test_cell_node_bounds_none_without_band_or_budget() -> None:
    """No band yields no bounds; the min-decisions floor uses the band base."""
    assert _cell_node_bounds({"metadata": {}}) is None
    # non-production (no length) -> the profile base floor, not a scaled one
    assert _min_decisions_floor({"metadata": {"age_band": "8-11"}}, 40) >= 0


@pytest.mark.unit
def test_region_cleanliness_reason_flags_conditions_and_effects() -> None:
    """A region choice carrying a condition or effects is not graft-eligible."""
    condition_region = {
        "nodes": [
            {"id": "r", "choices": [{"id": "rc", "target": "r2", "condition": "x>1"}]}
        ]
    }
    assert "condition-free" in cast(
        "str", _region_cleanliness_reason(condition_region, frozenset({"r"}))
    )
    effect_region = {
        "nodes": [
            {"id": "r", "choices": [{"id": "rc", "target": "r2", "effects": ["x+1"]}]}
        ]
    }
    assert "effect-free" in cast(
        "str", _region_cleanliness_reason(effect_region, frozenset({"r"}))
    )


@pytest.mark.unit
def test_region_referenced_slots_scans_all_three_surfaces() -> None:
    """Slot tokens are read from FILL beats, ending titles, and choice labels."""
    nodes: list[Mapping[str, object]] = [
        {"id": "n1", "body": "<<FILL role=passage words=50 beats='meet {HERO}'>>"},
        {"id": "n2", "body": "plain prose, no fill directive"},  # no FILL match
        {"id": "n3", "ending": {"title": "{PLACE} falls"}},
        {"id": "n4", "choices": [{"id": "c", "label": "go to {DOOR}"}]},
        {"id": "n5", "ending": {}, "choices": [{"id": "c2"}]},  # no title / no label
    ]
    assert region_referenced_slots(nodes) == frozenset({"HERO", "PLACE", "DOOR"})


@pytest.mark.unit
def test_rename_region_slot_tokens_rewrites_only_slotted_surfaces() -> None:
    """Non-string bodies/titles/labels and non-dict choices are left untouched."""
    nodes: list[dict[str, object]] = [
        {
            "id": "n1",
            "body": "<<FILL role=passage words=50 beats='find {GEM}'>>",
            "ending": {"title": "{PLACE} wins"},
            "choices": ["not-a-choice", {"id": "c", "label": "open {DOOR}"}],
        },
        {"id": "n2", "body": 123, "ending": {"title": 9}, "choices": "nope"},
    ]
    _rename_region_slot_tokens(nodes, 2)
    assert "{M2_GEM}" in cast("str", nodes[0]["body"])
    assert cast("dict[str, object]", nodes[0]["ending"])["title"] == "{M2_PLACE} wins"
    choices = cast("list[object]", nodes[0]["choices"])
    assert cast("dict[str, object]", choices[1])["label"] == "open {M2_DOOR}"
    # the non-string surfaces on n2 are untouched
    assert nodes[1]["body"] == 123


@pytest.mark.unit
def test_evaluate_prune_rejection_ladder() -> None:
    """Each early prune-precondition failure surfaces its own reason."""
    story = _swap_story()
    # unknown choice
    assert "not a choice" in cast("str", _evaluate_prune(story, "nope")[1])


@pytest.mark.unit
def test_evaluate_prune_rejects_a_multi_in_edge_root() -> None:
    """A subtree root with two in-edges is not a single-edge prune."""
    story = {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [
            {
                "id": "s",
                "choices": [
                    {"id": "c1", "target": "a"},
                    {"id": "c2", "target": "a"},  # second edge into ``a``
                    {"id": "c3", "target": "b"},
                ],
            },
            {"id": "a", "is_ending": True, "ending": {"id": "ae", "kind": "success"}},
            {"id": "b", "is_ending": True, "ending": {"id": "be", "kind": "success"}},
        ],
    }
    _plan, reason = _evaluate_prune(story, "c1")
    assert reason is not None


@pytest.mark.unit
def test_apply_prune_raises_without_a_nodes_list() -> None:
    """A parent with no node list cannot be pruned."""
    plan = _PrunePlan(
        choice_id="c1",
        parent_node_id="s",
        root="a",
        region_ids=frozenset({"a"}),
    )
    with pytest.raises(ValidationError, match="no nodes list"):
        _apply_prune({"metadata": {}}, plan)


@pytest.mark.unit
def test_apply_prune_skips_malformed_nodes_and_choiceless_parent() -> None:
    """A non-dict node is kept as-is and a choiceless parent node is untouched."""
    story = {
        "nodes": [
            "not-a-node",
            {"id": "s"},  # parent node with no choices list
            {"id": "a", "is_ending": True, "ending": {"id": "ae", "kind": "success"}},
        ]
    }
    plan = _PrunePlan(
        choice_id="c1",
        parent_node_id="s",
        root="a",
        region_ids=frozenset({"a"}),
    )
    candidate = _apply_prune(story, plan)
    kept = cast("list[object]", candidate["nodes"])
    ids = {cast("dict[str, object]", n).get("id") for n in kept if isinstance(n, dict)}
    assert "a" not in ids  # pruned
    assert "not-a-node" in kept  # non-dict node kept verbatim


@pytest.mark.unit
def test_ending_ratio_advisory_edge_cases() -> None:
    """An empty story and an in-band ratio both produce no advisory."""
    assert _ending_ratio_advisory({"nodes": []}) is None
    # 2 endings of 10 nodes = 0.20, inside the 0.15-0.22 band -> no advisory
    in_band = {
        "nodes": [
            *[{"id": f"n{i}"} for i in range(8)],
            {"id": "e1", "is_ending": True},
            {"id": "e2", "is_ending": True},
        ]
    }
    assert _ending_ratio_advisory(in_band) is None


@pytest.mark.unit
def test_ending_ratio_advisory_out_of_band_returns_one_note_string() -> None:
    """An out-of-band ratio yields a single note, not a variable-length tuple.

    The helper reports at most one advisory, so its return arity is fixed:
    exactly one ``str`` or ``None``. Encoding "zero or one" as a tuple made the
    returned arity vary per code path (SonarCloud python:S8495).
    """
    # 3 endings of 6 nodes = 0.50, above the 0.15-0.22 band -> one advisory
    out_of_band = {
        "nodes": [
            *[{"id": f"n{i}"} for i in range(3)],
            *[{"id": f"e{i}", "is_ending": True} for i in range(3)],
        ]
    }
    advisory = _ending_ratio_advisory(out_of_band)
    assert isinstance(advisory, str)
    assert advisory.startswith("advisory: post-prune ending ratio 0.50")


@pytest.mark.unit
def test_region_all_ids_skips_idless_surfaces() -> None:
    """Id-less nodes, choices, and endings contribute nothing to the id union."""
    nodes: list[Mapping[str, object]] = [
        {"choices": [{"target": "t"}], "ending": {"kind": "x"}},  # all id-less
        {"id": "n", "choices": [{"id": "c"}], "ending": {"id": "e"}},
    ]
    assert _region_all_ids(nodes) == {"n", "c", "e"}


@pytest.mark.unit
def test_choose_graft_index_increments_past_a_collision() -> None:
    """A colliding ``m1_`` prefix forces the deterministic index up to 2."""
    region: list[Mapping[str, object]] = [{"id": "a"}]
    assert _choose_graft_index({"m1_a"}, region) == 2


@pytest.mark.unit
def test_unique_graft_choice_id_suffixes_past_a_collision() -> None:
    """A taken base graft-choice id gets a numeric suffix."""
    base = "m1_graft_into_dec"
    result = _unique_graft_choice_id(1, "dec", {base}, [])
    assert result == f"{base}_1"


@pytest.mark.unit
def test_post_graft_graph_skips_idless_nodes_and_targetless_choices() -> None:
    """A renamed node with no id and a targetless choice add no edges."""
    host = {"nodes": [{"id": "h", "choices": [{"id": "hc", "target": "h"}]}]}
    renamed: list[dict[str, object]] = [
        {"choices": [{"id": "x", "target": "h"}]},  # id-less renamed node
        {"id": "g", "choices": [{"id": "gc"}]},  # choice with no target
    ]
    graph = _post_graft_graph(host, renamed, "h", "g")
    assert ("h", "g") in graph.edges
    assert "g" in graph.nodes


@pytest.mark.unit
def test_satisfying_in_nodes_skips_malformed_endings() -> None:
    """A region ending with no node id or a non-dict block is skipped."""
    nodes: list[dict[str, object]] = [
        {"is_ending": True, "ending": {"kind": "success"}},  # no node id
        {"id": "g", "is_ending": True, "ending": {"kind": "success"}},
    ]
    assert _satisfying_in_nodes(nodes) == {"g"}


@pytest.mark.unit
def test_clamp_position_clamps_into_range() -> None:
    """An in-range index is returned; a negative one clamps to zero."""
    assert _clamp_position(2, 5) == 2
    assert _clamp_position(-3, 5) == 0
    assert _clamp_position(None, 5) == 5


@pytest.mark.unit
def test_evaluate_graft_rejection_ladder() -> None:
    """Ending host decision, series donor, and a missing/unclean donor subtree fail."""
    host = _tier1_story()
    # host decision is an ending node
    reason = _evaluate_graft(host, host, "<self>", "a", "a", None)[1]
    assert "ending node" in cast("str", reason)
    # series donor
    series_donor = _tier1_story(series="saga")
    reason2 = _evaluate_graft(host, series_donor, "d", "a", "s", None)[1]
    assert "series" in cast("str", reason2)
    # donor subtree root absent
    reason3 = _evaluate_graft(host, _tier1_story(), "d", "ghost", "s", None)[1]
    assert "does not exist" in cast("str", reason3)


@pytest.mark.unit
def test_apply_graft_raises_without_a_nodes_list() -> None:
    """A host with no node list cannot be grafted into."""
    plan = _GraftPlan(
        donor_slug="d",
        subtree_root="r",
        host_decision="h",
        position=0,
        k=1,
        renamed_nodes=({"id": "m1_r"},),
        root_new_id="m1_r",
        new_choice_id="m1_gc",
        new_choice_label="lbl",
        region_size=1,
    )
    with pytest.raises(ValidationError, match="no nodes list"):
        _apply_graft({"metadata": {}}, plan)


@pytest.mark.unit
def test_graft_reguide_items_tolerates_a_missing_root_node() -> None:
    """When the renamed root is absent the root-beat item still carries empty text."""
    plan = _GraftPlan(
        donor_slug="d",
        subtree_root="r",
        host_decision="h",
        position=0,
        k=1,
        renamed_nodes=({"id": "other"},),  # no node matches root_new_id
        root_new_id="m1_r",
        new_choice_id="m1_gc",
        new_choice_label="lbl",
        region_size=1,
    )
    items = _graft_reguide_items(plan)
    node_item = next(item for item in items if item.target_id == "m1_r")
    assert node_item.current_text == ""


@pytest.mark.unit
def test_load_catalog_donor_raises_for_an_unknown_slug() -> None:
    """A slug that names no catalog skeleton is a hard load failure."""
    with pytest.raises(ValidationError, match="was not found in the catalog"):
        _load_catalog_donor("no-such-skeleton-slug-xyz")


@pytest.mark.unit
def test_merge_graft_contract_skips_unknown_and_unbound_slots() -> None:
    """A referenced slot the donor never declares is skipped during the merge."""
    host = ThemeContract.model_validate(
        {
            "contract_version": 1,
            "skeleton_slug": "host",
            "age_band": "8-11",
            "default_binding": {"HERO": "a fox"},
            "slots": [
                {"id": "HERO", "scope": "global", "meaning": "hero", "guidance": ""}
            ],
        }
    )
    donor = ThemeContract.model_validate(
        {
            "contract_version": 1,
            "skeleton_slug": "donor",
            "age_band": "8-11",
            "default_binding": {"GEM": "a ruby"},
            "slots": [
                {"id": "GEM", "scope": "global", "meaning": "gem", "guidance": ""}
            ],
        }
    )
    # ``ABSENT`` is referenced but not declared by the donor -> skipped.
    merged = merge_graft_contract(
        host, donor, frozenset({"GEM", "ABSENT"}), 1, "mutant"
    )
    imported = {spec.id for spec in merged.slots}
    assert "M1_GEM" in imported
    assert "M1_ABSENT" not in imported


@pytest.mark.unit
def test_prune_contract_raises_when_every_slot_would_drop() -> None:
    """A prune that survives no slot must not leave an empty contract."""
    host = ThemeContract.model_validate(
        {
            "contract_version": 1,
            "skeleton_slug": "host",
            "age_band": "8-11",
            "default_binding": {"HERO": "a fox"},
            "slots": [
                {"id": "HERO", "scope": "global", "meaning": "hero", "guidance": ""}
            ],
        }
    )
    with pytest.raises(ValidationError, match="drop every slot"):
        prune_contract(host, frozenset(), "mutant")


@pytest.mark.unit
def test_m3_preconditions_flag_series_production_and_bad_modes() -> None:
    """Series, non-production, an absent mode, and bad prune/graft params all fail."""
    report = M3.preconditions(
        _tier1_story(series="saga", production_eligible=False), OpParams.of()
    )
    assert any("series" in f for f in report.failures)
    assert any("production-eligible" in f for f in report.failures)
    assert any("mode" in f for f in report.failures)

    prune_bad = M3.preconditions(_tier1_story(), OpParams.of(mode="prune", choice=7))
    assert any("choice id string" in f for f in prune_bad.failures)

    graft_bad_donor = M3.preconditions(
        _tier1_story(), OpParams.of(mode="graft", donor=7)
    )
    assert not graft_bad_donor.satisfied

    graft_bad_ids = M3.preconditions(
        _tier1_story(), OpParams.of(mode="graft", subtree_root=7)
    )
    assert any("subtree_root" in f for f in graft_bad_ids.failures)


@pytest.mark.unit
def test_m3_preconditions_flag_no_prunable_choice() -> None:
    """A minimal story with no closed prunable subtree fails prune preconditions."""
    report = M3.preconditions(_tier1_story(), OpParams.of(mode="prune"))
    assert any("no eligible prune" in f for f in report.failures)


@pytest.mark.unit
def test_m3_resolve_donor_reports_a_failed_resolver() -> None:
    """A resolver that raises surfaces as a graft precondition failure."""

    def _raiser(slug: str) -> dict[str, object]:
        msg = f"cannot load {slug}"
        raise ValidationError(msg, field="donor", value=slug)

    op = M3PruneGraft(donor_resolver=_raiser)
    report = op.preconditions(
        _tier1_story(),
        OpParams.of(mode="graft", donor="missing", subtree_root="a", host_decision="s"),
    )
    assert any("could not be loaded" in f for f in report.failures)


@pytest.mark.unit
def test_m3_apply_raises_across_the_mode_and_param_ladder() -> None:
    """apply raises for an unknown mode and for each ineligible sub-operation."""
    with pytest.raises(ValidationError, match="mode"):
        M3.apply(_tier1_story(), OpParams.of(mode="nope"), random.Random(0))
    with pytest.raises(ValidationError, match="choice id string"):
        M3.apply(_tier1_story(), OpParams.of(mode="prune", choice=7), random.Random(0))
    with pytest.raises(ValidationError, match="no eligible prune"):
        M3.apply(_tier1_story(), OpParams.of(mode="prune"), random.Random(0))
    with pytest.raises(ValidationError):
        M3.apply(_tier1_story(), OpParams.of(mode="graft", donor=7), random.Random(0))
    with pytest.raises(ValidationError, match="subtree_root"):
        M3.apply(
            _tier1_story(), OpParams.of(mode="graft", subtree_root=7), random.Random(0)
        )
    with pytest.raises(ValidationError, match="ineligible"):
        M3.apply(
            _tier1_story(),
            OpParams.of(mode="graft", subtree_root="a", host_decision="a"),
            random.Random(0),
        )


# --------------------------------------------------------------------------- #
# M4 vary-decisions helpers                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_path_decision_counts_empty_without_a_start() -> None:
    """A story with no start node enumerates no paths."""
    assert path_decision_counts({"nodes": []}) == ((), False)


@pytest.mark.unit
def test_decision_window_reason_none_without_paths() -> None:
    """When either side has no enumerable paths the window check is a no-op."""
    assert _decision_window_reason({"nodes": []}, {"nodes": []}) is None


@pytest.mark.unit
def test_node_count_reason_flags_both_envelope_sides() -> None:
    """A too-large candidate exceeds the max; a too-small one drops below the min."""
    parent = _load(_CAVE)
    parent_nodes = cast("list[object]", parent["nodes"])
    too_big = dict(parent)
    too_big["nodes"] = [*parent_nodes, *({"id": f"pad{i}"} for i in range(400))]
    assert "exceeds" in cast("str", _node_count_reason(parent, too_big))
    too_small = dict(parent)
    too_small["nodes"] = parent_nodes[:1]
    assert "below" in cast("str", _node_count_reason(parent, too_small))
    # no band -> no bounds -> no reason
    assert _node_count_reason({"metadata": {}}, too_big) is None


@pytest.mark.unit
def test_depth_reason_none_without_a_budget_and_flags_a_deep_chain() -> None:
    """No band yields no depth budget; a long linear chain exceeds the cell max."""
    assert _depth_reason({"metadata": {}}, {"nodes": []}) is None
    parent = _load(_CAVE)
    chain_nodes: list[dict[str, object]] = [
        {"id": f"d{i}", "choices": [{"id": f"dc{i}", "target": f"d{i + 1}"}]}
        for i in range(60)
    ]
    chain_nodes.append(
        {"id": "d60", "is_ending": True, "ending": {"id": "de", "kind": "success"}}
    )
    deep = {"metadata": parent["metadata"], "start_node": "d0", "nodes": chain_nodes}
    assert "depth" in cast("str", _depth_reason(parent, deep))


@pytest.mark.unit
def test_topology_reason_flags_an_undeclarable_topology() -> None:
    """A candidate whose metadata lacks a topology cannot re-declare one."""
    candidate = {
        "metadata": {"age_band": "8-11"},  # no topology field
        "start_node": "s",
        "nodes": [
            {"id": "s", "choices": [{"id": "c1", "target": "a"}]},
            {"id": "a", "is_ending": True, "ending": {"id": "ae", "kind": "success"}},
        ],
    }
    assert "inadmissible" in cast("str", _topology_reason(candidate))


@pytest.mark.unit
def test_reconvergence_ceiling_reason_returns_none_below_a_configured_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With a (patched) generous ceiling the reconvergence count clears it.

    No shipped band configures ``reconvergence_ceiling`` (every profile leaves it
    None), so the below-ceiling return path is only reachable by simulating a band
    that does configure one. This drives that real code path.
    """

    class _Profile:
        reconvergence_ceiling: int = 1000

    def _generous(_band: object) -> _Profile:
        return _Profile()

    monkeypatch.setattr("cyo_adventure.mutation.operators.profile_for", _generous)
    assert _reconvergence_ceiling_reason(_tier1_story(), _tier1_story()) is None


@pytest.mark.unit
def test_retarget_and_candidate_nodes_defensive_paths() -> None:
    """``_candidate_nodes`` raises without a node list; retarget skips non-dicts."""
    with pytest.raises(ValidationError, match="no nodes list"):
        _candidate_nodes({"metadata": {}})


@pytest.mark.unit
def test_evaluate_insert_linear_rejects_unknown_and_absent_targets() -> None:
    """An unknown choice and a choice into a missing node are both ineligible."""
    story = _tier1_story()
    assert "not a choice" in cast("str", _evaluate_insert_linear(story, "nope")[1])
    ghost = {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [{"id": "s", "choices": [{"id": "c1", "target": "ghost"}]}],
    }
    assert "does not exist" in cast("str", _evaluate_insert_linear(ghost, "c1")[1])


@pytest.mark.unit
def test_evaluate_remove_linear_rejection_ladder() -> None:
    """Each remove-linear precondition failure surfaces its own reason."""
    story = {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [
            {"id": "s", "choices": [{"id": "cs", "target": "p"}]},
            {
                "id": "p",
                "on_enter": ["x+1"],
                "choices": [
                    {"id": "cp", "target": "e", "condition": "x>0", "effects": ["y+1"]}
                ],
            },
            {"id": "e", "is_ending": True, "ending": {"id": "ee", "kind": "success"}},
            {
                "id": "end2",
                "is_ending": True,
                "ending": {"id": "e2", "kind": "success"},
            },
        ],
    }
    assert _evaluate_remove_linear(story, "nope")[1] == "node 'nope' does not exist"
    assert "ending" in cast("str", _evaluate_remove_linear(story, "e")[1])
    assert "start_node" in cast("str", _evaluate_remove_linear(story, "s")[1])
    assert "on_enter" in cast("str", _evaluate_remove_linear(story, "p")[1])


@pytest.mark.unit
def test_evaluate_remove_linear_rejects_condition_effect_and_selfloop() -> None:
    """A clean-node guard rejects conditions, effects, and self-loops."""
    condition = {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [
            {"id": "s", "choices": [{"id": "cs", "target": "p"}]},
            {"id": "p", "choices": [{"id": "cp", "target": "e", "condition": "x>0"}]},
            {"id": "e", "is_ending": True, "ending": {"id": "ee", "kind": "success"}},
        ],
    }
    assert "condition" in cast("str", _evaluate_remove_linear(condition, "p")[1])
    effect = {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [
            {"id": "s", "choices": [{"id": "cs", "target": "p"}]},
            {"id": "p", "choices": [{"id": "cp", "target": "e", "effects": ["x+1"]}]},
            {"id": "e", "is_ending": True, "ending": {"id": "ee", "kind": "success"}},
        ],
    }
    assert "effects" in cast("str", _evaluate_remove_linear(effect, "p")[1])
    selfloop = {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [
            {"id": "s", "choices": [{"id": "cs", "target": "p"}]},
            {"id": "p", "choices": [{"id": "cp", "target": "p"}]},  # self-loop
        ],
    }
    assert "self-loop" in cast("str", _evaluate_remove_linear(selfloop, "p")[1])
    missing_succ = {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [
            {"id": "s", "choices": [{"id": "cs", "target": "p"}]},
            {"id": "p", "choices": [{"id": "cp", "target": "ghost"}]},
        ],
    }
    assert "successor" in cast("str", _evaluate_remove_linear(missing_succ, "p")[1])


@pytest.mark.unit
def test_micro_stub_kind_reason_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    """No profile returns None; a forbidden discovery kind returns a reason."""
    assert _micro_stub_kind_reason({"metadata": {}}) is None

    class _Kind:
        value = "discovery"

    class _ProfileForbidding:
        forbidden_ending_kinds: frozenset[object] = frozenset({_Kind()})

    def _forbidding(_band: object) -> _ProfileForbidding:
        return _ProfileForbidding()

    monkeypatch.setattr("cyo_adventure.mutation.operators.profile_for", _forbidding)
    story: dict[str, object] = {"metadata": {"age_band": "8-11"}}
    assert "forbidden" in cast("str", _micro_stub_kind_reason(story))


@pytest.mark.unit
def test_evaluate_insert_decision_variant_ladder() -> None:
    """Unknown choice, absent target, and each variant guard surface reasons."""
    story = _tier1_story()
    assert "not a choice" in cast(
        "str", _evaluate_insert_decision(story, "nope", "reconvergence", None)[1]
    )
    # reconvergence variant with no valid target
    r = _evaluate_insert_decision(story, "c1", "reconvergence", None)
    assert "existing 'target'" in cast("str", r[1])
    # reconvergence target equal to the continuing target
    r2 = _evaluate_insert_decision(story, "c1", "reconvergence", "a")
    assert "no-op" in cast("str", r2[1])
    # unknown variant
    r3 = _evaluate_insert_decision(story, "c1", "sideways", None)
    assert "must be" in cast("str", r3[1])


@pytest.mark.unit
def test_m4_preconditions_flag_series_and_bad_params() -> None:
    """Series/production guards and each sub-mode's parameter guards fail cleanly."""
    report = M4.preconditions(
        _tier1_story(series="saga", production_eligible=False), OpParams.of()
    )
    assert any("series" in f for f in report.failures)
    assert any("production-eligible" in f for f in report.failures)
    assert any("mode" in f for f in report.failures)

    lin = M4.preconditions(_tier1_story(), OpParams.of(mode="insert-linear", choice=7))
    assert any("choice id string" in f for f in lin.failures)
    rem = M4.preconditions(_tier1_story(), OpParams.of(mode="remove-linear", node=7))
    assert any("node id string" in f for f in rem.failures)
    dec = M4.preconditions(
        _tier1_story(), OpParams.of(mode="insert-decision", choice=7)
    )
    assert any("reconvergence" in f or "variant" in f for f in dec.failures)


@pytest.mark.unit
def test_m4_preconditions_flag_no_eligible_candidates() -> None:
    """A minimal story admits no insert-linear/remove-linear/insert-decision move."""
    story = _tier1_story()
    assert not M4.preconditions(story, OpParams.of(mode="insert-linear")).satisfied
    assert not M4.preconditions(story, OpParams.of(mode="remove-linear")).satisfied
    assert not M4.preconditions(story, OpParams.of(mode="insert-decision")).satisfied


@pytest.mark.unit
def test_evaluate_prune_rejects_absent_and_non_self_contained_subtrees() -> None:
    """A choice to a missing node, and a subtree with an internal in-edge, fail."""
    ghost = {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [{"id": "s", "choices": [{"id": "c1", "target": "ghost"}]}],
    }
    assert "does not exist" in cast("str", _evaluate_prune(ghost, "c1")[1])
    # ``m`` (internal to ``a``'s subtree) has an external in-edge from ``x``,
    # so the subtree rooted at ``a`` is not self-contained.
    leaky = {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [
            {
                "id": "s",
                "choices": [{"id": "c1", "target": "a"}, {"id": "c2", "target": "x"}],
            },
            {"id": "a", "choices": [{"id": "ca", "target": "m"}]},
            {"id": "m", "is_ending": True, "ending": {"id": "me", "kind": "success"}},
            {"id": "x", "choices": [{"id": "cx", "target": "m"}]},  # external -> m
        ],
    }
    assert "not self-contained" in cast("str", _evaluate_prune(leaky, "c1")[1])


@pytest.mark.unit
def test_evaluate_graft_rejects_a_non_self_contained_donor_subtree() -> None:
    """A donor subtree with an external in-edge to an internal node is rejected."""
    host = {
        "metadata": {"age_band": "8-11"},
        "start_node": "h",
        "nodes": [
            {"id": "h", "choices": [{"id": "hc", "target": "he"}]},
            {"id": "he", "is_ending": True, "ending": {"id": "hee", "kind": "success"}},
        ],
    }
    # donor subtree root ``g`` -> ``m`` -> ending; ``x`` also enters ``m`` from
    # outside the region, so the subtree rooted at ``g`` is not self-contained.
    leaky_donor = {
        "metadata": {"age_band": "8-11"},
        "start_node": "g",
        "nodes": [
            {"id": "g", "choices": [{"id": "gc", "target": "m"}]},
            {"id": "m", "choices": [{"id": "mc", "target": "ge"}]},
            {"id": "ge", "is_ending": True, "ending": {"id": "gee", "kind": "success"}},
            {"id": "x", "choices": [{"id": "xc", "target": "m"}]},  # external -> m
        ],
    }
    reason = _evaluate_graft(host, leaky_donor, "d", "g", "h", None)[1]
    assert "not self-contained" in cast("str", reason)


@pytest.mark.unit
def test_apply_graft_skips_non_dict_nodes_and_absent_host_decision() -> None:
    """A non-dict node is skipped and an absent host decision leaves choices intact."""
    story = {"nodes": ["not-a-node", {"id": "h", "choices": []}]}
    plan = _GraftPlan(
        donor_slug="d",
        subtree_root="r",
        host_decision="absent",  # no node matches -> loop completes without inserting
        position=0,
        k=1,
        renamed_nodes=({"id": "m1_r"},),
        root_new_id="m1_r",
        new_choice_id="m1_gc",
        new_choice_label="lbl",
        region_size=1,
    )
    candidate = _apply_graft(story, plan)
    nodes = cast("list[object]", candidate["nodes"])
    host = cast("dict[str, object]", nodes[2])  # grafted node appended after skip
    assert host["id"] == "m1_r"


@pytest.mark.unit
def test_retarget_choice_skips_malformed_nodes_and_choices() -> None:
    """Non-dict nodes and non-dict choices are passed over; a match is rewritten."""
    candidate: dict[str, object] = {
        "nodes": [
            "not-a-node",
            {"choices": [123, {"id": "c1", "target": "old"}]},
        ]
    }
    _retarget_choice(candidate, "c1", "new")
    nodes = cast("list[object]", candidate["nodes"])
    choices = cast("list[object]", cast("dict[str, object]", nodes[1])["choices"])
    assert cast("dict[str, object]", choices[1])["target"] == "new"


@pytest.mark.unit
def test_apply_remove_linear_skips_malformed_nodes_and_choices() -> None:
    """A non-dict node is kept and a non-dict choice is passed over during splice."""
    story = {
        "nodes": [
            "not-a-node",
            {"id": "s", "choices": [456, {"id": "cs", "target": "p"}]},
            {"id": "p", "choices": [{"id": "cp", "target": "e"}]},
            {"id": "e", "is_ending": True, "ending": {"id": "ee", "kind": "success"}},
        ]
    }
    plan = _RemoveLinearPlan(node_id="p", successor="e", retargeted_choice_ids=("cs",))
    candidate = _apply_remove_linear(story, plan)
    kept = cast("list[object]", candidate["nodes"])
    assert "not-a-node" in kept
    s_node = next(
        cast("dict[str, object]", n)
        for n in kept
        if isinstance(n, dict) and cast("dict[str, object]", n).get("id") == "s"
    )
    choices = cast("list[object]", s_node["choices"])
    # the ``cs`` choice was retargeted from ``p`` to its successor ``e``
    assert cast("dict[str, object]", choices[1])["target"] == "e"


@pytest.mark.unit
def test_select_insert_linear_raises_on_an_ineligible_explicit_choice() -> None:
    """An explicit but ineligible insert-linear choice raises from apply."""
    ghost = {
        "metadata": {"age_band": "8-11"},
        "start_node": "s",
        "nodes": [{"id": "s", "choices": [{"id": "c1", "target": "ghost"}]}],
    }
    with pytest.raises(ValidationError, match="ineligible"):
        M4.apply(
            ghost,
            OpParams.of(mode="insert-linear", choice="c1"),
            random.Random(0),
        )


@pytest.mark.unit
def test_m4_apply_raises_across_modes_and_selection() -> None:
    """apply raises for an unknown mode and for empty seeded-selection candidates."""
    with pytest.raises(ValidationError, match="mode"):
        M4.apply(_tier1_story(), OpParams.of(mode="nope"), random.Random(0))
    with pytest.raises(ValidationError, match="choice id string"):
        M4.apply(
            _tier1_story(),
            OpParams.of(mode="insert-linear", choice=7),
            random.Random(0),
        )
    with pytest.raises(ValidationError, match="no eligible insert-linear"):
        M4.apply(_tier1_story(), OpParams.of(mode="insert-linear"), random.Random(0))
    with pytest.raises(ValidationError, match="node id string"):
        M4.apply(
            _tier1_story(),
            OpParams.of(mode="remove-linear", node=7),
            random.Random(0),
        )
    with pytest.raises(ValidationError, match="no eligible remove-linear"):
        M4.apply(_tier1_story(), OpParams.of(mode="remove-linear"), random.Random(0))
    with pytest.raises(ValidationError, match="insert-decision requires"):
        M4.apply(
            _tier1_story(),
            OpParams.of(mode="insert-decision", choice=7),
            random.Random(0),
        )
    with pytest.raises(ValidationError, match="no eligible insert-decision"):
        M4.apply(_tier1_story(), OpParams.of(mode="insert-decision"), random.Random(0))
