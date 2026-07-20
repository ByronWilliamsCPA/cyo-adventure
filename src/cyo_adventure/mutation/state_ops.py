"""The M5 state-variation operator family (WS-5 D6, design section 5).

M5 makes one verified stateful (Tier-2) tree play as several: same map,
different pressure. Two halves, both driven by explicit, JSON-scalar parameters
so a given ``(parent, params)`` yields a byte-identical candidate:

- **M5a** (design 5.1): variable semantics and dynamics retune (``mode=retune``)
  and pure alpha-rename (``mode=rename``). Within a declared variable's type it
  changes ``initial``/``min``/``max`` and the variable's ``description`` (and,
  where new bounds narrow the range, clamps the integer literals in conditions
  and ``set`` effects that reference the variable), or renames the variable and
  every reference in one pass. It never changes a variable's type and never adds
  or removes a variable (design 5.5, deferred).
- **M5b** (design 5.2): condition-gated route add/rewire. ``mode=gate-choice``
  adds a condition to a currently unconditioned choice; ``mode=add-route`` adds a
  new condition-gated choice on a decision node targeting an existing node (a
  shortcut / secret door); ``mode=relocate-effect`` moves an ``on_enter`` effect
  to a different node, preserving its ``op``/``var``/``value``/``once``.

Every M5 operator requires ``recompute_tier(parent) == 2`` and a band whose
ADR-011 section 7 row permits stateful loops (8-11 and up). None of them touches
an ending kind, valence, or the ending multiset, so the fail-state policy
surface (PL-15/16/17) is untouched by construction; this is asserted after every
apply (:func:`_assert_endings_untouched`).

The dead/trap-state obligation each M5b move can create is proven by the walk,
not by the operator: the unchanged gate's Layer 2 (L2-9..L2-12) over
``walk_configurations`` is the authority. The operator does only cheap
preconditions (design 5.2).

This module also carries the state-signature vector, its distance, the
promotion-only state-signature floor (design 5.4), and the two Tier-2 acceptance
checks the gate does not directly make (design 5.3): ending coverage and the
clock re-proof over the configuration walk. The acceptance harness
(``mutation/acceptance.py``) consumes those from a single ``WalkResult``.

Pure module: standard library, ``networkx``, and lower project layers only. It
imports from ``validator`` and ``player`` solely to *call* the walk and the
band-floor lookups, never to construct a report or move a threshold (design
CR-2). It imports nothing from ``db``, ``generation``, or ``network``.
"""

from __future__ import annotations

import copy
import json
from collections import Counter, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import networkx as nx

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation.identity import recompute_tier, resync_metadata
from cyo_adventure.mutation.ops import (
    REGISTRY,
    MutationResult,
    OpParams,
    PreconditionReport,
    ReguideItem,
    ReguideTarget,
)
from cyo_adventure.mutation.subtree import adjacency, node_ids
from cyo_adventure.storybook.condition import (
    COMPARISON_OPERATORS,
    MAX_ABS_STORY_INT,
    ORDERING_OPERATORS,
    referenced_vars,
    validate_condition,
)
from cyo_adventure.storybook.models import Effect, EndingKind, Storybook, Variable
from cyo_adventure.validator.band_profile import min_complete_floor
from cyo_adventure.validator.walk import walk_configurations

if TYPE_CHECKING:
    import random
    from collections.abc import Mapping

    from pydantic import JsonValue

    from cyo_adventure.validator.walk import ConfigKey, WalkResult

# The M5 operator id, recorded in every lineage manifest and used as the registry
# key. Kept as a module constant so the CLI and tests never spell the literal.
M5_OP_ID = "M5"

# The five M5 sub-operation modes (design 5.1-5.2), matching the single-operator
# ``mode`` shape M3/M4 use.
_M5_MODE_RETUNE = "retune"
_M5_MODE_RENAME = "rename"
_M5_MODE_GATE_CHOICE = "gate-choice"
_M5_MODE_ADD_ROUTE = "add-route"
_M5_MODE_RELOCATE = "relocate-effect"
_M5_MODES: frozenset[str] = frozenset(
    {
        _M5_MODE_RETUNE,
        _M5_MODE_RENAME,
        _M5_MODE_GATE_CHOICE,
        _M5_MODE_ADD_ROUTE,
        _M5_MODE_RELOCATE,
    }
)

# The satisfying-ending kinds (a full-arc completion) the clock re-proof targets,
# per ADR-011 section 4; kept in sync with ``validator.policy`` by value.
_SATISFYING_KINDS: frozenset[EndingKind] = frozenset(
    {EndingKind.SUCCESS, EndingKind.COMPLETION}
)

# The ADR-011 section 6 choices-per-decision window (2-3). The gate does not
# hard-enforce choices-per-decision (design 4.8), so M5b add-route self-enforces
# the upper bound as a precondition.
_MAX_CHOICES_PER_DECISION = 3

# #ASSUME: security: the bands whose ADR-011 section 7 row permits stateful loops
# (and therefore Tier-2 state variation) are 8-11 and up; 3-5 and 5-8 are the
# stateless young bands. There is no band-to-state allowance table in code today
# (band_profile carries budgets and content policy, not the loop-allowance row),
# so the row is declared here as a single module-level source, mirroring the
# identity module's _BAND_TOPOLOGIES intent. A Tier-2 skeleton in a stateless
# band would already fail its own hand-authoring review; this predicate keeps M5
# from ever attempting one.
# #VERIFY: tests/unit/test_mutation_m5.py asserts M5 rejects a stateless-band or
# Tier-1 parent at preconditions, and accepts the-flooded-quarter (10-13).
_STATE_PERMITTED_BANDS: frozenset[str] = frozenset({"8-11", "10-13", "13-16", "16+"})

# #ASSUME: data-integrity: the anti-no-op floor for an M5-only mutant is a
# state-signature distance (design 5.4), because a state-only change leaves the
# graph shape (and so structural_distance) at ~0. _TAU_STATE is a PROVISIONAL
# placeholder: D7 calibrates it from cross-Tier-2-catalog signature pairs and
# replaces this number with the committed baseline. It is wired reject-only, so a
# provisional value can only over- or under-reject a non-safety diversity floor,
# never admit an unsafe mutant. 0.5 is chosen so any single bound/initial change,
# any added condition, or any relocated effect clears it while a cosmetic no-op
# (oil 3 -> 3), a description-only edit, and a pure alpha-rename (all distance 0)
# fail it.
# #VERIFY: tests/unit/test_mutation_m5.py pins that a no-op retune, a
# description-only edit, and an alpha-rename all fall below _TAU_STATE, and that a
# real retune / gate-choice / relocate clear it. D7 replaces the value.
_TAU_STATE: float = 0.5
_TAU_STATE_IS_PROVISIONAL = True  # flipped to False by D7 once calibrated.

# Static precondition and error messages, kept as single-line module constants so
# a long fixed string never needs a plain-string line wrap.
_M5_TIER2_ONLY_MSG = (
    "M5 is restricted to Tier-2 (stateful) parents; a Tier-1 tree has no state to "
    "vary"
)
_M5_BAND_MSG = (
    "M5 requires a band whose ADR-011 section 7 row permits stateful loops (8-11 "
    "and up)"
)
_M5_SERIES_MSG = "M5 requires metadata.series to be None; series books are out of scope"
_M5_PRODUCTION_ONLY_MSG = (
    "M5 requires a production-eligible parent; MVP seeds are out of scope"
)
_M5_MODE_MSG = (
    "M5 requires a 'mode' parameter of 'retune', 'rename', 'gate-choice', "
    "'add-route', or 'relocate-effect'"
)
_M5_RETUNE_VAR_MSG = "M5 retune requires a 'variable' parameter naming a declared variable"
_M5_RETUNE_EMPTY_MSG = (
    "M5 retune requires at least one of 'initial', 'min', 'max', or 'description'"
)
_M5_RENAME_MSG = (
    "M5 rename requires a 'variable' (old name) and a 'new_name' matching "
    "^[a-z][a-z0-9_]*$"
)
_M5_GATE_MSG = (
    "M5 gate-choice requires an unconditioned 'choice' id plus 'gate_var', "
    "'gate_op', and 'gate_value'"
)
_M5_ADD_ROUTE_MSG = (
    "M5 add-route requires a 'host' decision id, a 'target' node id, and "
    "'gate_var'/'gate_op'/'gate_value'"
)
_M5_RELOCATE_MSG = (
    "M5 relocate-effect requires a 'from_node' with an on_enter effect and a "
    "non-ending 'to_node'"
)


