#!/usr/bin/env python
"""Measure the similarity vocabulary against the real corpus (A4/A5).

    uv run python scripts/measure_theme_coverage.py

Reports three things and asserts no target for any of them, per the plan's own
rule that a threshold is calibrated against the corpus before it ships and that
coverage is stated rather than assumed:

1. **Curated-theme coverage.** What share of the catalog's distinct
   ``metadata.themes`` the similarity vocabulary maps, and which are dropped.
   A dropped theme is not a bug by itself: :func:`similarity_signature` drops
   rather than passes through, because an unmappable string cannot make two
   stories measurably similar, only spuriously distinct.
2. **The A4 premise panel.** Realistic child requests paired with what the
   catalog actually offers, so the request side is measured on requests a child
   would plausibly make rather than on strings chosen to make the map look good.
3. **The score distribution** under both measures, which is the input to A5's
   ``tau_theme`` re-derivation. Symmetric Jaccard and containment are printed
   side by side, because the whole point of A2 is that they disagree.
"""

from __future__ import annotations

import collections
import json
import pathlib
import statistics
import sys
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Iterator

from cyo_adventure.diversity.normalize import (
    containment,
    jaccard_similarity,
    similarity_signature,
    theme_signature,
)
from cyo_adventure.diversity.similarity_vocab import (
    CANONICAL_TAGS,
    SIMILARITY_TAG_MAP,
    SUBJECT_TAGS,
    THEME_TAGS,
)

# A4: the committed premise panel. Written to mirror how the plan describes real
# requests (pets, sports, family, school, music, invention, weather, food,
# siblings), plus the fantasy staples the echo vocabulary already anticipates.
# These are REQUESTS, not catalog descriptions: the point is to measure whether a
# child's own words reach the same space the catalog is tagged in.
PREMISE_PANEL: tuple[str, ...] = (
    "a story about my dog who gets lost in the woods",
    "a dragon who is scared of fire",
    "me and my sister solving a mystery in an old castle",
    "a robot that learns to play music",
    "a pirate looking for treasure under the sea",
    "a kid who wants to win the big race",
    "a story about baking a cake for my grandma",
    "exploring a cave with a friend",
    "a rocket trip to another planet",
    "a snowstorm on the night of the festival",
    "an invention that goes wrong at school",
    "a knight who would rather be a gardener",
    "a detective story with secret codes",
    "a story about being brave at the doctor",
    "dinosaurs waking up in a museum",
    "a horse who will not jump the fence",
)


def _iter_catalog() -> Iterator[tuple[str, list[str]]]:
    """Yield ``(slug, curated themes)`` for every skeleton in the catalog."""
    for path in sorted(pathlib.Path("skeletons").rglob("*.json")):
        if ".contract." in path.name or ".lineage." in path.name:
            continue
        blob = cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))
        metadata = blob.get("metadata")
        raw: object = (
            cast("dict[str, object]", metadata).get("themes")
            if isinstance(metadata, dict)
            else None
        )
        themes = [t for t in cast("list[object]", raw or []) if isinstance(t, str)]
        yield path.stem, themes


def _catalog_theme_counts() -> collections.Counter[str]:
    """Return every distinct curated theme in the catalog with its usage count."""
    counts: collections.Counter[str] = collections.Counter()
    for _slug, themes in _iter_catalog():
        for theme in themes:
            if theme.strip():
                counts[theme.strip().lower()] += 1
    return counts


def _report_theme_coverage(counts: collections.Counter[str]) -> None:
    """Print curated-theme coverage and list what is dropped."""
    mapped = [t for t in counts if t in SIMILARITY_TAG_MAP]
    dropped = sorted(t for t in counts if t not in SIMILARITY_TAG_MAP)
    total_uses = sum(counts.values())
    mapped_uses = sum(counts[t] for t in mapped)

    sys.stdout.write("== 1. curated-theme coverage ==\n")
    pct_distinct = len(mapped) / len(counts)
    sys.stdout.write(
        f"distinct themes: {len(counts)}  mapped: {len(mapped)} ({pct_distinct:.0%})\n"
    )
    pct_uses = mapped_uses / total_uses
    used_note = "(weighted by how often each theme is actually used)"
    sys.stdout.write(
        f"theme USES: {total_uses}  mapped: {mapped_uses} ({pct_uses:.0%})  {used_note}\n"
    )
    sys.stdout.write(f"canonical tag space: {len(CANONICAL_TAGS)} tags\n")
    if dropped:
        sys.stdout.write(f"\ndropped ({len(dropped)}), with usage count:\n")
        for theme in dropped:
            sys.stdout.write(f"  {counts[theme]:2d}  {theme}\n")
    sys.stdout.write("\n")


