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
# ADR-020 floor-recalibration amendment: TAU_CELL is the anti-duplication floor
# (min distance to any in-cell tree, parent included). The fallback mirrors the
# committed baseline's owner-chosen value so a missing baseline degrades safely.
_FALLBACK_TAU_CELL = 0.05
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
    # dict[str, object] has no forward reference to defer, so there is no
    # runtime cost to not quoting it in these cast() calls (see
    # review_surface.py for the same pattern); left unquoted here so the type
    # expression is not a duplicated string literal (S1192) across the module.
    data = cast(
        dict[str, object],  # noqa: TC006
        json.loads(_BASELINE_PATH.read_text(encoding="utf-8")),
    )
    tau_struct = float(cast("float", data["tau_struct"]))
    tau_cell = float(cast("float", data["tau_cell"]))
    tau_state = float(cast("float", data["tau_state"]))
    return (tau_struct, tau_cell, tau_state)


# The calibrated floors, loaded once from the committed baseline. ADR-020
# Amendment 1 (floor recalibration): the mutant-vs-parent distance clause that
# once gated on TAU_STRUCT is retired; TAU_CELL is now the in-cell
# anti-duplication floor, applied to every in-cell tree INCLUDING the parent
# (design 4.6, restated in this module's docstring). TAU_STRUCT is retained in
# the baseline (fingerprint/calibration reuse) but no longer gates promotion.
# TAU_STATE (design 5.4) is re-exported for state_ops.py.
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


def _cell_from_candidate(
    candidate: Mapping[str, object],
) -> tuple[str, str, str] | None:
    """Return the candidate's declared ``(age_band, length, narrative_style)``.

    Args:
        candidate: The mutated candidate document.

    Returns:
        tuple[str, str, str] | None: The declared cell, or None when the
            candidate's metadata is missing or not fully typed.
    """
    meta_raw = candidate.get("metadata")
    if not isinstance(meta_raw, dict):
        return None
    # dict[str, object] has no forward reference to defer, so there is no
    # runtime cost to not quoting it in these cast() calls (see
    # review_surface.py for the same pattern); left unquoted here so the type
    # expression is not a duplicated string literal (S1192) across the module.
    typed_meta = cast(dict[str, object], meta_raw)  # noqa: TC006
    band = typed_meta.get("age_band")
    length = typed_meta.get("length")
    style = typed_meta.get("narrative_style")
    if isinstance(band, str) and isinstance(length, str) and isinstance(style, str):
        return band, length, style
    return None


def _load_sibling_document(path: Path) -> dict[str, object] | None:
    """Return the parsed sibling skeleton document at ``path``, or None.

    Args:
        path: The candidate sibling skeleton file.

    Returns:
        dict[str, object] | None: The parsed document, or None when the file
            cannot be read or does not parse as JSON.
    """
    try:
        return cast(
            dict[str, object],  # noqa: TC006
            json.loads(path.read_text(encoding="utf-8")),
        )
    except (OSError, json.JSONDecodeError):
        return None


def _is_eligible_sibling(
    document: Mapping[str, object], *, band: str, length: str, style: str
) -> bool:
    """Return whether ``document`` is a production-eligible sibling in the cell.

    Args:
        document: The parsed sibling skeleton document.
        band: The candidate's age band.
        length: The candidate's length.
        style: The candidate's narrative style.

    Returns:
        bool: True when the sibling has valid, production-eligible metadata
            matching the given ``(band, length, style)`` cell.
    """
    meta = document.get("metadata")
    if not isinstance(meta, dict):
        return False
    try:
        typed = StoryMetadata.model_validate(meta)
    except ValueError:
        return False
    return typed.production_eligible and _matches_cell(
        typed, band=band, length=length, style=style
    )


