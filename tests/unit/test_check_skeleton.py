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
        # Tracked skip (UW-F19): skeletons/16+/the-ninth-hand.json has never been
        # committed, so this test has never executed. It is kept rather than deleted
        # because it runs unchanged the moment that skeleton lands. Deliberately a skip
        # and not a CI failure: the artifact is absent on every checkout including CI,
        # so failing would break the suite rather than reveal anything.
        pytest.skip(
            "skeletons/16+/the-ninth-hand.json is not committed; tracked by "
            "UW-F19 (weak-skip audit) and UW-F20 (corpus coverage)"
        )
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
        # Tracked skip (UW-F19): skeletons/16+/the-ninth-hand.json has never been
        # committed, so this test has never executed. It is kept rather than deleted
        # because it runs unchanged the moment that skeleton lands. Deliberately a skip
        # and not a CI failure: the artifact is absent on every checkout including CI,
        # so failing would break the suite rather than reveal anything.
        pytest.skip(
            "skeletons/16+/the-ninth-hand.json is not committed; tracked by "
            "UW-F19 (weak-skip audit) and UW-F20 (corpus coverage)"
        )
    assert check_skeleton.main([str(path)]) == 0
    assert "headroom" not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Gate findings surfaced + --strict (2026-08-09 review, sections 2.2 / Part 3)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_SHELL = _REPO_ROOT / "tests" / "fixtures" / "skeletons" / "demo_shell.json"


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


# ---------------------------------------------------------------------------
# Agency advisory: merge nodes against declared variables (UW-C479, AL-768)
# ---------------------------------------------------------------------------


def _diamond(variables: list[dict[str, object]]) -> dict[str, object]:
    """Return a two-route diamond whose ``m`` node is a merge."""
    story = _walk_story(
        [
            _walk_choice_node("a", ["b", "c"]),
            _walk_choice_node("b", ["m"]),
            _walk_choice_node("c", ["m"]),
            _walk_choice_node("m", ["end"]),
            _walk_ending("end", "positive"),
        ]
    )
    story["variables"] = variables
    return story


@pytest.mark.unit
def test_agency_flags_merges_without_variables() -> None:
    """A merge with no state erases the route; the skeleton is where to fix it."""
    lines = check_skeleton.agency_lines(_diamond([]))
    assert lines[0] == "agency: merge nodes 1, declared variables 0"
    assert len(lines) == 2
    assert lines[1].startswith("advisory agency: 1 merge nodes and no declared")
    assert "no early choice can matter later" in lines[1]


@pytest.mark.unit
def test_agency_is_quiet_when_a_variable_can_carry_the_route() -> None:
    lines = check_skeleton.agency_lines(
        _diamond([{"name": "has_key", "type": "bool", "initial": False}])
    )
    assert lines == ["agency: merge nodes 1, declared variables 1"]


@pytest.mark.unit
def test_agency_is_quiet_on_a_stateless_tree() -> None:
    """No merge, no erased route: a pure tree needs no state to keep choices."""
    story = _walk_story(
        [
            _walk_choice_node("a", ["b", "c"]),
            _walk_ending("b", "positive"),
            _walk_ending("c", "negative"),
        ]
    )
    assert check_skeleton.agency_lines(story) == [
        "agency: merge nodes 0, declared variables 0"
    ]


