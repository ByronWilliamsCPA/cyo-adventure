"""Unit tests for scripts/parameterize_skeleton.py.

Covers the plan-application invariants from
``docs/planning/ws2-parameterized-catalog-design.md`` section 8.1 step 4:
missing/unused beats and title mappings, a dangling label reference,
role=/words= byte-preservation, malformed-token rejection, and the happy
path (fingerprint preserved, gate passes, output written).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from cyo_adventure.diversity.structure import structure_fingerprint
from cyo_adventure.validator.gate import run_gate
from scripts import parameterize_skeleton as ps

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _pristine_skeleton() -> dict[str, object]:
    """A tiny, gate-passing, schema-valid, UNSLOTTED fixture skeleton.

    One decision node with a plain-prose FILL body and two ending nodes.
    Structurally identical (node ids, choices, targets, ending kinds) to
    ``test_binding_render.py``'s ``_tiny_skeleton`` fixture, which is
    independently verified to pass ``run_gate``; only the beats/title/label
    text differs (here it is un-slotted "original theme" prose, the
    pre-migration state a plan is applied to).
    """
    return {
        "schema_version": "2.0",
        "id": "s_test_param",
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
                    "<<FILL role=setup words=40 beats='Maya and her dog Biscuit "
                    "arrive at the sea cave and must choose a path.'>>"
                ),
                "is_ending": False,
                "choices": [
                    {
                        "id": "c_a",
                        "label": "Approach the glinting tide pool.",
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
                    "<<FILL role=ending words=30 beats='Maya claims the "
                    "glass starfish and celebrates.'>>"
                ),
                "is_ending": True,
                "ending": {
                    "id": "e_a",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The Glass Starfish",
                },
                "choices": [],
            },
            {
                "id": "n_end_b",
                "body": (
                    "<<FILL role=ending words=30 beats='Maya returns home safely.'>>"
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


def _valid_plan() -> dict[str, object]:
    """A slotting plan that neutralizes every beat/title, and one label."""
    return {
        "beats": {
            "n_start": (
                "{HERO} and {COMPANION} arrive at {THRESHOLD} and must choose a path."
            ),
            "n_end_a": "{HERO} claims {PRIZE} and celebrates.",
            "n_end_b": "{HERO} returns home safely.",
        },
        "titles": {
            "n_end_a": "The {PRIZE}",
            "n_end_b": "Home Again",
        },
        "labels": {
            "n_start": {"c_a": "Approach {OFFER}."},
        },
    }


def _write(tmp_path: Path, name: str, payload: dict[str, object]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _nodes(doc: dict[str, object]) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", doc["nodes"])


def _node_by_id(doc: dict[str, object], node_id: str) -> dict[str, object]:
    for node in _nodes(doc):
        if node["id"] == node_id:
            return node
    msg = f"no node with id {node_id!r}"
    raise AssertionError(msg)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_success_writes_parameterized_skeleton_and_preserves_invariants(
    tmp_path: Path,
) -> None:
    """A valid plan applies cleanly: fingerprint held, role/words held, gate ok."""
    original = _pristine_skeleton()
    skeleton_path = _write(tmp_path, "skeleton.json", original)
    plan_path = _write(tmp_path, "plan.json", _valid_plan())
    out_path = tmp_path / "out.json"

    exit_code = ps.main([str(skeleton_path), str(plan_path), "--out", str(out_path)])

    assert exit_code == 0
    assert out_path.is_file()
    parameterized = cast(
        "dict[str, object]", json.loads(out_path.read_text(encoding="utf-8"))
    )

    start = _node_by_id(parameterized, "n_start")
    assert start["body"] == (
        "<<FILL role=setup words=40 beats='{HERO} and {COMPANION} arrive at "
        "{THRESHOLD} and must choose a path.'>>"
    )
    choices = cast("list[dict[str, object]]", start["choices"])
    assert choices[0]["label"] == "Approach {OFFER}."
    assert choices[1]["label"] == "Turn back toward home."

    end_a = _node_by_id(parameterized, "n_end_a")
    ending_a = cast("dict[str, object]", end_a["ending"])
    assert ending_a["title"] == "The {PRIZE}"

    assert structure_fingerprint(parameterized) == structure_fingerprint(original)
    assert run_gate(parameterized).blocked is False


def test_success_prints_a_summary_with_counts_and_slot_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skeleton_path = _write(tmp_path, "skeleton.json", _pristine_skeleton())
    plan_path = _write(tmp_path, "plan.json", _valid_plan())
    out_path = tmp_path / "out.json"

    exit_code = ps.main([str(skeleton_path), str(plan_path), "--out", str(out_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "3 beats" in out
    assert "2 titles" in out
    assert "1 labels rewritten" in out
    assert "HERO" in out
    assert "PRIZE" in out


def test_in_place_write_via_tempfile_replaces_the_source(tmp_path: Path) -> None:
    """--out equal to the input path is supported (atomic in-place rewrite)."""
    skeleton_path = _write(tmp_path, "skeleton.json", _pristine_skeleton())
    plan_path = _write(tmp_path, "plan.json", _valid_plan())

    exit_code = ps.main(
        [str(skeleton_path), str(plan_path), "--out", str(skeleton_path)]
    )

    assert exit_code == 0
    rewritten = cast(
        "dict[str, object]", json.loads(skeleton_path.read_text(encoding="utf-8"))
    )
    start = _node_by_id(rewritten, "n_start")
    assert "{HERO}" in cast("str", start["body"])
    # No stray temp file left behind in the directory.
    leftover = [p for p in tmp_path.iterdir() if p.name.startswith(".skeleton.json.")]
    assert leftover == []


# ---------------------------------------------------------------------------
# Missing / unused mapping guards
# ---------------------------------------------------------------------------


def test_missing_fill_node_mapping_is_rejected(tmp_path: Path) -> None:
    plan = _valid_plan()
    beats = cast("dict[str, str]", plan["beats"])
    del beats["n_end_b"]
    skeleton_path = _write(tmp_path, "skeleton.json", _pristine_skeleton())
    plan_path = _write(tmp_path, "plan.json", plan)
    out_path = tmp_path / "out.json"

    exit_code = ps.main([str(skeleton_path), str(plan_path), "--out", str(out_path)])

    assert exit_code == 1
    assert not out_path.exists()


def test_unused_beats_mapping_is_rejected(tmp_path: Path) -> None:
    plan = _valid_plan()
    beats = cast("dict[str, str]", plan["beats"])
    beats["n_does_not_exist"] = "{HERO} does something."
    skeleton_path = _write(tmp_path, "skeleton.json", _pristine_skeleton())
    plan_path = _write(tmp_path, "plan.json", plan)
    out_path = tmp_path / "out.json"

    exit_code = ps.main([str(skeleton_path), str(plan_path), "--out", str(out_path)])

    assert exit_code == 1
    assert not out_path.exists()


def test_unused_title_mapping_is_rejected(tmp_path: Path) -> None:
    plan = _valid_plan()
    titles = cast("dict[str, str]", plan["titles"])
    titles["n_start"] = "Not an ending"  # n_start has no `ending` block
    skeleton_path = _write(tmp_path, "skeleton.json", _pristine_skeleton())
    plan_path = _write(tmp_path, "plan.json", plan)
    out_path = tmp_path / "out.json"

    exit_code = ps.main([str(skeleton_path), str(plan_path), "--out", str(out_path)])

    assert exit_code == 1
    assert not out_path.exists()


def test_dangling_label_reference_is_rejected(tmp_path: Path) -> None:
    """A labels entry pointing at a non-existent choice id fails closed."""
    plan = _valid_plan()
    labels = cast("dict[str, dict[str, str]]", plan["labels"])
    labels["n_start"]["c_does_not_exist"] = "Bogus {OFFER}."
    skeleton_path = _write(tmp_path, "skeleton.json", _pristine_skeleton())
    plan_path = _write(tmp_path, "plan.json", plan)
    out_path = tmp_path / "out.json"

    exit_code = ps.main([str(skeleton_path), str(plan_path), "--out", str(out_path)])

    assert exit_code == 1
    assert not out_path.exists()


# ---------------------------------------------------------------------------
# Malformed token grammar
# ---------------------------------------------------------------------------


def test_malformed_token_is_rejected(tmp_path: Path) -> None:
    """A `{lowercase}` token fails the SLOT_TOKEN_RE grammar check."""
    plan = _valid_plan()
    beats = cast("dict[str, str]", plan["beats"])
    beats["n_start"] = "{HERO} and {companion} arrive at {THRESHOLD}."
    skeleton_path = _write(tmp_path, "skeleton.json", _pristine_skeleton())
    plan_path = _write(tmp_path, "plan.json", plan)
    out_path = tmp_path / "out.json"

    exit_code = ps.main([str(skeleton_path), str(plan_path), "--out", str(out_path)])

    assert exit_code == 1
    assert not out_path.exists()


# ---------------------------------------------------------------------------
# role=/words= byte-preservation guard
# ---------------------------------------------------------------------------


def test_role_words_guard_rejects_a_mangled_words_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulates a corrupted apply step that mangles `words=`; the explicit
    role/words comparison (not fingerprinting, which strips the whole body)
    is what must catch it.
    """
    real_apply_beats = ps._apply_beats

    def _corrupting_apply_beats(
        skeleton: dict[str, object],
        beats_plan: dict[str, str],
        errors: list[str],
    ) -> set[str]:
        rewritten = real_apply_beats(skeleton, beats_plan, errors)
        for node in ps._iter_nodes(skeleton):
            if node.get("id") == "n_start":
                node["body"] = cast("str", node["body"]).replace("words=40", "words=4")
        return rewritten

    monkeypatch.setattr(ps, "_apply_beats", _corrupting_apply_beats)

    skeleton_path = _write(tmp_path, "skeleton.json", _pristine_skeleton())
    plan_path = _write(tmp_path, "plan.json", _valid_plan())
    out_path = tmp_path / "out.json"

    exit_code = ps.main([str(skeleton_path), str(plan_path), "--out", str(out_path)])

    assert exit_code == 1
    assert not out_path.exists()


