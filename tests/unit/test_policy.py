"""Unit tests for the age-policy gate layer (PL-15..PL-18)."""

from cyo_adventure.storybook.models import (
    Choice,
    ContentFlags,
    Ending,
    EndingKind,
    Node,
    ReadingLevel,
    Storybook,
    StoryMetadata,
    Topology,
    Valence,
)
from cyo_adventure.validator.policy import validate_policy


def _story(*, age_band: str, kind: EndingKind, scariness: str = "none") -> Storybook:
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
            content_flags=ContentFlags(scariness=scariness),
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