@pytest.mark.unit
def test_agency_advisory_never_changes_the_exit_code(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report-only: 69 of 84 shells have no variables, and that is content work.

    The demo shell has no merge, so the merge count is forced; the advisory
    must print and the exit code must stay what the gate alone decides, in
    both the default and the strict mode.
    """
    assert check_skeleton.main([str(_DEMO_SHELL), "--allow-mvp"]) == 0
    capsys.readouterr()
    assert check_skeleton.main([str(_DEMO_SHELL), "--allow-mvp", "--strict"]) == 1
    strict_err_before = capsys.readouterr().err

    monkeypatch.setattr(check_skeleton, "merge_node_count", lambda _story: 7)

    assert check_skeleton.main([str(_DEMO_SHELL), "--allow-mvp"]) == 0
    out = capsys.readouterr().out
    assert "advisory agency: 7 merge nodes and no declared variables" in out
    assert "ok: skeleton passes gate and brief checks" in out
    assert check_skeleton.main([str(_DEMO_SHELL), "--allow-mvp", "--strict"]) == 1
    captured = capsys.readouterr()
    assert captured.err == strict_err_before
    assert "agency" not in captured.err


# ---------------------------------------------------------------------------
# ADR-011 section 12: --strict requires declared state at 8-11+ with a merge
# ---------------------------------------------------------------------------

_PROD_META = {"age_band": "10-13", "production_eligible": True}


def _strict_violation(
    story: dict, meta: dict, grandfathered: frozenset[str] = frozenset()
) -> str | None:
    return check_skeleton.stateless_shell_violation(story, meta, grandfathered)


@pytest.mark.unit
def test_strict_agency_fails_a_stateless_merge_shell() -> None:
    story = _diamond([])
    story["id"] = "sk_new"
    message = _strict_violation(story, _PROD_META)
    assert message is not None
    assert "1 merge nodes and no declared variables at 10-13" in message


@pytest.mark.unit
def test_strict_agency_passes_when_state_is_declared() -> None:
    story = _diamond([{"name": "has_key", "type": "bool", "initial": False}])
    assert _strict_violation(story, _PROD_META) is None


@pytest.mark.unit
def test_strict_agency_exempts_pure_trees_young_bands_and_seeds() -> None:
    tree = _walk_story(
        [
            _walk_choice_node("a", ["b", "c"]),
            _walk_ending("b", "positive"),
            _walk_ending("c", "negative"),
        ]
    )
    assert _strict_violation(tree, _PROD_META) is None
    story = _diamond([])
    assert _strict_violation(story, {**_PROD_META, "age_band": "5-8"}) is None
    assert (
        _strict_violation(story, {**_PROD_META, "production_eligible": False}) is None
    )


@pytest.mark.unit
def test_strict_agency_grandfathers_listed_shells() -> None:
    story = _diamond([])
    story["id"] = "sk_old"
    assert _strict_violation(story, _PROD_META, frozenset({"10-13/sk_old"})) is None
    assert _strict_violation(story, _PROD_META, frozenset({"13-16/sk_old"})) is not None


@pytest.mark.unit
def test_grandfather_list_is_complete_for_the_committed_corpus() -> None:
    """Every committed stateless merge shell is listed, so no CI run can regress."""
    import json

    grandfathered = check_skeleton.load_stateless_grandfather()
    assert grandfathered
    for path in sorted((_REPO_ROOT / "skeletons").glob("*/*.json")):
        if path.name.count(".") != 1:
            continue
        story = json.loads(path.read_text(encoding="utf-8"))
        meta = story["metadata"]
        assert _strict_violation(story, meta, grandfathered) is None, path.name


@pytest.mark.unit
def test_missing_grandfather_list_fails_closed(tmp_path: Path) -> None:
    assert (
        check_skeleton.load_stateless_grandfather(tmp_path / "nope.txt") == frozenset()
    )


@pytest.mark.unit
def test_strict_agency_blocks_only_under_strict(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        check_skeleton, "stateless_shell_violation", lambda *_: "strict agency: x"
    )
    assert check_skeleton.main([str(_DEMO_SHELL), "--allow-mvp"]) == 0
    capsys.readouterr()
    assert check_skeleton.main([str(_DEMO_SHELL), "--allow-mvp", "--strict"]) == 1
    assert "FAIL strict agency: x" in capsys.readouterr().err


def _dead_end_story(*, extra_choice: bool) -> dict:
    def ending(nid: str, valence: str) -> dict:
        node = _walk_ending(nid, "positive")
        node["ending"]["valence"] = valence
        return node

    nodes = [
        _walk_choice_node("a", ["b", "c"] + (["d"] if extra_choice else [])),
        ending("b", "negative"),
        ending("c", "negative"),
    ]
    if extra_choice:
        nodes.append(ending("d", "positive"))
    return _walk_story(nodes)


@pytest.mark.unit
def test_tier1_dead_end_flags_all_forbidden_decision() -> None:
    meta = {"age_band": "10-13"}
    assert check_skeleton.all_forbidden_decision_nodes(
        _dead_end_story(extra_choice=False), meta
    ) == ["a"]
    assert (
        check_skeleton.all_forbidden_decision_nodes(
            _dead_end_story(extra_choice=True), meta
        )
        == []
    )
    # The teen bands forbid death only, and these are not death endings.
    assert (
        check_skeleton.all_forbidden_decision_nodes(
            _dead_end_story(extra_choice=False), {"age_band": "13-16"}
        )
        == []
    )


@pytest.mark.unit
def test_tier1_dead_end_is_advisory_only(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        check_skeleton, "all_forbidden_decision_nodes", lambda *_: ["n1"]
    )
    assert check_skeleton.main([str(_DEMO_SHELL), "--allow-mvp"]) == 0
    assert "WARNING tier1-dead-end node=n1" in capsys.readouterr().out
