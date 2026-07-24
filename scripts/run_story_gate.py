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

_REPO_ROOT = Path(__file__).resolve().parent.parent


# #ASSUME: security: the only documented invocation shape (docs/planning/
# story-inventory-initial-run.md, ws0-phase2-harness-design.md,
# ws2-parameterized-catalog-design.md) is a skeleton or filled-story JSON
# living under the repo tree (skeletons/, an authoring working dir), and
# this script has no test suite that exercises it against an out-of-repo
# tmp_path fixture; containing it to the repo root closes the CWE-23 gap
# (Snyk python/PT) without rejecting any documented or tested invocation.
# #VERIFY: if a future authoring workflow needs a story file outside the
# repo tree, this containment must be relaxed deliberately (and the
# rationale above updated), not silently bypassed.
def _resolve_within_repo(path_arg: str) -> Path:
    """Resolve a CLI-supplied story path and require it stay in the repo root.

    Args:
        path_arg: The raw path string from argparse.

    Returns:
        Path: The resolved, canonical path.

    Raises:
        SystemExit: If the resolved path falls outside the repo root.
    """
    resolved = Path(path_arg).resolve()
    try:
        resolved.relative_to(_REPO_ROOT)
    except ValueError:
        msg = (
            f"error: {path_arg!r} resolves to {resolved}, which is outside "
            f"the repo root {_REPO_ROOT}\n"
        )
        sys.stderr.write(msg)
        raise SystemExit(1) from None
    return resolved


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
    resolved_path = _resolve_within_repo(path)
    try:
        data = json.loads(resolved_path.read_text(encoding="utf-8"))
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
