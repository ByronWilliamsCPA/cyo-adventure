"""Layer-1 graph validator (rules L1-1 through L1-7).

Layer 1 runs on every story and is a hard gate: any error-severity finding blocks
the story from advancing past ``auto_check``. The rule ids and failure-message
templates come from ``docs/planning/validator-rules.md``; the node and depth
budgets come from ``docs/planning/drafting-guide.md``.

This validator operates on the raw decoded JSON (a mapping) rather than a parsed
``Storybook`` so that each violation is attributed to its specific rule id even
when the Pydantic model would also reject it. L1-1 uses the exported JSON Schema
as the structural backstop; the remaining rules are checked explicitly.

Layer 2 (state-space, Tier-2 only: stateful dead ends, loop escape, the
configuration cap) is intentionally out of scope here and lands in Phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias, cast

import networkx as nx
from jsonschema import Draft202012Validator

from cyo_adventure.storybook.condition import (
    COMPARISON_OPERATORS,
    referenced_vars,
    validate_condition,
)
from cyo_adventure.storybook.schema_export import build_schema
from cyo_adventure.validator.report import (
    Severity,
    ValidationFinding,
    ValidationReport,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic import JsonValue

# Age band -> (min nodes, max nodes, max branch depth). From the drafting guide.
_BUDGETS: dict[str, tuple[int, int, int]] = {
    "8-11": (15, 30, 6),
    "10-13": (25, 50, 8),
    "13-16": (30, 60, 10),
}


def band_budget(age_band: str) -> tuple[int, int, int] | None:
    """Return the ``(min_nodes, max_nodes, max_branch_depth)`` budget for a band.

    This is the single source of truth for the L1-7 node-count and branch-depth
    budget. The Stage A prompt builder imports it so the prompt promises models
    exactly what :func:`_check_budget` enforces; keeping one table prevents the
    prompt and the gate from drifting apart (which would either over-constrain
    generation or let overshoot through).

    Args:
        age_band: The story age band value (e.g. ``"8-11"``), matching an
            :class:`~cyo_adventure.storybook.models.AgeBand` value.

    Returns:
        The ``(min_nodes, max_nodes, max_branch_depth)`` triple for the band,
        or ``None`` when the band is not in the budget table.
    """
    return _BUDGETS.get(age_band)


_ORDERING_OPERATORS: frozenset[str] = frozenset({"<", "<=", ">", ">="})

# Cast shapes for raw decoded JSON, named once to avoid duplicated type literals.
_ObjectMap: TypeAlias = dict[str, object]
_ObjectList: TypeAlias = list[object]


def _as_map(value: object) -> _ObjectMap:
    """Narrow a raw-JSON value to a string-keyed mapping (caller-checked shape)."""
    return cast("dict[str, object]", value)


def _as_list(value: object) -> _ObjectList:
    """Narrow a raw-JSON value to a list (caller-checked shape)."""
    return cast("list[object]", value)


@dataclass(frozen=True, slots=True)
class _VarInfo:
    """Declared variable types and int bounds, bundled for the L1-6 effect checks."""

    types: dict[str, str]
    bounds: dict[str, tuple[int | None, int | None]]


@dataclass(frozen=True, slots=True)
class _BudgetViolation:
    """An L1-7 budget breach: which dimension, the value, the band, severity."""

    budget_type: str
    actual: int
    low: int
    high: int
    severity: Severity


class _Story:
    """A defensively-parsed view of a story for the semantic rules.

    Only well-formed parts are exposed; malformed parts are dropped so a rule can
    run without raising. L1-1 reports the structural problems separately.
    """

    def __init__(self, data: Mapping[str, object]) -> None:
        """Build the view from raw decoded JSON.

        Args:
            data: The decoded story mapping.
        """
        raw_id = data.get("id")
        self.story_id: str = raw_id if isinstance(raw_id, str) else "<unknown>"
        raw_start = data.get("start_node")
        self.start_node: str | None = raw_start if isinstance(raw_start, str) else None
        raw_meta = data.get("metadata")
        self.metadata: dict[str, object] = (
            raw_meta if isinstance(raw_meta, dict) else {}
        )
        raw_nodes = data.get("nodes")
        self.nodes: list[dict[str, object]] = (
            [n for n in raw_nodes if isinstance(n, dict)]
            if isinstance(raw_nodes, list)
            else []
        )
        raw_vars = data.get("variables")
        self.variables: list[dict[str, object]] = (
            [v for v in raw_vars if isinstance(v, dict)]
            if isinstance(raw_vars, list)
            else []
        )

    def node_ids(self) -> list[str]:
        """Return every node id that is a string, in document order.

        Returns:
            list[str]: The node ids.
        """
        return [nid for n in self.nodes if isinstance((nid := n.get("id")), str)]

    def declared_var_types(self) -> dict[str, str]:
        """Return a map of declared variable name to its declared type string.

        Returns:
            dict[str, str]: ``name -> "bool" | "int"`` for well-formed declarations.
        """
        out: dict[str, str] = {}
        for var in self.variables:
            name = var.get("name")
            vtype = var.get("type")
            if isinstance(name, str) and isinstance(vtype, str):
                out[name] = vtype
        return out

    def declared_int_bounds(self) -> dict[str, tuple[int | None, int | None]]:
        """Return declared ``(min, max)`` bounds for each int variable.

        Returns:
            dict[str, tuple[int | None, int | None]]: ``name -> (min, max)`` for
                int variables; a bound is ``None`` when not declared.
        """
        out: dict[str, tuple[int | None, int | None]] = {}
        for var in self.variables:
            name = var.get("name")
            if var.get("type") != "int" or not isinstance(name, str):
                continue
            low = var.get("min")
            high = var.get("max")
            out[name] = (
                low if isinstance(low, int) and not isinstance(low, bool) else None,
                high if isinstance(high, int) and not isinstance(high, bool) else None,
            )
        return out


def validate_layer1(data: Mapping[str, object]) -> ValidationReport:
    """Run every Layer-1 rule over a decoded story mapping.

    Args:
        data: The decoded story JSON.

    Returns:
        ValidationReport: All findings; ``report.ok`` is ``True`` when no
            error-severity finding was raised.
    """
    report = ValidationReport()
    story = _Story(data)
    _check_schema(data, story, report)
    _check_references(story, report)
    _check_logic(story, report)
    if story.start_node is not None and story.nodes:
        graph = _build_graph(story)
        _check_graph_termination(story, graph, report)
        _check_reachability(story, graph, report)
        _check_trap_loops(story, graph, report)
        _check_budget(story, graph, report)
    return report


def _check_schema(
    data: Mapping[str, object], story: _Story, report: ValidationReport
) -> None:
    """L1-1: validate the document against the exported Storybook JSON Schema."""
    validator = Draft202012Validator(build_schema())
    for error in validator.iter_errors(cast("JsonValue", dict(data))):
        location = "/".join(str(p) for p in error.absolute_path) or "<root>"
        report.add(
            ValidationFinding(
                rule_id="L1-1",
                severity=Severity.ERROR,
                story_id=story.story_id,
                message=(
                    f"L1-1 schema: document does not conform to Storybook schema "
                    f"at '{location}': {error.message}"
                ),
            )
        )


def _check_references(story: _Story, report: ValidationReport) -> None:
    """L1-2: id uniqueness, start_node existence, and choice-target existence."""
    node_ids = story.node_ids()
    _report_duplicates("node", node_ids, story, report)
    choice_ids: list[str] = []
    ending_ids: list[str] = []
    id_set = set(node_ids)
    for node in story.nodes:
        _collect_node_ref_ids(node, choice_ids, ending_ids)
        _check_choice_targets(node, id_set, story.story_id, report)
    _report_duplicates("choice", choice_ids, story, report)
    _report_duplicates("ending", ending_ids, story, report)
    if story.start_node is not None and story.start_node not in id_set:
        report.add(
            ValidationFinding(
                rule_id="L1-2",
                severity=Severity.ERROR,
                story_id=story.story_id,
                message=(
                    f"L1-2 ref: start_node '{story.start_node}' not found or not "
                    f"unique in story '{story.story_id}' (referenced from start_node)"
                ),
            )
        )


def _collect_node_ref_ids(
    node: dict[str, object], choice_ids: list[str], ending_ids: list[str]
) -> None:
    """Accumulate choice ids and the ending id declared on a node."""
    raw_choices = node.get("choices")
    if isinstance(raw_choices, list):
        choice_ids.extend(
            cast("str", c["id"])
            for c in raw_choices
            if isinstance(c, dict) and isinstance(c.get("id"), str)
        )
    ending = node.get("ending")
    if isinstance(ending, dict) and isinstance(ending.get("id"), str):
        ending_ids.append(cast("str", ending["id"]))


def _check_choice_targets(
    node: dict[str, object],
    id_set: set[str],
    story_id: str,
    report: ValidationReport,
) -> None:
    """L1-2: every choice target must resolve to an existing node id."""
    raw_node_id = node.get("id")
    node_id = raw_node_id if isinstance(raw_node_id, str) else None
    raw_choices = node.get("choices")
    if not isinstance(raw_choices, list):
        return
    for choice in raw_choices:
        if not isinstance(choice, dict):
            continue
        target = choice.get("target")
        raw_choice_id = choice.get("id")
        choice_id = raw_choice_id if isinstance(raw_choice_id, str) else None
        if isinstance(target, str) and target not in id_set:
            report.add(
                ValidationFinding(
                    rule_id="L1-2",
                    severity=Severity.ERROR,
                    story_id=story_id,
                    node_id=node_id,
                    choice_id=choice_id,
                    message=(
                        f"L1-2 ref: target '{target}' not found or not unique in "
                        f"story '{story_id}' (referenced from node '{node_id}')"
                    ),
                )
            )


def _report_duplicates(
    ref_type: str, ids: list[str], story: _Story, report: ValidationReport
) -> None:
    """L1-2: report any id that appears more than once."""
    seen: set[str] = set()
    duplicated: set[str] = set()
    for identifier in ids:
        if identifier in seen:
            duplicated.add(identifier)
        seen.add(identifier)
    for identifier in sorted(duplicated):
        report.add(
            ValidationFinding(
                rule_id="L1-2",
                severity=Severity.ERROR,
                story_id=story.story_id,
                message=(
                    f"L1-2 ref: {ref_type} '{identifier}' not found or not unique "
                    f"in story '{story.story_id}' (referenced from {ref_type} id)"
                ),
            )
        )


def _check_logic(story: _Story, report: ValidationReport) -> None:
    """L1-6: operator whitelist, variable declarations, types, and tier rule."""
    declared = story.declared_var_types()
    var_info = _VarInfo(types=declared, bounds=story.declared_int_bounds())
    _check_variable_declarations(story, report)
    _check_tier_variables(story, declared, report)
    for node in story.nodes:
        _check_node_conditions(node, declared, story.story_id, report)
        _check_node_effects(node, var_info, story.story_id, report)


def _check_variable_declarations(story: _Story, report: ValidationReport) -> None:
    """L1-6: each declared variable's initial value and bounds must be valid."""
    for var in story.variables:
        name = var.get("name")
        vtype = var.get("type")
        if not (isinstance(name, str) and isinstance(vtype, str)):
            continue
        detail = _variable_declaration_error(var, vtype)
        if detail is not None:
            report.add(
                ValidationFinding(
                    rule_id="L1-6",
                    severity=Severity.ERROR,
                    story_id=story.story_id,
                    message=(
                        f"L1-6 logic: invalid variable declaration in story "
                        f"'{story.story_id}' at variable '{name}': {detail} "
                        f"(var='{name}', declared_type={vtype})"
                    ),
                )
            )


