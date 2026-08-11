"""Compare two books' bound devices for collision, across category boundaries.

Usage:
    uv run python scripts/check_device_collision.py <selection.json>
        <selection.json> [--max-text-jaccard 0.5] [--check]

The pre-fill screen for the failure mode where two books in a series share a
world *and* share the props inside it.

**What a selection is.** Before a fill, each book binds concrete props to
nodes: the one code the story is indexed by, the ways in, the hint each zone
carries, the jam remedy, the anti-taking safeguard, the hidden workshop's
signature, and the mechanism each ending turns on. A selection file maps node
id to slot to ``{"text": ..., "kind": ...}``, or to a plain string for the
ending mechanisms.

**Why this exists.** Sharing a world is the series contract and must never be
penalised: a child who notices they are back at the same lock-house is having
the intended experience. Sharing the *devices* is a different thing entirely,
and it reads to a reader as the same book. Measured: a treatment book bound 14
of 24 props byte-identically to its control, including the cipher, and two
blind raters reading in opposite orders both named exactly those props as the
decisive evidence that the pair was repetitive. One of them put it plainly:
strip those forks out and the two pairs are indistinguishable. The rating
measured the binding, not the thing under test, and the whole round was wasted
(AL-195).

**Comparing every prop against every prop, not slot against slot, is what makes
it work.** Of those 14, only 6 sat at the same node in both books; the other 8
were the same props *relocated*, arm C's culvert at `n_note` against the
treatment's at `n_door`, arm C's toll ledgers at `n_stairs` against the
treatment's at `n_study`. A same-slot diff sees 6 and calls the binding mostly
fresh. Relocation is not variation: a blind rater described it unprompted as
reading like variety fork by fork while being pure rearrangement at the book
level, and said answering node by node had nearly let it pass.

**Why category-scoped checking is not enough.** ``check_bible_diversity.py``
compares device-kind multisets *within* each category, so a device that moves
category is invisible to it. It certified a pair at 0.978 while one book's
hint carrier (``pattern_in_mechanism``, "long, long, short") and the other's
cipher (``rhythm_code``, "read each pull as long or short") were the same
device; a blind rater caught it unaided (AL-185). This checker flattens every
slot and compares all of them against all of them, so a rhythm in one category
is at least eligible to collide with a rhythm in another.

Four signals, in descending order of confidence:

- **Identical text.** Deterministic and always a defect.
- **Near-identical text**, by token Jaccard over content words. Catches the
  reworded prop.
- **Rare shared vocabulary**, three or more content words that both props use
  and that are used by almost nothing else in either book. This is the signal
  that reaches the AL-185 pair: "read each pull as long or short and let the
  repeating phrase spell out the setting" and "the weir gates sluice in a
  repeating run, long, long, short, the same run the flags spell" share only
  0.21 by Jaccard, because one is about bell pulls and the other about weir
  gates, but they share `long`, `short`, `repeating` and `spell`, and nothing
  else in either book uses those words. Rarity is what separates a shared
  device from shared world vocabulary; a plain token count would fire on
  "winch loft" in every book set in this world.
- **Shared distinctive phrase**, a content bigram used by both. The weakest
  signal, since a single bigram recurs innocently.

Kind reuse is reported per slot but is NOT by itself a failure: two books may
both need a person-mediated way in, and the contract may require it. What must
differ is the prop.

**What it cannot do.** Two props that are the same device described with wholly
different words share no vocabulary and will pass. This is a screen, not an
arbiter; a reader or an annotator remains the ground truth. Calibration to
date is one known-bad pair (0.583) and one known-good pair (0.000), which is
thin, so treat the rate as ordinal rather than absolute.

Exits 1 with ``--check`` on any identical or near-identical text. The rare-
vocabulary and phrase signals are advisory: they are evidence for a human to
weigh, not grounds to fail a binding automatically.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from itertools import pairwise
from pathlib import Path
from typing import Any, NamedTuple, cast

_WORD_RE = re.compile(r"[a-z']+")
_TEXT_JACCARD_CEILING = 0.5
_MIN_BIGRAM_HITS = 2
_MIN_RARE_SHARED = 3
_RARE_PROP_COUNT = 2
_STOPWORDS = frozenset(
    """a an and are as at be been by for from had has have he her his in into is it
    its of on or she that the their them they this to was were what when which who
    with you your not no but so than then there here up down out over under""".split()
)


class Slot(NamedTuple):
    """One bound prop."""

    node_id: str
    slot: str
    kind: str
    text: str


def _tokens(text: str) -> set[str]:
    """Return the content words of a prop description."""
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS}


def _bigrams(text: str) -> set[tuple[str, str]]:
    """Return adjacent content-word pairs, the distinctive-phrase signal."""
    words = [w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS]
    return set(pairwise(words))


def slots(selection: dict[str, Any]) -> list[Slot]:
    """Flatten a selection file to a list of bound props.

    Category is deliberately discarded: a device that moved category is still
    the same device, and category-scoped comparison cannot see it.

    Args:
        selection: The decoded selection JSON.

    Returns:
        Every bound prop, in file order.
    """
    out: list[Slot] = []
    for node_id, block in selection.items():
        if not isinstance(block, dict):
            continue
        for slot, value in cast("dict[str, Any]", block).items():
            if isinstance(value, dict):
                entry = cast("dict[str, Any]", value)
                out.append(
                    Slot(
                        str(node_id),
                        str(slot),
                        str(entry.get("kind") or ""),
                        str(entry.get("text") or ""),
                    )
                )
            elif isinstance(value, str):
                out.append(Slot(str(node_id), str(slot), "", value))
    return out


def _jaccard(left: set[Any], right: set[Any]) -> float:
    """Return the Jaccard similarity of two sets, 0.0 when both are empty."""
    if not left and not right:
        return 0.0
    return len(left & right) / len(left | right)


def compare(
    left: dict[str, Any], right: dict[str, Any], ceiling: float
) -> tuple[dict[str, float], list[str], list[str]]:
    """Compare every prop of one book against every prop of the other.

    Args:
        left: One decoded selection.
        right: The other decoded selection.
        ceiling: Token-Jaccard above which two texts are near-identical.

    Returns:
        A (scores, failures, advisories) triple.
    """
    a, b = slots(left), slots(right)
    by_key = {(s.node_id, s.slot): s for s in b}
    failures: list[str] = []
    advisories: list[str] = []

    # A word is rare when almost nothing else in either book uses it. Shared
    # rare words are the signal that survives two props describing one device
    # in different nouns; shared common words are just the shared world.
    document_frequency: Counter[str] = Counter()
    for prop in (*a, *b):
        document_frequency.update(_tokens(prop.text))
    rare = {w for w, n in document_frequency.items() if n <= _RARE_PROP_COUNT}

    identical = 0
    near = 0
    kind_reuse = 0
    rare_overlaps = 0
    for one in a:
        for other in b:
            if one.text and one.text == other.text:
                identical += 1
                failures.append(
                    f"  IDENTICAL TEXT {one.node_id}.{one.slot} vs "
                    f"{other.node_id}.{other.slot}: {one.text[:70]}"
                )
                continue
            score = _jaccard(_tokens(one.text), _tokens(other.text))
            if score > ceiling:
                near += 1
                failures.append(
                    f"  NEAR-IDENTICAL ({score:.2f}) {one.node_id}.{one.slot} vs "
                    f"{other.node_id}.{other.slot}\n"
                    f"      A: {one.text[:70]}\n      B: {other.text[:70]}"
                )
                continue
            shared_rare = _tokens(one.text) & _tokens(other.text) & rare
            if len(shared_rare) >= _MIN_RARE_SHARED:
                rare_overlaps += 1
                advisories.append(
                    f"  RARE SHARED VOCABULARY {one.node_id}.{one.slot} vs "
                    f"{other.node_id}.{other.slot}: "
                    f"{', '.join(sorted(shared_rare))}\n"
                    f"      A: {one.text[:70]}\n      B: {other.text[:70]}"
                )
                continue
            shared = _bigrams(one.text) & _bigrams(other.text)
            if len(shared) >= _MIN_BIGRAM_HITS:
                phrases = ", ".join(" ".join(p) for p in sorted(shared)[:3])
                advisories.append(
                    f"  shared phrase(s) {one.node_id}.{one.slot} vs "
                    f"{other.node_id}.{other.slot}: {phrases}"
                )

    for one in a:
        other = by_key.get((one.node_id, one.slot))
        if other is not None and one.kind and one.kind == other.kind:
            kind_reuse += 1
            advisories.append(
                f"  same kind at {one.node_id}.{one.slot}: {one.kind} "
                f"(not a failure; the prop is what must differ)"
            )

    total = float(max(len(a), len(b)))
    return (
        {
            "slots_compared": total,
            "identical_texts": float(identical),
            "near_identical_texts": float(near),
            "same_kind_same_slot": float(kind_reuse),
            "rare_vocabulary_overlaps": float(rare_overlaps),
            "collision_rate": (identical + near) / total if total else 0.0,
        },
        failures,
        advisories,
    )


def _load(path: str) -> dict[str, Any]:
    """Load a JSON object from path."""
    return cast(
        "dict[str, Any]", json.loads(Path(path).resolve().read_text(encoding="utf-8"))
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 unless --check and a collision was found."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("selections", nargs=2, help="Two books' device selections.")
    parser.add_argument(
        "--max-text-jaccard",
        type=float,
        default=_TEXT_JACCARD_CEILING,
        help=(
            "Content-word overlap above which two prop texts are treated as the "
            "same device reworded."
        ),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    left, right = (_load(p) for p in args.selections)
    scores, failures, advisories = compare(left, right, args.max_text_jaccard)

    for key, value in scores.items():
        shown = f"{value:.3f}" if "rate" in key else f"{value:.0f}"
        sys.stdout.write(f"{key:24s} {shown}\n")
    for line in failures:
        sys.stdout.write(f"{line}\n")
    for line in advisories[:20]:
        sys.stdout.write(f"{line}\n")
    if len(advisories) > 20:
        sys.stdout.write(f"  ... {len(advisories) - 20} further advisory line(s)\n")

    if failures:
        sys.stderr.write(
            f"FAIL {len(failures)} device collision(s): the two books share props, "
            f"not merely a world, and a reader will call them the same book on that "
            f"evidence regardless of what else differs\n"
        )
    sys.stdout.write(f"{'FAIL' if failures else 'ok  '}: device collision\n")
    return 1 if (failures and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
