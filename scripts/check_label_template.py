"""Flag a book whose choice labels share one grammatical template.

Usage:
    uv run python scripts/check_label_template.py <filled.json>... [--check]
        [--max-share 0.20]

**Written after a rating round was spoiled by this and nothing caught it.** An
experimental arm testing whether a world that prices failure reads as less
repetitive drew its `label_style` from its own contract, picked "name the cost
before the reward", and produced **35 of 35 labels beginning with the word
"Spend"**. Its comparison books used ordinary styles. The first blind rater
named the pattern unprompted as the most distinctive signature among the three
texts and leant on it in the verdict, so the round could not separate the
treatment from a label template (`AL-225`).

**What it measures.** Three signals over a book's choice labels, each a
different way one template can take over:

- **First-word concentration.** The share of labels opening with the single
  most common first word. A house style may favour imperatives; it should not
  favour one *verb*.
- **Opening-bigram concentration.** The same for the first two words, which
  catches "We decide ...", "Spend the ..." and other fixed frames that vary
  the second word just enough to dodge the first signal.
- **Shape uniformity.** The share of labels matching the most common
  comma-and-length silhouette, which catches a fixed "X, then Y" frame whose
  vocabulary rotates freely.

**What it is not.** Not a style checker and not a quality judgement. A book may
have a strong voice; what it may not have is a voice a reader could identify
from the labels with the prose removed. And it says nothing about *shared*
templates across books, which `check_sibling_fills.py` covers from the other
direction: this one asks whether a single book is internally templated.

**Calibration, on the three books of the round that prompted it:**

| Book | First word | Opening bigram | Shape |
| --- | --- | --- | --- |
| the spoiled arm | **1.000** | **0.371** | 0.400 |
| its two comparison books | 0.114, 0.229 | 0.086, 0.229 | 0.371, 0.600 |

The default ceiling of 0.20 on first-word concentration separates them. The
comparison books' own numbers are the reason the other two signals are advisory
rather than gating: shape uniformity reaches 0.600 in a perfectly ordinary book,
because "three words where possible" makes most labels the same silhouette by
design, and gating on it would fire on good work.

Exits 1 with ``--check`` when first-word concentration exceeds the ceiling.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, NamedTuple, cast

_WORD_RE = re.compile(r"[A-Za-z']+")
_MAX_SHARE = 0.20
_MIN_LABELS = 8
_SHAPE_ADVISORY = 0.65


class Scores(NamedTuple):
    """Template concentration across one book's labels."""

    labels: int
    first_word: float
    first_word_token: str
    bigram: float
    bigram_token: str
    shape: float


def _labels(story: dict[str, Any]) -> list[str]:
    """Return every choice label in the book."""
    return [
        str(c["label"])
        for n in cast("list[dict[str, Any]]", story.get("nodes") or [])
        for c in cast("list[dict[str, Any]]", n.get("choices") or [])
        if c.get("label")
    ]


def _shape(label: str) -> tuple[int, int]:
    """Return a coarse silhouette: comma count and word-count bucket.

    Deliberately coarse. A finer shape would separate labels that read
    identically to a child, and the signal being chased is the one a reader
    could spot at a glance.
    """
    words = _WORD_RE.findall(label)
    return label.count(","), min(len(words) // 3, 4)


def score(story: dict[str, Any]) -> Scores | None:
    """Score one book's labels for template concentration.

    Args:
        story: The decoded filled storybook.

    Returns:
        The scores, or None when the book has too few labels to judge.
    """
    labels = _labels(story)
    if len(labels) < _MIN_LABELS:
        return None
    total = float(len(labels))

    firsts = Counter((_WORD_RE.findall(x) or [""])[0].lower() for x in labels)
    bigrams = Counter(
        " ".join(_WORD_RE.findall(x)[:2]).lower() for x in labels if _WORD_RE.findall(x)
    )
    shapes = Counter(_shape(x) for x in labels)

    first_token, first_n = firsts.most_common(1)[0]
    bigram_token, bigram_n = bigrams.most_common(1)[0]
    return Scores(
        len(labels),
        first_n / total,
        first_token,
        bigram_n / total,
        bigram_token,
        shapes.most_common(1)[0][1] / total,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 1 with --check when a book is templated."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stories", nargs="+", help="Filled storybook JSON files.")
    parser.add_argument(
        "--max-share",
        type=float,
        default=_MAX_SHARE,
        help=(
            "Ceiling on the share of labels opening with one word. Above this, "
            "the book is identifiable from its labels alone."
        ),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    breached = False
    sys.stdout.write(
        f"{'book':26s} {'labels':>6s} {'first word':>18s} {'bigram':>20s} {'shape':>6s}\n"
    )
    sys.stdout.write("-" * 82 + "\n")
    for path in args.stories:
        story = cast(
            "dict[str, Any]",
            json.loads(Path(path).resolve().read_text(encoding="utf-8")),
        )
        scored = score(story)
        if scored is None:
            sys.stdout.write(f"{Path(path).stem:26s} too few labels to judge\n")
            continue
        bad = scored.first_word > args.max_share
        breached = breached or bad
        sys.stdout.write(
            f"{Path(path).stem:26s} {scored.labels:6d} "
            f"{scored.first_word_token + ' ' + format(scored.first_word, '.3f'):>18s} "
            f"{scored.bigram_token + ' ' + format(scored.bigram, '.3f'):>20s} "
            f"{scored.shape:6.3f}{'   <== TEMPLATED' if bad else ''}\n"
        )
        if scored.shape > _SHAPE_ADVISORY:
            sys.stdout.write(
                f"{'':26s} advisory: {scored.shape:.3f} of labels share one "
                f"silhouette; check this is house style and not a frame\n"
            )

    if breached:
        sys.stderr.write(
            f"FAIL label template: one opening word covers more than "
            f"{args.max_share:.0%} of a book's choices, so the book is "
            f"identifiable from its labels with the prose removed, and any "
            f"comparison it takes part in measures that instead\n"
        )
    sys.stdout.write(f"{'FAIL' if breached else 'ok  '}: label template\n")
    return 1 if (breached and args.check) else 0


if __name__ == "__main__":
    raise SystemExit(main())
