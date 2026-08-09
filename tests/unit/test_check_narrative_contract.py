"""Unit tests for scripts/check_narrative_contract.py (NC checks, redesign pilot)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_narrative_contract import (
    check_bible,
    check_contract,
    check_selection,
)

_SKELETON = {
    "start_node": "a",
    "nodes": [
        {
            "id": "a",
            "choices": [{"id": "c_ab", "target": "b"}, {"id": "c_ac", "target": "c"}],
        },
        {
            "id": "b",
            "choices": [{"id": "c_bd", "target": "d"}, {"id": "c_ba", "target": "a"}],
        },
        {"id": "c", "choices": [{"id": "c_cd", "target": "d"}]},
        {"id": "d", "ending": {"kind": "success", "valence": "positive"}},
    ],
}


def _contract(nodes: dict[str, dict[str, object]]) -> dict[str, object]:
    return {"facts": {"f1": "", "f2": "", "f3": ""}, "nodes": nodes}


@pytest.mark.unit
def test_nc1_flags_entry_state_not_guaranteed_on_every_path() -> None:
    """d presupposes f2, but only parent b establishes it; parent c does not."""
    contract = _contract(
        {
            "a": {
                "tier": "open",
                "establishes": ["f1"],
                "reentrant": True,
                "reentry_contract": "x",
            },
            "b": {
                "tier": "open",
                "establishes": ["f2"],
                "reentrant": True,
                "reentry_contract": "x",
            },
            "c": {"tier": "open", "establishes": ["f3"]},
            "d": {"tier": "open", "entry_state": ["f2"], "establishes": ["f1"]},
        }
    )
    errors, _ = check_contract(_SKELETON, contract)
    assert any("NC-1" in e and "'d'" in e for e in errors)


@pytest.mark.unit
def test_nc1_passes_when_all_parents_guarantee_the_fact() -> None:
    contract = _contract(
        {
            "a": {
                "tier": "open",
                "establishes": ["f1"],
                "reentrant": True,
                "reentry_contract": "x",
            },
            "b": {
                "tier": "open",
                "establishes": ["f2"],
                "reentrant": True,
                "reentry_contract": "x",
            },
            "c": {"tier": "open", "establishes": ["f2"]},
            "d": {"tier": "open", "entry_state": ["f1", "f2"], "establishes": ["f3"]},
        }
    )
    errors, _ = check_contract(_SKELETON, contract)
    assert not [e for e in errors if "NC-1" in e]


@pytest.mark.unit
def test_nc4_requires_reentrant_flag_on_cycle_nodes() -> None:
    """a and b sit on a cycle (a->b->a); omitting the flag is an error (AL-155)."""
    contract = _contract(
        {
            "a": {"tier": "open", "establishes": ["f1"]},
            "b": {"tier": "open", "establishes": ["f2"]},
            "c": {"tier": "open", "establishes": ["f3"]},
            "d": {"tier": "open", "establishes": ["f1"]},
        }
    )
    errors, _ = check_contract(_SKELETON, contract)
    assert any("NC-4" in e and "'a'" in e for e in errors)
    assert any("NC-4" in e and "'b'" in e for e in errors)


@pytest.mark.unit
def test_nc5_rejects_forbidden_device_kind_and_unsafe_string() -> None:
    contract = {
        "safety_envelope": {"permitted_device_kinds": ["testimony"]},
        "nodes": {},
        "facts": {},
    }
    bible = {
        "device_vocabulary": {
            "clue_channels": [{"text": "a {SLOT} marker", "kind": "deception"}]
        }
    }
    errors, _ = check_bible(bible, contract, "3-5")
    assert any("kind 'deception'" in e for e in errors)
    assert any("forbidden token" in e for e in errors)


@pytest.mark.unit
def test_nc7_label_style_must_come_from_contract_list() -> None:
    contract = {
        "label_styles": ["plain verbs", "sensory-first"],
        "nodes": {},
        "facts": {},
    }
    bible = {"device_vocabulary": {}}
    errors, _ = check_selection({"label_style": "plain verbs"}, contract, bible)
    assert errors == []
    errors, _ = check_selection({"label_style": "rhyming couplets"}, contract, bible)
    assert any("label_style" in e for e in errors)


@pytest.mark.unit
def test_the_pilot_contract_is_coherent() -> None:
    root = Path(__file__).resolve().parent.parent.parent
    skeleton = json.loads((root / "skeletons/3-5/the-lost-mitten.json").read_text())
    contract = json.loads(
        (root / "skeletons/3-5/the-lost-mitten.narrative.json").read_text()
    )
    errors, _ = check_contract(skeleton, contract)
    assert errors == []
