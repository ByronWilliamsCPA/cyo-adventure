"""Flag verbatim convergence across sibling fills of one skeleton.

Usage:
    uv run python scripts/check_sibling_fills.py <filled.json> <filled.json>...
        [--max-shared-per-1000 N] [--check]

B-plus amendment 3 (AL-156/UW-C93): the first pilot's raters found the
dominant residual recognition leaks are ritual phrases repeated across
sibling fills ("Team time", "One, two, three, reach it together", "boing
boing"), and that isolated free authors converge on near-verbatim beats.
Pairwise device margins and lexical gates cannot see this; a
sibling-scoped n-gram check can.

Deterministic: normalizes bodies plus choice labels (lowercase, punctuation
stripped), extracts word 4-grams, drops grams made entirely of function
words, and reports every gram appearing in two or more sibling fills. The
tokenizer, stop list and gram extraction live in
``cyo_adventure.diversity.grams`` and are shared with the request-path
advisory, so the calibration figures below keep describing the running code.
With ``--check``, exits 1 when the count of distinct shared grams per 1000
mean leaf words exceeds ``--max-shared-per-1000`` (default 4.0). The budget
is length-normalized because a fixed count cannot serve both an 11-node and
a 26-node fill (AL-159). Calibration: the first pilot's obligation arm
scores 2.8 per 1000, its control arm 25, its free arm 12.6, and the
clocktower pilot 9.0.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any, cast

from cyo_adventure.diversity.grams import (
    STOPWORDS as _STOPWORDS,
)
from cyo_adventure.diversity.grams import (
    content_grams,
    pairwise_overlap,
    story_text,
    tokenize,
)


def _load(path: str) -> dict[str, Any] | None:
    """Load a filled-story JSON object, or report and return None.

    Args:
        path: File path to read.

    Returns:
        The decoded object, or None on any load failure.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot load {path}: {exc}\n")
        return None
    if not isinstance(data, dict):
        sys.stderr.write(f"error: expected a JSON object in {path}\n")
        return None
    return cast("dict[str, Any]", data)


def _leaf_text(story: dict[str, Any]) -> str:
    """Return the whole recognition surface: node bodies plus choice labels.

    Labels are included here and excluded on the request path. This tool asks
    what a reader could recognize across two books, and a reader reads the
    menu; ``moderation/leaf_diversity.py`` asks how much of the FILL was
    reused, and the labels are the skeleton's, identical in every sibling by
    construction.
    """
    return story_text(story, include_choice_labels=True)


def _grams(text: str, n: int = 4) -> frozenset[tuple[str, ...]]:
    """Return the distinct content-bearing ``n``-grams in ``text``."""
    return content_grams(text, n)


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
    #ASSUME: tooling: this helper is **not wired into main()** and nothing gates
    on it. An earlier docstring claimed main() gated --check on the highest-rate
    pair via --max-pair-shared-per-1000; no such flag exists and main() never
    calls this. It is used from analysis scripts that import it directly, and a
    reader calibrating against it should know no gate depends on it.
    #VERIFY: grep for the flag name before believing any claim that it gates.
    """
    pairs: list[tuple[int, int, int, float]] = []
    for i, j in combinations(range(len(stories)), 2):
        overlap = pairwise_overlap(
            stories[i], stories[j], include_choice_labels=True, n=n
        )
        pairs.append((i, j, overlap.shared, overlap.per_1000))
    return pairs


def ranked_shared(
    shared: Counter[tuple[str, ...]], limit: int
) -> list[tuple[tuple[str, ...], int]]:
    """Return the ``limit`` most-shared grams, ties broken by the gram itself.

    ``Counter.most_common`` is insertion-stable for ties, and ``shared_grams``
    inserts by iterating per-fill gram sets, whose order is hash-randomized per
    process. Left alone, the printed evidence list therefore reorders between
    two runs over identical input while the gate number stays fixed, which
    reads as churn in the fills. Sorting on (-count, gram) makes the report a
    function of its input.

    Args:
        shared: gram -> number of sibling fills containing it.
        limit: How many rows to return.

    Returns:
        The highest-count grams first, alphabetical within a count.
    """
    return sorted(shared.items(), key=lambda item: (-item[1], item[0]))[:limit]


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
                    for w in tokenize(str(choice.get("label", "")))
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
    """CLI entry point.

    Returns:
        Exit code: 2 when fewer than two fills are given or a fill cannot
        be read, 1 when ``--check`` is set and the shared-gram budget is
        exceeded, 0 otherwise.
    """
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
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if len(args.fills) < 2:
        sys.stderr.write("need at least two fills\n")
        return 2
    stories: list[dict[str, Any]] = []
    for p in args.fills:
        story = _load(p)
        if story is None:
            return 2
        stories.append(story)
    shared = shared_grams(stories)
    mean_words = sum(len(tokenize(_leaf_text(story))) for story in stories) / len(
        stories
    )
    per_1000 = len(shared) / max(mean_words, 1.0) * 1000.0
    budget = args.max_shared_per_1000
    sys.stdout.write(
        f"shared 4-grams across {len(stories)} fills: {len(shared)} "
        f"({per_1000:.1f} per 1000 mean leaf words; budget {budget})\n"
    )
    for gram, count in ranked_shared(shared, 15):
        sys.stdout.write(f"  x{count}  {' '.join(gram)}\n")
    frames = menu_frame_overlap(stories)
    sys.stdout.write(
        f"menu frames shared by 2+ fills (same node, same choice position, "
        f"same opening words): {len(frames)}\n"
    )
    for node_id, index, frame in frames[:10]:
        sys.stdout.write(f"  {node_id}[{index}]: {' '.join(frame)}\n")
    if args.check and per_1000 > budget:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
