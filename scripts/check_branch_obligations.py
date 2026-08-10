"""Compare what each branch of a story graph is OBLIGED to deliver.

Usage:
    uv run python scripts/check_branch_obligations.py <skeleton.json>
        <contract.json> <contract.json> [--max-same-shape-rate 0.6] [--check]

The cheapest possible delivery check for a diversity intervention, and the one
that would have saved this project a fill, a rating, and two authoring rounds.

**What it measures.** For every branch out of every fork, the *obligation*: the
facts the destination presupposes on arrival (`entry_state`) that the fork does
not already guarantee. That set is what the branch must accomplish, whatever
prose eventually realizes it. Two contracts over one graph are then compared
branch by branch.

**Why it matters.** A contract may rename every fact, relocate every scene and
rewrite every choice label, and still oblige each branch to deliver the same
thing in the same place. When it does, the same decisions follow by necessity,
because a choice's meaning to a reader is what taking it accomplishes. Measured
on the pair this checker was built from: 28 of 28 branches owed an
identically-shaped obligation, with facts that were largely direct renames
(`past_the_seal` to `past_the_barred_door`, `trial_rooms_known` to
`service_points_known`, `at_the_dial` to `at_the_tide_board`). An independent
annotator, labelling the resulting choices blind, judged 28 of 28 to be the
same decision. This checker predicts that verdict from the contracts alone.

**Why it beats annotating the choices.** It is deterministic, needs no model,
no labelling principle, and no annotator agreement study, and it runs before a
single word of prose exists. A signature-based measure of the same property is
Class C, costs a model call per choice, and is only as good as an unstated
labelling convention: the same two artifacts scored 0.179 and 1.000 on tradeoff
reuse depending purely on who annotated them (AL-188). Use this first, and
spend annotation only on what survives it.

Reports the shape comparison (fully deterministic) and a rename analysis (a
weaker signal, since a genuinely new fact and a renamed one are not always
distinguishable without reading the prose).

Exits 1 with ``--check`` when too many branches owe the same-shaped obligation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple, cast

_SAME_SHAPE_CEILING = 0.6
_MIN_FORK_OPTIONS = 2


class Obligation(NamedTuple):
    """What one branch must deliver, and where."""

    node_id: str
    choice_id: str
    owed: frozenset[str]


def _load(path: str) -> dict[str, Any]:
    """Load a JSON object from path."""
    return cast(
        "dict[str, Any]", json.loads(Path(path).resolve().read_text(encoding="utf-8"))
    )


def _forks(skeleton: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    """Return {node_id: [(choice_id, target_id)]} for real forks only.

    A node offering one option is a page turn, not a decision, and including
    such nodes pads any rate with units that cannot repeat (AL-189).

    Args:
        skeleton: The decoded skeleton JSON.

    Returns:
        Mapping of fork node id to its (choice id, target) pairs.
    """
    out: dict[str, list[tuple[str, str]]] = {}
    for node in cast("list[dict[str, Any]]", skeleton.get("nodes") or []):
        choices = cast("list[dict[str, Any]]", node.get("choices") or [])
        if len(choices) >= _MIN_FORK_OPTIONS:
            out[str(node["id"])] = [
                (str(c["id"]), str(c["target"])) for c in choices if c.get("target")
            ]
    return out


def obligations(
    skeleton: dict[str, Any], contract: dict[str, Any]
) -> dict[tuple[str, str], Obligation]:
    """Return the obligation each branch carries under one contract.

    Args:
        skeleton: The decoded skeleton, source of graph shape.
        contract: The decoded narrative contract, source of per-node facts.

    Returns:
        Mapping of (fork id, choice id) to that branch's Obligation.
    """
    nodes = cast("dict[str, Any]", contract.get("nodes") or {})
    out: dict[tuple[str, str], Obligation] = {}
    for fork, branches in _forks(skeleton).items():
        if fork not in nodes:
            continue
        here = set(cast("list[str]", nodes[fork].get("entry_state") or []))
        for choice_id, target in branches:
            if target not in nodes:
                continue
            needs = set(cast("list[str]", nodes[target].get("entry_state") or []))
            out[(fork, choice_id)] = Obligation(
                fork, choice_id, frozenset(needs - here)
            )
    return out


def compare(
    skeleton: dict[str, Any], left: dict[str, Any], right: dict[str, Any]
) -> tuple[dict[str, float], list[str]]:
    """Compare two contracts' branch obligations over one graph.

    Args:
        skeleton: The shared skeleton.
        left: One decoded contract.
        right: The other decoded contract.

    Returns:
        A (scores, notes) pair.
    """
    a, b = obligations(skeleton, left), obligations(skeleton, right)
    keys = sorted(set(a) & set(b))
    notes: list[str] = []
    if not keys:
        return {}, ["no branch is declared by both contracts"]

    same_shape = 0
    identical = 0
    rename_map: dict[str, str] = {}
    for key in keys:
        owed_a, owed_b = a[key].owed, b[key].owed
        if len(owed_a) == len(owed_b):
            same_shape += 1
        if owed_a == owed_b:
            identical += 1
            notes.append(
                f"  {key[0]}.{key[1]}: identical obligation {sorted(owed_a)}"
            )
        elif len(owed_a) == 1 and len(owed_b) == 1:
            # A one-for-one swap at the same branch is the signature of a
            # renamed fact rather than a new commitment. Collected, not gated:
            # a renamed fact and a genuinely different one are not always
            # separable without reading the prose.
            rename_map[next(iter(owed_a))] = next(iter(owed_b))

    total = float(len(keys))
    if rename_map:
        notes.append(f"  {len(rename_map)} one-for-one fact swap(s), e.g.:")
        for src, dst in list(rename_map.items())[:5]:
            notes.append(f"      {src} -> {dst}")
    return (
        {
            "branches_compared": total,
            "same_shape_rate": same_shape / total,
            "identical_obligation_rate": identical / total,
            "one_for_one_swaps": float(len(rename_map)),
        },
        notes,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 unless --check and the ceiling is breached."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skeleton", help="The shared skeleton JSON.")
    parser.add_argument("contracts", nargs=2, help="Two contracts over that skeleton.")
    parser.add_argument(
        "--max-same-shape-rate",
        type=float,
        default=_SAME_SHAPE_CEILING,
        help=(
            "Ceiling on branches owing an identically-shaped obligation. Above "
            "this, the two contracts oblige the same work in the same places and "
            "the same decisions will follow however the prose is written."
        ),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    skeleton = _load(args.skeleton)
    left, right = (_load(p) for p in args.contracts)
    scores, notes = compare(skeleton, left, right)
    if not scores:
        for note in notes:
            sys.stderr.write(f"{note}\n")
        return 2

    for key, value in scores.items():
        shown = f"{value:.0f}" if "rate" not in key else f"{value:.3f}"
        sys.stdout.write(f"{key:28s} {shown}\n")
    for note in notes[:20]:
        sys.stdout.write(f"{note}\n")

    breached = scores["same_shape_rate"] > args.max_same_shape_rate
    if breached:
        sys.stderr.write(
            f"FAIL same-shape rate {scores['same_shape_rate']:.3f} > "
            f"{args.max_same_shape_rate}: both contracts oblige the same work at "
            f"the same branches, so the decisions are not meaningfully varied\n"
        )
    sys.stdout.write(f"{'FAIL' if breached else 'ok  '}: delivery check\n")
    return 1 if (breached and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
