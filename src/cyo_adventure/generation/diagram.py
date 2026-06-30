"""Render a validated skeleton shell as a PlantUML state diagram.

A skeleton (see :mod:`cyo_adventure.generation.skeleton`) is a directed graph of
nodes. This module transforms that graph into deterministic PlantUML state-diagram
source: ``[*]`` to the start node, choices as labeled transitions, and ending
nodes as terminal states styled by valence. The transform is pure (no I/O, no
clock, no network), which is what makes it byte-stable and cheap to test.
"""

from __future__ import annotations

import re

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


def _parse_fill(body: str) -> tuple[str | None, int | None]:  # pyright: ignore[reportUnusedFunction]
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
