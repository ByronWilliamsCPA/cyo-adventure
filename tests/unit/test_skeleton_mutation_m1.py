"""Unit and property tests for the M1 sibling-subtree swap (WS-5 D2).

Covers design section 4.2: the preserved-by-construction invariants (node set,
node count, ending multiset, every in-degree), determinism, the acceptance
property (an accepted swap is never gate-blocked), and the discard path for a
cycle-creating (non-disjoint) swap. Runs on both small crafted fixtures and the
real Tier-1 production catalog.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation.operators import (
    M1,
    M1_OP_ID,
    _post_swap_is_acyclic,  # pyright: ignore[reportPrivateUsage]
    _SwapPair,  # pyright: ignore[reportPrivateUsage]
)
from cyo_adventure.mutation.ops import OpParams, ReguideTarget
from cyo_adventure.validator.gate import run_gate

if TYPE_CHECKING:
    from collections.abc import Mapping

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"


def _tier1_catalog() -> list[tuple[str, dict[str, object]]]:
    """Return ``(slug, story)`` for every production Tier-1 standalone skeleton.

    Mirrors the operator's own preconditions: production-eligible, Tier-1, and
    ``series is None`` (the only parents M1 accepts in D2).
    """
    catalog: list[tuple[str, dict[str, object]]] = []
    for path in sorted(_SKELETONS_ROOT.glob("*/*.json")):
        if path.name.endswith(".contract.json"):
            continue
        story = cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))
        meta = story.get("metadata")
        if not isinstance(meta, dict):
            continue
        metadata = cast("dict[str, object]", meta)
        if metadata.get("production_eligible") is False:
            continue
        if metadata.get("tier") != 1:
            continue
        if metadata.get("series") is not None:
            continue
        catalog.append((path.stem, story))
    return catalog


_CATALOG = _tier1_catalog()
_CATALOG_IDS = [slug for slug, _ in _CATALOG]


def _node_ids(story: Mapping[str, object]) -> set[str]:
    """Return the set of node ids in a raw story."""
    nodes = story.get("nodes")
    ids: set[str] = set()
    if isinstance(nodes, list):
        for node in cast("list[object]", nodes):
            if isinstance(node, dict):
                node_id = cast("dict[str, object]", node).get("id")
                if isinstance(node_id, str):
                    ids.add(node_id)
    return ids


def _ending_multiset(story: Mapping[str, object]) -> Counter[tuple[str, str]]:
    """Return the ``(kind, valence)`` ending multiset of a raw story."""
    counter: Counter[tuple[str, str]] = Counter()
    nodes = story.get("nodes")
    if isinstance(nodes, list):
        for node in cast("list[object]", nodes):
            if not isinstance(node, dict):
                continue
            ending = cast("dict[str, object]", node).get("ending")
            if not isinstance(ending, dict):
                continue
            ending_map = cast("dict[str, object]", ending)
            kind = ending_map.get("kind")
            valence = ending_map.get("valence")
            if isinstance(kind, str) and isinstance(valence, str):
                counter[kind, valence] += 1
    return counter


def _in_degrees(story: Mapping[str, object]) -> Counter[str]:
    """Return the in-degree of every node, counting choice edges to existing nodes."""
    present = _node_ids(story)
    degrees: Counter[str] = Counter()
    nodes = story.get("nodes")
    if isinstance(nodes, list):
        for node in cast("list[object]", nodes):
            if not isinstance(node, dict):
                continue
            choices = cast("dict[str, object]", node).get("choices")
            if not isinstance(choices, list):
                continue
            for choice in cast("list[object]", choices):
                if not isinstance(choice, dict):
                    continue
                target = cast("dict[str, object]", choice).get("target")
                if isinstance(target, str) and target in present:
                    degrees[target] += 1
    return degrees


def _eligible_slugs() -> list[tuple[str, dict[str, object]]]:
    """Return catalog entries that actually admit at least one M1 swap."""
    return [
        (slug, story)
        for slug, story in _CATALOG
        if M1.preconditions(story, OpParams.of()).satisfied
    ]


_ELIGIBLE = _eligible_slugs()
_ELIGIBLE_IDS = [slug for slug, _ in _ELIGIBLE]


def _diamond_tier1() -> dict[str, object]:
    """Return a tiny Tier-1 story with two disjoint self-contained sibling subtrees.

    ``start`` offers two sibling choices ``c_left`` and ``c_right`` rooting the
    closed subtrees ``{left, e_left}`` and ``{right, e_right}``; swapping them is
    the canonical M1 move. (This shell is not a production-cell skeleton, so it
    exercises the operator mechanics rather than the gate.)
    """
    return {
        "start_node": "start",
        "metadata": {
            "age_band": "5-8",
            "tier": 1,
            "topology": "time_cave",
            "ending_count": 2,
        },
        "variables": [],
        "nodes": [
            {
                "id": "start",
                "body": "<<FILL role=setup words=40 beats='pick a path'>>",
                "is_ending": False,
                "choices": [
                    {"id": "c_left", "label": "Go left.", "target": "left"},
                    {"id": "c_right", "label": "Go right.", "target": "right"},
                ],
            },
            {
                "id": "left",
                "body": "<<FILL role=rising words=40 beats='left way'>>",
                "is_ending": False,
                "choices": [
                    {"id": "c_left_end", "label": "Finish.", "target": "e_left"}
                ],
            },
            {
                "id": "right",
                "body": "<<FILL role=rising words=40 beats='right way'>>",
                "is_ending": False,
                "choices": [
                    {"id": "c_right_end", "label": "Finish.", "target": "e_right"}
                ],
            },
            {
                "id": "e_left",
                "body": "left done",
                "is_ending": True,
                "ending": {
                    "id": "end_left",
                    "kind": "success",
                    "valence": "positive",
                    "title": "Left",
                },
            },
            {
                "id": "e_right",
                "body": "right done",
                "is_ending": True,
                "ending": {
                    "id": "end_right",
                    "kind": "success",
                    "valence": "positive",
                    "title": "Right",
                },
            },
        ],
    }


def _nested_cycle_fixture() -> dict[str, object]:
    """Return an acyclic linear story whose two 'subtrees' are nested.

    ``c1`` on ``start`` targets ``mid`` (subtree ``{mid, leaf}``); ``c2`` on
    ``mid`` targets ``leaf`` (subtree ``{leaf}``). The subtrees overlap, so the
    swap is rejected as non-disjoint, and swapping the raw targets would put a
    self-loop on ``mid``.
    """
    return {
        "start_node": "start",
        "metadata": {"age_band": "5-8", "tier": 1, "topology": "time_cave"},
        "variables": [],
        "nodes": [
            {
                "id": "start",
                "body": "<<FILL role=setup words=40 beats='s'>>",
                "is_ending": False,
                "choices": [{"id": "c1", "label": "On.", "target": "mid"}],
            },
            {
                "id": "mid",
                "body": "<<FILL role=rising words=40 beats='m'>>",
                "is_ending": False,
                "choices": [{"id": "c2", "label": "On.", "target": "leaf"}],
            },
            {
                "id": "leaf",
                "body": "done",
                "is_ending": True,
                "ending": {
                    "id": "e",
                    "kind": "success",
                    "valence": "positive",
                    "title": "End",
                },
            },
        ],
    }


@pytest.mark.unit
def test_m1_is_registered_under_its_op_id() -> None:
    """The M1 singleton is registered and exposes its stable op id."""
    assert M1.op_id == M1_OP_ID == "M1"


@pytest.mark.unit
def test_m1_swaps_two_sibling_subtrees_on_a_small_fixture() -> None:
    """An explicit swap retargets each choice to the other subtree's root."""
    story = _diamond_tier1()
    result = M1.apply(
        story, OpParams.of(choice1="c_left", choice2="c_right"), random.Random(0)
    )
    candidate = result.candidate
    nodes = {
        cast("dict[str, object]", n)["id"]: cast("dict[str, object]", n)
        for n in cast("list[object]", candidate["nodes"])
    }
    start_choices = cast("list[object]", nodes["start"]["choices"])
    targets = {
        cast("dict[str, object]", c)["id"]: cast("dict[str, object]", c)["target"]
        for c in start_choices
    }
    assert targets["c_left"] == "right"
    assert targets["c_right"] == "left"