def _variable_declaration_error(var: dict[str, object], vtype: str) -> str | None:
    """Return a description of a bad variable declaration, or None if valid."""
    initial = var.get("initial")
    if vtype == "bool":
        if not isinstance(initial, bool):
            return "bool variable must have a boolean initial value"
        return None
    if isinstance(initial, bool) or not isinstance(initial, int):
        return "int variable must have an integer initial value"
    return _int_bounds_error(var, initial)


def _int_bounds_error(var: dict[str, object], initial: int) -> str | None:
    """Return a description of an int variable's bound problem, or None."""
    low = var.get("min")
    high = var.get("max")
    if isinstance(low, int) and isinstance(high, int) and low > high:
        return f"min {low} exceeds max {high}"
    if isinstance(low, int) and initial < low:
        return f"initial {initial} below min {low}"
    if isinstance(high, int) and initial > high:
        return f"initial {initial} above max {high}"
    return None


def _check_tier_variables(
    story: _Story, declared: dict[str, str], report: ValidationReport
) -> None:
    """L1-6: a Tier-1 story must not declare any variables."""
    if story.metadata.get("tier") == 1 and declared:
        report.add(
            ValidationFinding(
                rule_id="L1-6",
                severity=Severity.ERROR,
                story_id=story.story_id,
                message=(
                    f"L1-6 logic: tier-1 story must not declare variables in story "
                    f"'{story.story_id}' at metadata: declared {sorted(declared)}"
                ),
            )
        )


