"""Cross-fill n-gram overlap: the shared definition (R-3).

Two places need to answer "how much verbatim wording do these two fills
share": the request-path advisory in ``moderation/leaf_diversity.py`` and the
offline ``scripts/check_sibling_fills.py``. Two copies of a formula drift
silently, and the offline calibration figures (obligation arm 2.8 per 1000,
control 25, free 12.6, clocktower 9.0) stop describing the code that runs the
moment they do, so both route through this module.

**Choice labels are separable, and the request path must exclude them.**
A skeleton supplies its ``choices[].label`` strings to every sibling fill
unchanged: a fill rewrites node bodies, not the menu. Measured on the
2026-08-22 cave-of-echoes trio, byte-identical labels contributed 347 shared
grams, 66% to 74% of every pair's total, a near-constant floor set by the
skeleton rather than by either fill's prose. Including labels therefore
measures the tree; only ``include_choice_labels=False`` measures the fill.
The offline script keeps labels because its question is the whole recognition
surface a reader sees, which is a different question.

Pure module: stdlib only, in keeping with the rest of ``diversity``. Never
imports ``db``, ``generation``, or ``sqlalchemy``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

# The offline calibration figures were measured with exactly this tokenizer
# and this stop list, so a divergence silently invalidates them; the script
# that produced them now imports both from here rather than keeping copies.
_WORD_RE = re.compile(r"[a-z']+")
STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "had",
        "has",
        "he",
        "her",
        "his",
        "i",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "she",
        "so",
        "that",
        "the",
        "their",
        "them",
        "they",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
        "you",
        "your",
        "not",
        "no",
        "one",
        "out",
        "up",
        "down",
        "all",
        "what",
        "says",
        "said",
    ]
)

DEFAULT_GRAM_SIZE = 4
"""Word-gram width. Four is short enough to catch a ritual phrase and long
enough that ordinary English does not collide by chance (measured: unrelated
fills of different skeletons score a median 0.59 shared grams per 1000)."""


@dataclass(frozen=True, slots=True)
class GramOverlap:
    """Verbatim-wording overlap between exactly two fills.

    Attributes:
        shared: Distinct content grams present in both fills.
        mean_words: Mean word count of the two fills, the rate's denominator.
        per_1000: ``shared`` per 1000 mean words. Length-normalized because a
            fixed count cannot serve both an 11-node and a 551-node fill
            (AL-159).
    """

    shared: int
    mean_words: float
    per_1000: float

    def __post_init__(self) -> None:
        """Refuse a rate that does not follow from the two counts beside it.

        ``per_1000`` is derived, not independent, and every caller that reads
        it reads it INSTEAD of recomputing. A value that drifted from
        ``shared`` and ``mean_words`` would therefore be believed. Cheap to
        check here, impossible to notice downstream.

        Raises:
            ValueError: If any field is negative, or if ``per_1000`` does not
                agree with ``shared`` and ``mean_words``.
        """
        if self.shared < 0 or self.mean_words < 0 or self.per_1000 < 0:
            msg = (
                f"GramOverlap fields must be non-negative: shared={self.shared}, "
                f"mean_words={self.mean_words}, per_1000={self.per_1000}"
            )
            raise ValueError(msg)
        expected = self.shared / max(self.mean_words, 1.0) * 1000.0
        if not math.isclose(self.per_1000, expected, rel_tol=1e-9, abs_tol=1e-9):
            msg = (
                f"per_1000={self.per_1000} does not follow from shared="
                f"{self.shared} over mean_words={self.mean_words} "
                f"(expected {expected})"
            )
            raise ValueError(msg)


def tokenize(text: str) -> list[str]:
    """Return ``text``'s lowercase word tokens, the one shared tokenizer.

    Args:
        text: Raw prose.

    Returns:
        Lowercased word tokens; apostrophes are kept inside words, all other
        punctuation is dropped.
    """
    return _WORD_RE.findall(text.lower())


def content_grams(text: str, n: int = DEFAULT_GRAM_SIZE) -> frozenset[tuple[str, ...]]:
    """Return the distinct content-bearing word ``n``-grams in ``text``.

    A gram made entirely of function words is dropped: "and to the of" recurs
    in every English text and carries no recognition risk.

    Args:
        text: Raw prose; case and punctuation are normalized away.
        n: Gram width.

    Returns:
        The distinct qualifying grams, as word tuples.
    """
    words = tokenize(text)
    return frozenset(
        gram
        for gram in (tuple(words[i : i + n]) for i in range(len(words) - n + 1))
        if not all(word in STOPWORDS for word in gram)
    )


def story_text(story: Mapping[str, Any], *, include_choice_labels: bool) -> str:
    """Flatten a fill's prose into one string.

    #ASSUME: data-integrity: a story blob reaching this function may be
    malformed (a non-list ``nodes``, a node that is not a dict, a missing
    ``body``). Every such shape degrades to contributing no text rather than
    raising, because one consumer, the sibling-gram advisory in
    ``moderation/leaf_diversity.py``, is fail-open by contract and must never
    be the thing that breaks a fill. The OTHER consumer is not an advisory:
    ``validator/series.py``'s SR-10 is a ``Severity.ERROR`` that blocks
    approve-and-publish, and for it this degradation is fail-OPEN in effect,
    since a malformed-but-parseable book flattens to less text and can clear a
    bound it should have tripped. That is the accepted trade: SR-10 runs behind
    the schema validation in ``publishing/service.py::_series_chain_docs``,
    which returns ``None`` and skips the gate outright for a blob that does not
    parse, so the shapes guarded here are ones SR-10 never sees.
    #VERIFY: tests/unit/test_diversity_grams.py::test_story_text_degrades_malformed_shapes_to_no_text

    Args:
        story: A decoded fill.
        include_choice_labels: Include ``choices[].label`` text. False for
            fill-quality questions (labels come from the skeleton and are
            identical across siblings); True to reproduce the offline
            script's whole-recognition-surface measure.

    Returns:
        Body prose, plus choice labels when requested, space-joined.
    """
    raw_nodes = story.get("nodes")
    if not isinstance(raw_nodes, list):
        return ""
    parts: list[str] = []
    for raw_node in cast("list[object]", raw_nodes):
        if not isinstance(raw_node, dict):
            continue
        node = cast("dict[str, Any]", raw_node)
        parts.append(str(node.get("body", "")))
        if not include_choice_labels:
            continue
        raw_choices = node.get("choices")
        if not isinstance(raw_choices, list):
            continue
        parts.extend(
            str(cast("dict[str, Any]", choice).get("label", ""))
            for choice in cast("list[object]", raw_choices)
            if isinstance(choice, dict)
        )
    return " ".join(parts)


DEFAULT_MIN_RUN = 15
"""Words in a shared contiguous run before it counts toward coverage.

