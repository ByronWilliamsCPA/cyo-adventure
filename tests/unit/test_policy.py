"""Unit tests for the age-policy gate layer (PL-15..PL-18)."""

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
from cyo_adventure.validator.policy import node_word_count, validate_policy


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
