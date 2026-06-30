"""Render a validated skeleton shell as a PlantUML state diagram.

A skeleton (see :mod:`cyo_adventure.generation.skeleton`) is a directed graph of
nodes. This module transforms that graph into deterministic PlantUML state-diagram
source: ``[*]`` to the start node, choices as labeled transitions, and ending
nodes as terminal states styled by valence. The transform is pure (no I/O, no
clock, no network), which is what makes it byte-stable and cheap to test.
"""

from __future__ import annotations

import re
from typing import cast

# Non-ending node background by narrative role (FILL ``role=``).
_ROLE_COLOR: dict[str, str] = {
    "setup": "#BBDEFB",
    "rising": "#D1C4E9",
    "choice": "#FFF9C4",
    "climax": "#FFE0B2",
}
# Ending node background by valence.
_VALENCE_COLOR: dict[str, str] = {
    "positive": "#C8E6C9",
    "neutral": "#E0E0E0",
    "negative": "#FFCDD2",
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
        ``beats`` is intentionally not extracted: author intent must never leak
        into the structural diagram.
    """
    match = _FILL_RE.search(body)
    if match is None:
        return None, None
    return match.group("role"), int(match.group("words"))


def _nodes(data: dict[str, object]) -> list[dict[str, object]]:
    """Return the node dicts from a skeleton, narrowing for strict typing."""
    raw = data.get("nodes")
    if not isinstance(raw, list):
        return []
    items: list[object] = cast("list[object]", raw)
    return [cast("dict[str, object]", item) for item in items if isinstance(item, dict)]


def _choices(node: dict[str, object]) -> list[dict[str, object]]:
    """Return the choice dicts from a node, narrowing for strict typing."""
    raw = node.get("choices")
    if not isinstance(raw, list):
        return []
    items: list[object] = cast("list[object]", raw)
    return [cast("dict[str, object]", item) for item in items if isinstance(item, dict)]


def _ending(node: dict[str, object]) -> dict[str, object]:
    """Return the ending dict from a node, or an empty dict."""
    raw = node.get("ending")
    return cast("dict[str, object]", raw) if isinstance(raw, dict) else {}


def _meta(data: dict[str, object]) -> dict[str, object]:  # pyright: ignore[reportUnusedFunction]  # narrowing helper; called by future tasks
    """Return the metadata dict from a skeleton, or an empty dict."""
    raw = data.get("metadata")
    return cast("dict[str, object]", raw) if isinstance(raw, dict) else {}


def _node_id(node: dict[str, object]) -> str:
    """Return a node's id as a string (empty if missing/wrong type)."""
    raw = node.get("id")
    return raw if isinstance(raw, str) else ""


def _truncate(label: str, limit: int = _LABEL_MAX) -> str:
    """Collapse newlines and truncate a transition label with an ellipsis."""
    flat = " ".join(label.split())
    if len(flat) <= limit:
        return flat
    return flat[:limit] + "..."


def skeleton_to_plantuml(data: dict[str, object], *, name: str | None = None) -> str:
    """Render a skeleton dict as deterministic PlantUML state-diagram source.

    Args:
        data: A decoded skeleton dict (typically from ``load_skeleton``).
        name: Optional diagram name for the ``@startuml`` line; defaults to the
            skeleton ``id`` (or ``"skeleton"`` when absent).

    Returns:
        PlantUML source ending in a trailing newline. Output is byte-stable for a
        given input: nodes and choices are emitted in document order.
    """
    nodes = _nodes(data)
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
    for node in nodes:
        node_id = _node_id(node)
        if not node_id:
            continue
        is_ending = bool(node.get("is_ending"))
        color = _node_color(node, is_ending=is_ending)
        lines.append(f"state {node_id} {color}")

    for node in nodes:
        node_id = _node_id(node)
        if not node_id:
            continue
        for choice in _choices(node):
            target = choice.get("target")
            label = choice.get("label")
            if not isinstance(target, str):
                continue
            label_text = _truncate(label) if isinstance(label, str) else ""
            lines.append(f"{node_id} --> {target} : {label_text}")

    for node in nodes:
        node_id = _node_id(node)
        if node_id and bool(node.get("is_ending")):
            lines.append(f"{node_id} --> [*]")

    lines.append("@enduml")
    return "\n".join(lines) + "\n"


def _node_color(node: dict[str, object], *, is_ending: bool) -> str:
    """Return the ``#RRGGBB`` PlantUML color token for a node."""
    if is_ending:
        valence = _ending(node).get("valence")
        key = valence if isinstance(valence, str) else ""
        return _VALENCE_COLOR.get(key, _DEFAULT_NODE_COLOR)
    body = node.get("body")
    role, _ = _parse_fill(body) if isinstance(body, str) else (None, None)
    return _ROLE_COLOR.get(role or "", _DEFAULT_NODE_COLOR)