# ---------------------------------------------------------------------------
# Local dict accessors (the mutation layer re-defines these tiny helpers per
# module, matching identity.py / subtree.py / operators.py, so no module reaches
# into another's private surface).
# ---------------------------------------------------------------------------


def _nodes_of(story: Mapping[str, object]) -> list[Mapping[str, object]]:
    """Return the story's node dicts, skipping any malformed entries."""
    raw = story.get("nodes")
    if not isinstance(raw, list):
        return []
    return [
        cast("Mapping[str, object]", item)
        for item in cast("list[object]", raw)
        if isinstance(item, dict)
    ]


def _choices_of(node: Mapping[str, object]) -> list[Mapping[str, object]]:
    """Return a node's choice dicts, skipping any malformed entries."""
    raw = node.get("choices")
    if not isinstance(raw, list):
        return []
    return [
        cast("Mapping[str, object]", item)
        for item in cast("list[object]", raw)
        if isinstance(item, dict)
    ]


def _str_field(container: Mapping[str, object], key: str) -> str | None:
    """Return a string-valued field of a mapping, or None when not a string."""
    value = container.get(key)
    return value if isinstance(value, str) else None


def _metadata_of(story: Mapping[str, object]) -> Mapping[str, object]:
    """Return the story's metadata block, or an empty mapping when absent."""
    meta = story.get("metadata")
    return cast("Mapping[str, object]", meta) if isinstance(meta, dict) else {}


def _variables_of(story: Mapping[str, object]) -> list[Mapping[str, object]]:
    """Return the story's variable declaration dicts, skipping malformed ones."""
    raw = story.get("variables")
    if not isinstance(raw, list):
        return []
    return [
        cast("Mapping[str, object]", item)
        for item in cast("list[object]", raw)
        if isinstance(item, dict)
    ]


def _variable_names(story: Mapping[str, object]) -> set[str]:
    """Return the set of declared variable names."""
    return {
        name for var in _variables_of(story) if (name := _str_field(var, "name"))
    }


def _node_by_id(
    story: Mapping[str, object], node_id: str
) -> Mapping[str, object] | None:
    """Return the node dict with ``node_id``, or None when absent."""
    for node in _nodes_of(story):
        if _str_field(node, "id") == node_id:
            return node
    return None


def _node_body(story: Mapping[str, object], node_id: str) -> str:
    """Return a node's body text, or the empty string when absent."""
    node = _node_by_id(story, node_id)
    return (_str_field(node, "body") or "") if node is not None else ""


def _choice_ref(
    story: Mapping[str, object], choice_id: str
) -> tuple[str, Mapping[str, object]] | None:
    """Return ``(node_id, choice)`` for a choice id, or None when absent."""
    for node in _nodes_of(story):
        node_id = _str_field(node, "id")
        if node_id is None:
            continue
        for choice in _choices_of(node):
            if _str_field(choice, "id") == choice_id:
                return node_id, choice
    return None


def _ending_multiset(story: Mapping[str, object]) -> tuple[tuple[str, str, str], ...]:
    """Return the sorted ``(ending_id, kind, valence)`` multiset over ending nodes.

    Args:
        story: The raw story document.

    Returns:
        tuple[tuple[str, str, str], ...]: One sorted entry per ending node's
            ``ending`` block; the identity M5 must leave unchanged.
    """
    entries: list[tuple[str, str, str]] = []
    for node in _nodes_of(story):
        if node.get("is_ending") is not True:
            continue
        ending = node.get("ending")
        if not isinstance(ending, dict):
            continue
        block = cast("Mapping[str, object]", ending)
        entries.append(
            (
                _str_field(block, "id") or "",
                _str_field(block, "kind") or "",
                _str_field(block, "valence") or "",
            )
        )
    return tuple(sorted(entries))


def _assert_endings_untouched(
    parent: Mapping[str, object], candidate: Mapping[str, object]
) -> None:
    """Raise unless the candidate's ending multiset equals the parent's.

    Args:
        parent: The raw parent story document.
        candidate: The mutated candidate document.

    Raises:
        ValidationError: If any ending block, kind, valence, or the ending
            multiset changed. M5 never touches an ending by construction; this is
            the fail-closed backstop for that guarantee.
    """
    # #CRITICAL: security: M5 never touches an ending kind, valence, or the
    # ending multiset, which is exactly why the fail-state policy surface
    # (PL-15 forbidden kinds, PL-16 ceilings, PL-17 floors) is untouched by
    # construction (design section 10, 5). This assertion is the type-level
    # guarantee: any M5 apply path that changed an ending is a programming error
    # and is rejected here before the candidate is returned.
    # #VERIFY: tests/unit/test_mutation_m5.py asserts every M5 mode leaves the
    # ending multiset byte-identical and that a hand-tampered ending trips this.
    if _ending_multiset(parent) != _ending_multiset(candidate):
        msg = "M5 must not change any ending block, kind, valence, or the multiset"
        raise ValidationError(msg, field="ending", value=None)


def _reguide_nodes_for_var(
    story: Mapping[str, object], var_name: str, reason: str
) -> tuple[ReguideItem, ...]:
    """Return NODE re-guidance items for the beats that narrate a variable.

    A beat narrates a variable when the node applies an ``on_enter`` effect to it,
    or offers a choice whose condition or effects reference it.

    Args:
        story: The raw story document.
        var_name: The variable whose narrating beats need re-authoring.
        reason: The re-guidance reason recorded on each item.

    Returns:
        tuple[ReguideItem, ...]: One NODE item per narrating node, in id order.
    """
    touched: set[str] = set()
    for node in _nodes_of(story):
        node_id = _str_field(node, "id")
        if node_id is None:
            continue
        if any(_str_field(eff, "var") == var_name for eff in _effects_of(node)):
            touched.add(node_id)
            continue
        for choice in _choices_of(node):
            if _choice_references_var(choice, var_name):
                touched.add(node_id)
                break
    return tuple(
        ReguideItem(
            target=ReguideTarget.NODE,
            target_id=node_id,
            reason=reason,
            current_text=_node_body(story, node_id),
        )
        for node_id in sorted(touched)
    )


def _effects_of(node: Mapping[str, object]) -> list[Mapping[str, object]]:
    """Return a node's ``on_enter`` effect dicts, skipping malformed entries."""
    raw = node.get("on_enter")
    if not isinstance(raw, list):
        return []
    return [
        cast("Mapping[str, object]", item)
        for item in cast("list[object]", raw)
        if isinstance(item, dict)
    ]


def _choice_references_var(choice: Mapping[str, object], var_name: str) -> bool:
    """Return whether a choice's condition or effects reference a variable."""
    condition = choice.get("condition")
    if isinstance(condition, dict) and var_name in referenced_vars(
        cast("dict[str, JsonValue]", condition)
    ):
        return True
    raw = choice.get("effects")
    if isinstance(raw, list):
        for item in cast("list[object]", raw):
            if (
                isinstance(item, dict)
                and cast("dict[str, object]", item).get("var") == var_name
            ):
                return True
    return False