Fifteen is 1.87x the highest run any unrelated pair of the committed corpus
produces (measured 2026-08-23 over all 465 pairs: 2 to 8 words, median 5, a
single pair at 8), so ordinary English cannot reach it by chance, and it is
6.53x below the 98-word run of the brass-lantern series pair. Its purpose is to let a deliberate
refrain cost nothing: a phrase short enough to be a refrain never enters the
coverage total at all.
"""


@dataclass(frozen=True, slots=True)
class RunProfile:
    """Shared *contiguous* wording between two fills.

    A length measure, deliberately unlike :class:`GramOverlap`'s volume
    measure. Volume cannot separate one reused paragraph from many short
    deliberate echoes, because it only totals overlap; run length can, because
    a refrain is short by definition and a copied passage is not.

    Attributes:
        longest: Words in the longest contiguous run present in both fills.
        covered_words: Words of the more affected fill lying inside a run of
            at least ``min_run`` words.
        total_words: That same fill's word count, the coverage denominator.
        coverage: ``covered_words / total_words``, taken from whichever fill
            is worse affected. Not a mean: a mean would let a long book absorb
            a short one's entire text and still report a small number.
    """

    longest: int
    covered_words: int
    total_words: int
    coverage: float

    def __post_init__(self) -> None:
        """Refuse a coverage that is not the ratio of the two counts beside it.

        SR-10 blocks a publish on ``coverage``, so this is the one derived
        value in the module a wrong answer would be acted on. The docstring
        above warns that coverage must be the WORSE side and never a mean, and
        until this check nothing enforced that: a mean of the two sides is
        still a plausible-looking float, and it would silently under-report
        exactly the case the rule exists to catch. Tying the float to
        ``covered_words / total_words`` makes a mean unconstructible, because
        a mean does not divide either side's counts.

        Raises:
            ValueError: If any count is negative, if more words are covered
                than exist, or if ``coverage`` is not ``covered_words`` over
                ``total_words``.
        """
        if self.longest < 0 or self.covered_words < 0 or self.total_words < 0:
            msg = (
                f"RunProfile counts must be non-negative: longest={self.longest}, "
                f"covered_words={self.covered_words}, total_words={self.total_words}"
            )
            raise ValueError(msg)
        if self.covered_words > self.total_words:
            msg = (
                f"covered_words={self.covered_words} exceeds "
                f"total_words={self.total_words}"
            )
            raise ValueError(msg)
        expected = self.covered_words / max(self.total_words, 1)
        if not math.isclose(self.coverage, expected, rel_tol=1e-9, abs_tol=1e-9):
            msg = (
                f"coverage={self.coverage} is not covered_words="
                f"{self.covered_words} over total_words={self.total_words} "
                f"(expected {expected}); coverage is the worse side's ratio, "
                f"never a mean of the two sides"
            )
            raise ValueError(msg)


def _kgrams(words: list[str], k: int) -> set[tuple[str, ...]]:
    """Return every contiguous ``k``-word window of ``words``."""
    return {tuple(words[i : i + k]) for i in range(len(words) - k + 1)}


# Rabin-Karp parameters for the shared-run search. The modulus is the Mersenne
# prime 2**61 - 1, large enough that an accidental collision between two real
# passages is vanishingly unlikely; every candidate is still verified by slice
# comparison, so a collision can only cost time, never change the answer.
_RUN_HASH_MOD = (1 << 61) - 1
_RUN_HASH_BASE = 1_000_003


def _word_ids(left: list[str], right: list[str]) -> tuple[list[int], list[int]]:
    """Map both token lists onto one shared integer alphabet.

    Hashing integers rather than strings keeps the rolling update to a couple
    of arithmetic operations per position, independent of word length.

    Args:
        left: One fill's tokens.
        right: The other fill's tokens.

    Returns:
        The two token lists rewritten as ids, sharing one alphabet so that
        equal words compare equal across the pair. Ids start at 1, so a
        leading run of the same word cannot hash to the same value as a
        shorter one.
    """
    alphabet: dict[str, int] = {}
    return (
        [alphabet.setdefault(word, len(alphabet) + 1) for word in left],
        [alphabet.setdefault(word, len(alphabet) + 1) for word in right],
    )


@dataclass(frozen=True, slots=True)
class _RunPair:
    """Two fills' tokens with their shared-alphabet ids, prepared once.

    The four lists are always used together and are derived from each other,
    so they travel as one value: preparing the alphabet per probe would undo
    the point of the rolling hash, and passing them separately invites a
    caller to pair ``left`` with ``right_ids``.

    Attributes:
        left: One fill's tokens.
        right: The other fill's tokens.
        left_ids: ``left`` rewritten by :func:`_word_ids`.
        right_ids: ``right`` rewritten by :func:`_word_ids`.
    """

    left: list[str]
    right: list[str]
    left_ids: list[int]
    right_ids: list[int]


def _rolling_hashes(ids: list[int], k: int) -> Iterator[tuple[int, int]]:
    """Yield ``(start, hash)`` for every ``k``-wide window of ``ids``.

    One multiply-add-subtract per position regardless of ``k``, which is the
    whole reason the enclosing search is linear per probe rather than
    O(len * k).

    Args:
        ids: Tokens rewritten as integers by :func:`_word_ids`.
        k: Window width, assumed ``1 <= k <= len(ids)``.

    Yields:
        The window's start index and its rolling hash, in index order.
    """
    power = pow(_RUN_HASH_BASE, k, _RUN_HASH_MOD)
    rolling = 0
    for i, value in enumerate(ids):
        rolling = (rolling * _RUN_HASH_BASE + value) % _RUN_HASH_MOD
        if i >= k:
            rolling = (rolling - ids[i - k] * power) % _RUN_HASH_MOD
        if i >= k - 1:
            yield i - k + 1, rolling


def _shares_run(pair: _RunPair, k: int) -> bool:
    """Report whether both token lists contain some identical ``k``-word run.

    Rolling hash rather than materialized windows: building every ``k``-gram
    as a tuple costs O(len * k), which is what made the enclosing search
    quadratic when the shared run was long. Hashing costs O(len) whatever
    ``k`` is, and a window is only materialized when a hash actually collides,
    so a collision can cost time but can never change the answer.

    Args:
        pair: Both fills' tokens and ids.
        k: The run length to test.

    Returns:
        ``True`` when some ``k``-word window appears in both.
    """
    if k <= 0 or k > len(pair.left) or k > len(pair.right):
        return False

    buckets: dict[int, list[int]] = {}
    for start, value in _rolling_hashes(pair.left_ids, k):
        buckets.setdefault(value, []).append(start)

    for start, value in _rolling_hashes(pair.right_ids, k):
        candidates = buckets.get(value)
        if candidates is None:
            continue
        # Only reached on a hash hit, so the O(k) slice stays off the hot path.
        window = pair.right[start : start + k]
        if any(pair.left[c : c + k] == window for c in candidates):
            return True
    return False


def _longest_shared_run(left: list[str], right: list[str]) -> int:
    """Return the longest contiguous word run present in both token lists.

    Doubling search then bisection over :func:`_shares_run`, which is O(len)
    per probe, giving O(len log len) overall. Two unrelated fills still settle
    in a handful of probes because they stop sharing runs almost immediately.

    #ASSUME: timing dependencies: this runs synchronously inside
    ``publishing/service.py::approve``, which holds the storybook row under
    ``SELECT ... FOR UPDATE``, and ``validator/series.py`` calls it once per
    PAIR of books in the chain. Per-probe cost must therefore stay linear in
    the text length: an earlier version materialized every ``k``-gram as a
    tuple, which is O(len * k) and reached 3.8s for a single pair of
    8,000-word books sharing a half-length run, all of it inside the lock.
    #VERIFY: tests/unit/test_diversity_grams.py::
    test_a_long_shared_run_does_not_cost_quadratic_time

    Args:
        left: One fill's tokens.
        right: The other fill's tokens.

    Returns:
        The run length in words; ``0`` when the two share no word at all.
    """
    limit = min(len(left), len(right))
    if limit == 0:
        return 0
    left_ids, right_ids = _word_ids(left, right)
    pair = _RunPair(left=left, right=right, left_ids=left_ids, right_ids=right_ids)
    if not _shares_run(pair, 1):
        return 0
    low, probe = 1, 2
    while probe <= limit and _shares_run(pair, probe):
        low = probe
        probe *= 2
    high = min(probe, limit + 1)
    while low + 1 < high:
        mid = (low + high) // 2
        if _shares_run(pair, mid):
            low = mid
        else:
            high = mid
    return low


def _covered_words(words: list[str], other: list[str], k: int) -> int:
    """Return how many of ``words`` lie inside a ``k``-word run shared with ``other``.

    Args:
        words: The fill being measured.
        other: The fill compared against.
        k: Minimum run length; shorter echoes are not counted.

    Returns:
        The number of covered word positions, each counted once however many
        overlapping runs contain it.
    """
    if len(words) < k or len(other) < k:
        return 0
    shared = _kgrams(other, k)
    covered, reach = 0, -1
    for i in range(len(words) - k + 1):
        if tuple(words[i : i + k]) in shared:
            covered += (i + k) - max(i, reach + 1)
            reach = i + k - 1
    return covered


def shared_run_profile(
    text_a: str, text_b: str, *, min_run: int = DEFAULT_MIN_RUN
) -> RunProfile:
    """Measure the shared contiguous wording between two fills.

    Answers "did these two reuse a passage", where
    :func:`pairwise_overlap` answers "how much wording do they share in
    total". A series needs the first question: sharing a refrain on purpose is
    legitimate craft, and only the length measure can tell it from a copied
    paragraph.

    Args:
        text_a: One fill's prose.
        text_b: The other fill's prose.
        min_run: Run length at which coverage starts counting.

    Returns:
        RunProfile: The longest shared run and the worse side's coverage.
    """
    left, right = tokenize(text_a), tokenize(text_b)
    covered_left = _covered_words(left, right, min_run)
    covered_right = _covered_words(right, left, min_run)
    share_left = covered_left / max(len(left), 1)
    share_right = covered_right / max(len(right), 1)
    if share_right > share_left:
        covered, total, coverage = covered_right, len(right), share_right
    else:
        covered, total, coverage = covered_left, len(left), share_left
    return RunProfile(
        longest=_longest_shared_run(left, right),
        covered_words=covered,
        total_words=total,
        coverage=coverage,
    )


def pairwise_overlap(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    *,
    include_choice_labels: bool,
    n: int = DEFAULT_GRAM_SIZE,
) -> GramOverlap:
    """Measure verbatim-wording overlap between two fills.

    Pairwise rather than set-aggregate on purpose. The aggregate rate divides
    by the mean word count of a whole sibling set, so two fills that converge
    heavily on each other still clear the budget once several clean siblings
    are averaged in; a pair's own denominator is immune to that dilution. The
    request path only ever holds one new fill and one partner anyway.

    Args:
        first: One decoded fill.
        second: The other decoded fill.
        include_choice_labels: See :func:`story_text`.
        n: Gram width.

    Returns:
        GramOverlap: The shared count and its length-normalized rate.
    """
    text_a = story_text(first, include_choice_labels=include_choice_labels)
    text_b = story_text(second, include_choice_labels=include_choice_labels)
    shared = len(content_grams(text_a, n) & content_grams(text_b, n))
    words_a = len(tokenize(text_a))
    words_b = len(tokenize(text_b))
    mean_words = (words_a + words_b) / 2.0
    return GramOverlap(
        shared=shared,
        mean_words=mean_words,
        per_1000=shared / max(mean_words, 1.0) * 1000.0,
    )
