"""Validate a skeleton shell against the gate and its declared/briefed cell.

Usage:
    uv run python scripts/check_skeleton.py <skeleton.json> [--band B] [--length L]
        [--style S] [--topology T] [--tier N] [--allow-mvp]

Runs ``load_skeleton`` (the full gate's blocking layers on the shell: structure,
references, reachability, budgets, policy incl. PL-19/20/21) and then asserts
the declared metadata matches the design brief when brief flags are given.
Used by Wave 5 of the story-inventory run (see
``docs/planning/story-inventory-initial-run.md`` section 6.1).

Exits 1 on a gate block or any brief mismatch.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from cyo_adventure.core.exceptions import ProjectBaseError
from cyo_adventure.generation.skeleton import FILL_MARKER, load_skeleton
from cyo_adventure.validator.band_profile import (
    is_offered_cell,
    production_cell_budget,
)


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
    args = parser.parse_args(argv)
    try:
        skeleton = load_skeleton(Path(args.path))
    except ProjectBaseError as exc:
        sys.stderr.write(f"FAIL gate: {exc}\n")
        return 1
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"FAIL load: {exc}\n")
        return 1

    failed = False
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
    if not failed:
        sys.stdout.write("ok: skeleton passes gate and brief checks\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
