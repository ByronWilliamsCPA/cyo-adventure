"""Uncertainty arithmetic for any quantity this programme presents as a rank.

Part IV ranks suppliers on single-digit samples and reports each cell as a bare
mean. W5 of the measurement workplan calls that a correction rather than a
feature, and pre-commits to a consequence: **if every pair of intervals across
the slate overlaps, the ranking is retracted rather than caveated.** This module
is the arithmetic that decision rests on, kept free of any domain vocabulary so
the quality panel, the compliance table and anything added later share one
implementation and cannot drift apart.

Two guards carry most of the value here, and both are the same lesson `AL-338`
records about the path enumerator: a number computed from too little input must
say so rather than shrink quietly.

- An interval over fewer than :data:`_MIN_SAMPLES` observations is marked
  ``complete=False`` and its bounds are the point estimate. Resampling one
  observation returns that observation every time, so the honest report is "no
  interval", not a zero-width one that reads as certainty.
- A leg whose interval is incomplete is excluded from pair counting and named,
  rather than being silently treated as separated from everything.

Nothing here is random at run time: every resample draws from a seeded
generator, so two runs over the same input produce identical bounds.
"""

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

# Below this, resampling cannot produce variation and the interval is a fiction.
# #CRITICAL: data integrity: a zero-width interval printed beside a mean reads
# as a precise measurement, and this programme has already published one
# conclusion that a single book decided (AL-349). Two observations is the
# smallest sample from which a resample can differ from the original at all.
# #VERIFY: bootstrap_interval returns complete=False below this count and its
# bounds equal the point estimate; test_instrument.py asserts both.
_MIN_SAMPLES: Final[int] = 2

_DEFAULT_RESAMPLES: Final[int] = 2000
_DEFAULT_CONFIDENCE: Final[float] = 0.95

# Any fixed value works; this one is the date the module was written. It is a
# parameter rather than a constant at the call sites so a reviewer can re-run a
# published interval under a different seed and see the bounds move by less than
# the effect being claimed.
_DEFAULT_SEED: Final[int] = 20260813

__all__ = [
    "Interval",
    "SlateRanking",
    "bootstrap_interval",
    "rank_separation",
]


@dataclass(frozen=True, slots=True)
class Interval:
    """A point estimate with the uncertainty around it.

    Attributes:
        point: The mean of the observations.
        lo: Lower percentile bound, equal to ``point`` when incomplete.
        hi: Upper percentile bound, equal to ``point`` when incomplete.
        n: How many observations the interval was computed over.
        complete: Whether the sample was large enough for the bounds to mean
            anything. A ``False`` here must suppress the interval in any report,
            not merely annotate it.
    """

    point: float
    lo: float
    hi: float
    n: int
    complete: bool

    @property
    def width(self) -> float:
        """Return the distance between the bounds.

        Returns:
            ``hi - lo``, which is zero for an incomplete interval.
        """
        return self.hi - self.lo

    def overlaps(self, other: Interval) -> bool:
        """Return whether this interval and another share any value.

        Two incomplete intervals, or one incomplete and one complete, are not a
        comparison the caller should make; :func:`rank_separation` excludes
        those before pairing, and this method answers only about the bounds.

        Args:
            other: The interval to compare against.

        Returns:
            True when the closed intervals intersect.
        """
        return self.lo <= other.hi and other.lo <= self.hi


@dataclass(frozen=True, slots=True)
class SlateRanking:
    """What a slate of intervals does and does not establish about ordering.

    Attributes:
        ordered: Labels sorted by point estimate, best first. Includes every
            label, complete or not, because the ordering is still the thing
            being questioned.
        separated_pairs: Pairs of comparable labels whose intervals are
            disjoint.
        total_pairs: Pairs of comparable labels considered.
        excluded: Labels dropped for having no usable interval.
        supported: Whether any pair at all is separated. False is the
            pre-registered trigger to retract the ranking rather than caveat it.
        extremes_separated: Whether the best and worst comparable labels are
            themselves disjoint, which is the strongest single claim a slate
            this size can make.
    """

    ordered: tuple[str, ...]
    separated_pairs: int
    total_pairs: int
    excluded: tuple[str, ...]
    supported: bool
    extremes_separated: bool


def bootstrap_interval(
    values: Sequence[float],
    *,
    seed: int = _DEFAULT_SEED,
    resamples: int = _DEFAULT_RESAMPLES,
    confidence: float = _DEFAULT_CONFIDENCE,
) -> Interval:
    """Return a percentile bootstrap interval around the mean of ``values``.

    Args:
        values: The observations, one per independent unit. For a supplier leg
            that unit is a book, never a scoring: three judges grading one book
            are three opinions about one observation, and treating them as three
            observations would narrow the interval by a factor of the panel size
            for no added evidence.
        seed: Seed for the resampling generator, so bounds are reproducible.
        resamples: How many resamples to draw.
        confidence: Central mass the interval should cover, as a fraction.

    Returns:
        The interval, marked incomplete when ``values`` is too small.

    Raises:
        ValueError: If ``values`` is empty, or ``confidence`` is not strictly
            between 0 and 1, or ``resamples`` is not positive.
    """
    if not values:
        msg = "bootstrap_interval needs at least one observation"
        raise ValueError(msg)
    if not 0.0 < confidence < 1.0:
        msg = f"confidence must be strictly between 0 and 1, got {confidence}"
        raise ValueError(msg)
    if resamples <= 0:
        msg = f"resamples must be positive, got {resamples}"
        raise ValueError(msg)

    point = statistics.fmean(values)
    if len(values) < _MIN_SAMPLES:
        return Interval(point=point, lo=point, hi=point, n=len(values), complete=False)

    # #ASSUME: data integrity: a seeded Mersenne generator is the right tool
    # here because this is an offline analysis of our own measurements, not a
    # security context. Bandit's S311 is about unpredictability, which is the
    # opposite of what a reproducible interval wants.
    # #VERIFY: test_instrument.py asserts byte-identical bounds under a fixed
    # seed and different bounds under a different one.
    rng = random.Random(seed)
    means = sorted(
        statistics.fmean(rng.choices(values, k=len(values))) for _ in range(resamples)
    )
    tail = (1.0 - confidence) / 2.0
    lo_index = max(int(tail * resamples), 0)
    hi_index = min(int((1.0 - tail) * resamples), resamples - 1)
    return Interval(
        point=point,
        lo=means[lo_index],
        hi=means[hi_index],
        n=len(values),
        complete=True,
    )


def rank_separation(intervals: Mapping[str, Interval]) -> SlateRanking:
    """Report what a slate of intervals establishes about the ordering of labels.

    Args:
        intervals: Label to its interval.

    Returns:
        The ordering, how much of it is separated, and whether it is supported
        at all.
    """
    ordered = tuple(
        label for label, _ in sorted(intervals.items(), key=lambda kv: -kv[1].point)
    )
    comparable = {
        label: interval for label, interval in intervals.items() if interval.complete
    }
    excluded = tuple(sorted(set(intervals) - set(comparable)))

    labels = sorted(comparable, key=lambda label: -comparable[label].point)
    separated = 0
    total = 0
    for i, left in enumerate(labels):
        for right in labels[i + 1 :]:
            total += 1
            if not comparable[left].overlaps(comparable[right]):
                separated += 1

    extremes = bool(labels) and len(labels) > 1
    if extremes:
        extremes = not comparable[labels[0]].overlaps(comparable[labels[-1]])

    return SlateRanking(
        ordered=ordered,
        separated_pairs=separated,
        total_pairs=total,
        excluded=excluded,
        supported=separated > 0,
        extremes_separated=extremes,
    )
