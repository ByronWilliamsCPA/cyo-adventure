"""Render a validated skeleton shell as a PlantUML state diagram.

A skeleton (see :mod:`cyo_adventure.generation.skeleton`) is a directed graph of
nodes. This module transforms that graph into deterministic PlantUML state-diagram
source: ``[*]`` to the start node, choices as labeled transitions, and ending
nodes as terminal states styled by valence. The transform is pure (no I/O, no
clock, no network), which is what makes it byte-stable and cheap to test.
"""

from __future__ import annotations

import re
from typing import TypeAlias, cast

from cyo_adventure.storybook.models import Valence

_ObjectMap: TypeAlias = dict[str, object]

# Non-ending node background by narrative role (FILL ``role=``).
_ROLE_COLOR: dict[str, str] = {
    "setup": "#BBDEFB",
    "rising": "#D1C4E9",
    "choice": "#FFF9C4",
    "climax": "#FFE0B2",
}
# Ending node background by valence. Keyed by the enforced Valence enum so a
# schema change to that enum surfaces here as a type error, not a silent gap.
_VALENCE_COLOR: dict[str, str] = {
    Valence.POSITIVE: "#C8E6C9",
    Valence.NEUTRAL: "#E0E0E0",
    Valence.NEGATIVE: "#FFCDD2",
}
_DEFAULT_NODE_COLOR = "#ECEFF1"
_LABEL_MAX = 40

# ``<<FILL role=setup words=85 beats='...'>>`` -> role token + integer word count.
_FILL_RE = re.compile(r"role=(?P<role>\S+)\s+words=(?P<words>\d+)")


def _parse_fill(body: str) -> tuple[str | None, int | None]:
    """Extract ``(role, words)`` from a FILL directive body.

    Args:
        body: A node ``body`` string, which may or may not be a FILL directive.

    Returns:
        ``(role, words)`` when ``body`` is a FILL directive, else ``(None, None)``.
        ``beats`` is intentionally not extracted: FILL-directive prose must never
        leak into the structural diagram. Choice labels are a separate, narrower
        exception to this: they are author-written text too, and are emitted
        (truncated and sanitized) into transition labels by design.
    """
    match = _FILL_RE.search(body)
    if match is None:
        return None, None
    return match.group("role"), int(match.group("words"))


def nodes_of(data: _ObjectMap) -> list[_ObjectMap]:
    """Return the node dicts from a skeleton, narrowing for strict typing."""
    raw = data.get("nodes")
    if not isinstance(raw, list):
        return []
    items: list[object] = cast("list[object]", raw)
    return [cast("_ObjectMap", item) for item in items if isinstance(item, dict)]


def _choices(node: _ObjectMap) -> list[_ObjectMap]:
    """Return the choice dicts from a node, narrowing for strict typing."""
    raw = node.get("choices")
    if not isinstance(raw, list):
        return []
    items: list[object] = cast("list[object]", raw)
    return [cast("_ObjectMap", item) for item in items if isinstance(item, dict)]


def ending_of(node: _ObjectMap) -> _ObjectMap:
    """Return the ending dict from a node, or an empty dict."""
    raw = node.get("ending")
    return cast("_ObjectMap", raw) if isinstance(raw, dict) else {}


def meta_of(data: _ObjectMap) -> _ObjectMap:
    """Return the metadata dict from a skeleton, or an empty dict."""
    raw = data.get("metadata")
    return cast("_ObjectMap", raw) if isinstance(raw, dict) else {}


def _node_id(node: _ObjectMap) -> str:
    """Return a node's id as a string (empty if missing/wrong type)."""
    raw = node.get("id")
    return raw if isinstance(raw, str) else ""


