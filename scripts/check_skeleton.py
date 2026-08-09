"""Validate a skeleton shell against the gate and its declared/briefed cell.

Usage:
    uv run python scripts/check_skeleton.py <skeleton.json> [--band B] [--length L]
        [--style S] [--topology T] [--tier N] [--allow-mvp] [--strict]

Runs ``load_skeleton`` (the full gate's blocking layers on the shell: structure,
references, reachability, budgets, policy incl. PL-19/20/21) and then asserts
the declared metadata matches the design brief when brief flags are given.
Used by Wave 5 of the story-inventory run (see
``docs/planning/story-inventory-initial-run.md`` section 6.1).

Every gate finding is printed at every severity (the loader used to discard
the report on a pass, so advisories were invisible here; 2026-08-09 review,
section 2.2).

``--strict`` is the bar for NEWLY DRAFTED skeletons (2026-08-09 review, Part
3): the grandfathered catalog keeps the default behavior, but a new shell
must also (a) carry no advisory from the escalation set (PL-19 story mean,
PL-23 clock, PL-24 ending mix, PL-25 first decision, PL-26 corridor density,
L1-7 below cell min), (b) pass the CG-1..CG-3 choice grammar
(``enforce_grammar=True``; CG-4 needs filled prose), (c) clear the band's
random-walk outcome floor: the probability that a uniform random reader
reaches a satisfying (positive- or neutral-valence) ending, (d) respect the
per-band max in-degree hard cap on tree-like topologies (reconvergence,
ruled blocking 2026-08-09), and (e) meet the breadth-scaled endings floor
counting only depth-qualified endings (at least a third of the arc floor
deep). All five are authoring-time policy, ruled 2026-08-09 (review Part 4);
they are deliberately NOT part of the production gate until the
grandfathered catalog is removed, so no rule id is claimed in the validator
catalog yet.

Exits 1 on a gate block, any brief mismatch, or (with ``--strict``) any
escalated advisory or a walk-floor breach.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import networkx as nx

from cyo_adventure.core.exceptions import ProjectBaseError
from cyo_adventure.generation.skeleton import FILL_MARKER, load_skeleton
from cyo_adventure.validator.band_profile import (
    breadth_scaled_floors,
    is_offered_cell,
    min_complete_floor,
    production_cell_budget,
    words_per_node_profile,
)
from cyo_adventure.validator.policy import node_word_count

if TYPE_CHECKING:
    from cyo_adventure.validator.gate import GateResult

# Advisory rule ids a newly drafted skeleton may not carry (--strict). The
# grandfathered catalog fires these on 40 of 61 skeletons; a new shell has no
# excuse. Two deliberate absences: L2-13 (past the hand-authoring ceiling) is
# a caution about review method, not a defect in the shell; CG-4 (choice
# label echoed in the next passage's opening) can only be judged on filled
# prose, and on a shell every body is a ``<<FILL>>`` directive, so it fires
# unconditionally. CG-4 belongs to the fill gate, not the shell gate.
STRICT_BLOCKING_WARNINGS: frozenset[str] = frozenset(
    {
        "PL-19",
        "PL-23",
        "PL-24",
        "PL-25",
        "PL-26",
        "L1-7",
        "CG-1",
        "CG-2",
        "CG-3",
    }
)

# Random-walk outcome floors by band (and, at the teen bands, narrative
# style): the minimum probability that a reader choosing uniformly at random
# reaches a satisfying (positive- or neutral-valence) ending. Grounding: the
# 2026-08-09 review measured the current catalog at medians of 100% (3-5),
# 71% (5-8), 43% (8-11), 29% (10-13), 0.3% (13-16) and 1.2% (16+); the teen
# gamebook floor of 2% forces a graded-setback economy without banning the
# lethal style. RULED 2026-08-09 (owner accepted review Part 4 R1): these
# values are the ratified floors for the rebuilt catalog.
_WALK_FLOORS: dict[str, float] = {
    "3-5": 0.60,
    "5-8": 0.40,
    "8-11": 0.25,
    "10-13": 0.15,
}
_TEEN_WALK_FLOORS: dict[str, float] = {"prose": 0.10, "gamebook": 0.02}
_TEEN_BANDS: frozenset[str] = frozenset({"13-16", "16+"})

# Reconvergence hard gate (RULED 2026-08-09: owner upgraded review Part 4 R4
# from advisory to blocking for the rebuilt catalog). Caps the maximum node
# in-degree, per band, for the tree-like topologies where a mega-funnel means
# corridors collapsing into one node (the removed clone pair funnelled 31
# branches into a single bottleneck). Topology-aware on the data, not as a
# concession: ``open_map`` hubs and ``loop_and_grow`` loops are re-entered by
# design (catalog medians 9 and 5, one legitimate hub at in-degree 126), so a
# blanket cap would ban two topology families outright. The exempt topologies
# get their reconvergence constraint from the per-path experience metrics
# (SQ-15) instead.
_RECONVERGENCE_CAPPED_TOPOLOGIES: frozenset[str] = frozenset(
    {"branch_and_bottleneck", "gauntlet", "sorting_hat", "time_cave"}
)
_MAX_INDEGREE_CAPS: dict[str, int] = {
    "3-5": 4,
    "5-8": 4,
    "8-11": 6,
    "10-13": 6,
    "13-16": 8,
    "16+": 8,
}

# Depth-qualified endings floor (RULED 2026-08-09, review Part 4 R2): under
# --strict, an ending counts toward the breadth-scaled endings floor only if
# its shortest depth from the start is at least this fraction of the cell's
# ``min_complete`` arc floor. Kills the shallow-failure-leaf incentive the
# AL-026 evidence exposed (a 746-node book satisfied its floor with 7 endings
# within two taps of the start) while preserving the breadth incentive.
_ENDING_DEPTH_QUALIFICATION_FRACTION = 1 / 3


def _headroom(story: dict[str, Any], metadata: dict[str, Any]) -> str:
    """Return a report of how close a skeleton sits to each budget edge.

    A pass/fail verdict tells an author nothing about proximity, and proximity is
    what makes ceiling-scale authoring tractable: hitting the depth cap or the
    arc floor becomes a tuning exercise rather than a rewrite (AL-018). This was
    previously available only inside a series-specific build script.

    Args:
        story: The raw skeleton document.
        metadata: Its metadata block.

    Returns:
        str: A newline-terminated multi-line report, or "" when the story
            declares no cell and therefore has no budget to be near.
    """
    band = str(metadata.get("age_band", ""))
    length = metadata.get("length")
    style = str(metadata.get("narrative_style", "prose"))
    nodes = story.get("nodes")
    if not isinstance(nodes, list) or length is None:
        return ""
    typed = cast("list[dict[str, Any]]", nodes)
    node_count = len(typed)
    endings = sum(1 for node in typed if node.get("ending"))
    decisions = sum(
        1
        for node in typed
        if not node.get("ending") and len(node.get("choices") or []) >= 2
    )
    lines: list[str] = []
    budget = production_cell_budget(band, str(length), style)
    if budget is not None:
        lo, hi, depth_max = budget
        lines.append(
            f"headroom nodes      {node_count} in {lo}..{hi} "
            f"({hi - node_count} below the ceiling)"
        )
        depth = _longest_path(story)
        if depth is not None:
            lines.append(
                f"headroom depth      {depth} of {depth_max} "
                f"({depth_max - depth} hops spare)"
            )
        else:
            lines.append(
                "headroom depth      undefined (the graph has a cycle, so L1-7 "
                "depth and branch_and_bottleneck do not apply)"
            )
    ending_floor, decision_floor = breadth_scaled_floors(node_count, style)
    lines.append(
        f"headroom endings    {endings} against floor {ending_floor} "
        f"({endings - ending_floor:+d})"
    )
    lines.append(
        f"headroom decisions  {decisions} against floor {decision_floor} "
        f"({decisions - decision_floor:+d})"
    )
    profile = words_per_node_profile(band, style)
    if profile is not None:
        target, adv_lo, adv_hi, hard = profile
        counts = [_declared_words(node) for node in typed]
        counts = [c for c in counts if c]
        if counts:
            mean = sum(counts) / len(counts)
            lines.append(
                f"headroom words      mean {mean:.1f} vs target {target} "
                f"({mean - target:+.1f}), advisory {adv_lo}-{adv_hi}, hard max {hard}"
            )
    floor = min_complete_floor(band, str(length), style)
    if floor is not None:
        lines.append(
            f"headroom arc floor  fastest satisfying finish must be >= {floor}"
        )
    return "".join(f"{line}\n" for line in lines)


def _declared_words(node: dict[str, Any]) -> int:
    """Return a node's declared FILL word target, or its prose word count."""
    body = node.get("body")
    if not isinstance(body, str):
        return 0
    return node_word_count(body)


