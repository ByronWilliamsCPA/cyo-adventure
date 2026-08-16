"""Measure the panel's run-to-run spread per criterion, and restate W7's
false-positive column against controls (`UW-C258`, `UW-C255`).

Two register rows have been waiting on the same thing: a second scoring of the
same arms by the same judges.

**`UW-C258`: per-criterion spread.** The 2026-08-15 estimate compared two runs
at *leg mean* granularity, because a killed run had been salvaged from its
stdout and stdout carries only the mean across the seven criteria. A leg mean
is the wrong unit for W7, whose verdicts are per criterion: averaging seven
criteria together hides a criterion that swings a full point behind six that
did not move. This reads per-criterion scores from both runs and reports the
spread that W7's own decision rule actually consumes.

**`UW-C255`: the false-positive column.** W7 counted a criterion as a false
positive when it moved on *another* criterion's defect arm. That assumes each
arm carries exactly one defect, and none do: `reading_level_up` rewrites a
third of the prose, so `voice` and `imagery` genuinely change, and
`premise_duplicate` replaces the opening node, so `engagement` genuinely
changes. Every recorded false positive was a correct detection of real
collateral change, so the column penalised criteria for working.

The restatement here uses the **control arms only**. A control is the book
unmodified, so a criterion that moves between two scorings of a control has
moved on nothing at all. That is the only comparison in this battery where
movement is unambiguously noise rather than detection, which makes it the
honest denominator for a false-positive rate.

Neither number is a verdict. Both describe the instrument, and the point of
measuring them is that a W7 KEEP whose effect size sits inside this spread is
not reproducible, whoever reports it.

Usage::

    uv run python scripts/w7_run_to_run.py \
        --first out/w7/verdicts.json --second out/w7-run4/journal.jsonl
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.w7_agreement import (  # noqa: E402
    _CONTROL_ARM,  # pyright: ignore[reportPrivateUsage]
    _CRITERIA,  # pyright: ignore[reportPrivateUsage]
    _MIN_PAIRS,  # pyright: ignore[reportPrivateUsage]
)

# W7's own detection margin. A criterion whose defect-arm effect is smaller
# than this is reported as INCONCLUSIVE rather than KEEP, so it is also the
# threshold against which run-to-run movement matters: movement at or above it
# can flip a verdict on its own.
_DETECTION_MARGIN: Final[float] = 0.5

__all__ = ["load_records", "matched_pairs", "report"]


def load_records(path: Path) -> list[dict[str, object]]:
    """Load scored records from a verdicts file or a per-line journal.

    Both shapes exist by design: `verdicts.json` is written when a run
    completes, and `journal.jsonl` is flushed per scoring so a killed run still
    leaves usable data (`AL-407`). A comparison that could read only the former
    would be unable to use exactly the runs this environment tends to produce.

    Args:
        path: A ``verdicts.json`` payload or a ``journal.jsonl`` file.

    Returns:
        list[dict[str, object]]: The scored records, errored ones excluded.

    Raises:
        SystemExit: If the file cannot be read or carries no usable record.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        print(f"could not read {path}: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    records: list[dict[str, object]] = []
    if path.suffix == ".jsonl":
        records.extend(json.loads(line) for line in text.splitlines() if line.strip())
    else:
        payload = json.loads(text)
        verdicts = payload.get("verdicts") if isinstance(payload, dict) else payload
        if isinstance(verdicts, dict):
            records = list(verdicts.values())
        else:
            records = list(verdicts or [])

    usable = [
        r for r in records if not r.get("error") and isinstance(r.get("scores"), dict)
    ]
    if not usable:
        print(f"{path} carries no scored record", file=sys.stderr)
        raise SystemExit(2)
    return usable


def _key(record: dict[str, object]) -> tuple[str, str]:
    """Return the ``(judge, arm)`` identity a record is matched on.

    Args:
        record: One scored record.

    Returns:
        tuple[str, str]: The judge label and the arm (book plus defect) name.
    """
    return (str(record.get("judge", "")), str(record.get("leg", "")))


def matched_pairs(
    first: list[dict[str, object]], second: list[dict[str, object]]
) -> list[tuple[str, str, dict[str, float], dict[str, float]]]:
    """Pair records that two runs scored identically-named.

    Args:
        first: Records from the earlier run.
        second: Records from the later run.

    Returns:
        list: One ``(judge, arm, first_scores, second_scores)`` per pair
        present in both runs, in sorted arm order.
    """
    left = {_key(r): r for r in first}
    right = {_key(r): r for r in second}
    pairs: list[tuple[str, str, dict[str, float], dict[str, float]]] = []
    for key in sorted(left.keys() & right.keys(), key=lambda k: (k[1], k[0])):
        a = left[key]["scores"]
        b = right[key]["scores"]
        if isinstance(a, dict) and isinstance(b, dict):
            pairs.append((key[0], key[1], a, b))  # pyright: ignore[reportArgumentType]
    return pairs


def _deltas_for(
    pairs: Sequence[tuple[str, str, dict[str, float], dict[str, float]]],
    criterion: str,
) -> list[float]:
    """Return the signed run-to-run change for one criterion.

    Args:
        pairs: Matched scorings.
        criterion: The criterion to read from each pair.

    Returns:
        list[float]: ``second - first`` per pair that scored the criterion.
    """
    out: list[float] = []
    for _judge, _arm, before, after in pairs:
        if criterion in before and criterion in after:
            out.append(float(after[criterion]) - float(before[criterion]))
    return out


def _is_control(arm: str) -> bool:
    """Return whether *arm* is a control (nothing seeded).

    Args:
        arm: The arm name, ``<book>__<defect>``.

    Returns:
        bool: True when the arm is the unmodified book.
    """
    return arm.rsplit("__", 1)[-1] == _CONTROL_ARM


def _summarize(deltas: Sequence[float]) -> str:
    """Format one row of spread statistics.

    Args:
        deltas: Signed run-to-run changes.

    Returns:
        str: A fixed-width summary, or a note when there is too little data.
    """
    if len(deltas) < _MIN_PAIRS:
        return f"n={len(deltas):<3} (under {_MIN_PAIRS}, not reported)"
    absolute = [abs(d) for d in deltas]
    over = sum(1 for d in absolute if d >= _DETECTION_MARGIN) / len(absolute)
    return (
        f"n={len(deltas):<3} mean |d| {statistics.mean(absolute):.3f}  "
        f"median {statistics.median(absolute):.3f}  "
        f"max {max(absolute):.3f}  "
        f"signed {statistics.mean(deltas):+.3f}  "
        f">=margin {over:.1%}"
    )


def _lines(
    pairs: Sequence[tuple[str, str, dict[str, float], dict[str, float]]],
) -> Iterator[str]:
    """Yield the body of the report.

    Args:
        pairs: Matched scorings across the two runs.

    Yields:
        str: One line at a time.
    """
    controls = [p for p in pairs if _is_control(p[1])]
    defects = [p for p in pairs if not _is_control(p[1])]
    judges = sorted({judge for judge, _, _, _ in pairs})

    yield f"Matched (judge, arm) pairs: {len(pairs)}"
    yield f"  control arms: {len(controls)}   defect arms: {len(defects)}"
    yield f"  judges: {', '.join(judges)}"
    yield ""
    yield f"Detection margin: {_DETECTION_MARGIN}"
    yield ""

    yield "UW-C258: per-criterion run-to-run spread, ALL arms"
    yield "-" * 66
    for criterion in _CRITERIA:
        yield f"  {criterion:<16} {_summarize(_deltas_for(pairs, criterion))}"

    yield ""
    yield "UW-C255: the same spread on CONTROL arms only, where movement is"
    yield "         unambiguously noise rather than collateral detection"
    yield "-" * 66
    for criterion in _CRITERIA:
        yield f"  {criterion:<16} {_summarize(_deltas_for(controls, criterion))}"

    yield ""
    yield "Per judge, pooled across criteria"
    yield "-" * 66
    for judge in judges:
        subset = [p for p in pairs if p[0] == judge]
        pooled = [d for c in _CRITERIA for d in _deltas_for(subset, c)]
        yield f"  {judge:<20} {_summarize(pooled)}"

    yield ""
    yield "Per judge, control arms only"
    yield "-" * 66
    for judge in judges:
        subset = [p for p in controls if p[0] == judge]
        pooled = [d for c in _CRITERIA for d in _deltas_for(subset, c)]
        yield f"  {judge:<20} {_summarize(pooled)}"


def report(first: list[dict[str, object]], second: list[dict[str, object]]) -> str:
    """Return the full run-to-run report.

    Args:
        first: Records from the earlier run.
        second: Records from the later run.

    Returns:
        str: The formatted report.
    """
    pairs = matched_pairs(first, second)
    if not pairs:
        return "No (judge, arm) pair appears in both runs; nothing to compare."
    header = [
        "W7 run-to-run variation, per criterion (UW-C258, UW-C255)",
        "=" * 66,
        "",
    ]
    return "\n".join([*header, *_lines(pairs)])


def main(argv: Sequence[str] | None = None) -> int:
    """Load two runs and print the comparison.

    Args:
        argv: Argument vector, or ``None`` for ``sys.argv``.

    Returns:
        int: ``0`` on success.
    """
    parser = argparse.ArgumentParser(description="W7 run-to-run spread")
    parser.add_argument("--first", type=Path, required=True)
    parser.add_argument("--second", type=Path, required=True)
    args = parser.parse_args(argv)

    print(report(load_records(args.first), load_records(args.second)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
