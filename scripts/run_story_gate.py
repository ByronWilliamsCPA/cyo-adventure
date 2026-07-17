"""Run the offline validation gate on a story JSON and print the report.

Usage:
    uv run python scripts/run_story_gate.py <story.json> [--scale standard|compact]

Runs ``cyo_adventure.validator.gate.run_gate`` (no database needed) and prints
every finding. Exits 1 when the gate blocks, 0 otherwise; warnings never block.
Used by the initial story-inventory authoring run (see
``docs/planning/story-inventory-initial-run.md`` section 5.1).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cyo_adventure.validator.gate import run_gate


def main(argv: list[str] | None = None) -> int:
    """Run the gate on one story file and print the merged report.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Exit code: 0 when not blocked, 1 when blocked or unreadable.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Path to the story JSON (skeleton or filled).")
    parser.add_argument(
        "--scale",
        choices=("standard", "compact"),
        default="standard",
        help="Layer-1 budget scale (default: standard).",
    )
    args = parser.parse_args(argv)
    path: str = args.path
    scale: str = args.scale
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot load {path}: {exc}\n")
        return 1
    if not isinstance(data, dict):
        sys.stderr.write(f"error: expected a JSON object in {path}\n")
        return 1
    result = run_gate(data, scale="compact" if scale == "compact" else "standard")
    for finding in result.report.findings:
        where = f" node={finding.node_id}" if finding.node_id else ""
        sys.stdout.write(
            f"{finding.severity.upper():7} {finding.rule_id:6}{where} "
            f"{finding.message}\n"
        )
    sys.stdout.write(
        f"findings={len(result.report.findings)} "
        f"blocked={result.blocked} safety_flagged={result.safety_flagged}\n"
    )
    return 1 if result.blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