def _require_node_id(node: _ObjectMap) -> str:
    """Return a node's id, or raise if it is missing/non-string.

    Raises:
        ValueError: If the node has no valid string ``id``. A gate-validated
            skeleton cannot reach this branch (see
            ``cyo_adventure.generation.skeleton.load_skeleton``); rendering
            engines would otherwise silently drop the node from the diagram
            with no error, under-representing the source JSON.
    """
    node_id = _node_id(node)
    if not node_id:
        msg = f"skeleton node missing a valid string id: {node!r}"
        raise ValueError(msg)
    return node_id


def _sanitize_text(text: str) -> str:
    """Collapse whitespace and neutralize characters that break PlantUML syntax.

    A double quote in author-written text (an ending title, a choice label)
    would prematurely terminate a quoted PlantUML string or otherwise corrupt
    the generated diagram source; replacing it with a single quote keeps the
    output well-formed without altering the text's meaning.
    """
    flat = " ".join(text.split())
    return flat.replace('"', "'")


def _truncate(label: str, limit: int = _LABEL_MAX) -> str:
    """Sanitize and truncate a transition label with an ellipsis."""
    flat = _sanitize_text(label)
    if len(flat) <= limit:
        return flat
    return flat[:limit] + "..."


def _state_declaration_lines(nodes: list[_ObjectMap]) -> list[str]:
    """Return one ``state <id> <color>`` line (plus descriptions) per node."""
    lines: list[str] = []
    for node in nodes:
        node_id = _require_node_id(node)
        is_ending = bool(node.get("is_ending"))
        color = _node_color(node, is_ending=is_ending)
        lines.append(f"state {node_id} {color}")
        lines.extend(
            f"{node_id} : {desc}"
            for desc in _node_descriptions(node, is_ending=is_ending)
        )
    return lines


def _transition_lines(nodes: list[_ObjectMap]) -> list[str]:
    """Return one ``<id> --> <target> : <label>`` line per valid choice."""
    lines: list[str] = []
    for node in nodes:
        node_id = _require_node_id(node)
        for choice in _choices(node):
            target = choice.get("target")
            label = choice.get("label")
            if not isinstance(target, str):
                continue
            label_text = _truncate(label) if isinstance(label, str) else ""
            lines.append(f"{node_id} --> {target} : {label_text}")
    return lines


def _terminal_lines(nodes: list[_ObjectMap]) -> list[str]:
    """Return one ``<id> --> [*]`` line per ending node."""
    return [
        f"{_require_node_id(node)} --> [*]"
        for node in nodes
        if bool(node.get("is_ending"))
    ]


def skeleton_to_plantuml(data: _ObjectMap, *, name: str | None = None) -> str:
    """Render a skeleton dict as deterministic PlantUML state-diagram source.

    Args:
        data: A decoded skeleton dict (typically from ``load_skeleton``).
        name: Optional diagram name for the ``@startuml`` line; defaults to the
            skeleton ``id`` (or ``"skeleton"`` when absent).

    Returns:
        PlantUML source ending in a trailing newline. Output is byte-stable for a
        given input: nodes and choices are emitted in document order.
    """
    nodes = nodes_of(data)
    start = data.get("start_node")
    start_id = start if isinstance(start, str) else ""
    raw_id = data.get("id")
    diagram_name = name or (raw_id if isinstance(raw_id, str) else "skeleton")

    lines: list[str] = [
        f"@startuml {diagram_name}",
        "' Generated from skeleton JSON by scripts/render_skeleton_diagrams.py.",
        "' Do not edit by hand; re-run the generator.",
        'skinparam defaultFontName "Roboto"',
        "skinparam backgroundColor #FAFAFA",
        "skinparam roundCorner 8",
        "hide empty description",
        "",
        f"[*] --> {start_id}",
    ]

    # State declarations (one per node), then transitions, then terminals.
    lines.extend(_state_declaration_lines(nodes))
    lines.extend(_transition_lines(nodes))
    lines.extend(_terminal_lines(nodes))

    lines.append("")
    lines.extend(_legend_lines(data, nodes))
    lines.append("@enduml")
    return "\n".join(lines) + "\n"


