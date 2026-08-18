"""Every offered cell must admit at least one story that satisfies all of it.

The rule set is about fifty rules calibrated independently against different
sources. Nothing ever asked whether they can be satisfied AT THE SAME TIME, and
five times they could not:

- `UW-C272`: PL-29 offered topologies PL-18 forbids, in 15 of 18 cells.
- `UW-C283`: PL-17's floor exceeded ADR-011 section 5's own endings ceiling in
  three cells and equalled it in a fourth, so a story authored to the top of its
  own node envelope could not pass.
- `UW-C284`: the gauntlet ADR-011 section 7 specifies classified as something
  else and drew a blocking error at 13-16 gamebook.
- `UW-C288`: filed as a three-way conflict, then shown to be jointly satisfiable
  after all, which a prover would have answered immediately.

Each was found by hand, late, by an author or an auditor. This asserts the
property directly: for every offered cell, synthesize a story to that cell's own
stated budgets and require the gate not to block it.

It is a FEASIBILITY check, not a quality one. The synthesized stories are
deliberately dull. A cell that cannot admit even a mechanical story cannot admit
a good one, and that is the failure worth catching before an author meets it.
"""

from __future__ import annotations

from typing import Any

import pytest

from cyo_adventure.validator.band_profile import (
    _PRODUCTION_CELLS,  # pyright: ignore[reportPrivateUsage]
    breadth_scaled_floors,
    cell_ending_bounds,
    min_complete_floor,
    profile_for,
    words_per_node_profile,
)
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.topology import BAND_TOPOLOGIES, admissible_topologies


