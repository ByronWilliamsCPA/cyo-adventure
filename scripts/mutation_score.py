# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Compute the mutation score from mutmut 3.x result metadata.

mutmut 3 persists one ``<source>.py.meta`` JSON file per mutated source
file under ``mutants/``, mapping each mutant name to the exit code of its
test run (``exit_code_by_key``). This script aggregates those exit codes
into the same status buckets mutmut itself uses and prints a Markdown
summary, so the weekly workflow (.github/workflows/mutation-testing.yml)
and ``nox -s mutate`` share one scoring implementation instead of
scraping mutmut's emoji progress line.

Score definition: ``(killed + timeout) / checked * 100``, where checked
excludes mutants that no test covers (``no tests``), mutants explicitly
skipped, and mutants never run (``not checked``). Timeouts count as
detected: a mutant that turns the suite into an infinite loop was caught
by testing, even though no assertion fired.

Usage:
    uv run python scripts/mutation_score.py [--fail-under PERCENT]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Mirrors mutmut.__main__.status_by_exit_code (mutmut 3.6). Unknown exit
# codes fall back to "suspicious", matching mutmut's defaultdict.
_STATUS_BY_EXIT_CODE: dict[int, str] = {
    1: "killed",
    3: "killed",
    0: "survived",
    5: "no tests",
    2: "interrupted",
    33: "no tests",
    34: "skipped",
    35: "suspicious",
    36: "timeout",
    37: "killed by type check",
    -24: "timeout",
    24: "timeout",
    152: "timeout",
    255: "timeout",
    -11: "segfault",
    -9: "segfault",
}

_DETECTED = frozenset({"killed", "timeout", "killed by type check"})
_UNDETECTED = frozenset({"survived", "suspicious", "segfault"})


def collect_counts(mutants_dir: Path) -> dict[str, int]:
    """Aggregate mutant statuses from every ``.meta`` file under ``mutants_dir``.

    Args:
        mutants_dir: mutmut's working tree, normally ``Path("mutants")``.

    Returns:
        Mapping of status name to mutant count (missing statuses omitted).

    Raises:
        FileNotFoundError: If ``mutants_dir`` holds no ``.meta`` files,
            meaning ``mutmut run`` has not produced results to score.
    """
    counts: dict[str, int] = {}
    meta_files = sorted(mutants_dir.rglob("*.meta"))
    if not meta_files:
        msg = f"no mutmut result metadata (*.meta) found under {mutants_dir}/"
        raise FileNotFoundError(msg)
    for meta_path in meta_files:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        exit_codes = data.get("exit_code_by_key", {})
        for raw_code in exit_codes.values():
            if raw_code is None:
                status = "not checked"
            else:
                status = _STATUS_BY_EXIT_CODE.get(int(raw_code), "suspicious")
            counts[status] = counts.get(status, 0) + 1
    return counts


def score_from_counts(counts: dict[str, int]) -> tuple[float, int, int]:
    """Compute the mutation score from aggregated status counts.

    Args:
        counts: Mapping of status name to mutant count.

    Returns:
        ``(score_percent, detected, checked)`` where ``checked`` is the
        number of mutants whose covering tests actually ran. A run with
        zero checked mutants scores 0.0 rather than dividing by zero.
    """
    detected = sum(counts.get(status, 0) for status in _DETECTED)
    undetected = sum(counts.get(status, 0) for status in _UNDETECTED)
    checked = detected + undetected
    if checked == 0:
        return 0.0, 0, 0
    return detected / checked * 100.0, detected, checked


def render_summary(counts: dict[str, int]) -> str:
    """Render the score and per-status counts as a Markdown fragment.

    Args:
        counts: Mapping of status name to mutant count.

    Returns:
        Markdown with the headline score followed by a status table.
    """
    score, detected, checked = score_from_counts(counts)
    lines = [
        "## Mutation Testing Results",
        "",
        f"**Mutation score: {score:.1f}%** ({detected}/{checked} checked mutants detected)",
        "",
        "| Status | Count |",
        "|--------|-------|",
    ]
    lines.extend(f"| {status} | {counts[status]} |" for status in sorted(counts))
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Print the mutation-score summary; optionally gate on a threshold.

    Args:
        argv: CLI arguments (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code: 0 on success, 1 when ``--fail-under`` is given
        and the score falls below it, 2 when no results exist to score.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        metavar="PERCENT",
        help="exit 1 if the mutation score is below this percentage",
    )
    parser.add_argument(
        "--mutants-dir",
        type=Path,
        default=Path("mutants"),
        help="mutmut working tree to score (default: mutants/)",
    )
    args = parser.parse_args(argv)

    try:
        counts = collect_counts(args.mutants_dir)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(render_summary(counts))
    score, _, _ = score_from_counts(counts)
    if args.fail_under is not None and score < args.fail_under:
        print(
            f"error: mutation score {score:.1f}% is below the "
            f"--fail-under threshold of {args.fail_under:.1f}%",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
