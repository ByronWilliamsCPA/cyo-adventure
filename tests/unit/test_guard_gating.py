"""Unit tests for two gating fixes in scripts/check_reading_level.py and
scripts/run_guard_battery.py (no network, no real DB).

scripts/ is not an importable package (no __init__.py, by design; see the
INP per-file-ignore for scripts/**/*.py in pyproject.toml), so each module is
loaded directly from its file path via importlib, mirroring
tests/unit/test_run_notification_digest.py.

Fix 1 (check_reading_level.py): ``main()`` used to ``continue`` when
``score()`` returned None ("too little prose to score") without setting the
breach flag, so a book too short to score exited 0 even under --check. It now
collects unscorable book stems and returns 1 under --check.

Fix 2 (run_guard_battery.py): the per-book guard list invoked
``check_prose_craft.py`` with no --check while recording that Result as
``gating=True``. ``check_prose_craft.py``'s ``main()`` is
``if args.check and breached: return 1`` then ``return 0``, so without the
flag it can never fail, which put a structurally-passing guard into the
gating denominator. It now passes ``--check``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

_READING_LEVEL_SPEC = importlib.util.spec_from_file_location(
    "check_reading_level", _REPO_ROOT / "scripts" / "check_reading_level.py"
)
assert _READING_LEVEL_SPEC is not None
assert _READING_LEVEL_SPEC.loader is not None
check_reading_level_script = importlib.util.module_from_spec(_READING_LEVEL_SPEC)
sys.modules[_READING_LEVEL_SPEC.name] = check_reading_level_script
_READING_LEVEL_SPEC.loader.exec_module(check_reading_level_script)

_GUARD_BATTERY_SPEC = importlib.util.spec_from_file_location(
    "run_guard_battery", _REPO_ROOT / "scripts" / "run_guard_battery.py"
)
assert _GUARD_BATTERY_SPEC is not None
assert _GUARD_BATTERY_SPEC.loader is not None
run_guard_battery_script = importlib.util.module_from_spec(_GUARD_BATTERY_SPEC)
sys.modules[_GUARD_BATTERY_SPEC.name] = run_guard_battery_script
_GUARD_BATTERY_SPEC.loader.exec_module(run_guard_battery_script)

pytestmark = pytest.mark.unit


def _story(bodies: list[str]) -> dict[str, Any]:
    """Return a minimal filled-storybook shape around the given node bodies."""
    return {
        "id": "s",
        "nodes": [{"id": f"n{i}", "body": body} for i, body in enumerate(bodies)],
    }


def _write_story(path: Path, bodies: list[str]) -> Path:
    """Write a minimal storybook JSON with the given node bodies and return it."""
    path.write_text(json.dumps(_story(bodies)), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Fix 1: scripts/check_reading_level.py
# --------------------------------------------------------------------------


def test_reading_level_unscorable_book_fails_check(tmp_path: Path) -> None:
    """A book whose total prose falls below the scoreable minimum must fail
    ``--check``, not exit 0 as though it had been cleared.

    ``grade()`` returns None once the whole-book word count is below
    ``_MIN_WORDS`` (20). Five words is comfortably under that floor.
    """
    assert check_reading_level_script._MIN_WORDS == 20
    book = _write_story(tmp_path / "too_short.json", ["Once upon a time now."])

    result = check_reading_level_script.main([str(book), "--check"])

    assert result == 1


def test_reading_level_in_band_book_passes_check(tmp_path: Path) -> None:
    """A normal, scoreable, in-band book still exits 0 under --check.

    This is the companion to the unscorable-book test above: the new failure
    path must not make every book fail, only the ones that cannot be scored
    at all or that are genuinely too hard.
    """
    bodies = [
        "The cat sat on the warm mat. The dog ran to the park.",
        "Sam had a big red ball. He can run and jump fast.",
        "The sun was out today. Tom and Sam went home now.",
        "They ate a snack and sat down. The day was good and calm.",
    ]
    book = _write_story(tmp_path / "in_band.json", bodies)

    scored = check_reading_level_script.score(book)
    assert scored is not None
    assert scored.grade <= check_reading_level_script._MAX_GRADE

    result = check_reading_level_script.main([str(book), "--check"])

    assert result == 0


# --------------------------------------------------------------------------
# Fix 2: scripts/run_guard_battery.py
# --------------------------------------------------------------------------


def test_guard_battery_prose_craft_invoked_with_check_flag() -> None:
    """``check_prose_craft.py`` must be invoked with ``--check``.

    Its own ``main()`` is ``if args.check and breached: return 1`` then
    ``return 0``: called bare, it can never return non-zero, so recording its
    Result as ``gating=True`` without the flag put a guard that could not
    fail into the gating denominator. This test intercepts the
    (script, args) pairs ``battery()`` builds rather than shelling out, so it
    fails immediately if the flag regresses.

    ``check_fill_integrity.py`` and ``run_story_gate.py`` are asserted the
    other way on purpose: they gate on ``return 1 if failed else 0`` already
    and take no --check flag, so asserting the flag's presence for them would
    be wrong.
    """
    calls: list[tuple[str, tuple[str, ...]]] = []

    def _fake_run(script: str, *args: str) -> tuple[int, str]:
        calls.append((script, args))
        return 0, "ok"

    with patch.object(run_guard_battery_script, "_run", _fake_run):
        run_guard_battery_script.battery(
            "skeleton.json", "contract.json", ["book.json"], []
        )

    prose_craft_calls = [c for c in calls if c[0] == "check_prose_craft.py"]
    assert prose_craft_calls, "check_prose_craft.py was not invoked"
    assert "--check" in prose_craft_calls[0][1]

    fill_integrity_calls = [c for c in calls if c[0] == "check_fill_integrity.py"]
    assert fill_integrity_calls, "check_fill_integrity.py was not invoked"
    assert "--check" not in fill_integrity_calls[0][1]

    story_gate_calls = [c for c in calls if c[0] == "run_story_gate.py"]
    assert story_gate_calls, "run_story_gate.py was not invoked"
    assert "--check" not in story_gate_calls[0][1]