# ---------------------------------------------------------------------------
# Condition assembly (M5b gate-choice / add-route)
# ---------------------------------------------------------------------------


def _assemble_condition(  # noqa: PLR0911 -- one cohesive whitelist ladder, one reason each
    story: Mapping[str, object], gate_var: object, gate_op: object, gate_value: object
) -> tuple[dict[str, object] | None, str | None]:
    """Assemble ``{op: [{"var": name}, value]}`` from scalar params, or a reason.

    The whitelisted-operator, declared-variable, and ordering-int rules are the
    same the schema and L1-6 enforce; assembling the condition here lets an M5b
    move be expressed with JSON-scalar CLI parameters.

    Args:
        story: The raw parent story document.
        gate_var: The variable-name parameter.
        gate_op: The comparison-operator parameter.
        gate_value: The literal-operand parameter.

    Returns:
        tuple[dict[str, object] | None, str | None]: ``(condition, None)`` when
            valid, else ``(None, reason)``.
    """
    if not (isinstance(gate_var, str) and isinstance(gate_op, str)):
        return None, "gate_var and gate_op must be strings"
    if gate_var not in _variable_names(story):
        return None, f"gate_var '{gate_var}' is not a declared variable"
    if gate_op not in COMPARISON_OPERATORS:
        allowed = sorted(COMPARISON_OPERATORS)
        return None, f"gate_op '{gate_op}' is not a comparison operator {allowed}"
    if not isinstance(gate_value, (bool, int)):
        return None, "gate_value must be an int or a bool literal"
    if gate_op in ORDERING_OPERATORS and isinstance(gate_value, bool):
        return None, "an ordering gate_op cannot compare a boolean literal"
    if not isinstance(gate_value, bool) and abs(gate_value) > MAX_ABS_STORY_INT:
        return None, f"gate_value magnitude must be <= {MAX_ABS_STORY_INT}"
    condition: dict[str, object] = {gate_op: [{"var": gate_var}, gate_value]}
    try:
        validate_condition(cast("dict[str, JsonValue]", condition))
    except ValueError as exc:
        return None, f"assembled condition is invalid: {exc}"
    return condition, None


def _clamp_int(value: int, low: int | None, high: int | None) -> int:
    """Return ``value`` clamped into ``[low, high]`` (open where a bound is None)."""
    if low is not None and value < low:
        return low
    if high is not None and value > high:
        return high
    return value


# ---------------------------------------------------------------------------
# M5a retune / rename
# ---------------------------------------------------------------------------


def _int_or_bool(value: object) -> bool | int | None:
    """Return an int or bool parameter unchanged, or None when off-type."""
    return value if isinstance(value, (bool, int)) else None


def _prospective_variable(
    current: Mapping[str, object], params: OpParams
) -> tuple[dict[str, object] | None, str | None]:
    """Build the retuned variable declaration, or a reason it is invalid.

    Applies the provided ``initial``/``min``/``max``/``description`` over the
    current declaration and validates the result against the Variable schema (so
    a type change, an out-of-bounds initial, or a magnitude past
    ``MAX_ABS_STORY_INT`` is rejected here, not only by the gate).

    Args:
        current: The current variable declaration dict.
        params: The operator parameters.

    Returns:
        tuple[dict[str, object] | None, str | None]: ``(new_declaration, None)``
            when valid, else ``(None, reason)``.
    """
    updated = copy.deepcopy(dict(current))
    changed = False
    if params.get("initial") is not None:
        updated["initial"] = _int_or_bool(params.get("initial"))
        changed = True
    for bound in ("min", "max"):
        if params.get(bound) is not None:
            updated[bound] = _int_or_bool(params.get(bound))
            changed = True
    description = params.get("description")
    if isinstance(description, str):
        updated["description"] = description
        changed = True
    if not changed:
        return None, _M5_RETUNE_EMPTY_MSG
    try:
        Variable.model_validate(updated)
    except ValueError as exc:
        return None, f"retuned variable is schema-invalid: {exc}"
    return updated, None


def _clamp_literals_for_var(
    candidate: dict[str, object], var_name: str, low: int | None, high: int | None
) -> None:
    """Clamp int literals referencing a variable into its new ``[low, high]``.

    Rewrites comparison literals in conditions and ``set`` effect values that
    reference ``var_name`` so a narrowed range never leaves a now-out-of-range
    literal (design 5.1, "the integer literals in the conditions and effects that
    reference it"). ``inc``/``dec`` deltas are left alone (they are bounded and
    the engine clamps them at runtime).

    Args:
        candidate: The candidate document under construction (mutated in place).
        var_name: The retuned variable.
        low: The new minimum, or None.
        high: The new maximum, or None.
    """
    if low is None and high is None:
        return
    for raw_node in cast("list[object]", candidate.get("nodes", [])):
        if not isinstance(raw_node, dict):
            continue
        node = cast("dict[str, object]", raw_node)
        for effect in _mutable_effects(node.get("on_enter")):
            _clamp_set_effect(effect, var_name, low, high)
        for raw_choice in cast("list[object]", node.get("choices", [])):
            if not isinstance(raw_choice, dict):
                continue
            choice = cast("dict[str, object]", raw_choice)
            for effect in _mutable_effects(choice.get("effects")):
                _clamp_set_effect(effect, var_name, low, high)
            condition = choice.get("condition")
            if isinstance(condition, dict):
                _clamp_condition_literals(
                    cast("dict[str, object]", condition), var_name, low, high
                )


def _mutable_effects(raw: object) -> list[dict[str, object]]:
    """Return an effect list's mutable dicts, or an empty list."""
    if not isinstance(raw, list):
        return []
    return [
        cast("dict[str, object]", item)
        for item in cast("list[object]", raw)
        if isinstance(item, dict)
    ]


def _clamp_set_effect(
    effect: dict[str, object], var_name: str, low: int | None, high: int | None
) -> None:
    """Clamp a ``set`` effect's int value into ``[low, high]`` when it targets the var."""
    if effect.get("var") != var_name or effect.get("op") != "set":
        return
    value = effect.get("value")
    if isinstance(value, int) and not isinstance(value, bool):
        effect["value"] = _clamp_int(value, low, high)


def _clamp_condition_literals(
    condition: dict[str, object], var_name: str, low: int | None, high: int | None
) -> None:
    """Clamp int literals compared against ``var_name`` into ``[low, high]``, in place."""
    operator, operand = next(iter(condition.items()))
    if operator == "!":
        if isinstance(operand, dict):
            _clamp_condition_literals(
                cast("dict[str, object]", operand), var_name, low, high
            )
        return
    if operator in {"and", "or"}:
        for clause in cast("list[object]", operand):
            if isinstance(clause, dict):
                _clamp_condition_literals(
                    cast("dict[str, object]", clause), var_name, low, high
                )
        return
    if operator in COMPARISON_OPERATORS and isinstance(operand, list):
        _clamp_comparison_pair(cast("list[object]", operand), var_name, low, high)


def _clamp_comparison_pair(
    pair: list[object], var_name: str, low: int | None, high: int | None
) -> None:
    """Clamp the int-literal side of a ``var``-vs-literal comparison, in place."""
    if len(pair) != 2:
        return
    literal_side = 1 if _names_var(pair[0], var_name) else 0
    var_side = 1 - literal_side
    if not _names_var(pair[var_side], var_name):
        return
    literal = pair[literal_side]
    if isinstance(literal, int) and not isinstance(literal, bool):
        pair[literal_side] = _clamp_int(literal, low, high)


def _names_var(operand: object, var_name: str) -> bool:
    """Return whether an operand is ``{"var": var_name}``."""
    return (
        isinstance(operand, dict)
        and cast("dict[str, object]", operand).get("var") == var_name
    )


