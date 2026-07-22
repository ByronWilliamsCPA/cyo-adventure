"""Tests for the WS-5 D7 anti-clone / state floors and contract acceptance.

Covers the calibrated baseline load and reproducibility (mutation/floors.py +
scripts/calibrate_mutation_floors.py), the degenerate-threshold clamp, the three
design-4.6 structural-floor clauses (including the M2 fingerprint-vs-distance
subtlety), the in-cell catalog loader, and stage-4 contract acceptance including
the load-bearing CR-4 band-floor pin (a mutated contract can never weaken the
band-mandatory denylist floor).
"""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from typing import cast

import pytest

from cyo_adventure.diversity.structure import structural_distance, structure_fingerprint
from cyo_adventure.generation.binding import load_contract_for
from cyo_adventure.mutation import state_ops
from cyo_adventure.mutation.contract_gate import contract_acceptance_reason
from cyo_adventure.mutation.floors import (
    TAU_CELL,
    TAU_STATE,
    TAU_STRUCT,
    load_in_cell_catalog,
    structural_floor_reason,
)
from cyo_adventure.mutation.operators import M2, M4
from cyo_adventure.mutation.ops import OpParams
from cyo_adventure.storybook.theme_contract import ThemeContract
from cyo_adventure.validator.slots import (
    BUNDLE_PROBES,
    band_mandatory_bundles,
    validate_slot_bindings,
)
from scripts import calibrate_mutation_floors as calib

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"
_BASELINE_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "planning"
    / "ws5_floor_baseline.json"
)


def _load(slug_path: str) -> dict[str, object]:
    """Load one catalog skeleton by its ``band/slug.json`` path."""
    return cast(
        "dict[str, object]",
        json.loads((_SKELETONS_ROOT / slug_path).read_text(encoding="utf-8")),
    )


def _first_m2_parent() -> tuple[str, dict[str, object]]:
    """Return the first catalog skeleton M2 accepts with default params."""
    for path in sorted(_SKELETONS_ROOT.glob("*/*.json")):
        if path.name.endswith(".contract.json"):
            continue
        story = cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))
        if M2.preconditions(story, OpParams.of()).satisfied:
            return path.stem, story
    pytest.skip("no M2-eligible parent in the catalog")


# --- The calibrated baseline ---


@pytest.mark.unit
def test_calibrated_floors_are_positive_and_ordered() -> None:
    """The loaded floors are strictly positive and TAU_CELL <= TAU_STRUCT (design 4.6)."""
    assert TAU_STRUCT > 0.0
    assert TAU_CELL > 0.0
    assert TAU_STATE > 0.0
    assert TAU_CELL <= TAU_STRUCT


@pytest.mark.unit
def test_state_floor_tau_equals_the_committed_baseline() -> None:
    """state_ops._TAU_STATE is the calibrated baseline value, not the D6 provisional."""
    baseline = cast(
        "dict[str, object]",
        json.loads(_BASELINE_PATH.read_text(encoding="utf-8")),
    )
    assert state_ops._TAU_STATE == TAU_STATE  # pyright: ignore[reportPrivateUsage]
    assert state_ops._TAU_STATE_IS_PROVISIONAL is False  # pyright: ignore[reportPrivateUsage]
    assert baseline["tau_state"] == TAU_STATE
    assert baseline["tau_struct"] == TAU_STRUCT
    assert baseline["tau_cell"] == TAU_CELL


@pytest.mark.unit
def test_calibration_is_deterministic_and_committed_baseline_is_current() -> None:
    """compute_baseline is reproducible and the committed baseline is not stale."""
    first = calib.compute_baseline()
    second = calib.compute_baseline()
    assert calib._serialize(first) == calib._serialize(second)  # pyright: ignore[reportPrivateUsage]
    # --check exits 0 against the committed artifact (no drift).
    assert calib.main(["--check"]) == 0


