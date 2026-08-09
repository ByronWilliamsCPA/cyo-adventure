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


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; exit 1 with --check above the shared-gram budget."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fills", nargs="+", help="Two or more sibling filled stories.")
    parser.add_argument("--max-shared", type=int, default=8)
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
    sys.stdout.write(
        f"shared 4-grams across {len(stories)} fills: {len(shared)} "
        f"(budget {args.max_shared})\n"
    )
    for gram, count in shared.most_common(15):
        sys.stdout.write(f"  x{count}  {' '.join(gram)}\n")
    if args.check and len(shared) > args.max_shared:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
