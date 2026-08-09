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


# ---------------------------------------------------------------------------
# Gate findings surfaced + --strict (2026-08-09 review, sections 2.2 / Part 3)
# ---------------------------------------------------------------------------

_DEMO_SHELL = Path("tests/fixtures/skeletons/demo_shell.json")


@pytest.mark.unit
def test_default_mode_prints_gate_warnings_and_still_passes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Advisories must be visible on a pass; the loader used to drop them.

    The demo shell fires L1-7 (9 nodes, below the 8-11 band range), which the
    old script swallowed while printing a clean ``ok``.
    """
    assert check_skeleton.main([str(_DEMO_SHELL), "--allow-mvp"]) == 0
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "L1-7" in out
    assert "ok: skeleton passes gate and brief checks" in out


@pytest.mark.unit
def test_strict_mode_escalates_advisories_to_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """--strict is the newly-drafted-skeleton bar: escalated advisories block."""
    assert check_skeleton.main([str(_DEMO_SHELL), "--allow-mvp", "--strict"]) == 1
    captured = capsys.readouterr()
    assert "FAIL strict: L1-7" in captured.err
    # The choice grammar runs under --strict (enforce_grammar=True).
    assert "CG-2" in captured.out
    # The walk line is part of strict output.
    assert "walk: P(satisfying ending, uniform reader)" in captured.out


@pytest.mark.unit
def test_strict_walk_floor_blocks_below_floor(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A skeleton below its band's random-walk outcome floor fails --strict."""
    monkeypatch.setitem(check_skeleton._WALK_FLOORS, "8-11", 1.01)
    assert check_skeleton.main([str(_DEMO_SHELL), "--allow-mvp", "--strict"]) == 1
    assert "strict walk floor" in capsys.readouterr().err


@pytest.mark.unit
def test_cg4_is_excluded_from_the_strict_escalation_set() -> None:
    """CG-4 needs filled prose; on a shell every body is a FILL directive.

    Including it would fail every shell unconditionally, making --strict
    useless for skeleton drafting. CG-4 belongs to the fill gate.
    """
    assert "CG-4" not in check_skeleton.STRICT_BLOCKING_WARNINGS
    assert {"CG-1", "CG-2", "CG-3"} <= check_skeleton.STRICT_BLOCKING_WARNINGS


# ---------------------------------------------------------------------------
# satisfying_walk_probability / walk_floor
# ---------------------------------------------------------------------------


def _walk_story(nodes: list[dict[str, object]]) -> dict[str, object]:
    """Wrap bare nodes in the minimal story shape the walk needs."""
    return {"start_node": nodes[0]["id"], "nodes": nodes}


def _walk_ending(node_id: str, valence: str) -> dict[str, object]:
    return {"id": node_id, "ending": {"kind": "success", "valence": valence}}


def _walk_choice_node(node_id: str, targets: list[str]) -> dict[str, object]:
    return {"id": node_id, "choices": [{"target": t} for t in targets]}


@pytest.mark.unit
def test_walk_probability_linear_win_is_one() -> None:
    story = _walk_story([_walk_choice_node("a", ["b"]), _walk_ending("b", "positive")])
    assert check_skeleton.satisfying_walk_probability(story) == pytest.approx(1.0)


@pytest.mark.unit
def test_walk_probability_even_split_is_half_and_neutral_satisfies() -> None:
    story = _walk_story(
        [
            _walk_choice_node("a", ["win", "lose"]),
            _walk_ending("win", "neutral"),
            _walk_ending("lose", "negative"),
        ]
    )
    assert check_skeleton.satisfying_walk_probability(story) == pytest.approx(0.5)


@pytest.mark.unit
def test_walk_probability_converges_on_a_cycle() -> None:
    """A loop_and_grow-style cycle must converge, not recurse forever.

    A self-looping node whose only exit is a win converges to 1.0; with a
    losing exit it converges to 0.0.
    """
    winning = _walk_story(
        [_walk_choice_node("a", ["a", "win"]), _walk_ending("win", "positive")]
    )
    losing = _walk_story(
        [_walk_choice_node("a", ["a", "lose"]), _walk_ending("lose", "negative")]
    )
    assert check_skeleton.satisfying_walk_probability(winning) == pytest.approx(
        1.0, abs=1e-6
    )
    assert check_skeleton.satisfying_walk_probability(losing) == pytest.approx(
        0.0, abs=1e-6
    )


@pytest.mark.unit
def test_walk_floor_is_style_scaled_at_the_teen_bands() -> None:
    assert check_skeleton.walk_floor("13-16", "gamebook") == pytest.approx(0.02)
    assert check_skeleton.walk_floor("16+", "prose") == pytest.approx(0.10)
    # An MVP seed (style None) is held to the stricter prose floor.
    assert check_skeleton.walk_floor("16+", None) == pytest.approx(0.10)
    assert check_skeleton.walk_floor("3-5", None) == pytest.approx(0.60)
    assert check_skeleton.walk_floor("nonsense", None) is None


# ---------------------------------------------------------------------------
# Reconvergence hard cap + depth-qualified endings (ruled 2026-08-09, Part 4)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_max_indegree_counts_parallel_edges_separately() -> None:
    story = _walk_story(
        [
            {
                "id": "a",
                "choices": [{"target": "b"}, {"target": "b"}, {"target": "c"}],
            },
            _walk_ending("b", "positive"),
            _walk_ending("c", "positive"),
        ]
    )
    assert check_skeleton.max_indegree(story) == 2


@pytest.mark.unit
def test_indegree_cap_exempts_hub_topologies() -> None:
    """open_map and loop_and_grow re-enter hubs by design; capping them would
    ban both topology families (catalog hub medians 9 and 5)."""
    assert check_skeleton.indegree_cap("8-11", "open_map") is None
    assert check_skeleton.indegree_cap("3-5", "loop_and_grow") is None
    assert check_skeleton.indegree_cap("3-5", "time_cave") == 4
    assert check_skeleton.indegree_cap("13-16", "branch_and_bottleneck") == 8
    assert check_skeleton.indegree_cap("nonsense", "gauntlet") is None


@pytest.mark.unit
def test_strict_reconvergence_cap_blocks_when_exceeded(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A funnel past the band cap fails --strict on a capped topology."""
    monkeypatch.setitem(check_skeleton._MAX_INDEGREE_CAPS, "8-11", 0)
    assert check_skeleton.main([str(_DEMO_SHELL), "--allow-mvp", "--strict"]) == 1
    assert "strict reconvergence" in capsys.readouterr().err


@pytest.mark.unit
def test_depth_qualified_endings_excludes_shallow_leaves() -> None:
    """An ending two taps from the start is not breadth (AL-026 evidence)."""
    story = _walk_story(
        [
            _walk_choice_node("a", ["shallow", "b"]),
            _walk_ending("shallow", "negative"),
            _walk_choice_node("b", ["c"]),
            _walk_choice_node("c", ["deep"]),
            _walk_ending("deep", "positive"),
        ]
    )
    assert check_skeleton.depth_qualified_endings(story, 3) == (1, 2)
    assert check_skeleton.depth_qualified_endings(story, 1) == (2, 2)