def _longest_path(story: dict[str, Any]) -> int | None:
    """Return the longest path in hops, or None when the graph has a cycle."""
    graph: nx.DiGraph[str] = nx.DiGraph()
    nodes = cast("list[dict[str, Any]]", story.get("nodes") or [])
    for node in nodes:
        graph.add_node(str(node.get("id")))
    for node in nodes:
        for choice in cast("list[dict[str, Any]]", node.get("choices") or []):
            graph.add_edge(str(node.get("id")), str(choice.get("target")))
    if not nx.is_directed_acyclic_graph(graph):
        return None
    return len(nx.dag_longest_path(graph)) - 1


def satisfying_walk_probability(story: dict[str, Any]) -> float:
    """Return P(a uniform random walk ends on a positive/neutral ending).

    Model: from each non-ending node every choice is taken with equal
    probability. Solved by value iteration so cyclic topologies
    (``loop_and_grow``) converge instead of recursing forever.

    Two modelling simplifications, both conservative to state up front:
    choice ``condition`` gating is ignored (every choice is treated as
    available, so a Tier-2 informed reader's odds are at least this value),
    and choices whose target id is unknown are skipped (the gate's reference
    checks make that unreachable for a shell that loaded).

    Args:
        story: The decoded skeleton dict (gate-passed).

    Returns:
        float: The satisfying-outcome probability from the start node, in
            [0, 1]; 0.0 when the start node cannot be resolved.
    """
    nodes_raw = story.get("nodes")
    nodes: dict[str, dict[str, Any]] = {
        str(n.get("id")): n
        for n in cast("list[Any]", nodes_raw if isinstance(nodes_raw, list) else [])
        if isinstance(n, dict)
    }
    if not nodes:
        return 0.0
    prob: dict[str, float] = {}
    ending_ids: set[str] = set()
    for node_id, node in nodes.items():
        ending = node.get("ending")
        if isinstance(ending, dict):
            ending_ids.add(node_id)
            prob[node_id] = (
                1.0 if ending.get("valence") in ("positive", "neutral") else 0.0
            )
        else:
            prob[node_id] = 0.0
    # Termination: the walk's transition graph is absorbing (the gate's
    # reachability/termination layers guarantee every node reaches an ending),
    # so value iteration converges geometrically; the iteration cap is a
    # safety net for malformed input, not the expected exit.
    for _ in range(10_000):
        delta = 0.0
        for node_id, node in nodes.items():
            if node_id in ending_ids:
                continue
            targets = [
                str(c.get("target"))
                for c in cast("list[Any]", node.get("choices") or [])
                if isinstance(c, dict) and str(c.get("target")) in nodes
            ]
            new = sum(prob[t] for t in targets) / len(targets) if targets else 0.0
            delta = max(delta, abs(new - prob[node_id]))
            prob[node_id] = new
        if delta < 1e-9:
            break
    start = str(story.get("start_node"))
    if start not in prob:
        start = next(iter(nodes))
    return prob[start]


