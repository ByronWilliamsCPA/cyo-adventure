"""Calibrate and commit the WS-5 anti-clone / state-signature floors.

Usage::

    uv run python scripts/calibrate_mutation_floors.py            # write baseline
    uv run python scripts/calibrate_mutation_floors.py --check    # fail on drift

Derives the three WS-5 acceptance floors from the real, gate-verified skeleton
catalog and writes a small versioned baseline artifact
(``docs/planning/ws5_floor_baseline.json``) that
:mod:`cyo_adventure.mutation.floors` loads as the single source of truth. The
committed baseline is tunable only by a reviewed PR (design section 4.6, 5.4,
OQ-3):

- ``TAU_STRUCT`` -- the 25th percentile of same-cell hand-authored pairwise
  :func:`~cyo_adventure.diversity.structure.structural_distance` values. A
  graph-shape-changed mutant must sit at least this far from its parent to be a
  genuinely new tree (design 4.6, clause 2).
- ``TAU_CELL`` -- the observed same-cell minimum pairwise structural distance. A
  mutant must not clone ANY existing in-cell tree, not just its parent (design
  4.6, clause 3). ``TAU_CELL <= TAU_STRUCT`` by construction.
- ``TAU_STATE`` -- the anti-no-op floor for a graph-shape-unchanged (M5-only)
  mutant, whose ``structural_distance`` is ~0 by design (design 5.4). Its job is
  to reject a distance-0 cosmetic edit (a no-op retune, a description-only edit,
  an alpha-rename); the smallest genuinely-distinct single-feature M5 change is
  >= 1, so the floor is set to the smaller of a fixed anti-no-op target and half
  the observed minimum cross-Tier-2-catalog state distance, then clamped to a
  documented minimum so it never admits a true no-op.

**Degenerate-threshold guard (design 4.6, OQ-3).** If calibration yields a
degenerate value (for example ``TAU_CELL == 0`` because two catalog skeletons in
one cell are near-identical), the value is NOT shipped as-is: a 0 floor would
admit clones. It is clamped to :data:`_MIN_STRUCT_FLOOR` (or
:data:`_MIN_STATE_FLOOR`) and the anomaly is recorded in the baseline's
``clamps`` list and printed to stderr.

The script is deterministic and re-runnable: the same catalog yields the same
baseline byte-for-byte, so ``--check`` can gate the committed artifact against
drift, mirroring ``scripts/render_skeleton_diagrams.py --check``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from cyo_adventure.diversity.structure import structural_distance
from cyo_adventure.generation.skeleton import is_sidecar
from cyo_adventure.mutation.state_ops import state_distance, state_signature
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.walk import walk_configurations

if TYPE_CHECKING:
    from collections.abc import Sequence

# The repository-root-relative catalog and baseline paths. Resolved from this
# file so the script behaves identically regardless of the invoking cwd.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKELETON_ROOT = _REPO_ROOT / "skeletons"
_BASELINE_PATH = _REPO_ROOT / "docs" / "planning" / "ws5_floor_baseline.json"

# The baseline schema version, bumped when the artifact's shape or a floor's
# derivation changes. v2: the ADR-020 floor-recalibration amendment made TAU_CELL
# a fixed owner-chosen anti-duplication floor and demoted TAU_STRUCT to
# documentation (see _TAU_CELL_FLOOR and docs/planning/ws8-floor-recalibration-proposal.md).
_BASELINE_VERSION = 2

# The percentile (0-100) used for TAU_STRUCT (design 4.6 / OQ-3: P25 of same-cell
# hand-authored pairs). As of the ADR-020 floor-recalibration amendment TAU_STRUCT
# is retained as documentation only (the cross-tree diversity target); it no
# longer gates mutants.
_TAU_STRUCT_PERCENTILE = 25.0

# TAU_CELL: the fixed, owner-chosen anti-duplication floor (ADR-020 floor-
# recalibration amendment). It is the minimum structural_distance a mutant must
# hold from EVERY in-cell tree INCLUDING its parent, replacing the retired
# mutant parent-distance-vs-TAU_STRUCT clause. Chosen at 0.05: it rejects the
# catalog's observed near-duplicate pair (~0.0009) with a ~53x margin while
# admitting mutations that represent a genuine structural change. Tunable only
# by a reviewed PR (a curation bar, not a data-derived value that would drift
# with operator changes).
_TAU_CELL_FLOOR = 0.05

# The anti-no-op target and the fraction of the minimum cross-Tier-2 state
# distance used to derive TAU_STATE (design 5.4). The smallest genuinely-distinct
# single-feature M5 change is >= 1, so a target of 0.5 bisects a true no-op
# (distance 0) from any real change while sitting far below any distinct-tree
# cross pair.
_TAU_STATE_TARGET = 0.5
_TAU_STATE_CROSS_FRACTION = 0.5

# #CRITICAL: data-integrity: the degenerate-threshold guard. A 0 (or near-0)
# floor would admit a structural or state clone, defeating the anti-clone bar
# (design 4.6, OQ-3). A calibrated value at or below these documented minima is
# clamped up and the anomaly is recorded, never silently shipped.
# #VERIFY: tests/unit/test_mutation_floors.py asserts a synthetic degenerate
# distribution clamps and records the anomaly, and that the shipped baseline
# carries no un-guarded 0 floor.
_MIN_STRUCT_FLOOR = 0.01
_MIN_STATE_FLOOR = 0.25


def _percentile(values: Sequence[float], percentile: float) -> float:
    """Return the linear-interpolated percentile of ``values``.

    Args:
        values: A non-empty sequence of samples.
        percentile: The percentile to compute, in ``[0, 100]``.

    Returns:
        float: The percentile value using the same linear-interpolation
            convention as numpy's default (rank ``(n - 1) * p / 100``).

    Raises:
        ValueError: If ``values`` is empty.
    """
    if not values:
        msg = "cannot compute a percentile of an empty sample"
        raise ValueError(msg)
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * (percentile / 100.0)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * frac


def _load_catalog() -> list[tuple[str, str, dict[str, object]]]:
    """Return ``(slug, band, document)`` for every production catalog skeleton.

    MVP seeds (``production_eligible`` false) and sidecars (``*.contract.json``
    and ``*.lineage.json``, per :func:`is_sidecar`) are excluded, matching the
    acceptance harness's in-cell catalog rule (design 4.6).

    Returns:
        list[tuple[str, str, dict[str, object]]]: The eligible catalog trees.
    """
    catalog: list[tuple[str, str, dict[str, object]]] = []
    for band_dir in sorted(p for p in _SKELETON_ROOT.iterdir() if p.is_dir()):
        for path in sorted(band_dir.glob("*.json")):
            if is_sidecar(path):
                continue
            document = cast(
                "dict[str, object]",
                json.loads(path.read_text(encoding="utf-8")),
            )
            meta = document.get("metadata")
            if not isinstance(meta, dict):
                continue
            if cast("dict[str, object]", meta).get("production_eligible") is False:
                continue
            catalog.append((path.stem, band_dir.name, document))
    return catalog


def _cell_of(document: dict[str, object]) -> tuple[str, str, str] | None:
    """Return a document's ``(age_band, length, narrative_style)`` cell, or None."""
    meta = document.get("metadata")
    if not isinstance(meta, dict):
        return None
    typed = cast("dict[str, object]", meta)
    band = typed.get("age_band")
    length = typed.get("length")
    style = typed.get("narrative_style")
    if not (
        isinstance(band, str) and isinstance(length, str) and isinstance(style, str)
    ):
        return None
    return (band, length, style)


