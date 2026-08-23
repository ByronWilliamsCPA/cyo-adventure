"""Report verbatim-wording convergence across every pair of a story corpus.

Usage:
    uv run python scripts/check_corpus_convergence.py <path|dir>...
        [--top N] [--check --max-per-1000 X]

`AL-564`/`UW-C341`: the request-path advisory in
``moderation/leaf_diversity.py`` selects its comparison partner by SAME
SKELETON within the SAME FAMILY, which is correct for the question it asks and
structurally blind to convergence that crosses a skeleton, a family, or a
series. Two books of the brass-lantern series share a 98-word verbatim run and
8,164 body-only 4-grams at 215 per 1000 mean words; nothing in the codebase
could see it, because ``validator/series.py`` compares ids and carried state
and never compares prose. This tool is the sweep that can: all pairs, each
labelled with the relationship it actually has.

Measured over the committed corpus on 2026-08-23 (465 pairs of
``out/*.filled.json``, body-only shared 4-grams per 1000 mean words):

    class        n     median    p90      max
    unrelated  464       0.59    2.52    12.92
    series       1     215.25  215.25   215.25

The defect is 16.7x the highest of every other pair, so RANKING finds it and no
threshold is required to. This tool still ships no default bound on the RATE,
and ``--check`` gates only on one the caller states. The series case is now
gated elsewhere and on a different measure: `UW-C341` was ruled on 2026-08-23
(`AL-568`), and validator rule SR-10 blocks a chain whose books share a
contiguous run of more than 15 words, because run LENGTH is the dimension on
which a deliberate refrain and a reused passage do not overlap. A rate cannot
express that permission, which is why it is not the thing that gates.

Choice labels are excluded from the measure, since a shared skeleton supplies
them identically to every fill and they would score the tree rather than the
prose (`AL-563`). Output is identifiers and numbers only: an all-pairs sweep is
the one report here that spans books belonging to different people, so it must
be readable by an operator entitled to read none of them.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, cast

from cyo_adventure.diversity.grams import pairwise_overlap

_CLASSES = ("series", "sibling", "unrelated")


@dataclass(frozen=True, slots=True)
class PairRow:
    """One measured pair.

    Attributes:
        left: The first fill's corpus name.
        right: The second fill's corpus name.
        relationship: One of ``series``, ``sibling``, ``unrelated``.
        shared: Distinct body-only content 4-grams present in both.
        per_1000: ``shared`` per 1000 mean body words.
    """

    left: str
    right: str
    relationship: str
    shared: int
    per_1000: float


def classify_pair(first: dict[str, Any], second: dict[str, Any]) -> str:
    """Name the relationship between two fills.

    Ordered by how much a shared phrase matters to a reader. A series is
    checked first because its books are meant to be read one after the other,
    so a repeated passage lands on the same child within days; siblings are
    two themings of one skeleton, which a single reader is much less likely to
    meet as a pair.

    Args:
        first: A decoded fill.
        second: Another decoded fill.

    Returns:
        ``"series"`` when both declare the same ``metadata.series.series_id``,
        ``"sibling"`` when they share a skeleton ``id``, else ``"unrelated"``.
    """
    meta_a = first.get("metadata")
    meta_b = second.get("metadata")
    series_a = meta_a.get("series") if isinstance(meta_a, dict) else None
    series_b = meta_b.get("series") if isinstance(meta_b, dict) else None
    if isinstance(series_a, dict) and isinstance(series_b, dict):
        id_a = series_a.get("series_id")
        id_b = series_b.get("series_id")
        if id_a is not None and id_a == id_b:
            return "series"
    story_a = first.get("id")
    if story_a is not None and story_a == second.get("id"):
        return "sibling"
    return "unrelated"


def rank_pairs(rows: list[PairRow], limit: int) -> list[PairRow]:
    """Return the ``limit`` most-converged pairs, highest rate first.

    Ties break on the pair's names rather than on discovery order, so two runs
    over one corpus produce one report (`AL-565`).

    Args:
        rows: Every measured pair.
        limit: How many rows to return.

    Returns:
        The ranked prefix.
    """
    return sorted(rows, key=lambda row: (-row.per_1000, row.left, row.right))[:limit]


def measure_corpus(corpus: dict[str, dict[str, Any]]) -> list[PairRow]:
    """Measure every pair of a corpus.

    Args:
        corpus: name -> decoded fill.

    Returns:
        One row per unordered pair; empty when fewer than two fills are given.
    """
    return [
        PairRow(
            left=name_a,
            right=name_b,
            relationship=classify_pair(story_a, story_b),
            shared=overlap.shared,
            per_1000=overlap.per_1000,
        )
        for (name_a, story_a), (name_b, story_b) in combinations(corpus.items(), 2)
        for overlap in (
            pairwise_overlap(story_a, story_b, include_choice_labels=False),
        )
    ]


def _collect_paths(inputs: list[str]) -> list[Path]:
    """Expand directories to the ``*.filled.json`` they contain."""
    paths: list[Path] = []
    for raw in inputs:
        path = Path(raw)
        if path.is_dir():
            paths.extend(sorted(path.glob("*.filled.json")))
        else:
            paths.append(path)
    return paths


def _load_corpus(paths: list[Path]) -> dict[str, dict[str, Any]] | None:
    """Decode every path, or report the first failure and return None."""
    corpus: dict[str, dict[str, Any]] = {}
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            sys.stderr.write(f"error: cannot load {path}: {exc}\n")
            return None
        if not isinstance(data, dict):
            sys.stderr.write(f"error: expected a JSON object in {path}\n")
            return None
        corpus[path.name.removesuffix(".filled.json")] = cast("dict[str, Any]", data)
    return corpus


def _write_distribution(rows: list[PairRow]) -> None:
    """Print the per-class distribution: the corpus's own noise floor."""
    for name in _CLASSES:
        rates = sorted(row.per_1000 for row in rows if row.relationship == name)
        if not rates:
            continue
        p90 = rates[int(0.9 * (len(rates) - 1))]
        sys.stdout.write(
            f"  {name:<10s} n={len(rates):<5d} median={statistics.median(rates):8.2f} "
            f"p90={p90:8.2f} max={max(rates):8.2f}\n"
        )