def _check_node_conditions(
    node: dict[str, object],
    declared: dict[str, str],
    story_id: str,
    report: ValidationReport,
) -> None:
    """L1-6: choice conditions must be whitelisted and reference declared vars."""
    raw_node_id = node.get("id")
    node_id = raw_node_id if isinstance(raw_node_id, str) else None
    raw_choices = node.get("choices")
    if not isinstance(raw_choices, list):
        return
    for choice in raw_choices:
        if not isinstance(choice, dict):
            continue
        condition = choice.get("condition")
        if not isinstance(condition, dict):
            continue
        raw_choice_id = choice.get("id")
        choice_id = raw_choice_id if isinstance(raw_choice_id, str) else None
        typed_condition = _as_map(condition)
        detail = _condition_error(typed_condition, declared)
        if detail is not None:
            report.add(
                ValidationFinding(
                    rule_id="L1-6",
                    severity=Severity.ERROR,
                    story_id=story_id,
                    node_id=node_id,
                    choice_id=choice_id,
                    message=(
                        f"L1-6 logic: invalid condition in story '{story_id}' "
                        f"at choice '{choice_id}': {detail}"
                    ),
                )
            )


def _condition_error(
    condition: dict[str, object], declared: dict[str, str]
) -> str | None:
    """Return a description of the first condition problem, or None if valid."""
    typed = cast("dict[str, JsonValue]", condition)
    try:
        validate_condition(typed)
    except ValueError as exc:
        return f"operator not whitelisted or malformed shape: {exc}"
    undeclared = referenced_vars(typed) - declared.keys()
    if undeclared:
        return f"references undeclared variable(s) {sorted(undeclared)}"
    return _comparison_type_error(condition, declared)


