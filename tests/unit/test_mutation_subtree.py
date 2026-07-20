"""Unit and property tests for subtree extraction (WS-5 D1, subtree.py).

The self-containment soundness property (design section 4.1 #CRITICAL block)
runs exhaustively over every node of every production catalog skeleton: for
every possible root, an ``extract_subtree`` result that reports itself
self-contained must survive a full edge scan proving no external node points
into the region anywhere but the root.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation.subtree import (
    adjacency,
    all_edges,
    descendants,
    extract_subtree,
    is_closed,
    is_self_contained,
    node_ids,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

# The catalog root, resolved from this test file (repo root is two parents up
# from tests/unit/), so the test is location-independent.
_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"


def _load_catalog() -> list[tuple[str, dict[str, object]]]:
    """Return ``(slug, story)`` for every production catalog skeleton.

    Mirrors ``generation.skeleton_match._production_candidates``: it skips
    ``*.contract.json`` sidecars and any skeleton whose metadata explicitly
    sets ``production_eligible`` to ``False`` (the three MVP/test seeds), so the
    corpus is exactly the production trees a mutant could descend from.

    Returns:
        list[tuple[str, dict[str, object]]]: The loaded skeletons, sorted by
            band then slug.
    """
    catalog: list[tuple[str, dict[str, object]]] = []
    for path in sorted(_SKELETONS_ROOT.glob("*/*.json")):
        if path.name.endswith(".contract.json"):
            continue
        story = cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))
        meta = story.get("metadata")
        if isinstance(meta, dict):
            eligible = cast("dict[str, object]", meta).get("production_eligible")
            if eligible is False:
                continue
        catalog.append((path.stem, story))
    return catalog


_CATALOG = _load_catalog()
_CATALOG_IDS = [slug for slug, _ in _CATALOG]


@pytest.mark.unit
def test_catalog_is_non_empty() -> None:
    """The production corpus is discovered (guards against a broken loader)."""
    assert len(_CATALOG) >= 50


@pytest.mark.unit
@pytest.mark.parametrize("story", [story for _, story in _CATALOG], ids=_CATALOG_IDS)
def test_extract_subtree_self_containment_is_sound(story: dict[str, object]) -> None:
    """For every root, a self-contained result has external in-edges only at root.

    This is the design section 4.1 #VERIFY: it enumerates in-edges over the
    WHOLE graph and confirms the utility never reports self-containment while an
    external node points into the region at a non-root node.
    """
    edges = all_edges(story)
    for root in node_ids(story):
        subtree = extract_subtree(story, root)
        assert root in subtree.node_ids
        # A forward closure can never leak an out-edge, so it is always closed.
        assert subtree.closed is True
        if not subtree.self_contained:
            assert subtree.external_in_edges
            continue
        # Exhaustive soundness scan: no external node enters the region except
        # at the root.
        for edge in edges:
            if edge.target in subtree.node_ids and edge.target != root:
                assert edge.source in subtree.node_ids


@pytest.mark.unit
@pytest.mark.parametrize("story", [story for _, story in _CATALOG], ids=_CATALOG_IDS)
def test_extract_subtree_is_deterministic(story: dict[str, object]) -> None:
    """Extraction from a fixed root is reproducible."""
    root = story["start_node"]
    assert isinstance(root, str)
    assert extract_subtree(story, root) == extract_subtree(story, root)


@pytest.mark.unit
@pytest.mark.parametrize("story", [story for _, story in _CATALOG], ids=_CATALOG_IDS)
def test_start_node_roots_a_self_contained_closed_whole_story(
    story: dict[str, object],
) -> None:
    """The start node's closure is the reachable story and is self-contained."""
    root = story["start_node"]
    assert isinstance(root, str)
    subtree = extract_subtree(story, root)
    # Nothing outside the start's closure can point into it at a non-root node,
    # because every such node is only reachable through the start.
    assert subtree.self_contained is True


