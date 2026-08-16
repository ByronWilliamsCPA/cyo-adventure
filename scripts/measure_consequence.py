"""Report fork consequence across a corpus, and say whether it discriminates (W3).

W3's stage-one decision rule is not "is the number good" but "does the number
distinguish our books from each other". A measure returning the same verdict for
every book is measuring nothing, which is exactly how the judge panel's dialogue
criterion appeared to fail: its per-leg cell means were 3.00 for seven of eight
legs and 3.25 for the eighth, a spread of 0.088. That reading is now itself
under review, since the deterministic measure it was compared against was
blind to unquoted dialogue; the principle stands regardless of how that
particular case resolves.

So this prints the distribution, not a mean, and states the verdict the
distribution supports:

- nearly every fork a false choice: act now, the catalogue has a real problem;
- nearly none: the measure has no discriminating power here and parks until the
  corpus changes;
- spread across books: keep it as a reported statistic.

Promotion to a blocking rule is out of scope by construction. `BandProfile`
already carries an unenforced ``reconvergence_ceiling`` waiting for a number, and
that number is W12's to supply, from readers rather than from this script.

Usage::

    uv run python scripts/measure_consequence.py skeletons/**/*.json
    uv run python scripts/measure_consequence.py out/*.filled.json --json out/w3.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pydantic import ValidationError  # noqa: E402

from cyo_adventure.storybook.models import Storybook  # noqa: E402
from cyo_adventure.validator.consequence import measure_consequence  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Sequence

# Bands for the stage-one verdict. Deliberately wide: this rule decides whether
# the measure discriminates at all, not whether any book is good.
_DOMINATED: Final[float] = 0.80
_ABSENT: Final[float] = 0.05

# Below this many complete books, a spread is not evidence of discrimination.
# One book has no spread by definition, and claiming a measure separates books
# on a sample of one is the shape of the error this whole plan exists to catch.
_MIN_BOOKS_FOR_A_CLAIM: Final[int] = 3

__all__ = ["BookConsequence", "scan"]


@dataclass(frozen=True, slots=True)
class BookConsequence:
    """One book's fork-consequence summary.

    Attributes:
        name: The file name.
        forks: How many branch pairs were measured.
        false_choices: How many changed nothing.
        rate: False-choice share, or ``None`` when the report was incomplete.
        median_distance: Median reconvergence distance over forks that rejoined.
        state_carrying: Forks whose branches arrived with differing state.
        stateless: Whether the book declares no variables at all, in which case
            the state half of the measure is empty by construction and the rate
            rests on distance alone.
        diverging: Forks whose branches ran to different endings and never
            rejoined. Reported separately from the false-choice rate because it
            is the opposite end of the same axis, and a book made entirely of
            them is as uninformative to this measure as one made entirely of
            false choices.
    """

    name: str
    forks: int
    false_choices: int
    rate: float | None
    median_distance: float | None
    state_carrying: int
    diverging: int
    stateless: bool


def scan(paths: Sequence[Path]) -> tuple[list[BookConsequence], list[str]]:
    """Measure fork consequence for every story file given.

    Args:
        paths: Story JSON files, skeletons or fills.

    Returns:
        One summary per measurable book, and the names skipped with a reason.
    """
    rows: list[BookConsequence] = []
    skipped: list[str] = []
    for path in paths:
        try:
            story = Storybook.model_validate(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (ValidationError, json.JSONDecodeError):
            skipped.append(f"{path.name} (unparseable or pre-v2 schema)")
            continue
        report = measure_consequence(story)
        distances = [f.distance for f in report.forks if f.distance is not None]
        rows.append(
            BookConsequence(
                name=path.name,
                forks=len(report.forks),
                false_choices=sum(1 for f in report.forks if f.is_false_choice),
                rate=report.false_choice_rate,
                median_distance=statistics.median(distances) if distances else None,
                state_carrying=sum(1 for f in report.forks if f.state_delta),
                diverging=sum(1 for f in report.forks if f.outcome == "diverges"),
                stateless=not story.variables,
            )
        )
    return rows, skipped


def _verdict(rates: Sequence[float]) -> str:
    """State whether the measure discriminates on this corpus.

    Args:
        rates: Per-book false-choice rates, incomplete books excluded.

    Returns:
        The stage-one verdict.
    """
    if not rates:
        return (
            "NOT MEASURED: no book produced a complete report, so nothing here "
            "is evidence about the catalogue"
        )
    if len(rates) < _MIN_BOOKS_FOR_A_CLAIM:
        return (
            f"NOT MEASURED: {len(rates)} complete book(s), under the "
            f"{_MIN_BOOKS_FOR_A_CLAIM} needed before a spread means anything. "
            "The per-book rows above are still real; the verdict is not"
        )
    mean = statistics.fmean(rates)
    spread = statistics.stdev(rates) if len(rates) > 1 else 0.0
    if mean >= _DOMINATED:
        return (
            f"ACT: {mean:.1%} of forks change nothing on average. That is a "
            "finding about the catalogue rather than about the measure, and it "
            "is worth acting on before any further structural work"
        )
    if mean <= _ABSENT and spread < 0.05:
        return (
            f"PARK: {mean:.1%} of forks change nothing and the spread is "
            f"{spread:.3f}. The measure returns effectively the same verdict for "
            "every book, so it has no discriminating power on this corpus. Park "
            "it and revisit when the corpus changes"
        )
    return (
        f"KEEP as a reported statistic: mean {mean:.1%}, spread {spread:.3f} "
        "across books. It separates books from each other, which is the stage-one "
        "bar. Promotion to a blocking rule still requires W12"
    )


def _print_report(
    rows: Sequence[BookConsequence], skipped: Sequence[str], elapsed: float
) -> None:
    """Print the distribution, then the verdict it supports.

    Args:
        rows: Per-book summaries.
        skipped: Names skipped, with reasons.
        elapsed: Wall-clock seconds for the scan.
    """
    print(f"\nFORK CONSEQUENCE  (W3; {len(rows)} books in {elapsed:.2f}s)")
    for name in skipped:
        print(f"    skipped: {name}")
    if not rows:
        print("  Nothing measurable.")
        return
    width = max(len(r.name) for r in rows)
    print(
        f"  {'book':<{width}}  {'forks':>5} {'false':>6} {'rate':>7} "
        f"{'med dist':>9} {'stateful':>9} {'diverge':>8}"
    )
    for row in sorted(rows, key=lambda r: -(r.rate or 0.0)):
        rate = f"{row.rate:.1%}" if row.rate is not None else "incompl"
        dist = f"{row.median_distance:.1f}" if row.median_distance is not None else "-"
        print(
            f"  {row.name:<{width}}  {row.forks:>5} {row.false_choices:>6} "
            f"{rate:>7} {dist:>9} {row.state_carrying:>9} {row.diverging:>8}"
        )
    stateless = [r for r in rows if r.stateless]
    if stateless:
        print(
            f"\n  {len(stateless)} of {len(rows)} book(s) declare no variables at "
            "all, so their forks can only be scored on distance and their state "
            "delta is empty by construction rather than by measurement. Read "
            "their rate as the weaker, distance-only half of this measure."
        )
    rates = [r.rate for r in rows if r.rate is not None]
    incomplete = len(rows) - len(rates)
    if incomplete:
        print(
            f"\n  {incomplete} book(s) reported incomplete and are excluded from "
            "the verdict: a fork that did not rejoin inside the horizon is an "
            "unmeasured distance, not a large one."
        )
    print(f"\nVerdict: {_verdict(rates)}")


def main(argv: Sequence[str] | None = None) -> int:
    """Scan a corpus and print the stage-one verdict.

    Args:
        argv: Argument vector, or ``None`` for ``sys.argv``.

    Returns:
        Process exit status. Always 0 on a completed scan: this reports a
        decision rather than gating one.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stories", nargs="+", type=Path)
    parser.add_argument("--json", type=Path, default=None, dest="json_out")
    args = parser.parse_args(argv)

    started = time.monotonic()
    rows, skipped = scan(args.stories)
    elapsed = time.monotonic() - started
    _print_report(rows, skipped, elapsed)

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(
                {
                    "seconds": round(elapsed, 3),
                    "skipped": list(skipped),
                    "books": [
                        {
                            "name": r.name,
                            "forks": r.forks,
                            "false_choices": r.false_choices,
                            "rate": r.rate,
                            "median_distance": r.median_distance,
                            "state_carrying": r.state_carrying,
                            "diverging": r.diverging,
                            "stateless": r.stateless,
                        }
                        for r in rows
                    ],
                    "verdict": _verdict([r.rate for r in rows if r.rate is not None]),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nWrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
