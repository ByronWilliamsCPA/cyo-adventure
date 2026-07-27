#!/usr/bin/env python
"""In-cell clone audit CLI (A8).

    uv run python scripts/check_incell_clones.py            # report
    uv run python scripts/check_incell_clones.py --check    # gate (exit 1)

A thin argparse shell over :mod:`cyo_adventure.diversity.incell`, which holds the
logic and documents why the audit uses ``structural_distance`` against the loaded
``TAU_CELL`` rather than ``structure_fingerprint`` or ``TAU_STRUCT``.

Only ``--check`` gates. The bare run reports the distance distribution and the
closest pairs, so the catalog can be inspected without a wall of red.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from typing import cast

from cyo_adventure.core.exceptions import ConfigurationError
from cyo_adventure.diversity.incell import (
    ALLOWLIST,
    PairDistance,
    audit,
    iter_incell_pairs,
    load_tau_cell,
)

_CLOSEST = 10


def _print_report(pairs: list[PairDistance], tau_cell: float) -> None:
    """Print the distance distribution and the closest pairs."""
    distances = [pair.distance for pair in pairs]
    cells = len({pair.cell for pair in pairs})
    summary = " ".join(
        [
            f"in-cell pairs: {len(pairs)}",
            f"cells: {cells}",
            f"tau_cell={tau_cell}",
            f"min={min(distances):.5f}",
            f"median={statistics.median(distances):.4f}",
            f"max={max(distances):.4f}",
        ]
    )
    sys.stdout.write(f"{summary}\n")
    sys.stdout.write(f"\nclosest {_CLOSEST} pairs:\n")
    for pair in sorted(pairs)[:_CLOSEST]:
        marker = "FAIL" if pair.distance < tau_cell else "ok  "
        row = f"  {marker} {pair.distance:.5f}  {pair.cell:26s}"
        sys.stdout.write(f"{row} {pair.slug_a} vs {pair.slug_b}\n")


def main(argv: list[str] | None = None) -> int:
    """Run the audit.

    Args:
        argv: Argument vector; defaults to ``sys.argv[1:]``.

    Returns:
        int: ``0`` clean, ``1`` on a finding under ``--check``, ``2`` on a
            configuration or catalog problem.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="gate: exit 1 on an unallowlisted breach or a stale allowlist entry",
    )
    args = parser.parse_args(argv)
    gate = bool(cast("object", args.check))

    try:
        tau_cell = load_tau_cell()
    except ConfigurationError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    pairs = list(iter_incell_pairs())
    if not pairs:
        sys.stderr.write("error: no in-cell pairs found; is the catalog present?\n")
        return 2

    if not gate:
        _print_report(pairs, tau_cell)
        return 0

    findings = audit(pairs, tau_cell)
    for finding in findings:
        sys.stdout.write(f"  {finding}\n")
    sys.stdout.write(f"findings={len(findings)}\n")
    if ALLOWLIST:
        sys.stdout.write(f"allowlisted (must shrink to zero): {len(ALLOWLIST)}\n")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