@pytest.mark.unit
def test_m1_emits_exactly_the_expected_reguide_items() -> None:
    """A swap emits its two choice labels and two moved subtree-root beats."""
    story = _diamond_tier1()
    result = M1.apply(
        story, OpParams.of(choice1="c_left", choice2="c_right"), random.Random(0)
    )
    choice_items = {
        item.target_id for item in result.reguide if item.target is ReguideTarget.CHOICE
    }
    node_items = {
        item.target_id for item in result.reguide if item.target is ReguideTarget.NODE
    }
    assert choice_items == {"c_left", "c_right"}
    assert node_items == {"left", "right"}
    assert len(result.reguide) == 4
    # The label current_text is captured for the reviewer's audit.
    labels = {
        item.current_text
        for item in result.reguide
        if item.target is ReguideTarget.CHOICE
    }
    assert labels == {"Go left.", "Go right."}


@pytest.mark.unit
def test_m1_swap_is_order_independent() -> None:
    """Passing the two choice ids in either order yields the same candidate."""
    story = _diamond_tier1()
    forward = M1.apply(
        story, OpParams.of(choice1="c_left", choice2="c_right"), random.Random(0)
    ).candidate
    reversed_ = M1.apply(
        story, OpParams.of(choice1="c_right", choice2="c_left"), random.Random(0)
    ).candidate
    assert json.dumps(forward, sort_keys=True) == json.dumps(reversed_, sort_keys=True)


