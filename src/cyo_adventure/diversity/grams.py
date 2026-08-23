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

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Mapping

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
    raising, because this feeds an advisory that is fail-open by contract and
    must never be the thing that breaks a fill.
    #VERIFY: tests/unit/test_diversity_grams.py::test_pairwise_overlap_survives_an_empty_story

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

Fifteen is roughly twice the highest run any unrelated pair of the committed
corpus produces (measured 2026-08-23: 4 to 8 words across six control pairs),
so ordinary English cannot reach it by chance, and it is far below the 98-word
run of the brass-lantern series pair. Its purpose is to let a deliberate
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


def _kgrams(words: list[str], k: int) -> set[tuple[str, ...]]:
    """Return every contiguous ``k``-word window of ``words``."""
    return {tuple(words[i : i + k]) for i in range(len(words) - k + 1)}


def _longest_shared_run(left: list[str], right: list[str]) -> int:
    """Return the longest contiguous word run present in both token lists.

    Doubling search then bisection, so the cost tracks the answer rather than
    the input: two unrelated fills settle in a handful of set builds because
    they stop sharing runs almost immediately.

    Args:
        left: One fill's tokens.
        right: The other fill's tokens.

    Returns:
        The run length in words; ``0`` when the two share no word at all.
    """
    limit = min(len(left), len(right))
    if limit == 0 or not _kgrams(left, 1) & _kgrams(right, 1):
        return 0
    low, probe = 1, 2
    while probe <= limit and _kgrams(left, probe) & _kgrams(right, probe):
        low = probe
        probe *= 2
    high = min(probe, limit + 1)
    while low + 1 < high:
        mid = (low + high) // 2
        if _kgrams(left, mid) & _kgrams(right, mid):
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
