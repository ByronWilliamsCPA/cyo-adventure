"""Per-merge notes for the fill prompt: which passages arrive at each merge.

A merge node is a node reached from two or more distinct nodes. Its single
``body`` is shown to every reader who arrives, whichever way they came, so it
must be true on every inbound route. The fill model sees the whole skeleton but
was never told which nodes are merges or what arrives at them, and the
editorial read of 2026-11-20 found it compensating in the worst way available:
69 merge bodies that open by telling the reader their route did not matter
("Whichever way Mira had come, every path had led her here"), and others that
state a companion's position or a fact only some routes earned.

This module renders a compact, deterministic note per merge (its id and its
inbound node ids) for the user block of every fill prompt, so the model can
write a body that presupposes only what every inbound route establishes.

The merge definition is the one ``validator/agency.py::inbound_sources`` uses
(distinct source nodes, self-loops excluded), restated here rather than
imported because that module is report-first and kept off the request path;
``tests/unit/test_merge_notes.py`` pins the two to the same answer on a
committed skeleton so they cannot drift apart silently.

Pure: stdlib only, no I/O.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Collection

__all__ = [
    "NO_MERGES_IN_BATCH",
    "NO_MERGES_IN_SKELETON",
    "merge_inbound",
    "render_merge_notes",
]

NO_MERGES_IN_SKELETON = (
    "No passage in this skeleton is reached from more than one other passage."
)
"""Rendered when the skeleton has no merge node at all."""

NO_MERGES_IN_BATCH = (
    "None of the passages you are writing now is reached from more than one "
    "other passage."
)
"""Rendered on the chunked path when the batch holds no merge node."""

_INTRO = (
    "Each passage below is reached from every passage listed after it. A reader "
    "can arrive from any one of them, so write its body to be true for all of "
    "them: open in the scene, and do not state anything (where a companion or "
    "object is, what the hero has learned or picked up) that only some of those "
    "passages establish. Never tell the reader their route did not matter."
)


def _node_dicts(document: dict[str, object]) -> list[dict[str, object]]:
    """Return the document's node dicts in document order, skipping non-dicts.

    Args:
        document: A skeleton or story document.

    Returns:
        The node dicts, in the order the document lists them.
    """
    raw = document.get("nodes")
    if not isinstance(raw, list):
        return []
    return [
        cast("dict[str, object]", entry)
        for entry in cast("list[object]", raw)
        if isinstance(entry, dict)
    ]


def _targets(node: dict[str, object]) -> list[str]:
    """Return the string targets of a node's choices, in declared order.

    Args:
        node: One node dict.

    Returns:
        Each choice's ``target`` that is a string; other entries are skipped.
    """
    raw = node.get("choices")
    if not isinstance(raw, list):
        return []
    targets: list[str] = []
    for entry in cast("list[object]", raw):
        if isinstance(entry, dict):
            target = cast("dict[str, object]", entry).get("target")
            if isinstance(target, str):
                targets.append(target)
    return targets


def merge_inbound(document: dict[str, object]) -> dict[str, tuple[str, ...]]:
    """Map each merge node to the distinct nodes with a choice targeting it.

    A merge is a node with two or more distinct inbound source nodes. A
    self-loop is not counted, because a node that leads back to itself has
    not been reached by a different route. Two choices from the same source
    count once.

    Ordering is deterministic and follows the document: merges appear in the
    order the document lists them, and each merge's sources in the order the
    document lists the source nodes. The same document therefore always
    renders the same prompt bytes.

    Args:
        document: A skeleton or story document (decoded JSON).

    Returns:
        Merge node id to its inbound source ids. Nodes with fewer than two
        distinct sources, and targets naming no node, are absent.
    """
    identified = [
        (node_id, node)
        for node in _node_dicts(document)
        if isinstance(node_id := node.get("id"), str)
    ]
    order = [node_id for node_id, _node in identified]
    inbound: dict[str, list[str]] = {node_id: [] for node_id in order}
    for source, node in identified:
        for target in _targets(node):
            sources = inbound.get(target)
            if sources is not None and target != source and source not in sources:
                sources.append(source)
    return {
        node_id: tuple(inbound[node_id])
        for node_id in order
        if len(inbound[node_id]) >= 2
    }


def render_merge_notes(
    document: dict[str, object], *, only: Collection[str] | None = None
) -> str:
    """Render the per-merge notes block for a fill prompt.

    Args:
        document: The skeleton being filled (decoded JSON).
        only: When given, restrict the notes to merges whose id is in this
            collection. The chunked path passes the batch's node ids, since the
            model writes only those passages and a note about any other merge
            would be input it cannot act on.

    Returns:
        A short markdown block: an instruction line followed by one bullet per
        merge, ``- `merge_id` (from `a`, `b`)``. When there is no merge to
        report, a single sentence saying so, so the template never ships an
        empty section.
    """
    merges = merge_inbound(document)
    if only is not None:
        wanted = set(only)
        merges = {
            node_id: srcs for node_id, srcs in merges.items() if node_id in wanted
        }
        if not merges:
            return NO_MERGES_IN_BATCH
    if not merges:
        return NO_MERGES_IN_SKELETON
    lines = [_INTRO, ""]
    for node_id, sources in merges.items():
        listed = ", ".join(f"`{source}`" for source in sources)
        lines.append(f"- `{node_id}` (from {listed})")
    return "\n".join(lines)
