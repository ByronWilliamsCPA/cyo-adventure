"""Enforce cross-binding device-kind diversity over sibling story bibles.

Usage:
    uv run python scripts/check_bible_diversity.py <bible.json> <bible.json>...
        [--tau T] [--check]

B-plus amendment 1 (AL-158/UW-C95): the first pilot's clue margin failed
because two of three bibles were authored with the same device-kind multiset
per category, so the pair collapsed to noun-swap at fill time. Device
distinctness must be enforced where devices are chosen. For every pair of
sibling bibles this computes Mechanic Divergence:

    MD(pair) = 1 - mean over device categories of
               Jaccard(kind multiset A, kind multiset B)

and flags pairs below ``--tau`` (default 0.34: with three-entry categories,
sharing at most two of three kinds passes, an identical kind multiset fails).
Additionally, two entries sharing (category, kind) whose texts overlap
heavily (token Jaccard above 0.5) are flagged as near-noun-swaps (warning).

Calibration anchor: the first pilot's three bibles score MD 0.0 on the
clue-channel category (identical kind multisets), exactly the failure the
scene rater found downstream.
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

_WORD_RE = re.compile(r"[\w']+", re.UNICODE)

# Above this token Jaccard, two same-kind entries read as one device with a
# different noun (the AL-158 noun-swap failure).
_NOUN_SWAP_JACCARD = 0.5


def _kind_multisets(bible: dict[str, Any]) -> dict[str, Counter[str]]:
    vocab = cast("dict[str, Any]", bible.get("device_vocabulary") or {})
    result: dict[str, Counter[str]] = {}
    for category, entries in vocab.items():
        result[category] = Counter(
            str(cast("dict[str, Any]", entry).get("kind"))
            for entry in cast("list[Any]", entries)
            if isinstance(entry, dict)
        )
    return result


def _jaccard_multiset(a: Counter[str], b: Counter[str]) -> float:
    union = sum((a | b).values())
    if union == 0:
        # Two empty multisets are identical, not disjoint. Returning 0.0 here
        # credited 1.0 of divergence for a category with no content, which
        # inflated MD and could mask a real breach below tau.
        return 1.0
    return sum((a & b).values()) / union


def mechanic_divergence(bible_a: dict[str, Any], bible_b: dict[str, Any]) -> float:
    """Return MD in [0, 1]: 0 = identical kind profile, 1 = fully disjoint."""
    kinds_a = _kind_multisets(bible_a)
    kinds_b = _kind_multisets(bible_b)
    categories = sorted(set(kinds_a) | set(kinds_b))
    if not categories:
        return 0.0
    overlaps = [
        _jaccard_multiset(
            kinds_a.get(category, Counter()), kinds_b.get(category, Counter())
        )
        for category in categories
    ]
    return 1.0 - sum(overlaps) / len(overlaps)


def near_noun_swaps(
    bible_a: dict[str, Any], bible_b: dict[str, Any]
) -> list[tuple[str, str, str]]:
    """Return (category, text_a, text_b) for same-kind entries with heavy overlap."""
    vocab_a = cast("dict[str, Any]", bible_a.get("device_vocabulary") or {})
    vocab_b = cast("dict[str, Any]", bible_b.get("device_vocabulary") or {})
    swaps: list[tuple[str, str, str]] = []
    for category in set(vocab_a) & set(vocab_b):
        for entry_a in cast("list[Any]", vocab_a[category]):
            for entry_b in cast("list[Any]", vocab_b[category]):
                if not (isinstance(entry_a, dict) and isinstance(entry_b, dict)):
                    continue
                ea = cast("dict[str, Any]", entry_a)
                eb = cast("dict[str, Any]", entry_b)
                if ea.get("kind") != eb.get("kind"):
                    continue
                tokens_a = set(_WORD_RE.findall(str(ea.get("text", "")).lower()))
                tokens_b = set(_WORD_RE.findall(str(eb.get("text", "")).lower()))
                if not tokens_a or not tokens_b:
                    continue
                jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
                if jaccard > _NOUN_SWAP_JACCARD:
                    swaps.append((category, str(ea.get("text")), str(eb.get("text"))))
    return swaps


def _load_json_object(path: str) -> dict[str, Any] | None:
    """Load a JSON object from path, or report and return None.

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


def main(argv: list[str] | None = None) -> int:
    """CLI entry point; exit 1 with --check when any pair sits below tau."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bibles", nargs="+", help="Two or more sibling bible paths.")
    parser.add_argument("--tau", type=float, default=0.34)
    parser.add_argument(
        "--contract",
        default=None,
        help=(
            "Narrative contract path: reports per-category kind headroom, "
            "marking kinds frozen by kind_must_be specs (AL-160)."
        ),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if len(args.bibles) < 2:
        sys.stderr.write("need at least two bibles\n")
        return 2
    if len(set(args.bibles)) != len(args.bibles):
        dupes = sorted({p for p in args.bibles if args.bibles.count(p) > 1})
        sys.stderr.write(f"error: duplicate bible path(s): {', '.join(dupes)}\n")
        return 2
    if not 0.0 <= args.tau <= 1.0:
        sys.stderr.write(f"error: --tau must be within [0.0, 1.0], got {args.tau}\n")
        return 2
    loaded: dict[str, dict[str, Any]] = {}
    for path in args.bibles:
        bible = _load_json_object(path)
        if bible is None:
            return 2
        loaded[path] = bible
    if args.contract:
        contract = _load_json_object(args.contract)
        if contract is None:
            return 2
        forced: dict[str, set[str]] = {}
        for entry in cast("dict[str, Any]", contract.get("nodes") or {}).values():
            for spec in cast(
                "dict[str, Any]", cast("dict[str, Any]", entry).get("invention") or {}
            ).values():
                spec_map = cast("dict[str, Any]", spec)
                category = spec_map.get("category")
                must = spec_map.get("kind_must_be")
                if category and must:
                    forced.setdefault(str(category), set()).add(str(must))
        sys.stdout.write("per-category kind headroom (forced kinds cannot diverge):\n")
        # Union the category set across every loaded bible: deriving it from
        # only the first bible (``next(iter(loaded.values()))``) silently
        # dropped any category that first appears in a later sibling, making
        # --contract report a falsely-clean table for it.
        aggregate_kinds: dict[str, Counter[str]] = {}
        for bible in loaded.values():
            for category, counter in _kind_multisets(bible).items():
                aggregate_kinds.setdefault(category, Counter()).update(counter)
        for category, kinds in sorted(aggregate_kinds.items()):
            frozen = sorted(forced.get(category, set()))
            free = sum(
                c for k, c in kinds.items() if k not in forced.get(category, set())
            )
            sys.stdout.write(
                f"  {category}: {sum(kinds.values())} entries, forced kinds "
                f"{frozen or 'none'}, free entries {free}\n"
            )
    breaches = 0
    for (path_a, bible_a), (path_b, bible_b) in combinations(loaded.items(), 2):
        divergence = mechanic_divergence(bible_a, bible_b)
        marker = "FAIL" if divergence < args.tau else "ok  "
        if divergence < args.tau:
            breaches += 1
        sys.stdout.write(
            f"{marker} MD={divergence:.3f}  {Path(path_a).name} vs {Path(path_b).name}"
            f" (tau {args.tau})\n"
        )
        for category, text_a, text_b in near_noun_swaps(bible_a, bible_b):
            sys.stdout.write(
                f"     WARNING near-noun-swap [{category}]: {text_a!r} ~ {text_b!r}\n"
            )
    if args.check and breaches:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
