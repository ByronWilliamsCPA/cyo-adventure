"""Re-unit a book-scope measure onto covering paths, and say whether it transfers.

This is W2 of the measurement workplan, made reproducible. The original W2 run
was executed ad hoc and left a table in a planning document that nobody else can
regenerate; the numbers were right and the method was unrepeatable, which is half
a measurement.

Two questions, kept apart:

**Does the finer unit change a verdict?** For each measure, count the books where
one covering path falls outside the acceptable band while the whole book falls
inside. Only that direction counts. A path's node set is a subset of the book's,
so any measure that is a count over nodes or endings can only ever be *smaller*
per path, and a per-path check on one of those is a laxer gate wearing the
language of a stricter one (`AL-343`). Such measures are refused rather than
scored, and the refusal names the monotonicity that caused it.

**Does the threshold still bind at the smaller denominator?** A rate calibrated
on whole books stops meaning anything when the denominator shrinks, and it fails
by ceasing to bind rather than by erroring. `check_prose_craft`'s told-emotion
band is 0.5 hits per 1000 narration words, calibrated on books of 2,344 to 24,601
words; on a 600-word covering path a single hit already scores 1.67, so the band
never binds and the measure has quietly become "does this path contain the phrase
at all" (`AL-342`). For every rate measure this script therefore reports the
**smallest nonzero value the new denominator admits**, and refuses to report a
disagreement rate for any measure whose band sits below that floor.

Usage::

    uv run python scripts/measure_per_path.py out/*.filled.json
    uv run python scripts/measure_per_path.py out/*.filled.json --json out/per-path.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pydantic import ValidationError  # noqa: E402

from cyo_adventure.storybook.models import Storybook  # noqa: E402
from cyo_adventure.validator.paths import (  # noqa: E402
    covering_paths,
    path_bodies,
)
from cyo_adventure.validator.reading_level import measure_book  # noqa: E402
from scripts.check_prose_craft import (  # noqa: E402
    _WORD,  # pyright: ignore[reportPrivateUsage]
    strip_dialogue,
    told_emotion,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

# W2's bar: a per-path measure earns its place when it changes a verdict on at
# least this share of books, counting only the direction that exposes a defect
# the book aggregate hides.
_DISAGREEMENT_BAR: Final[float] = 0.10

# The told-emotion band and the denominator range it was calibrated over. Both
# are recorded here rather than only in the checker, because a re-unit is a
# change of premise and the premise has to be visible to be checked (`AL-342`).
_TOLD_BAND_PER_1000: Final[float] = 0.5
_TOLD_CALIBRATION_WORDS: Final[tuple[int, int]] = (2_344, 24_601)

__all__ = ["MeasureOutcome", "measure_corpus", "told_floor"]


@dataclass
class MeasureOutcome:
    """What one measure did when re-unitted from the book onto its paths.

    Attributes:
        measure: The measure's name.
        books: Books it could be computed on.
        book_in_path_out: Books where a path breaches the band and the book does
            not. The only direction that counts toward the bar.
        book_out_path_in: Books where the book breaches and no path does. Recorded
            because it is evidence about dilution, never toward the bar.
        band_floor_breaches: Books where the band sits at or below the smallest
            nonzero value the path denominator admits, so the band cannot bind.
        spreads: Within-book spread across paths, one entry per book.
        refused: Why the measure was not scored, or empty when it was.
    """

    measure: str
    books: int = 0
    book_in_path_out: int = 0
    book_out_path_in: int = 0
    band_floor_breaches: int = 0
    spreads: list[float] = field(default_factory=list)
    refused: str = ""

    @property
    def disagreement(self) -> float:
        """Share of books where a path exposes what the book aggregate hides.

        Returns:
            The rate against :data:`_DISAGREEMENT_BAR`, or ``0.0`` with no books.
        """
        return self.book_in_path_out / self.books if self.books else 0.0

    @property
    def verdict(self) -> str:
        """State keep, drop, or refused, with the reason.

        Returns:
            One line, suitable for the report and for the workplan's outcome
            note.
        """
        if self.refused:
            return f"REFUSED: {self.refused}"
        if self.band_floor_breaches:
            return (
                f"INERT at path scale: the band cannot bind on "
                f"{self.band_floor_breaches} of {self.books} books, because a "
                "single hit already exceeds it. Re-derive the band or express "
                "the path-scope version as a count."
            )
        if self.disagreement >= _DISAGREEMENT_BAR:
            return f"KEEP: {self.disagreement:.1%} of books change verdict"
        return (
            f"DROP: {self.disagreement:.1%} of books change verdict, under the "
            f"{_DISAGREEMENT_BAR:.0%} bar; the book aggregate is sufficient"
        )


def told_floor(narration_words: int) -> float:
    """Return the smallest nonzero told-emotion rate a passage length admits.

    Args:
        narration_words: Non-dialogue words the rate is normalised against.

    Returns:
        The rate a single hit produces. A band at or below this number cannot
        distinguish one hit from many and has stopped being a rate.
    """
    return 1_000.0 / max(narration_words, 1)


def _band(doc: dict[str, Any]) -> tuple[float, float] | None:
    """Read the declared reading-level band.

    Args:
        doc: The filled story JSON.

    Returns:
        ``(target, tolerance)``, or ``None`` when the book declares no band.
    """
    metadata = doc.get("metadata")
    if not isinstance(metadata, dict):
        return None
    level = metadata.get("reading_level")
    if not isinstance(level, dict):
        return None
    target, tolerance = level.get("target"), level.get("tolerance")
    if not isinstance(target, (int, float)) or not isinstance(tolerance, (int, float)):
        return None
    if isinstance(target, bool) or isinstance(tolerance, bool):
        return None
    return float(target), float(tolerance)


def _told_rate(bodies: Sequence[str]) -> tuple[float, int]:
    """Compute the told-emotion rate over a set of bodies.

    Args:
        bodies: Node bodies, whole book or one path.

    Returns:
        ``(hits per 1000 narration words, narration words)``.
    """
    story = {"nodes": [{"id": str(i), "body": b} for i, b in enumerate(bodies)]}
    report = told_emotion(story)
    words = sum(len(_WORD.findall(strip_dialogue(body))) for body in bodies)
    return (len(report.hits) / max(words, 1) * 1_000.0, words)


def _score_reading_level(
    doc: dict[str, Any], paths: Sequence[list[str]], story: Storybook
) -> tuple[bool, bool, float] | None:
    """Score one book's reading level at both units.

    Args:
        doc: The filled story JSON.
        paths: The covering path set.
        story: The parsed story.

    Returns:
        ``(book_outside, any_path_outside, within_book_spread)``, or ``None``
        when the book declares no band or holds too little scorable prose.
    """
    band = _band(doc)
    if band is None:
        return None
    target, tolerance = band
    whole = measure_book(
        (node.body for node in story.nodes), target=target, tolerance=tolerance
    )
    if whole is None:
        return None
    grades: list[float] = []
    for path in paths:
        level = measure_book(
            path_bodies(story, path), target=target, tolerance=tolerance
        )
        if level is not None:
            grades.append(level.grade)
    if not grades:
        return None
    outside = abs(whole.grade - target) > tolerance
    any_path_outside = any(abs(g - target) > tolerance for g in grades)
    spread = statistics.stdev(grades) if len(grades) > 1 else 0.0
    return (outside, any_path_outside, spread)


def _score_told(
    story: Storybook, paths: Sequence[list[str]]
) -> tuple[bool, bool, float, bool]:
    """Score one book's told-emotion rate at both units.

    Args:
        story: The parsed story.
        paths: The covering path set.

    Returns:
        ``(book_outside, any_path_outside, spread, band_is_inert)``. The last
        element is the finding that matters: it is ``True`` when the band sits
        at or below the smallest nonzero rate the shortest path admits, which
        makes every "breach" on that path a single hit rather than a rate.
    """
    book_rate, _book_words = _told_rate([node.body for node in story.nodes])
    rates: list[float] = []
    inert = False
    for path in paths:
        rate, words = _told_rate(path_bodies(story, path))
        rates.append(rate)
        if told_floor(words) >= _TOLD_BAND_PER_1000:
            inert = True
    spread = statistics.stdev(rates) if len(rates) > 1 else 0.0
    return (
        book_rate > _TOLD_BAND_PER_1000,
        any(r > _TOLD_BAND_PER_1000 for r in rates),
        spread,
        inert,
    )


def measure_corpus(
    paths_in: Sequence[Path],
) -> tuple[dict[str, MeasureOutcome], list[str], list[str]]:
    """Re-unit every supported measure over a corpus of filled books.

    Args:
        paths_in: Filled-story JSON files.

    Returns:
        The per-measure outcomes, the files measured, and the files skipped with
        the reason. The last two are returned rather than logged because **every
        verdict here is a statement about the corpus it ran on**, and a reader
        comparing two runs needs to see whether they measured the same books.
    """
    measured: list[str] = []
    skipped: list[str] = []
    outcomes = {
        "reading_level": MeasureOutcome("reading_level"),
        "told_emotion": MeasureOutcome("told_emotion"),
        "moral_tags": MeasureOutcome(
            "moral_tags",
            refused=(
                "monotone under path-subsetting: a path's endings are a subset "
                "of the book's, so its count can never exceed the book's and a "
                "per-path check can only pass books the book-level check fails "
                "(AL-343)"
            ),
        ),
        "tense_instability": MeasureOutcome(
            "tense_instability",
            refused=(
                "monotone under path-subsetting: unstable nodes on a path are a "
                "subset of the book's, so the per-path version is weaker by "
                "construction (AL-343)"
            ),
        ),
    }

    for file_path in paths_in:
        doc = json.loads(file_path.read_text(encoding="utf-8"))
        try:
            story = Storybook.model_validate(doc)
        except ValidationError:
            # A pre-schema-v2 fill, not a defect in this measurement. Skipped
            # loudly and counted, so a shrinking corpus is visible in the
            # denominator rather than only in stderr.
            skipped.append(f"{file_path.name} (pre-v2 schema)")
            print(f"  skip {file_path.name}: pre-v2 schema", file=sys.stderr)
            continue
        if any("<<FILL" in node.body for node in story.nodes):
            skipped.append(f"{file_path.name} (retained FILL directives)")
            print(f"  skip {file_path.name}: retained FILL directives", file=sys.stderr)
            continue
        path_set = covering_paths(story)
        if not path_set.complete or not path_set.paths:
            skipped.append(f"{file_path.name} (incomplete path set)")
            print(f"  skip {file_path.name}: incomplete path set", file=sys.stderr)
            continue
        measured.append(file_path.name)

        level = _score_reading_level(doc, path_set.paths, story)
        if level is not None:
            book_out, path_out, spread = level
            entry = outcomes["reading_level"]
            entry.books += 1
            entry.spreads.append(spread)
            entry.book_in_path_out += int(path_out and not book_out)
            entry.book_out_path_in += int(book_out and not path_out)

        book_out, path_out, spread, inert = _score_told(story, path_set.paths)
        entry = outcomes["told_emotion"]
        entry.books += 1
        entry.spreads.append(spread)
        entry.book_in_path_out += int(path_out and not book_out)
        entry.book_out_path_in += int(book_out and not path_out)
        entry.band_floor_breaches += int(inert)

    return outcomes, measured, skipped


def _print_report(
    outcomes: dict[str, MeasureOutcome], measured: Sequence[str], skipped: Sequence[str]
) -> None:
    """Print the per-measure verdicts and the calibration premises behind them.

    Args:
        outcomes: Output of :func:`measure_corpus`.
        measured: The files that contributed.
        skipped: The files that did not, each with its reason.
    """
    print(f"\nCORPUS  {len(measured)} measured, {len(skipped)} skipped")
    for name in skipped:
        print(f"    skipped: {name}")
    print("\nPER-PATH RE-UNIT  (W2; covering paths, book aggregate as the parent)")
    width = max(len(name) for name in outcomes)
    print(
        f"  {'measure':<{width}}  {'books':>5} {'B-in/P-out':>11} "
        f"{'B-out/P-in':>11} {'spread':>7}"
    )
    for name, entry in outcomes.items():
        if entry.refused:
            print(f"  {name:<{width}}  {'-':>5} {'-':>11} {'-':>11} {'-':>7}")
            continue
        spread = statistics.median(entry.spreads) if entry.spreads else 0.0
        print(
            f"  {name:<{width}}  {entry.books:>5} {entry.book_in_path_out:>11} "
            f"{entry.book_out_path_in:>11} {spread:>7.3f}"
        )
    print("\n  Verdicts:")
    for name, entry in outcomes.items():
        print(f"    {name}: {entry.verdict}")
    print(
        "\n  Only the book-inside/path-outside direction counts toward the "
        f"{_DISAGREEMENT_BAR:.0%} bar. The reverse is dilution, not sensitivity."
    )
    print(
        "\n  EVERY VERDICT ABOVE IS SCOPED TO THIS CORPUS. A measure that drops "
        "here has dropped on these books, not in general. The published W2 run "
        "measured 53 books including out/vendor-comparison/, which is untracked "
        "and therefore absent from any checkout but the machine that produced "
        "it; a run over the committed books alone is a different and easier "
        "corpus, since those are the hand-authored catalogue fills rather than "
        "the machine-generated comparison books. Quote the corpus with the "
        "number or do not quote the number."
    )
    print(
        f"\n  Told-emotion band {_TOLD_BAND_PER_1000} per 1000 was calibrated over "
        f"books of {_TOLD_CALIBRATION_WORDS[0]:,} to "
        f"{_TOLD_CALIBRATION_WORDS[1]:,} narration words. A band binds only "
        f"above 1000/denominator, so it needs a passage over "
        f"{int(1_000 / _TOLD_BAND_PER_1000):,} words to distinguish one hit "
        "from a rate."
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Re-unit the corpus and print the verdicts.

    Args:
        argv: Argument vector, or ``None`` for ``sys.argv``.

    Returns:
        Process exit status. Always 0 on a completed measurement: this script
        reports a decision, it does not gate one.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fills", nargs="+", type=Path)
    parser.add_argument("--json", type=Path, default=None, dest="json_out")
    args = parser.parse_args(argv)

    outcomes, measured, skipped = measure_corpus(args.fills)
    _print_report(outcomes, measured, skipped)

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(
                {
                    "corpus_measured": measured,
                    "corpus_skipped": skipped,
                    "disagreement_bar": _DISAGREEMENT_BAR,
                    "told_band_per_1000": _TOLD_BAND_PER_1000,
                    "told_calibration_words": list(_TOLD_CALIBRATION_WORDS),
                    "measures": {
                        name: {
                            "books": entry.books,
                            "book_in_path_out": entry.book_in_path_out,
                            "book_out_path_in": entry.book_out_path_in,
                            "band_floor_breaches": entry.band_floor_breaches,
                            "median_spread": (
                                statistics.median(entry.spreads)
                                if entry.spreads
                                else None
                            ),
                            "refused": entry.refused,
                            "verdict": entry.verdict,
                        }
                        for name, entry in outcomes.items()
                    },
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
