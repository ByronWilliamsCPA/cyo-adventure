"""Build the generated region of the story-skeleton catalog document.

The catalog doc (``docs/architecture/story-skeletons.md``) has a hand-authored
frame (basics, data dictionary) and a generated region (the documented-skeletons
table and band-coverage matrix) delimited by marker comments. This module builds
that region purely from skeleton data so it cannot drift from the JSON.
"""

from __future__ import annotations

from cyo_adventure.generation.diagram import meta_of, nodes_of, valence_split
from cyo_adventure.storybook.models import AgeBand

BEGIN_MARKER = "<!-- BEGIN GENERATED: skeleton-catalog -->"
END_MARKER = "<!-- END GENERATED: skeleton-catalog -->"

_DIAGRAM_REL = "diagrams/skeletons"


def build_catalog_region(
    skeletons: list[dict[str, object]], *, slugs: list[str]
) -> str:
    """Return the generated catalog region (table + coverage matrix), marker-wrapped.

    Args:
        skeletons: Decoded skeleton dicts, parallel to ``slugs``.
        slugs: Diagram slugs (filename stems), used to link each row's SVG.

    Returns:
        A marker-wrapped string starting with ``BEGIN_MARKER`` and ending with
        ``END_MARKER`` followed by a blank line.
    """
    lines: list[str] = [BEGIN_MARKER, "", "### Documented skeletons", ""]
    lines.append(
        "| Skeleton | Band | Length (min) | Tier | Topology | Nodes | Endings (+/n/-) | Diagram |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")

    populated: set[str] = set()
    rows = sorted(
        zip(skeletons, slugs, strict=True),
        key=lambda pair: (str(meta_of(pair[0]).get("age_band", "")), pair[1]),
    )
    for data, slug in rows:
        meta = meta_of(data)
        nodes = nodes_of(data)
        band = str(meta.get("age_band", "?"))
        populated.add(band)
        tier = meta.get("tier")
        minutes = meta.get("estimated_minutes")
        topology = str(meta.get("topology", "?"))
        title = str(data.get("title", "Untitled"))
        pos, neu, neg = valence_split(nodes)
        svg = f"{_DIAGRAM_REL}/{band}/{slug}.svg"
        tier_text = str(tier) if isinstance(tier, int) else "?"
        minutes_text = str(minutes) if isinstance(minutes, int) else "?"
        row = (
            f"| {title} | {band} | {minutes_text} | {tier_text} | {topology} |"
            f" {len(nodes)} | {pos}/{neu}/{neg} | [svg]({svg}) |"
        )
        lines.append(row)

    lines.extend(["", "### Band coverage", ""])
    lines.append("| Age band | Skeletons |")
    lines.append("| --- | --- |")
    for band_enum in AgeBand:
        mark = "yes" if band_enum.value in populated else "none yet"
        lines.append(f"| {band_enum.value} | {mark} |")

    lines.extend(["", END_MARKER, ""])
    return "\n".join(lines)


def splice_region(doc: str, region: str) -> str:
    """Replace the content between the catalog markers in ``doc`` with ``region``.

    Args:
        doc: The full catalog document text.
        region: A marker-wrapped region (from ``build_catalog_region``).

    Returns:
        The document with its generated region replaced. If markers are absent,
        the region is appended.
    """
    start = doc.find(BEGIN_MARKER)
    end = doc.find(END_MARKER)
    if start == -1 or end == -1:
        return doc.rstrip() + "\n\n" + region.rstrip() + "\n"
    end_full = end + len(END_MARKER)
    return doc[:start] + region.rstrip() + doc[end_full:]
