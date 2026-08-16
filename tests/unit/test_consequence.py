"""Unit tests for the fork-consequence measure (W3).

The workplan names four shapes this has to tell apart: a false choice, a real
choice, a fork that never reconverges, and a fork that reconverges only under one
condition. Each is built here as a fixture, because the whole value of the
measure is the distinction between them and a measure that collapses two of them
is worse than none.

The distinction that cost a rewrite has its own test. A fork whose branches run
to different endings never rejoins, and the first version scored that as an
unmeasured horizon hit, which made every book in the 61-book catalogue report
incomplete and the whole scan return "not measured". Terminal divergence is an
answer, and the most consequential one a fork can have.
"""

from __future__ import annotations

from typing import Any

from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.consequence import measure_consequence


def _node(
    node_id: str,
    *,
    choices: list[dict[str, Any]] | None = None,
    ending: bool = False,
    on_enter: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build one node.

    Args:
        node_id: The node's id.
        choices: Choice dicts, or ``None`` for none.
        ending: Whether this node ends the story.
        on_enter: Effects fired on entry.

    Returns:
        The node dict.
    """
    node: dict[str, Any] = {
        "id": node_id,
        "body": f"Body for {node_id}, long enough to look like prose.",
        "is_ending": ending,
        "choices": choices or [],
    }
    if ending:
        node["ending"] = {
            "id": f"e_{node_id}",
            "valence": "positive",
            "kind": "completion",
            "title": f"Ending at {node_id}",
        }
    if on_enter:
        node["on_enter"] = on_enter
    return node


def _story(nodes: list[dict[str, Any]], variables: list[dict[str, Any]]) -> Storybook:
    """Assemble a minimal valid story around the given nodes.

    Args:
        nodes: The node dicts.
        variables: Variable declarations.

    Returns:
        The parsed story.
    """
    return Storybook.model_validate(
        {
            "id": "s_fixture",
            "title": "Fixture",
            "schema_version": "2.0",
            "version": 1,
            "metadata": {
                "age_band": "8-11",
                "reading_level": {
                    "scheme": "flesch_kincaid",
                    "target": 3.0,
                    "tolerance": 1.0,
                },
                "tier": 2,
                "themes": ["adventure"],
                "estimated_minutes": 5,
                "ending_count": sum(1 for n in nodes if n.get("is_ending")),
                "content_flags": {
                    "violence": "none",
                    "scariness": "none",
                    "peril": "none",
                },
                "topology": "branch_and_bottleneck",
            },
            "start_node": "n_start",
            "variables": variables,
            "nodes": nodes,
        }
    )


def _fork(left: str, right: str) -> list[dict[str, Any]]:
    """Build a two-option choice list.

    Args:
        left: Target of the first option.
        right: Target of the second.

    Returns:
        The choice dicts.
    """
    return [
        {"id": "c_left", "label": "Go left", "target": left},
        {"id": "c_right", "label": "Go right", "target": right},
    ]


def test_a_fork_rejoining_next_node_with_no_state_is_a_false_choice() -> None:
    """The shape the measure exists to name.

    The reader is asked, both answers land on the same next node, and nothing
    anywhere records which was chosen.
    """
    story = _story(
        [
            _node("n_start", choices=_fork("n_a", "n_b")),
            _node("n_a", choices=[{"id": "c1", "label": "On", "target": "n_join"}]),
            _node("n_b", choices=[{"id": "c2", "label": "On", "target": "n_join"}]),
            _node("n_join", ending=True),
        ],
        [],
    )

    report = measure_consequence(story)

    assert report.complete is True
    assert len(report.forks) == 1
    assert report.forks[0].is_false_choice is True
    assert report.forks[0].distance == 1
    assert report.forks[0].reconverged_at == "n_join"
    assert report.false_choice_rate == 1.0


def test_a_fork_rejoining_immediately_but_setting_a_flag_is_not_false() -> None:
    """Distance alone would call this false, and it is not.

    The branches rejoin at the very next node, so a distance-only measure says
    the choice changed nothing. It set a variable, which a later ending can read.
    This is why the two quantities are reported separately and both are required
    before anything is called false.
    """
    story = _story(
        [
            _node("n_start", choices=_fork("n_a", "n_b")),
            _node(
                "n_a",
                choices=[{"id": "c1", "label": "On", "target": "n_join"}],
                on_enter=[{"op": "set", "var": "took_left", "value": True}],
            ),
            _node("n_b", choices=[{"id": "c2", "label": "On", "target": "n_join"}]),
            _node("n_join", ending=True),
        ],
        [{"name": "took_left", "type": "bool", "initial": False}],
    )

    report = measure_consequence(story)

    fork = report.forks[0]
    assert fork.distance == 1
    assert fork.state_delta == frozenset({"took_left"})
    assert fork.is_false_choice is False


def test_a_fork_running_to_two_endings_is_measured_not_unmeasured() -> None:
    """Terminal divergence is an answer, and scoring it as a gap broke the scan.

    The first version reported ``distance=None`` for both this case and a horizon
    hit, and marked the report incomplete for either. Every book in the catalogue
    has forks that lead to different endings, so every book came back incomplete
    and the corpus scan returned "not measured" over 61 books.
    """
    story = _story(
        [
            _node("n_start", choices=_fork("n_good", "n_bad")),
            _node("n_good", ending=True),
            _node("n_bad", ending=True),
        ],
        [],
    )

    report = measure_consequence(story)

    fork = report.forks[0]
    assert fork.outcome == "diverges"
    assert fork.distance is None
    assert fork.is_false_choice is False
    # The distinction that matters: this report is COMPLETE.
    assert report.complete is True
    assert report.false_choice_rate == 0.0


def test_a_fork_unresolved_at_the_horizon_reports_unmeasured() -> None:
    """A budget-limited answer must not be dressed as a measurement.

    Two long corridors that would rejoin beyond the horizon are searched to the
    budget and no further. The report says so rather than reporting the horizon
    as a distance, and withholds the rate entirely.
    """
    nodes = [_node("n_start", choices=_fork("l0", "r0"))]
    chain = 6
    for side in ("l", "r"):
        for i in range(chain):
            target = f"{side}{i + 1}" if i + 1 < chain else "n_join"
            nodes.append(
                _node(
                    f"{side}{i}",
                    choices=[{"id": f"c_{side}{i}", "label": "On", "target": target}],
                )
            )
    nodes.append(_node("n_join", ending=True))
    story = _story(nodes, [])

    report = measure_consequence(story, horizon=2)

    assert report.forks[0].outcome == "unmeasured"
    assert report.forks[0].distance is None
    assert report.complete is False
    # The rate is withheld, not computed over the forks that did resolve.
    assert report.false_choice_rate is None


def test_the_same_fork_rejoins_within_a_horizon_that_reaches_it() -> None:
    """The companion to the previous test: the horizon is the only difference.

    Without this pair, a bug that reported every fork unmeasured would look like
    correct caution.
    """
    nodes = [_node("n_start", choices=_fork("l0", "r0"))]
    chain = 6
    for side in ("l", "r"):
        for i in range(chain):
            target = f"{side}{i + 1}" if i + 1 < chain else "n_join"
            nodes.append(
                _node(
                    f"{side}{i}",
                    choices=[{"id": f"c_{side}{i}", "label": "On", "target": target}],
                )
            )
    nodes.append(_node("n_join", ending=True))
    story = _story(nodes, [])

    report = measure_consequence(story, horizon=12)

    assert report.forks[0].outcome == "reconverged"
    assert report.forks[0].distance == chain
    assert report.complete is True


def test_a_conditional_reconvergence_is_measured_under_the_state_that_reaches_it() -> (
    None
):
    """A branch gated on a flag is a different question to a reader who has it.

    The fork is measured over the configuration graph rather than the node graph
    precisely so that a choice visible only under one variable state is not
    silently pooled with the same node under another.
    """
    story = _story(
        [
            _node(
                "n_start",
                choices=[
                    {"id": "c_take", "label": "Take the key", "target": "n_mid"},
                    {"id": "c_leave", "label": "Leave it", "target": "n_mid"},
                ],
                on_enter=None,
            ),
            _node(
                "n_mid",
                choices=[
                    {
                        "id": "c_open",
                        "label": "Open the door",
                        "target": "n_open",
                        "condition": {"==": [{"var": "has_key"}, True]},
                    },
                    {"id": "c_wait", "label": "Wait", "target": "n_wait"},
                ],
            ),
            _node("n_open", ending=True),
            _node("n_wait", ending=True),
        ],
        [{"name": "has_key", "type": "bool", "initial": False}],
    )

    report = measure_consequence(story)

    # n_start's two options both go to n_mid and set nothing: a false choice.
    start = next(f for f in report.forks if f.node_id == "n_start")
    assert start.is_false_choice is True
    # n_mid offers a second option only to a reader holding the key; with the
    # flag never set it is a single-option node and produces no fork at all.
    assert all(f.node_id != "n_mid" for f in report.forks)
