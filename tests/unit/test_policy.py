"""Unit tests for the age-policy gate layer (PL-15..PL-18)."""

from cyo_adventure.storybook.models import (
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


def test_pl16_blocks_content_over_band_ceiling():
    # 3-5 scariness ceiling is "mild"; "intense" exceeds it.
    report = validate_policy(
        _story(age_band="3-5", kind=EndingKind.SUCCESS, scariness="intense")
    )
    assert any(f.rule_id == "PL-16" for f in report.errors)