def load_in_cell_catalog(
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
    cell = _cell_from_candidate(candidate)
    if cell is None:
        return []
    band, length, style = cell

    band_dir = _SKELETON_ROOT / band
    if not band_dir.is_dir():
        return []

    siblings: list[dict[str, object]] = []
    for path in sorted(band_dir.glob("*.json")):
        if is_sidecar(path) or path.stem == parent_slug:
            continue
        document = _load_sibling_document(path)
        if document is not None and _is_eligible_sibling(
            document, band=band, length=length, style=style
        ):
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

    Applies two clauses (design 4.6 as amended by the ADR-020 floor-recalibration
    amendment, ``docs/planning/ws8-floor-recalibration-proposal.md``); the first
    failure is the returned discard reason:

    1. ``structure_fingerprint(candidate) != structure_fingerprint(parent)`` -- the
       anti-no-op clause: the mutation must change the gate-relevant structure
       (topology / ending set), so a pure re-labeling never counts as a new tree.
    2. ``min over EVERY in-cell tree t, INCLUDING the parent, of
       structural_distance(t, candidate) >= TAU_CELL`` -- the anti-duplication
       clause: the mutant must not be a near-duplicate of ANY existing in-cell
       tree, its parent included (the parent is itself an in-cell tree). This
       single, correctly-scoped clause replaces the retired parent-distance-vs-
       ``TAU_STRUCT`` clause: ``TAU_STRUCT`` was the 25th percentile of same-cell
       hand-authored SIBLING-PAIR distances, which is categorically larger than
       any bounded mutation's distance from its own parent, so applying it to the
       parent distance rejected ~every mutant. Folding the parent into the
       ``TAU_CELL`` check keeps the anti-clone guarantee (an M2-only re-map, whose
       distance from the parent is ~0, is rejected HERE) at a value bounded
       mutations can actually clear. ``TAU_STRUCT`` is retained in the baseline as
       the documented hand-authored cross-tree diversity target only.

    Reject-only (design CR-2, 4.6): a passing candidate returns ``None`` (the
    floor never raises promotability); a cloning candidate returns a reason.

    Args:
        parent: The raw parent story document (compared as an in-cell tree).
        candidate: The mutated candidate document (graph shape changed).
        in_cell: The sibling in-cell catalog documents (see
            :func:`load_in_cell_catalog`), which already exclude the parent; the
            parent is added back into the comparison set here.

    Returns:
        str | None: A discard reason when any clause fails, else None.
    """
    # #CRITICAL: data-integrity: this is the structural anti-clone floor (design
    # 4.6, ADR-020 floor-recalibration amendment). It is reject-only: it can lower
    # a candidate's promotability (a near-duplicate of an existing in-cell tree is
    # not a distinct tree) but never raise it, so the calibrated TAU_CELL threshold
    # carries no safety risk (design CR-2). Nothing reaches a child without the
    # full gate + moderation + human structure approval (the promotion PR) + human
    # story approval (ADR-005); this floor is a catalog-curation bar, not a safety
    # gate. The parent is compared as an in-cell tree so a near-parent clone is
    # rejected without the retired cross-tree TAU_STRUCT parent-distance clause.
    # #VERIFY: tests/unit/test_mutation_floors.py pins that a fingerprint-equal
    # candidate is rejected by clause 1; an M2-only re-map and any near-parent or
    # near-sibling clone (< TAU_CELL) by clause 2; and that a genuine structural
    # mutant at or above TAU_CELL from the parent and every sibling passes.
    if structure_fingerprint(candidate) == structure_fingerprint(parent):
        return (
            "structural fingerprint equals the parent's: the mutation left the "
            "gate-relevant structure unchanged (design 4.6 clause 1)"
        )
    # The parent is itself an in-cell tree; compare against it plus every sibling.
    # ``in_cell`` already excludes the parent (load_in_cell_catalog), so prepend it.
    for tree in (parent, *_excluding_parent(parent, in_cell)):
        distance = structural_distance(tree, candidate)
        if distance < TAU_CELL:
            return (
                f"structural distance to an in-cell catalog tree (parent included) "
                f"{distance:.4f} is below TAU_CELL {TAU_CELL}: the mutant is a "
                f"near-duplicate of an existing in-cell tree (design 4.6 clause 2, "
                f"ADR-020 floor-recalibration amendment)"
            )
    return None