def _rename_var_everywhere(
    candidate: dict[str, object], old: str, new: str
) -> None:
    """Rename a variable in its declaration and every effect/condition reference."""
    for raw_var in cast("list[object]", candidate.get("variables", [])):
        if isinstance(raw_var, dict):
            var = cast("dict[str, object]", raw_var)
            if var.get("name") == old:
                var["name"] = new
    for raw_node in cast("list[object]", candidate.get("nodes", [])):
        if isinstance(raw_node, dict):
            _rename_node_var_refs(cast("dict[str, object]", raw_node), old, new)


def _rename_node_var_refs(node: dict[str, object], old: str, new: str) -> None:
    """Rename a variable in one node's on_enter effects, choice effects, conditions."""
    for effect in _mutable_effects(node.get("on_enter")):
        if effect.get("var") == old:
            effect["var"] = new
    for raw_choice in cast("list[object]", node.get("choices", [])):
        if not isinstance(raw_choice, dict):
            continue
        choice = cast("dict[str, object]", raw_choice)
        for effect in _mutable_effects(choice.get("effects")):
            if effect.get("var") == old:
                effect["var"] = new
        condition = choice.get("condition")
        if isinstance(condition, dict):
            _rename_condition_var(cast("dict[str, object]", condition), old, new)


def _rename_condition_var(condition: dict[str, object], old: str, new: str) -> None:
    """Rename every ``{"var": old}`` reference in a condition tree, in place."""
    for _operator, operand in list(condition.items()):
        if isinstance(operand, dict):
            inner = cast("dict[str, object]", operand)
            if inner.get("var") == old:
                inner["var"] = new
            else:
                _rename_condition_var(inner, old, new)
        elif isinstance(operand, list):
            for item in cast("list[object]", operand):
                if isinstance(item, dict):
                    inner = cast("dict[str, object]", item)
                    if inner.get("var") == old:
                        inner["var"] = new
                    else:
                        _rename_condition_var(inner, old, new)


# ---------------------------------------------------------------------------
# The state signature (design 5.4) and its distance / floor
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StateSignature:
    """A deterministic, alpha-invariant feature vector over a story's state.

    Variable identity is abstracted to each variable's ``(type, initial, min,
    max)`` descriptor token, so a pure alpha-rename produces an identical
    signature (design 5.4). Conditions and effects are name-free (referenced via
    the descriptor token); effect placement keeps the structural node/choice id so
    a relocated effect changes the signature. Walk statistics come from the same
    ``WalkResult`` the acceptance harness ran.

    Attributes:
        var_descriptors: The sorted ``(type, initial, min, max)`` numeric tuples.
        conditions: The sorted name-free canonical condition strings.
        effects: The sorted ``(location, op, token, value, once)`` effect tuples.
        config_count: The number of reachable configurations.
        ending_config_counts: Per-ending-node config counts, sorted by node id.
        mean_visible_ratio: The mean fraction of a node's choices visible across
            non-ending configurations.
    """

    var_descriptors: tuple[tuple[int, int, int, int], ...]
    conditions: tuple[str, ...]
    effects: tuple[tuple[str, str, str, int, int], ...]
    config_count: int
    ending_config_counts: tuple[tuple[str, int], ...]
    mean_visible_ratio: float


def _bound_value(value: bool | int | None) -> int:
    """Return a bound as an int for the descriptor vector (None and bool normalized)."""
    if value is None:
        return 0
    return int(value)


def _var_descriptor_token(var: Variable) -> str:
    """Return a name-free descriptor token for a variable (alpha-invariant)."""
    return f"{var.type.value}|{int(var.initial)}|{_bound_value(var.min)}|{_bound_value(var.max)}"


def _var_token_map(story: Storybook) -> dict[str, str]:
    """Return a variable-name -> descriptor-token map (drops variable identity)."""
    return {var.name: _var_descriptor_token(var) for var in story.variables}


def _canonical_condition(
    condition: Mapping[str, object], token_map: Mapping[str, str]
) -> str:
    """Return a name-free canonical JSON form of a condition (literals kept)."""
    rewritten = _rewrite_condition_tokens(dict(condition), token_map)
    return json.dumps(rewritten, sort_keys=True, ensure_ascii=False)


def _rewrite_condition_tokens(
    condition: dict[str, object], token_map: Mapping[str, str]
) -> dict[str, object]:
    """Return a deep copy of a condition with var names replaced by tokens."""
    result: dict[str, object] = {}
    for operator, operand in condition.items():
        result[operator] = _rewrite_operand_tokens(operand, token_map)
    return result


def _rewrite_operand_tokens(operand: object, token_map: Mapping[str, str]) -> object:
    """Return an operand with any ``{"var": name}`` rewritten to its token."""
    if isinstance(operand, dict):
        inner = cast("dict[str, object]", operand)
        name = inner.get("var")
        if isinstance(name, str) and name in token_map:
            return {"var": token_map[name]}
        return _rewrite_condition_tokens(inner, token_map)
    if isinstance(operand, list):
        return [
            _rewrite_operand_tokens(item, token_map)
            for item in cast("list[object]", operand)
        ]
    return operand


def state_signature(story: Storybook, walk: WalkResult) -> StateSignature:
    """Return the state signature for a story, using a single ``WalkResult``.

    Args:
        story: The parsed, schema-valid Storybook.
        walk: The reachable-configuration closure (the same result the acceptance
            harness ran for the candidate; design 5.3/5.4 single-walk rule).

    Returns:
        StateSignature: The alpha-invariant feature vector.
    """
    token_map = _var_token_map(story)
    descriptors = sorted(
        (
            _type_ord(var),
            int(var.initial),
            _bound_value(var.min),
            _bound_value(var.max),
        )
        for var in story.variables
    )
    return StateSignature(
        var_descriptors=tuple(descriptors),
        conditions=tuple(sorted(_collect_conditions(story, token_map))),
        effects=tuple(sorted(_collect_effects(story, token_map))),
        config_count=len(walk.configs),
        ending_config_counts=_ending_config_counts(story, walk),
        mean_visible_ratio=_mean_visible_ratio(story, walk),
    )


def _collect_conditions(
    story: Storybook, token_map: Mapping[str, str]
) -> list[str]:
    """Return the name-free canonical condition strings over every choice condition."""
    return [
        _canonical_condition(choice.condition, token_map)
        for node in story.nodes
        for choice in node.choices
        if choice.condition is not None
    ]


def _collect_effects(
    story: Storybook, token_map: Mapping[str, str]
) -> list[tuple[str, str, str, int, int]]:
    """Return the name-free effect-placement tuples over on_enter and choice effects."""
    node_effects = [
        _effect_tuple(f"node:{node.id}", effect, token_map)
        for node in story.nodes
        for effect in node.on_enter
    ]
    choice_effects = [
        _effect_tuple(f"choice:{choice.id}", effect, token_map)
        for node in story.nodes
        for choice in node.choices
        for effect in choice.effects
    ]
    return node_effects + choice_effects


def _type_ord(var: Variable) -> int:
    """Return a stable integer ordinal for a variable's type (bool=0, int=1)."""
    return 0 if var.type.value == "bool" else 1


def _effect_tuple(
    location: str, effect: Effect, token_map: Mapping[str, str]
) -> tuple[str, str, str, int, int]:
    """Return a name-free ``(location, op, token, value, once)`` effect tuple."""
    token = token_map.get(effect.var, effect.var)
    value_int = int(effect.value) if isinstance(effect.value, (bool, int)) else 0
    return (location, effect.op.value, token, value_int, int(effect.once))