def _comparison_type_error(
    condition: dict[str, object], declared: dict[str, str]
) -> str | None:
    """Return an ordering-on-bool type error inside a condition, or None."""
    for operator, operand in condition.items():
        if operator in _ORDERING_OPERATORS and isinstance(operand, list):
            detail = _ordering_bool_error(operator, _as_list(operand), declared)
        elif operator not in COMPARISON_OPERATORS and isinstance(operand, list):
            detail = _scan_nested(_as_list(operand), declared)
        elif operator == "!" and isinstance(operand, dict):
            detail = _comparison_type_error(_as_map(operand), declared)
        else:
            detail = None
        if detail is not None:
            return detail
    return None


def _ordering_bool_error(
    operator: str, operand: list[object], declared: dict[str, str]
) -> str | None:
    """Return an error if an ordering operator is applied to a bool variable."""
    for side in operand:
        if not isinstance(side, dict):
            continue
        name = _as_map(side).get("var")
        if isinstance(name, str) and declared.get(name) == "bool":
            return f"ordering operator '{operator}' applied to bool variable '{name}'"
    return None


def _scan_nested(operand: list[object], declared: dict[str, str]) -> str | None:
    """Scan an n-ary operand list for a nested comparison type error."""
    for clause in operand:
        if isinstance(clause, dict):
            nested = _comparison_type_error(_as_map(clause), declared)
            if nested is not None:
                return nested
    return None


