"""Skeleton loading utilities for structurally-valid Storybook shells.

A skeleton is a Storybook shell whose non-ending node bodies carry a
``<<FILL ...>>`` directive to be replaced by prose.

The shell is validated through the existing gate's blocking layers (structure,
references, reachability, termination, budget) at load time, so a skeleton can
never introduce a structural defect; the fill step only writes prose.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from cyo_adventure.validator.gate import run_gate

if TYPE_CHECKING:
    from pathlib import Path

FILL_MARKER = "<<FILL"


def load_skeleton(path: Path) -> dict[str, object]:
    """Load a skeleton JSON file and assert it is a structurally-valid shell.

    Args:
        path: Path to the skeleton JSON.

    Returns:
        The decoded skeleton as a dict.

    Raises:
        ValueError: If the skeleton fails the gate's blocking (L1/L2) layers.
    """
    data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    result = run_gate(data)
    if result.blocked:
        messages = (
            "; ".join(f.message for f in result.report.errors)
            or "no error details available"
        )
        msg = f"skeleton {path} failed structural validation: {messages}"
        raise ValueError(msg)
    return data


def has_unfilled_directives(story: dict[str, object]) -> bool:
    """Return True if any node body still contains a ``<<FILL``-prefixed directive."""
    nodes = story.get("nodes")
    if not isinstance(nodes, list):
        return False
    return any(
        isinstance(n, dict)
        and isinstance(n.get("body"), str)
        and FILL_MARKER in n["body"]
        for n in nodes
    )