def _ending_config_counts(
    story: Storybook, walk: WalkResult
) -> tuple[tuple[str, int], ...]:
    """Return per-ending-node reachable-config counts, sorted by node id."""
    ending_ids = {node.id for node in story.nodes if node.is_ending}
    counts: Counter[str] = Counter()
    for key in walk.configs:
        node_id = key[0]
        if node_id in ending_ids:
            counts[node_id] += 1
    return tuple(sorted((node_id, counts.get(node_id, 0)) for node_id in ending_ids))


def _mean_visible_ratio(story: Storybook, walk: WalkResult) -> float:
    """Return the mean visible-choice ratio over non-ending configurations."""
    total_choices = {
        node.id: len(node.choices) for node in story.nodes if not node.is_ending
    }
    ratios: list[float] = []
    for key in walk.configs:
        node_id = key[0]
        denom = total_choices.get(node_id)
        if denom is None or denom == 0:
            continue
        visible = len(walk.edges.get(key, []))
        ratios.append(visible / denom)
    if not ratios:
        return 0.0
    return round(sum(ratios) / len(ratios), 6)


def state_distance(a: StateSignature, b: StateSignature) -> float:
    """Return a deterministic distance between two state signatures.

    The distance is additive over four terms: the L1 distance between aligned,
    sorted variable descriptors; the symmetric-difference size of the condition
    multiset; the symmetric-difference size of the effect-placement multiset; and
    a normalized walk-statistics term. It is zero exactly when the two signatures
    are identical (a no-op retune, a description-only edit, or an alpha-rename).

    Args:
        a: One signature.
        b: The other signature.

    Returns:
        float: The non-negative distance.
    """
    var_delta = _descriptor_l1(a.var_descriptors, b.var_descriptors)
    cond_delta = float(_multiset_symdiff(a.conditions, b.conditions))
    effect_delta = float(_multiset_symdiff(a.effects, b.effects))
    walk_delta = _walk_stat_delta(a, b)
    return var_delta + cond_delta + effect_delta + walk_delta


def _descriptor_l1(
    a: tuple[tuple[int, int, int, int], ...], b: tuple[tuple[int, int, int, int], ...]
) -> float:
    """Return the L1 distance between aligned, sorted variable descriptors.

    M5 never adds or removes a variable, so ``a`` and ``b`` have equal length; a
    length mismatch (a misuse) contributes a large fixed penalty rather than
    raising, keeping the distance total.
    """
    if len(a) != len(b):
        return float(10 * (abs(len(a) - len(b)) + 1))
    total = 0
    for left, right in zip(a, b, strict=True):
        total += sum(abs(x - y) for x, y in zip(left, right, strict=True))
    return float(total)


def _multiset_symdiff(a: tuple[object, ...], b: tuple[object, ...]) -> int:
    """Return the size of the symmetric difference of two multisets."""
    counter_a: Counter[object] = Counter(a)
    counter_b: Counter[object] = Counter(b)
    return sum((counter_a - counter_b).values()) + sum(
        (counter_b - counter_a).values()
    )


def _walk_stat_delta(a: StateSignature, b: StateSignature) -> float:
    """Return a normalized [0, ~3] walk-statistics distance term."""
    config_denom = max(1, a.config_count, b.config_count)
    config_term = abs(a.config_count - b.config_count) / config_denom
    ratio_term = abs(a.mean_visible_ratio - b.mean_visible_ratio)
    ending_map_a = dict(a.ending_config_counts)
    ending_map_b = dict(b.ending_config_counts)
    keys = set(ending_map_a) | set(ending_map_b)
    ending_l1 = sum(
        abs(ending_map_a.get(k, 0) - ending_map_b.get(k, 0)) for k in keys
    )
    ending_denom = max(1, sum(ending_map_a.values()), sum(ending_map_b.values()))
    ending_term = ending_l1 / ending_denom
    return config_term + ratio_term + ending_term


def state_signature_floor_reason(
    parent: Storybook, candidate: Storybook, candidate_walk: WalkResult
) -> str | None:
    """Return why an M5-only mutant fails the state-signature floor, or None.

    Reject-only (design 5.4/CR-2): a distance at or above the provisional
    ``_TAU_STATE`` returns None (the floor does not admit anything, it only
    rejects); a distance below it returns a reason. The candidate's walk
    statistics come from the single ``candidate_walk`` the harness already ran;
    the parent is walked once here.

    Args:
        parent: The parsed parent Storybook.
        candidate: The parsed candidate Storybook.
        candidate_walk: The candidate's reachable-configuration closure.

    Returns:
        str | None: A reason when the state distance is below ``_TAU_STATE``, else
            None.
    """
    # #CRITICAL: data-integrity: this is the anti-no-op floor for a state-only
    # mutant (design 5.4). It is reject-only: it can lower promotability (a
    # cosmetic retune, a description-only edit, or an alpha-rename is not a
    # distinct tree) but never raise it, so the provisional _TAU_STATE carries no
    # safety risk (design CR-2, floors reject-only). D7 calibrates _TAU_STATE.
    # #VERIFY: tests/unit/test_mutation_m5.py pins that a no-op / description-only
    # / alpha-rename mutant is below the floor and a real retune clears it.
    parent_walk = walk_configurations(parent)
    parent_sig = state_signature(parent, parent_walk)
    candidate_sig = state_signature(candidate, candidate_walk)
    distance = state_distance(parent_sig, candidate_sig)
    if distance < _TAU_STATE:
        provisional = " (PROVISIONAL; D7 calibrates)" if _TAU_STATE_IS_PROVISIONAL else ""
        return (
            f"state-signature distance {distance:.4f} is below the floor "
            f"_TAU_STATE {_TAU_STATE}{provisional}: an M5-only mutant this close to "
            f"its parent is a cosmetic no-op / alpha-rename, not a distinct tree"
        )
    return None


# ---------------------------------------------------------------------------
# The section 5.3 acceptance checks (ending coverage + clock re-proof)
# ---------------------------------------------------------------------------


def ending_coverage_gap(story: Storybook, walk: WalkResult) -> set[str]:
    """Return the ending node ids absent from the walk's reachable configurations.

    Design 5.3 check 1: every ``is_ending`` node id must appear in
    ``WalkResult.configs``; a retune that silently makes an ending
    config-unreachable (without tripping L2-11) is caught here.

    Args:
        story: The parsed candidate Storybook.
        walk: The single reachable-configuration closure the harness ran.

    Returns:
        set[str]: The ending node ids that never occur as a configuration's
            current node; empty when coverage is complete.
    """
    ending_ids = {node.id for node in story.nodes if node.is_ending}
    present = {key[0] for key in walk.configs}
    return ending_ids - present


def walk_fastest_satisfying_finish(story: Storybook, walk: WalkResult) -> int | None:
    """Return the fewest config-path nodes from the start to a satisfying finish.

    Design 5.3 check 2: the walk-derived fastest satisfying finish is the minimum
    node count on a configuration path from the initial configuration to any
    configuration at a ``success``/``completion`` node. Measured over the SAME
    ``WalkResult`` the gate's L2 consumed (single-walk rule).

    Args:
        story: The parsed candidate Storybook.
        walk: The single reachable-configuration closure the harness ran.

    Returns:
        int | None: The minimum config-path node count (hops + 1), or None when no
            satisfying finish is reachable in any configuration.
    """
    satisfying_nodes = {
        node.id
        for node in story.nodes
        if node.is_ending and node.ending is not None and node.ending.kind in _SATISFYING_KINDS
    }
    if not walk.configs:
        return None
    initial_key = next(iter(walk.configs))
    seen: set[ConfigKey] = {initial_key}
    queue: deque[tuple[ConfigKey, int]] = deque([(initial_key, 1)])
    while queue:
        key, nodes = queue.popleft()
        if key[0] in satisfying_nodes:
            return nodes
        for succ in walk.edges.get(key, []):
            if succ in walk.configs and succ not in seen:
                seen.add(succ)
                queue.append((succ, nodes + 1))
    return None


