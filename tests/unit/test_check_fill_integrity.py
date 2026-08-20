"""Unit tests for scripts/check_fill_integrity.py.

scripts/ is not an importable package (no __init__.py, by design; see
per-file-ignores INP for scripts/**/*.py in pyproject.toml), so the module
is loaded directly from its file path via importlib.

Covers the WS-0 labels-are-leaves alignment: a fill that only rewrites
choice labels (in addition to bodies) passes the structural check, while a
rewritten ``target`` still fails it.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from types import ModuleType

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name: str) -> ModuleType:
    """Load a scripts/ module from its file path."""
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_fill_integrity = _load("check_fill_integrity")

pytestmark = pytest.mark.unit

_SKELETON: dict[str, Any] = {
    "schema_version": "2.0",
    "id": "sk_test",
    "version": 1,
    "title": "A Fine Adventure",
    "metadata": {
        "age_band": "8-11",
        "reading_level": {"scheme": "flesch_kincaid", "target": 4.5},
        "tier": 1,
        "estimated_minutes": 5,
        "ending_count": 1,
        "topology": "gauntlet",
    },
    "start_node": "n1",
    "nodes": [
        {
            "id": "n1",
            "body": "<<FILL body>>",
            "is_ending": False,
            "choices": [
                {"id": "c1", "label": "<<FILL label>>", "target": "n2"},
            ],
        },
        {
            "id": "n2",
            "body": "<<FILL body>>",
            "is_ending": True,
            "ending": {
                "id": "e1",
                "valence": "positive",
                "kind": "completion",
                "title": "Home Safe",
            },
        },
    ],
}


def _filled() -> dict[str, Any]:
    """Return a filled version of ``_SKELETON`` with bodies/labels replaced.

    Title and ending title are left untouched: ``check_fill_integrity.py``
    has never treated those as leaf fields (only ``body`` and, after this
    change, choice ``label``), so a realistic fill leaves them as-authored.
    """
    filled = copy.deepcopy(_SKELETON)
    filled["nodes"][0]["body"] = "You stand at a fork in the path."
    filled["nodes"][0]["choices"][0]["label"] = "Go toward the light."
    filled["nodes"][1]["body"] = "You made it home safe."
    return filled


def _write(tmp_path: Path, name: str, data: dict[str, Any]) -> str:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_label_rewritten_fill_passes_the_structure_check(tmp_path: Path) -> None:
    """A fill that rewrites bodies and choice labels passes structural check."""
    skeleton_path = _write(tmp_path, "skeleton.json", _SKELETON)
    filled_path = _write(tmp_path, "filled.json", _filled())
    exit_code = check_fill_integrity.main([skeleton_path, filled_path])
    assert exit_code == 0


def test_title_rewrite_flag_permits_book_and_ending_titles(tmp_path: Path) -> None:
    """With --allow-title-rewrite, storybook and ending titles are leaves.

    Amendment 4 of the contract-hygiene pass (AL-161): an unslotted title
    is byte-frozen across bindings and a top recognition channel, so a
    title-contract fill rewrites both the book title and ending titles.
    Without the flag the same fill must still fail.
    """
    filled = _filled()
    filled["title"] = "The Comet Glyphs"
    filled["nodes"][1]["ending"]["title"] = "Starlight Kept"
    skeleton_path = _write(tmp_path, "skeleton.json", _SKELETON)
    filled_path = _write(tmp_path, "filled.json", filled)
    assert (
        check_fill_integrity.main([skeleton_path, filled_path, "--allow-title-rewrite"])
        == 0
    )
    assert check_fill_integrity.main([skeleton_path, filled_path]) == 1


def test_rewritten_target_fails_the_structure_check(tmp_path: Path) -> None:
    """A fill whose choice target changes is a genuine structural violation."""
    filled = _filled()
    filled["nodes"][0]["choices"][0]["target"] = "n1"
    skeleton_path = _write(tmp_path, "skeleton.json", _SKELETON)
    filled_path = _write(tmp_path, "filled.json", filled)
    exit_code = check_fill_integrity.main([skeleton_path, filled_path])
    assert exit_code == 1


def test_check_fill_integrity_rejects_same_file(tmp_path: Path) -> None:
    """Comparing a file against itself is a degenerate, always-passing input.

    AL-016: a builder bug once wrote the prose story to both the skeleton
    and filled paths, and the structural comparison then compared a file
    with itself and passed, making the verification vacuous. The checker
    must refuse this input outright rather than report a meaningless
    success.
    """
    skeleton_path = _write(tmp_path, "skeleton.json", _SKELETON)
    exit_code = check_fill_integrity.main([skeleton_path, skeleton_path])
    assert exit_code == 1


def _commissioned_skeleton() -> dict[str, Any]:
    """Return ``_SKELETON`` with explicit ``words=`` targets on both nodes."""
    skeleton = copy.deepcopy(_SKELETON)
    skeleton["nodes"][0]["body"] = "<<FILL role=scene words=100 beats='a fork'>>"
    skeleton["nodes"][1]["body"] = "<<FILL role=ending words=100 beats='home'>>"
    return skeleton


def _filled_at(words_per_node: int) -> dict[str, Any]:
    """Return a fill of ``_commissioned_skeleton`` at a chosen delivery length."""
    filled = copy.deepcopy(_SKELETON)
    body = " ".join(f"word{i}" for i in range(words_per_node))
    filled["nodes"][0]["body"] = body
    filled["nodes"][0]["choices"][0]["label"] = "Go toward the light."
    filled["nodes"][1]["body"] = body
    return filled


def test_an_underdelivered_fill_fails_the_fill_rate_check(tmp_path: Path) -> None:
    """A book at 40 percent of its commissioned words is blocked (AL-490).

    The live DeepSeek run delivered 38.9-52.9 percent of three books'
    commissioned prose and every book passed, because the per-node advisory
    is soft and the only hard word rule is a ceiling. The story-level ratio
    is the check that composes those legitimate per-node liberties into an
    illegitimate whole.
    """
    skeleton_path = _write(tmp_path, "skeleton.json", _commissioned_skeleton())
    filled_path = _write(tmp_path, "filled.json", _filled_at(40))
    assert check_fill_integrity.main([skeleton_path, filled_path]) == 1


def test_a_delivered_fill_passes_the_fill_rate_check(tmp_path: Path) -> None:
    """Delivery near the commissioned total clears the floor."""
    skeleton_path = _write(tmp_path, "skeleton.json", _commissioned_skeleton())
    filled_path = _write(tmp_path, "filled.json", _filled_at(95))
    assert check_fill_integrity.main([skeleton_path, filled_path]) == 0


def test_min_fill_rate_zero_measures_without_blocking(tmp_path: Path) -> None:
    """A zero floor reports the ratio but never fails on it."""
    skeleton_path = _write(tmp_path, "skeleton.json", _commissioned_skeleton())
    filled_path = _write(tmp_path, "filled.json", _filled_at(40))
    assert (
        check_fill_integrity.main([skeleton_path, filled_path, "--min-fill-rate", "0"])
        == 0
    )


@pytest.mark.parametrize("floor", ["nan", "-0.5"], ids=["nan", "negative"])
def test_a_degenerate_fill_rate_floor_is_refused(tmp_path: Path, floor: str) -> None:
    """A NaN or negative floor would pass every fill, so it is a usage error.

    ``fill_rate < float("nan")`` is False for every ratio and a negative
    floor sits below every possible delivery; either silently disables the
    gate while looking configured. Zero stays legal as the documented
    measure-without-blocking setting.
    """
    skeleton_path = _write(tmp_path, "skeleton.json", _commissioned_skeleton())
    filled_path = _write(tmp_path, "filled.json", _filled_at(40))
    assert (
        check_fill_integrity.main(
            [skeleton_path, filled_path, "--min-fill-rate", floor]
        )
        == 1
    )


def test_fill_rate_skips_a_skeleton_without_word_targets(tmp_path: Path) -> None:
    """No ``words=`` directives means no commissioned total, not a zero rate.

    A directive-less skeleton would otherwise divide by zero or read as 0
    percent delivered; the check must recognise there is nothing to measure.
    """
    skeleton_path = _write(tmp_path, "skeleton.json", _SKELETON)
    filled_path = _write(tmp_path, "filled.json", _filled())
    assert check_fill_integrity.main([skeleton_path, filled_path]) == 0


def test_check_fill_integrity_rejects_a_skeleton_with_no_markers(
    tmp_path: Path,
) -> None:
    """A ``skeleton`` argument with no ``<<FILL`` directive is not a skeleton.

    Comparing two already-filled stories cannot detect a failed fill, so the
    checker must refuse this input rather than run the structural comparison
    against a skeleton that carries no markers to check.
    """
    skeleton_path = _write(tmp_path, "skeleton.json", _filled())
    filled_path = _write(tmp_path, "filled.json", _filled())
    exit_code = check_fill_integrity.main([skeleton_path, filled_path])
    assert exit_code == 1
