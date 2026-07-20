"""Branch-coverage tests for stage-4 contract acceptance (WS-5 D7 follow-up).

Targets the error, mismatch, and probe-selection branches of
``mutation/contract_gate.py`` that ``test_mutation_floors.py`` does not reach:
the three-surface token scanner on malformed skeletons, ``_pick_probe``'s
declared-forbid and unconstrained-mature paths, and every reject branch of
``contract_acceptance_reason`` (gate-blocked candidate, unknown forbid bundle, a
default_binding that fails its own contract, a probe that does not bite, and a
render that fails or leaves residual tokens). The last three are wired through
targeted monkeypatches, since a correctly-calibrated contract never reaches
them; each patch is a narrow stand-in for a genuinely defensive branch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.binding import load_contract_for
from cyo_adventure.mutation import contract_gate
from cyo_adventure.mutation.contract_gate import (
    _pick_probe,  # pyright: ignore[reportPrivateUsage]
    _slotted_surface_tokens,  # pyright: ignore[reportPrivateUsage]
    contract_acceptance_reason,
)
from cyo_adventure.storybook.theme_contract import ThemeContract

if TYPE_CHECKING:
    from collections.abc import Mapping

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"


def _load(slug_path: str) -> dict[str, object]:
    """Load one catalog skeleton by its ``band/slug.json`` path."""
    return cast(
        "dict[str, object]",
        json.loads((_SKELETONS_ROOT / slug_path).read_text(encoding="utf-8")),
    )


def _cave_contract() -> ThemeContract:
    """Return the-cave-of-echoes theme contract (a parameterized 8-11 parent)."""
    cave_path = _SKELETONS_ROOT / "8-11" / "the-cave-of-echoes.json"
    contract = load_contract_for(cave_path, _load("8-11/the-cave-of-echoes.json"))
    assert contract is not None
    return contract


def _mature_contract(*, forbid: list[str]) -> ThemeContract:
    """Return a hand-built 13-16 contract (band-floor-free) with one slot."""
    return ThemeContract.model_validate(
        {
            "contract_version": 1,
            "skeleton_slug": "hand-built",
            "age_band": "13-16",
            "default_binding": {"HERO": "Ari"},
            "slots": [
                {
                    "id": "HERO",
                    "scope": "global",
                    "meaning": "the hero",
                    "guidance": "",
                    "constraints": {
                        "max_words": 3,
                        "forbid": forbid,
                        "distinct_from": [],
                    },
                }
            ],
        }
    )


# --- _slotted_surface_tokens on malformed skeletons ---


@pytest.mark.unit
def test_slotted_surface_tokens_tolerates_malformed_surfaces() -> None:
    """A non-list nodes field, junk nodes, and off-type surfaces yield no tokens."""
    assert _slotted_surface_tokens({"nodes": "not-a-list"}) == frozenset()
    skeleton: dict[str, object] = {
        "nodes": [
            42,
            {"body": 7},
            {"body": "plain body, no fill directive"},
            {"ending": {"title": 9}},
            {"choices": [3, {"label": 11}]},
        ]
    }
    assert _slotted_surface_tokens(skeleton) == frozenset()


@pytest.mark.unit
def test_slotted_surface_tokens_reads_the_three_legal_surfaces() -> None:
    """A FILL beats token, an ending title token, and a choice label token are found."""
    skeleton: dict[str, object] = {
        "nodes": [
            {"body": "<<FILL role=body words=10 beats='meet {HERO}'>>"},
            {"ending": {"title": "the {PLACE}"}},
            {"choices": [{"label": "follow {ALLY}"}]},
        ]
    }
    assert _slotted_surface_tokens(skeleton) == frozenset({"HERO", "PLACE", "ALLY"})


# --- _pick_probe selection ladder ---


@pytest.mark.unit
def test_pick_probe_uses_a_declared_forbid_when_no_gate_or_floor() -> None:
    """A band-floor-free contract falls back to a slot's own declared forbid bundle."""
    probe = _pick_probe(_mature_contract(forbid=["lethal"]))
    assert probe is not None
    slot, bundle = probe
    assert slot.id == "HERO"
    assert bundle == "lethal"


@pytest.mark.unit
def test_pick_probe_returns_none_for_an_unconstrained_mature_contract() -> None:
    """A mature reskin with no gate, floor, or forbid is legitimately unprobed."""
    assert _pick_probe(_mature_contract(forbid=[])) is None


# --- contract_acceptance_reason reject branches ---


