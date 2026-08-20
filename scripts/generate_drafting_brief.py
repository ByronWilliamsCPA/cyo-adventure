"""Generate a per-cell skeleton drafting brief from the enforced rule sources.

Usage:
    uv run python scripts/generate_drafting_brief.py <band> <length> <style>
        [--json]

Emits the complete constraint set an authoring agent needs to draft a
strict-compliant skeleton for one production cell, read live from
``validator/band_profile.py``, ``validator/choice_grammar.py``,
``validator/policy.py`` and ``scripts/check_skeleton.py`` rather than
hand-copied. Exists because both strict-pilot briefs drifted from the code
when written by hand (AL-149: one mis-stated PL-26's gamebook ceiling as 6.0
against the enforced 4.0), and a brief that drifts silently miscalibrates
every draft built to it.

The primary consumer is an LLM authoring agent (the catalog's goal is
high-quality LLM-generated stories); the brief is equally valid for the rare
hand-drafted small-cell shell.
"""

from __future__ import annotations

import argparse
import json
import math
import sys

from cyo_adventure.storybook.character_vocabulary import (
    CANONICAL_CHARACTER_VARIABLES,
)
from cyo_adventure.validator.band_profile import (
    breadth_scaled_floors,
    cell_ending_bounds,
    is_offered_cell,
    min_complete_floor,
    nodes_per_decision_ceiling,
    production_cell_budget,
    reading_pace_wpm,
    words_per_node_profile,
)
from cyo_adventure.validator.choice_grammar import (
    _DISCRETE_RUN_CAP,
    _OPTIONS_BOUNDS,
    _WORDS_PER_STOP_CEILING,
)
from cyo_adventure.validator.policy import (
    _ENDING_KIND_SHARE_CEILING,
    _POSITIVE_ENDING_COUNT_FLOOR_GAMEBOOK,
    _POSITIVE_ENDING_SHARE_FLOOR_GAMEBOOK,
    _POSITIVE_VALENCE_SHARE_FLOOR_PROSE,
)
from cyo_adventure.validator.topology import BAND_TOPOLOGIES
from cyo_adventure.validator.walk import DEFAULT_CONFIG_CAP

try:
    from scripts.check_skeleton import (
        _ENDING_DEPTH_QUALIFICATION_FRACTION,
        _MAX_INDEGREE_CAPS,
        _RECONVERGENCE_CAPPED_TOPOLOGIES,
        walk_floor,
    )
except ModuleNotFoundError:  # direct CLI run: scripts/ itself is on sys.path
    from check_skeleton import (
        _ENDING_DEPTH_QUALIFICATION_FRACTION,
        _MAX_INDEGREE_CAPS,
        _RECONVERGENCE_CAPPED_TOPOLOGIES,
        walk_floor,
    )


