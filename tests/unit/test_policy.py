"""Unit tests for the age-policy gate layer (PL-15 through PL-26)."""

from __future__ import annotations

import random
import time

import networkx as nx
import pytest

from cyo_adventure.storybook.models import (
    AgeBand,
    Choice,
    ContentFlags,
    Ending,
    EndingKind,
    Length,
    NarrativeStyle,
    Node,
    ReadingLevel,
    Storybook,
    StoryMetadata,
    Topology,
    Valence,
)
from cyo_adventure.validator.band_profile import ARC_CEILING_MULTIPLE
from cyo_adventure.validator.policy import (
    _build_graph,
    _decision_node_ids,
    _fewest_decision_shortest_path,
    node_word_count,
    validate_policy,
)
from cyo_adventure.validator.report import Severity


def _story(
    *,
    age_band: str,
    kind: EndingKind,
    violence: str = "none",
    scariness: str = "none",
    peril: str = "none",
) -> Storybook:
    end = Node(
        id="n_end",
        body="done",
        is_ending=True,
        ending=Ending(id="e1", valence=Valence.NEGATIVE, kind=kind, title="End"),
    )
    start = Node(
        id="n0",
        body="go",
        choices=[
            {"id": "c1", "label": "a", "target": "n_end"},
            {"id": "c2", "label": "b", "target": "n_end"},
        ],
    )
    return Storybook(
        id="s1",
        version=1,
        title="T",
        start_node="n0",
        nodes=[start, end],
        metadata=StoryMetadata(
            age_band=age_band,
            reading_level=ReadingLevel(target=2.0),
            tier=1,
            estimated_minutes=5,
            ending_count=1,
            content_flags=ContentFlags(
                violence=violence, scariness=scariness, peril=peril
            ),
            topology=Topology.GAUNTLET,
        ),
    )


def test_pl15_blocks_death_ending_in_young_band():
    report = validate_policy(_story(age_band="5-8", kind=EndingKind.DEATH))
    assert any(f.rule_id == "PL-15" for f in report.errors)


def test_pl15_allows_death_in_older_band():
    report = validate_policy(_story(age_band="16+", kind=EndingKind.DEATH))
    assert not any(f.rule_id == "PL-15" for f in report.errors)


def test_pl15_blocks_capture_ending_in_young_band():
    # capture is the other forbidden kind for the young bands.
    report = validate_policy(_story(age_band="3-5", kind=EndingKind.CAPTURE))
    assert any(f.rule_id == "PL-15" for f in report.errors)


def test_pl16_blocks_content_over_band_ceiling():
    # 3-5 scariness ceiling is "mild"; "intense" exceeds it.
    report = validate_policy(
        _story(age_band="3-5", kind=EndingKind.SUCCESS, scariness="intense")
    )
    assert any(f.rule_id == "PL-16" for f in report.errors)


def test_pl16_allows_content_at_band_ceiling():
    # 3-5 scariness ceiling is exactly "mild"; a flag AT the ceiling must pass
    # (the rule uses strict ">" against the ceiling rank, not ">=").
    report = validate_policy(
        _story(age_band="3-5", kind=EndingKind.SUCCESS, scariness="mild")
    )
    assert not any(f.rule_id == "PL-16" for f in report.errors)


def test_pl16_blocks_violence_over_band_ceiling():
    # 3-5 violence ceiling is NONE; even "mild" violence must be blocked.
    report = validate_policy(
        _story(age_band="3-5", kind=EndingKind.SUCCESS, violence="mild")
    )
    assert any(f.rule_id == "PL-16" and "violence" in f.message for f in report.errors)


def test_pl16_blocks_peril_over_band_ceiling():
    # 3-5 peril ceiling is "mild"; "intense" exceeds it.
    report = validate_policy(
        _story(age_band="3-5", kind=EndingKind.SUCCESS, peril="intense")
    )
    assert any(f.rule_id == "PL-16" and "peril" in f.message for f in report.errors)


def _two_ending_story(age_band: str, topology: Topology) -> Storybook:
    e1 = Node(
        id="e1n",
        body="a",
        is_ending=True,
        ending=Ending(
            id="e1", valence=Valence.POSITIVE, kind=EndingKind.SUCCESS, title="A"
        ),
    )
    e2 = Node(
        id="e2n",
        body="b",
        is_ending=True,
        ending=Ending(
            id="e2", valence=Valence.NEUTRAL, kind=EndingKind.DISCOVERY, title="B"
        ),
    )
    start = Node(
        id="n0",
        body="go",
        choices=[
            Choice(id="c1", label="x", target="e1n"),
            Choice(id="c2", label="y", target="e2n"),
        ],
    )
    return Storybook(
        id="s",
        version=1,
        title="T",
        start_node="n0",
        nodes=[start, e1, e2],
        metadata=StoryMetadata(
            age_band=age_band,
            reading_level=ReadingLevel(target=2.0),
            tier=1,
            estimated_minutes=5,
            ending_count=2,
            topology=topology,
        ),
    )


def test_pl17_blocks_too_few_endings():
    # 13-16 requires 4 endings; this story has 2.
    report = validate_policy(_two_ending_story("13-16", Topology.TIME_CAVE))
    assert any(f.rule_id == "PL-17" and "ending" in f.message for f in report.errors)


def test_pl18_blocks_mislabelled_topology():
    # A pure two-branch tree is TIME_CAVE; label it LOOP_AND_GROW and PL-18 fires.
    report = validate_policy(_two_ending_story("3-5", Topology.LOOP_AND_GROW))
    assert any(f.rule_id == "PL-18" for f in report.errors)


def test_pl18_accepts_admissible_topology():
    report = validate_policy(_two_ending_story("3-5", Topology.TIME_CAVE))
    assert not any(f.rule_id == "PL-18" for f in report.errors)


def test_pl17_blocks_too_few_decisions():
    # 13-16 requires 4 decision nodes; this story has 1.
    report = validate_policy(_two_ending_story("13-16", Topology.TIME_CAVE))
    assert any(f.rule_id == "PL-17" and "decision" in f.message for f in report.errors)


def test_fully_compliant_story_has_no_policy_findings():
    # 3-5 needs 2 endings / 1 decision; this story meets every floor, ceiling,
    # forbidden-kind and topology rule, so the policy report is empty.
    report = validate_policy(_two_ending_story("3-5", Topology.TIME_CAVE))
    assert report.ok
    assert report.findings == []


# --- PL-19 words-per-node and PL-20 fastest-finish arc floor -------------------


def test_node_word_count_reads_fill_directive():
    """A skeleton FILL directive contributes its declared word target."""
    assert node_word_count("<<FILL role=setup words=85 beats='a b c'>>") == 85


def test_node_word_count_counts_prose_words():
    """A filled (prose) body contributes its actual word count."""
    assert node_word_count("one two three four five") == 5


def test_node_word_count_fill_without_words_is_zero():
    """A FILL directive with no words= token counts as zero (no per-node min)."""
    assert node_word_count("<<FILL role=setup beats='x'>>") == 0


def _fill(words: int) -> str:
    """A FILL directive body with an exact declared word target."""
    return f"<<FILL role=x words={words} beats='b'>>"


def _linear_scale_story(
    *,
    middles: int,
    ending_kind: EndingKind = EndingKind.SUCCESS,
    age_band: AgeBand = AgeBand.BAND_8_11,
    length: Length | None = Length.SHORT,
    narrative_style: NarrativeStyle = NarrativeStyle.PROSE,
    words: int = 100,
    production_eligible: bool = True,
) -> Storybook:
    """Build ``start -> m0 -> ... -> end``: one linear satisfying path.

    The satisfying-completion path is ``middles + 2`` nodes (start + middles +
    end). Bodies are FILL directives so the per-node word budget is exact.
    """
    body = _fill(words)
    first = "m0" if middles > 0 else "n_end"
    nodes: list[Node] = [
        Node(id="n0", body=body, choices=[Choice(id="c0", label="go", target=first)])
    ]
    for i in range(middles):
        target = f"m{i + 1}" if i + 1 < middles else "n_end"
        nodes.append(
            Node(
                id=f"m{i}",
                body=body,
                choices=[Choice(id=f"cm{i}", label="go", target=target)],
            )
        )
    nodes.append(
        Node(
            id="n_end",
            body=body,
            is_ending=True,
            ending=Ending(
                id="e1", valence=Valence.POSITIVE, kind=ending_kind, title="End"
            ),
        )
    )
    return Storybook(
        id="s",
        version=1,
        title="T",
        start_node="n0",
        nodes=nodes,
        metadata=StoryMetadata(
            age_band=age_band,
            reading_level=ReadingLevel(target=2.0),
            tier=1,
            estimated_minutes=5,
            ending_count=1,
            topology=Topology.GAUNTLET,
            length=length,
            narrative_style=narrative_style,
            production_eligible=production_eligible,
        ),
    )