def _same_cell_distances(
    catalog: list[tuple[str, str, dict[str, object]]],
) -> list[float]:
    """Return every same-cell hand-authored pairwise structural distance.

    Args:
        catalog: The eligible catalog trees.

    Returns:
        list[float]: One structural distance per unordered same-cell pair.
    """
    by_cell: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for _slug, _band, document in catalog:
        cell = _cell_of(document)
        if cell is None:
            continue
        by_cell.setdefault(cell, []).append(document)
    return [
        structural_distance(docs[i], docs[j])
        for docs in by_cell.values()
        for i in range(len(docs))
        for j in range(i + 1, len(docs))
    ]


def _cross_tier2_state_distances(
    catalog: list[tuple[str, str, dict[str, object]]],
) -> list[float]:
    """Return every cross-Tier-2-catalog pairwise state-signature distance.

    Each Tier-2 tree is walked exactly once; the pairwise state distance is
    computed from those signatures (design 5.4).

    Args:
        catalog: The eligible catalog trees.

    Returns:
        list[float]: One state distance per unordered pair of distinct Tier-2
            trees.
    """
    signatures: list[object] = []
    for _slug, _band, document in catalog:
        variables = document.get("variables")
        if not (isinstance(variables, list) and variables):
            continue
        story = Storybook.model_validate(document)
        signatures.append(state_signature(story, walk_configurations(story)))
    return [
        state_distance(signatures[i], signatures[j])  # pyright: ignore[reportArgumentType]
        for i in range(len(signatures))
        for j in range(i + 1, len(signatures))
    ]