@pytest.mark.unit
def test_tau_cell_ships_the_fixed_floor_not_the_degenerate_observed_minimum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TAU_CELL ships as the fixed anti-duplication floor, never the observed minimum.

    ADR-020 floor-recalibration amendment: TAU_CELL is a fixed owner-chosen
    anti-duplication floor (0.05), so a same-cell distribution whose minimum is a
    near-duplicate (0.0) can never ship a clone-admitting TAU_CELL. The fixed value
    is shipped and the observed minimum is recorded in the clamps note. TAU_STATE's
    own anti-no-op clamp is unchanged.
    """
    monkeypatch.setattr(
        calib, "_same_cell_distances", lambda _catalog: [0.0, 0.004, 0.5]
    )
    monkeypatch.setattr(
        calib, "_cross_tier2_state_distances", lambda _catalog: [0.1, 0.2]
    )
    baseline = calib.compute_baseline()
    clamps = cast("list[str]", baseline["clamps"])
    assert clamps  # the observed minimum is recorded, not silently shipped
    assert baseline["tau_cell"] == calib._TAU_CELL_FLOOR  # pyright: ignore[reportPrivateUsage]
    assert cast("float", baseline["tau_cell"]) > 0.004  # never the near-duplicate min
    # min cross state 0.1 -> 0.05 < 0.25, clamped up to the documented minimum.
    assert baseline["tau_state"] == calib._MIN_STATE_FLOOR  # pyright: ignore[reportPrivateUsage]


# --- The structural anti-clone floor (design 4.6, three clauses) ---


@pytest.mark.unit
def test_structural_floor_clause1_rejects_a_fingerprint_equal_candidate() -> None:
    """A leaf-only change leaves the structural fingerprint equal: clause 1 rejects."""
    parent = _load("8-11/the-cave-of-echoes.json")
    candidate = copy.deepcopy(parent)
    # Change a node body only (leaf content): structure_fingerprint is unchanged.
    cast("list[dict[str, object]]", candidate["nodes"])[0]["body"] = "reworded prose"
    assert structure_fingerprint(candidate) == structure_fingerprint(parent)
    reason = structural_floor_reason(parent, candidate, [])
    assert reason is not None
    assert "fingerprint" in reason


@pytest.mark.unit
@pytest.mark.security
def test_structural_floor_rejects_an_m2_only_remap_as_a_near_parent_clone() -> None:
    """An M2-only re-map (distance ~0 from its parent) is rejected as a near-parent clone.

    ADR-020 floor-recalibration amendment: the parent is compared as an in-cell
    tree, so an M2-only re-map -- whose permutation-invariant ending histograms
    leave its structural_distance from the parent ~0 -- is rejected by the
    anti-duplication clause (< TAU_CELL), NOT by the retired parent-distance-vs-
    TAU_STRUCT clause. Its fingerprint differs (kinds moved between leaves), so
    clause 1 does not fire. The empty sibling cohort proves the parent itself is
    the tree it clones.
    """
    _slug, parent = _first_m2_parent()
    candidate = M2.apply(parent, OpParams.of(), random.Random(0)).candidate
    # Clause 1 does not fire: the fingerprint differs (kinds moved between leaves).
    assert structure_fingerprint(candidate) != structure_fingerprint(parent)
    # It sits below TAU_CELL from its parent (permutation-invariant histograms).
    assert structural_distance(parent, candidate) < TAU_CELL
    reason = structural_floor_reason(parent, candidate, [])
    assert reason is not None
    assert "near-duplicate of an existing in-cell tree" in reason
    assert "TAU_CELL" in reason
    # Rejected by the anti-duplication clause, not the fingerprint clause.
    assert "fingerprint equals" not in reason


@pytest.mark.unit
def test_structural_floor_clause3_rejects_an_in_cell_clone() -> None:
    """A mutant far from its parent but cloning a SIBLING is rejected by clause 3."""
    parent = _load("10-13/the-cinderwick-exchange.json")
    sibling = _load("10-13/the-flooded-quarter.json")
    candidate = copy.deepcopy(sibling)
    cast("list[dict[str, object]]", candidate["nodes"])[0]["body"] = "reworded prose"
    # Clause 1/2 pass: the candidate is a different, far tree from the parent.
    assert structure_fingerprint(candidate) != structure_fingerprint(parent)
    assert structural_distance(parent, candidate) >= TAU_STRUCT
    # But it clones the sibling (leaf-only edit => distance 0 to it): clause 3.
    reason = structural_floor_reason(parent, candidate, [sibling])
    assert reason is not None
    assert "in-cell catalog tree" in reason
    assert "TAU_CELL" in reason


@pytest.mark.unit
def test_structural_floor_passes_a_genuine_distinct_mutant() -> None:
    """A structurally distinct candidate with no in-cell clone clears the floor."""
    parent = _load("10-13/the-cinderwick-exchange.json")
    candidate = _load("10-13/the-flooded-quarter.json")
    assert structural_distance(parent, candidate) >= TAU_STRUCT
    # Empty in-cell cohort => clause 3 vacuously satisfied (documented).
    assert structural_floor_reason(parent, candidate, []) is None


@pytest.mark.unit
def test_load_in_cell_catalog_excludes_the_parent_and_mvp_seeds() -> None:
    """The in-cell cohort omits the parent (by structure) and every non-production seed."""
    cave = _load("8-11/the-cave-of-echoes.json")
    siblings = load_in_cell_catalog(cave, "the-cave-of-echoes")
    assert siblings  # the 8-11 short cell has other trees
    parent_fp = structure_fingerprint(cave)
    assert all(structure_fingerprint(s) != parent_fp for s in siblings)
    assert all(
        cast("dict[str, object]", s.get("metadata", {})).get("production_eligible")
        is not False
        for s in siblings
    )


# --- Stage 4 contract acceptance (design 4.7, CR-4) ---


def _cave_contract() -> ThemeContract:
    """Return the-cave-of-echoes theme contract (a parameterized 8-11 parent)."""
    cave_path = _SKELETONS_ROOT / "8-11" / "the-cave-of-echoes.json"
    contract = load_contract_for(cave_path, _load("8-11/the-cave-of-echoes.json"))
    assert contract is not None
    return contract


@pytest.mark.unit
def test_slot_preserving_mutant_carries_the_parent_contract_through_stage4() -> None:
    """An M4 insert-linear (fresh non-slotted node) carries the parent contract clean."""
    cave = _load("8-11/the-cave-of-echoes.json")
    candidate = M4.apply(
        cave, OpParams.of(mode="insert-linear", choice="c_left"), random.Random(0)
    ).candidate
    assert contract_acceptance_reason(candidate, _cave_contract()) is None


@pytest.mark.unit
def test_contract_stage_rejects_a_slot_token_set_mismatch() -> None:
    """A candidate missing a declared slot's tokens fails stage 4 (token-set drift)."""
    cave = _load("8-11/the-cave-of-echoes.json")
    contract = _cave_contract()
    # Rebuild the contract with one extra declared slot the skeleton never uses.
    raw = contract.model_dump()
    raw["slots"].append(
        {
            "id": "GHOST_SLOT",
            "scope": "global",
            "meaning": "unused",
            "guidance": "unused",
            "constraints": {"max_words": 3, "forbid": [], "distinct_from": []},
        }
    )
    raw["default_binding"]["GHOST_SLOT"] = "phantom"
    drifted = ThemeContract.model_validate(raw)
    reason = contract_acceptance_reason(cave, drifted)
    assert reason is not None
    assert "slot id set does not match" in reason


@pytest.mark.unit
@pytest.mark.security
def test_cr4_a_weakened_forbid_list_cannot_defeat_the_band_floor() -> None:
    """CR-4 (design 14): a mutated contract with an emptied forbid still fails a floor
    violation.

    ``validate_slot_bindings`` unions ``band_mandatory_bundles`` regardless of
    contract content, so stripping every slot's ``forbid`` list cannot open a
    band-floor safety hole. This is the load-bearing children's-safety pin for
    parameterized mutants.
    """
    contract = _cave_contract()
    floor = band_mandatory_bundles(contract.age_band)
    assert "lethal" in floor  # 8-11 mandates the lethal denylist
    # Weaken the contract: drop every declared forbid bundle from every slot.
    raw = contract.model_dump()
    for slot in raw["slots"]:
        slot["constraints"]["forbid"] = []
    weakened = ThemeContract.model_validate(raw)
    target = weakened.slots[0].id
    bindings = dict(weakened.default_binding)
    bindings[target] = BUNDLE_PROBES["lethal"]
    violations = validate_slot_bindings(weakened, bindings)
    assert any(v.rule == "forbid:lethal" and v.slot_id == target for v in violations), (
        "the band-mandatory lethal floor must still bite on a weakened contract"
    )
