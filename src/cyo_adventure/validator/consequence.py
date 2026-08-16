"""Measure how much a fork actually changes, in nodes and in state (W3).

A choice a reader makes is only a choice if something differs afterwards. Two
branches that rejoin at the next node carrying identical variable state are a
false choice: the reader was asked, the answer was recorded nowhere, and the
next sentence is the same either way. This module measures that, per fork, over
the configuration graph the validator already builds.

**Two quantities, both reported, neither pooled.** *Distance* is how many nodes
a reader travels on the longer branch before the two rejoin. *State delta* is the
set of variable names whose values differ on arrival. They fail independently: a
fork can rejoin immediately while setting a flag that pays off in a later ending
(short distance, real consequence), and a fork can run eight nodes down two
cosmetic corridors and arrive identical (long distance, no consequence). Reading
either alone would call one of those a false choice.

**Why the configuration graph rather than the node graph.** A fork's branches can
be the same nodes under different variable state, and on the node graph those are
one path. `walk_configurations` already distinguishes them, already handles
once-effects soundly, and already reports when it was capped. Re-implementing
reachability here would mean re-deriving all three.

**This is a reported statistic, not a gate.** `BandProfile.reconvergence_ceiling`
exists and is unenforced, and it stays that way: promoting a measure to a rule
that blocks a book requires evidence that a reader is affected, which is W12's
job. `AL-337` is the record of what happens when a number becomes a gate on the
strength of being computable.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from cyo_adventure.validator.walk import walk_configurations

if TYPE_CHECKING:
    from cyo_adventure.player.state import VarState
    from cyo_adventure.storybook.models import Storybook
    from cyo_adventure.validator.walk import ConfigKey

# How far to search for a reconvergence before giving up. Twelve nodes is well
# past the point where two branches are still "the same scene": the catalogue's
# band profiles cap a whole reading in the tens of nodes, so a fork that has not
# rejoined by twelve has diverged for the rest of the book in every practical
# sense.
#
# #CRITICAL: data integrity: a horizon is a budget, and a number computed under
# a budget is a statement about the budget until proven otherwise (AL-338). A
# fork that does not rejoin within it reports `distance=None`, never the horizon
# itself, and any report containing one is `complete=False`.
# #VERIFY: test_consequence.py asserts a never-reconverging fork reports None
# and drives the horizon with a chain longer than it.
_DEFAULT_HORIZON: Final[int] = 12

# Reconvergence distance at or below which a fork showed the reader nothing
# distinct. See ForkConsequence.is_false_choice for why this is not `== 1`.
_FALSE_CHOICE_DISTANCE: Final[int] = 1

__all__ = [
    "ConsequenceReport",
    "ForkConsequence",
    "measure_consequence",
]


@dataclass(frozen=True, slots=True)
class ForkConsequence:
    """What one pair of branches out of one fork actually changes.

    Attributes:
        node_id: The node the reader is standing on when asked.
        choices: The two choice ids compared, in the order the node lists them.
        outcome: What happened to the two branches. ``"reconverged"`` means they
            rejoined and ``distance`` is a measurement. ``"diverges"`` means both
            branches ran to their endings without ever rejoining, which is a
            **measured** result and the most consequential a fork can have.
            ``"unmeasured"`` means the search hit its horizon with the question
            still open, which is the only one that makes a report incomplete.
            Collapsing the last two was the first version's error: it scored
            every book in the catalogue incomplete and reported nothing, because
            a fork leading to two different endings correctly never rejoins.
        distance: Nodes travelled on the longer branch before the two rejoin, or
            ``None`` for any outcome other than ``"reconverged"``.
        reconverged_at: The node the branches rejoined on, or ``None``.
        state_delta: Variable names whose values differ on arrival at the
            reconvergence point. Empty means the two readers are, from the
            engine's point of view, in the same story.
    """

    node_id: str
    choices: tuple[str, str]
    outcome: Literal["reconverged", "diverges", "unmeasured"]
    distance: int | None
    reconverged_at: str | None
    state_delta: frozenset[str]

    @property
    def is_false_choice(self) -> bool:
        """Whether this fork asked a question that changed nothing.

        Returns:
            ``True`` when the branches rejoin within one node carrying identical
            variable state. Both conditions are required: an immediate rejoin
            that sets a flag is a real choice whose payoff is deferred, and a
            long detour arriving identical is a real one only in the sense that
            the reader spent time on it.

        Note:
            Distance is measured in hops **after** the choice is taken, so ``0``
            means both options target the same node and the reader saw no
            distinct content at all, and ``1`` means one distinct node each. The
            workplan's phrase is "reconverging in one node", which covers both;
            reading the threshold as ``== 1`` silently exempts the purest case,
            which is what a fixture whose two options share a target caught.
        """
        return (
            self.outcome == "reconverged"
            and self.distance is not None
            and self.distance <= _FALSE_CHOICE_DISTANCE
            and not self.state_delta
        )


@dataclass(frozen=True, slots=True)
class ConsequenceReport:
    """Every fork in one story, measured.

    Attributes:
        forks: One entry per compared branch pair.
        complete: ``False`` when the configuration walk was capped or any fork
            ended ``"unmeasured"``. A fork that diverges to different endings does
            NOT make a report incomplete: that is an answer, not a gap.
        horizon: The search horizon this report was computed under, recorded
            because it is a condition of the measurement.
    """

    forks: tuple[ForkConsequence, ...]
    complete: bool
    horizon: int

    @property
    def false_choice_rate(self) -> float | None:
        """Share of measured forks that changed nothing.

        Returns:
            The rate, or ``None`` when the report is incomplete or holds no
            fork. ``None`` rather than ``0.0``: a story with no forks has no
            false choices and also no evidence, and the two must not average
            together across a catalogue.
        """
        if not self.complete or not self.forks:
            return None
        return sum(1 for f in self.forks if f.is_false_choice) / len(self.forks)


def _state_of(key: ConfigKey) -> dict[str, bool | int | str]:
    """Return the variable state a configuration key encodes.

    Args:
        key: The configuration key.

    Returns:
        The variable state as a plain mapping.
    """
    return dict(key[1])


def _reachable(
    start: ConfigKey,
    edges: dict[ConfigKey, list[ConfigKey]],
    horizon: int,
) -> tuple[dict[str, tuple[int, VarState]], bool]:
    """Map each node reachable from *start* to its shortest distance and state.

    Args:
        start: The configuration to search from.
        edges: The configuration graph.
        horizon: Maximum distance to search.

    Returns:
        Node id to ``(distance, variable state on first arrival)``, and whether
        the search was cut off by the horizon. First arrival is used
        deliberately: the reconvergence a reader experiences is the earliest one,
        not the one that happens to carry the most state.

        The truncation flag is what separates "these branches never rejoin" from
        "we stopped looking". A branch that ran out of successors inside the
        horizon has been searched exhaustively, and its non-reconvergence is a
        fact about the story rather than about the budget.
    """
    seen: dict[str, tuple[int, VarState]] = {}
    visited: set[ConfigKey] = {start}
    queue: deque[tuple[ConfigKey, int]] = deque([(start, 0)])
    truncated = False
    while queue:
        key, depth = queue.popleft()
        node_id = key[0]
        if node_id not in seen:
            seen[node_id] = (depth, _state_of(key))
        if depth >= horizon:
            # Only a node with somewhere left to go counts as truncation. A
            # configuration sitting at the horizon with no successors is an
            # ending, and the search finished there of its own accord.
            if edges.get(key):
                truncated = True
            continue
        for nxt in edges.get(key, []):
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, depth + 1))
    return seen, truncated


def _compare(
    node_id: str,
    choices: tuple[str, str],
    left: tuple[dict[str, tuple[int, VarState]], bool],
    right: tuple[dict[str, tuple[int, VarState]], bool],
) -> ForkConsequence:
    """Find where two branches rejoin, and what differs when they do.

    Args:
        node_id: The forking node.
        choices: The two choice ids.
        left: Reachability from the first branch, with its truncation flag.
        right: Reachability from the second, with its truncation flag.

    Returns:
        The measured consequence for this pair.
    """
    left_reach, left_cut = left
    right_reach, right_cut = right
    shared = set(left_reach) & set(right_reach)
    if not shared:
        return ForkConsequence(
            node_id=node_id,
            choices=choices,
            # Both branches searched to exhaustion and shared nothing: they run
            # to different endings and the reader's choice decided the book.
            outcome="unmeasured" if (left_cut or right_cut) else "diverges",
            distance=None,
            reconverged_at=None,
            state_delta=frozenset(),
        )
    # The reconvergence a reader meets is the earliest one, measured on the
    # branch that takes longer to get there: that is how many nodes the story
    # actually stayed different for.
    target = min(shared, key=lambda n: max(left_reach[n][0], right_reach[n][0]))
    left_distance, left_state = left_reach[target]
    right_distance, right_state = right_reach[target]
    names = set(left_state) | set(right_state)
    delta = frozenset(
        name for name in names if left_state.get(name) != right_state.get(name)
    )
    return ForkConsequence(
        node_id=node_id,
        choices=choices,
        outcome="reconverged",
        distance=max(left_distance, right_distance),
        reconverged_at=target,
        state_delta=delta,
    )


def measure_consequence(
    story: Storybook,
    *,
    horizon: int = _DEFAULT_HORIZON,
    walk_cap: int = 100_000,
) -> ConsequenceReport:
    """Measure every fork in *story* for distance and state consequence.

    Args:
        story: The parsed story.
        horizon: How far to search for a reconvergence.
        walk_cap: Configuration cap forwarded to the walk.

    Returns:
        The report. ``complete`` is ``False`` when the walk was capped or any
        fork failed to rejoin inside the horizon, in which case
        :attr:`ConsequenceReport.false_choice_rate` withholds a number.

    Note:
        A configuration is a fork when it offers more than one visible choice.
        The same node can therefore be a fork under one variable state and not
        under another, and each is measured; a story that gates a choice behind
        a flag genuinely offers different questions to different readers.
    """
    walk = walk_configurations(story, cap=walk_cap)
    choices_by_node = {
        node.id: [choice.id for choice in node.choices] for node in story.nodes
    }
    forks: list[ForkConsequence] = []
    seen_pairs: set[tuple[str, str, str]] = set()

    for key, successors in walk.edges.items():
        if len(successors) < 2:
            continue
        node_id = key[0]
        labels = choices_by_node.get(node_id, [])
        reach = [_reachable(s, walk.edges, horizon) for s in successors]
        for i in range(len(successors)):
            for j in range(i + 1, len(successors)):
                left_id = labels[i] if i < len(labels) else f"#{i}"
                right_id = labels[j] if j < len(labels) else f"#{j}"
                # One node can fork under several variable states. The reader
                # meets one question per (node, choice pair), so dedupe on that
                # rather than counting the same question once per configuration.
                signature = (node_id, left_id, right_id)
                if signature in seen_pairs:
                    continue
                seen_pairs.add(signature)
                forks.append(_compare(node_id, (left_id, right_id), reach[i], reach[j]))

    horizon_hit = any(f.outcome == "unmeasured" for f in forks)
    return ConsequenceReport(
        forks=tuple(forks),
        complete=not walk.capped and not horizon_hit,
        horizon=horizon,
    )
