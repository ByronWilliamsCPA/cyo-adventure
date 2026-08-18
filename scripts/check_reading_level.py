"""Gate a book on its whole-book reading level, which nothing currently does.

Usage:
    uv run python scripts/check_reading_level.py <filled.json>... [--check]
        [--max-grade 7.0] [--min-in-band 0.5]

**The gap.** `RL-13` in the production validator scores each node and emits
`WARNING` findings that never block. That is deliberate and defensible per node,
where a single short body scores noisily. It leaves nobody watching the book.
Three 101-node books were measured at whole-book Flesch-Kincaid 8.14 to 8.41
against a 5.5 target, with 16 to 20 of 101 nodes in band and 81 to 85 advisory
warnings each, and the gate returned not-blocked on all three (`AL-209`).
Reading level degrades with scale and nothing stops it.

**What this adds.** The aggregate the per-node rule cannot see: Flesch-Kincaid
over the concatenated bodies, plus the share of nodes inside the band. Both are
computed with the production validator's own syllable and sentence heuristics,
imported rather than reimplemented, so this cannot drift from `RL-13`.

**Why it is a script and not a severity change to `RL-13`.** Measured across the
22 filled books this programme has produced, **a blocking rule at grade 7.0
would reject 9 of them**, several of which pass every other guard. That is a
real decision about what the product ships, it affects the existing catalog and
CI, and it belongs to the owner rather than to a checker. The measurement is
here so the decision can be made with a number attached.

**Calibration, on those 22 books:**

| Whole-book FK | Books |
| --- | --- |
| 4.5 to 5.5, comfortably in band | 5 |
| 5.5 to 7.0, in band or at its edge | 8 |
| 7.0 to 7.5, over | 5 |
| 8.1 to 8.4, well over | 4, of which 3 are the 101-node books |

The default ceiling of 7.0 is the band's own upper edge (target 5.5 plus
tolerance 1.5) rather than a number chosen to make current work pass. Every
101-node book fails it and that is the finding, not a miscalibration.

**What it cannot do.** Flesch-Kincaid is a sentence-length and syllable proxy.
A book of short sentences full of unfamiliar words scores well and reads badly,
and no formula reaches vocabulary difficulty. Treat a pass as "not obviously too
hard" and never as "age-appropriate".
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple, cast

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cyo_adventure.validator.band_profile import reading_level_target_for
from cyo_adventure.validator.reading_level import BookReadingLevel, measure_book

# Fallbacks for a book that declares neither a reading level nor a configured
# band. These are the old hardcoded values, kept only so an undeclared book is
# still graded rather than skipped; a declared book never reaches them.
_FALLBACK_TARGET = 5.5
_FALLBACK_TOLERANCE = 1.5
# How far past a book's own upper bound counts as "too hard for its band". One
# grade, so the blocking tier sits clear of the advisory window rather than on
# its edge.
_CEILING_HEADROOM = 1.0
# Arbitrary, and advisory for that reason. Only the grade ceiling gates.
_MIN_IN_BAND = 0.5


class Score(NamedTuple):
    """One book's aggregate reading level, its name, and its own grade ceiling."""

    book: str
    level: BookReadingLevel
    max_grade: float


def score(path: Path) -> Score | None:
    """Score one filled storybook, or None when it has too little prose.

    The measurement itself lives in ``validator.reading_level.measure_book``,
    which is also what `RL-13` and the generation-time reading-level repair
    loop use. This script previously reimplemented the Flesch-Kincaid formula
    over three privately-imported symbols, and the reimplementation had drifted:
    it counted sentences with ``_SENTENCE_RE.split`` where the validator uses
    ``findall``, and applied a ``_WORD_RE``-based word floor where the validator
    splits on whitespace. Both differences moved reported grades slightly, so
    the docstring's claim that this measure "cannot drift from RL-13" was false
    at the time it was written.

    Args:
        path: Path to a filled storybook JSON.

    Returns:
        Its aggregate Score, or None.
    """
    story = cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))
    bodies = [
        str(n.get("body") or "")
        for n in cast("list[dict[str, Any]]", story.get("nodes") or [])
    ]
    target, tolerance, max_grade = _thresholds_for(story)
    level = measure_book(bodies, target=target, tolerance=tolerance)
    return None if level is None else Score(path.stem, level, max_grade)