def clock_floor_for(story: Storybook) -> int | None:
    """Return the cell's ``min_complete_floor``, or None when it does not apply.

    The clock re-proof floor applies only to a scale-classified production story
    (one that declares a ``length`` on an offered cell), matching how PL-20 is
    scoped.

    Args:
        story: The parsed candidate Storybook.

    Returns:
        int | None: The ``min_complete_floor`` node count for the cell, or None.
    """
    meta = story.metadata
    if meta.length is None or not meta.production_eligible:
        return None
    return min_complete_floor(
        meta.age_band.value, meta.length.value, meta.narrative_style.value
    )


# ---------------------------------------------------------------------------
# The M5 operator
# ---------------------------------------------------------------------------


def _base_failures(parent: Mapping[str, object]) -> list[str]:
    """Return the parent-level (tier/band/series/production) precondition failures."""
    failures: list[str] = []
    meta = _metadata_of(parent)
    if recompute_tier(parent) != 2:
        failures.append(_M5_TIER2_ONLY_MSG)
    band = _str_field(meta, "age_band")
    if band is None or band not in _STATE_PERMITTED_BANDS:
        failures.append(_M5_BAND_MSG)
    if meta.get("series") is not None:
        failures.append(_M5_SERIES_MSG)
    if meta.get("production_eligible") is False:
        failures.append(_M5_PRODUCTION_ONLY_MSG)
    return failures


def _retune_failures(parent: Mapping[str, object], params: OpParams) -> list[str]:
    """Return M5a retune-specific precondition failures."""
    variable = params.get("variable")
    if not isinstance(variable, str):
        return [_M5_RETUNE_VAR_MSG]
    current = next(
        (v for v in _variables_of(parent) if _str_field(v, "name") == variable), None
    )
    if current is None:
        return [f"retune variable '{variable}' is not declared"]
    _new, reason = _prospective_variable(current, params)
    return [] if reason is None else [reason]


def _rename_failures(parent: Mapping[str, object], params: OpParams) -> list[str]:
    """Return M5a rename-specific precondition failures."""
    variable = params.get("variable")
    new_name = params.get("new_name")
    if not (isinstance(variable, str) and isinstance(new_name, str)):
        return [_M5_RENAME_MSG]
    names = _variable_names(parent)
    if variable not in names:
        return [f"rename source '{variable}' is not a declared variable"]
    if not _is_var_name(new_name):
        return [_M5_RENAME_MSG]
    if new_name == variable:
        return ["rename new_name equals the current name (a no-op)"]
    if new_name in names:
        return [f"rename new_name '{new_name}' is already a declared variable"]
    return []


def _is_var_name(name: str) -> bool:
    """Return whether a name matches the story-variable pattern."""
    if not name or not name[0].islower() or not name[0].isalpha():
        return False
    return all(ch.islower() or ch.isdigit() or ch == "_" for ch in name)


def _gate_choice_failures(parent: Mapping[str, object], params: OpParams) -> list[str]:
    """Return M5b gate-choice-specific precondition failures."""
    choice_id = params.get("choice")
    if not isinstance(choice_id, str):
        return [_M5_GATE_MSG]
    ref = _choice_ref(parent, choice_id)
    if ref is None:
        return [f"gate-choice target '{choice_id}' is not a choice in this story"]
    node_id, choice = ref
    if choice.get("condition") is not None:
        return [f"choice '{choice_id}' already carries a condition"]
    _condition, reason = _assemble_condition(
        parent, params.get("gate_var"), params.get("gate_op"), params.get("gate_value")
    )
    if reason is not None:
        return [reason]
    return _stranding_precondition(parent, node_id, choice_id, params)


def _stranding_precondition(
    parent: Mapping[str, object], node_id: str, choice_id: str, params: OpParams
) -> list[str]:
    """Return the cheap stranding precondition for gating a choice (design 5.2).

    Require either a sibling choice at that node that remains unconditioned, or an
    operator-supplied ``justification`` argument. The walk is the authority
    (L2-9/L2-10 prove non-stranding at the gate); this only avoids burning walk
    time on an obvious dead-end.
    """
    # #ASSUME: security: gating a node's only unconditioned exit can strand a
    # configuration with zero visible choices. The cheap precondition requires a
    # surviving unconditioned sibling OR an explicit justification; the gate's
    # L2-9/L2-10 over the configuration walk is the authority that actually proves
    # no reader is trapped (design 5.2, "the walk is the authority").
    # #VERIFY: tests/unit/test_mutation_m5.py pins that gating a lone-exit choice
    # is refused at preconditions, and that a gate-choice which strands a config is
    # discarded at the gate (L2-9).
    node = _node_by_id(parent, node_id)
    if node is None:
        return [f"gate-choice node '{node_id}' vanished"]
    has_uncond_sibling = any(
        _str_field(sibling, "id") != choice_id and sibling.get("condition") is None
        for sibling in _choices_of(node)
    )
    if has_uncond_sibling or params.get("justification") is not None:
        return []
    reason = (
        f"gating '{choice_id}' would leave node '{node_id}' with no unconditioned"
        f" sibling; supply a 'justification' argument if every reachable var-state"
        f" still satisfies a sibling"
    )
    return [reason]


def _add_route_failures(parent: Mapping[str, object], params: OpParams) -> list[str]:
    """Return M5b add-route-specific precondition failures."""
    host = params.get("host")
    target = params.get("target")
    if not (isinstance(host, str) and isinstance(target, str)):
        return [_M5_ADD_ROUTE_MSG]
    host_node = _node_by_id(parent, host)
    if host_node is None or host_node.get("is_ending") is True:
        return [f"add-route host '{host}' is not a decision node"]
    if target not in node_ids(parent):
        return [f"add-route target '{target}' is not a node in this story"]
    if len(_choices_of(host_node)) >= _MAX_CHOICES_PER_DECISION:
        cap_reason = (
            f"add-route would push node '{host}' past the"
            f" {_MAX_CHOICES_PER_DECISION}-choice cap"
        )
        return [cap_reason]
    _condition, reason = _assemble_condition(
        parent, params.get("gate_var"), params.get("gate_op"), params.get("gate_value")
    )
    if reason is not None:
        return [reason]
    cycle_reason = _add_route_cycle_reason(parent, host, target)
    return [] if cycle_reason is None else [cycle_reason]


def _add_route_cycle_reason(
    parent: Mapping[str, object], host: str, target: str
) -> str | None:
    """Return why an add-route edge would close a cycle on an acyclic parent, or None.

    An ``open_map``/``loop_and_grow`` parent already carries back-edges (the band's
    loop allowance is the precondition), so a back-edge target is legal there; only
    an acyclic parent must stay acyclic (design 5.2, matching M4's reconvergence
    guard).
    """
    graph = _choice_graph(parent)
    if not nx.is_directed_acyclic_graph(graph):
        return None
    graph.add_edge(host, target)
    if nx.is_directed_acyclic_graph(graph):
        return None
    return (
        f"add-route edge '{host}' -> '{target}' would create a cycle in an "
        f"otherwise acyclic story"
    )


def _relocate_failures(parent: Mapping[str, object], params: OpParams) -> list[str]:
    """Return M5b relocate-effect-specific precondition failures."""
    from_node = params.get("from_node")
    to_node = params.get("to_node")
    if not (isinstance(from_node, str) and isinstance(to_node, str)):
        return [_M5_RELOCATE_MSG]
    source = _node_by_id(parent, from_node)
    dest = _node_by_id(parent, to_node)
    if source is None:
        return [f"relocate-effect from_node '{from_node}' is not a node"]
    if dest is None or dest.get("is_ending") is True:
        return [f"relocate-effect to_node '{to_node}' is not a non-ending node"]
    if from_node == to_node:
        return ["relocate-effect from_node and to_node are the same node (a no-op)"]
    index = _effect_index(params)
    effects = _effects_of(source)
    if index < 0 or index >= len(effects):
        range_reason = (
            f"relocate-effect index {index} is out of range for node '{from_node}'"
            f" ({len(effects)} on_enter effect(s))"
        )
        return [range_reason]
    return []


