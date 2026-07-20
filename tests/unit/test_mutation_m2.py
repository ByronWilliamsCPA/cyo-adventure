"""Unit and property tests for the M2 ending re-map (WS-5 D3).

Covers design section 4.3: the preserved-by-construction invariants (graph shape
entirely, the ``(kind, valence)`` ending multiset), the PL-20 arc-floor
pre-check, determinism, the composition-only rationale (an M2 output is at
``structural_distance`` ~ 0 from its parent), the composed M1 -> M2 chain, and
the PL-15 safety property (an M2 output can never introduce an ending kind absent
from the parent's multiset, so a band-forbidden kind can never appear). Runs on
small crafted fixtures and the real Tier-1 production catalog.
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
from cyo_adventure.diversity.structure import structural_distance
from cyo_adventure.mutation.acceptance import run_acceptance
from cyo_adventure.mutation.operators import (
    M1,
    M2,
    M2_OP_ID,
)
from cyo_adventure.mutation.ops import OpParams, ReguideTarget
from cyo_adventure.validator.gate import run_gate

if TYPE_CHECKING:
    from collections.abc import Mapping

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"
_CINDERWICK = _SKELETONS_ROOT / "10-13" / "the-cinderwick-exchange.json"


def _tier1_catalog() -> list[tuple[str, dict[str, object]]]:
    """Return ``(slug, story)`` for every production Tier-1 standalone skeleton."""
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


def _m2_eligible() -> list[tuple[str, dict[str, object]]]:
    """Return Tier-1 catalog entries that admit at least one M2 re-map."""
    return [
        (slug, story)
        for slug, story in _CATALOG
        if M2.preconditions(story, OpParams.of()).satisfied
    ]


_ELIGIBLE = _m2_eligible()
_ELIGIBLE_IDS = [slug for slug, _ in _ELIGIBLE]


def _both_eligible() -> list[tuple[str, dict[str, object]]]:
    """Return Tier-1 catalog entries eligible for both M1 and M2 (for composition)."""
    return [
        (slug, story)
        for slug, story in _ELIGIBLE
        if M1.preconditions(story, OpParams.of()).satisfied
    ]


_BOTH = _both_eligible()
_BOTH_IDS = [slug for slug, _ in _BOTH]


def _node_ids(story: Mapping[str, object]) -> set[str]:
    """Return the set of node ids in a raw story."""
    ids: set[str] = set()
    nodes = story.get("nodes")
    if isinstance(nodes, list):
        for node in cast("list[object]", nodes):
            if isinstance(node, dict):
                node_id = cast("dict[str, object]", node).get("id")
                if isinstance(node_id, str):
                    ids.add(node_id)
    return ids


def _edges(story: Mapping[str, object]) -> set[tuple[str, str]]:
    """Return the set of ``(source, target)`` choice edges in a raw story."""
    edges: set[tuple[str, str]] = set()
    nodes = story.get("nodes")
    if isinstance(nodes, list):
        for node in cast("list[object]", nodes):
            if not isinstance(node, dict):
                continue
            source = cast("dict[str, object]", node).get("id")
            choices = cast("dict[str, object]", node).get("choices")
            if not isinstance(source, str) or not isinstance(choices, list):
                continue
            for choice in cast("list[object]", choices):
                if not isinstance(choice, dict):
                    continue
                target = cast("dict[str, object]", choice).get("target")
                if isinstance(target, str):
                    edges.add((source, target))
    return edges


def _choice_targets(story: Mapping[str, object]) -> dict[str, str]:
    """Return ``choice_id -> target`` for every choice (M1's swap moves these)."""
    targets: dict[str, str] = {}
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
                choice_map = cast("dict[str, object]", choice)
                choice_id = choice_map.get("id")
                target = choice_map.get("target")
                if isinstance(choice_id, str) and isinstance(target, str):
                    targets[choice_id] = target
    return targets


def _in_degrees(story: Mapping[str, object]) -> Counter[str]:
    """Return the in-degree of every node over choice edges to existing nodes."""
    present = _node_ids(story)
    degrees: Counter[str] = Counter()
    for source, target in _edges(story):
        if source in present and target in present:
            degrees[target] += 1
    return degrees


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


def _ending_kinds(story: Mapping[str, object]) -> set[str]:
    """Return the set of ending kinds present in a raw story."""
    return {kind for kind, _valence in _ending_multiset(story)}


def _ending_by_node(story: Mapping[str, object]) -> dict[str, tuple[str, str]]:
    """Return ``node_id -> (kind, title)`` for every ending node."""
    mapping: dict[str, tuple[str, str]] = {}
    nodes = story.get("nodes")
    if isinstance(nodes, list):
        for node in cast("list[object]", nodes):
            if not isinstance(node, dict):
                continue
            node_map = cast("dict[str, object]", node)
            node_id = node_map.get("id")
            ending = node_map.get("ending")
            if not isinstance(node_id, str) or not isinstance(ending, dict):
                continue
            ending_map = cast("dict[str, object]", ending)
            kind = ending_map.get("kind")
            title = ending_map.get("title")
            if isinstance(kind, str) and isinstance(title, str):
                mapping[node_id] = (kind, title)
    return mapping


def _ending_ids(story: Mapping[str, object]) -> list[str]:
    """Return every ending block id in a raw story, in file order."""
    ids: list[str] = []
    nodes = story.get("nodes")
    if isinstance(nodes, list):
        for node in cast("list[object]", nodes):
            if not isinstance(node, dict):
                continue
            ending = cast("dict[str, object]", node).get("ending")
            if isinstance(ending, dict):
                ending_id = cast("dict[str, object]", ending).get("id")
                if isinstance(ending_id, str):
                    ids.append(ending_id)
    return ids


def _two_kind_positive_fixture() -> dict[str, object]:
    """Return a non-scale-classified fixture with two distinct positive endings.

    ``start`` offers two choices leading to a ``discovery`` and a ``success``
    ending, both positive. With no declared ``length`` there is no PL-20 floor,
    so this fixture isolates the permutation mechanics from the arc-floor check.
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
                    {"id": "c_disc", "label": "Explore.", "target": "e_disc"},
                    {"id": "c_win", "label": "Finish.", "target": "e_win"},
                ],
            },
            {
                "id": "e_disc",
                "body": "found it",
                "is_ending": True,
                "ending": {
                    "id": "end_disc",
                    "kind": "discovery",
                    "valence": "positive",
                    "title": "A Quiet Find",
                },
            },
            {
                "id": "e_win",
                "body": "won",
                "is_ending": True,
                "ending": {
                    "id": "end_win",
                    "kind": "success",
                    "valence": "positive",
                    "title": "The Prize",
                },
            },
        ],
    }


def _single_kind_fixture() -> dict[str, object]:
    """Return a fixture whose only endings share one kind (no meaningful re-map)."""
    story = _two_kind_positive_fixture()
    nodes = cast("list[dict[str, object]]", story["nodes"])
    ending = cast("dict[str, object]", nodes[1]["ending"])
    ending["kind"] = "success"  # both positives are now `success`
    ending["title"] = "Another Prize"
    return story


def _pl20_fixture() -> dict[str, object]:
    """Return an 8-11 short-prose fixture whose success ending sits at the floor.

    The shortest satisfying path (``start`` .. ``e_win``) is 9 nodes, exactly the
    ``(8-11, short, prose)`` PL-20 floor. A shallow ``discovery`` (positive) sits
    two nodes from ``start``. Moving ``success`` onto that shallow leaf drops the
    fastest finish to 2 nodes, below the floor, so M2 must reject that permutation
    at preconditions. (Structure only; this shell is not gate-valid, and the
    precondition check never runs the gate.)
    """
    nodes: list[dict[str, object]] = [
        {
            "id": "start",
            "body": "<<FILL role=setup words=40 beats='begin'>>",
            "is_ending": False,
            "choices": [
                {"id": "c_deep", "label": "The long way.", "target": "n1"},
                {"id": "c_shallow", "label": "Peek aside.", "target": "e_disc"},
            ],
        }
    ]
    # A linear spine start -> n1 -> ... -> n7 -> e_win (9 nodes on the path).
    for index in range(1, 8):
        target = f"n{index + 1}" if index < 7 else "e_win"
        nodes.append(
            {
                "id": f"n{index}",
                "body": f"<<FILL role=rising words=40 beats='step {index}'>>",
                "is_ending": False,
                "choices": [{"id": f"c_n{index}", "label": "On.", "target": target}],
            }
        )
    nodes.append(
        {
            "id": "e_win",
            "body": "won",
            "is_ending": True,
            "ending": {
                "id": "end_win",
                "kind": "success",
                "valence": "positive",
                "title": "Earned",
            },
        }
    )
    nodes.append(
        {
            "id": "e_disc",
            "body": "peeked",
            "is_ending": True,
            "ending": {
                "id": "end_disc",
                "kind": "discovery",
                "valence": "positive",
                "title": "A Glimpse",
            },
        }
    )
    return {
        "start_node": "start",
        "metadata": {
            "age_band": "8-11",
            "tier": 1,
            "topology": "branch_and_bottleneck",
            "length": "short",
            "narrative_style": "prose",
            "production_eligible": True,
            "ending_count": 2,
        },
        "variables": [],
        "nodes": nodes,
    }


@pytest.mark.unit
def test_m2_is_registered_under_its_op_id() -> None:
    """The M2 singleton is registered and exposes its stable op id."""
    assert M2.op_id == M2_OP_ID == "M2"


@pytest.mark.unit
def test_m2_permutes_two_positive_endings_on_a_small_fixture() -> None:
    """An explicit re-map swaps the two positive payloads and keeps the multiset."""
    story = _two_kind_positive_fixture()
    before = _ending_by_node(story)
    result = M2.apply(
        story,
        OpParams.of(valence="positive", order="end_win,end_disc"),
        random.Random(0),
    )
    candidate = result.candidate
    after = _ending_by_node(candidate)
    # The two payloads (kind, title) have swapped node positions.
    assert after["e_disc"] == before["e_win"]
    assert after["e_win"] == before["e_disc"]
    # The multiset is invariant and ending ids stay unique (a bijection).
    assert _ending_multiset(candidate) == _ending_multiset(story)
    assert sorted(_ending_ids(candidate)) == sorted(_ending_ids(story))


@pytest.mark.unit
def test_m2_emits_reguide_for_the_affected_leaves() -> None:
    """A re-map emits an ending-title and a leaf-beat item per moved leaf."""
    story = _two_kind_positive_fixture()
    result = M2.apply(
        story,
        OpParams.of(valence="positive", order="end_win,end_disc"),
        random.Random(0),
    )
    ending_items = {
        item.target_id for item in result.reguide if item.target is ReguideTarget.ENDING
    }
    node_items = {
        item.target_id for item in result.reguide if item.target is ReguideTarget.NODE
    }
    # Both ending payloads moved, so both ending ids need title review.
    assert ending_items == {"end_win", "end_disc"}
    # Both leaves' beats need review, plus the shared upstream approach node.
    assert {"e_disc", "e_win"} <= node_items
    assert "start" in node_items  # advisory upstream approach node


@pytest.mark.unit
def test_m2_identity_permutation_rejected_at_preconditions() -> None:
    """An identity (no kind moves) re-map is a no-op and rejected at stage 0."""
    story = _two_kind_positive_fixture()
    report = M2.preconditions(
        story, OpParams.of(valence="positive", order="end_disc,end_win")
    )
    assert report.satisfied is False
    assert any("no-op" in reason or "identity" in reason for reason in report.failures)
    with pytest.raises(ValidationError):
        M2.apply(
            story,
            OpParams.of(valence="positive", order="end_disc,end_win"),
            random.Random(0),
        )


@pytest.mark.unit
def test_m2_rejects_a_single_kind_class_parent() -> None:
    """A parent whose endings share one kind admits no meaningful re-map."""
    story = _single_kind_fixture()
    report = M2.preconditions(story, OpParams.of())
    assert report.satisfied is False
    assert any("distinct ending kinds" in reason for reason in report.failures)


@pytest.mark.unit
def test_m2_moving_success_below_the_floor_is_discarded_pre_gate() -> None:
    """Moving a success ending onto a shallow leaf fails the PL-20 pre-check.

    Design section 4.3: relocating the satisfying kinds to shallower leaves is the
    one way M2 can break the arc clock, so the operator pre-computes it and
    discards at preconditions, before any gate run.
    """
    story = _pl20_fixture()
    # Positive class node ids sort e_disc < e_win, so position 0 is the shallow
    # e_disc leaf. order=[end_win, end_disc] puts the success block (end_win) on
    # that shallow leaf, dropping the fastest finish from 9 nodes to 2 (floor 9).
    report = M2.preconditions(
        story, OpParams.of(valence="positive", order="end_win,end_disc")
    )
    assert report.satisfied is False
    assert any("PL-20" in reason or "floor" in reason for reason in report.failures)
    with pytest.raises(ValidationError):
        M2.apply(
            story,
            OpParams.of(valence="positive", order="end_win,end_disc"),
            random.Random(0),
        )


@pytest.mark.unit
def test_catalog_has_m2_eligible_tier1_parents() -> None:
    """The Tier-1 corpus is discovered and many parents admit an M2 re-map."""
    assert len(_CATALOG) >= 20
    assert len(_ELIGIBLE) >= 10
    assert len(_BOTH) >= 1


@pytest.mark.unit
@pytest.mark.parametrize("story", [story for _, story in _ELIGIBLE], ids=_ELIGIBLE_IDS)
def test_m2_preserves_multiset_and_passes_gate_on_catalog(
    story: dict[str, object],
) -> None:
    """On every eligible Tier-1 parent, an rng re-map holds the safety invariants.

    Design section 4.3 preserved-by-construction set (the ``(kind, valence)``
    multiset), the PL-15 safety property (no new ending kind can appear, so a
    band-forbidden kind never can), and the acceptance property that the accepted
    output is never gate-blocked.
    """
    parent_multiset = _ending_multiset(story)
    parent_kinds = _ending_kinds(story)
    for seed in (0, 1, 2, 3):
        result = M2.apply(story, OpParams.of(), random.Random(seed))
        candidate = result.candidate
        # #ASSUME: the (kind, valence) multiset is invariant by construction (a
        # permutation), which is WHY PL-15 can never fire on an M2 output: no kind
        # absent from the parent can appear, so a band-forbidden kind cannot be
        # introduced. The gate re-proves PL-15 at stage 1 regardless.
        assert _ending_multiset(candidate) == parent_multiset
        assert _ending_kinds(candidate) <= parent_kinds
        # The full unchanged gate never blocks the accepted output.
        assert run_gate(candidate).blocked is False


@pytest.mark.unit
@pytest.mark.parametrize("story", [story for _, story in _ELIGIBLE], ids=_ELIGIBLE_IDS)
def test_m2_preserves_graph_shape_and_is_structurally_a_clone(
    story: dict[str, object],
) -> None:
    """M2 leaves the graph shape identical, so ``structural_distance`` is ~0.

    Design section 4.3 composition note: because ``structure_fingerprint`` strips
    ending titles and ``structural_distance``'s features are aggregate /
    position-blind, an M2-only mutant is structurally indistinguishable from its
    parent (distance ~0) and the D7 anti-clone floor will correctly reject it.
    The fingerprint itself may or may not differ (ending kind is retained in the
    stripped structure); the load-bearing claim is the zero structural distance.
    """
    result = M2.apply(story, OpParams.of(), random.Random(0))
    candidate = result.candidate
    assert _node_ids(candidate) == _node_ids(story)
    assert _edges(candidate) == _edges(story)
    assert _in_degrees(candidate) == _in_degrees(story)
    assert structural_distance(story, candidate) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.unit
@pytest.mark.parametrize("story", [story for _, story in _ELIGIBLE], ids=_ELIGIBLE_IDS)
def test_m2_is_deterministic_per_seed_on_catalog(story: dict[str, object]) -> None:
    """The same seed reproduces a byte-identical candidate."""
    a = M2.apply(story, OpParams.of(), random.Random(11)).candidate
    b = M2.apply(story, OpParams.of(), random.Random(11)).candidate
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


@pytest.mark.unit
def test_m2_explicit_params_are_deterministic() -> None:
    """The same explicit valence/order reproduces a byte-identical candidate."""
    story = _two_kind_positive_fixture()
    params = OpParams.of(valence="positive", order="end_win,end_disc")
    a = M2.apply(story, params, random.Random(0)).candidate
    b = M2.apply(story, params, random.Random(99)).candidate  # rng unused for params
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


@pytest.mark.unit
@pytest.mark.parametrize("story", [story for _, story in _BOTH], ids=_BOTH_IDS)
def test_m2_composed_after_m1_clears_gate_with_both_changes(
    story: dict[str, object],
) -> None:
    """M1 then M2 clears the gate and carries a structural change AND an outcome remap.

    An operator is a pure ``(document, params, rng) -> MutationResult``, so a
    length-2 chain is just applying M2 to M1's ``result.candidate`` (the
    ``op_chain`` lineage schema is D8). The final candidate must (a) clear the
    unchanged gate and cell assertion, (b) differ structurally from the original
    (M1's swap), and (c) re-map at least one ending outcome (M2).
    """
    m1_candidate = M1.apply(story, OpParams.of(), random.Random(0)).candidate
    # Feed M1's candidate to M2 through the unchanged acceptance harness.
    result = run_acceptance(M2, m1_candidate, OpParams.of(), seed=1)
    assert result.discarded_at_stage is None  # cleared gate + cell
    final = result.candidate
    assert final is not None
    # M1 re-pairs which choice leads to which subtree; M2 never touches choice
    # targets, so the final per-choice target map differs from the original
    # parent's (the structural contribution of M1). A same-decision sibling swap
    # leaves the edge *set* identical, so the per-choice map is the honest signal.
    assert _choice_targets(final) != _choice_targets(story)
    # M1 leaves ending blocks on their nodes, so M2 is the only source of an
    # outcome re-map: some node's (kind, title) differs from the M1 candidate's.
    assert _ending_by_node(final) != _ending_by_node(m1_candidate)
    # The whole chain preserves the (kind, valence) multiset.
    assert _ending_multiset(final) == _ending_multiset(story)


@pytest.mark.unit
def test_m2_cinderwick_smoke_is_accepted_and_held() -> None:
    """A live catalog parent is accepted (held, re-guidance outstanding) by M2."""
    story = cast(
        "dict[str, object]", json.loads(_CINDERWICK.read_text(encoding="utf-8"))
    )
    result = run_acceptance(M2, story, OpParams.of(), seed=0, parent_slug="cinderwick")
    assert result.discarded_at_stage is None
    assert result.held is True
    assert result.promotable is False
    assert result.reguide_outstanding > 0


@pytest.mark.unit
@settings(max_examples=25, deadline=None)
@given(seed=st.integers(min_value=0, max_value=10_000))
def test_m2_gate_property_over_seeds(seed: int) -> None:
    """For arbitrary seeds on a representative parent, output is never gate-blocked."""
    story = _representative_parent()
    result = M2.apply(story, OpParams.of(), random.Random(seed))
    assert run_gate(result.candidate).blocked is False
    assert _ending_multiset(result.candidate) == _ending_multiset(story)
    again = M2.apply(story, OpParams.of(), random.Random(seed)).candidate
    assert json.dumps(result.candidate, sort_keys=True) == json.dumps(
        again, sort_keys=True
    )


def _representative_parent() -> dict[str, object]:
    """Return a real, gate-passing M2-eligible Tier-1 catalog parent."""
    for _slug, story in _ELIGIBLE:
        return story
    pytest.skip("no eligible Tier-1 catalog parent available")
