"""Unit tests for scripts/check_theme_contract.py.

Covers the six migration acceptance checks from
``docs/planning/ws2-parameterized-catalog-design.md`` sections 8.4 and 9.3:
a good skeleton/contract pair passes everything; an unknown ``forbid``
bundle id fails check 3; a ``default_binding`` that violates its own
contract fails check 4; and a contract whose target ``_GATE`` slot does not
declare ``lethal`` (and sits at a band with no mandatory floor) fails check
5, proving the synthesized-lethal-binding check actually exercises the
contract's own constraints rather than always passing.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from cyo_adventure.diversity.structure import structure_fingerprint
from cyo_adventure.generation.binding import contract_path_for
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.theme_contract import (
    SlotConstraints,
    SlotScope,
    SlotSpec,
    ThemeContract,
)
from scripts import check_theme_contract as ctc

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _tiny_skeleton() -> dict[str, object]:
    """A tiny, gate-passing, already-parameterized fixture skeleton.

    Structurally identical to ``test_binding_render.py``'s ``_tiny_skeleton``
    (one decision node, two endings; two global-ish slots, one track slot,
    one ending slot), independently verified to pass ``run_gate`` and to
    render cleanly. The skeleton's own ``metadata.age_band`` is "3-5" (whose
    PL-17 floor a 3-node story can actually satisfy); the theme *contract*
    fixtures below independently declare their own ``age_band``, since
    nothing cross-checks the two (the contract's ``age_band`` only feeds the
    band-mandatory denylist union in ``validate_slot_bindings``).
    """
    return {
        "schema_version": "2.0",
        "id": "s_test_ctc",
        "version": 1,
        "title": "Test Story",
        "metadata": {
            "age_band": "3-5",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 1.0,
                "tolerance": 1.0,
            },
            "tier": 1,
            "themes": ["adventure"],
            "estimated_minutes": 5,
            "ending_count": 2,
            "topology": "time_cave",
            "content_flags": {
                "violence": "none",
                "scariness": "none",
                "peril": "none",
            },
        },
        "variables": [],
        "start_node": "n_start",
        "nodes": [
            {
                "id": "n_start",
                "body": (
                    "<<FILL role=setup words=40 beats='The hero, {HERO}, arrives "
                    "at {A1_GATE} and must choose a path.'>>"
                ),
                "is_ending": False,
                "choices": [
                    {
                        "id": "c_a",
                        "label": "Approach {A1_OFFER}.",
                        "target": "n_end_a",
                    },
                    {
                        "id": "c_b",
                        "label": "Turn back toward home.",
                        "target": "n_end_b",
                    },
                ],
            },
            {
                "id": "n_end_a",
                "body": (
                    "<<FILL role=ending words=30 beats='The hero claims the "
                    "prize and celebrates.'>>"
                ),
                "is_ending": True,
                "ending": {
                    "id": "e_a",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The {PRIZE}",
                },
                "choices": [],
            },
            {
                "id": "n_end_b",
                "body": (
                    "<<FILL role=ending words=30 beats='The hero returns "
                    "home safely.'>>"
                ),
                "is_ending": True,
                "ending": {
                    "id": "e_b",
                    "valence": "neutral",
                    "kind": "completion",
                    "title": "Home Again",
                },
                "choices": [],
            },
        ],
    }


_FULL_BINDINGS = {
    "HERO": "Priya",
    "A1_GATE": "the jammed hatch",
    "A1_OFFER": "a glinting tide pool",
    "PRIZE": "Glass Starfish",
}


def _slot(
    slot_id: str,
    *,
    scope: SlotScope = SlotScope.GLOBAL,
    constraints: SlotConstraints | None = None,
) -> SlotSpec:
    return SlotSpec(
        id=slot_id,
        scope=scope,
        meaning=f"placeholder meaning for {slot_id}",
        constraints=constraints or SlotConstraints(),
    )


def _well_configured_contract() -> ThemeContract:
    """A contract whose `_GATE` slot correctly declares the retreat bundles.

    Age band 13-16 has no band-mandatory denylist floor (section 3.1's
    table), so this contract's own `A1_GATE.constraints.forbid` is the only
    thing standing between a lethal binding and acceptance -- exactly what
    check 5 is designed to prove.
    """
    return ThemeContract(
        contract_version=1,
        skeleton_slug="s_test_ctc",
        age_band=AgeBand.BAND_13_16,
        legacy_lexicon=[],
        default_binding=dict(_FULL_BINDINGS),
        slots=[
            _slot("HERO", constraints=SlotConstraints(max_words=6, forbid=["weapon"])),
            _slot(
                "A1_GATE",
                scope=SlotScope.TRACK,
                constraints=SlotConstraints(
                    max_words=8, forbid=["lethal", "toxic", "weapon"]
                ),
            ),
            _slot(
                "A1_OFFER",
                scope=SlotScope.TRACK,
                constraints=SlotConstraints(max_words=8, forbid=["weapon"]),
            ),
            _slot(
                "PRIZE",
                scope=SlotScope.ENDING,
                constraints=SlotConstraints(max_words=8, forbid=["lethal", "weapon"]),
            ),
        ],
    )


def _misconfigured_contract() -> ThemeContract:
    """Same as above, but `A1_GATE` forgot to declare `lethal`.

    At age band 13-16 (no mandatory floor), a lethal `A1_GATE` binding is
    therefore NOT rejected by ``validate_slot_bindings``, so check 5 must
    fail: this is the misconfigured-contract case the check exists to catch.
    """
    contract = _well_configured_contract()
    slots = [
        slot.model_copy(update={"constraints": SlotConstraints(max_words=8)})
        if slot.id == "A1_GATE"
        else slot
        for slot in contract.slots
    ]
    return contract.model_copy(update={"slots": slots})


def _unknown_bundle_contract() -> ThemeContract:
    """A contract declaring a typo'd, unknown `forbid` bundle id."""
    contract = _well_configured_contract()
    slots = [
        slot.model_copy(
            update={
                "constraints": slot.constraints.model_copy(
                    update={"forbid": [*slot.constraints.forbid, "lehtal"]}
                )
            }
        )
        if slot.id == "A1_GATE"
        else slot
        for slot in contract.slots
    ]
    return contract.model_copy(update={"slots": slots})