def _thresholds_for(story: dict[str, Any]) -> tuple[float, float, float]:
    """Return this book's own ``(target, tolerance, max_grade)``.

    This script is listed in ``run_guard_battery.py`` as "is the whole book too
    hard for its band", gating yes, and it never read the band. It graded all six
    bands against a hardcoded 5.5 plus or minus 1.5 with a 7.0 ceiling, which is
    effectively the 10-13 target. Over the 31 committed books every one it marked
    OVER was INSIDE its own declared window (``the-last-train-north``, 16+,
    window 7.5-10.5, FK 9.33, failed as "too hard for its age band"), while
    ``the-sunken-signal`` sat a full grade BELOW its 16+ window and passed. A 3-5
    book had 5.0 grades of headroom before the gate fired (``UW-C281``).

    Precedence matches RL-13's: the story's own declared
    ``metadata.reading_level`` governs, since that is what the node-level rule
    grades against, and the band table is the default it should have been
    authored from. The ceiling scales with the target so it stays a ceiling
    rather than a second, band-blind target.

    Args:
        story: The decoded storybook.

    Returns:
        The ``(target, tolerance, max_grade)`` triple for this book.
    """
    metadata = story.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    declared = metadata.get("reading_level")
    declared = declared if isinstance(declared, dict) else {}

    band = metadata.get("age_band")
    band_target = reading_level_target_for(str(band)) if band is not None else None

    raw_target = declared.get("target")
    target = (
        float(cast("float", raw_target))
        if isinstance(raw_target, (int, float))
        else (band_target if band_target is not None else _FALLBACK_TARGET)
    )
    raw_tolerance = declared.get("tolerance")
    tolerance = (
        float(cast("float", raw_tolerance))
        if isinstance(raw_tolerance, (int, float))
        else _FALLBACK_TOLERANCE
    )
    return target, tolerance, target + tolerance + _CEILING_HEADROOM


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Returns 1 with --check when a book is too hard for its band, or when a book
    holds too little prose to score at all.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stories", nargs="+", help="Filled storybook JSON files.")
    parser.add_argument(
        "--max-grade",
        type=float,
        default=None,
        help="Ceiling on whole-book Flesch-Kincaid. Default is the band's edge.",
    )
    parser.add_argument(
        "--min-in-band",
        type=float,
        default=_MIN_IN_BAND,
        help="Floor on the share of nodes inside the band. Advisory, never gates.",
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    breached = False
    unscorable: list[str] = []
    sys.stdout.write(
        f"{'book':34s} {'nodes':>5s} {'words':>6s} {'FK grade':>9s} {'in band':>8s}\n"
    )
    sys.stdout.write("-" * 70 + "\n")
    for raw in args.stories:
        scored = score(Path(raw).resolve())
        if scored is None:
            unscorable.append(Path(raw).stem)
            sys.stdout.write(f"{Path(raw).stem:34s} too little prose to score\n")
            continue
        level = scored.level
        ceiling = args.max_grade if args.max_grade is not None else scored.max_grade
        over = level.grade > ceiling
        breached = breached or over
        sys.stdout.write(
            f"{scored.book:34s} {level.nodes:5d} {level.words:6d} "
            f"{level.grade:9.2f} {level.in_band:7.0%}"
            + (
                f"  ({level.nodes - level.scored_nodes} node(s) too short to score)"
                if level.scored_nodes != level.nodes
                else ""
            )
            + f"{'   OVER' if over else ''}\n"
        )
        if level.in_band < args.min_in_band:
            sys.stdout.write(
                f"{'':34s} advisory: only {level.in_band:.0%} of SCORED nodes sit inside "
                f"the band, so the aggregate is carried by a minority\n"
            )

    # #CRITICAL: data integrity: a guard that could not evaluate a book must not
    # report it clear. score() returns None only when the WHOLE book holds fewer
    # than the minimum scoreable words, which in a filled storybook means the
    # fill is empty or truncated: the very defect this guard exists to catch.
    # Skipping it left the book counted as a pass, so run_guard_battery could
    # print a green battery for a book no reader could use.
    # #VERIFY: test_reading_level_unscorable_book_fails_check asserts main()
    # returns 1 under --check when a book falls below the scoreable floor.
    if unscorable:
        sys.stderr.write(
            f"FAIL reading level: {len(unscorable)} book(s) hold too little prose "
            f"to score, so this guard cannot say whether they sit in band: "
            f"{', '.join(sorted(unscorable))}\n"
        )
    if breached:
        sys.stderr.write(
            f"FAIL reading level: whole-book grade above {ceiling:.1f}, which is "
            f"the band's own upper edge. Per-node RL-13 findings are advisory and "
            f"will not catch this; the book is too hard for its age band\n"
        )
    failed = breached or bool(unscorable)
    sys.stdout.write(f"{'FAIL' if failed else 'ok  '}: reading level\n")
    return 1 if (failed and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
