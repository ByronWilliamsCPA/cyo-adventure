"""Deterministic story player (Story Runtime Semantics v1).

The :class:`StoryEngine` is the reference implementation of the canonical
execution model shared by the validator and the TypeScript client.
"""

from __future__ import annotations

from cyo_adventure.player.engine import StoryEngine
from cyo_adventure.player.state import ReadingState, Snapshot

__all__ = [
    "ReadingState",
    "Snapshot",
    "StoryEngine",
]