def _bad_default_binding_contract() -> ThemeContract:
    """A contract whose own `default_binding` violates its declared constraints."""
    contract = _well_configured_contract()
    slots = [
        slot.model_copy(update={"constraints": SlotConstraints(max_words=1)})
        if slot.id == "HERO"
        else slot
        for slot in contract.slots
    ]
    updated = contract.model_copy(update={"slots": slots})
    # "Priya the Explorer" is 3 words, over the new max_words=1 cap.
    bindings = dict(updated.default_binding)
    bindings["HERO"] = "Priya the Explorer"
    return updated.model_copy(update={"default_binding": bindings})


def _write_pair(
    tmp_path: Path, skeleton: dict[str, object], contract: ThemeContract
) -> Path:
    skeleton_path = tmp_path / "s_test_ctc.json"
    skeleton_path.write_text(json.dumps(skeleton), encoding="utf-8")
    contract_path_for(skeleton_path).write_text(
        contract.model_dump_json(), encoding="utf-8"
    )
    return skeleton_path


def test_a_well_configured_contract_passes_every_check(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skeleton_path = _write_pair(tmp_path, _tiny_skeleton(), _well_configured_contract())

    exit_code = ctc.main([str(skeleton_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "FAIL" not in out
    assert out.count("PASS") == 6


def test_unknown_forbid_bundle_id_fails_check_3(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skeleton_path = _write_pair(tmp_path, _tiny_skeleton(), _unknown_bundle_contract())

    exit_code = ctc.main([str(skeleton_path)])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "FAIL 3." in out
    assert "lehtal" in out


def test_default_binding_violation_fails_check_4(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skeleton_path = _write_pair(
        tmp_path, _tiny_skeleton(), _bad_default_binding_contract()
    )

    exit_code = ctc.main([str(skeleton_path)])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "FAIL 4." in out


def test_misconfigured_gate_slot_fails_check_5(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skeleton_path = _write_pair(tmp_path, _tiny_skeleton(), _misconfigured_contract())

    exit_code = ctc.main([str(skeleton_path)])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "FAIL 5." in out
    # Sanity: the other checks (1, 2, 4, 6) still pass; only 5 is broken.
    assert "PASS 1." in out
    assert "PASS 4." in out
    assert "PASS 6." in out


def test_missing_contract_sidecar_fails_check_2_and_skips_the_rest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skeleton_path = tmp_path / "s_test_ctc.json"
    skeleton_path.write_text(json.dumps(_tiny_skeleton()), encoding="utf-8")

    exit_code = ctc.main([str(skeleton_path)])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "FAIL 2." in out
    assert "skipped: no contract" in out


def test_gate_blocked_skeleton_fails_check_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A structurally broken skeleton fails check 1 (no nodes at all)."""
    broken: dict[str, object] = {"schema_version": "2.0", "id": "s_bad", "nodes": []}
    skeleton_path = tmp_path / "s_test_ctc.json"
    skeleton_path.write_text(json.dumps(broken), encoding="utf-8")

    exit_code = ctc.main([str(skeleton_path)])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "FAIL 1." in out


def test_fingerprint_manifest_match_reports_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skeleton = _tiny_skeleton()
    skeleton_path = _write_pair(tmp_path, skeleton, _well_configured_contract())
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"s_test_ctc": structure_fingerprint(skeleton)}), encoding="utf-8"
    )

    exit_code = ctc.main(
        [str(skeleton_path), "--fingerprint-manifest", str(manifest_path)]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "PASS opt." in out


def test_fingerprint_manifest_mismatch_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skeleton_path = _write_pair(tmp_path, _tiny_skeleton(), _well_configured_contract())
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"s_test_ctc": "deadbeef"}), encoding="utf-8")

    exit_code = ctc.main(
        [str(skeleton_path), "--fingerprint-manifest", str(manifest_path)]
    )

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "FAIL opt." in out


def test_no_fingerprint_manifest_prints_a_skip_note_without_failing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skeleton_path = _write_pair(tmp_path, _tiny_skeleton(), _well_configured_contract())

    exit_code = ctc.main([str(skeleton_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "note: --fingerprint-manifest not provided" in out


def test_pick_lethal_target_slot_prefers_a_gate_slot() -> None:
    contract = _well_configured_contract()
    target = ctc._pick_lethal_target_slot(contract)
    assert target.id == "A1_GATE"


def test_pick_lethal_target_slot_falls_back_to_first_slot_when_no_gate() -> None:
    contract = _well_configured_contract()
    slots = [
        slot.model_copy(update={"id": "NOGATEHERE"}) if slot.id == "A1_GATE" else slot
        for slot in contract.slots
    ]
    no_gate_contract = contract.model_copy(update={"slots": slots})
    target = ctc._pick_lethal_target_slot(no_gate_contract)
    assert target.id == no_gate_contract.slots[0].id
