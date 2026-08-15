"""Recompute W7's inter-judge agreement the way the design actually asks for it.

`AL-367` found the reported figures unusable and `UW-C251` schedules this. The
original method rounded each judge's mean **across all seven criteria** to an
integer and ran unweighted Cohen's kappa on the result. That does two harmful
things at once. It discards the per-criterion structure W7 exists to examine, so
a judge who tracks another closely on `imagery` and not at all on `voice` is
scored as one number. And it lands in the skewed-marginals regime where kappa
collapses regardless of raw agreement: `gpt-5.6` rounds into two categories with
24 of 31 books in one, `grok-4.6` into three with 23 of 31 in one. The published
+0.16, +0.58 and +0.14 therefore measure how differently spread each judge's
scale is, not whether the judges agree, and must not be quoted.

What this computes instead
--------------------------
Three things, per criterion, never pooled across criteria:

1. **Agreement on the change, not the level.** W7 is a paired design: every
   defect arm has a control arm of the same book. What the battery needs to know
   is whether two judges agree that a defect *moved* a criterion, and a judge who
   scores a whole point stricter than another agrees perfectly about the change
   while disagreeing about every absolute score. So the unit is the within-book
   delta, ``score(defect arm) - score(control arm)``, and Spearman's rho over
   those deltas is the headline.
2. **Quadratic-weighted kappa on the raw scores**, which is the ordinal-
   appropriate form: it charges a 4-versus-1 disagreement sixteen times what it
   charges a 4-versus-3, where the unweighted form charges both the same. Kept
   alongside rho because it answers the level question rho deliberately ignores.
3. **The marginal distribution per judge per criterion**, printed beside both,
   because a chance-corrected coefficient computed over skewed marginals is
   exactly the artefact that produced the retracted figures. A reader who can see
   the marginals can see when a low coefficient is a scale artefact.

Usage::

    uv run python scripts/w7_agreement.py --verdicts out/w7/verdicts.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

# The battery's seven judged criteria, in the order the rubric declares them so
# a report reads the same way every time.
_CRITERIA: Final[tuple[str, ...]] = (
    "age_fit",
    "imagery",
    "voice",
    "dialogue",
    "choice_quality",
    "ending_quality",
    "engagement",
)

# Below this many paired observations a correlation is not worth printing as a
# number. W7's thinnest arm (`dialogue_flat`) contributes 2 books, so this is a
# live case rather than a defensive one.
_MIN_PAIRS: Final[int] = 4

_CONTROL_ARM: Final[str] = "control"

# Kappa needs at least two distinct levels to have a scale to disagree on.
_MIN_LEVELS: Final[int] = 2


def spearman(first: Sequence[float], second: Sequence[float]) -> float | None:
    """Return Spearman's rank correlation, or ``None`` when it is undefined.

    Ties are handled by midranks, which matters here: a five-point rubric over a
    handful of books produces ties constantly, and the naive
    ``1 - 6*d^2/(n^3-n)`` shortcut is wrong the moment one appears.

    Args:
        first: One judge's values.
        second: The other judge's values, index-aligned with *first*.

    Returns:
        The correlation, or ``None`` when there are too few pairs or either
        judge gave the identical value throughout (zero variance, so no
        correlation exists to report).
    """
    if len(first) != len(second) or len(first) < _MIN_PAIRS:
        return None
    rank_first = _midranks(first)
    rank_second = _midranks(second)
    try:
        return statistics.correlation(rank_first, rank_second)
    except statistics.StatisticsError:
        return None


def _midranks(values: Sequence[float]) -> list[float]:
    """Return ranks for *values*, averaging over ties.

    Args:
        values: The observations.

    Returns:
        list[float]: One rank per observation, in the input's order.
    """
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while (
            end + 1 < len(order) and values[order[end + 1]] == values[order[position]]
        ):
            end += 1
        shared = (position + end) / 2 + 1
        for index in order[position : end + 1]:
            ranks[index] = shared
        position = end + 1
    return ranks


def quadratic_weighted_kappa(
    first: Sequence[float], second: Sequence[float]
) -> float | None:
    """Return quadratic-weighted Cohen's kappa over an ordinal scale.

    The weighting is the whole point. Unweighted kappa treats a 5-versus-1
    disagreement as identical to a 4-versus-3, which on a rubric scale is not a
    defensible model of how wrong a judge was, and it is what let the retracted
    figures collapse.

    Args:
        first: One judge's scores.
        second: The other judge's scores, index-aligned with *first*.

    Returns:
        The coefficient, or ``None`` when fewer than ``_MIN_PAIRS`` pairs exist
        or the expected disagreement is zero (both judges constant, where kappa
        is undefined rather than perfect).
    """
    if len(first) != len(second) or len(first) < _MIN_PAIRS:
        return None
    levels = sorted({*first, *second})
    if len(levels) < _MIN_LEVELS:
        return None
    index = {level: position for position, level in enumerate(levels)}
    size = len(levels)
    span = (size - 1) ** 2

    observed = 0.0
    for left, right in zip(first, second, strict=True):
        observed += (index[left] - index[right]) ** 2 / span

    left_counts = Counter(index[value] for value in first)
    right_counts = Counter(index[value] for value in second)
    total = len(first)
    expected = 0.0
    for left_level, left_count in left_counts.items():
        for right_level, right_count in right_counts.items():
            weight = (left_level - right_level) ** 2 / span
            expected += weight * left_count * right_count / total
    if expected == 0:
        return None
    return 1 - observed / expected


def _deltas(
    records: list[dict[str, object]], criterion: str
) -> dict[str, dict[str, float]]:
    """Return each judge's within-book delta per defect arm, for one criterion.

    Args:
        records: Every verdict record.
        criterion: The criterion to extract.

    Returns:
        dict[str, dict[str, float]]: Judge to leg to
        ``score(arm) - score(that book's control)``. Legs whose book has no
        control scored by that judge are omitted rather than imputed.
    """
    by_judge_leg: dict[str, dict[str, float]] = defaultdict(dict)
    for record in records:
        scores = record["scores"]
        if not isinstance(scores, dict) or criterion not in scores:
            continue
        by_judge_leg[str(record["judge"])][str(record["leg"])] = float(
            scores[criterion]
        )

    result: dict[str, dict[str, float]] = {}
    for judge, legs in by_judge_leg.items():
        controls = {
            leg.split("__")[0]: value
            for leg, value in legs.items()
            if leg.endswith(f"__{_CONTROL_ARM}")
        }
        result[judge] = {
            leg: value - controls[leg.split("__")[0]]
            for leg, value in legs.items()
            if not leg.endswith(f"__{_CONTROL_ARM}") and leg.split("__")[0] in controls
        }
    return result


def _raw(
    records: list[dict[str, object]], criterion: str
) -> dict[str, dict[str, float]]:
    """Return each judge's raw score per leg, for one criterion.

    Args:
        records: Every verdict record.
        criterion: The criterion to extract.

    Returns:
        dict[str, dict[str, float]]: Judge to leg to score.
    """
    result: dict[str, dict[str, float]] = defaultdict(dict)
    for record in records:
        scores = record["scores"]
        if isinstance(scores, dict) and criterion in scores:
            result[str(record["judge"])][str(record["leg"])] = float(scores[criterion])
    return result


def _paired(
    left: dict[str, float], right: dict[str, float]
) -> tuple[list[float], list[float]]:
    """Return the two judges' values over the legs they both scored.

    Args:
        left: One judge's leg-to-value mapping.
        right: The other judge's mapping.

    Returns:
        tuple[list[float], list[float]]: Index-aligned values, in sorted leg
        order so the pairing is reproducible.
    """
    shared = sorted(set(left) & set(right))
    return [left[leg] for leg in shared], [right[leg] for leg in shared]


def _marginal(values: Sequence[float]) -> str:
    """Render a judge's score distribution compactly.

    Args:
        values: The judge's scores.

    Returns:
        str: Counts per level, lowest first, so a reader can see skew at a
        glance and discount a chance-corrected number accordingly.
    """
    counts = Counter(values)
    return " ".join(f"{level:g}:{counts[level]}" for level in sorted(counts))


def report(records: list[dict[str, object]]) -> str:
    """Build the per-criterion agreement report.

    Args:
        records: Every verdict record.

    Returns:
        str: The rendered report.
    """
    judges = sorted({str(record["judge"]) for record in records})
    lines: list[str] = [
        f"judges: {', '.join(judges)}",
        f"records: {len(records)}",
        "",
        "Per criterion. rho is Spearman over WITHIN-BOOK DELTAS (agreement about",
        "what a defect did); qwk is quadratic-weighted kappa over RAW scores",
        "(agreement about level). Marginals are raw, and a low coefficient beside",
        "a one-sided marginal is a scale artefact, not a disagreement.",
        "",
    ]
    for criterion in _CRITERIA:
        deltas = _deltas(records, criterion)
        raws = _raw(records, criterion)
        lines.append(f"== {criterion}")
        for left, right in combinations(judges, 2):
            d_left, d_right = _paired(deltas.get(left, {}), deltas.get(right, {}))
            r_left, r_right = _paired(raws.get(left, {}), raws.get(right, {}))
            rho = spearman(d_left, d_right)
            qwk = quadratic_weighted_kappa(r_left, r_right)
            lines.append(
                f"   {left:18s} vs {right:18s} "
                f"rho {_fmt(rho):>7s} (n={len(d_left)})  qwk {_fmt(qwk):>7s}"
            )
        for judge in judges:
            values = list(raws.get(judge, {}).values())
            lines.append(f"   marginal {judge:18s} {_marginal(values)}")
        lines.append("")
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    """Render a coefficient, or say plainly that it is undefined.

    Args:
        value: The coefficient.

    Returns:
        str: The formatted value, or ``n/a`` where it does not exist. Never a
        zero standing in for a missing number.
    """
    return "n/a" if value is None else f"{value:+.2f}"


def main(argv: Sequence[str] | None = None) -> int:
    """Load verdicts and print the report.

    Args:
        argv: Argument vector, or ``None`` for ``sys.argv``.

    Returns:
        int: ``0`` on success, ``2`` when the verdict file is unusable.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verdicts", type=Path, default=Path("out/w7/verdicts.json"))
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.verdicts.read_text())
    except (OSError, ValueError) as error:
        print(f"could not read {args.verdicts}: {error}", file=sys.stderr)
        return 2

    verdicts = payload.get("verdicts")
    records = (
        list(verdicts.values()) if isinstance(verdicts, dict) else list(verdicts or [])
    )
    if not records:
        print(f"{args.verdicts} carries no verdicts", file=sys.stderr)
        return 2

    print(report(records))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