def _synthesize(band: str, length: str, style: str) -> dict[str, Any]:
    """Build a minimal story sized to the cell's own budgets.

    A spine long enough to clear the arc floor, then a fan of decision nodes each
    reaching endings, padded to the cell's node minimum. Word targets come from
    the cell's own mean, so PL-19 is satisfied by construction rather than by
    luck.
    """
    min_nodes, _max_nodes, _depth = _PRODUCTION_CELLS[(band, length, style)]
    profile = words_per_node_profile(band, style)
    assert profile is not None
    mean = profile[0]
    arc = min_complete_floor(band, length, style) or 6
    band_profile = profile_for(band)
    assert band_profile is not None

    target_endings, _decisions = breadth_scaled_floors(
        min_nodes, style, (cell_ending_bounds(band, length, style) or (0, None))[1]
    )
    target_endings = max(target_endings, band_profile.min_endings)

    body = f"<<FILL role=beat words={mean} beats='b'>>"
    nodes: list[dict[str, Any]] = []

    # An establishing stop first: PL-25 floors the first decision at the second
    # node, and one single-choice opening satisfies that at every band.
    nodes.append(
        {
            "id": "n_open",
            "body": body,
            "choices": [{"id": "c_open", "label": "Go on", "target": "d0"}],
        }
    )

    # A spine of decisions deep enough that the shortest satisfying finish clears
    # the arc floor. Each decision sends one branch onward and one to an ending.
    depth = max(arc, 2)
    for i in range(depth):
        onward = f"d{i + 1}" if i + 1 < depth else "e_win"
        nodes.append(
            {
                "id": f"d{i}",
                "body": body,
                "choices": [
                    {"id": f"c{i}a", "label": "Press on", "target": onward},
                    {"id": f"c{i}b", "label": "Turn aside", "target": f"e{i}"},
                ],
            }
        )
        nodes.append(
            {
                "id": f"e{i}",
                "body": body,
                "is_ending": True,
                # Never a SATISFYING kind (success/completion): the spine's
                # asides are reachable two nodes in, so a satisfying one would
                # give the story a 3-node fastest finish and trip PL-20's arc
                # floor. Only `e_win`, at the end of the spine, may satisfy.
                "ending": {
                    "id": f"end{i}",
                    "valence": "neutral" if i % 2 else "negative",
                    "kind": "discovery" if i % 2 else "setback",
                    "title": f"Aside {i}",
                },
            }
        )
    nodes.append(
        {
            "id": "e_win",
            "body": body,
            "is_ending": True,
            "ending": {
                "id": "win",
                "valence": "positive",
                "kind": "success",
                "title": "Won",
            },
        }
    )

    # Pad with further decision-and-ending pairs until the cell's node minimum
    # and endings floor are both met.
    pad = 0
    while (
        len(nodes) < min_nodes
        or sum(1 for n in nodes if n.get("is_ending")) < target_endings
    ):
        nodes.append(
            {
                "id": f"p{pad}",
                "body": body,
                # Both branches reach NON-satisfying endings. Routing one to the
                # win would give the story a 3-node shortest satisfying path and
                # trip PL-20's arc floor, which is a defect in this synthesizer
                # rather than in the cell. Keeping the win reachable only through
                # the spine is what makes the arc floor a real test here.
                "choices": [
                    {"id": f"pc{pad}a", "label": "Left", "target": f"pe{pad}"},
                    {"id": f"pc{pad}b", "label": "Right", "target": f"pf{pad}"},
                ],
            }
        )
        nodes.append(
            {
                "id": f"pe{pad}",
                "body": body,
                "is_ending": True,
                "ending": {
                    "id": f"pend{pad}",
                    "valence": "negative" if pad % 3 else "neutral",
                    "kind": "setback" if pad % 3 else "discovery",
                    "title": f"Way {pad}",
                },
            }
        )
        nodes.append(
            {
                "id": f"pf{pad}",
                "body": body,
                "is_ending": True,
                "ending": {
                    "id": f"pfend{pad}",
                    "valence": "negative",
                    "kind": "setback",
                    "title": f"Turn {pad}",
                },
            }
        )
        # Reach the padding from the spine so nothing is orphaned.
        nodes[1]["choices"].append(
            {"id": f"link{pad}", "label": f"Path {pad}", "target": f"p{pad}"}
        )
        pad += 1

    topology = next(
        (
            t.value
            for t in BAND_TOPOLOGIES[band]
            if t in admissible_topologies(_graph(nodes))
        ),
        next(iter(BAND_TOPOLOGIES[band])).value,
    )
    return {
        "id": f"sk_feas_{band}_{length}_{style}".replace("-", "_").replace("+", "p"),
        "version": 1,
        "title": "Feasibility",
        "start_node": "n_open",
        "nodes": nodes,
        "metadata": {
            "age_band": band,
            "length": length,
            "narrative_style": style,
            "reading_level": {"target": 5.0},
            "tier": 1,
            "estimated_minutes": 30,
            "ending_count": sum(1 for n in nodes if n.get("is_ending")),
            "topology": topology,
            "production_eligible": True,
        },
    }


def _graph(nodes: list[dict[str, Any]]):
    """Build the choice digraph for topology classification."""
    import networkx as nx

    graph: nx.DiGraph[str] = nx.DiGraph()
    graph.add_nodes_from(n["id"] for n in nodes)
    for n in nodes:
        for c in n.get("choices", []):
            graph.add_edge(n["id"], c["target"])
    return graph


@pytest.mark.parametrize("cell", sorted(_PRODUCTION_CELLS))
def test_every_offered_cell_admits_a_gate_passing_story(
    cell: tuple[str, str, str],
) -> None:
    """A story built to a cell's own budgets must not be blocked by that cell's rules.

    When this fails, the rule set is over-constrained for that cell and no author
    can succeed in it, however good the writing. The failure message carries the
    blocking rules so the contradiction is named rather than hunted.
    """
    band, length, style = cell
    result = run_gate(_synthesize(band, length, style))

    blocking = [
        f"{f.rule_id}: {f.message}"
        for f in result.report.findings
        if f.severity.name == "ERROR"
    ]
    assert not result.blocked, (
        f"cell {band}/{length}/{style} admits no gate-passing story; blocked by:\n  "
        + "\n  ".join(blocking[:6])
    )