def test_pl19_blocks_node_over_per_node_max():
    """A node whose word budget exceeds the band+style per-node max blocks."""
    over = "word " * 100  # 100 prose words, over the 3-5 prose max of 90
    win = Node(
        id="e1n",
        body="a",
        is_ending=True,
        ending=Ending(
            id="e1", valence=Valence.POSITIVE, kind=EndingKind.SUCCESS, title="A"
        ),
    )
    other = Node(
        id="e2n",
        body="b",
        is_ending=True,
        ending=Ending(
            id="e2", valence=Valence.NEUTRAL, kind=EndingKind.DISCOVERY, title="B"
        ),
    )
    start = Node(
        id="n0",
        body=over,
        choices=[
            Choice(id="c1", label="x", target="e1n"),
            Choice(id="c2", label="y", target="e2n"),
        ],
    )
    story = Storybook(
        id="s",
        version=1,
        title="T",
        start_node="n0",
        nodes=[start, win, other],
        metadata=StoryMetadata(
            age_band=AgeBand.BAND_3_5,
            reading_level=ReadingLevel(target=1.0),
            tier=1,
            estimated_minutes=5,
            ending_count=2,
            topology=Topology.TIME_CAVE,
        ),
    )
    report = validate_policy(story)
    assert any(f.rule_id == "PL-19" and f.node_id == "n0" for f in report.errors)


def test_pl19_warns_when_scale_story_mean_below_advisory():
    """A scale-classified story whose mean words/node is off-band warns (PL-19)."""
    # 8-11 short advisory mean band is 70-135; 40-word nodes average below it.
    report = validate_policy(_linear_scale_story(middles=7, words=40))
    assert any(f.rule_id == "PL-19" for f in report.warnings)


def test_pl19_mean_not_checked_without_length():
    """A story with no length is not scale-classified, so the mean is not judged."""
    report = validate_policy(_linear_scale_story(middles=7, words=40, length=None))
    assert not any(f.rule_id == "PL-19" for f in report.warnings)


def test_pl20_blocks_too_short_satisfying_path():
    """A scale story whose shortest win is below the arc floor blocks (PL-20)."""
    # 8-11 short floor is 9 nodes; start -> end is only 2.
    report = validate_policy(_linear_scale_story(middles=0))
    assert any(f.rule_id == "PL-20" for f in report.errors)


def test_pl20_allows_path_meeting_the_floor():
    """A satisfying path that meets the arc floor passes PL-20."""
    # 8-11 short floor is 9 nodes; start + 7 middles + end is exactly 9.
    report = validate_policy(_linear_scale_story(middles=7))
    assert not any(f.rule_id == "PL-20" for f in report.errors)


# --- PL-17 breadth-scaled floors ----------------------------------------------


def _wide_scale_story(
    *,
    node_count: int,
    endings: int,
    decisions: int,
    age_band: AgeBand = AgeBand.BAND_8_11,
    length: Length | None = Length.MEDIUM,
    narrative_style: NarrativeStyle = NarrativeStyle.PROSE,
) -> Storybook:
    """Build a wide story with exact node, ending, and decision counts.

    Structure: a start node, ``decisions`` two-choice decision nodes, ``endings``
    success endings, and single-choice filler nodes padding to ``node_count``.
    Targets all resolve to real nodes; the shape reconverges, so it is declared
    ``branch_and_bottleneck`` to keep PL-18 clean. (PL-20's arc floor is not the
    subject here, so tests filter on the PL-17 rule id.)
    """
    nodes: list[Node] = [
        Node(
            id=f"e{i}",
            body=_fill(50),
            is_ending=True,
            ending=Ending(
                id=f"end{i}",
                valence=Valence.POSITIVE,
                kind=EndingKind.SUCCESS,
                title="W",
            ),
        )
        for i in range(endings)
    ]
    second = "e1" if endings > 1 else "e0"
    nodes.extend(
        Node(
            id=f"d{i}",
            body=_fill(50),
            choices=[
                Choice(id=f"d{i}a", label="a", target="e0"),
                Choice(id=f"d{i}b", label="b", target=second),
            ],
        )
        for i in range(decisions)
    )
    fillers = node_count - endings - decisions - 1  # minus the start node
    nodes.extend(
        Node(
            id=f"f{i}",
            body=_fill(50),
            choices=[Choice(id=f"f{i}c", label="go", target="e0")],
        )
        for i in range(fillers)
    )
    start_target = "d0" if decisions else "e0"
    nodes.insert(
        0,
        Node(
            id="n0",
            body=_fill(50),
            choices=[Choice(id="c0", label="go", target=start_target)],
        ),
    )
    return Storybook(
        id="s",
        version=1,
        title="T",
        start_node="n0",
        nodes=nodes,
        metadata=StoryMetadata(
            age_band=age_band,
            reading_level=ReadingLevel(target=2.0),
            tier=1,
            estimated_minutes=5,
            ending_count=max(1, endings),
            topology=Topology.BRANCH_AND_BOTTLENECK,
            length=length,
            narrative_style=narrative_style,
        ),
    )


def test_pl17_scaled_endings_floor_blocks_large_thin_story():
    """A large scale story with only band-floor endings trips the scaled floor."""
    # 8-11 medium, 100 nodes: prose endings floor = ceil(100 * 0.15) = 15.
    # 3 endings clears the band floor (3) but not the breadth-scaled floor.
    report = validate_policy(_wide_scale_story(node_count=100, endings=3, decisions=40))
    assert any(
        f.rule_id == "PL-17" and "ending" in f.message and "scale-adjusted" in f.message
        for f in report.errors
    )


def test_pl17_scaled_decisions_floor_blocks_near_linear_story():
    """A large scale story with too few decision nodes trips the scaled floor."""
    # 8-11 medium, 100 nodes: decisions floor = ceil(100 * 0.08) = 8.
    # 3 decisions clears the band floor (3) but not the breadth-scaled floor.
    report = validate_policy(_wide_scale_story(node_count=100, endings=20, decisions=3))
    assert any(
        f.rule_id == "PL-17"
        and "decision" in f.message
        and "scale-adjusted" in f.message
        for f in report.errors
    )


def test_pl17_scaled_floor_passes_when_breadth_met():
    """A scale story meeting the breadth-scaled floors has no PL-17 finding."""
    # 100 nodes: endings floor 15, decisions floor 8; supply 20 and 12.
    report = validate_policy(
        _wide_scale_story(node_count=100, endings=20, decisions=12)
    )
    assert not any(f.rule_id == "PL-17" for f in report.errors)


def test_pl17_length_less_story_keeps_band_floor_only():
    """A length-less story is not scale-classified; only the band floor applies."""
    # 100 nodes, 8-11 band floor is 3 endings / 3 decisions. With no length the
    # breadth floor (which would demand 15/8) must NOT apply, so 4/4 passes.
    report = validate_policy(
        _wide_scale_story(node_count=100, endings=4, decisions=4, length=None)
    )
    assert not any(f.rule_id == "PL-17" for f in report.errors)


# --- PL-21 off-matrix cell rejection ------------------------------------------


def test_pl21_blocks_off_matrix_length():
    """A 3-5 'long' story is off-matrix (young bands cap at Medium) and blocks."""
    report = validate_policy(
        _linear_scale_story(middles=5, age_band=AgeBand.BAND_3_5, length=Length.LONG)
    )
    assert any(f.rule_id == "PL-21" for f in report.errors)


def test_pl21_blocks_gamebook_for_young_band():
    """An 8-11 gamebook is off-matrix (gamebook is 13-16/16+ only) and blocks."""
    report = validate_policy(
        _linear_scale_story(
            middles=5, length=Length.MEDIUM, narrative_style=NarrativeStyle.GAMEBOOK
        )
    )
    assert any(f.rule_id == "PL-21" for f in report.errors)


def test_pl21_allows_offered_cell():
    """An offered cell (8-11 short prose) raises no PL-21 finding."""
    report = validate_policy(_linear_scale_story(middles=7, length=Length.SHORT))
    assert not any(f.rule_id == "PL-21" for f in report.errors)


def test_pl21_not_checked_without_length():
    """A length-less story is not scale-classified, so PL-21 does not apply."""
    report = validate_policy(_linear_scale_story(middles=5, length=None))
    assert not any(f.rule_id == "PL-21" for f in report.errors)


def test_pl20_skipped_without_length():
    """A non-scale story (no length) has no arc floor."""
    report = validate_policy(_linear_scale_story(middles=0, length=None))
    assert not any(f.rule_id == "PL-20" for f in report.errors)


def test_pl20_skipped_for_mvp_even_with_length():
    """An MVP (non-production) story waives the arc floor even with a length."""
    report = validate_policy(_linear_scale_story(middles=0, production_eligible=False))
    assert not any(f.rule_id == "PL-20" for f in report.errors)