def _check_node_effects(
    node: dict[str, object],
    var_info: _VarInfo,
    story_id: str,
    report: ValidationReport,
) -> None:
    """L1-6: effects must target declared variables with type-correct values."""
    raw_node_id = node.get("id")
    node_id = raw_node_id if isinstance(raw_node_id, str) else None
    effects = _gather_effects(node)
    for effect in effects:
        var = effect.get("var")
        if not isinstance(var, str):
            continue
        detail = _effect_error(effect, var, var_info)
        if detail is not None:
            report.add(
                ValidationFinding(
                    rule_id="L1-6",
                    severity=Severity.ERROR,
                    story_id=story_id,
                    node_id=node_id,
                    message=(
                        f"L1-6 logic: invalid effect in story '{story_id}' at "
                        f"node '{node_id}': {detail} (var='{var}', "
                        f"declared_type={var_info.types.get(var, 'undeclared')})"
                    ),
                )
            )


def _gather_effects(node: dict[str, object]) -> list[dict[str, object]]:
    """Return every effect dict on a node (on_enter plus choice effects)."""
    out: list[dict[str, object]] = []
    raw_on_enter = node.get("on_enter")
    if isinstance(raw_on_enter, list):
        out.extend(e for e in raw_on_enter if isinstance(e, dict))
    raw_choices = node.get("choices")
    if isinstance(raw_choices, list):
        for choice in raw_choices:
            if isinstance(choice, dict) and isinstance(choice.get("effects"), list):
                out.extend(
                    e for e in _as_list(choice["effects"]) if isinstance(e, dict)
                )
    return out


def _effect_error(
    effect: dict[str, object], var: str, var_info: _VarInfo
) -> str | None:
    """Return a description of a bad effect, or None if valid."""
    if var not in var_info.types:
        return "references undeclared variable"
    op = effect.get("op")
    value = effect.get("value")
    vtype = var_info.types[var]
    if op in {"inc", "dec"}:
        return _inc_dec_effect_error(op, vtype, value)
    if op == "set":
        return _set_effect_error(var, vtype, value, var_info.bounds)
    return None


def _inc_dec_effect_error(op: object, vtype: str, value: object) -> str | None:
    """Return an error for a bad ``inc``/``dec`` effect, or None if valid."""
    if vtype != "int":
        return f"'{op}' may only target an int variable"
    if isinstance(value, bool) or not isinstance(value, int):
        return f"'{op}' requires an integer value"
    return None


def _set_effect_error(
    var: str,
    vtype: str,
    value: object,
    bounds: dict[str, tuple[int | None, int | None]],
) -> str | None:
    """Return an error for a bad ``set`` effect, or None if valid."""
    if vtype == "bool" and not isinstance(value, bool):
        return "'set' on a bool variable requires a boolean value"
    if vtype == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            return "'set' on an int variable requires an integer value"
        return _set_bounds_error(var, value, bounds)
    return None


