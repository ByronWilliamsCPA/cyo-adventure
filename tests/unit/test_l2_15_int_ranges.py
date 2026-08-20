"""L2-15: a declared integer range far wider than the story's conditions test.

The rule exists because the first story-first gamebook declared two counters as
`0..99` when no condition in it compares either above 3. That is a 625x
inflation of the reachable configuration space across the two, and it surfaced
only as an L2-12 ceiling breach 16,000 words later. `AL-008` recorded the same
lesson on 2026-07-25 against the same cap and proposed a prose rule; no check was
built, so it was re-learned 24 days on (`UW-C294`).
"""

from __future__ import annotations

from typing import Any

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
    Variable,
    VariableType,
)
from cyo_adventure.validator.layer2 import validate_layer2


def _story_with(*, declared_max: int, thresholds: list[int]) -> Storybook:
    """A two-node story testing `wounds` against each threshold in turn."""
    choices: list[dict[str, Any]] = [
        {
            "id": f"c{index}",
            "label": f"Press on, hurt {threshold}",
            "target": "n_end",
            "condition": {"<": [{"var": "wounds"}, threshold]},
        }
        for index, threshold in enumerate(thresholds)
    ]
    if not choices:
        choices = [{"id": "c0", "label": "Press on", "target": "n_end"}]
    return Storybook(
        id="s_wounds",
        version=1,
        title="Wounds",
        start_node="n0",
        nodes=[
            Node(id="n0", body="A hard road.", choices=choices),
            Node(
                id="n_end",
                body="Through.",
                is_ending=True,
                ending=Ending(
                    id="e1",
                    valence=Valence.POSITIVE,
                    kind=EndingKind.SUCCESS,
                    title="Through",
                ),
            ),
        ],
        variables=[
            Variable(
                name="wounds",
                type=VariableType.INT,
                initial=0,
                min=0,
                max=declared_max,
            )
        ],
        metadata=StoryMetadata(
            age_band="13-16",
            reading_level=ReadingLevel(target=7.0),
            tier=2,
            estimated_minutes=5,
            ending_count=1,
            content_flags=ContentFlags(),
            topology=Topology.GAUNTLET,
        ),
    )


def _l2_15(story: Storybook) -> list[str]:
    report = validate_layer2(story)
    return [f.message for f in report.warnings if f.rule_id == "L2-15"]


def test_a_range_far_wider_than_the_conditions_test_warns() -> None:
    """The case the rule was built for: 0..99 tested at 1, 2, 3."""
    findings = _l2_15(_story_with(declared_max=99, thresholds=[1, 2, 3]))
    assert len(findings) == 1
    message = findings[0]
    assert "'wounds'" in message
    assert "0..99" in message
    # The multiplier is against the distinguishable span (0 through 3), not
    # against the literal spread, so it must read 25x rather than 33x.
    assert "25x" in message


def test_a_threshold_counter_with_ordinary_headroom_stays_silent() -> None:
    """Declaring 0..6 and testing at 3 is correct authoring, not a defect.

    A counter climbs to its threshold, so every value below the threshold is a
    distinct step toward it. An earlier draft of this rule measured the spread
    between tested literals instead, read this as a single exercised value, and
    fired on two correctly authored committed skeletons.
    """
    assert _l2_15(_story_with(declared_max=6, thresholds=[3])) == []


def test_it_never_blocks() -> None:
    """A wide range is a cost the author may knowingly accept, not a defect."""
    story = _story_with(declared_max=99, thresholds=[1, 2, 3])
    report = validate_layer2(story)
    assert [f.rule_id for f in report.errors if f.rule_id == "L2-15"] == []
    assert any(f.rule_id == "L2-15" for f in report.warnings)


def test_a_variable_no_condition_compares_is_not_reported() -> None:
    """Silence, not a zero-span finding.

    Such a variable may exist only for its effects, or be carried for a series
    continuation, and reporting every one of them would make the rule noise.
    """
    assert _l2_15(_story_with(declared_max=99, thresholds=[])) == []


def test_it_fires_even_when_the_walk_caps() -> None:
    """The early warning must survive the failure it warns about.

    L2-12 returns immediately on a capped walk and skips the remaining Layer-2
    rules. L2-15 is the early warning for the commonest cause of that cap, so it
    runs before the walk; emitting it only on a completed walk would silence it
    in exactly the case it exists for.
    """
    story = _story_with(declared_max=99, thresholds=[1, 2, 3])
    report = validate_layer2(story, cap=1)
    assert any(f.rule_id == "L2-12" for f in report.errors)
    assert any(f.rule_id == "L2-15" for f in report.warnings)