def test_pl20_allows_fast_fail_when_win_is_deep():
    """A quick fail-fast ending is fine; only the winning path is floored."""
    body = _fill(100)
    nodes: list[Node] = [
        Node(
            id="n0",
            body=body,
            choices=[
                Choice(id="c_win", label="win", target="w0"),
                Choice(id="c_fail", label="fail", target="n_fail"),
            ],
        )
    ]
    for i in range(7):  # w0..w6, then n_win: a 9-node winning path
        target = f"w{i + 1}" if i < 6 else "n_win"
        nodes.append(
            Node(
                id=f"w{i}",
                body=body,
                choices=[Choice(id=f"cw{i}", label="go", target=target)],
            )
        )
    nodes.append(
        Node(
            id="n_win",
            body=body,
            is_ending=True,
            ending=Ending(
                id="ew", valence=Valence.POSITIVE, kind=EndingKind.SUCCESS, title="Win"
            ),
        )
    )
    nodes.append(
        Node(
            id="n_fail",
            body=body,
            is_ending=True,
            ending=Ending(
                id="ef", valence=Valence.NEGATIVE, kind=EndingKind.SETBACK, title="Fail"
            ),
        )
    )
    story = Storybook(
        id="s",
        version=1,
        title="T",
        start_node="n0",
        nodes=nodes,
        metadata=StoryMetadata(
            age_band=AgeBand.BAND_8_11,
            reading_level=ReadingLevel(target=2.0),
            tier=1,
            estimated_minutes=5,
            ending_count=2,
            topology=Topology.GAUNTLET,
            length=Length.SHORT,
        ),
    )
    report = validate_policy(story)
    assert not any(f.rule_id == "PL-20" for f in report.errors)