def _set_bounds_error(
    var: str, value: int, bounds: dict[str, tuple[int | None, int | None]]
) -> str | None:
    """Return an error if a ``set`` value falls outside the variable's bounds."""
    low, high = bounds.get(var, (None, None))
    if low is not None and value < low:
        return f"'set' value {value} below min {low}"
    if high is not None and value > high:
        return f"'set' value {value} above max {high}"
    return None


def _build_graph(story: _Story) -> nx.DiGraph[str]:
    """Build the directed choice graph over existing node ids."""
    graph: nx.DiGraph[str] = nx.DiGraph()
    id_set = set(story.node_ids())
    graph.add_nodes_from(id_set)
    for node in story.nodes:
        node_id = node.get("id")
        if not isinstance(node_id, str):
            continue
        raw_choices = node.get("choices")
        if not isinstance(raw_choices, list):
            continue
        for choice in raw_choices:
            if isinstance(choice, dict):
                target = choice.get("target")
                if isinstance(target, str) and target in id_set:
                    graph.add_edge(node_id, target)
    return graph


def _ending_ids(story: _Story) -> set[str]:
    """Return the ids of nodes marked as endings."""
    return {
        cast("str", n["id"])
        for n in story.nodes
        if n.get("is_ending") is True and isinstance(n.get("id"), str)
    }


def _nodes_reaching_endings(graph: nx.DiGraph[str], endings: set[str]) -> set[str]:
    """Return every node from which some ending node is reachable."""
    reaching: set[str] = set(endings)
    for ending in endings:
        if ending in graph:
            reaching |= nx.ancestors(graph, ending)
    return reaching


def _check_graph_termination(
    story: _Story, graph: nx.DiGraph[str], report: ValidationReport
) -> None:
    """L1-4: ending consistency, non-ending choices, and path-to-ending."""
    can_reach = _nodes_reaching_endings(graph, _ending_ids(story))
    for node in story.nodes:
        _check_node_termination(node, can_reach, story.story_id, report)


def _check_node_termination(
    node: dict[str, object],
    can_reach: set[str],
    story_id: str,
    report: ValidationReport,
) -> None:
    """L1-4: assess a single node's termination obligations."""
    node_id = node.get("id")
    if not isinstance(node_id, str):
        return
    is_ending = node.get("is_ending") is True
    raw_choices = node.get("choices")
    choice_count = len(raw_choices) if isinstance(raw_choices, list) else 0
    reason: str | None = None
    if is_ending and (choice_count > 0 or not isinstance(node.get("ending"), dict)):
        reason = "ending node has choices or is missing its ending block"
    elif not is_ending and choice_count == 0:
        reason = "non-ending node has zero choices"
    elif not is_ending and node_id not in can_reach:
        reason = "no path to any ending"
    if reason is not None:
        report.add(
            ValidationFinding(
                rule_id="L1-4",
                severity=Severity.ERROR,
                story_id=story_id,
                node_id=node_id,
                message=f"L1-4 term: node '{node_id}' {reason} in story '{story_id}'",
            )
        )


def _check_reachability(
    story: _Story, graph: nx.DiGraph[str], report: ValidationReport
) -> None:
    """L1-3: every node must be reachable from start_node via BFS."""
    start = story.start_node
    if start is None or start not in graph:
        return
    reachable = nx.descendants(graph, start) | {start}
    for node_id in sorted(set(graph.nodes) - reachable):
        report.add(
            ValidationFinding(
                rule_id="L1-3",
                severity=Severity.ERROR,
                story_id=story.story_id,
                node_id=node_id,
                message=(
                    f"L1-3 reach: node '{node_id}' is unreachable from start_node "
                    f"'{start}' in story '{story.story_id}'"
                ),
            )
        )


