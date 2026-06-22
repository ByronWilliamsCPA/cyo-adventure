"""Layer-2 state-space validator (rules L2-9 through L2-12).

Layer 2 runs only on Tier-2 stories and operates over the full reachable
configuration space produced by :func:`~cyo_adventure.validator.walk.walk_configurations`.
Any Tier-1 story is returned immediately with an empty report.

Rule summary
------------
L2-12 (cap)
    The configuration walk exceeded the ceiling. Returned immediately; no
    further rules are checked.
L2-9 (stateful dead-end)
    A reachable, non-ending configuration has zero visible choices.
L2-10 (stateful termination / loop escape)
    A reachable configuration has no path to any ending config.
L2-11 (conditional usefulness / dead branch)
    A conditional choice is never visible in any reachable configuration.

All failure-message templates match the exact strings specified in
``docs/planning/validator-rules.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cyo_adventure.player.engine import StoryEngine
from cyo_adventure.validator.report import (
    Severity,
    ValidationFinding,
    ValidationReport,
)
from cyo_adventure.validator.walk import walk_configurations

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cyo_adventure.player.state import ReadingState
    from cyo_adventure.storybook.evaluator import VarValue
    from cyo_adventure.storybook.models import Node, Storybook
    from cyo_adventure.validator.walk import ConfigKey, WalkResult


# ---------------------------------------------------------------------------
# Internal data containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _WalkContext:
    """Bundles the walk result and engine for rule checks.

    Attributes:
        story_id: The story id, extracted once for message formatting.
        result: The complete configuration closure from the walk.
        engine: A StoryEngine instance for the story.
    """

    story_id: str
    result: WalkResult
    engine: StoryEngine


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def validate_layer2(story: Storybook, *, cap: int = 100_000) -> ValidationReport:
    """Run every Layer-2 rule over a Tier-2 story's reachable configuration space.

    Returns an empty report immediately for Tier-1 stories; Layer-2 rules are
    meaningless on variable-free graphs.

    Args:
        story: The parsed, schema-valid Storybook to validate.
        cap: Maximum number of distinct configurations the walk may enumerate
            before aborting. Defaults to 100 000. When the walk caps, exactly
            one L2-12 finding is returned and no other Layer-2 rules are run.

    Returns:
        ValidationReport: All findings from the Layer-2 rules. ``report.ok``
            is ``True`` when no error-severity finding was raised.
    """
    report = ValidationReport()

    # Tier gate: Layer 2 has no meaning for Tier-1 stories.
    if story.metadata.tier == 1:
        return report

    result = walk_configurations(story, cap=cap)

    # L2-12: configuration space too large. Return immediately -- partial results
    # are unreliable for the remaining rules.
    if result.capped:
        report.add(_l2_12_finding(story.id, cap))
        return report

    ctx = _WalkContext(
        story_id=story.id,
        result=result,
        engine=StoryEngine(story),
    )

    dead_end_keys = _check_dead_ends(ctx, report)
    _check_loop_escape(ctx, dead_end_keys, report)
    _check_dead_branches(ctx, story.nodes, report)

    return report


# ---------------------------------------------------------------------------
# Internal helpers: finding constructors
# ---------------------------------------------------------------------------


def _l2_12_finding(story_id: str, cap: int) -> ValidationFinding:
    """Build the L2-12 cap finding.

    Args:
        story_id: The story id.
        cap: The cap ceiling that was exceeded.

    Returns:
        ValidationFinding: The formatted L2-12 finding.
    """
    return ValidationFinding(
        rule_id="L2-12",
        severity=Severity.ERROR,
        story_id=story_id,
        message=(
            f"L2-12 cap: reachable configuration set exceeded the ceiling "
            f"of {cap} configurations in story '{story_id}' (state space "
            f"too large; reduce variable count or tighten bounds)"
        ),
    )


def _l2_9_finding(
    story_id: str, node_id: str, var_state: Mapping[str, VarValue]
) -> ValidationFinding:
    """Build an L2-9 stateful dead-end finding.

    Args:
        story_id: The story id.
        node_id: The dead-end node id.
        var_state: The deterministically sorted variable state.

    Returns:
        ValidationFinding: The formatted L2-9 finding.
    """
    return ValidationFinding(
        rule_id="L2-9",
        severity=Severity.ERROR,
        story_id=story_id,
        node_id=node_id,
        message=(
            f"L2-9 dead: node '{node_id}' with var_state {var_state} is a "
            f"stateful dead end (no visible choices, not an ending) in story "
            f"'{story_id}'"
        ),
    )


def _l2_10_finding(
    story_id: str, node_id: str, var_state: Mapping[str, VarValue]
) -> ValidationFinding:
    """Build an L2-10 loop-escape finding.

    Args:
        story_id: The story id.
        node_id: The config's current node id.
        var_state: The deterministically sorted variable state.

    Returns:
        ValidationFinding: The formatted L2-10 finding.
    """
    return ValidationFinding(
        rule_id="L2-10",
        severity=Severity.ERROR,
        story_id=story_id,
        node_id=node_id,
        message=(
            f"L2-10 escape: configuration ('{node_id}', {var_state}) has no "
            f"path to any ending in story '{story_id}' (cycle with no escape "
            f"/ dead configuration chain)"
        ),
    )


def _l2_11_finding(story_id: str, node_id: str, choice_id: str) -> ValidationFinding:
    """Build an L2-11 dead-branch finding.

    Args:
        story_id: The story id.
        node_id: The node that owns the dead choice.
        choice_id: The choice id that is never visible.

    Returns:
        ValidationFinding: The formatted L2-11 finding.
    """
    return ValidationFinding(
        rule_id="L2-11",
        severity=Severity.ERROR,
        story_id=story_id,
        node_id=node_id,
        choice_id=choice_id,
        message=(
            f"L2-11 dead-branch: choice '{choice_id}' on node '{node_id}' "
            f"is never visible in any reachable configuration in story "
            f"'{story_id}' (condition always false)"
        ),
    )


# ---------------------------------------------------------------------------
# Internal rule implementations
# ---------------------------------------------------------------------------


def _configs_as_reading_states(
    ctx: _WalkContext,
) -> list[tuple[ConfigKey, ReadingState]]:
    """Return the (key, ReadingState) pairs from the walk configs.

    The walk types ``configs`` as ``dict[ConfigKey, ReadingState]``, so every
    value is already a ``ReadingState``; this helper returns them as a plain
    list for iteration convenience.

    Args:
        ctx: The walk context.

    Returns:
        list[tuple[ConfigKey, ReadingState]]: All config key/state pairs.
    """
    return list(ctx.result.configs.items())


def _check_dead_ends(ctx: _WalkContext, report: ValidationReport) -> set[ConfigKey]:
    """L2-9: flag every reachable non-ending config with zero visible choices.

    Args:
        ctx: The walk context (story id, result, engine).
        report: The report to append findings to.

    Returns:
        set[ConfigKey]: The exact configuration keys that triggered an L2-9
            finding. L2-10 uses this to suppress duplicate reports for the
            same configuration (not the same node), so a non-dead-end config
            sharing a node id with a dead-end config is still checked.
    """
    dead_end_keys: set[ConfigKey] = set()
    for key, rs in _configs_as_reading_states(ctx):
        if ctx.engine.is_ending(rs):
            continue
        # #ASSUME: data integrity: edges[key] is an empty list (not absent) for
        # every recorded config, including dead-ends -- a KeyError here means
        # walk.py broke its invariant set(edges)==set(configs).
        # #VERIFY: walk.py WalkResult guarantees set(edges)==set(configs);
        # see walk_configurations invariant.
        if ctx.result.edges[key]:
            continue
        # Non-ending node with no successors: stateful dead end.
        node_id = rs.current_node
        var_state = dict(sorted(rs.var_state.items()))
        report.add(_l2_9_finding(ctx.story_id, node_id, var_state))
        dead_end_keys.add(key)
    return dead_end_keys


def _build_reverse_edges(ctx: _WalkContext) -> dict[ConfigKey, set[ConfigKey]]:
    """Build a reverse-edge index over the walk result.

    Args:
        ctx: The walk context.

    Returns:
        dict[ConfigKey, set[ConfigKey]]: Maps each config key to the set of
            predecessor config keys that have it as a successor.
    """
    reverse: dict[ConfigKey, set[ConfigKey]] = {k: set() for k in ctx.result.configs}
    for key, successors in ctx.result.edges.items():
        for succ in successors:
            if succ in reverse:
                reverse[succ].add(key)
    return reverse


def _ending_reachable_set(ctx: _WalkContext) -> set[ConfigKey]:
    """Return every config key from which some ending config is reachable.

    Uses backward BFS from ending configs over the reverse edge index.

    Args:
        ctx: The walk context.

    Returns:
        set[ConfigKey]: Keys that have a path (possibly empty) to an ending.
    """
    reverse = _build_reverse_edges(ctx)
    can_reach: set[ConfigKey] = set()
    queue: list[ConfigKey] = []

    for key, rs in _configs_as_reading_states(ctx):
        if ctx.engine.is_ending(rs):
            can_reach.add(key)
            queue.append(key)

    while queue:
        current = queue.pop()
        for pred in reverse.get(current, set()):
            if pred not in can_reach:
                can_reach.add(pred)
                queue.append(pred)

    return can_reach


def _check_loop_escape(
    ctx: _WalkContext,
    dead_end_keys: set[ConfigKey],
    report: ValidationReport,
) -> None:
    """L2-10: flag every reachable config from which no ending is reachable.

    Configs already flagged by L2-9 are skipped to avoid double-reporting.

    Args:
        ctx: The walk context (story id, result, engine).
        dead_end_keys: Set of configuration keys already attributed to an L2-9
            finding.
        report: The report to append findings to.
    """
    # #ASSUME: data integrity: suppression is per ConfigKey, not per node id; a
    # node may be reachable in both a dead-end config (L2-9) and a separate
    # trapped config (L2-10 must still fire for it), so only the exact dead-end
    # ConfigKey is skipped.
    # #VERIFY: the two-config-same-node scenario is exercised by the regression
    # test for a non-dead-end config that shares a node with a dead-end config.
    can_reach_ending = _ending_reachable_set(ctx)

    for key, rs in _configs_as_reading_states(ctx):
        if key in can_reach_ending:
            continue
        if key in dead_end_keys:
            continue  # already reported as L2-9
        node_id = rs.current_node
        var_state = dict(sorted(rs.var_state.items()))
        report.add(_l2_10_finding(ctx.story_id, node_id, var_state))


def _ever_visible_choice_ids(ctx: _WalkContext) -> set[str]:
    """Return the set of choice ids that are visible in at least one config.

    Args:
        ctx: The walk context.

    Returns:
        set[str]: Every choice id that engine.visible_choices returned for any
            reachable configuration.
    """
    ever_visible: set[str] = set()
    for _, rs in _configs_as_reading_states(ctx):
        for choice in ctx.engine.visible_choices(rs):
            ever_visible.add(choice.id)
    return ever_visible


def _reachable_node_ids(ctx: _WalkContext) -> set[str]:
    """Return the set of node ids that appear in at least one config.

    Args:
        ctx: The walk context.

    Returns:
        set[str]: Node ids present across all reachable configs.
    """
    return {rs.current_node for _, rs in _configs_as_reading_states(ctx)}


def _check_dead_branches(
    ctx: _WalkContext,
    nodes: list[Node],
    report: ValidationReport,
) -> None:
    """L2-11: flag conditional choices that are never visible in any reachable config.

    A conditional choice on a reachable node that is invisible in every
    reachable configuration of that node is a dead branch.

    Args:
        ctx: The walk context (story id, result, engine).
        nodes: The full node list from the story.
        report: The report to append findings to.
    """
    reachable = _reachable_node_ids(ctx)
    ever_visible = _ever_visible_choice_ids(ctx)
    node_map = {node.id: node for node in nodes}

    for node_id in reachable:
        node = node_map.get(node_id)
        if node is None:
            continue
        for choice in node.choices:
            if choice.condition is None:
                continue  # unconditional choices are never dead branches
            if choice.id not in ever_visible:
                report.add(_l2_11_finding(ctx.story_id, node_id, choice.id))
