"""Score a story graph against the structural properties a reader depends on.

Usage:
    uv run python scripts/check_graph_structure.py <story.json>... [--check]

Written for Q-3, which asks how close an unaided model gets to a valid story
graph with no skeleton to work from. The project gate answers a different and
larger question (safety, reading level, band profile, sentinel integrity); this
answers only "is this a well-formed piece of interactive fiction", which is the
part a skeleton would otherwise have guaranteed by construction.

**Six failure classes, all deterministic**, and every one of them is something
a child would actually hit:

- `dangling_target`, a choice pointing at a node that does not exist. The
  reader taps it and there is nowhere to go.
- `unreachable_node`, prose no path arrives at. Invisible, and paid for.
- `sink_node`, a non-ending node offering no choices. The story stops without
  ending.
- `ending_with_choices`, an ending node still offering options.
- `no_ending_reachable`, a node from which no ending can be reached at all.
  The reader is inside a closed loop.
- `start_missing`, a declared start node that is not in the graph.

**Repairability is reported alongside, because it is the half of Q-3's
falsifier that the counting does not settle.** A `dangling_target` needs
somebody to decide where the choice should have pointed, which is authorial
judgement. An `ending_with_choices` is a deletion. That distinction decides
whether a low yield is a cost or a refutation, so it is computed here rather
than argued about afterwards.

**What it does not check.** Whether the story is any good, whether its branches
are meaningfully different, whether the prose suits the band. Structural
validity is necessary and nowhere near sufficient, and a graph passing this is
merely eligible to be judged.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from pathlib import Path
from typing import Any, NamedTuple, cast

# Whether a failure class can be repaired without an author deciding anything.
MECHANICAL = {
    "ending_with_choices": True,
    "unreachable_node": True,
    "dangling_target": False,
    "sink_node": False,
    "no_ending_reachable": False,
    "start_missing": False,
}


class Failure(NamedTuple):
    """One structural defect, and whether fixing it needs an author."""

    kind: str
    node_id: str
    detail: str

    @property
    def mechanical(self) -> bool:
        """Whether this can be repaired without authorial judgement."""
        return MECHANICAL.get(self.kind, False)


def _nodes(story: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the graph's nodes keyed by id."""
    return {
        str(n["id"]): n
        for n in cast("list[dict[str, Any]]", story.get("nodes") or [])
        if n.get("id")
    }


def failures(story: dict[str, Any]) -> list[Failure]:
    """Return every structural defect in one story graph.

    Args:
        story: The decoded story JSON.

    Returns:
        Every failure found, in class order.
    """
    nodes = _nodes(story)
    start = str(story.get("start_node") or "")
    out: list[Failure] = []
    if start not in nodes:
        return [
            Failure("start_missing", start, "declared start node is not in the graph")
        ]

    def targets(node: dict[str, Any]) -> list[str]:
        return [
            str(c["target"])
            for c in cast("list[dict[str, Any]]", node.get("choices") or [])
            if c.get("target")
        ]

    for node_id, node in nodes.items():
        is_ending = bool(node.get("is_ending"))
        choices = cast("list[dict[str, Any]]", node.get("choices") or [])
        if is_ending and choices:
            out.append(
                Failure("ending_with_choices", node_id, f"{len(choices)} choice(s)")
            )
        if not is_ending and not choices:
            out.append(Failure("sink_node", node_id, "no choices and not an ending"))
        out.extend(
            Failure("dangling_target", node_id, f"-> {target}")
            for target in targets(node)
            if target not in nodes
        )

    # Forward reachability from the start.
    seen = {start}
    queue = deque([start])
    while queue:
        for target in targets(nodes[queue.popleft()]):
            if target in nodes and target not in seen:
                seen.add(target)
                queue.append(target)
    out.extend(
        Failure("unreachable_node", n, "no path from the start reaches it")
        for n in sorted(set(nodes) - seen)
    )

    # Backward: which nodes can still reach an ending. Iterate to a fixed point
    # rather than walking forward, so cycles resolve correctly.
    can_end = {n for n, node in nodes.items() if node.get("is_ending")}
    changed = True
    while changed:
        changed = False
        for node_id, node in nodes.items():
            if node_id not in can_end and any(t in can_end for t in targets(node)):
                can_end.add(node_id)
                changed = True
    out.extend(
        Failure("no_ending_reachable", n, "trapped: no ending is reachable from here")
        for n in sorted(seen - can_end)
    )
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 1 with --check when any graph has a failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stories", nargs="+", help="Story graph JSON files.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    clean = 0
    all_failures: list[Failure] = []
    sys.stdout.write(
        f"{'graph':22s} {'nodes':>6s} {'ends':>5s} {'forks':>6s} {'failures':>9s}  verdict\n"
    )
    sys.stdout.write("-" * 72 + "\n")
    for path in args.stories:
        story = cast(
            "dict[str, Any]",
            json.loads(Path(path).resolve().read_text(encoding="utf-8")),
        )
        nodes = _nodes(story)
        found = failures(story)
        all_failures.extend(found)
        clean += not found
        endings = sum(1 for n in nodes.values() if n.get("is_ending"))
        forks = sum(
            1
            for n in nodes.values()
            if len(cast("list[Any]", n.get("choices") or [])) >= 2
        )
        sys.stdout.write(
            f"{Path(path).stem:22s} {len(nodes):6d} {endings:5d} {forks:6d} "
            f"{len(found):9d}  {'clean' if not found else 'FAILS'}\n"
        )
        for f in found[:8]:
            hand = "mechanical" if f.mechanical else "needs an author"
            sys.stdout.write(f"    {f.kind:20s} {f.node_id:16s} {f.detail}  [{hand}]\n")

    total = len(args.stories)
    sys.stdout.write(
        f"\nstructurally clean: {clean} of {total} ({clean / total:.0%})\n"
    )
    if all_failures:
        needs_author = sum(1 for f in all_failures if not f.mechanical)
        sys.stdout.write(
            f"failures: {len(all_failures)}, of which {needs_author} need authorial "
            f"judgement and {len(all_failures) - needs_author} are mechanical\n"
        )
        by_kind: dict[str, int] = {}
        for f in all_failures:
            by_kind[f.kind] = by_kind.get(f.kind, 0) + 1
        for kind, n in sorted(by_kind.items(), key=lambda kv: -kv[1]):
            sys.stdout.write(f"  {kind:22s} {n}\n")
    return 1 if (all_failures and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
