"""Flag verbatim convergence across sibling fills of one skeleton.

Usage:
    uv run python scripts/check_sibling_fills.py <filled.json> <filled.json>...
        [--max-shared N] [--check]

B-plus amendment 3 (AL-156/UW-C93): the first pilot's raters found the
dominant residual recognition leaks are ritual phrases repeated across
sibling fills ("Team time", "One, two, three, reach it together", "boing
boing"), and that isolated free authors converge on near-verbatim beats.
Pairwise device margins and lexical gates cannot see this; a
sibling-scoped n-gram check can.

Deterministic: normalizes bodies plus choice labels (lowercase, punctuation
stripped), extracts word 4-grams, drops grams made entirely of function
words, and reports every gram appearing in two or more sibling fills.
With ``--check``, exits 1 when the count of distinct shared grams exceeds
``--max-shared`` (default 8; the first pilot's control arm shares 40+,
its free arm 15+, and genuinely independent texts stay in single digits).

Worst-unit reporting (2026-08-10 external review): a global per-1000 rate
averages the whole sibling set together, and with more than two fills that
average can hide one badly-converged pair inside several clean ones. This
script now also computes, for every pair of fills, the shared-gram count and
rate restricted to just that pair, and gates ``--check`` on the worst
(highest-rate) pair via ``--max-pair-shared-per-1000`` whenever more than two
fills are given. It also tallies which node contributes the most shared
grams, so a reviewer is pointed at a location, not only a number.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any, cast

_WORD_RE = re.compile(r"[a-z']+")
_STOPWORDS = frozenset(
    "a an and are as at be but by for from had has he her his i in is it its "
    "of on she so that the their them they this to was were will with you your "
    "not no one out up down all what says said".split()
)


def _leaf_text(story: dict[str, Any]) -> str:
    parts: list[str] = []
    for node in cast("list[dict[str, Any]]", story.get("nodes") or []):
        parts.append(str(node.get("body", "")))
        parts.extend(
            str(c.get("label", ""))
            for c in cast("list[dict[str, Any]]", node.get("choices") or [])
        )
    return " ".join(parts)


def _grams(text: str, n: int = 4) -> set[tuple[str, ...]]:
    words = _WORD_RE.findall(text.lower())
    grams: set[tuple[str, ...]] = set()
    for i in range(len(words) - n + 1):
        gram = tuple(words[i : i + n])
        if all(word in _STOPWORDS for word in gram):
            continue
        grams.add(gram)
    return grams


def shared_grams(stories: list[dict[str, Any]], n: int = 4) -> Counter[tuple[str, ...]]:
    """Return gram -> number of sibling fills containing it (only counts >= 2)."""
    per_story = [_grams(_leaf_text(story), n) for story in stories]
    counts: Counter[tuple[str, ...]] = Counter()
    for grams in per_story:
        for gram in grams:
            counts[gram] += 1
    return Counter({gram: c for gram, c in counts.items() if c >= 2})


def pairwise_shared_grams(
    stories: list[dict[str, Any]], n: int = 4
) -> list[tuple[int, int, int, float]]:
    """Return (i, j, shared_count, per_1000) for every pair of sibling fills.

    #ASSUME: data-integrity: a pairwise intersection is computed directly
    between two fills' gram sets, independent of how many other siblings are
    present. This is deliberate: the global ``shared_grams`` rate is diluted
    by the mean word count of the *whole* set, so two fills that converge
    heavily on their own can still clear the aggregate budget once several
    clean fills are averaged in. The worst pair below is immune to that
    dilution because its denominator is only the two fills involved.
    #VERIFY: main() gates --check on the highest-rate pair here (via
    --max-pair-shared-per-1000) whenever more than two fills are supplied.
    """
    grams = [_grams(_leaf_text(story), n) for story in stories]
    words = [len(_WORD_RE.findall(_leaf_text(story).lower())) for story in stories]
    pairs: list[tuple[int, int, int, float]] = []
    for i, j in combinations(range(len(stories)), 2):
        count = len(grams[i] & grams[j])
        mean_words = (words[i] + words[j]) / 2.0
        rate = count / max(mean_words, 1.0) * 1000.0
        pairs.append((i, j, count, rate))
    return pairs


def node_gram_concentration(
    stories: list[dict[str, Any]], shared: Counter[tuple[str, ...]], n: int = 4
) -> Counter[str]:
    """Tally, per node id, how many globally-shared grams that node contains.

    A shared gram counted once at the aggregate level may in practice live
    entirely inside one or two nodes; this points a reviewer at the node or
    region carrying the recognition risk instead of leaving them to search
    the whole book for a rate.

    Args:
        stories: Decoded sibling fills.
        shared: The output of ``shared_grams`` for the same fills.
        n: Gram length, matched to ``shared``.

    Returns:
        node id -> number of (story, node) occurrences of a shared gram.
        A gram repeated in the same node across several fills counts once
        per fill, so a node that is the recurring source of the leak scores
        higher than one that merely echoes it once.
    """
    shared_set = set(shared)
    tally: Counter[str] = Counter()
    for story in stories:
        for node in cast("list[dict[str, Any]]", story.get("nodes") or []):
            node_id = str(node.get("id", "?"))
            parts = [str(node.get("body", ""))]
            parts.extend(
                str(c.get("label", ""))
                for c in cast("list[dict[str, Any]]", node.get("choices") or [])
            )
            node_grams = _grams(" ".join(parts), n)
            hit = len(node_grams & shared_set)
            if hit:
                tally[node_id] += hit
    return tally


def menu_frame_overlap(
    stories: list[dict[str, Any]],
) -> list[tuple[str, int, tuple[str, ...]]]:
    """Return (node, choice index, frame) where 2+ fills share a label frame.

    A frame is the first two content-bearing words of a choice label at the
    same node and position; shared frames are the menu-surface recognition
    channel AL-161 identified (verdict landed on a menu at node 2).
    """
    seen: dict[tuple[str, int, tuple[str, ...]], int] = {}
    for story in stories:
        for node in cast("list[dict[str, Any]]", story.get("nodes") or []):
            for index, choice in enumerate(
                cast("list[dict[str, Any]]", node.get("choices") or [])
            ):
                words = [
                    w
                    for w in _WORD_RE.findall(str(choice.get("label", "")).lower())
                    if w not in _STOPWORDS
                ]
                if len(words) < 2:
                    continue
                key = (str(node.get("id")), index, tuple(words[:2]))
                seen[key] = seen.get(key, 0) + 1
    return sorted(
        [(n, i, f) for (n, i, f), c in seen.items() if c >= 2],
        key=lambda item: (item[0], item[1]),
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; exit 1 with --check above the shared-gram budget."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fills", nargs="+", help="Two or more sibling filled stories.")
    parser.add_argument(
        "--max-shared-per-1000",
        type=float,
        default=4.0,
        help=(
            "Shared-gram budget per 1000 mean leaf words (AL-159: a fixed "
            "budget cannot serve both an 11-node and a 26-node fill; "
            "calibration: first-pilot obligation arm 2.8, control arm 25, "
            "free arm 12.6, clocktower pilot 9.0 per 1000)."
        ),
    )
    parser.add_argument(
        "--max-pair-shared-per-1000",
        type=float,
        default=4.0,
        help=(
            "Worst-pair budget (default 4.0, matching --max-shared-per-1000: "
            "for exactly two fills the two metrics are identical, so this "
            "flag changes nothing for the common two-fill case). Applies "
            "only when more than two fills are given, since a global rate "
            "averaged over several siblings can pass while one specific "
            "pair has converged heavily; this catches that pair directly."
        ),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if len(args.fills) < 2:
        sys.stderr.write("need at least two fills\n")
        return 2
    stories = [
        cast("dict[str, Any]", json.loads(Path(p).read_text(encoding="utf-8")))
        for p in args.fills
    ]
    shared = shared_grams(stories)
    mean_words = sum(
        len(_WORD_RE.findall(_leaf_text(story).lower())) for story in stories
    ) / len(stories)
    per_1000 = len(shared) / max(mean_words, 1.0) * 1000.0
    budget = args.max_shared_per_1000
    sys.stdout.write(
        f"shared 4-grams across {len(stories)} fills: {len(shared)} "
        f"({per_1000:.1f} per 1000 mean leaf words; budget {budget})\n"
    )
    for gram, count in shared.most_common(15):
        sys.stdout.write(f"  x{count}  {' '.join(gram)}\n")

    concentration = node_gram_concentration(stories, shared)
    if concentration:
        sys.stdout.write("most concentrated nodes (shared-gram occurrences):\n")
        for node_id, count in concentration.most_common(5):
            sys.stdout.write(f"  {node_id}: {count}\n")

    pair_budget = args.max_pair_shared_per_1000
    worst_pair_rate = 0.0
    worst_pair_desc = ""
    if len(stories) > 2:
        pairs = pairwise_shared_grams(stories)
        worst_i, worst_j, worst_count, worst_pair_rate = max(
            pairs, key=lambda pair: pair[3]
        )
        worst_pair_desc = f"{args.fills[worst_i]} vs {args.fills[worst_j]}"
        sys.stdout.write(
            f"worst pair: {worst_pair_desc}: {worst_count} shared grams "
            f"({worst_pair_rate:.1f} per 1000; budget {pair_budget})\n"
        )

    failures: list[str] = []
    if per_1000 > budget:
        failures.append(f"aggregate rate {per_1000:.1f} per 1000 > budget {budget}")
    if worst_pair_desc and worst_pair_rate > pair_budget:
        failures.append(
            f"worst pair ({worst_pair_desc}) rate {worst_pair_rate:.1f} per "
            f"1000 > budget {pair_budget}"
        )
    if failures:
        for failure in failures:
            sys.stderr.write(f"FAIL: {failure}\n")

    frames = menu_frame_overlap(stories)
    sys.stdout.write(
        f"menu frames shared by 2+ fills (same node, same choice position, "
        f"same opening words): {len(frames)}\n"
    )
    for node_id, index, frame in frames[:10]:
        sys.stdout.write(f"  {node_id}[{index}]: {' '.join(frame)}\n")
    if args.check and failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