def _diamond_story() -> dict[str, object]:
    """Return a tiny reconverging graph: start branches to a/b, both meet at c."""
    return {
        "start_node": "start",
        "nodes": [
            {
                "id": "start",
                "choices": [
                    {"id": "s_a", "target": "a"},
                    {"id": "s_b", "target": "b"},
                ],
            },
            {"id": "a", "choices": [{"id": "a_c", "target": "c"}]},
            {"id": "b", "choices": [{"id": "b_c", "target": "c"}]},
            {"id": "c", "choices": [{"id": "c_end", "target": "end"}]},
            {"id": "end", "is_ending": True, "ending": {"id": "e1"}},
        ],
    }


@pytest.mark.unit
def test_reconverging_branch_is_not_self_contained() -> None:
    """A subtree rooted mid-diamond fails self-containment on the sibling in-edge."""
    story = _diamond_story()
    subtree = extract_subtree(story, "a")
    assert subtree.node_ids == frozenset({"a", "c", "end"})
    assert subtree.self_contained is False
    sources = {edge.source for edge in subtree.external_in_edges}
    targets = {edge.target for edge in subtree.external_in_edges}
    assert sources == {"b"}
    assert targets == {"c"}


@pytest.mark.unit
def test_is_closed_distinguishes_a_reconvergence_out_edge() -> None:
    """An explicit region with an out-edge is not closed; its closure is."""
    story = _diamond_story()
    closed, out_edges = is_closed(story, {"a"})
    assert closed is False
    assert {edge.target for edge in out_edges} == {"c"}
    # The full forward closure of a leaves no out-edge.
    assert is_closed(story, {"a", "c", "end"})[0] is True


@pytest.mark.unit
def test_is_self_contained_scans_the_whole_graph() -> None:
    """The in-edge scan considers external predecessors, not just region edges."""
    story = _diamond_story()
    # Region {a, c, end} rooted at a: the sibling edge b -> c enters a non-root
    # region node from outside, so the whole-graph scan must flag it.
    contained, violations = is_self_contained(story, {"a", "c", "end"}, "a")
    assert contained is False
    assert {edge.source for edge in violations} == {"b"}


@pytest.mark.unit
def test_descendants_follows_choice_edges_and_terminates_on_cycles() -> None:
    """Forward closure includes the root, reachable nodes, and survives a cycle."""
    story: dict[str, object] = {
        "start_node": "hub",
        "nodes": [
            {
                "id": "hub",
                "choices": [
                    {"id": "h_x", "target": "x"},
                    {"id": "h_end", "target": "end"},
                ],
            },
            {"id": "x", "choices": [{"id": "x_hub", "target": "hub"}]},
            {"id": "end", "is_ending": True, "ending": {"id": "e"}},
        ],
    }
    assert descendants(story, "hub") == frozenset({"hub", "x", "end"})
    assert descendants(story, "x") == frozenset({"x", "hub", "end"})


@pytest.mark.unit
def test_descendants_rejects_unknown_root() -> None:
    """A root that is not a declared node raises a ValidationError."""
    story: dict[str, object] = {
        "start_node": "a",
        "nodes": [{"id": "a", "is_ending": True, "ending": {"id": "e"}}],
    }
    with pytest.raises(ValidationError):
        descendants(story, "ghost")


@pytest.mark.unit
def test_adjacency_drops_dangling_targets() -> None:
    """A choice targeting a missing node contributes no edge."""
    story: dict[str, object] = {
        "start_node": "a",
        "nodes": [
            {
                "id": "a",
                "choices": [
                    {"id": "a_b", "target": "b"},
                    {"id": "a_ghost", "target": "ghost"},
                ],
            },
            {"id": "b", "is_ending": True, "ending": {"id": "e"}},
        ],
    }
    graph: Mapping[str, tuple[str, ...]] = adjacency(story)
    assert graph["a"] == ("b",)
    assert {(edge.source, edge.target) for edge in all_edges(story)} == {("a", "b")}


@pytest.mark.unit
def test_malformed_documents_yield_empty_graphs() -> None:
    """A missing node list or an id-less node contributes nothing, never raises."""
    assert node_ids({"nodes": "not-a-list"}) == frozenset()
    # An id-less node is skipped rather than crashing the adjacency scan.
    story: dict[str, object] = {
        "nodes": [{"choices": [{"id": "c", "target": "b"}]}, {"id": "b"}]
    }
    assert node_ids(story) == frozenset({"b"})
    assert adjacency(story) == {"b": ()}