def _write_verdict(rows: list[PairRow], bound: float | None) -> None:
    """Write the single closing line a battery row can quote.

    ``scripts/run_guard_battery.py`` summarizes a checker by its last
    "ok"/"FAIL" line and falls back to the final line printed, so the ranked
    table alone would be summarized by whichever pair happened to rank last.
    Observe mode deliberately prints neither prefix: with no bound on the rate
    this tool reports a measurement, not a verdict.

    Args:
        rows: Every measured pair.
        bound: The caller's stated ceiling, or ``None`` in observe mode.
    """
    worst = rank_pairs(rows, 1)
    if not worst:
        sys.stdout.write("no pairs measured; convergence is a property of a set\n")
        return
    top = worst[0]
    where = f"{top.per_1000:.2f}/1000 [{top.relationship}] {top.left} ~ {top.right}"
    if bound is None:
        sys.stdout.write(f"top pair {where}; no rate bound, see SR-10\n")
    elif top.per_1000 > bound:
        sys.stdout.write(f"FAIL {where} exceeds {bound:.2f}\n")
    else:
        sys.stdout.write(f"ok worst pair {where} within {bound:.2f}\n")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Returns:
        Exit code: 2 when a path cannot be read or ``--check`` is given with no
        bound, 1 when ``--check`` is given with a bound the corpus exceeds,
        0 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="Filled stories, or directories.")
    parser.add_argument("--top", type=int, default=10, help="Rows to print.")
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--max-per-1000",
        type=float,
        default=None,
        help=(
            "Bound for --check. No default on purpose: where it belongs is an "
            "open owner decision (UW-C341)."
        ),
    )
    args = parser.parse_args(argv)

    if args.check and args.max_per_1000 is None:
        sys.stderr.write(
            "error: --check needs an explicit --max-per-1000. This tool ships no "
            "default bound on the rate: a rate cannot separate a deliberate "
            "refrain from a reused passage, which is why the series case is "
            "gated by validator rule SR-10 on run LENGTH instead (AL-568). Run "
            "without --check to observe.\n"
        )
        return 2

    corpus = _load_corpus(_collect_paths(args.paths))
    if corpus is None:
        return 2

    rows = measure_corpus(corpus)
    sys.stdout.write(
        f"corpus convergence: {len(corpus)} fill(s), {len(rows)} pair(s), "
        "body-only shared 4-grams per 1000 mean words\n"
    )
    _write_distribution(rows)
    for row in rank_pairs(rows, args.top):
        sys.stdout.write(
            f"  {row.per_1000:8.2f}  {row.shared:6d}  [{row.relationship}] "
            f"{row.left} ~ {row.right}\n"
        )

    bound = cast("float | None", args.max_per_1000) if args.check else None
    _write_verdict(rows, bound)

    if bound is not None and any(row.per_1000 > bound for row in rows):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