def _node_color(node: _ObjectMap, *, is_ending: bool) -> str:
    """Return the ``#RRGGBB`` PlantUML color token for a node."""
    if is_ending:
        valence = ending_of(node).get("valence")
        key = valence if isinstance(valence, str) else ""
        return _VALENCE_COLOR.get(key, _DEFAULT_NODE_COLOR)
    body = node.get("body")
    role, _ = _parse_fill(body) if isinstance(body, str) else (None, None)
    return _ROLE_COLOR.get(role or "", _DEFAULT_NODE_COLOR)


def _node_descriptions(node: _ObjectMap, *, is_ending: bool) -> list[str]:
    """Return PlantUML state-description lines for a node (no author prose)."""
    if is_ending:
        ending = ending_of(node)
        kind = ending.get("kind")
        valence = ending.get("valence")
        title = ending.get("title")
        descs: list[str] = []
        if isinstance(kind, str) and isinstance(valence, str):
            descs.append(f"{kind} ({valence})")
        if isinstance(title, str):
            descs.append(f'"{_sanitize_text(title)}"')
        return descs
    body = node.get("body")
    role, words = _parse_fill(body) if isinstance(body, str) else (None, None)
    if role is None or words is None:
        return []
    return [f"{role} · {words}w"]


def valence_split(nodes: list[_ObjectMap]) -> tuple[int, int, int]:
    """Return ``(positive, neutral, negative)`` ending counts.

    A missing ``valence`` (an incomplete ending block) is tolerated and simply
    not counted, consistent with this module's other missing-field handling.
    A *present but unrecognized* value is not tolerated: silently dropping it
    would make the legend's ``ending_total`` and this split diverge with no
    signal, which is exactly the silent-drift failure mode this generator
    exists to prevent.

    Raises:
        ValueError: If an ending node declares a non-null ``valence`` that is
            not one of :class:`~cyo_adventure.storybook.models.Valence`'s
            values. A gate-validated skeleton cannot reach this branch (see
            ``cyo_adventure.generation.skeleton.load_skeleton``).
    """
    pos = neu = neg = 0
    for node in nodes:
        if not bool(node.get("is_ending")):
            continue
        valence = ending_of(node).get("valence")
        if valence is None:
            continue
        if valence == Valence.POSITIVE:
            pos += 1
        elif valence == Valence.NEUTRAL:
            neu += 1
        elif valence == Valence.NEGATIVE:
            neg += 1
        else:
            msg = f"ending node has unrecognized valence: {valence!r}"
            raise ValueError(msg)
    return pos, neu, neg


def _legend_lines(data: _ObjectMap, nodes: list[_ObjectMap]) -> list[str]:
    """Return the ``legend ... endlegend`` block carrying skeleton metadata."""
    meta = meta_of(data)
    title = data.get("title")
    title_text = title if isinstance(title, str) else "Untitled"
    band = meta.get("age_band")
    tier = meta.get("tier")
    minutes = meta.get("estimated_minutes")
    topology = meta.get("topology")
    ending_total = sum(1 for n in nodes if bool(n.get("is_ending")))
    pos, neu, neg = valence_split(nodes)
    band_text = band if isinstance(band, str) else "?"
    tier_text = str(tier) if isinstance(tier, int) else "?"
    minutes_text = str(minutes) if isinstance(minutes, int) else "?"
    topology_text = topology if isinstance(topology, str) else "?"
    ending_word = "ending" if ending_total == 1 else "endings"
    return [
        "legend right",
        f"  {title_text}",
        f"  Band {band_text} · Tier {tier_text} · ~{minutes_text} min",
        f"  Topology: {topology_text}",
        f"  {len(nodes)} nodes · {ending_total} {ending_word} ({pos}+ / {neu}n / {neg}-)",
        "endlegend",
    ]