def max_indegree(story: dict[str, Any]) -> int:
    """Return the highest node in-degree over all choice edges.

    Parallel edges count separately: two choices on one node targeting the
    same successor contribute 2, because each is a corridor funnelling in.

    Args:
        story: The decoded skeleton dict.

    Returns:
        int: The maximum in-degree, 0 for a story with no choices.
    """
    counts: dict[str, int] = {}
    nodes_raw = story.get("nodes")
    for node in cast("list[Any]", nodes_raw if isinstance(nodes_raw, list) else []):
        if not isinstance(node, dict):
            continue
        for choice in cast("list[Any]", node.get("choices") or []):
            if isinstance(choice, dict):
                target = str(choice.get("target"))
                counts[target] = counts.get(target, 0) + 1
    return max(counts.values(), default=0)


def indegree_cap(band: str, topology: str | None) -> int | None:
    """Return the reconvergence hard cap for a cell, or None when exempt.

    Args:
        band: The skeleton's ``age_band``.
        topology: Its declared topology; hub topologies (``open_map``,
            ``loop_and_grow``) are exempt because re-entry is their design.

    Returns:
        int | None: The cap, or None for an exempt topology or unknown band.
    """
    if topology not in _RECONVERGENCE_CAPPED_TOPOLOGIES:
        return None
    return _MAX_INDEGREE_CAPS.get(band)