@pytest.mark.unit
def test_m1_rejects_a_non_disjoint_cycle_creating_swap_at_preconditions() -> None:
    """A nested (non-disjoint) subtree pair is discarded at stage 0."""
    story = _nested_cycle_fixture()
    report = M1.preconditions(story, OpParams.of(choice1="c1", choice2="c2"))
    assert report.satisfied is False
    assert any("cycle" in reason or "disjoint" in reason for reason in report.failures)
    # And apply raises rather than emitting an ineligible candidate.
    params = OpParams.of(choice1="c1", choice2="c2")
    rng = random.Random(0)
    with pytest.raises(ValidationError):
        M1.apply(story, params, rng)


@pytest.mark.unit
def test_post_swap_acyclicity_guard_detects_a_back_edge() -> None:
    """The explicit acyclicity guard rejects a swap that would self-loop a node.

    Constructed directly (bypassing the disjointness precondition that would
    normally catch it) to prove the safety branch works: retargeting ``c2`` on
    ``mid`` to ``mid`` closes a self-loop, which an acyclic parent must not gain.
    """
    story = _nested_cycle_fixture()
    pair = _SwapPair(
        choice1_id="c1",
        node1_id="start",
        root1="mid",
        choice2_id="c2",
        node2_id="mid",
        root2="leaf",
    )
    assert _post_swap_is_acyclic(story, pair) is False


@pytest.mark.unit
def test_m1_precondition_rejects_tier2_parent() -> None:
    """M1 (D2) refuses a Tier-2 parent (variables present)."""
    story = _diamond_tier1()
    cast("dict[str, object]", story["metadata"])["tier"] = 2
    story["variables"] = [{"name": "x", "type": "int", "initial": 0}]
    report = M1.preconditions(story, OpParams.of())
    assert report.satisfied is False
    assert any("Tier-1" in reason for reason in report.failures)


@pytest.mark.unit
def test_catalog_has_eligible_tier1_parents() -> None:
    """The Tier-1 corpus is discovered and at least some parents admit a swap."""
    assert len(_CATALOG) >= 20
    assert len(_ELIGIBLE) >= 5


@pytest.mark.unit
@pytest.mark.parametrize("story", [story for _, story in _ELIGIBLE], ids=_ELIGIBLE_IDS)
def test_m1_preserves_invariants_and_passes_gate_on_catalog(
    story: dict[str, object],
) -> None:
    """On every eligible Tier-1 parent, an rng-selected swap holds the invariants.

    Design section 4.2 preserved-by-construction set, plus the acceptance
    property that the accepted output is never gate-blocked.
    """
    for seed in (0, 1, 2, 3):
        result = M1.apply(story, OpParams.of(), random.Random(seed))
        candidate = result.candidate
        # Preserved-by-construction invariants.
        assert _node_ids(candidate) == _node_ids(story)
        assert len(cast("list[object]", candidate["nodes"])) == len(
            cast("list[object]", story["nodes"])
        )
        assert _ending_multiset(candidate) == _ending_multiset(story)
        assert _in_degrees(candidate) == _in_degrees(story)
        parent_meta = cast("dict[str, object]", story["metadata"])
        cand_meta = cast("dict[str, object]", candidate["metadata"])
        assert cand_meta["ending_count"] == parent_meta["ending_count"]
        # Acceptance property: the full unchanged gate never blocks the output.
        assert run_gate(candidate).blocked is False


@pytest.mark.unit
@pytest.mark.parametrize("story", [story for _, story in _ELIGIBLE], ids=_ELIGIBLE_IDS)
def test_m1_is_deterministic_per_seed_on_catalog(story: dict[str, object]) -> None:
    """The same seed reproduces a byte-identical candidate."""
    a = M1.apply(story, OpParams.of(), random.Random(7)).candidate
    b = M1.apply(story, OpParams.of(), random.Random(7)).candidate
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


@pytest.mark.unit
@settings(max_examples=25, deadline=None)
@given(seed=st.integers(min_value=0, max_value=10_000))
def test_m1_gate_property_over_seeds(seed: int) -> None:
    """For arbitrary seeds on a representative parent, output is never gate-blocked."""
    story = _diamond_tier1_representative()
    result = M1.apply(story, OpParams.of(), random.Random(seed))
    assert run_gate(result.candidate).blocked is False
    # Determinism holds for the same seed.
    again = M1.apply(story, OpParams.of(), random.Random(seed)).candidate
    assert json.dumps(result.candidate, sort_keys=True) == json.dumps(
        again, sort_keys=True
    )


def _diamond_tier1_representative() -> dict[str, object]:
    """Return a real, gate-passing Tier-1 catalog parent for the property test."""
    for _slug, story in _ELIGIBLE:
        return story
    pytest.skip("no eligible Tier-1 catalog parent available")