def _report_panel() -> None:
    """Print what each panel premise yields under each vocabulary."""
    sys.stdout.write("== 2. A4 premise panel ==\n")
    empty_echo = 0
    empty_sim = 0
    for premise in PREMISE_PANEL:
        brief = {"premise": premise}
        echo = theme_signature(brief)
        sim = similarity_signature(brief)
        empty_echo += not echo
        empty_sim += not sim
        echo_text = ",".join(sorted(echo)) or "-"
        sim_text = ",".join(sorted(sim)) or "-"
        sys.stdout.write(f"  echo={echo_text:26s} sim={sim_text}\n")
        sys.stdout.write(f"      {premise}\n")
    total = len(PREMISE_PANEL)
    note = "(an empty request signature can never match anything)"
    counts_text = f"echo {empty_echo}/{total}, similarity {empty_sim}/{total}"
    sys.stdout.write(f"\nempty signatures: {counts_text} {note}\n\n")


def _report_distribution(counts: collections.Counter[str]) -> None:
    """Print the score distribution that A5 re-derives tau_theme from."""
    del counts
    stories = [
        (slug, similarity_signature(None, themes)) for slug, themes in _iter_catalog()
    ]

    jaccards: list[float] = []
    contains: list[float] = []
    best_rows: list[tuple[float, float, str, str]] = []
    for premise in PREMISE_PANEL:
        request = similarity_signature({"premise": premise})
        pairs = [
            (jaccard_similarity(request, sig), containment(request, sig), slug)
            for slug, sig in stories
            if sig
        ]
        if not pairs:
            continue
        jaccards.extend(p[0] for p in pairs)
        contains.extend(p[1] for p in pairs)
        best = max(pairs, key=lambda p: p[1])
        best_rows.append((best[0], best[1], best[2], premise))

    sys.stdout.write("== 3. score distribution (input to A5) ==\n")
    if not jaccards:
        sys.stdout.write("no scorable pairs; is the catalog present?\n")
        return
    for label, values in (("jaccard", jaccards), ("containment", contains)):
        stats = " ".join(
            [
                f"{label:12s} n={len(values)}",
                f"median={statistics.median(values):.4f}",
                f"mean={statistics.fmean(values):.4f}",
                f"p90={sorted(values)[int(0.9 * (len(values) - 1))]:.4f}",
                f"max={max(values):.4f}",
            ]
        )
        sys.stdout.write(f"{stats}\n")
    sys.stdout.write("\nbest match per premise, by containment:\n")
    for jac, con, slug, premise in best_rows:
        row = f"  containment={con:.3f} jaccard={jac:.3f}  {slug[:34]:34s}"
        sys.stdout.write(f"{row} <- {premise[:44]}\n")
    sys.stdout.write("\n")


def _report_axis_population() -> None:
    """Print which canonical tags the story side actually populates.

    The most decision-relevant output here, and not what the vocabulary work was
    expected to reveal. Fixing the two mechanical defects (verbatim passthrough,
    symmetric measure) does not fix matching if the story side never populates
    the axis a child's request lands on.
    """
    story_tags: collections.Counter[str] = collections.Counter()
    for _slug, themes in _iter_catalog():
        story_tags.update(similarity_signature(None, themes))

    missing_subject = sorted(SUBJECT_TAGS - set(story_tags))
    missing_theme = sorted(THEME_TAGS - set(story_tags))
    sys.stdout.write("== 4. which axes the STORY side populates ==\n")
    theme_present = len(THEME_TAGS) - len(missing_theme)
    theme_missing = missing_theme or "none"
    sys.stdout.write(
        f"theme tags present: {theme_present}/{len(THEME_TAGS)}  missing: {theme_missing}\n"
    )
    subject_text = f"{len(SUBJECT_TAGS) - len(missing_subject)}/{len(SUBJECT_TAGS)}"
    sys.stdout.write(
        f"subject tags present: {subject_text}  missing: {missing_subject}\n"
    )
    if missing_subject:
        explanation = "\n".join(
            [
                "",
                "The subject axis is the request side's native language, and",
                "the catalog barely speaks it. Every missing tag above is a",
                "request a child can make that NO story can match on theme,",
                "however good the vocabulary is, because no story declares it.",
                "Note how many are echo-vocabulary values: the echo map exists",
                "precisely because we expect children to ask for these. This is",
                "a catalog TAGGING gap, not a code gap, and it is cheap to close",
                "(metadata, not prose). Pair it with A20's contract backfill.",
                "",
            ]
        )
        sys.stdout.write(explanation)
    sys.stdout.write("\n")


def main() -> int:
    """Run the measurement.

    Returns:
        int: ``0`` always. This reports; it does not gate. A threshold derived
            from it belongs in the baseline, not in this script.
    """
    counts = _catalog_theme_counts()
    if not counts:
        sys.stderr.write("error: no curated themes found; is the catalog present?\n")
        return 2
    _report_theme_coverage(counts)
    _report_panel()
    _report_distribution(counts)
    _report_axis_population()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
