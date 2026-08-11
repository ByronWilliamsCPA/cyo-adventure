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

from cyo_adventure.validator.reading_level import (
    _SENTENCE_RE,  # pyright: ignore[reportPrivateUsage]
    _WORD_RE,  # pyright: ignore[reportPrivateUsage]
    _count_syllables,  # pyright: ignore[reportPrivateUsage]
)

_MAX_GRADE = 7.0
_MIN_IN_BAND = 0.5
_MIN_WORDS = 20
_TARGET = 5.5
_TOLERANCE = 1.5


class Score(NamedTuple):
    """One book's aggregate reading level."""

    book: str
    nodes: int
    words: int
    grade: float
    in_band: float


def grade(text: str) -> float | None:
    """Return the Flesch-Kincaid grade of a passage, or None if too short.

    Uses the production validator's own tokenisation and syllable estimate so
    this measure cannot drift away from the per-node rule it complements.

    Args:
        text: The passage to score.

    Returns:
        The grade, or None when the passage is too short to score stably.
    """
    words = cast("list[str]", _WORD_RE.findall(text))
    if len(words) < _MIN_WORDS:
        return None
    sentences = max(len([s for s in _SENTENCE_RE.split(text) if s.strip()]), 1)
    syllables = sum(_count_syllables(w) for w in words)
    return 0.39 * (len(words) / sentences) + 11.8 * (syllables / len(words)) - 15.59


def score(path: Path) -> Score | None:
    """Score one filled storybook, or None when it has too little prose.

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
    whole = grade(" ".join(bodies))
    if whole is None:
        return None
    scored = [g for g in (grade(b) for b in bodies) if g is not None]
    in_band = (
        sum(1 for g in scored if abs(g - _TARGET) <= _TOLERANCE) / len(scored)
        if scored
        else 0.0
    )
    return Score(
        path.stem,
        len(bodies),
        len(_WORD_RE.findall(" ".join(bodies))),
        whole,
        in_band,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 1 with --check when a book is too hard."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stories", nargs="+", help="Filled storybook JSON files.")
    parser.add_argument(
        "--max-grade",
        type=float,
        default=_MAX_GRADE,
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
    sys.stdout.write(
        f"{'book':34s} {'nodes':>5s} {'words':>6s} {'FK grade':>9s} {'in band':>8s}\n"
    )
    sys.stdout.write("-" * 70 + "\n")
    for raw in args.stories:
        scored = score(Path(raw).resolve())
        if scored is None:
            sys.stdout.write(f"{Path(raw).stem:34s} too little prose to score\n")
            continue
        over = scored.grade > args.max_grade
        breached = breached or over
        sys.stdout.write(
            f"{scored.book:34s} {scored.nodes:5d} {scored.words:6d} "
            f"{scored.grade:9.2f} {scored.in_band:7.0%}"
            f"{'   OVER' if over else ''}\n"
        )
        if scored.in_band < args.min_in_band:
            sys.stdout.write(
                f"{'':34s} advisory: only {scored.in_band:.0%} of nodes sit inside "
                f"the band, so the aggregate is carried by a minority\n"
            )

    if breached:
        sys.stderr.write(
            f"FAIL reading level: whole-book grade above {args.max_grade}, which is "
            f"the band's own upper edge. Per-node RL-13 findings are advisory and "
            f"will not catch this; the book is too hard for its age band\n"
        )
    sys.stdout.write(f"{'FAIL' if breached else 'ok  '}: reading level\n")
    return 1 if (breached and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
