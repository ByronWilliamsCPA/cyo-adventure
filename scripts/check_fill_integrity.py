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
        # #ASSUME: security: canonicalized with .resolve() (CWE-23 hardening,
        # Snyk python/PT), but deliberately NOT contained to a fixed base
        # (the generation/import_cli.py::_load_blob idiom):
        # tests/unit/test_check_fill_integrity.py exercises both the
        # skeleton and filled paths against pytest tmp_path fixtures well
        # outside the repo tree with no chdir, proving arbitrary-location
        # paths are legitimate, exercised behavior that containment would
        # reject. No privilege boundary is crossed either way: the operator
        # (or authoring agent acting on the operator's own machine) invoking
        # this dev-only checker already has full filesystem access.
        # #VERIFY: any future change adding a fixed base must re-run
        # test_check_fill_integrity.py first; a rejection there means real
        # behavior broke.
        data = json.loads(Path(path).resolve().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: cannot load {path}: {exc}\n")
        return None
    if not isinstance(data, dict):
        sys.stderr.write(f"error: expected a JSON object in {path}\n")
        return None
    return data


def _defers_titles(skeleton: dict[str, Any]) -> bool:
    """Return whether the skeleton wrote any title as a FILL directive.

    Args:
        skeleton: The decoded skeleton.

    Returns:
        True when the storybook title or any ending title is an unfilled
        directive, meaning the fill is expected to author it.
    """
    if "<<FILL" in str(skeleton.get("title") or ""):
        return True
    return any(
        "<<FILL"
        in str(cast("dict[str, Any]", node.get("ending") or {}).get("title") or "")
        for node in cast("list[dict[str, Any]]", skeleton.get("nodes") or [])
    )


def _strip_leaf_fields(
    story: dict[str, Any], *, allow_title_rewrite: bool = False
) -> dict[str, Any]:
    """Return a deep copy of a story with body/label leaf fields removed.

    Args:
        story: The decoded story JSON.
        allow_title_rewrite: Also strip the storybook ``title`` and ending
            ``title``s from the
            comparison. Ending titles are leaf content by the WS-0
            labels-are-leaves decision (``structure_fingerprint`` strips
            them), but this checker historically froze them; the
            narrative-redesign pilots showed unslotted titles are
            byte-identical across sibling books and a top recognition
            channel (AL-161), so a title-contract fill may rewrite them
            when the caller opts in.

    Returns:
        A copy suitable for structure-only comparison: every node ``body``
        and every choice ``label`` removed (and, when opted in, every
        ending ``title``), leaving ids, targets, conditions, effects,
        ending kind/valence, variables, and metadata.
    """
    copy: dict[str, Any] = json.loads(json.dumps(story))
    if allow_title_rewrite:
        copy.pop("title", None)
    nodes = copy.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if isinstance(node, dict):
                node.pop("body", None)
                if allow_title_rewrite:
                    ending = node.get("ending")
                    if isinstance(ending, dict):
                        ending.pop("title", None)
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
    parser.add_argument(
        "--allow-title-rewrite",
        action="store_true",
        help=(
            "Permit ending titles to differ (title-contract fills; titles are "
            "leaf content per WS-0, AL-161)."
        ),
    )
    args = parser.parse_args(argv)
    # #CRITICAL: data-integrity: this check is a comparison, so it is only as
    # good as the independence of its two inputs. A builder bug once wrote the
    # prose story to BOTH paths, and the structural comparison then compared a
    # file with itself and PASSED, silently making the verification vacuous
    # (AL-016). A check that cannot fail manufactures confidence, so refuse the
    # degenerate inputs outright instead of reporting a meaningless success.
    # #VERIFY: test_check_fill_integrity_rejects_same_file and
    # test_check_fill_integrity_rejects_a_skeleton_with_no_markers.
    if Path(args.skeleton).resolve() == Path(args.filled).resolve():
        sys.stderr.write(
            "FAIL inputs: skeleton and filled are the same file, so the "
            "structural comparison would trivially pass and prove nothing\n"
        )
        return 1
    skeleton = _load(args.skeleton)
    filled = _load(args.filled)
    if skeleton is None or filled is None:
        return 1
    if _FILL_MARKER not in json.dumps(skeleton):
        sys.stderr.write(
            f"FAIL inputs: '{args.skeleton}' contains no {_FILL_MARKER} directive, "
            f"so it is not an unfilled skeleton; comparing two filled stories "
            f"cannot detect a failed fill\n"
        )
        return 1
    failed = False

    # A field the skeleton itself wrote as a FILL directive is fillable by
    # definition, so titles must not be compared when the skeleton defers them.
    # Every shell in the diversity programme has deferred its title since a
    # skeleton `id` leaked one book title into three arms (AL-207), and this
    # checker reported a structural FAIL on every correct fill until the flag
    # was passed by hand, which read like a serious defect and was not one
    # (AL-224). Deriving it removes a step nobody can be relied on to remember.
    defers_titles = _defers_titles(skeleton)
    allow_title_rewrite = args.allow_title_rewrite or defers_titles
    if defers_titles and not args.allow_title_rewrite:
        sys.stdout.write(
            "note  titles: the skeleton defers its title as a FILL directive, so "
            "title differences are expected and are not compared\n"
        )

    canonical_skeleton = json.dumps(
        _strip_leaf_fields(skeleton, allow_title_rewrite=allow_title_rewrite),
        sort_keys=True,
    )
    canonical_filled = json.dumps(
        _strip_leaf_fields(filled, allow_title_rewrite=allow_title_rewrite),
        sort_keys=True,
    )
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
