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


def test_rewritten_target_fails_the_structure_check(tmp_path: Path) -> None:
    """A fill whose choice target changes is a genuine structural violation."""
    filled = _filled()
    filled["nodes"][0]["choices"][0]["target"] = "n1"
    skeleton_path = _write(tmp_path, "skeleton.json", _SKELETON)
    filled_path = _write(tmp_path, "filled.json", filled)
    exit_code = check_fill_integrity.main([skeleton_path, filled_path])
    assert exit_code == 1
