"""Unit tests for scripts/check_skeleton.py's author-facing headroom report."""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.check_skeleton as check_skeleton

# ---------------------------------------------------------------------------
# --headroom (AL-018)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_headroom_reports_proximity_to_every_budget_edge(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A pass/fail verdict hides proximity, which is what an author needs.

    The report previously existed only inside a series-specific build script, so
    the general tool told an author nothing about how close they were to the
    depth cap or the ending floor.
    """
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "skeletons"
        / "16+"
        / "the-ninth-hand.json"
    )
    if not path.is_file():
        pytest.skip("the-ninth-hand skeleton not present")
    assert check_skeleton.main([str(path), "--headroom"]) == 0
    out = capsys.readouterr().out
    for expected in (
        "headroom nodes",
        "headroom depth",
        "headroom endings",
        "headroom decisions",
        "headroom words",
        "headroom arc floor",
    ):
        assert expected in out, f"{expected} missing from the headroom report"
    # The signal that matters for this book: it sits on the endings floor exactly.
    assert "against floor 187 (+0)" in out


@pytest.mark.unit
def test_headroom_is_opt_in(capsys: pytest.CaptureFixture[str]) -> None:
    """Without the flag the output is unchanged, so existing callers are safe."""
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "skeletons"
        / "16+"
        / "the-ninth-hand.json"
    )
    if not path.is_file():
        pytest.skip("the-ninth-hand skeleton not present")
    assert check_skeleton.main([str(path)]) == 0
    assert "headroom" not in capsys.readouterr().out
