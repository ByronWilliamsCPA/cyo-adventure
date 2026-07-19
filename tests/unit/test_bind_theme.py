"""Unit tests for scripts/bind_theme.py.

Covers the offline deterministic bind+validate+render path (design section
5.3, 8.1 step 7): valid bindings render a bound skeleton with zero residual
``{SLOT}`` tokens; violating bindings are rejected before any file is
written (fail closed, mirroring the worker's own bind -> validate -> render
order); and omitting ``--bindings`` falls back to the contract's
``default_binding`` (the original-theme reference render).
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, cast

from cyo_adventure.generation.binding import contract_path_for, render_bound_skeleton
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.theme_contract import (
    SlotConstraints,
    SlotScope,
    SlotSpec,
    ThemeContract,
)
from scripts import bind_theme

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _tiny_skeleton() -> dict[str, object]:
    """A tiny, gate-passing, already-parameterized fixture skeleton.

    Same shape as ``test_binding_render.py``'s ``_tiny_skeleton`` (one
    decision node with two slotted choices, two ending nodes; one slot per
    surface kind: beats, ending title, choice label).
    """
    return {
        "schema_version": "2.0",
        "id": "s_test_bind_theme",
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


_DEFAULT_BINDING = {
    "HERO": "Maya",
    "A1_GATE": "the flooding crack",
    "A1_OFFER": "a glowing crystal",
    "PRIZE": "Glowing Crystal",
}


def _slot(slot_id: str, *, scope: SlotScope = SlotScope.GLOBAL) -> SlotSpec:
    return SlotSpec(
        id=slot_id,
        scope=scope,
        meaning=f"placeholder meaning for {slot_id}",
        constraints=SlotConstraints(),
    )


def _tiny_contract() -> ThemeContract:
    return ThemeContract(
        contract_version=1,
        skeleton_slug="s_test_bind_theme",
        age_band=AgeBand.BAND_3_5,
        legacy_lexicon=[],
        default_binding=dict(_DEFAULT_BINDING),
        slots=[
            _slot("HERO"),
            _slot("A1_GATE", scope=SlotScope.TRACK),
            _slot("A1_OFFER", scope=SlotScope.TRACK),
            _slot("PRIZE", scope=SlotScope.ENDING),
        ],
    )


def _write_pair(tmp_path: Path) -> Path:
    skeleton_path = tmp_path / "s_test_bind_theme.json"
    skeleton_path.write_text(json.dumps(_tiny_skeleton()), encoding="utf-8")
    contract_path_for(skeleton_path).write_text(
        _tiny_contract().model_dump_json(), encoding="utf-8"
    )
    return skeleton_path


def _residual_tokens(doc: dict[str, object]) -> list[str]:
    return re.findall(r"\{[A-Z][A-Z0-9_]*\}", json.dumps(doc))


def test_valid_bindings_write_a_bound_skeleton_with_no_residual_tokens(
    tmp_path: Path,
) -> None:
    skeleton_path = _write_pair(tmp_path)
    bindings = {
        "HERO": "Priya",
        "A1_GATE": "the jammed hatch",
        "A1_OFFER": "a glinting tide pool",
        "PRIZE": "Glass Starfish",
    }
    bindings_path = tmp_path / "bindings.json"
    bindings_path.write_text(json.dumps(bindings), encoding="utf-8")
    out_bound_path = tmp_path / "bound.json"

    exit_code = bind_theme.main(
        [
            str(skeleton_path),
            "--bindings",
            str(bindings_path),
            "--out-bound",
            str(out_bound_path),
        ]
    )

    assert exit_code == 0
    assert out_bound_path.is_file()
    bound = cast(
        "dict[str, object]", json.loads(out_bound_path.read_text(encoding="utf-8"))
    )
    assert _residual_tokens(bound) == []

    expected = render_bound_skeleton(_tiny_skeleton(), bindings)
    assert bound == expected


def test_out_binding_echoes_the_bindings_actually_used(tmp_path: Path) -> None:
    skeleton_path = _write_pair(tmp_path)
    bindings = {
        "HERO": "Priya",
        "A1_GATE": "the jammed hatch",
        "A1_OFFER": "a glinting tide pool",
        "PRIZE": "Glass Starfish",
    }
    bindings_path = tmp_path / "bindings.json"
    bindings_path.write_text(json.dumps(bindings), encoding="utf-8")
    out_bound_path = tmp_path / "bound.json"
    out_binding_path = tmp_path / "binding-echo.json"

    exit_code = bind_theme.main(
        [
            str(skeleton_path),
            "--bindings",
            str(bindings_path),
            "--out-bound",
            str(out_bound_path),
            "--out-binding",
            str(out_binding_path),
        ]
    )

    assert exit_code == 0
    echoed: object = json.loads(  # pyright: ignore[reportAny]
        out_binding_path.read_text(encoding="utf-8")
    )
    assert echoed == bindings


def test_violating_bindings_are_rejected_and_nothing_is_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skeleton_path = _write_pair(tmp_path)
    lethal_bindings = {
        "HERO": "Priya",
        "A1_GATE": "a chasm that kills anyone who falls",
        "A1_OFFER": "a glinting tide pool",
        "PRIZE": "Glass Starfish",
    }
    bindings_path = tmp_path / "bindings.json"
    bindings_path.write_text(json.dumps(lethal_bindings), encoding="utf-8")
    out_bound_path = tmp_path / "bound.json"

    exit_code = bind_theme.main(
        [
            str(skeleton_path),
            "--bindings",
            str(bindings_path),
            "--out-bound",
            str(out_bound_path),
        ]
    )

    assert exit_code == 1
    assert not out_bound_path.exists()
    err = capsys.readouterr().err
    assert "forbid:lethal" in err
    assert "binding rejected" in err


def test_missing_bindings_flag_falls_back_to_default_binding(tmp_path: Path) -> None:
    skeleton_path = _write_pair(tmp_path)
    out_bound_path = tmp_path / "bound.json"

    exit_code = bind_theme.main(
        [str(skeleton_path), "--out-bound", str(out_bound_path)]
    )

    assert exit_code == 0
    bound = cast(
        "dict[str, object]", json.loads(out_bound_path.read_text(encoding="utf-8"))
    )
    expected = render_bound_skeleton(_tiny_skeleton(), _DEFAULT_BINDING)
    assert bound == expected
    assert _residual_tokens(bound) == []


def test_missing_contract_sidecar_is_a_clean_failure(tmp_path: Path) -> None:
    skeleton_path = tmp_path / "s_test_bind_theme.json"
    skeleton_path.write_text(json.dumps(_tiny_skeleton()), encoding="utf-8")
    out_bound_path = tmp_path / "bound.json"

    exit_code = bind_theme.main(
        [str(skeleton_path), "--out-bound", str(out_bound_path)]
    )

    assert exit_code == 1
    assert not out_bound_path.exists()


def test_missing_bindings_file_is_a_clean_failure(tmp_path: Path) -> None:
    skeleton_path = _write_pair(tmp_path)
    out_bound_path = tmp_path / "bound.json"

    exit_code = bind_theme.main(
        [
            str(skeleton_path),
            "--bindings",
            str(tmp_path / "does-not-exist.json"),
            "--out-bound",
            str(out_bound_path),
        ]
    )

    assert exit_code == 1
    assert not out_bound_path.exists()