def test_validate_policy_fails_closed_when_profile_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unconfigured band profile must block, not silently skip (fail closed).

    Owner ruling 2026-07-16: a band with no configured BandProfile must not
    let a story through PL-15/16/17 unvalidated. test_profiles_match_age_band_enum_exactly
    guarantees every real AgeBand has a configured profile, so this branch is
    unreachable through any valid Storybook; that lockstep test is kept as
    defense in depth. This test exercises the runtime behavior directly by
    monkeypatching profile_for at its policy.py import site, proving the gate
    itself fails closed rather than relying solely on the enum lockstep.
    """
    monkeypatch.setattr(
        "cyo_adventure.validator.policy.profile_for", lambda _band: None
    )
    story = _story(age_band="8-11", kind=EndingKind.SUCCESS)
    report = validate_policy(story)
    assert report.ok is False
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.rule_id == "PL-22"
    assert finding.severity is Severity.ERROR
    assert finding.story_id == story.id
    assert "band profile not configured" in finding.message
    assert "8-11" in finding.message


@pytest.mark.parametrize("band", ["3-5", "5-8", "8-11", "10-13", "13-16", "16+"])
def test_validate_policy_never_emits_pl22_for_a_configured_band(band: str) -> None:
    """Every real, configured band must validate exactly as before: no PL-22.

    The PL-22 fail-closed guard exists for the unconfigured-band branch only;
    it must never fire for any band that ``band_profile._PROFILES`` actually
    configures. Uses a benign SUCCESS ending with no content flags so no other
    PL rule fires either, isolating the assertion to PL-22.
    """
    report = validate_policy(_story(age_band=band, kind=EndingKind.SUCCESS))
    assert not any(f.rule_id == "PL-22" for f in report.findings)


# ---------------------------------------------------------------------------
# PL-23 declared read time vs the derived clock (AL-021)
# ---------------------------------------------------------------------------


def _clock_story(*, estimated_minutes: int, words: int) -> Storybook:
    """A two-node story with a satisfying ending and a known path word count."""
    end = Node(
        id="n_end",
        body="w " * (words // 2),
        is_ending=True,
        ending=Ending(
            id="e1", valence=Valence.POSITIVE, kind=EndingKind.COMPLETION, title="Win"
        ),
    )
    start = Node(
        id="n0",
        body="w " * (words - words // 2),
        choices=[{"id": "c1", "label": "a", "target": "n_end"}],
    )
    return Storybook(
        id="clock",
        version=1,
        title="T",
        start_node="n0",
        nodes=[start, end],
        metadata=StoryMetadata(
            age_band="16+",
            reading_level=ReadingLevel(target=9.0),
            tier=1,
            estimated_minutes=estimated_minutes,
            ending_count=1,
            content_flags=ContentFlags(violence="none", scariness="none", peril="none"),
            topology=Topology.BRANCH_AND_BOTTLENECK,
        ),
    )


def test_pl23_warns_when_declared_read_time_is_far_from_derived() -> None:
    """A 3x overstatement of estimated_minutes is surfaced as an advisory."""
    # 440 words at the 16+ anchor of 220 wpm is a 2-minute fastest finish.
    report = validate_policy(_clock_story(estimated_minutes=6, words=440))
    pl23 = [f for f in report.findings if f.rule_id == "PL-23"]
    assert len(pl23) == 1
    assert pl23[0].severity is Severity.WARNING, "the clock is advisory, never blocking"
    assert "derived fastest-finish clock 2 min" in pl23[0].message


def test_pl23_is_silent_when_the_declared_clock_matches() -> None:
    """A correct declaration produces no finding."""
    report = validate_policy(_clock_story(estimated_minutes=2, words=440))
    assert not [f for f in report.findings if f.rule_id == "PL-23"]


# ---------------------------------------------------------------------------
# PL-24 ending mix (AL-015)
# ---------------------------------------------------------------------------


def _mix_story(
    *, kinds: list[tuple[EndingKind, Valence]], style: NarrativeStyle
) -> Storybook:
    """A story whose ending mix is exactly the supplied kind/valence list."""
    ends = [
        Node(
            id=f"n_end{i}",
            body="done",
            is_ending=True,
            ending=Ending(id=f"e{i}", valence=valence, kind=kind, title=f"E{i}"),
        )
        for i, (kind, valence) in enumerate(kinds)
    ]
    start = Node(
        id="n0",
        body="go",
        choices=[
            {"id": f"c{i}", "label": "a", "target": node.id}
            for i, node in enumerate(ends)
        ],
    )
    return Storybook(
        id="mix",
        version=1,
        title="T",
        start_node="n0",
        nodes=[start, *ends],
        metadata=StoryMetadata(
            age_band="16+",
            reading_level=ReadingLevel(target=9.0),
            tier=1,
            estimated_minutes=1,
            ending_count=len(ends),
            content_flags=ContentFlags(violence="none", scariness="none", peril="none"),
            topology=Topology.BRANCH_AND_BOTTLENECK,
            narrative_style=style,
        ),
    )


def test_pl24_warns_when_one_ending_kind_dominates() -> None:
    """A story that is almost entirely one kind is surfaced."""
    kinds = [(EndingKind.SETBACK, Valence.NEGATIVE)] * 9
    kinds += [(EndingKind.COMPLETION, Valence.POSITIVE)]
    report = validate_policy(_mix_story(kinds=kinds, style=NarrativeStyle.GAMEBOOK))
    dominant = [f for f in report.findings if "is 9 of 10 endings" in f.message]
    assert len(dominant) == 1
    assert dominant[0].rule_id == "PL-24"
    assert dominant[0].severity is Severity.WARNING


def test_pl24_gamebook_floor_is_a_count_not_a_share() -> None:
    """A gamebook with one winnable ending warns even though breadth is intended.

    Calibration note: every catalog gamebook sits at 2-5% positive-valence
    endings, so a share floor would flag the whole style. The absolute floor
    catches the real defect instead.
    """
    kinds: list[tuple[EndingKind, Valence]] = [
        (EndingKind.DEATH, Valence.NEGATIVE)
    ] * 40
    kinds += [(EndingKind.COMPLETION, Valence.POSITIVE)]
    report = validate_policy(_mix_story(kinds=kinds, style=NarrativeStyle.GAMEBOOK))
    winnable = [f for f in report.findings if "positive-valence ending(s)" in f.message]
    assert len(winnable) == 1, "one winnable ending in 41 must be surfaced"
    assert "below the gamebook floor of 3" in winnable[0].message


def test_pl24_gamebook_with_enough_winnable_endings_is_silent() -> None:
    """Few wins and many fails is the declared gamebook shape, not a defect."""
    kinds: list[tuple[EndingKind, Valence]] = [
        (EndingKind.DEATH, Valence.NEGATIVE)
    ] * 40
    kinds += [(EndingKind.SUCCESS, Valence.POSITIVE)] * 3
    report = validate_policy(_mix_story(kinds=kinds, style=NarrativeStyle.GAMEBOOK))
    assert not [f for f in report.findings if "positive-valence ending(s)" in f.message]


def test_pl24_prose_uses_a_share_floor() -> None:
    """Prose is held to a share, where a low win rate is a real signal."""
    kinds: list[tuple[EndingKind, Valence]] = [
        (EndingKind.SETBACK, Valence.NEUTRAL)
    ] * 19
    kinds += [(EndingKind.COMPLETION, Valence.POSITIVE)]
    report = validate_policy(_mix_story(kinds=kinds, style=NarrativeStyle.PROSE))
    share = [f for f in report.findings if "below the prose floor" in f.message]
    assert len(share) == 1, "1 positive in 20 (5%) is below the 10% prose floor"


# --- PL-25 depth to first decision and PL-26 decision density -----------------


def _branch_at_depth(
    *,
    lead_in: int,
    age_band: AgeBand = AgeBand.BAND_8_11,
    length: Length | None = None,
    words: int = 100,
) -> Storybook:
    """Build a lead-in corridor whose last node offers the first decision.

    ``n0 -> ... -> n{lead_in}``, where ``n{lead_in}`` branches to a success and a
    discovery ending. The first decision therefore sits exactly ``lead_in + 1``
    nodes in, which is what PL-25 measures. ``length`` defaults to ``None`` so
    the story is not scale-classified and PL-20/PL-26 stay silent, isolating the
    rule under test.

    Args:
        lead_in: Single-choice nodes before the decision node.
        age_band: The band whose PL-25 window applies.
        length: Declared length, or ``None`` to skip the scale-classified rules.
        words: Declared word target per node. The default of 100 is the 8-11
            mean, so a default-built story's node count and word count agree on
            every PL-25 verdict; vary it to separate the two readings.

    Returns:
        The assembled Storybook.
    """
    body = _fill(words)
    nodes: list[Node] = [
        Node(
            id=f"n{i}",
            body=body,
            choices=[Choice(id=f"c{i}", label="on", target=f"n{i + 1}")],
        )
        for i in range(lead_in)
    ]
    nodes.append(
        Node(
            id=f"n{lead_in}",
            body=body,
            choices=[
                Choice(id="cw", label="win", target="n_win"),
                Choice(id="ca", label="look", target="n_alt"),
            ],
        )
    )
    nodes += [
        Node(
            id="n_win",
            body=body,
            is_ending=True,
            ending=Ending(
                id="e1", valence=Valence.POSITIVE, kind=EndingKind.SUCCESS, title="W"
            ),
        ),
        Node(
            id="n_alt",
            body=body,
            is_ending=True,
            ending=Ending(
                id="e2", valence=Valence.NEUTRAL, kind=EndingKind.DISCOVERY, title="A"
            ),
        ),
    ]
    return Storybook(
        id="s",
        version=1,
        title="T",
        start_node="n0",
        nodes=nodes,
        metadata=StoryMetadata(
            age_band=age_band,
            reading_level=ReadingLevel(target=2.0),
            tier=1,
            estimated_minutes=5,
            ending_count=2,
            topology=Topology.TIME_CAVE,
            length=length,
        ),
    )


def test_pl25_warns_on_first_decision_past_band_ceiling():
    """One node past the 8-11 ceiling of 9 warns rather than blocks.

    A ceiling overshoot is a craft defect, and the ERROR tier means the story is
    unpublishable. Grading a narrow overshoot as fatal would block work on a
    margin narrower than the calibration's own confidence.
    """
    report = validate_policy(_branch_at_depth(lead_in=9))
    assert any(f.rule_id == "PL-25" for f in report.warnings)
    assert not any(f.rule_id == "PL-25" for f in report.errors)


def test_pl25_blocks_first_decision_past_the_hard_limit():
    """Past ``ARC_CEILING_MULTIPLE`` x the ceiling, the shape does block."""
    hard = int(9 * ARC_CEILING_MULTIPLE)
    report = validate_policy(_branch_at_depth(lead_in=hard))
    assert any(f.rule_id == "PL-25" for f in report.errors)


def test_pl25_hard_limit_derives_from_the_measured_arc_multiple():
    """The blocking tier tracks the constant, not a hand-copied number.

    Guards the linkage: re-deriving ``ARC_CEILING_MULTIPLE`` from new corpus data
    must move this threshold with it, so the two cannot drift apart silently.
    """
    hard = int(9 * ARC_CEILING_MULTIPLE)
    at_limit = validate_policy(_branch_at_depth(lead_in=hard - 1))
    assert not any(f.rule_id == "PL-25" for f in at_limit.errors)
    assert any(f.rule_id == "PL-25" for f in at_limit.warnings)


def test_pl25_allows_first_decision_at_the_ceiling():
    """A first decision exactly at the band ceiling passes."""
    report = validate_policy(_branch_at_depth(lead_in=8))
    assert not any(f.rule_id == "PL-25" for f in report.findings)


def test_pl25_blocks_a_cold_open():
    """A start node that already branches is under the floor, so it blocks."""
    report = validate_policy(_branch_at_depth(lead_in=0))
    findings = [f for f in report.errors if f.rule_id == "PL-25"]
    assert len(findings) == 1
    assert "under the band" in findings[0].message


def test_pl25_grades_its_floor_and_ceiling_differently():
    """The floor blocks in one tier; the ceiling warns until the hard limit.

    Guards the asymmetry deliberately, because the two directions are not the
    same kind of defect. Opening on the first choice leaves the reader nothing
    to choose about, which no amount of degree makes acceptable. Burying it is a
    pacing fault that only becomes fatal well past the window.
    """
    cold = validate_policy(_branch_at_depth(lead_in=0))
    buried = validate_policy(_branch_at_depth(lead_in=9))
    assert any(f.rule_id == "PL-25" for f in cold.errors)
    assert not any(f.rule_id == "PL-25" for f in cold.warnings)
    assert any(f.rule_id == "PL-25" for f in buried.warnings)
    assert not any(f.rule_id == "PL-25" for f in buried.errors)


def test_pl25_allows_cold_open_at_3_5():
    """3-5 has a floor of 1, so a pre-reader story may open on its choice."""
    report = validate_policy(_branch_at_depth(lead_in=0, age_band=AgeBand.BAND_3_5))
    assert not any(f.rule_id == "PL-25" for f in report.findings)


def test_pl25_floor_accepts_a_cold_open_that_covers_the_ground_in_words():
    """A single opening scene worth 2 nodes of prose clears the 8-11 floor of 2.

    The JHM anchor counts pages, not authoring units, so an opening that carries
    the floor's worth of situation satisfies the floor however its node
    boundaries fall. 210 words is over 2 x the band mean of 100 and still under
    PL-19's per-node max of 220, so the story is legal on both rules at once.
    """
    report = validate_policy(_branch_at_depth(lead_in=0, words=210))
    assert not any(f.rule_id == "PL-25" for f in report.findings)


def test_pl25_floor_still_blocks_a_cold_open_that_covers_no_ground():
    """The word reading does not retire the floor: a thin cold open still blocks.

    The contrast case for the test above. Same shape, same band, one node before
    the first choice; only the prose behind it differs, and 100 words is under
    the 200 the floor stands for.
    """
    report = validate_policy(_branch_at_depth(lead_in=0, words=100))
    assert any(f.rule_id == "PL-25" for f in report.errors)


def test_pl25_ceiling_accepts_a_deep_opening_told_in_short_beats():
    """Ten 30-word beats are 300 words, inside the 8-11 ceiling's 900.

    The ceiling carries the same unit defect as the floor and in the same
    direction: told in beats rather than pages, an opening reaches a high node
    count without burying the choice in reading time.
    """
    report = validate_policy(_branch_at_depth(lead_in=9, words=30))
    assert not any(f.rule_id == "PL-25" for f in report.findings)


def test_pl25_hard_limit_accepts_short_beats_and_still_blocks_long_ones():
    """Past the hard limit, the word reading separates a real prologue from beats.

    Both stories put the first decision the same number of nodes in, well past
    ``ARC_CEILING_MULTIPLE`` x the ceiling. Only the one whose prose also runs
    past the hard limit's word equivalent is the unbranching prologue the
    blocking tier exists to catch.
    """
    hard = int(9 * ARC_CEILING_MULTIPLE)
    beats = validate_policy(_branch_at_depth(lead_in=hard, words=30))
    prologue = validate_policy(_branch_at_depth(lead_in=hard, words=100))
    assert not any(f.rule_id == "PL-25" for f in beats.findings)
    assert any(f.rule_id == "PL-25" for f in prologue.errors)


def test_pl25_word_reading_does_not_depend_on_node_ids():
    """Two equally short openings of different lengths: renaming cannot flip it.

    ``n0`` forks into a 40-word beat and a 220-word scene that rejoin on the
    first decision, so the two fewest-node openings carry very different word
    counts. Reading one arbitrarily chosen path would make the verdict a
    property of the ids; ``_opening_extent`` brackets them instead, so shuffling
    the ids must leave the finding set identical. Same trap as PL-26's, caught
    by the same shape of test.
    """

    def build(fork_a: str, fork_b: str) -> Storybook:
        end = Node(
            id="n_win",
            body=_fill(100),
            is_ending=True,
            ending=Ending(
                id="e1", valence=Valence.POSITIVE, kind=EndingKind.SUCCESS, title="W"
            ),
        )
        alt = Node(
            id="n_alt",
            body=_fill(100),
            is_ending=True,
            ending=Ending(
                id="e2", valence=Valence.NEUTRAL, kind=EndingKind.DISCOVERY, title="A"
            ),
        )
        return Storybook(
            id="s",
            version=1,
            title="T",
            start_node="n0",
            nodes=[
                Node(
                    id="n0",
                    body=_fill(40),
                    choices=[
                        Choice(id="ca", label="a", target=fork_a),
                        Choice(id="cb", label="b", target=fork_b),
                    ],
                ),
                Node(
                    id=fork_a,
                    body=_fill(40),
                    choices=[Choice(id="fa", label="on", target="n_dec")],
                ),
                Node(
                    id=fork_b,
                    body=_fill(220),
                    choices=[Choice(id="fb", label="on", target="n_dec")],
                ),
                Node(
                    id="n_dec",
                    body=_fill(100),
                    choices=[
                        Choice(id="cw", label="win", target="n_win"),
                        Choice(id="cx", label="look", target="n_alt"),
                    ],
                ),
                end,
                alt,
            ],
            metadata=StoryMetadata(
                age_band=AgeBand.BAND_8_11,
                reading_level=ReadingLevel(target=2.0),
                tier=1,
                estimated_minutes=5,
                ending_count=2,
                topology=Topology.TIME_CAVE,
            ),
        )

    original = validate_policy(build("a_short", "z_long"))
    renamed = validate_policy(build("z_short", "a_long"))
    assert [f.message for f in original.findings if f.rule_id == "PL-25"] == [
        f.message for f in renamed.findings if f.rule_id == "PL-25"
    ]


def test_pl25_word_reading_only_ever_relaxes():
    """A story inside the node window never starts failing on its word count.

    Five 200-word nodes are 1,000 words, past the 8-11 ceiling's 900-word
    equivalent, but the node count is inside the window and that alone decides.
    Guards the one-way property the relaxation rests on: no story that passes
    today can be failed by the added reading.
    """
    report = validate_policy(_branch_at_depth(lead_in=4, words=200))
    assert not any(f.rule_id == "PL-25" for f in report.findings)


def test_pl25_silent_when_story_has_no_decision():
    """A story with no decision node is left to PL-17, not double-reported."""
    report = validate_policy(_linear_scale_story(middles=7))
    assert not any(f.rule_id == "PL-25" for f in report.findings)


def _dense_spine(
    *,
    spine: int,
    decision_every: int,
    age_band: AgeBand = AgeBand.BAND_8_11,
    length: Length = Length.SHORT,
    narrative_style: NarrativeStyle = NarrativeStyle.PROSE,
    words: int = 100,
) -> Storybook:
    """Build a spine to a win where every Nth node also offers an escape choice.

    The fastest-finish path is ``spine + 1`` nodes and carries
    ``ceil(spine / decision_every)`` decisions, so the PL-26 density is
    controllable directly.

    Args:
        spine: Non-ending nodes on the winning path.
        decision_every: Offer a second choice on every Nth spine node.
        age_band: The story band.
        length: The declared length (scale-classifies the story).
        narrative_style: ``prose`` or ``gamebook``; selects the PL-26 window.
        words: Per-node declared word budget.

    Returns:
        The assembled Storybook.
    """
    body = _fill(words)
    nodes: list[Node] = []
    for i in range(spine):
        target = f"s{i + 1}" if i + 1 < spine else "n_win"
        choices = [Choice(id=f"c{i}", label="on", target=target)]
        if i % decision_every == 0:
            choices.append(Choice(id=f"x{i}", label="aside", target="n_alt"))
        nodes.append(Node(id=f"s{i}", body=body, choices=choices))
    nodes += [
        Node(
            id="n_win",
            body=body,
            is_ending=True,
            ending=Ending(
                id="e1", valence=Valence.POSITIVE, kind=EndingKind.SUCCESS, title="W"
            ),
        ),
        Node(
            id="n_alt",
            body=body,
            is_ending=True,
            ending=Ending(
                id="e2", valence=Valence.NEUTRAL, kind=EndingKind.DISCOVERY, title="A"
            ),
        ),
    ]
    return Storybook(
        id="s",
        version=1,
        title="T",
        start_node="s0",
        nodes=nodes,
        metadata=StoryMetadata(
            age_band=age_band,
            reading_level=ReadingLevel(target=2.0),
            tier=1,
            estimated_minutes=5,
            ending_count=2,
            topology=Topology.BRANCH_AND_BOTTLENECK,
            length=length,
            narrative_style=narrative_style,
        ),
    )


def test_pl26_warns_when_choices_come_too_rarely():
    """A near-corridor warns: one decision over a 12-node fastest finish."""
    report = validate_policy(_dense_spine(spine=11, decision_every=11))
    assert any(f.rule_id == "PL-26" for f in report.warnings)


def test_pl26_accepts_prose_density_near_the_measured_anchor():
    """A choice roughly every third node sits under the prose ceiling."""
    # 12-node fastest finish carrying 4 decisions is 3.0, near the JHM 3.28 mean.
    report = validate_policy(_dense_spine(spine=11, decision_every=3))
    assert not any(f.rule_id == "PL-26" for f in report.findings)


def test_pl26_does_not_bound_density_from_below():
    """A choice on every node is dense, not a corridor, so PL-26 stays silent.

    PL-26 is a ceiling only. A shortest path is biased toward decision nodes by
    construction (out-degree >= 2 makes a node likelier to sit on a fast route),
    so a low measured density is an artifact of the measurement rather than
    evidence of a defect.
    """
    report = validate_policy(_dense_spine(spine=11, decision_every=1))
    assert not any(f.rule_id == "PL-26" for f in report.findings)


def test_pl26_gamebook_ceiling_is_tighter_than_prose():
    """One density, two verdicts: fine as prose, a corridor as a gamebook.

    21-node fastest finish over 5 decisions is 4.2, under the 13-16 prose ceiling
    of 4.29 and over the gamebook ceiling of 4.0. A gamebook that steers this
    rarely has abandoned the genre's own section-by-section pacing.

    The window is narrow, and deliberately measured at 13-16. PL-26's prose
    ceiling is now derived per band so it bounds the same number of WORDS between
    decisions at every band; the gamebook ceiling stays a flat, product-defined
    4.0 with no page anchor to convert. The two therefore CROSS: gamebook is
    tighter than prose at 13-16 (4.0 vs 4.29) and looser at 16+ (4.0 vs 3.43), so
    this property is band-specific rather than universal (`UW-C287`).
    """
    kwargs = {
        "spine": 20,
        "decision_every": 4,
        "age_band": AgeBand.BAND_13_16,
        "length": Length.MEDIUM,
        "words": 65,
    }
    as_prose = validate_policy(
        _dense_spine(narrative_style=NarrativeStyle.PROSE, **kwargs)
    )
    as_gamebook = validate_policy(
        _dense_spine(narrative_style=NarrativeStyle.GAMEBOOK, **kwargs)
    )
    assert not any(f.rule_id == "PL-26" for f in as_prose.findings)
    assert any(f.rule_id == "PL-26" for f in as_gamebook.warnings)


def test_pl26_warns_when_fastest_finish_offers_no_decision():
    """A corridor to a win reports the absence of any decision distinctly."""
    report = validate_policy(_linear_scale_story(middles=7))
    findings = [f for f in report.warnings if f.rule_id == "PL-26"]
    assert len(findings) == 1
    assert "no decision at all" in findings[0].message


def test_pl26_is_never_an_error():
    """Density is advisory only; it must not block a story."""
    report = validate_policy(_dense_spine(spine=11, decision_every=11))
    assert not any(f.rule_id == "PL-26" for f in report.errors)


def test_pl26_skipped_without_length():
    """An unclassified story has no cell, so density is not judged."""
    report = validate_policy(_branch_at_depth(lead_in=3))
    assert not any(f.rule_id == "PL-26" for f in report.findings)


def test_pl20_warns_when_shortest_win_runs_past_the_ceiling():
    """8-11 short floors at 9 nodes, so the 2.5x advisory ceiling is 22."""
    report = validate_policy(_linear_scale_story(middles=21))
    findings = [f for f in report.warnings if f.rule_id == "PL-20"]
    assert len(findings) == 1
    assert "advisory ceiling" in findings[0].message


def test_pl20_ceiling_allows_a_path_exactly_at_the_limit():
    """A 22-node fastest finish sits on the ceiling and must not warn."""
    report = validate_policy(_linear_scale_story(middles=20))
    assert not any(f.rule_id == "PL-20" for f in report.warnings)


def test_pl20_ceiling_is_advisory_not_blocking():
    """Overrunning the arc ceiling warns; only the floor blocks."""
    report = validate_policy(_linear_scale_story(middles=21))
    assert not any(f.rule_id == "PL-20" for f in report.errors)


# ---------------------------------------------------------------------------
# PL-26 regression: PL-20 and PL-26 must not share a tie-break (PR #635)
#
# ``_check_min_to_complete`` used to hand a lexically tie-broken single result
# to both PL-20 (which reads only path length, safe under any tie-break) and
# PL-26 (which reads decision count along the path, NOT safe: equally short
# paths can carry different decision counts). The shared tie-break was BFS
# discovery order, i.e. node-id alphabetical order, so renaming the two
# equally fast routes flipped PL-26's verdict with zero structural change.
# The fix adds ``_decision_node_ids`` (one shared definition of "a decision")
# and ``_fewest_decision_shortest_path`` (an O(V+E) DP that picks, among
# equally short paths, the one with the fewest decisions, i.e. the worst
# density case, deliberately rather than by node-id order).
# ---------------------------------------------------------------------------


def _tiebreak_story(
    *, corridor: str, branchy: str, age_band: AgeBand = AgeBand.BAND_8_11
) -> Storybook:
    """Two equally-short (7-node) routes from a fork to the same win.

    ``corridor`` and ``branchy`` are id prefixes for the two routes: the
    corridor route is a straight walk to the SUCCESS ending; the branchy
    route is the same length but carries one extra decision partway along
    (an escape to a SETBACK ending). Swapping which prefix sorts first (so a
    node-id alphabetical tie-break would land on a different route) must not
    change which route the search reports on, since only decision count
    should drive the PL-26 verdict.

    Args:
        corridor: Id prefix for the decision-free route.
        branchy: Id prefix for the route carrying an extra decision.

    Returns:
        The assembled Storybook.
    """
    body = _fill(100)
    nodes: list[Node] = [
        Node(id="p0", body=body, choices=[Choice(id="c0", label="on", target="D")]),
        Node(
            id="D",
            body=body,
            choices=[
                Choice(id="cA", label="a", target=f"{corridor}1"),
                Choice(id="cB", label="b", target=f"{branchy}1"),
            ],
        ),
    ]
    for i in (1, 2, 3, 4):
        target = f"{corridor}{i + 1}" if i < 4 else "n_win"
        nodes.append(
            Node(
                id=f"{corridor}{i}",
                body=body,
                choices=[Choice(id=f"c{corridor}{i}", label="on", target=target)],
            )
        )
    for i in (1, 2, 4):
        target = f"{branchy}{i + 1}" if i < 4 else "n_win"
        nodes.append(
            Node(
                id=f"{branchy}{i}",
                body=body,
                choices=[Choice(id=f"c{branchy}{i}", label="on", target=target)],
            )
        )
    nodes.append(
        Node(
            id=f"{branchy}3",
            body=body,
            choices=[
                Choice(id=f"c{branchy}3x", label="on", target=f"{branchy}4"),
                Choice(id=f"c{branchy}3y", label="aside", target="n_alt"),
            ],
        )
    )
    nodes += [
        Node(
            id="n_win",
            body=body,
            is_ending=True,
            ending=Ending(
                id="e_win",
                valence=Valence.POSITIVE,
                kind=EndingKind.SUCCESS,
                title="Win",
            ),
        ),
        Node(
            id="n_alt",
            body=body,
            is_ending=True,
            ending=Ending(
                id="e_alt",
                valence=Valence.NEGATIVE,
                kind=EndingKind.SETBACK,
                title="Alt",
            ),
        ),
    ]
    return Storybook(
        id="s_tie",
        version=1,
        title="T",
        start_node="p0",
        nodes=nodes,
        metadata=StoryMetadata(
            age_band=age_band,
            reading_level=ReadingLevel(target=2.0),
            tier=1,
            estimated_minutes=5,
            ending_count=2,
            topology=Topology.BRANCH_AND_BOTTLENECK,
            length=Length.SHORT,
            narrative_style=NarrativeStyle.PROSE,
        ),
    )


def test_pl26_verdict_is_invariant_to_node_id_alphabetical_order():
    """Renaming the two equally-fast routes must not change PL-26's verdict.

    Before the fix, whichever route's ids sorted first was fed to PL-26
    unconditionally: the corridor route (1 decision over 7 nodes, density
    7.0, over the 6.0 prose ceiling) warned when it sorted first, but the
    exact same story stayed SILENT when the branchy route (2 decisions,
    density 3.5, under the ceiling) sorted first instead. Removing either
    assertion below would let that asymmetry (a real defect, not merely two
    runs disagreeing) back in.
    """
    corridor_first = validate_policy(_tiebreak_story(corridor="aa", branchy="zz"))
    branchy_first = validate_policy(_tiebreak_story(corridor="zz", branchy="aa"))
    density_a = [f for f in corridor_first.warnings if f.rule_id == "PL-26"]
    density_b = [f for f in branchy_first.warnings if f.rule_id == "PL-26"]
    assert len(density_a) == 1
    assert len(density_b) == 1
    assert "7.0" in density_a[0].message
    assert density_a[0].message == density_b[0].message


def test_pl26_reports_the_worst_equally_fast_walk_not_its_average():
    """PL-26 must report the fewest-decision (highest-density) equal walk.

    Two 7-node routes reach the win: one with one decision (density 7.0) and
    one with two (density 3.5). ``branchy`` sorts first here, so a naive
    alphabetical tie-break would have picked the *denser-in-decisions* route
    and reported 3.5 (silent, under the 8-11 ceiling of 6.0); an averaging
    implementation would report 5.25. Only 7.0, the deliberate worst case, is
    correct.
    """
    report = validate_policy(_tiebreak_story(corridor="zz", branchy="aa"))
    findings = [f for f in report.warnings if f.rule_id == "PL-26"]
    assert len(findings) == 1
    assert "7.0" in findings[0].message
    assert "3.5" not in findings[0].message
    assert "5.2" not in findings[0].message  # would-be average of 7.0 and 3.5


def _length_priority_story() -> Storybook:
    """A story where the shortest path carries MORE decisions than a longer one.

    The 5-node route (through decision node ``d1``) reaches the win fastest but
    carries 2 decisions (``n0`` and ``d1``); a 7-node alternate route reaches a
    different SUCCESS ending with only 1 decision (``n0``). If the fewest-
    decision search were not first constrained to minimum-length paths, it
    could wrongly prefer the longer, decision-sparser route and report a
    shortest length of 7 instead of the true 5.
    """
    body = _fill(100)
    nodes = [
        Node(
            id="n0",
            body=body,
            choices=[
                Choice(id="c_a", label="short", target="a1"),
                Choice(id="c_b", label="long", target="b1"),
            ],
        ),
        Node(id="a1", body=body, choices=[Choice(id="ca1", label="on", target="a2")]),
        Node(id="a2", body=body, choices=[Choice(id="ca2", label="on", target="d1")]),
        Node(
            id="d1",
            body=body,
            choices=[
                Choice(id="cd1w", label="win", target="a_win"),
                Choice(id="cd1x", label="aside", target="d1_alt"),
            ],
        ),
        Node(
            id="a_win",
            body=body,
            is_ending=True,
            ending=Ending(
                id="e_a", valence=Valence.POSITIVE, kind=EndingKind.SUCCESS, title="A"
            ),
        ),
        Node(
            id="d1_alt",
            body=body,
            is_ending=True,
            ending=Ending(
                id="e_alt",
                valence=Valence.NEGATIVE,
                kind=EndingKind.SETBACK,
                title="Alt",
            ),
        ),
    ]
    for i in range(1, 6):
        target = f"b{i + 1}" if i < 5 else "b_win"
        nodes.append(
            Node(
                id=f"b{i}",
                body=body,
                choices=[Choice(id=f"cb{i}", label="on", target=target)],
            )
        )
    nodes.append(
        Node(
            id="b_win",
            body=body,
            is_ending=True,
            ending=Ending(
                id="e_b", valence=Valence.POSITIVE, kind=EndingKind.SUCCESS, title="B"
            ),
        )
    )
    return Storybook(
        id="s",
        version=1,
        title="T",
        start_node="n0",
        nodes=nodes,
        metadata=StoryMetadata(
            age_band=AgeBand.BAND_3_5,
            reading_level=ReadingLevel(target=2.0),
            tier=1,
            estimated_minutes=5,
            ending_count=3,
            topology=Topology.BRANCH_AND_BOTTLENECK,
            length=Length.SHORT,
            narrative_style=NarrativeStyle.PROSE,
        ),
    )


def test_pl20_reads_the_true_shortest_length_not_the_fewest_decision_length():
    """PL-20 must not move when a longer, decision-sparser route exists.

    The true shortest satisfying completion is 5 nodes (below the 3-5 short
    prose floor of 6, so PL-20 must block). A DP that dropped the minimum-
    length constraint and globally minimized decisions would instead report
    the 7-node route (1 decision, 7 >= floor 6) and stay silent: this is
    exactly the future "optimization" bug the DP's docstring warns against.
    """
    report = validate_policy(_length_priority_story())
    findings = [f for f in report.errors if f.rule_id == "PL-20"]
    assert len(findings) == 1
    assert "shortest satisfying completion is 5 node(s)" in findings[0].message


def _diamond_chain_story(*, diamonds: int = 20) -> Storybook:
    """A chain of ``diamonds`` two-way diamonds, doubling the path count each.

    Each ``c{i}`` is a decision (2 choices) into ``u{i}``/``v{i}``, which both
    rejoin at ``c{i + 1}``, before a final win. With ``diamonds=20`` there are
    ``2**20`` (over a million) equally short satisfying paths from the start to
    the win, over ~60 total nodes: a path-enumerating search would need to walk
    all of them, but the layered DP this guards touches each node/edge once.

    Args:
        diamonds: Number of chained two-way diamonds.

    Returns:
        The assembled Storybook.
    """
    body = _fill(50)
    nodes: list[Node] = []
    for i in range(diamonds):
        nodes.append(
            Node(
                id=f"c{i}",
                body=body,
                choices=[
                    Choice(id=f"c{i}u", label="up", target=f"u{i}"),
                    Choice(id=f"c{i}v", label="down", target=f"v{i}"),
                ],
            )
        )
        nodes.append(
            Node(
                id=f"u{i}",
                body=body,
                choices=[Choice(id=f"u{i}c", label="on", target=f"c{i + 1}")],
            )
        )
        nodes.append(
            Node(
                id=f"v{i}",
                body=body,
                choices=[Choice(id=f"v{i}c", label="on", target=f"c{i + 1}")],
            )
        )
    nodes.append(
        Node(
            id=f"c{diamonds}",
            body=body,
            choices=[Choice(id="c_final", label="win", target="n_win")],
        )
    )
    nodes.append(
        Node(
            id="n_win",
            body=body,
            is_ending=True,
            ending=Ending(
                id="e_win",
                valence=Valence.POSITIVE,
                kind=EndingKind.SUCCESS,
                title="Win",
            ),
        )
    )
    return Storybook(
        id="s_diamond",
        version=1,
        title="T",
        start_node="c0",
        nodes=nodes,
        metadata=StoryMetadata(
            age_band=AgeBand.BAND_8_11,
            reading_level=ReadingLevel(target=2.0),
            tier=1,
            estimated_minutes=5,
            ending_count=1,
            topology=Topology.BRANCH_AND_BOTTLENECK,
            length=Length.SHORT,
            narrative_style=NarrativeStyle.PROSE,
        ),
    )


def test_pl26_density_scales_past_exponential_path_counts():
    """The fastest-finish search must stay O(V+E), not enumerate paths.

    20 chained diamonds carry 2**20 (over a million) equally short satisfying
    paths over ~60 nodes. A shortest-path-enumerating implementation would need
    to visit each one and would take far longer than this bound, or hang
    outright; the layered DP visits each node and edge once. Dropping either
    assertion would let a return to enumeration pass silently (slow but not
    "wrong") until it hangs on a real large skeleton.
    """
    story = _diamond_chain_story(diamonds=20)
    start = time.perf_counter()
    report = validate_policy(story)
    elapsed = time.perf_counter() - start
    assert report is not None
    assert elapsed < 5.0, "fastest-finish search must not enumerate exponential paths"


def test_decision_node_ids_and_density_handle_a_story_with_no_decisions():
    """Zero decision nodes must not divide by zero and must read as absence.

    ``_decision_node_ids`` returns an empty set for a purely linear story, and
    feeding that empty set through the search and the density check must not
    raise ZeroDivisionError; ``_check_decision_density``'s ``decisions == 0``
    guard is what stands between this and a crash.
    """
    story = _linear_scale_story(middles=3)
    assert _decision_node_ids(story) == set()
    graph = _build_graph(story)
    path = _fewest_decision_shortest_path(graph, story.start_node, {"n_end"}, set())
    assert path is not None
    assert path[-1] == "n_end"
    # A real run through the public gate must not raise, and must report the
    # explicit "no decision" case rather than silently computing 0/0.
    report = validate_policy(story)
    findings = [f for f in report.warnings if f.rule_id == "PL-26"]
    assert len(findings) == 1
    assert "no decision at all" in findings[0].message


def test_fewest_decision_shortest_path_returns_none_for_unreachable_targets():
    """An unreachable target set yields ``None``, not a ``min()`` on empty.

    If the DP's early return on an empty ``depths`` list were dropped, ``min()``
    over that empty sequence would raise ``ValueError`` instead of this clean
    ``None``.
    """
    graph: nx.DiGraph[str] = nx.DiGraph()
    graph.add_nodes_from(["a", "b", "isolated"])
    graph.add_edge("a", "b")
    result = _fewest_decision_shortest_path(graph, "a", {"isolated"}, set())
    assert result is None


def test_fewest_decision_shortest_path_returns_none_when_start_is_absent():
    """A ``start`` id absent from the graph is handled, not ``KeyError``'d.

    Guards the ``if start not in graph`` guard at the top of the function;
    removing it would make the BFS level-seeding loop over ``graph.successors``
    of a nonexistent node raise instead of returning ``None`` cleanly.
    """
    graph: nx.DiGraph[str] = nx.DiGraph()
    graph.add_node("only")
    result = _fewest_decision_shortest_path(graph, "missing", {"only"}, set())
    assert result is None


def test_fewest_decision_shortest_path_counts_a_decision_start_node():
    """The start node's own decision status must be seeded, not skipped.

    Both of the start node's choices land on the same win, so the fastest
    finish is forced through the start node alone. If ``fewest[start]`` were
    seeded at 0 instead of ``int(start in decisions)``, this story's only
    decision would be missed entirely, and PL-26 would wrongly report "no
    decision at all" instead of staying silent (density 2.0, under ceiling).
    """
    body = _fill(50)
    story = Storybook(
        id="s",
        version=1,
        title="T",
        start_node="n0",
        nodes=[
            Node(
                id="n0",
                body=body,
                choices=[
                    Choice(id="c1", label="a", target="n_end"),
                    Choice(id="c2", label="b", target="n_end"),
                ],
            ),
            Node(
                id="n_end",
                body=body,
                is_ending=True,
                ending=Ending(
                    id="e1",
                    valence=Valence.POSITIVE,
                    kind=EndingKind.SUCCESS,
                    title="W",
                ),
            ),
        ],
        metadata=StoryMetadata(
            age_band=AgeBand.BAND_3_5,
            reading_level=ReadingLevel(target=2.0),
            tier=1,
            estimated_minutes=5,
            ending_count=1,
            topology=Topology.GAUNTLET,
            length=Length.SHORT,
        ),
    )
    report = validate_policy(story)
    assert not any(f.rule_id == "PL-26" for f in report.findings)


def test_fewest_decision_shortest_path_includes_an_unavoidable_decision():
    """A mandatory decision on the sole route must be counted, not routed around.

    The only path from ``start`` to ``target`` passes through ``mid``, a
    decision node whose second choice is a dead end. "Fewest decisions" must
    not be read as license to avoid a decision that every shortest path is
    forced to carry.
    """
    graph: nx.DiGraph[str] = nx.DiGraph()
    graph.add_edge("start", "mid")
    graph.add_edge("mid", "target")
    graph.add_edge("mid", "dead_end")
    path = _fewest_decision_shortest_path(graph, "start", {"target"}, {"mid"})
    assert path == ["start", "mid", "target"]


# ---------------------------------------------------------------------------
# PL-26 brute-force cross-check: an exhaustive oracle beats any hand-built
# graph, and is the test that would catch a future refactor that breaks
# optimality without breaking any specific case above.
#
# The 9-node cap below is a property of the ORACLE (``nx.all_simple_paths``
# enumerates every simple path, which is exponential in graph size), not of
# ``_fewest_decision_shortest_path`` itself; the large-graph, linear-time case
# is covered from the other direction by
# ``test_pl26_density_scales_past_exponential_path_counts`` above, which the
# oracle could never check in reasonable time.
# ---------------------------------------------------------------------------


def _brute_force_best(
    graph: nx.DiGraph[str], start: str, targets: set[str], decisions: set[str]
) -> tuple[int, int] | None:
    """Exhaustively find ``(min_len, min_decisions_among_min_len)`` by walking
    every simple path from ``start`` to each target.

    Args:
        graph: The directed graph to search.
        start: The start node id.
        targets: Candidate destination node ids.
        decisions: Ids of the nodes that count as a decision.

    Returns:
        The ``(length, decision count)`` of the best path, or ``None`` when no
        target is reachable from ``start``.
    """
    best: tuple[int, int] | None = None
    for target in targets:
        if target not in graph:
            continue
        for candidate in nx.all_simple_paths(graph, start, target):
            key = (len(candidate), sum(1 for node in candidate if node in decisions))
            if best is None or key < best:
                best = key
    return best


def _cross_check(
    graph: nx.DiGraph[str], start: str, targets: set[str], decisions: set[str]
) -> str | None:
    """Return ``None`` when the DP agrees with the brute-force oracle.

    Checks all four properties an optimality bug could break independently: a
    real walk, correct endpoints, minimum length, and fewest decisions among
    the minimum-length paths.

    Args:
        graph: The directed graph to search.
        start: The start node id.
        targets: Candidate destination node ids.
        decisions: Ids of the nodes that count as a decision.

    Returns:
        ``None`` on agreement, or a failure message describing the mismatch.
    """
    best = _brute_force_best(graph, start, targets, decisions)
    got = _fewest_decision_shortest_path(graph, start, targets, decisions)
    if best is None:
        return None if got is None else f"unreachable but DP returned {got}"
    if got is None:
        return f"brute found {best} but DP returned None"
    if not all(graph.has_edge(got[i], got[i + 1]) for i in range(len(got) - 1)):
        return f"DP returned a non-walk: {got}"
    if got[0] != start or got[-1] not in targets:
        return f"DP endpoints wrong: {got}"
    got_key = (len(got), sum(1 for node in got if node in decisions))
    if got_key != best:
        return f"brute {best} vs DP {got_key} path={got}"
    return None


def test_fewest_decision_shortest_path_matches_brute_force_oracle():
    """The DP must match exhaustive enumeration on every randomized small graph.

    Generates 500 random directed graphs (3-9 nodes, ~28% edge density,
    random target and decision sets) from a fixed seed, deterministic across
    runs and independent of ``PYTHONHASHSEED``, and asserts the DP agrees with
    ``_brute_force_best`` on all four properties every time. A hand-built graph
    can only prove the DP right on the cases someone thought to write; this
    proves it on hundreds it did not, which is what would catch a refactor
    that breaks optimality without failing any single named case above.
    """
    rng = random.Random(20260806)
    mismatches: list[str] = []
    for _ in range(500):
        node_count = rng.randint(3, 9)
        ids = [f"n{i}" for i in range(node_count)]
        graph: nx.DiGraph[str] = nx.DiGraph()
        graph.add_nodes_from(ids)
        for i in range(node_count):
            for j in range(node_count):
                if i != j and rng.random() < 0.28:
                    graph.add_edge(ids[i], ids[j])
        start = ids[0]
        targets = set(rng.sample(ids, k=rng.randint(1, node_count)))
        decisions = set(rng.sample(ids, k=rng.randint(0, node_count)))
        failure = _cross_check(graph, start, targets, decisions)
        if failure is not None:
            mismatches.append(failure)
    assert not mismatches, (
        f"{len(mismatches)} DP/brute-force mismatch(es): {mismatches[:5]}"
    )


def test_pl24_gamebook_floor_scales_with_ending_count() -> None:
    """The floor is max(3, ceil(5% of endings)), ruled 2026-08-09 (R1).

    A 100-ending gamebook cannot clear the floor with 4 wins (floor 5); with
    5 wins it is silent. The pre-ruling absolute floor of 3 let a 200-ending
    book pass with the same 2-3 wins that satisfy a 30-ending one.
    """
    kinds: list[tuple[EndingKind, Valence]] = [
        (EndingKind.DEATH, Valence.NEGATIVE)
    ] * 96
    kinds += [(EndingKind.SUCCESS, Valence.POSITIVE)] * 4
    report = validate_policy(_mix_story(kinds=kinds, style=NarrativeStyle.GAMEBOOK))
    winnable = [f for f in report.findings if "positive-valence ending(s)" in f.message]
    assert len(winnable) == 1, "4 wins in 100 endings is below the scaled floor of 5"
    assert "below the gamebook floor of 5" in winnable[0].message

    kinds = [(EndingKind.DEATH, Valence.NEGATIVE)] * 95
    kinds += [(EndingKind.SUCCESS, Valence.POSITIVE)] * 5
    report = validate_policy(_mix_story(kinds=kinds, style=NarrativeStyle.GAMEBOOK))
    assert not [f for f in report.findings if "positive-valence ending(s)" in f.message]


def test_pl24_gamebook_floor_rounds_up_not_down() -> None:
    """The 5% floor uses ``math.ceil``, not truncation or nearest-rounding.

    At total=61, 5% is 3.05: ``ceil`` yields a floor of 4 while ``int`` and
    ``round`` both yield 3. Combined with the ``max(3, ...)`` absolute floor,
    3 wins in 61 endings only trips the warning under ``ceil``; a truncating
    or nearest-rounding implementation would consider 3 wins sufficient and
    stay silent.
    """
    kinds: list[tuple[EndingKind, Valence]] = [
        (EndingKind.DEATH, Valence.NEGATIVE)
    ] * 58
    kinds += [(EndingKind.SUCCESS, Valence.POSITIVE)] * 3
    report = validate_policy(_mix_story(kinds=kinds, style=NarrativeStyle.GAMEBOOK))
    winnable = [f for f in report.findings if "positive-valence ending(s)" in f.message]
    assert len(winnable) == 1, (
        "3 wins in 61 endings is below the ceil-scaled floor of 4"
    )
    assert "below the gamebook floor of 4" in winnable[0].message


@pytest.mark.unit
def test_pl29_rejects_a_topology_the_band_forbids() -> None:
    """A well-formed shape can still be wrong for its band (ADR-011 s7).

    `branch_and_bottleneck` first becomes legal at 8-11. Three skeletons
    drafted 2026-08-16 declared it at 3-5 and 5-8, cleared
    `check_skeleton --strict`, and were caught only by the offline mutation
    core, which is far too late and does not run on the authoring path.
    """
    story = _two_ending_story("5-8", Topology.BRANCH_AND_BOTTLENECK)

    report = validate_policy(story)

    assert any(
        f.rule_id == "PL-29" and f.severity is Severity.ERROR for f in report.findings
    )


@pytest.mark.unit
def test_pl29_allows_a_topology_the_band_permits() -> None:
    """The rule must key off the band row alone, not reject broadly."""
    story = _two_ending_story("5-8", Topology.TIME_CAVE)

    assert not any(f.rule_id == "PL-29" for f in validate_policy(story).findings)


@pytest.mark.unit
def test_pl29_accepts_every_committed_skeleton() -> None:
    """The rule blocks nothing that already exists.

    Measured before shipping it: all 61 committed skeletons satisfy their
    band's row, so this is a guard against new drafts rather than a
    retroactive judgement on the catalog. If this fails, either a skeleton
    landed that should not have or the row itself moved.
    """
    import json
    from pathlib import Path

    from cyo_adventure.validator.topology import BAND_TOPOLOGIES

    # Anchored to this file, not to the cwd: `Path("skeletons")` resolved to
    # nothing whenever pytest ran from anywhere but the repo root, and a glob
    # that matches nothing makes this a silently vacuous pass rather than a
    # failure (`AL-439`).
    skeletons_dir = Path(__file__).resolve().parents[2] / "skeletons"

    offenders: list[str] = []
    paths = sorted(skeletons_dir.glob("*/*.json"))
    assert paths, f"no skeletons found under {skeletons_dir}; the glob is wrong"
    for path in paths:
        if path.name.endswith((".lineage.json", ".narrative.json", ".contract.json")):
            continue
        metadata = json.loads(path.read_text())["metadata"]
        allowed = BAND_TOPOLOGIES.get(metadata.get("age_band"))
        topology = metadata.get("topology")
        if allowed and topology not in {t.value for t in allowed}:
            offenders.append(f"{path}: {metadata.get('age_band')} declares {topology}")

    assert offenders == []


@pytest.mark.unit
def test_deprecation_does_not_change_the_node_budget() -> None:
    """Retirement and the MVP tier are different claims and must stay separate.

    `production_eligible=False` rebudgets a story against the band-independent
    MVP envelope, which is looser. Expressing retirement by flipping that flag
    would make a retired book EASIER to validate than a live one, so
    `deprecated` must not touch budgeting at all.
    """
    live = _two_ending_story("5-8", Topology.TIME_CAVE)
    retired = _two_ending_story("5-8", Topology.TIME_CAVE)
    retired.metadata.deprecated = True

    assert [f.rule_id for f in validate_policy(live).findings] == [
        f.rule_id for f in validate_policy(retired).findings
    ]