def test_role_words_guard_rejects_a_fill_directive_degraded_to_prose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_apply_beats = ps._apply_beats

    def _degrading_apply_beats(
        skeleton: dict[str, object],
        beats_plan: dict[str, str],
        errors: list[str],
    ) -> set[str]:
        rewritten = real_apply_beats(skeleton, beats_plan, errors)
        for node in ps._iter_nodes(skeleton):
            if node.get("id") == "n_start":
                node["body"] = "Maya arrives at the sea cave."
        return rewritten

    monkeypatch.setattr(ps, "_apply_beats", _degrading_apply_beats)

    skeleton_path = _write(tmp_path, "skeleton.json", _pristine_skeleton())
    plan_path = _write(tmp_path, "plan.json", _valid_plan())
    out_path = tmp_path / "out.json"

    exit_code = ps.main([str(skeleton_path), str(plan_path), "--out", str(out_path)])

    assert exit_code == 1
    assert not out_path.exists()


# ---------------------------------------------------------------------------
# Load errors
# ---------------------------------------------------------------------------


def test_missing_skeleton_file_is_a_clean_failure(tmp_path: Path) -> None:
    plan_path = _write(tmp_path, "plan.json", _valid_plan())
    out_path = tmp_path / "out.json"
    exit_code = ps.main(
        [str(tmp_path / "does-not-exist.json"), str(plan_path), "--out", str(out_path)]
    )
    assert exit_code == 1
    assert not out_path.exists()


def test_plan_with_wrong_typed_beats_is_rejected(tmp_path: Path) -> None:
    """A plan whose 'beats' is not an object of strings fails to parse."""
    skeleton_path = _write(tmp_path, "skeleton.json", _pristine_skeleton())
    bad_plan: dict[str, object] = {"beats": "not-a-map", "titles": {}, "labels": {}}
    plan_path = _write(tmp_path, "plan.json", bad_plan)
    out_path = tmp_path / "out.json"

    exit_code = ps.main([str(skeleton_path), str(plan_path), "--out", str(out_path)])

    assert exit_code == 1
    assert not out_path.exists()