def _summ(values: Sequence[float]) -> dict[str, object]:
    """Return a small min/p05/p25/median summary of a distance sample."""
    if not values:
        return {"n_pairs": 0}
    ordered = sorted(values)
    return {
        "n_pairs": len(ordered),
        "min": round(ordered[0], 6),
        "p05": round(_percentile(ordered, 5.0), 6),
        "p25": round(_percentile(ordered, 25.0), 6),
        "median": round(_percentile(ordered, 50.0), 6),
        "max": round(ordered[-1], 6),
    }


def compute_baseline() -> dict[str, object]:
    """Compute the full, deterministic floor baseline from the live catalog.

    Returns:
        dict[str, object]: The baseline artifact ready to serialize.
    """
    catalog = _load_catalog()
    same_cell = _same_cell_distances(catalog)
    cross_state = _cross_tier2_state_distances(catalog)
    clamps: list[str] = []

    raw_tau_struct = (
        _percentile(same_cell, _TAU_STRUCT_PERCENTILE) if same_cell else 0.0
    )
    raw_tau_state = (
        min(_TAU_STATE_TARGET, min(cross_state) * _TAU_STATE_CROSS_FRACTION)
        if cross_state
        else _TAU_STATE_TARGET
    )

    tau_struct = raw_tau_struct
    if tau_struct <= _MIN_STRUCT_FLOOR:
        struct_clamp = (
            f"TAU_STRUCT calibrated to {raw_tau_struct:.6f} (<= {_MIN_STRUCT_FLOOR}): "
            f"clamped up to the documented minimum to avoid a clone-admitting floor"
        )
        clamps.append(struct_clamp)
        tau_struct = _MIN_STRUCT_FLOOR

    # ADR-020 floor-recalibration amendment: TAU_CELL is the fixed owner-chosen
    # anti-duplication floor, NOT the observed same-cell minimum (which was the
    # catalog's own near-duplicate pair). It gates a mutant against every in-cell
    # tree including its parent; the retired parent-distance clause is subsumed.
    observed_min = min(same_cell) if same_cell else 0.0
    tau_cell = _TAU_CELL_FLOOR
    cell_note = (
        f"TAU_CELL is the fixed anti-duplication floor {_TAU_CELL_FLOOR} (ADR-020 "
        f"floor-recalibration amendment); it rejects the observed same-cell minimum "
        f"pair at {observed_min:.6f} with margin. The raw observed minimum is no "
        f"longer shipped as the floor."
    )
    clamps.append(cell_note)

    tau_state = raw_tau_state
    if tau_state < _MIN_STATE_FLOOR:
        state_clamp = (
            f"TAU_STATE calibrated to {raw_tau_state:.6f} (< {_MIN_STATE_FLOOR}): "
            f"clamped up to the documented minimum to keep the anti-no-op floor "
            f"strictly positive"
        )
        clamps.append(state_clamp)
        tau_state = _MIN_STATE_FLOOR

    return {
        "baseline_version": _BASELINE_VERSION,
        "generated_by": "scripts/calibrate_mutation_floors.py",
        "tau_struct": round(tau_struct, 6),
        "tau_cell": round(tau_cell, 6),
        "tau_state": round(tau_state, 6),
        "derivation": {
            "tau_struct": (
                "DOCUMENTATION ONLY as of the ADR-020 floor-recalibration"
                " amendment: the 25th percentile of same-cell hand-authored"
                " structural_distance pairs (the cross-tree diversity target for"
                " independently authored trees). No longer gates mutants; the"
                " anti-clone guarantee is TAU_CELL against parent + siblings."
            ),
            "tau_cell": (
                "owner-chosen fixed anti-duplication floor (ADR-020 floor-"
                "recalibration amendment, docs/planning/ws8-floor-recalibration-"
                "proposal.md): the minimum structural_distance a mutant must hold"
                " from EVERY in-cell tree INCLUDING its parent. Replaces the"
                " retired mutant parent-distance-vs-TAU_STRUCT clause, which"
                " mis-applied a same-cell SIBLING-PAIR percentile to the parent"
                " distance and rejected ~every bounded mutant."
            ),
            "tau_state": (
                "anti-no-op floor min(0.5, min_cross_tier2_state_distance/2), clamped"
                " to >= 0.25 (design 5.4)"
            ),
        },
        "stats": {
            "same_cell_structural": _summ(same_cell),
            "cross_tier2_state": _summ(cross_state),
        },
        "clamps": clamps,
    }