def build_brief(band: str, length: str, style: str) -> dict[str, object]:
    """Assemble the drafting brief for one cell from the enforced sources.

    Args:
        band: The age band, e.g. ``"10-13"``.
        length: The length tier (``short``/``medium``/``long``).
        style: The narrative style (``prose``/``gamebook``).

    Returns:
        dict[str, object]: The brief, JSON-serializable.

    Raises:
        ValueError: If the cell is not on the offered matrix.
    """
    if not is_offered_cell(band, length, style):
        msg = f"({band}, {length}, {style}) is not an offered production cell"
        raise ValueError(msg)
    budget = production_cell_budget(band, length, style)
    if budget is None:  # pragma: no cover - is_offered_cell guards this
        msg = f"no budget for offered cell ({band}, {length}, {style})"
        raise ValueError(msg)
    min_nodes, max_nodes, depth_cap = budget
    words = words_per_node_profile(band, style)
    _cell_bounds = cell_ending_bounds(band, length, style)
    arc_floor = min_complete_floor(band, length, style)
    brief: dict[str, object] = {
        "cell": {"age_band": band, "length": length, "narrative_style": style},
        "nodes": {"min": min_nodes, "max": max_nodes, "depth_cap": depth_cap},
        # The ADR section 5 per-cell MAXIMUM, which the brief never printed. It
        # is advisory in PL-17 so it does not block, but under the authoring
        # bar of zero findings at any severity it binds, and `the-last-blue-cup`
        # is the proof that a strict-bar book can cross it (`UW-C300`).
        "endings_ceiling_for_cell": (None if _cell_bounds is None else _cell_bounds[1]),
        "endings_range_for_cell": _cell_bounds,
        # Capped by the cell ceiling, as PL-17 caps it. Printing the uncapped
        # figure made the brief demand more endings than the same brief's own
        # ceiling permits at the top of a node envelope.
        "endings_floor_by_node_count": {
            str(n): breadth_scaled_floors(
                n, style, None if _cell_bounds is None else _cell_bounds[1]
            )[0]
            for n in (min_nodes, (min_nodes + max_nodes) // 2, max_nodes)
        },
        "decisions_floor_by_node_count": {
            str(n): breadth_scaled_floors(n, style)[1]
            for n in (min_nodes, (min_nodes + max_nodes) // 2, max_nodes)
        },
        "words_per_node": None
        if words is None
        else {
            "mean_target": words[0],
            "advisory_low": words[1],
            "advisory_high": words[2],
            "hard_max": words[3],
        },
        "arc_floor_min_complete": arc_floor,
        "ending_depth_qualification_min_depth": None
        if arc_floor is None
        else math.ceil(arc_floor * _ENDING_DEPTH_QUALIFICATION_FRACTION),
        "choice_grammar": {
            "options_per_decision": _OPTIONS_BOUNDS.get(band),
            "single_choice_run_cap": _DISCRETE_RUN_CAP.get(band, 6),
            "words_per_stop_ceiling": _WORDS_PER_STOP_CEILING.get(band),
            "note": (
                "a single-choice chain composes into one stop WITH the node it "
                "flows into; the stop's summed declared words must stay under "
                "the ceiling (CG-3)"
            ),
        },
        "pacing": {
            # Read through the accessor, not the flat by-style table. PL-26
            # grades `nodes_per_decision_ceiling(style, band)`, and since the
            # Wave 3 per-band derivation the flat entry is a fallback for an
            # unconfigured band only. Printing it here made the brief disagree
            # with the rule it describes at every band, and the error flipped
            # direction across the range: 6.0 printed against 15.0 and 8.57
            # enforced at the young bands, against 4.29 and 3.43 at the teen
            # ones, so a teen-band author designed to a budget 40 to 75 percent
            # looser than the gate allows. Three of the seven authoring agents
            # on 2026-08-18 reproduced it independently (`UW-C300`).
            "nodes_per_decision_ceiling_fastest_finish": (
                nodes_per_decision_ceiling(style, band)
            ),
            "reading_pace_wpm": reading_pace_wpm(band),
            "estimated_minutes_rule": (
                "declare the derived fastest-finish clock; check_skeleton "
                "--headroom prints declared vs derived (PL-23 tolerance 25%)"
            ),
        },
        "state_budget": {
            "requires_tier_2": (
                "declaring ANY variable requires metadata.tier = 2. A tier-1 "
                "story that declares one is a BLOCKING L1-6 (`tier-1 story must "
                "not declare variables`), so this is the first thing to set on a "
                "stateful book, not something to discover from the gate. Omitted "
                "from this brief until 2026-08-19, when it cost a gamebook author "
                "a whole iteration in the one cell where every book is stateful "
                "(`UW-C306`)"
            ),
            "configuration_cap": DEFAULT_CONFIG_CAP,
            "bound": (
                "nodes x (product of declared variable ranges) x 2 ** "
                "(nodes carrying a once:true on_enter effect)"
            ),
            "guarantee": (
                f"a bound at or under {DEFAULT_CONFIG_CAP:,} is certainly inside "
                f"L2-12; above it a story may still fit, but only measurement "
                f"answers"
            ),
            "measured_range": (
                "across the 15 stateful stories measured 2026-08-18, the "
                "reachable set ran from 4.9% to 52.6% of its own bound, so the "
                "bound cannot be turned into a predicted count"
            ),
            "watch_once_effects": (
                "every once:true on_enter effect DOUBLES the bound, because the "
                "walk must tell a reader who has fired it from one who has not; "
                "six of them cost 64x, which is why a 3-variable 248-node prose "
                "story reaches 51,241 configurations while a 4-variable 551-node "
                "gamebook reaches 3,669"
            ),
            "declare_ranges_tightly": (
                "declare an int variable's range as what the story tests, not "
                "what it could hold; L2-15 warns past 4x, and a 0..99 counter "
                "tested at 3 cost one draft a 25x inflation per variable"
            ),
            "measure_it": "check_skeleton.py --headroom prints the measured count",
        },
        "outcome_economy": {
            "ending_kind_share_ceiling": _ENDING_KIND_SHARE_CEILING,
            "winnability_floor": (
                {
                    "style": "gamebook",
                    "rule": (
                        f"positive endings >= max("
                        f"{_POSITIVE_ENDING_COUNT_FLOOR_GAMEBOOK}, "
                        f"ceil({_POSITIVE_ENDING_SHARE_FLOOR_GAMEBOOK:.0%} of "
                        f"endings))"
                    ),
                }
                if style == "gamebook"
                else {
                    "style": "prose",
                    "rule": (
                        f"positive-valence share >= "
                        f"{_POSITIVE_VALENCE_SHARE_FLOOR_PROSE:.0%}"
                    ),
                }
            ),
            "random_walk_satisfying_floor": walk_floor(band, style),
        },
        "topology": {
            "allowed_for_this_band": sorted(
                topology.value for topology in BAND_TOPOLOGIES.get(band, frozenset())
            ),
            "rule": (
                "PL-29 BLOCKS a topology this band may not declare. The list above "
                "is the whole of what this cell may use; anything else is a "
                "blocking finding, not a stylistic preference"
            ),
            "note": (
                "published per band because `reconvergence.capped_topologies` "
                "below is a band-INDEPENDENT list and reads as a menu. It is not "
                "one: it names the topologies whose in-degree is capped, several "
                "of which this band cannot declare at all. Two independent "
                "authoring agents picked a forbidden topology off that list on "
                "2026-08-19 and had to read `validator/topology.py` to find out "
                "(`UW-C306`)"
            ),
        },
        "depth": {
            "cap": depth_cap,
            "metric": (
                "L1-7 grades `nx.dag_longest_path_length` over the reachable "
                "subgraph: the graph's LONGEST simple path, not the depth a "
                "reader experiences and not the BFS shortest path the "
                "ending-depth floor uses"
            ),
            "watch": (
                "a single-choice detour that rejoins the spine adds a hop to the "
                "longest path while adding nothing any one reader walks, so six "
                "of them can push a 35-hop story to 41 and fail the cap. If the "
                "cap fails and the story looks shallow, look for rejoining "
                "detours before shortening anything"
            ),
        },
        "reconvergence": {
            "capped_topologies": sorted(_RECONVERGENCE_CAPPED_TOPOLOGIES),
            "max_indegree_cap": _MAX_INDEGREE_CAPS.get(band),
            "exempt": "open_map and loop_and_grow (hub re-entry is by design)",
            "see_also": "topology.allowed_for_this_band for what this cell may declare",
        },
        "gate_commands": {
            "on_your_draft": [
                "uv run python scripts/check_skeleton.py <path> --strict --headroom"
            ],
            "on_the_whole_catalog": {
                "note": (
                    "these take no path argument and audit the committed catalog; "
                    "they say nothing about the file you are drafting"
                ),
                "commands": [
                    "uv run python scripts/check_incell_clones.py",
                    "uv run python scripts/check_outcome_spread.py",
                ],
            },
            "if_this_book_is_part_of_a_series": {
                "note": (
                    "check_skeleton.py does NOT run the SR family. A book with a "
                    "foreign series_id, a wrong book_index, no series_entry_node, or "
                    "carries_state disagreeing with its chain passes --strict with "
                    "exit 0. Run the chain checker over every book in the series"
                ),
                "commands": [
                    "uv run python scripts/build_series_book.py --series <book1> <book2> ..."
                ],
            },
        },
        "reserved_variable_names": {
            "names": sorted(CANONICAL_CHARACTER_VARIABLES),
            "note": (
                "the canonical persistent-character vocabulary (ADR-028). Declaring "
                "one of these as an ordinary story variable is a BLOCKING CH-6, so "
                "pick another word for the trait: 'nerve' in particular reads as an "
                "ordinary noun and has already cost an author a rebuild cycle"
            ),
        },
    }
    return brief


def _render_markdown(brief: dict[str, object]) -> str:
    """Render the brief as a compact markdown block."""
    lines = [f"# Drafting brief: {json.dumps(brief['cell'])}", ""]
    for key, value in brief.items():
        if key == "cell":
            continue
        lines.append(f"- **{key}**: `{json.dumps(value)}`")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Exit code: 0 on success, 2 for an off-matrix cell.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("band")
    parser.add_argument("length")
    parser.add_argument("style")
    parser.add_argument(
        "--json", action="store_true", help="Emit JSON instead of markdown."
    )
    args = parser.parse_args(argv)
    try:
        brief = build_brief(args.band, args.length, args.style)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    if args.json:
        sys.stdout.write(json.dumps(brief, indent=2) + "\n")
    else:
        sys.stdout.write(_render_markdown(brief))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
