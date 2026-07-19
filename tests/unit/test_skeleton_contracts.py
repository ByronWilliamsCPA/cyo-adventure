"""Catalog-wide drift guard for WS-2 theme contracts.

Iterates every ``skeletons/<band>/<slug>.contract.json`` sidecar on disk and
asserts the deterministic acceptance properties from
``docs/planning/ws2-parameterized-catalog-design.md`` section 9.3 (checks 1-4
plus the render post-conditions). This makes post-migration drift fail CI
permanently: a skeleton edited without its contract (a new/renamed token, a
removed slot, a default value that no longer satisfies its own constraints)
breaks one of these assertions.

Pure and fast: no LLM, no database, no network. Reuses the same framework
functions the offline ``scripts/check_theme_contract.py`` runner uses, so the
in-repo catalog is held to exactly the acceptance bar every migration passed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.generation.binding import load_contract_for, render_bound_skeleton
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.slots import BUNDLE_IDS, validate_slot_bindings

if TYPE_CHECKING:
    from cyo_adventure.storybook.theme_contract import ThemeContract

# The catalog root, resolved relative to this test file rather than the cwd, so
# the test is location-independent (repo root is three parents up from
# tests/unit/).
_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"

_CONTRACT_PATHS = sorted(_SKELETONS_ROOT.glob("*/*.contract.json"))


def _skeleton_path_for(contract_path: Path) -> Path:
    """Return the skeleton path a contract sidecar constrains.

    ``<slug>.contract.json`` -> ``<slug>.json`` in the same band directory.

    Args:
        contract_path: The ``*.contract.json`` sidecar path.

    Returns:
        The sibling skeleton ``.json`` path.
    """
    slug = contract_path.name.removesuffix(".contract.json")
    return contract_path.with_name(f"{slug}.json")


def _load_skeleton(contract_path: Path) -> tuple[dict[str, object], ThemeContract]:
    """Load the skeleton dict and its cross-checked contract for a sidecar.

    Args:
        contract_path: The contract sidecar path.

    Returns:
        The decoded skeleton dict and the validated :class:`ThemeContract`.
    """
    skeleton_path = _skeleton_path_for(contract_path)
    skeleton = cast(
        "dict[str, object]",
        json.loads(skeleton_path.read_text(encoding="utf-8")),
    )
    contract = load_contract_for(skeleton_path, skeleton)
    assert contract is not None, f"no contract loaded for {skeleton_path}"
    return skeleton, contract


def test_the_catalog_has_theme_contracts() -> None:
    """Guard the guard: fail loudly if the discovery glob finds nothing.

    A refactor that moved the catalog or changed the sidecar naming would
    otherwise make every parametrized test below silently vanish.
    """
    assert _CONTRACT_PATHS, f"no *.contract.json found under {_SKELETONS_ROOT}"


@pytest.mark.parametrize("contract_path", _CONTRACT_PATHS, ids=lambda p: p.stem)
def test_skeleton_gates_clean(contract_path: Path) -> None:
    """Check 1: the parameterized skeleton itself passes the blocking gate."""
    skeleton, _ = _load_skeleton(contract_path)
    result = run_gate(skeleton)
    assert not result.blocked, f"{contract_path.stem} is gate-blocked: " + "; ".join(
        finding.message for finding in result.report.errors
    )


@pytest.mark.parametrize("contract_path", _CONTRACT_PATHS, ids=lambda p: p.stem)
def test_contract_loads_and_token_set_matches(contract_path: Path) -> None:
    """Check 2: the contract loads and its slot ids match the skeleton tokens.

    ``load_contract_for`` raises on any drift between the skeleton's ``{SLOT}``
    tokens and the contract's declared slot ids, so a successful load IS the
    cross-check.
    """
    _, contract = _load_skeleton(contract_path)
    assert contract.slots, f"{contract_path.stem} declares no slots"


@pytest.mark.parametrize("contract_path", _CONTRACT_PATHS, ids=lambda p: p.stem)
def test_declared_forbid_bundle_ids_are_known(contract_path: Path) -> None:
    """Check 3: every declared ``forbid`` bundle id is a real bundle."""
    _, contract = _load_skeleton(contract_path)
    unknown = sorted(
        {
            bundle_id
            for slot in contract.slots
            for bundle_id in slot.constraints.forbid
            if bundle_id not in BUNDLE_IDS
        }
    )
    assert not unknown, f"{contract_path.stem} declares unknown bundle(s): {unknown}"


@pytest.mark.parametrize("contract_path", _CONTRACT_PATHS, ids=lambda p: p.stem)
def test_default_binding_passes_its_own_contract(contract_path: Path) -> None:
    """Check 4: the original theme's ``default_binding`` satisfies the contract.

    ``is_default=True`` exempts only the ``legacy_lexicon`` leak check (the
    default binding IS the original theme, whose identity terms populate
    ``legacy_lexicon``); every other constraint still applies.
    """
    _, contract = _load_skeleton(contract_path)
    violations = validate_slot_bindings(
        contract, contract.default_binding, is_default=True
    )
    assert not violations, (
        f"{contract_path.stem} default_binding violates its own contract: "
        + "; ".join(f"{v.slot_id}:{v.rule}" for v in violations)
    )


@pytest.mark.parametrize("contract_path", _CONTRACT_PATHS, ids=lambda p: p.stem)
def test_default_binding_renders_with_no_residual_tokens(contract_path: Path) -> None:
    """The render post-conditions hold for the golden default binding.

    ``render_bound_skeleton`` raises on any post-condition failure (residual
    token, structural-fingerprint drift, blocked gate, or a mutated FILL
    directive), so a clean return is the assertion.
    """
    skeleton, contract = _load_skeleton(contract_path)
    render_bound_skeleton(skeleton, contract.default_binding)