def _effect_index(params: OpParams) -> int:
    """Return the relocate-effect ``effect_index`` param (default 0)."""
    value = params.get("effect_index")
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _choice_graph(story: Mapping[str, object]) -> nx.DiGraph[str]:
    """Build the directed choice graph over the story's node ids."""
    graph: nx.DiGraph[str] = nx.DiGraph()
    graph.add_nodes_from(node_ids(story))
    for source, targets in adjacency(story).items():
        for target in targets:
            graph.add_edge(source, target)
    return graph


def _apply_retune(parent: Mapping[str, object], params: OpParams) -> MutationResult:
    """Apply an M5a retune and return the resynced candidate plus its re-guidance."""
    variable = cast("str", params.get("variable"))
    current = next(
        v for v in _variables_of(parent) if _str_field(v, "name") == variable
    )
    new_decl, reason = _prospective_variable(current, params)
    if new_decl is None:
        msg = f"M5 retune of '{variable}' is ineligible: {reason}"
        raise ValidationError(msg, field="variable", value=variable)
    candidate = copy.deepcopy(dict(parent))
    for raw_var in cast("list[object]", candidate.get("variables", [])):
        if isinstance(raw_var, dict):
            var_dict = cast("dict[str, object]", raw_var)
            if var_dict.get("name") == variable:
                var_dict.clear()
                var_dict.update(new_decl)
    low = _int_or_bound(new_decl.get("min"))
    high = _int_or_bound(new_decl.get("max"))
    _clamp_literals_for_var(candidate, variable, low, high)
    resynced = resync_metadata(candidate)
    _assert_endings_untouched(parent, resynced)
    reason_text = "variable retuned; re-check the beats that narrate its new semantic"
    reguide = _reguide_nodes_for_var(parent, variable, reason_text)
    note = f"M5 retune: variable '{variable}' -> {json.dumps(new_decl, sort_keys=True)}"
    return MutationResult(candidate=resynced, reguide=reguide, notes=(note,))


def _int_or_bound(value: object) -> int | None:
    """Return an int bound value, or None (bool and non-int normalized to None)."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _apply_rename(parent: Mapping[str, object], params: OpParams) -> MutationResult:
    """Apply an M5a alpha-rename and return the resynced candidate plus re-guidance."""
    old = cast("str", params.get("variable"))
    new = cast("str", params.get("new_name"))
    candidate = copy.deepcopy(dict(parent))
    _rename_var_everywhere(candidate, old, new)
    resynced = resync_metadata(candidate)
    _assert_endings_untouched(parent, resynced)
    reason_text = (
        "variable alpha-renamed; re-check the beats that narrate it for honesty"
    )
    reguide = _reguide_nodes_for_var(parent, old, reason_text)
    note = f"M5 rename: variable '{old}' -> '{new}' (pure alpha-rename)"
    return MutationResult(candidate=resynced, reguide=reguide, notes=(note,))


def _apply_gate_choice(
    parent: Mapping[str, object], params: OpParams
) -> MutationResult:
    """Apply an M5b gate-choice and return the resynced candidate plus re-guidance."""
    choice_id = cast("str", params.get("choice"))
    condition, reason = _assemble_condition(
        parent, params.get("gate_var"), params.get("gate_op"), params.get("gate_value")
    )
    if condition is None:
        msg = f"M5 gate-choice on '{choice_id}' is ineligible: {reason}"
        raise ValidationError(msg, field="choice", value=choice_id)
    candidate = copy.deepcopy(dict(parent))
    node_id, label = _set_choice_condition(candidate, choice_id, condition)
    resynced = resync_metadata(candidate)
    _assert_endings_untouched(parent, resynced)
    reguide = (
        ReguideItem(
            target=ReguideTarget.CHOICE,
            target_id=choice_id,
            reason="choice is now condition-gated; re-check its label",
            current_text=label,
        ),
        ReguideItem(
            target=ReguideTarget.NODE,
            target_id=node_id,
            reason="a choice here is now gated; re-check the node's beats",
            current_text=_node_body(parent, node_id),
        ),
    )
    note = f"M5 gate-choice: gated '{choice_id}' with {json.dumps(condition)}"
    return MutationResult(candidate=resynced, reguide=reguide, notes=(note,))


def _set_choice_condition(
    candidate: dict[str, object], choice_id: str, condition: dict[str, object]
) -> tuple[str, str]:
    """Set a choice's condition in place and return its node id and label."""
    for raw_node in cast("list[object]", candidate.get("nodes", [])):
        if not isinstance(raw_node, dict):
            continue
        node = cast("dict[str, object]", raw_node)
        node_id = node.get("id")
        for raw_choice in cast("list[object]", node.get("choices", [])):
            if not isinstance(raw_choice, dict):
                continue
            choice = cast("dict[str, object]", raw_choice)
            if choice.get("id") == choice_id:
                choice["condition"] = condition
                label = choice.get("label")
                return (
                    node_id if isinstance(node_id, str) else "",
                    label if isinstance(label, str) else "",
                )
    msg = f"gate-choice target '{choice_id}' vanished during apply"
    raise ValidationError(msg, field="choice", value=choice_id)


def _apply_add_route(
    parent: Mapping[str, object], params: OpParams
) -> MutationResult:
    """Apply an M5b add-route and return the resynced candidate plus re-guidance."""
    host = cast("str", params.get("host"))
    target = cast("str", params.get("target"))
    condition, reason = _assemble_condition(
        parent, params.get("gate_var"), params.get("gate_op"), params.get("gate_value")
    )
    if condition is None:
        msg = f"M5 add-route on '{host}' is ineligible: {reason}"
        raise ValidationError(msg, field="host", value=host)
    candidate = copy.deepcopy(dict(parent))
    new_choice_id = _mint_choice_id(parent, host)
    _append_choice(candidate, host, new_choice_id, target, condition)
    resynced = resync_metadata(candidate)
    _assert_endings_untouched(parent, resynced)
    reguide = (
        ReguideItem(
            target=ReguideTarget.CHOICE,
            target_id=new_choice_id,
            reason="new gated route (a shortcut / secret door); author its label",
            current_text="",
        ),
        ReguideItem(
            target=ReguideTarget.NODE,
            target_id=host,
            reason="a new gated route was added here; re-check the node's beats",
            current_text=_node_body(parent, host),
        ),
        ReguideItem(
            target=ReguideTarget.NODE,
            target_id=target,
            reason="this node now has a new gated approach; re-check its beats",
            current_text=_node_body(parent, target),
        ),
    )
    note = (
        f"M5 add-route: gated '{new_choice_id}' on '{host}' -> '{target}' with "
        f"{json.dumps(condition)}"
    )
    return MutationResult(candidate=resynced, reguide=reguide, notes=(note,))


def _mint_choice_id(parent: Mapping[str, object], host: str) -> str:
    """Return a fresh, collision-free choice id for a new route on ``host``."""
    existing = {
        choice_id
        for node in _nodes_of(parent)
        for choice in _choices_of(node)
        if (choice_id := _str_field(choice, "id")) is not None
    }
    k = 1
    while f"c_{host}_m5_{k}" in existing:
        k += 1
    return f"c_{host}_m5_{k}"