def depth_qualified_endings(story: dict[str, Any], min_depth: int) -> tuple[int, int]:
    """Return (qualified, total) ending counts at or past a BFS depth.

    Depth is the shortest hop count from the start node; an ending shallower
    than ``min_depth`` is reachable too early to count as real breadth
    (review Part 4 R2).

    Args:
        story: The decoded skeleton dict (gate-passed).
        min_depth: The qualification threshold in hops.

    Returns:
        tuple[int, int]: Qualified ending count, then total ending count.
    """
    nodes_raw = story.get("nodes")
    nodes: dict[str, dict[str, Any]] = {
        str(n.get("id")): n
        for n in cast("list[Any]", nodes_raw if isinstance(nodes_raw, list) else [])
        if isinstance(n, dict)
    }
    start = str(story.get("start_node"))
    depth: dict[str, int] = {start: 0} if start in nodes else {}
    frontier = [start] if start in nodes else []
    while frontier:
        next_frontier: list[str] = []
        for node_id in frontier:
            for choice in cast("list[Any]", nodes[node_id].get("choices") or []):
                if not isinstance(choice, dict):
                    continue
                target = str(choice.get("target"))
                if target in nodes and target not in depth:
                    depth[target] = depth[node_id] + 1
                    next_frontier.append(target)
        frontier = next_frontier
    total = 0
    qualified = 0
    for node_id, node in nodes.items():
        if isinstance(node.get("ending"), dict):
            total += 1
            if depth.get(node_id, 0) >= min_depth:
                qualified += 1
    return qualified, total


def walk_floor(band: str, style: str | None) -> float | None:
    """Return the strict-mode random-walk outcome floor for a cell.

    Args:
        band: The skeleton's ``age_band``.
        style: Its ``narrative_style`` (``None`` for an MVP seed, which is
            held to the stricter prose floor at the teen bands).

    Returns:
        float | None: The floor in [0, 1], or None for an unknown band.
    """
    if band in _TEEN_BANDS:
        key = style if style in _TEEN_WALK_FLOORS else "prose"
        return _TEEN_WALK_FLOORS[key]
    return _WALK_FLOORS.get(band)


def _fail(message: str) -> bool:
    """Write one FAIL line to stderr.

    Args:
        message: The failure description.

    Returns:
        Always True, so callers can accumulate ``failed |= _fail(...)``.
    """
    sys.stderr.write(f"FAIL {message}\n")
    return True


def _check_brief(metadata: dict[str, Any], args: argparse.Namespace) -> bool:
    """Assert declared metadata matches the brief flags that were given.

    Args:
        metadata: The skeleton's decoded ``metadata`` mapping.
        args: Parsed CLI arguments carrying optional brief expectations.

    Returns:
        True when any given expectation is violated.
    """
    failed = False
    expectations: list[tuple[str, str, object | None]] = [
        ("age_band", "band", args.band),
        ("length", "length", args.length),
        ("narrative_style", "style", args.style),
        ("topology", "topology", args.topology),
        ("tier", "tier", args.tier),
    ]
    for key, label, expected in expectations:
        if expected is not None and metadata.get(key) != expected:
            failed |= _fail(
                f"brief: {label} is {metadata.get(key)!r}, brief says {expected!r}"
            )
    return failed