@pytest.mark.unit
def test_contract_acceptance_rejects_a_gate_blocked_skeleton() -> None:
    """A structurally-broken candidate is caught by the stage-4 gate re-run."""
    reason = contract_acceptance_reason({}, _cave_contract())
    assert reason is not None
    assert "gate-blocked" in reason


@pytest.mark.unit
def test_contract_acceptance_rejects_an_unknown_forbid_bundle() -> None:
    """A contract naming a forbid bundle id the validator does not know fails."""
    cave = _load("8-11/the-cave-of-echoes.json")
    contract = _cave_contract()
    raw = contract.model_dump()
    cast("list[dict[str, object]]", raw["slots"])[0]["constraints"] = {
        **cast(
            "dict[str, object]",
            cast("list[dict[str, object]]", raw["slots"])[0]["constraints"],
        ),
        "forbid": ["notabundle"],
    }
    drifted = ThemeContract.model_validate(raw)
    reason = contract_acceptance_reason(cave, drifted)
    assert reason is not None
    assert "unknown forbid bundle" in reason


@pytest.mark.unit
def test_contract_acceptance_rejects_a_default_binding_that_fails_itself() -> None:
    """A default_binding value breaking its own slot constraint is rejected."""
    cave = _load("8-11/the-cave-of-echoes.json")
    contract = _cave_contract()
    raw = contract.model_dump()
    first_slot = cast("list[dict[str, object]]", raw["slots"])[0]["id"]
    binding = cast("dict[str, str]", raw["default_binding"])
    binding[cast("str", first_slot)] = " ".join(f"w{i}" for i in range(20))
    broken = ThemeContract.model_validate(raw)
    reason = contract_acceptance_reason(cave, broken)
    assert reason is not None
    assert "default_binding fails its own contract" in reason


@pytest.mark.unit
def test_contract_acceptance_passes_an_unconstrained_mature_reskin() -> None:
    """A real 13-16 skeleton with every forbid stripped renders clean (probe None)."""
    labyrinth = _load("13-16/the-labyrinth-of-glass.json")
    raw = cast(
        "dict[str, object]",
        json.loads(
            (_SKELETONS_ROOT / "13-16/the-labyrinth-of-glass.contract.json").read_text(
                encoding="utf-8"
            )
        ),
    )
    for slot in cast("list[dict[str, object]]", raw["slots"]):
        cast("dict[str, object]", slot["constraints"])["forbid"] = []
    stripped = ThemeContract.model_validate(raw)
    assert _pick_probe(stripped) is None
    assert contract_acceptance_reason(labyrinth, stripped) is None


@pytest.mark.unit
@pytest.mark.security
def test_contract_acceptance_rejects_a_probe_that_does_not_bite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the constraints do not reject a synthesized floor-violating probe, discard.

    This is the CR-4 safety net: a weakened floor must be caught. A correct
    contract always bites, so the no-bite path is forced by stubbing
    ``validate_slot_bindings`` to report no violations at all.
    """
    cave = _load("8-11/the-cave-of-echoes.json")

    def _no_violations(*_args: object, **_kwargs: object) -> list[object]:
        return []

    monkeypatch.setattr(contract_gate, "validate_slot_bindings", _no_violations)
    reason = contract_acceptance_reason(cave, _cave_contract())
    assert reason is not None
    assert "do not bite" in reason


@pytest.mark.unit
def test_contract_acceptance_rejects_a_render_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A render that raises ValidationError becomes a stage-4 discard reason."""

    def _boom(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise ValidationError("render exploded", field="binding", value=None)

    monkeypatch.setattr(contract_gate, "render_bound_skeleton", _boom)
    reason = contract_acceptance_reason(
        _load("8-11/the-cave-of-echoes.json"), _cave_contract()
    )
    assert reason is not None
    assert "render_bound_skeleton(default_binding) failed" in reason


@pytest.mark.unit
def test_contract_acceptance_rejects_a_render_with_residual_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A render that leaves an unbound ``{SLOT}`` token is rejected."""

    def _residual(
        _skeleton: Mapping[str, object], _binding: Mapping[str, str]
    ) -> dict[str, object]:
        return {"leftover": "still has {GHOST} in it"}

    monkeypatch.setattr(contract_gate, "render_bound_skeleton", _residual)
    reason = contract_acceptance_reason(
        _load("8-11/the-cave-of-echoes.json"), _cave_contract()
    )
    assert reason is not None
    assert "residual slot token" in reason