def _append_choice(  # noqa: PLR0913 -- the fields one new gated choice needs
    candidate: dict[str, object],
    host: str,
    choice_id: str,
    target: str,
    condition: dict[str, object],
) -> None:
    """Append a condition-gated choice to a host node's choice list, in place."""
    for raw_node in cast("list[object]", candidate.get("nodes", [])):
        if not isinstance(raw_node, dict):
            continue
        node = cast("dict[str, object]", raw_node)
        if node.get("id") != host:
            continue
        choices = node.get("choices")
        if not isinstance(choices, list):
            choices = []
            node["choices"] = choices
        new_choice: dict[str, object] = {
            "id": choice_id,
            "label": "(new gated route: re-author this choice label)",
            "target": target,
            "condition": condition,
        }
        cast("list[object]", choices).append(new_choice)
        return
    msg = f"add-route host '{host}' vanished during apply"
    raise ValidationError(msg, field="host", value=host)


def _apply_relocate(
    parent: Mapping[str, object], params: OpParams
) -> MutationResult:
    """Apply an M5b relocate-effect and return the resynced candidate plus re-guidance."""
    from_node = cast("str", params.get("from_node"))
    to_node = cast("str", params.get("to_node"))
    index = _effect_index(params)
    candidate = copy.deepcopy(dict(parent))
    moved = _move_on_enter_effect(candidate, from_node, to_node, index)
    resynced = resync_metadata(candidate)
    _assert_endings_untouched(parent, resynced)
    reguide = (
        ReguideItem(
            target=ReguideTarget.NODE,
            target_id=from_node,
            reason="an on_enter effect moved away from here; re-check the beats",
            current_text=_node_body(parent, from_node),
        ),
        ReguideItem(
            target=ReguideTarget.NODE,
            target_id=to_node,
            reason="an on_enter effect now fires here; re-check the beats",
            current_text=_node_body(parent, to_node),
        ),
    )
    note = (
        f"M5 relocate-effect: moved on_enter effect {json.dumps(moved, sort_keys=True)}"
        f" from '{from_node}' to '{to_node}'"
    )
    return MutationResult(candidate=resynced, reguide=reguide, notes=(note,))


def _move_on_enter_effect(
    candidate: dict[str, object], from_node: str, to_node: str, index: int
) -> dict[str, object]:
    """Move one on_enter effect between nodes in place; return the moved effect.

    Raises:
        ValidationError: If the source effect or the destination node vanished.
    """
    moved: dict[str, object] | None = None
    for raw_node in cast("list[object]", candidate.get("nodes", [])):
        if not isinstance(raw_node, dict):
            continue
        node = cast("dict[str, object]", raw_node)
        if node.get("id") == from_node:
            effects = _mutable_effects(node.get("on_enter"))
            if 0 <= index < len(effects):
                moved = effects[index]
                # Rebuild the list without the moved effect, preserving order.
                node["on_enter"] = [e for i, e in enumerate(effects) if i != index]
    if moved is None:
        msg = f"relocate-effect source at '{from_node}'[{index}] vanished during apply"
        raise ValidationError(msg, field="from_node", value=from_node)
    for raw_node in cast("list[object]", candidate.get("nodes", [])):
        if not isinstance(raw_node, dict):
            continue
        node = cast("dict[str, object]", raw_node)
        if node.get("id") == to_node:
            dest = node.get("on_enter")
            if not isinstance(dest, list):
                dest = []
                node["on_enter"] = dest
            cast("list[object]", dest).append(copy.deepcopy(moved))
            return moved
    msg = f"relocate-effect destination '{to_node}' vanished during apply"
    raise ValidationError(msg, field="to_node", value=to_node)


class M5StateVariation:
    """M5: vary a Tier-2 tree's state without touching its endings (design 5).

    One operator, five sub-operations selected by the ``mode`` parameter, matching
    the single-op-per-op-id shape M1-M4 use:

    - ``retune`` (M5a): change a declared variable's ``initial``/``min``/``max``
      and ``description`` within its type, clamping now-out-of-range int literals
      in conditions and ``set`` effects that reference it.
    - ``rename`` (M5a): pure alpha-rename of a variable and every reference in one
      pass (semantically free; exists so a retuned description reads honestly).
    - ``gate-choice`` (M5b): add a condition to a currently unconditioned choice.
    - ``add-route`` (M5b): add a condition-gated choice on a decision node (within
      the 2-3 cap) targeting an existing node (a shortcut / secret door); a
      back-edge is legal on an ``open_map``/``loop_and_grow`` parent.
    - ``relocate-effect`` (M5b): move an ``on_enter`` effect to a different node,
      preserving its ``op``/``var``/``value``/``once``.

    M5 requires ``recompute_tier(parent) == 2`` and a band whose ADR-011 section 7
    row permits stateful loops (8-11 and up). It never touches an ending kind,
    valence, or the ending multiset (asserted after every apply), so PL-15/16/17
    are untouched by construction. The dead/trap-state obligation each M5b move can
    create is proven by the unchanged gate's Layer 2 over the configuration walk
    (L2-9..L2-12); the operator does only cheap preconditions.

    M5 is parameter-driven and needs no rng: a given ``(parent, params)`` yields a
    byte-identical candidate, so the injected seed is recorded for lineage but
    unused.
    """

    op_id: str = M5_OP_ID

    def preconditions(
        self, parent: Mapping[str, object], params: OpParams
    ) -> PreconditionReport:
        """Return whether M5 may attempt a mutation on ``parent`` (design 5).

        Args:
            parent: The raw parent story document.
            params: The operator parameters (``mode`` plus mode-specific ids).

        Returns:
            PreconditionReport: Satisfied when eligible, else the failing reasons.
        """
        failures = list(_base_failures(parent))
        mode = params.get("mode")
        if mode == _M5_MODE_RETUNE:
            failures.extend(_retune_failures(parent, params))
        elif mode == _M5_MODE_RENAME:
            failures.extend(_rename_failures(parent, params))
        elif mode == _M5_MODE_GATE_CHOICE:
            failures.extend(_gate_choice_failures(parent, params))
        elif mode == _M5_MODE_ADD_ROUTE:
            failures.extend(_add_route_failures(parent, params))
        elif mode == _M5_MODE_RELOCATE:
            failures.extend(_relocate_failures(parent, params))
        else:
            failures.append(_M5_MODE_MSG)
        if failures:
            return PreconditionReport.failed(*failures)
        return PreconditionReport.passed()

    def apply(
        self, parent: Mapping[str, object], params: OpParams, rng: random.Random
    ) -> MutationResult:
        """Apply the selected sub-operation and return the resynced candidate.

        Args:
            parent: The raw parent story document (never mutated).
            params: The operator parameters (``mode`` plus mode-specific ids).
            rng: The injected random source; unused, because M5 is fully
                parameter-driven (recorded for lineage replay parity).

        Returns:
            MutationResult: The candidate (metadata resynced, endings untouched)
                plus re-guidance.

        Raises:
            ValidationError: If the mode is unknown or the selected mutation is
                ineligible.
        """
        _ = rng
        mode = params.get("mode")
        if mode == _M5_MODE_RETUNE:
            return _apply_retune(parent, params)
        if mode == _M5_MODE_RENAME:
            return _apply_rename(parent, params)
        if mode == _M5_MODE_GATE_CHOICE:
            return _apply_gate_choice(parent, params)
        if mode == _M5_MODE_ADD_ROUTE:
            return _apply_add_route(parent, params)
        if mode == _M5_MODE_RELOCATE:
            return _apply_relocate(parent, params)
        raise ValidationError(_M5_MODE_MSG, field="mode", value=mode)


# Register the singleton M5 operator in the default catalog registry alongside
# M1-M4. Import of this module is the registration side effect the CLI relies on.
M5 = REGISTRY.register(M5StateVariation())
