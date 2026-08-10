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

from cyo_adventure.validator.band_profile import (
    _NODES_PER_DECISION_CEILING,
    breadth_scaled_floors,
    is_offered_cell,
    min_complete_floor,
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
    arc_floor = min_complete_floor(band, length, style)
    density_key = "gamebook" if style == "gamebook" else "prose"
    brief: dict[str, object] = {
        "cell": {"age_band": band, "length": length, "narrative_style": style},
        "nodes": {"min": min_nodes, "max": max_nodes, "depth_cap": depth_cap},
        "endings_floor_by_node_count": {
            str(n): breadth_scaled_floors(n, style)[0]
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
            "nodes_per_decision_ceiling_fastest_finish": (
                _NODES_PER_DECISION_CEILING[density_key]
            ),
            "reading_pace_wpm": reading_pace_wpm(band),
            "estimated_minutes_rule": (
                "declare the derived fastest-finish clock; check_skeleton "
                "--headroom prints declared vs derived (PL-23 tolerance 25%)"
            ),
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
        "reconvergence": {
            "capped_topologies": sorted(_RECONVERGENCE_CAPPED_TOPOLOGIES),
            "max_indegree_cap": _MAX_INDEGREE_CAPS.get(band),
            "exempt": "open_map and loop_and_grow (hub re-entry is by design)",
        },
        "gate_commands": [
            "uv run python scripts/check_skeleton.py <path> --strict --headroom",
            "uv run python scripts/check_incell_clones.py",
            "uv run python scripts/check_outcome_spread.py",
        ],
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
