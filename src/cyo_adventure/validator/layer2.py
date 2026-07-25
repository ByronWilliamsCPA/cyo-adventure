"""Layer-2 state-space validator (rules L2-9 through L2-13).

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
L2-13 (scale advisory)
    A completed-walk Tier-2 story exceeds the ADR-011 hand-authoring node
    ceiling, so the configuration walk is its sole correctness guarantee
    (hand-review is no longer sufficient at this scale). WARNING only; never
    blocks. Operationalises the dagger-cell finding (a large stateful story's
    state-gated defects are caught only by the walk, not by inspection).

All failure-message templates match the exact strings specified in
``docs/planning/validator-rules.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import networkx as nx

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
    from cyo_adventure.storybook.models import Storybook
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

# ADR-011 hand-authoring node ceiling. Past this size a stateful story can no
# longer be reasoned correct by hand (the dagger-cell experiment: a best-win
# outcome gated on an unreachable state was invisible to inspection and caught
# only by walking every configuration), so the completed Layer-2 walk is the
# sole correctness guarantee. L2-13 flags this as an advisory, never a block.
HAND_AUTHORING_NODE_CEILING = 460


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

    # L2-13: scale advisory (WARNING). The walk completed, and this Tier-2 story
    # is past the hand-authoring ceiling, so the walk above is now its only
    # correctness guarantee. Emitted regardless of whether the rule checks below
    # find defects; it flags reviewability, not a defect. Never blocks.
    if len(story.nodes) > HAND_AUTHORING_NODE_CEILING:
        report.add(
            _l2_13_finding(story.id, len(story.nodes), HAND_AUTHORING_NODE_CEILING)
        )

    ctx = _WalkContext(
        story_id=story.id,
        result=result,
        engine=StoryEngine(story),
    )

    dead_end_keys = _check_dead_ends(ctx, report)
    _check_loop_escape(ctx, dead_end_keys, report)
    _check_dead_branches(ctx, story, report)

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


def _l2_13_finding(story_id: str, node_count: int, ceiling: int) -> ValidationFinding:
    """Build the L2-13 scale-advisory finding (WARNING, non-blocking).

    Args:
        story_id: The story id.
        node_count: The story's node count.
        ceiling: The hand-authoring node ceiling that was exceeded.

    Returns:
        ValidationFinding: The formatted L2-13 advisory finding.
    """
    return ValidationFinding(
        rule_id="L2-13",
        severity=Severity.WARNING,
        story_id=story_id,
        message=(
            f"L2-13 scale: Tier-2 story '{story_id}' has {node_count} nodes, past "
            f"the hand-authoring ceiling of {ceiling}; the completed Layer-2 "
            f"configuration walk is now its sole correctness guarantee "
            f"(hand-review insufficient at this scale)"
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


def _condition_var_names(condition: object) -> set[str]:
    """Return every variable name referenced anywhere in a condition tree.

    A condition is a plain nested dict whose variable references are
    ``{"var": name}`` leaves (``storybook/condition.py``), so the walk is
    structural and needs no evaluator.

    Args:
        condition: A condition dict, or any nested fragment of one.

    Returns:
        set[str]: The referenced variable names.
    """
    names: set[str] = set()
    if isinstance(condition, dict):
        typed = cast("dict[str, object]", condition)
        for key, value in typed.items():
            if key == "var" and isinstance(value, str):
                names.add(value)
            else:
                names |= _condition_var_names(value)
    elif isinstance(condition, list):
        for item in cast("list[object]", condition):
            names |= _condition_var_names(item)
    return names


def _dead_branch_cause(story: Storybook, node_id: str, condition: object) -> str | None:
    """Return a plain-language cause for an unsatisfiable condition, if known.

    Across a real series build every L2-11 had one of exactly two causes, and the
    bare "condition always false" message pointed at neither. Both are
    mechanically detectable from data the walk already has, and the hint also
    reaches the Stage C repair prompt, which receives findings verbatim: a repair
    model told the cause fixes the gate, while one told only the symptom tends to
    delete the branch.

    Args:
        story: The parsed story, for variable declarations and effects.
        node_id: The node owning the dead choice.
        condition: The choice's condition tree.

    Returns:
        str | None: A cause clause to append, or ``None`` when neither pattern
            matches and the generic message should stand alone.
    """
    referenced = _condition_var_names(condition)
    if not referenced:
        return None
    declared = {var.name: var for var in story.variables}
    mutated: set[str] = set()
    for node in story.nodes:
        for effect in node.on_enter:
            mutated.add(effect.var)
        for choice in node.choices:
            for effect in choice.effects:
                mutated.add(effect.var)

    for name in sorted(referenced):
        var = declared.get(name)
        if var is None:
            continue
        # Carried-variable polarity: a continuation seeds a carried variable
        # true and never unsets it, so any condition requiring it false is
        # unsatisfiable by construction.
        if var.initial is True and name not in mutated:
            return (
                f"variable '{name}' initialises true and no effect ever unsets it, "
                f"so a condition requiring it false can never hold; carried state "
                f"in a continuation is read-only"
            )
        # Grant order: the gate is reachable but no node that grants the
        # variable precedes it, so the gate is checked before it can be earned.
        if (
            var.initial is False
            and name in mutated
            and _no_grant_precedes(story, node_id, name)
        ):
            return (
                f"no node granting '{name}' precedes this one, so the gate is "
                f"reached before the variable can be earned"
            )
    return None


def _no_grant_precedes(story: Storybook, node_id: str, var_name: str) -> bool:
    """Whether no node that mutates ``var_name`` can reach ``node_id``."""
    granting = {
        node.id for node in story.nodes for e in node.on_enter if e.var == var_name
    } | {
        node.id
        for node in story.nodes
        for choice in node.choices
        for e in choice.effects
        if e.var == var_name
    }
    graph = _forward_graph(story)
    if node_id not in graph:
        return False
    return not any(
        target != node_id and nx.has_path(graph, target, node_id)
        for target in granting
        if target in graph
    )


def _forward_graph(story: Storybook) -> nx.DiGraph[str]:
    """Build the choice graph over node ids, ignoring conditions."""
    graph: nx.DiGraph[str] = nx.DiGraph()
    graph.add_nodes_from(node.id for node in story.nodes)
    for node in story.nodes:
        for choice in node.choices:
            graph.add_edge(node.id, choice.target)
    return graph


def _l2_11_finding(
    story_id: str,
    node_id: str,
    choice_id: str,
    cause: str | None = None,
) -> ValidationFinding:
    """Build an L2-11 dead-branch finding, with a cause hint when one is known.

    Args:
        story_id: The story id.
        node_id: The node that owns the dead choice.
        choice_id: The choice id that is never visible.
        cause: An optional plain-language cause clause.

    Returns:
        ValidationFinding: The formatted L2-11 finding.
    """
    suffix = f" ({cause})" if cause else " (condition always false)"
    return ValidationFinding(
        rule_id="L2-11",
        severity=Severity.ERROR,
        story_id=story_id,
        node_id=node_id,
        choice_id=choice_id,
        message=(
            f"L2-11 dead-branch: choice '{choice_id}' on node '{node_id}' "
            f"is never visible in any reachable configuration in story "
            f"'{story_id}'{suffix}"
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
    story: Storybook,
    report: ValidationReport,
) -> None:
    """L2-11: flag conditional choices that are never visible in any reachable config.

    A conditional choice on a reachable node that is invisible in every
    reachable configuration of that node is a dead branch.

    Args:
        ctx: The walk context (story id, result, engine).
        story: The parsed story, for its nodes and variable declarations.
        report: The report to append findings to.
    """
    reachable = _reachable_node_ids(ctx)
    ever_visible = _ever_visible_choice_ids(ctx)
    node_map = {node.id: node for node in story.nodes}

    for node_id in reachable:
        node = node_map.get(node_id)
        if node is None:
            continue
        for choice in node.choices:
            if choice.condition is None:
                continue  # unconditional choices are never dead branches
            if choice.id not in ever_visible:
                cause = _dead_branch_cause(story, node_id, choice.condition)
                report.add(_l2_11_finding(ctx.story_id, node_id, choice.id, cause))