def main(argv: list[str] | None = None) -> int:
    """Validate one skeleton file.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Exit code: 0 when the shell passes, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Path to the skeleton JSON.")
    parser.add_argument(
        "--headroom",
        action="store_true",
        help=(
            "Print how close the skeleton is to each budget edge (nodes, endings "
            "and decisions against their floors, words, depth, fastest finish)."
        ),
    )
    parser.add_argument("--band", default=None, help="Expected age_band.")
    parser.add_argument("--length", default=None, help="Expected length tier.")
    parser.add_argument("--style", default=None, help="Expected narrative_style.")
    parser.add_argument("--topology", default=None, help="Expected topology.")
    parser.add_argument("--tier", type=int, default=None, help="Expected tier.")
    parser.add_argument(
        "--allow-mvp",
        action="store_true",
        help="Accept a non-production (MVP) shell.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "New-skeleton bar: fail on any escalated advisory (PL-19/23/24/25/26, "
            "L1-7 below cell min), enforce the CG-1..CG-3 choice grammar, and "
            "require the random-walk outcome floor, the reconvergence in-degree "
            "cap, and the depth-qualified endings floor."
        ),
    )
    args = parser.parse_args(argv)
    gate_results: list[GateResult] = []
    try:
        skeleton = load_skeleton(
            Path(args.path),
            enforce_grammar=bool(args.strict),
            report_sink=gate_results.append,
        )
    except ProjectBaseError as exc:
        _print_findings(gate_results)
        sys.stderr.write(f"FAIL gate: {exc}\n")
        return 1
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"FAIL load: {exc}\n")
        return 1

    failed = False
    _print_findings(gate_results)
    if args.strict:
        for result in gate_results:
            for finding in result.report.findings:
                if finding.rule_id in STRICT_BLOCKING_WARNINGS:
                    failed |= _fail(
                        f"strict: {finding.rule_id} advisory is blocking for a "
                        f"newly drafted skeleton: {finding.message}"
                    )
    metadata_raw = skeleton.get("metadata")
    metadata: dict[str, Any] = metadata_raw if isinstance(metadata_raw, dict) else {}
    nodes_raw = skeleton.get("nodes")
    nodes: list[Any] = nodes_raw if isinstance(nodes_raw, list) else []
    node_count = len(nodes)
    ending_count = sum(1 for n in nodes if isinstance(n, dict) and n.get("is_ending"))
    fill_count = sum(
        1
        for n in nodes
        if isinstance(n, dict)
        and isinstance(n.get("body"), str)
        and FILL_MARKER in n["body"]
    )

    production = bool(metadata.get("production_eligible"))
    if not production and not args.allow_mvp:
        failed |= _fail("cell: not production_eligible (pass --allow-mvp for seeds)")
    if production:
        band = str(metadata.get("age_band", ""))
        length = str(metadata.get("length", ""))
        style = str(metadata.get("narrative_style", ""))
        if not is_offered_cell(band, length, style):
            failed |= _fail(f"cell: ({band}, {length}, {style}) is off-matrix")
        else:
            budget = production_cell_budget(band, length, style)
            if budget is not None:
                min_nodes, max_nodes, _ = budget
                if node_count > max_nodes:
                    failed |= _fail(
                        f"envelope: {node_count} nodes exceeds cell max {max_nodes}"
                    )
                elif node_count < min_nodes:
                    sys.stdout.write(
                        f"warn envelope: {node_count} nodes below cell min "
                        f"{min_nodes} (gate treats as warning)\n"
                    )
    failed |= _check_brief(metadata, args)

    sys.stdout.write(
        f"stats: nodes={node_count} endings={ending_count} fill_nodes={fill_count} "
        f"cell=({metadata.get('age_band')}, {metadata.get('length')}, "
        f"{metadata.get('narrative_style')}) topology={metadata.get('topology')} "
        f"tier={metadata.get('tier')}\n"
    )
    if args.headroom or args.strict:
        band = str(metadata.get("age_band", ""))
        style_raw = metadata.get("narrative_style")
        style = str(style_raw) if isinstance(style_raw, str) else None
        p_satisfying = satisfying_walk_probability(skeleton)
        floor = walk_floor(band, style)
        if floor is not None:
            floor_note = f"floor {floor:.0%} for {band} {style or 'prose'}"
        else:
            floor_note = "no floor for this band"
        sys.stdout.write(
            f"walk: P(satisfying ending, uniform reader) {p_satisfying:.1%} "
            f"({floor_note})\n"
        )
        if args.strict and floor is not None and p_satisfying < floor:
            failed |= _fail(
                f"strict walk floor: a uniform random reader reaches a "
                f"satisfying ending with probability {p_satisfying:.1%}, below "
                f"the {floor:.0%} floor for ({band}, {style or 'prose'}); add "
                f"graded setbacks or reconverge failure corridors"
            )
        topology_raw = metadata.get("topology")
        topology = str(topology_raw) if isinstance(topology_raw, str) else None
        cap = indegree_cap(band, topology)
        observed = max_indegree(skeleton)
        if cap is not None:
            sys.stdout.write(
                f"reconvergence: max in-degree {observed} "
                f"(hard cap {cap} for {band} {topology})\n"
            )
            if args.strict and observed > cap:
                failed |= _fail(
                    f"strict reconvergence: max in-degree {observed} exceeds "
                    f"the hard cap {cap} for ({band}, {topology}); a funnel "
                    f"this wide collapses corridors into one node (ruled "
                    f"2026-08-09, review Part 4 R4 upgraded to blocking)"
                )
        else:
            sys.stdout.write(
                f"reconvergence: max in-degree {observed} "
                f"(exempt topology {topology}: hub re-entry is by design)\n"
            )
        length_raw = metadata.get("length")
        if args.strict and isinstance(length_raw, str):
            arc_floor = min_complete_floor(band, length_raw, style or "prose")
            if arc_floor is not None:
                min_depth = math.ceil(arc_floor * _ENDING_DEPTH_QUALIFICATION_FRACTION)
                qualified, total_endings = depth_qualified_endings(skeleton, min_depth)
                ending_floor, _ = breadth_scaled_floors(node_count, style or "prose")
                sys.stdout.write(
                    f"endings depth-qualified: {qualified} of {total_endings} at "
                    f"depth >= {min_depth} against floor {ending_floor}\n"
                )
                if qualified < ending_floor:
                    failed |= _fail(
                        f"strict endings floor: only {qualified} of "
                        f"{total_endings} endings sit at depth >= {min_depth} "
                        f"(33% of the {arc_floor}-node arc floor), below the "
                        f"breadth-scaled floor of {ending_floor}; shallow "
                        f"failure leaves do not count as breadth (ruled "
                        f"2026-08-09, review Part 4 R2)"
                    )
    if args.headroom:
        sys.stdout.write(_headroom(skeleton, metadata))
    if not failed:
        sys.stdout.write("ok: skeleton passes gate and brief checks\n")
    return 1 if failed else 0


def _print_findings(gate_results: list[GateResult]) -> None:
    """Print every gate finding at every severity, run_story_gate-style.

    The loader used to drop the report on a pass, so a skeleton with PL-19/
    PL-23..PL-26/L1-7 advisories printed a clean ``ok`` (2026-08-09 review,
    section 2.2). Findings go to stdout so authoring logs keep them next to
    the stats line.

    Args:
        gate_results: The GateResults captured by the load_skeleton sink.
    """
    for result in gate_results:
        for finding in result.report.findings:
            where = f" node={finding.node_id}" if finding.node_id else ""
            sys.stdout.write(
                f"{finding.severity.upper():7} {finding.rule_id:6}{where} "
                f"{finding.message}\n"
            )


if __name__ == "__main__":
    raise SystemExit(main())
