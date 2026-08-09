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
words, and reports every gram appearing in two or more sibling fills.
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
import re
import sys
from collections import Counter
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
