"""Emit the two prose questions only a model can answer, as a bounded worklist.

Usage:
    uv run python scripts/build_prose_review_worklist.py <skeleton.json>
        <contract.json> <filled.json> [--out worklist.json]

Two defects reached finished books through every guard in this programme and
were found by blind readers rather than by tooling. Both are entailment
questions about prose, and this programme has twice measured what happens when
those are attempted lexically: precision 0.167 on obligation delivery
(`check_fill_fidelity.py`), and 2 of 6 props classified on an unseen contract
(`AL-211`). So this does not judge. **It builds the smallest correct list of
things a model must read, and stops.**

**Item 1, label against destination (`AL-227`).** A rater found a book whose
option "Call the risk not worth it" leads to a scene in which the character
attempts the crossing and slips, and another whose "Leave the lever broken"
leads to a scene saying the splice held. The label promises one thing and the
destination delivers another. A child choosing the cautious option gets the
risk anyway.

*The deterministic half*: pair every choice's label and stated semantics with
the opening of the node it leads to. That is the whole context needed, and it
is 35 short pairs for a 26-node book.

**Item 2, prose over-assumption at merges (`AL-228`).** Fact-graph closure
constrains what a node may *assume*, and it is enforced on the contract. Nothing
enforces it on the prose. A merge node's text named clues from two of four rooms
when a reader visits exactly one: closure passed under two independent
implementations while the prose violated the same property.

*The deterministic half*: for each node with several parents, compute the facts
its `entry_state` does **not** guarantee but which some parent establishes, then
hand a model the node's prose and that list. Merge nodes are few, three in a
26-node graph and a handful in a 101-node one, so the cost is bounded by
structure rather than by book length.

**Why one script for two checks.** They share their input assembly, they share
their reviewer, and both are per-node prose entailment against a contract. Two
scripts would mean two passes over the same book for one human or one model.

**What a caller does with this.** Feed each item's `question` and `context` to a
model, one call per item, and treat any `yes` as a defect to repair. The output
is deliberately plain JSON with no scoring: adding a lexical pre-filter here
would reintroduce exactly the false-confidence this programme has measured
twice.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple, cast

_OPENING_CHARS = 400
_MIN_PARENTS = 2


class Item(NamedTuple):
    """One question for a model, with everything needed to answer it."""

    kind: str
    node_id: str
    question: str
    context: dict[str, Any]


def _load(path: str) -> dict[str, Any]:
    """Load a JSON object from path."""
    return cast(
        "dict[str, Any]", json.loads(Path(path).resolve().read_text(encoding="utf-8"))
    )


def _parents(skeleton: dict[str, Any]) -> dict[str, list[str]]:
    """Return {node_id: [parent ids]} over the graph."""
    out: dict[str, list[str]] = {}
    for node in cast("list[dict[str, Any]]", skeleton.get("nodes") or []):
        for choice in cast("list[dict[str, Any]]", node.get("choices") or []):
            target = str(choice.get("target") or "")
            if target:
                out.setdefault(target, []).append(str(node["id"]))
    return out


def label_items(
    skeleton: dict[str, Any], contract: dict[str, Any], filled: dict[str, Any]
) -> list[Item]:
    """Build one item per choice, pairing its label with its destination.

    Args:
        skeleton: The decoded skeleton, source of graph shape.
        contract: The decoded narrative contract, source of choice semantics.
        filled: The finished storybook, source of labels and prose.

    Returns:
        One Item per choice that has a destination with prose.
    """
    bodies = {
        str(n["id"]): str(n.get("body") or "")
        for n in cast("list[dict[str, Any]]", filled.get("nodes") or [])
    }
    labels = {
        (str(n["id"]), str(c["id"])): str(c.get("label") or "")
        for n in cast("list[dict[str, Any]]", filled.get("nodes") or [])
        for c in cast("list[dict[str, Any]]", n.get("choices") or [])
    }
    nodes = cast("dict[str, Any]", contract.get("nodes") or {})
    out: list[Item] = []
    for node in cast("list[dict[str, Any]]", skeleton.get("nodes") or []):
        node_id = str(node["id"])
        semantics = cast(
            "dict[str, str]", (nodes.get(node_id) or {}).get("choice_semantics") or {}
        )
        for choice in cast("list[dict[str, Any]]", node.get("choices") or []):
            choice_id, target = str(choice["id"]), str(choice.get("target") or "")
            if target not in bodies:
                continue
            out.append(
                Item(
                    "label_destination",
                    node_id,
                    "Does the destination text deliver what this option's label "
                    "promises? Answer no if the label offers to decline, retreat "
                    "or avoid something and the text has it happen anyway, or if "
                    "the label promises to take or claim an object the text never "
                    "mentions again.",
                    {
                        "choice": f"{node_id}.{choice_id}",
                        "label": labels.get((node_id, choice_id), ""),
                        "stated_meaning": semantics.get(choice_id, ""),
                        "destination": target,
                        "destination_opening": bodies[target][:_OPENING_CHARS],
                    },
                )
            )
    return out


def merge_items(
    skeleton: dict[str, Any], contract: dict[str, Any], filled: dict[str, Any]
) -> list[Item]:
    """Build one item per merge node, listing what its prose may not assume.

    Args:
        skeleton: The decoded skeleton, source of graph shape.
        contract: The decoded narrative contract, source of facts.
        filled: The finished storybook, source of prose.

    Returns:
        One Item per multi-parent node that has facts it must not assume.
    """
    bodies = {
        str(n["id"]): str(n.get("body") or "")
        for n in cast("list[dict[str, Any]]", filled.get("nodes") or [])
    }
    nodes = cast("dict[str, Any]", contract.get("nodes") or {})
    facts = cast("dict[str, Any]", contract.get("facts") or {})
    out: list[Item] = []
    for node_id, parents in _parents(skeleton).items():
        if len(parents) < _MIN_PARENTS or node_id not in nodes:
            continue
        guaranteed = set(cast("list[str]", nodes[node_id].get("entry_state") or []))
        # A fact some parent establishes but the merge cannot assume, because
        # not every path in supplies it. This is what the prose may not lean on.
        forbidden = {
            fact
            for parent in parents
            if parent in nodes
            for fact in cast("list[str]", nodes[parent].get("establishes") or [])
        } - guaranteed
        if not forbidden or node_id not in bodies:
            continue
        out.append(
            Item(
                "merge_assumption",
                node_id,
                "Does this node's prose refer to, or depend on, anything in the "
                "may-not-assume list? A reader arrives here by only one path, so "
                "naming a detail from a path they did not take is a defect.",
                {
                    "node": node_id,
                    "parents": sorted(parents),
                    "may_assume": sorted(guaranteed),
                    "may_not_assume": {
                        fact: (facts.get(fact) if isinstance(facts, dict) else fact)
                        for fact in sorted(forbidden)
                    },
                    "prose": bodies[node_id],
                },
            )
        )
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Always returns 0: this builds work, it does not judge."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skeleton")
    parser.add_argument("contract")
    parser.add_argument("filled")
    parser.add_argument("--out", help="Write the worklist as JSON to this path.")
    args = parser.parse_args(argv)

    skeleton, contract, filled = (
        _load(args.skeleton),
        _load(args.contract),
        _load(args.filled),
    )
    items = label_items(skeleton, contract, filled) + merge_items(
        skeleton, contract, filled
    )

    by_kind: dict[str, int] = {}
    for item in items:
        by_kind[item.kind] = by_kind.get(item.kind, 0) + 1
    for kind, n in sorted(by_kind.items()):
        sys.stdout.write(f"{kind:24s} {n} item(s)\n")
    sys.stdout.write(f"{'total model calls':24s} {len(items)}\n")

    if args.out:
        Path(args.out).resolve().write_text(
            json.dumps([i._asdict() for i in items], indent=1, ensure_ascii=False),
            encoding="utf-8",
        )
        sys.stdout.write(f"wrote {args.out}\n")
    else:
        sys.stdout.write("\nfirst item of each kind:\n")
        for kind in sorted(by_kind):
            first = next(i for i in items if i.kind == kind)
            sys.stdout.write(
                f"  [{kind}] {first.node_id}\n"
                f"    {json.dumps(first.context, ensure_ascii=False)[:220]}\n"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
