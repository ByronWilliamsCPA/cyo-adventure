"""Tests for the W0.2 ending-valence triage audit.

Focus: the audit's own honesty. A triage script whose whole purpose is
finding mis-tagged endings must not be able to drop an ending from its own
report, and must not report a clean scan when it could not audit something.
Every case below is a defect the audit previously absorbed silently while
still exiting 0.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from scripts.audit_ending_valence import main

if TYPE_CHECKING:
    from pathlib import Path


def _write_story(root: Path, name: str, nodes: list[dict[str, Any]]) -> None:
    """Write a minimal filled-story file containing ``nodes``.

    Args:
        root: The out/ root to write into.
        name: File stem; ``.filled.json`` is appended.
        nodes: The story's node list, written verbatim.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.filled.json").write_text(
        json.dumps({"metadata": {"age_band": "8-11"}, "nodes": nodes}),
        encoding="utf-8",
    )


def _run(tmp_path: Path, extra: list[str] | None = None) -> int:
    """Run the audit against ``tmp_path``'s out/ tree only.

    Args:
        tmp_path: Directory holding an ``out/`` subdirectory.
        extra: Additional CLI arguments.

    Returns:
        The audit's exit code.
    """
    argv = [
        "--skeletons-root",
        str(tmp_path / "no_skeletons"),
        "--out-root",
        str(tmp_path / "out"),
        *(extra or []),
    ]
    return main(argv)


@pytest.mark.unit
def test_a_well_formed_catalog_exits_zero(tmp_path: Path) -> None:
    _write_story(
        tmp_path / "out",
        "clean",
        [
            {
                "id": "n_end",
                "is_ending": True,
                "body": "They walked home together.",
                "ending": {"id": "e1", "valence": "positive", "kind": "success"},
            }
        ],
    )
    assert _run(tmp_path) == 0


@pytest.mark.unit
def test_missing_valence_is_reported_as_a_problem(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The sharpest case: `.get("valence", "")` collapsed a MISSING valence
    into "", which `_is_suspect` treats as not-negative and therefore benign.
    The one ending guaranteed to need a human was the one guaranteed to be
    invisible."""
    _write_story(
        tmp_path / "out",
        "no_valence",
        [
            {
                "id": "n_end",
                "is_ending": True,
                "body": "They walked home together.",
                "ending": {"id": "e1", "kind": "success"},
            }
        ],
    )
    assert _run(tmp_path) == 2
    out = capsys.readouterr().out
    assert "PROBLEM" in out
    assert "bad-valence:<missing>" in out


@pytest.mark.unit
def test_unrecognized_valence_is_reported_as_a_problem(tmp_path: Path) -> None:
    _write_story(
        tmp_path / "out",
        "typo",
        [
            {
                "id": "n_end",
                "is_ending": True,
                "body": "They walked home together.",
                "ending": {"id": "e1", "valence": "postive", "kind": "success"},
            }
        ],
    )
    assert _run(tmp_path) == 2


@pytest.mark.unit
def test_ending_node_without_an_ending_object_still_gets_a_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """It was `continue`d, so the audit reported a smaller catalog than it
    scanned with no indication that it had."""
    _write_story(
        tmp_path / "out",
        "no_object",
        [{"id": "n_end", "is_ending": True, "body": "The end."}],
    )
    assert _run(tmp_path) == 2
    out = capsys.readouterr().out
    assert "no-ending-object" in out
    assert "total endings: 1" in out


@pytest.mark.unit
def test_non_list_nodes_is_reported_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Zero rows from a malformed file is indistinguishable from zero rows
    from a story that genuinely has no endings, unless it says so."""
    out_root = tmp_path / "out"
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "bad.filled.json").write_text(
        json.dumps({"metadata": {}, "nodes": "not-a-list"}), encoding="utf-8"
    )
    _run(tmp_path)
    assert "'nodes' is not a list" in capsys.readouterr().err


@pytest.mark.unit
def test_a_display_filter_cannot_silence_a_problem(tmp_path: Path) -> None:
    """--band and --suspect-only narrow what is PRINTED. The exit code is
    computed over the full scan, so choosing a filter for readability can
    never turn a defective catalog into a clean-looking run."""
    _write_story(
        tmp_path / "out",
        "no_valence",
        [
            {
                "id": "n_end",
                "is_ending": True,
                "body": "They walked home together.",
                "ending": {"id": "e1", "kind": "success"},
            }
        ],
    )
    assert _run(tmp_path, ["--suspect-only"]) == 2
    assert _run(tmp_path, ["--band", "3-5"]) == 2


@pytest.mark.unit
def test_unparseable_file_still_exits_one(tmp_path: Path) -> None:
    """Load failure outranks a structural defect: 1, not 2."""
    out_root = tmp_path / "out"
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "broken.filled.json").write_text("{not json", encoding="utf-8")
    assert _run(tmp_path) == 1