def _check_trap_loops(
    story: _Story, graph: nx.DiGraph[str], report: ValidationReport
) -> None:
    """L1-5: every non-trivial SCC must be able to reach an ending."""
    endings = _ending_ids(story)
    can_reach = _nodes_reaching_endings(graph, endings)
    for component in nx.strongly_connected_components(graph):
        if not _is_nontrivial_scc(graph, component):
            continue
        if component & can_reach:
            continue
        anchor = min(component)
        report.add(
            ValidationFinding(
                rule_id="L1-5",
                severity=Severity.ERROR,
                story_id=story.story_id,
                node_id=anchor,
                message=(
                    f"L1-5 trap: strongly connected component containing node "
                    f"'{anchor}' has no exit edge in story '{story.story_id}' "
                    f"(nodes in SCC: {sorted(component)})"
                ),
            )
        )


def _is_nontrivial_scc(graph: nx.DiGraph[str], component: set[str]) -> bool:
    """Return True for a multi-node SCC or a single node with a self-loop."""
    if len(component) > 1:
        return True
    (only,) = tuple(component)
    return graph.has_edge(only, only)


def _check_budget(
    story: _Story, graph: nx.DiGraph[str], report: ValidationReport
) -> None:
    """L1-7: ending_count match, node-count band, and max branch depth."""
    _check_ending_count(story, report)
    band = story.metadata.get("age_band")
    if not isinstance(band, str) or band not in _BUDGETS:
        return
    min_nodes, max_nodes, max_depth = _BUDGETS[band]
    count = len(story.node_ids())
    if count > max_nodes:
        report.add(
            _budget_finding(
                story.story_id,
                _BudgetViolation(
                    "node_count", count, min_nodes, max_nodes, Severity.ERROR
                ),
            )
        )
    elif count < min_nodes:
        report.add(
            _budget_finding(
                story.story_id,
                _BudgetViolation(
                    "node_count", count, min_nodes, max_nodes, Severity.WARNING
                ),
            )
        )
    depth = _branch_depth(story, graph)
    if depth is not None and depth > max_depth:
        report.add(
            _budget_finding(
                story.story_id,
                _BudgetViolation("branch_depth", depth, 0, max_depth, Severity.ERROR),
            )
        )


def _check_ending_count(story: _Story, report: ValidationReport) -> None:
    """L1-7: metadata.ending_count must equal the count of distinct endings."""
    declared = story.metadata.get("ending_count")
    actual = len(_ending_ids(story))
    if (
        isinstance(declared, int)
        and not isinstance(declared, bool)
        and declared != actual
    ):
        report.add(
            ValidationFinding(
                rule_id="L1-7",
                severity=Severity.ERROR,
                story_id=story.story_id,
                message=(
                    f"L1-7 budget: ending_count out of range in story "
                    f"'{story.story_id}': {actual} (allowed {declared}..{declared})"
                ),
            )
        )


def _budget_finding(story_id: str, violation: _BudgetViolation) -> ValidationFinding:
    """Build an L1-7 budget finding with the standard message template.

    Args:
        story_id: The story the finding applies to.
        violation: The budget dimension, actual value, allowed band, and severity.

    Returns:
        ValidationFinding: The formatted L1-7 finding.
    """
    return ValidationFinding(
        rule_id="L1-7",
        severity=violation.severity,
        story_id=story_id,
        message=(
            f"L1-7 budget: {violation.budget_type} out of range in story "
            f"'{story_id}': {violation.actual} (allowed {violation.low}..{violation.high})"
        ),
    )


def _branch_depth(story: _Story, graph: nx.DiGraph[str]) -> int | None:
    """Return the longest start-to-ending path length, or None if not a DAG.

    Branch depth is the longest path in hops over the reachable subgraph. When
    that subgraph contains a cycle the longest path is ill-defined, so depth is
    skipped (a trap cycle is already flagged by L1-5 and a legitimate loop is a
    Layer-2 concern).
    """
    start = story.start_node
    if start is None or start not in graph:
        return None
    reachable = nx.descendants(graph, start) | {start}
    subgraph = graph.subgraph(reachable)
    if not nx.is_directed_acyclic_graph(subgraph):
        return None
    return int(nx.dag_longest_path_length(subgraph))
