"""Check a filled story against its skeleton: structure, markers, word stats.

Usage:
    uv run python scripts/check_fill_integrity.py <skeleton.json> <filled.json>

Three checks for the story-inventory authoring run (see
``docs/planning/story-inventory-initial-run.md`` section 5.1):

1. Structural immutability: with every node ``body`` and every choice
   ``label`` removed, the filled story must be byte-identical (canonical
   JSON) to the skeleton. An author agent only writes leaf prose (bodies and
   labels); any other difference is a hard fail. Choice labels are leaf
   content, aligned with ``diversity/structure.py``'s
   ``structure_fingerprint`` (the WS-0 labels-are-leaves decision): the
   automated fill contract (``generation/templates/fill.md``) rewrites
   labels per theme, so this check no longer treats that rewrite as a
   structural violation. A label's *action-semantic* (what the choice
   means, as opposed to its surface wording) is not checked here at all;
   that is a Stage 1 fidelity concern, not a byte-equality one.
2. No ``<<FILL`` markers may remain anywhere in the filled file.
3. Word stats: per-node counts vs the band's per-node hard max (fail) and the
   story mean vs the band's advisory range (warning only; PL-19 mirrors this).

Exits 1 on a structural diff, a leftover marker, or a node over the hard max.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from cyo_adventure.validator.band_profile import words_per_node_profile

_FILL_MARKER = "<<FILL"


def _load(path: str) -> dict[str, Any] | None:
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
    return data


def _strip_leaf_fields(story: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of a story with body/label leaf fields removed.

    Args:
        story: The decoded story JSON.

    Returns:
        A copy suitable for structure-only comparison: every node ``body``
        and every choice ``label`` removed, leaving ids, targets,
        conditions, effects, endings, variables, and metadata.
    """
    copy: dict[str, Any] = json.loads(json.dumps(story))
    nodes = copy.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict):
                node.pop("body", None)
                choices = node.get("choices")
                if isinstance(choices, list):
                    for choice in choices:
                        if isinstance(choice, dict):
                            choice.pop("label", None)
    return copy


def _word_stats(filled: dict[str, Any]) -> tuple[list[tuple[str, int]], float]:
    """Return per-node (id, word count) pairs and the story mean.

    Args:
        filled: The decoded filled story JSON.

    Returns:
        The per-node counts and the mean words per node (0.0 when empty).
    """
    counts: list[tuple[str, int]] = []
    nodes = filled.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict):
                body = node.get("body", "")
                node_id = str(node.get("id", "?"))
                if isinstance(body, str):
                    counts.append((node_id, len(body.split())))
    mean = sum(c for _, c in counts) / len(counts) if counts else 0.0
    return counts, mean


def main(argv: list[str] | None = None) -> int:
    """Run all integrity checks for one skeleton/filled pair.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Exit code: 0 when all hard checks pass, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skeleton", help="Path to the pristine skeleton JSON.")
    parser.add_argument("filled", help="Path to the filled story JSON.")
    args = parser.parse_args(argv)
    skeleton = _load(args.skeleton)
    filled = _load(args.filled)
    if skeleton is None or filled is None:
        return 1
    failed = False

    canonical_skeleton = json.dumps(_strip_leaf_fields(skeleton), sort_keys=True)
    canonical_filled = json.dumps(_strip_leaf_fields(filled), sort_keys=True)
    if canonical_skeleton != canonical_filled:
        sys.stderr.write(
            "FAIL structure: filled story differs from skeleton outside node "
            "bodies and choice labels (ids, choices, targets, endings, "
            "variables, or metadata)\n"
        )
        failed = True
    else:
        sys.stdout.write("ok   structure: only node bodies and choice labels differ\n")

    raw = json.dumps(filled)
    if _FILL_MARKER in raw:
        markers = [
            str(node.get("id", "?"))
            for node in filled.get("nodes", [])
            if isinstance(node, dict)
            and isinstance(node.get("body"), str)
            and _FILL_MARKER in node["body"]
        ]
        sys.stderr.write(f"FAIL markers: <<FILL remains in nodes: {markers}\n")
        failed = True
    else:
        sys.stdout.write("ok   markers: no <<FILL markers remain\n")

    metadata = filled.get("metadata")
    band = metadata.get("age_band", "") if isinstance(metadata, dict) else ""
    style = (
        metadata.get("narrative_style") or "prose"
        if isinstance(metadata, dict)
        else "prose"
    )
    profile = words_per_node_profile(str(band), str(style))
    counts, mean = _word_stats(filled)
    if profile is None:
        sys.stderr.write(f"FAIL words: unknown band '{band}' (no envelope)\n")
        failed = True
    else:
        target_mean, advisory_lo, advisory_hi, per_node_max = profile
        over = [(nid, c) for nid, c in counts if c > per_node_max]
        for nid, count in over:
            sys.stderr.write(
                f"FAIL words: node '{nid}' is {count} words, over the "
                f"{band}/{style} per-node max {per_node_max}\n"
            )
            failed = True
        in_range = advisory_lo <= mean <= advisory_hi
        marker = "ok  " if in_range else "warn"
        sys.stdout.write(
            f"{marker} words: mean {mean:.1f}/node over {len(counts)} nodes "
            f"(target {target_mean}, advisory {advisory_lo}-{advisory_hi}, "
            f"max {per_node_max})\n"
        )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
