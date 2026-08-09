"""Validate a narrative obligation contract against its skeleton graph.

Usage:
    uv run python scripts/check_narrative_contract.py <skeleton.json>
        [--bible <bible.json>]

Deterministic NC checks from the skeleton-narrative-redesign proposal
(2026-08-09, sections 3 and 5). The narrative sidecar
(``<slug>.narrative.json``) declares per-node obligations (facts
established/forbidden, affect envelopes, choice semantics); these checks
make the obligations coherent against the graph BEFORE any prose exists,
which is the deterministic replacement for the assurance a verbatim beat
used to carry by provenance.

Checks:

- NC-0 coverage: every skeleton node has a contract entry and vice versa;
  every choice with declared semantics exists on the node.
- NC-1 merge closure: a node's declared ``entry_state`` must be guaranteed
  on EVERY path into it. Computed as a must-analysis fixpoint:
  ``guaranteed(n) = (intersection over parents of guaranteed(parent))
  union establishes(n)``, cycles handled by iterating from the
  all-facts top element.
- NC-2 dead beat: a non-reentrant node re-establishing a fact every parent
  already guarantees is a beat that says nothing new (warning).
- NC-3 orphan facts: every declared fact is established somewhere; a fact
  never consumed (never in any ``entry_state`` and not established by an
  ending node) is flagged (warning).
- NC-4 reentrancy: any node reachable from its own successors must declare
  ``reentrant: true`` and carry a ``reentry_contract`` (the shipped seed
  re-rendered its loss-discovery beat on every loop, AL-155).
- NC-5 (with ``--bible``): every device-vocabulary entry declares a kind in
  the contract's ``permitted_device_kinds``; every bible leaf string is a
  single printable line under 120 chars with no braces, directive markers,
  or em-dash; the band-mandatory denylist is applied to every leaf string.
- NC-6: every ``open``-tier node establishes at least one fact.

Exits 1 on any ERROR-severity finding; warnings print but do not fail.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.validator.slots import band_mandatory_bundles, denylisted_bundles


def _load(path: Path) -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))


def _graph(skeleton: dict[str, Any]) -> tuple[dict[str, list[str]], list[str], str]:
    """Return (successors, node ids, start node id)."""
    succ: dict[str, list[str]] = {}
    ids: list[str] = []
    for node in cast("list[dict[str, Any]]", skeleton["nodes"]):
        node_id = str(node["id"])
        ids.append(node_id)
        succ[node_id] = [
            str(c["target"])
            for c in cast("list[dict[str, Any]]", node.get("choices") or [])
        ]
    return succ, ids, str(skeleton["start_node"])


def _predecessors(succ: dict[str, list[str]]) -> dict[str, list[str]]:
    pred: dict[str, list[str]] = {n: [] for n in succ}
    for src, targets in succ.items():
        for target in targets:
            if target in pred:
                pred[target].append(src)
    return pred


def _reachable(succ: dict[str, list[str]], roots: list[str]) -> set[str]:
    seen: set[str] = set()
    frontier = list(roots)
    while frontier:
        node = frontier.pop()
        if node in seen:
            continue
        seen.add(node)
        frontier.extend(succ.get(node, []))
    return seen


def _guaranteed_facts(
    succ: dict[str, list[str]],
    pred: dict[str, list[str]],
    start: str,
    contracts: dict[str, dict[str, Any]],
    all_facts: frozenset[str],
) -> dict[str, frozenset[str]]:
    """Must-analysis fixpoint: facts guaranteed on every path into each node."""
    est = {
        n: frozenset(cast("list[str]", c.get("establishes") or []))
        for n, c in contracts.items()
    }
    guaranteed: dict[str, frozenset[str]] = dict.fromkeys(succ, all_facts)
    guaranteed[start] = est.get(start, frozenset())
    changed = True
    while changed:
        changed = False
        for node in succ:
            if node == start:
                incoming = est.get(start, frozenset())
            else:
                parents = pred.get(node) or []
                if not parents:
                    incoming = frozenset()
                else:
                    meet = guaranteed[parents[0]]
                    for parent in parents[1:]:
                        meet = meet & guaranteed[parent]
                    incoming = meet
                incoming = incoming | est.get(node, frozenset())
            if incoming != guaranteed[node]:
                guaranteed[node] = incoming
                changed = True
    return guaranteed


_BIBLE_MAX_CHARS = 120
_FORBIDDEN_SUBSTRINGS = ("{", "}", "<<", ">>", "\u2014")


def _bible_string_errors(text: str) -> list[str]:
    errors: list[str] = []
    if "\n" in text or "\r" in text:
        errors.append("must be a single line")
    if len(text) > _BIBLE_MAX_CHARS:
        errors.append(f"longer than {_BIBLE_MAX_CHARS} chars")
    errors.extend(
        f"contains forbidden token {token!r}"
        for token in _FORBIDDEN_SUBSTRINGS
        if token in text
    )
    if not text.isprintable():
        errors.append("contains non-printable characters")
    return errors


def check_bible(
    bible: dict[str, Any], contract: dict[str, Any], band: str
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a story bible against the contract."""
    errors: list[str] = []
    warnings: list[str] = []
    envelope = cast("dict[str, Any]", contract.get("safety_envelope") or {})
    permitted = set(cast("list[str]", envelope.get("permitted_device_kinds") or []))
    bundles = band_mandatory_bundles(AgeBand(band))

    def _walk_strings(value: object, path: str) -> None:
        if isinstance(value, str):
            errors.extend(
                f"NC-5 bible {path}: {problem}"
                for problem in _bible_string_errors(value)
            )
            hits = denylisted_bundles(value, bundles)
            if hits:
                errors.append(
                    f"NC-5 bible {path}: band-mandatory denylist hit {sorted(hits)}"
                )
        elif isinstance(value, dict):
            for key, item in cast("dict[str, Any]", value).items():
                _walk_strings(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(cast("list[Any]", value)):
                _walk_strings(item, f"{path}[{index}]")

    _walk_strings(bible, "$")
    vocab = cast("dict[str, Any]", bible.get("device_vocabulary") or {})
    for category, entries in vocab.items():
        for index, entry in enumerate(cast("list[Any]", entries)):
            if not isinstance(entry, dict):
                errors.append(f"NC-5 bible device {category}[{index}]: not an object")
                continue
            kind = str(cast("dict[str, Any]", entry).get("kind"))
            if permitted and kind not in permitted:
                errors.append(
                    f"NC-5 bible device {category}[{index}]: kind {kind!r} not in "
                    f"permitted_device_kinds"
                )
    return errors, warnings


def check_selection(
    selection: dict[str, Any], contract: dict[str, Any], bible: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """NC-7: validate a per-request selection vector (B-plus amendment 2).

    Every assigned device must exist verbatim in the bible under its
    category; ``kind_must_be`` constraints from the contract's invention
    specs are honored; a device marked ``unique_within_story`` is assigned
    to at most one node; and an ending node's ``mechanism`` must be drawn
    from that node's contract ``mechanisms`` list (falling back to
    ``premise.resolution_space``), with the mechanism-selection rule from
    AL-157: locked_outcome locks kind, valence, and affect, never the
    mechanism.
    """
    errors: list[str] = []
    warnings: list[str] = []
    contracts = cast("dict[str, dict[str, Any]]", contract.get("nodes") or {})
    vocab = cast("dict[str, Any]", bible.get("device_vocabulary") or {})
    by_category: dict[str, set[str]] = {
        category: {
            str(cast("dict[str, Any]", e).get("text"))
            for e in cast("list[Any]", entries)
            if isinstance(e, dict)
        }
        for category, entries in vocab.items()
    }
    category_of = {
        "clue_channel": "clue_channels",
        "obstacle": "obstacle_kinds",
        "help_mode": "help_modes",
        "container": "containers",
    }
    unique_seen: dict[str, str] = {}
    for node_id, assigned in selection.items():
        if node_id not in contracts:
            errors.append(f"NC-7: selection names unknown node {node_id!r}")
            continue
        entry = contracts[node_id]
        inventions = cast("dict[str, Any]", entry.get("invention") or {})
        for slot_name, device in cast("dict[str, Any]", assigned).items():
            if slot_name == "mechanism":
                space = cast(
                    "list[str]",
                    entry.get("mechanisms")
                    or cast("dict[str, Any]", contract.get("premise") or {}).get(
                        "resolution_space"
                    )
                    or [],
                )
                if str(device) not in space:
                    errors.append(
                        f"NC-7: {node_id!r} mechanism {device!r} not in the "
                        f"contract's mechanism space {space}"
                    )
                continue
            spec = cast("dict[str, Any]", inventions.get(slot_name) or {})
            spec_category = spec.get("category")
            if not isinstance(device, dict):
                errors.append(f"NC-7: {node_id}.{slot_name} is not a device object")
                continue
            device_map = cast("dict[str, Any]", device)
            text = str(device_map.get("text"))
            kind = str(device_map.get("kind"))
            category = (
                str(spec_category) if spec_category else category_of.get(slot_name)
            )
            if category and text not in by_category.get(category, set()):
                errors.append(
                    f"NC-7: {node_id}.{slot_name} device {text!r} is not in the "
                    f"bible's {category}"
                )
            must_be = spec.get("kind_must_be")
            if must_be and kind != str(must_be):
                errors.append(
                    f"NC-7: {node_id}.{slot_name} kind {kind!r} violates "
                    f"kind_must_be {must_be!r}"
                )
            if spec.get("unique_within_story"):
                prior = unique_seen.get(text)
                if prior and prior != node_id:
                    errors.append(
                        f"NC-7: device {text!r} assigned to both {prior!r} and "
                        f"{node_id!r} but is unique_within_story"
                    )
                unique_seen[text] = node_id
    return errors, warnings


def check_contract(
    skeleton: dict[str, Any], contract: dict[str, Any]
) -> tuple[list[str], list[str]]:
    """Run NC-0..NC-4 and NC-6. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    succ, node_ids, start = _graph(skeleton)
    pred = _predecessors(succ)
    contracts = cast("dict[str, dict[str, Any]]", contract.get("nodes") or {})
    declared_facts = frozenset(cast("dict[str, Any]", contract.get("facts") or {}))

    # NC-0 coverage
    errors.extend(
        f"NC-0: skeleton node {node_id!r} has no contract entry"
        for node_id in node_ids
        if node_id not in contracts
    )
    errors.extend(
        f"NC-0: contract node {node_id!r} not in the skeleton"
        for node_id in contracts
        if node_id not in succ
    )
    choice_ids = {
        str(c["id"]): str(n["id"])
        for n in cast("list[dict[str, Any]]", skeleton["nodes"])
        for c in cast("list[dict[str, Any]]", n.get("choices") or [])
    }
    for node_id, entry in contracts.items():
        errors.extend(
            f"NC-0: {node_id!r} declares semantics for {choice_id!r}, "
            f"which is not a choice on that node"
            for choice_id in cast("dict[str, Any]", entry.get("choice_semantics") or {})
            if choice_ids.get(choice_id) != node_id
        )
        for fact_list in ("entry_state", "establishes"):
            warnings.extend(
                f"NC-0: {node_id}.{fact_list} uses undeclared fact {fact!r}"
                for fact in cast("list[str]", entry.get(fact_list) or [])
                if fact not in declared_facts
            )
    if errors:
        return errors, warnings  # graph-mismatch makes the rest unreliable

    # NC-1 merge closure
    guaranteed = _guaranteed_facts(succ, pred, start, contracts, declared_facts)
    for node_id, entry in contracts.items():
        declared_entry = frozenset(cast("list[str]", entry.get("entry_state") or []))
        parents = pred.get(node_id) or []
        if node_id == start or not parents:
            available: frozenset[str] = frozenset()
        else:
            available = guaranteed[parents[0]]
            for parent in parents[1:]:
                available = available & guaranteed[parent]
        missing = declared_entry - available
        if missing:
            errors.append(
                f"NC-1: {node_id!r} presupposes {sorted(missing)} but some "
                f"inbound path does not guarantee it (parents: {sorted(parents)})"
            )

    # NC-2 dead beat (non-reentrant only), NC-4 reentrancy, NC-6 open establishes
    for node_id, entry in contracts.items():
        parents = pred.get(node_id) or []
        reentrant_declared = bool(entry.get("reentrant"))
        reachable_from_successors = node_id in _reachable(succ, succ.get(node_id, []))
        if reachable_from_successors and not reentrant_declared:
            errors.append(
                f"NC-4: {node_id!r} is reachable from its own successors but does "
                f"not declare reentrant: true"
            )
        if reachable_from_successors and not str(entry.get("reentry_contract") or ""):
            errors.append(f"NC-4: {node_id!r} is reentrant but has no reentry_contract")
        if not reachable_from_successors and parents and node_id != start:
            meet = guaranteed[parents[0]]
            for parent in parents[1:]:
                meet = meet & guaranteed[parent]
            redundant = (
                frozenset(cast("list[str]", entry.get("establishes") or [])) & meet
            )
            if redundant:
                warnings.append(
                    f"NC-2: {node_id!r} re-establishes {sorted(redundant)}, already "
                    f"guaranteed by every parent (dead beat)"
                )
        if str(entry.get("tier")) == "open" and not entry.get("establishes"):
            errors.append(f"NC-6: open node {node_id!r} establishes nothing")

    # NC-3 orphan facts
    established = {
        fact
        for entry in contracts.values()
        for fact in cast("list[str]", entry.get("establishes") or [])
    }
    ending_nodes = {
        str(n["id"])
        for n in cast("list[dict[str, Any]]", skeleton["nodes"])
        if n.get("ending")
    }
    consumed = {
        fact
        for entry in contracts.values()
        for fact in cast("list[str]", entry.get("entry_state") or [])
    } | {
        fact
        for node_id, entry in contracts.items()
        if node_id in ending_nodes
        for fact in cast("list[str]", entry.get("establishes") or [])
    }
    warnings.extend(
        f"NC-3: fact {fact!r} is declared but never established"
        for fact in sorted(declared_facts - established)
    )
    warnings.extend(
        f"NC-3: fact {fact!r} is never consumed (no entry_state or ending payoff)"
        for fact in sorted(declared_facts - consumed)
    )
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 when no errors, 1 otherwise."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skeleton", help="Path to the skeleton JSON.")
    parser.add_argument("--bible", default=None, help="Optional story-bible JSON.")
    parser.add_argument(
        "--selection",
        default=None,
        help="Optional selection-vector JSON (needs --bible).",
    )
    args = parser.parse_args(argv)
    skeleton_path = Path(args.skeleton)
    contract_path = skeleton_path.with_name(
        skeleton_path.name.removesuffix(".json") + ".narrative.json"
    )
    if not contract_path.is_file():
        sys.stderr.write(f"FAIL: no narrative contract at {contract_path}\n")
        return 1
    skeleton = _load(skeleton_path)
    contract = _load(contract_path)
    errors, warnings = check_contract(skeleton, contract)
    if args.bible:
        band = str(
            cast("dict[str, Any]", skeleton.get("metadata") or {}).get("age_band", "")
        )
        bible = _load(Path(args.bible))
        bible_errors, bible_warnings = check_bible(bible, contract, band)
        errors.extend(bible_errors)
        warnings.extend(bible_warnings)
        if args.selection:
            sel_errors, sel_warnings = check_selection(
                _load(Path(args.selection)), contract, bible
            )
            errors.extend(sel_errors)
            warnings.extend(sel_warnings)
    elif args.selection:
        sys.stderr.write("--selection requires --bible\n")
        return 2
    for warning in warnings:
        sys.stdout.write(f"WARNING {warning}\n")
    for error in errors:
        sys.stderr.write(f"FAIL {error}\n")
    if not errors:
        sys.stdout.write(
            f"ok: narrative contract coherent ({len(warnings)} warning(s))\n"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
