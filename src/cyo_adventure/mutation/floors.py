"""The WS-5 anti-clone floors and their committed calibration (design 4.6/5.4).

Two concerns live here, both pure and reject-only:

- **The calibrated thresholds.** ``TAU_STRUCT``, ``TAU_CELL``, and ``TAU_STATE``
  are loaded from the single committed baseline
  (``docs/planning/ws5_floor_baseline.json``, produced by
  ``scripts/calibrate_mutation_floors.py``). The baseline is the single source of
  truth; the values are tunable only by a reviewed PR (design 4.6, OQ-3).
- **The structural anti-clone floor.** :func:`structural_floor_reason` decides
  whether a graph-shape-changed mutant is a genuinely new tree, by the three
  design-4.6 clauses (fingerprint inequality, parent distance ``>= TAU_STRUCT``,
  and minimum in-cell distance ``>= TAU_CELL``). :func:`load_in_cell_catalog`
  discovers the sibling catalog trees that clause 3 compares against.

The floor can only REJECT (design CR-2): every entry point returns either a
discard reason or ``None``; nothing here constructs a gate result, moves a
threshold, or admits a candidate the gate blocked. The M5-only (graph-shape-
unchanged) case uses the state-signature floor in ``state_ops.py`` instead, which
reads ``TAU_STATE`` from here.

Pure module: standard library plus the ``diversity`` and ``generation``
skeleton-discovery surfaces the design permits (section 4.1). It imports nothing
from ``db``, ``validator``'s report/threshold surface, or ``network``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

from cyo_adventure.diversity.structure import structural_distance, structure_fingerprint
from cyo_adventure.generation.skeleton import is_sidecar
from cyo_adventure.storybook.models import StoryMetadata
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

# The repository root, resolved from this file so both the baseline load and the
# catalog scan are cwd-independent. The catalog root mirrors
# ``generation.skeleton_match._SKELETON_ROOT`` by value ("skeletons/<band>"),
# reimplemented here so the pure mutation layer pulls in no ``db``/``sqlalchemy``
# dependency (design section 4.1 layering discipline).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SKELETON_ROOT = _REPO_ROOT / "skeletons"

# Bands where the narrative-style axis is meaningful (ADR-011), mirroring
# ``skeleton_match._STYLE_AWARE_BANDS``; below these, style collapses to prose.
_STYLE_AWARE_BANDS = frozenset({"13-16", "16+"})

# The committed baseline artifact, resolved from this file so the load is
# cwd-independent (design 4.6: the single source of the floor thresholds).
_BASELINE_PATH = _REPO_ROOT / "docs" / "planning" / "ws5_floor_baseline.json"

# Documented conservative fallbacks, used only when the committed baseline is
# absent (the pre-calibration bootstrap). They match the calibrator's clamp
# minima, so a missing baseline degrades to the strictest safe floors rather than
# a clone-admitting 0. The committed baseline always overrides these in practice.
_FALLBACK_TAU_STRUCT = 0.01
_FALLBACK_TAU_CELL = 0.01
_FALLBACK_TAU_STATE = 0.25


def _load_thresholds() -> tuple[float, float, float]:
    """Return ``(TAU_STRUCT, TAU_CELL, TAU_STATE)`` from the committed baseline.

    Returns:
        tuple[float, float, float]: The calibrated thresholds, or the documented
            conservative fallbacks when the baseline file is absent.
    """
    if not _BASELINE_PATH.is_file():
        get_logger(__name__).warning(
            "mutation.floor_baseline_missing",
            path=str(_BASELINE_PATH),
            note="using conservative fallback floors; run calibrate_mutation_floors",
        )
        return (_FALLBACK_TAU_STRUCT, _FALLBACK_TAU_CELL, _FALLBACK_TAU_STATE)
    data = cast(
        "dict[str, object]",
        json.loads(_BASELINE_PATH.read_text(encoding="utf-8")),
    )
    tau_struct = float(cast("float", data["tau_struct"]))
    tau_cell = float(cast("float", data["tau_cell"]))
    tau_state = float(cast("float", data["tau_state"]))
    return (tau_struct, tau_cell, tau_state)


# The calibrated floors, loaded once from the committed baseline. Design 4.6:
# TAU_CELL <= TAU_STRUCT (a mutant far enough from its parent may still clone a
# sibling). TAU_STATE (design 5.4) is re-exported for state_ops.py.
TAU_STRUCT, TAU_CELL, TAU_STATE = _load_thresholds()


def _matches_cell(
    metadata: StoryMetadata, *, band: str, length: str, style: str
) -> bool:
    """Return whether a skeleton's metadata matches a ``(band, length, style)`` cell.

    Mirrors ``generation.skeleton_match.skeleton_matches_cell`` by value: a
    length-less skeleton is a wildcard, and narrative style is matched only for
    the two teen bands.

    Args:
        metadata: The sibling skeleton's typed metadata.
        band: The candidate's age band.
        length: The candidate's length.
        style: The candidate's narrative style.

    Returns:
        bool: True when the sibling shares the candidate's cell.
    """
    if metadata.age_band != band:
        return False
    if metadata.length is not None and metadata.length != length:
        return False
    return band not in _STYLE_AWARE_BANDS or metadata.narrative_style == style


def load_in_cell_catalog(  # noqa: C901 -- one cohesive sibling-catalog scan with per-file skips
    candidate: Mapping[str, object], parent_slug: str
) -> list[dict[str, object]]:
    """Return the in-cell catalog trees a mutant must not clone (design 4.6).

    Discovers every production-eligible catalog skeleton that shares the
    candidate's ``(age_band, length, narrative_style)`` cell, EXCLUDING the parent
    (by slug and by structural identity) and any MVP seed (``production_eligible``
    false). Reuses the ``skeleton_match`` discovery convention and the shared
    :func:`~cyo_adventure.generation.skeleton.is_sidecar` skip (contracts and
    lineage records).

    Args:
        candidate: The mutated candidate document (its declared cell is used).
        parent_slug: The parent's catalog slug, excluded from the comparison set.

    Returns:
        list[dict[str, object]]: The sibling in-cell skeleton documents; empty
            when the candidate declares no cell or the cell has no other tree
            (clause 3 is then vacuously satisfied).
    """
    # #ASSUME: external-resources: the in-cell catalog is read from
    # ``skeletons/<band>/*.json`` under the same repository-root convention the
    # selector uses (skeleton_match._SKELETON_ROOT). The acceptance harness runs
    # catalog-time from the repository root (design section 6 #ASSUME).
    # #VERIFY: tests/unit/test_mutation_floors.py loads a real in-cell cohort and
    # asserts the parent and MVP seeds are excluded.
    meta_raw = candidate.get("metadata")
    if not isinstance(meta_raw, dict):
        return []
    typed_meta = cast("dict[str, object]", meta_raw)
    band = typed_meta.get("age_band")
    length = typed_meta.get("length")
    style = typed_meta.get("narrative_style")
    if not (
        isinstance(band, str) and isinstance(length, str) and isinstance(style, str)
    ):
        return []

    band_dir = _SKELETON_ROOT / band
    if not band_dir.is_dir():
        return []

    siblings: list[dict[str, object]] = []
    for path in sorted(band_dir.glob("*.json")):
        if is_sidecar(path) or path.stem == parent_slug:
            continue
        try:
            document = cast(
                "dict[str, object]",
                json.loads(path.read_text(encoding="utf-8")),
            )
        except (OSError, json.JSONDecodeError):
            continue
        meta = document.get("metadata")
        if not isinstance(meta, dict):
            continue
        try:
            typed = StoryMetadata.model_validate(meta)
        except ValueError:
            continue
        if not typed.production_eligible:
            continue
        if not _matches_cell(typed, band=band, length=length, style=style):
            continue
        siblings.append(document)
    return siblings


def _excluding_parent(
    parent: Mapping[str, object], siblings: Sequence[Mapping[str, object]]
) -> list[Mapping[str, object]]:
    """Return ``siblings`` with any structural duplicate of ``parent`` removed."""
    parent_fp = structure_fingerprint(parent)
    return [s for s in siblings if structure_fingerprint(s) != parent_fp]


def structural_floor_reason(
    parent: Mapping[str, object],
    candidate: Mapping[str, object],
    in_cell: Sequence[Mapping[str, object]],
) -> str | None:
    """Return why a shape-changed mutant fails the anti-clone floor, or None.

    Applies the three design-4.6 clauses in order; the first failure is the
    returned discard reason:

    1. ``structure_fingerprint(candidate) != structure_fingerprint(parent)`` -- a
       pure structural-identity check. An M2-only re-map passes this clause
       (``structure_fingerprint`` retains ending kind/id) but fails clause 2.
    2. ``structural_distance(parent, candidate) >= TAU_STRUCT`` -- the mutant must
       sit a meaningful structural distance from its parent. An M2-only re-map is
       rejected HERE (its histograms are permutation-invariant, so its distance is
       ~0), by the distance clause, not the fingerprint clause.
    3. ``min over in-cell sibling s of structural_distance(s, candidate) >=
       TAU_CELL`` -- the mutant must not clone ANY existing in-cell tree. When the
       cell has no other tree the clause is vacuously satisfied.

    Reject-only (design CR-2, 4.6): a passing candidate returns ``None`` (the
    floor never raises promotability); a cloning candidate returns a reason.

    Args:
        parent: The raw parent story document.
        candidate: The mutated candidate document (graph shape changed).
        in_cell: The sibling in-cell catalog documents (see
            :func:`load_in_cell_catalog`); the parent is removed defensively.

    Returns:
        str | None: A discard reason when any clause fails, else None.
    """
    # #CRITICAL: data-integrity: this is the structural analog of the anti-clone
    # floor (design 4.6). It is reject-only: it can lower a candidate's
    # promotability (a near-isomorphic copy is not a distinct tree) but never
    # raise it, so a calibrated threshold carries no safety risk (design CR-2,
    # floors reject-only). The gate stages remain mandatory upstream.
    # #VERIFY: tests/unit/test_mutation_floors.py pins that an M2-only re-map is
    # rejected by the DISTANCE clause (clause 2), a fingerprint-equal candidate by
    # clause 1, and an in-cell clone by clause 3; a genuine structural mutant
    # passes.
    if structure_fingerprint(candidate) == structure_fingerprint(parent):
        return (
            "structural fingerprint equals the parent's: the mutation left the "
            "gate-relevant structure unchanged (design 4.6 clause 1)"
        )
    parent_distance = structural_distance(parent, candidate)
    if parent_distance < TAU_STRUCT:
        return (
            f"structural distance to the parent {parent_distance:.4f} is below "
            f"TAU_STRUCT {TAU_STRUCT}: too near-isomorphic to count as a new tree "
            f"(design 4.6 clause 2)"
        )
    for sibling in _excluding_parent(parent, in_cell):
        distance = structural_distance(sibling, candidate)
        if distance < TAU_CELL:
            return (
                f"structural distance to an in-cell catalog tree {distance:.4f} is "
                f"below TAU_CELL {TAU_CELL}: the mutant clones an existing sibling "
                f"tree (design 4.6 clause 3)"
            )
    return None
