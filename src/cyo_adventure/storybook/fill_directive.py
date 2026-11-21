# pyright: reportImplicitStringConcatenation=false
# Ruff ISC003 requires implicit concatenation for wrapped messages and this
# BasedPyright rule forbids it; the two conflict, and Ruff is the project's gate.
"""FILL directive grammars, version 1 and the typed version 2 (WP-2.2).

A skeleton node body is a ``<<FILL ...>>`` directive the fill step replaces
with prose. Two grammars exist:

- **Version 1**, ``<<FILL role=<role> words=<n> beats='<free text>'>>``. Every
  committed skeleton under ``skeletons/`` uses it and keeps using it: the
  skeleton-fill pipeline as built quotes the beats to the fill model, and ADR-033
  Decision 5 keeps that path selectable until the plan-first pilot shows it is
  not worse.
- **Version 2**, ``<<FILL v=2 role=<role> words=<n> function=<function>>>``
  (ADR-033 Decision 4). A shape authors only the role, the word budget and the
  node's graph function; the event comes from the book's Story Plan and the
  per-scene instruction from the directive compiler (WP-2.5). There is no
  ``beats`` field and no free text, so a shape carries no story content.

``function`` is a closed vocabulary (:data:`NODE_FUNCTIONS`) and is not a free
choice: it is the node's structural function in the graph, derived by
:func:`derive_node_functions`, and ``scripts/check_skeleton.py`` fails a v2
directive whose function disagrees with the derivation. The words in the
vocabulary are the ones the hand-written WP-0.3 plans already used for
``nodes.<id>.function``, minus ``payoff``: a payoff is where a plan's thread
returns, which is per-book meaning (D4 item 3: state comes from plan threads),
not a property of the frozen shape.

This module imports nothing but the standard library and
:mod:`cyo_adventure.core.exceptions` on purpose. ``generation/skeleton.py`` is
contractually free of the database chain (its import probe test) and
:mod:`cyo_adventure.storybook.slotted_surfaces` is not (it reaches
``validator.slots``), so the grammar lives here and both modules import it.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, cast, get_args

from cyo_adventure.core.exceptions import ValidationError

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

__all__ = [
    "FILL_DIRECTIVE_RE",
    "FILL_V2_DIRECTIVE_RE",
    "FILL_V2_MARKER",
    "FILL_VERSION_RE",
    "NODE_FUNCTIONS",
    "FillDirectiveV2",
    "NodeFunction",
    "convert_to_v2",
    "derive_node_functions",
    "directive_version",
    "has_v2_directives",
    "parse_fill_v2",
    "v2_directive_violations",
]

# The production FILL directive parse, version 1. Re-exported unchanged by
# :mod:`cyo_adventure.storybook.slotted_surfaces`, which owned it first and where
# every v1 consumer imports it from. DOTALL so a beats segment containing a
# newline still matches as one group.
FILL_DIRECTIVE_RE = re.compile(
    r"^<<FILL role=(\w+) words=(\d+) beats='(.*)'>>$", re.DOTALL
)

# The typed version-2 directive: exactly these four fields, in this order,
# single-space separated, nothing else. No DOTALL and an anchored ``\Z``, so a
# trailing newline or any text after ``>>`` fails the match. That strictness is
# the whole of "a v2 directive carries no free text".
FILL_V2_DIRECTIVE_RE = re.compile(
    r"^<<FILL v=2 role=(?P<role>[a-z][a-z0-9_]*) words=(?P<words>[1-9][0-9]*) "
    r"function=(?P<function>[a-z]+)>>\Z"
)

# A body that claims a directive version at all. Separates a malformed v2
# directive (claims ``v=2`` and fails the grammar) from a v1 directive (no
# ``v=`` field) and from prose.
FILL_VERSION_RE = re.compile(r"^<<FILL v=(?P<version>\S*)")

# The prefix every version-2 directive starts with; a cheap membership probe for
# consumers that only need to know whether a document holds v2 bodies.
FILL_V2_MARKER: Final[str] = "<<FILL v=2 "

NodeFunction = Literal["opening", "decision", "continue", "merge", "ending"]

# In precedence order: a node takes the first function that applies.
NODE_FUNCTIONS: Final[tuple[NodeFunction, ...]] = get_args(NodeFunction)


@dataclass(frozen=True, slots=True)
class FillDirectiveV2:
    """One parsed version-2 directive.

    Attributes:
        role: The narrative role token carried over from version 1.
        words: The word budget, a positive integer.
        function: The node's graph function.
    """

    role: str
    words: int
    function: NodeFunction

    def render(self) -> str:
        """Return the canonical directive text.

        Returns:
            str: ``<<FILL v=2 role=... words=... function=...>>``.
        """
        return (
            f"<<FILL v=2 role={self.role} words={self.words} function={self.function}>>"
        )


def parse_fill_v2(body: str) -> FillDirectiveV2 | None:
    """Parse a version-2 directive, or return None when ``body`` is not one.

    Args:
        body: A node body.

    Returns:
        FillDirectiveV2 | None: The parsed directive, or None when the body is
            not a well-formed v2 directive (free text, a missing or reordered
            field, or a function outside :data:`NODE_FUNCTIONS` all give None).
    """
    match = FILL_V2_DIRECTIVE_RE.match(body)
    if match is None:
        return None
    function = match.group("function")
    if function not in NODE_FUNCTIONS:
        return None
    return FillDirectiveV2(
        role=match.group("role"),
        words=int(match.group("words")),
        function=function,
    )


def directive_version(body: str) -> int | None:
    """Return which FILL grammar a body is written in.

    Args:
        body: A node body.

    Returns:
        int | None: ``2`` for any body that claims ``v=2`` (well-formed or
            not, so a malformed v2 directive is reported as one rather than as
            prose), ``1`` for a well-formed v1 directive, ``0`` for a body that
            claims some other ``v=`` value, and None for anything else (prose,
            or a malformed v1 directive).
    """
    claimed = FILL_VERSION_RE.match(body)
    if claimed is not None:
        return 2 if claimed.group("version") == "2" else 0
    if FILL_DIRECTIVE_RE.match(body) is not None:
        return 1
    return None


def _nodes(story: Mapping[str, object]) -> Iterator[Mapping[str, object]]:
    """Yield the story's node mappings, skipping malformed entries.

    Args:
        story: Decoded skeleton or book JSON.

    Yields:
        Mapping[str, object]: Each node that is a JSON object.
    """
    raw = story.get("nodes")
    if not isinstance(raw, list):
        return
    for node in cast("list[object]", raw):
        if isinstance(node, dict):
            yield cast("dict[str, object]", node)


def _choice_targets(node: Mapping[str, object]) -> list[str]:
    """Return the targets of a node's choices, skipping malformed choices.

    Args:
        node: One node mapping.

    Returns:
        list[str]: The ``target`` of each well-formed choice, in order.
    """
    raw = node.get("choices")
    if not isinstance(raw, list):
        return []
    targets: list[str] = []
    for choice in cast("list[object]", raw):
        if isinstance(choice, dict):
            target = cast("dict[str, object]", choice).get("target")
            if isinstance(target, str):
                targets.append(target)
    return targets


def _is_ending(node: Mapping[str, object]) -> bool:
    """Return whether a raw node is an ending.

    Args:
        node: One node mapping.

    Returns:
        bool: True when ``is_ending`` is true or an ``ending`` block is present.
    """
    return node.get("is_ending") is True or isinstance(node.get("ending"), dict)


def _inbound_sources(story: Mapping[str, object]) -> dict[str, set[str]]:
    """Map each node id to the distinct other nodes with a choice targeting it.

    Args:
        story: Decoded skeleton or book JSON.

    Returns:
        dict[str, set[str]]: Target id to source ids; a self-loop is not counted.
    """
    inbound: dict[str, set[str]] = {}
    for node in _nodes(story):
        source = node.get("id")
        if not isinstance(source, str):
            continue
        for target in _choice_targets(node):
            if target != source:
                inbound.setdefault(target, set()).add(source)
    return inbound


def derive_node_functions(story: Mapping[str, object]) -> dict[str, NodeFunction]:
    """Return each node's graph function, the value a v2 directive must carry.

    Precedence, first match wins: the start node is ``opening``; an ending node
    is ``ending``; a node reached from two or more distinct nodes (self-loops
    not counted, the same definition as
    :func:`cyo_adventure.validator.agency.inbound_sources`) is ``merge``; a node
    with two or more choices is ``decision``; anything else is ``continue``.
    A merge that is also a decision stays ``merge`` because the merge is the
    harder obligation for the compiler (entry-guaranteed facts, no route
    narration) and the choice count is in the graph anyway.

    Args:
        story: Decoded skeleton or book JSON. Reads ids, choice targets, the
            start node and the ending markers only.

    Returns:
        dict[str, NodeFunction]: Node id to function, for every node with a
            string id, in document order.
    """
    inbound = _inbound_sources(story)
    start = story.get("start_node")
    functions: dict[str, NodeFunction] = {}
    for node in _nodes(story):
        node_id = node.get("id")
        if not isinstance(node_id, str):
            continue
        if node_id == start:
            functions[node_id] = "opening"
        elif _is_ending(node):
            functions[node_id] = "ending"
        elif len(inbound.get(node_id, ())) >= 2:
            functions[node_id] = "merge"
        elif len(_choice_targets(node)) >= 2:
            functions[node_id] = "decision"
        else:
            functions[node_id] = "continue"
    return functions


def has_v2_directives(story: Mapping[str, object]) -> bool:
    """Return whether any node body claims the version-2 grammar.

    Args:
        story: Decoded skeleton or book JSON.

    Returns:
        bool: True when at least one node body starts with ``<<FILL v=2``,
            well-formed or not.
    """
    for node in _nodes(story):
        body = node.get("body")
        if isinstance(body, str) and directive_version(body) == 2:
            return True
    return False


def _v2_body_violation(
    node_id: str, body: str, expected: NodeFunction | None
) -> str | None:
    """Return the violation for one body that claims ``v=2``, or None.

    Args:
        node_id: The node's id, for the message.
        body: The node body, which starts with ``<<FILL v=2``.
        expected: The derived graph function, or None when unknown.

    Returns:
        str | None: One human-readable violation, or None when well-formed and
            consistent with the graph.
    """
    match = FILL_V2_DIRECTIVE_RE.match(body)
    if match is None:
        if "beats=" in body or "'" in body or '"' in body:
            reason = "carries free text (a beats field or quoted text)"
        else:
            reason = (
                "is malformed or carries free text; the only form is "
                "<<FILL v=2 role=<role> words=<n> function=<function>>>"
            )
        return f"node {node_id!r}: v2 directive {reason}: {body[:120]!r}"
    function = match.group("function")
    if function not in NODE_FUNCTIONS:
        return (
            f"node {node_id!r}: v2 directive function {function!r} is not one of "
            f"{', '.join(NODE_FUNCTIONS)}"
        )
    if expected is not None and function != expected:
        return (
            f"node {node_id!r}: v2 directive says function={function} but the "
            f"graph makes it {expected}"
        )
    return None


def v2_directive_violations(story: Mapping[str, object]) -> list[str]:
    """Return every v2 grammar violation in a skeleton; empty when clean.

    A document with no v2 directive returns nothing, so every v1 skeleton is
    untouched by this check. Once any body claims ``v=2`` the document is a
    shape and is held to all of: every ``v=2`` body matches the strict grammar
    (no beats, no free text, nothing after ``>>``); its ``function`` is in the
    vocabulary and equals :func:`derive_node_functions`; no body claims an
    unknown version; and no v1 directive remains, because the compiler renders
    every scene of a shape from the plan and a half-converted shell would give
    some scenes beats and others not.

    Args:
        story: Decoded skeleton JSON.

    Returns:
        list[str]: Human-readable violations, in node order.
    """
    if not has_v2_directives(story):
        return []
    functions = derive_node_functions(story)
    violations: list[str] = []
    for node in _nodes(story):
        node_id = str(node.get("id"))
        body = node.get("body")
        if not isinstance(body, str):
            continue
        version = directive_version(body)
        if version == 2:
            found = _v2_body_violation(node_id, body, functions.get(node_id))
            if found is not None:
                violations.append(found)
        elif version == 1:
            violations.append(
                f"node {node_id!r}: v1 directive in a v2 shape; convert every "
                "directive or none"
            )
        elif version == 0:
            violations.append(
                f"node {node_id!r}: unknown directive version: {body[:60]!r}"
            )
        elif "<<FILL" in body:
            violations.append(
                f"node {node_id!r}: malformed FILL directive in a v2 shape: "
                f"{body[:60]!r}"
            )
    return violations


def convert_to_v2(story: Mapping[str, object]) -> dict[str, object]:
    """Return a deep copy of a v1 skeleton with every directive rewritten to v2.

    Each ``<<FILL role=R words=N beats='...'>>`` becomes
    ``<<FILL v=2 role=R words=N function=F>>`` with ``F`` from
    :func:`derive_node_functions`. The beats are dropped. Nothing else in the
    document changes: ids, choices, labels, targets, conditions, effects,
    variables, endings, title and metadata are copied as they are, so
    :func:`cyo_adventure.storyplan.models.shape_hash` is unchanged by
    construction (it never reads a body).

    Args:
        story: Decoded v1 skeleton JSON.

    Returns:
        dict[str, object]: The converted copy.

    Raises:
        ValidationError: If any node body is not a well-formed v1 directive. A
            prose body or a malformed directive has no role and budget to keep,
            and inventing one is not conversion.
    """
    converted = copy.deepcopy(dict(story))
    functions = derive_node_functions(converted)
    for node in _nodes(converted):
        node_id = node.get("id")
        body = node.get("body")
        match = FILL_DIRECTIVE_RE.match(body) if isinstance(body, str) else None
        if not isinstance(node_id, str) or match is None:
            msg = (
                f"node {node_id!r} has no v1 FILL directive to convert; a shape "
                "is converted only from a skeleton whose every body is one"
            )
            raise ValidationError(msg, field="body", value=node_id)
        directive = FillDirectiveV2(
            role=match.group(1), words=int(match.group(2)), function=functions[node_id]
        )
        rendered = directive.render()
        if parse_fill_v2(rendered) != directive:
            msg = (
                f"node {node_id!r}: role {directive.role!r} or words "
                f"{directive.words} cannot be written in the v2 grammar "
                "(role must be lower-case, words a positive integer)"
            )
            raise ValidationError(msg, field="body", value=node_id)
        cast("dict[str, object]", node)["body"] = rendered
    return converted