def _serialize(baseline: dict[str, object]) -> str:
    """Return the canonical JSON text (sorted keys, trailing newline) of a baseline."""
    return json.dumps(baseline, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Compute the baseline and either write it or check it for drift.

    Args:
        argv: Optional argument list (defaults to ``sys.argv``).

    Returns:
        int: 0 on success (write done, or check clean); 1 on a ``--check`` drift.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail (exit 1) if the committed baseline is stale; write nothing.",
    )
    args = parser.parse_args(argv)

    baseline = compute_baseline()
    text = _serialize(baseline)
    clamps = cast("list[str]", baseline["clamps"])
    for anomaly in clamps:
        sys.stderr.write(f"warning: degenerate-threshold clamp: {anomaly}\n")

    if args.check:  # pyright: ignore[reportAny]
        if not _BASELINE_PATH.is_file():
            sys.stderr.write(
                f"error: baseline missing at {_BASELINE_PATH}; run without --check\n"
            )
            return 1
        current = _BASELINE_PATH.read_text(encoding="utf-8")
        if current != text:
            stale_msg = (
                f"Stale mutation-floor baseline (re-run the calibrator and commit):"
                f"\n  {_BASELINE_PATH}\n"
            )
            sys.stderr.write(stale_msg)
            return 1
        ok_msg = (
            f"Mutation-floor baseline is up to date: "
            f"TAU_STRUCT={baseline['tau_struct']} TAU_CELL={baseline['tau_cell']} "
            f"TAU_STATE={baseline['tau_state']}\n"
        )
        sys.stdout.write(ok_msg)
        return 0

    _BASELINE_PATH.write_text(text, encoding="utf-8")
    wrote_msg = (
        f"Wrote {_BASELINE_PATH}: TAU_STRUCT={baseline['tau_struct']} "
        f"TAU_CELL={baseline['tau_cell']} TAU_STATE={baseline['tau_state']}\n"
    )
    sys.stdout.write(wrote_msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
