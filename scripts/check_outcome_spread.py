"""Audit outcome-economy spread across the skeletons within each cell.

Usage:
    uv run python scripts/check_outcome_spread.py [--check] [--tau T]

Ruled 2026-08-09 (review Part 4 R1, accepted): the trees a reader alternates
between inside one ``(age_band, length, narrative_style)`` cell must offer
different outcome economies, so a cell never holds three copies of the same
2-wins/98%-death shape. This is the outcome-economy analogue of the in-cell
structural clone audit (``check_incell_clones.py``): that one proves the
graphs differ, this one proves the endings a reader can reach differ.

Signature per skeleton: the distribution of endings over ``ending.kind``
joined with the distribution over ``ending.valence`` (both as shares, so
size cancels). Distance between two skeletons is total variation distance
averaged over the two components, in [0, 1]. Pairs below ``--tau`` (default
0.10) are breaches.

Report mode (default) prints every in-cell pair sorted by distance. With
``--check`` the exit code is 1 when any breach exists. NOT wired into CI
yet: the grandfathered catalog predates the ruling and is being rebuilt;
wire this next to the A8 clone audit once the rebuild lands, with the same
shrink-only allowlist discipline if any breach is deliberately retained.

Only production-eligible skeletons participate (MVP seeds declare no cell).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

from cyo_adventure.generation.skeleton import is_sidecar

_SKELETONS_ROOT = Path(__file__).resolve().parent.parent / "skeletons"

# Below this total-variation distance two trees in one cell count as offering
# the same outcome economy. Grounding: the identical clone pair sits at 0.0,
# and same-shape teen gamebooks (2 wins, death-dominant) sit under ~0.08;
# genuinely different economies (graded-setback vs lethal) sit above ~0.2.
DEFAULT_TAU = 0.10

_KINDS = ("success", "completion", "discovery", "setback", "death", "capture")
_VALENCES = ("positive", "neutral", "negative")


def outcome_signature(story: dict[str, Any]) -> tuple[float, ...] | None:
    """Return the ending-economy signature of a skeleton, or None if endingless.

    Args:
        story: The decoded skeleton dict.

    Returns:
        tuple[float, ...] | None: Kind shares then valence shares, or None
            when the story has no endings to sign.
    """
    nodes = cast("list[Any]", story.get("nodes") or [])
    kinds: dict[str, int] = dict.fromkeys(_KINDS, 0)
    valences: dict[str, int] = dict.fromkeys(_VALENCES, 0)
    total = 0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        ending = node.get("ending")
        if not isinstance(ending, dict):
            continue
        kind = str(ending.get("kind"))
        valence = str(ending.get("valence"))
        if kind not in kinds or valence not in valences:
            # Counting an unrecognized value in `total` without a bucket makes
            # the shares sum to less than 1.0, pulling the signature toward the
            # origin and understating every distance, which produces false
            # passes in --check. Surface it instead of absorbing it.
            msg = (
                f"unknown ending kind/valence {kind!r}/{valence!r} in node "
                f"{node.get('id')!r}"
            )
            raise ValueError(msg)
        total += 1
        kinds[kind] += 1
        valences[valence] += 1
    if total == 0:
        return None
    return tuple(kinds[k] / total for k in _KINDS) + tuple(
        valences[v] / total for v in _VALENCES
    )


def signature_distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Return the outcome distance between two signatures, in [0, 1].

    Total variation distance computed separately over the kind block and the
    valence block, then averaged, so neither block dominates.

    Args:
        a: First signature (kind shares then valence shares).
        b: Second signature of the same shape.

    Returns:
        float: 0.0 for identical economies, 1.0 for disjoint ones.
    """
    n_kinds = len(_KINDS)
    tv_kind = sum(abs(x - y) for x, y in zip(a[:n_kinds], b[:n_kinds], strict=True)) / 2
    tv_val = sum(abs(x - y) for x, y in zip(a[n_kinds:], b[n_kinds:], strict=True)) / 2
    return (tv_kind + tv_val) / 2


def _load_cells() -> dict[tuple[str, str, str], list[tuple[str, tuple[float, ...]]]]:
    """Group production skeleton signatures by (band, length, style) cell."""
    cells: dict[tuple[str, str, str], list[tuple[str, tuple[float, ...]]]] = {}
    for path in sorted(_SKELETONS_ROOT.glob("*/*.json")):
        if is_sidecar(path):
            continue
        story = cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))
        metadata = cast("dict[str, Any]", story.get("metadata") or {})
        band = metadata.get("age_band")
        length = metadata.get("length")
        style = metadata.get("narrative_style")
        if (
            not isinstance(band, str)
            or not isinstance(length, str)
            or not isinstance(style, str)
        ):
            continue  # MVP seed: declares no cell, audits nothing
        signature = outcome_signature(story)
        if signature is None:
            continue
        cell = (band, length, style)
        cells.setdefault(cell, []).append((path.stem, signature))
    return cells


def main(argv: list[str] | None = None) -> int:
    """Run the audit.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Exit code: 0, or 1 with ``--check`` when a breach exists.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 when any in-cell pair sits below tau.",
    )
    parser.add_argument(
        "--tau",
        type=float,
        default=DEFAULT_TAU,
        help=f"Breach threshold (default {DEFAULT_TAU}).",
    )
    args = parser.parse_args(argv)
    pairs: list[tuple[float, tuple[str, str, str], str, str]] = []
    for cell, members in sorted(_load_cells().items()):
        for i, (slug_a, sig_a) in enumerate(members):
            for slug_b, sig_b in members[i + 1 :]:
                pairs.append((signature_distance(sig_a, sig_b), cell, slug_a, slug_b))
    breaches = [p for p in pairs if p[0] < args.tau]
    sys.stdout.write(
        f"in-cell pairs: {len(pairs)} tau={args.tau} breaches={len(breaches)}\n"
    )
    for dist, cell, slug_a, slug_b in sorted(pairs)[:20]:
        marker = "FAIL" if dist < args.tau else "ok  "
        sys.stdout.write(
            f"  {marker} {dist:.4f}  {'/'.join(cell):26} {slug_a} vs {slug_b}\n"
        )
    if args.check and breaches:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
