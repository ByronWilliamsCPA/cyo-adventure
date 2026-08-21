"""Check a filled story against its skeleton: structure, markers, word stats.

Usage:
    uv run python scripts/check_fill_integrity.py <skeleton.json> <filled.json>

Four checks for the story-inventory authoring run (see
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
4. Story-level fill rate: delivered words over commissioned ``words=`` words,
   across the nodes that carried a directive (AL-490/UW-C307). The per-node
   advisory is legitimately soft (a one-line beat is legitimate), but the live
   DeepSeek run delivered 38.9-52.9 percent of three books' commissioned prose
   with zero hard findings, so the story-level ratio is a blocking check here,
   where the skeleton is in hand.

Exits 1 on a structural diff, a leftover marker, a node over the hard max, or
a story-level fill rate under ``--min-fill-rate``.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, cast

from cyo_adventure.generation.skeleton import commissioned_words_by_node
from cyo_adventure.validator.band_profile import words_per_node_profile

_FILL_MARKER = "<<FILL"

# Floor for the story-level fill rate. Calibrated 2026-08-20 against the
# nine passing books of the W4/W5 vendor pool (grok, gemini, sonnet), which
# span 0.715-0.990, and the three under-delivering DeepSeek books (AL-490),
# which span 0.389-0.529.
#
# The margin is thinner than that pool alone suggests, so do not read
# "0.715" as the headroom. Recomputed across all 48 (skeleton, filled) pairs
# committed anywhere in the tree (``out/``, ``tests/data/diversity_panel/``,
# and the vendor-comparison runs), the tightest KNOWN-GOOD pair is
# ``tests/data/diversity_panel/fills/the-sky-ship-stowaway.deep-sea-submarine.filled.json``
# at 0.635 (0.634 after the per-node capping below), and
# ``the-lantern-festival.filled.json`` sits at 0.668. So 0.6 clears the
# tightest good fill by about 0.035, not by 0.115, and two known-good pairs
# live inside the 0.529-0.715 band this floor was said to "split".
#
# It still admits every one of the 48 and blocks every book the live run
# proved unpublishable, which is the property that matters. But a raise
# above ~0.63 starts rejecting known-good fills. Revisit with the
# calibration rerun, not by hand.
_DEFAULT_MIN_FILL_RATE = 0.6


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


def _delivered_words_by_node(filled: dict[str, Any]) -> dict[str, int]:
    """Return delivered word counts keyed the way the commissioned side keys.

    The fill-rate join looks these up by the keys
    ``commissioned_words_by_node`` produces: the node id, or ``#index`` for an
    id-less node, with duplicate keys accumulating. Reusing ``_word_stats``'s
    pairs here would key id-less nodes as ``"?"`` and let a ``dict()`` collapse
    duplicate ids, silently undercounting delivery and failing a fill that
    delivered in full. The structural check pins the filled story to the
    skeleton's node order, which is what makes a positional key comparable at
    all.

    Args:
        filled: The decoded filled story JSON.

    Returns:
        Delivered words per commissioned-style node key.
    """
    delivered: dict[str, int] = {}
    nodes = filled.get("nodes")
    if not isinstance(nodes, list):
        return delivered
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        body = node.get("body")
        if not isinstance(body, str):
            continue
        raw_id = node.get("id")
        key = str(raw_id) if raw_id is not None else f"#{index}"
        delivered[key] = delivered.get(key, 0) + len(body.split())
    return delivered


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
    # `cast` is a type-checker assertion with NO runtime effect, so the previous
    # comprehension raised AttributeError on a non-dict node instead of the
    # clean message every other check in this file emits. Reachable from the
    # hand-edited or partially written skeleton this checker exists for, and
    # normally masked only because a FILL title short-circuits above.
    nodes = skeleton.get("nodes")
    if not isinstance(nodes, list):
        return False
    for node in nodes:
        if not isinstance(node, dict):
            continue
        ending = node.get("ending")
        if not isinstance(ending, dict):
            continue
        if "<<FILL" in str(ending.get("title") or ""):
            return True
    return False


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
            "Permit the storybook title and ending titles to differ "
            "(title-contract fills; titles are "
            "leaf content per WS-0, AL-161)."
        ),
    )
    parser.add_argument(
        "--min-fill-rate",
        type=float,
        default=_DEFAULT_MIN_FILL_RATE,
        help=(
            "Fail when delivered words over commissioned words falls below "
            "this ratio, measured across the nodes carrying a words= "
            f"directive (default {_DEFAULT_MIN_FILL_RATE}; pass 0 to "
            "measure without blocking). AL-490: three books delivering "
            "38.9-52.9 percent of their commissioned prose passed every "
            "existing check."
        ),
    )
    args = parser.parse_args(argv)
    # A NaN floor compares False against every ratio and a negative one is
    # below every possible delivery, so either silently disables the gate
    # while looking configured. Zero stays legal as the documented
    # measure-without-blocking setting.
    min_fill_rate = float(args.min_fill_rate)
    if not math.isfinite(min_fill_rate) or min_fill_rate < 0:
        sys.stderr.write(
            f"FAIL inputs: --min-fill-rate {args.min_fill_rate} is not a "
            "finite, non-negative ratio; a NaN or negative floor would pass "
            "every fill, and an infinite one would fail every fill\n"
        )
        return 1
    # A floor above 1.0 is the percent-typo shape (``--min-fill-rate 60``
    # meaning 60 percent). It passes the finiteness guard above and then
    # fails EVERY book, including one that delivered its commission in
    # full, which reads as a vendor finding rather than as the usage error
    # it is. The two guards are not redundant: the first rejects floors
    # that silently pass everything, this one rejects a floor that
    # silently fails everything.
    if min_fill_rate > 1:
        sys.stderr.write(
            f"FAIL inputs: --min-fill-rate {args.min_fill_rate} is above "
            "1.0, so no fill could satisfy it; the floor is a ratio, not a "
            "percentage (use 0.6, not 60)\n"
        )
        return 1
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

    # Derived rather than remembered: a skeleton that writes its title as a FILL
    # directive expects the fill to author it, so comparing titles reports a
    # structural failure that is not one. This previously depended on the flag
    # being passed by hand (AL-224 on this branch, renumbered in the merge).
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

    # Story-level fill rate (AL-490/UW-C307): the per-node advisory is soft on
    # purpose (a one-line beat is legitimate), but that softness composes into
    # a whole book at 40 percent of its commissioned prose that nothing
    # blocks. The ratio is measured over directive-bearing nodes only, so
    # pre-authored prose neither pads nor dilutes it.
    # #CRITICAL: data-integrity: the blocking ratio must be monotone in
    # per-node delivery, or a surplus becomes a licence to omit. Summing raw
    # delivery against the commissioned total lets one over-written node pay
    # for another that came back empty: ten nodes commissioned at 60 words,
    # five delivering 120 and five delivering nothing, sums to 600 of 600 and
    # reports a perfect fill. That is not hypothetical here -- 15 of the 48
    # committed pairs over-deliver in aggregate (up to 1.19x), so the surplus
    # to spend is real, and ``Node.body`` carries no ``min_length`` while the
    # band profile sets no per-node minimum by design, so nothing downstream
    # catches the blank nodes either. Capping each node's credit at what it
    # was commissioned makes the ratio fall whenever any node under-delivers.
    # #VERIFY: test_surplus_on_one_node_cannot_pay_for_an_empty_node and
    # test_a_dropped_node_body_counts_as_zero_delivery.
    commissioned = commissioned_words_by_node(skeleton)
    if not commissioned:
        # Distinguish two very different reasons the map came back empty.
        #
        # A well-formed skeleton whose directives simply carry no ``words=``
        # target commissions nothing, so there is genuinely nothing to
        # measure and a note is right. Older skeletons predate the targets.
        #
        # A skeleton whose ``nodes`` is not a list of node objects is a
        # different animal: the scan could not look at a single node, so the
        # gate reports success having compared nothing. That is the
        # vacuous-success shape AL-294 ruled a defect in
        # ``check_reading_level``, where an unscoreable book was "counted as
        # a pass" and now fails. ``commissioned_words_by_node`` degrades to
        # ``{}`` on both, because its caller ``expected_output_tokens`` wants
        # a relaxed estimate rather than an exception; a BLOCKING gate wants
        # the opposite, and the two cases must not share an outcome here.
        raw_nodes = skeleton.get("nodes")
        scannable = isinstance(raw_nodes, list) and any(
            isinstance(node, dict) for node in cast("list[object]", raw_nodes)
        )
        if not scannable:
            sys.stderr.write(
                "FAIL fill-rate: the skeleton exposes no node objects to "
                "scan, so no commissioned total exists and every check above "
                "compared nothing; this is a malformed skeleton, not a fill "
                "that delivered\n"
            )
            failed = True
        else:
            sys.stdout.write(
                "note  fill-rate: no words= directives in the skeleton, so "
                "there is no commissioned total to measure against\n"
            )
    else:
        delivered_by_node = _delivered_words_by_node(filled)
        total = sum(commissioned.values())
        # Raw delivery is the headline figure and the one AL-490's journalled
        # 38.9/52.9/42.7 percent refer to; the capped figure is what gates.
        raw_delivered = sum(delivered_by_node.get(nid, 0) for nid in commissioned)
        effective = sum(
            min(delivered_by_node.get(nid, 0), words)
            for nid, words in commissioned.items()
        )
        raw_rate = raw_delivered / total
        fill_rate = effective / total
        capped = ""
        if abs(raw_rate - fill_rate) >= 0.001:
            capped = f"; {fill_rate:.1%} once per-node surplus is discounted"
        line = (
            f"fill-rate: delivered {raw_delivered} of {total} commissioned "
            f"words ({raw_rate:.1%}{capped}) over {len(commissioned)} "
            f"directive nodes (floor {min_fill_rate})\n"
        )
        if fill_rate < min_fill_rate:
            sys.stderr.write(f"FAIL {line}")
            failed = True
        else:
            sys.stdout.write(f"ok   {line}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
