"""Story Plan: the per-book meaning layer of ADR-033.

A Story Plan is one JSON document per book that states who is in the story,
the one true answer to its question, a ledger of facts with what each node
requires and establishes, and the threads by which an early choice returns
later. It is an authoring-side artifact: the reader app never loads it and the
Storybook schema does not reference it.

This package is offline-only at this stage (WP-1.1, WP-1.2): nothing on the
request path, the gate or moderation imports it.

- :mod:`~cyo_adventure.storyplan.models` holds the Pydantic schema and the
  shape hash that binds a plan to a book's graph.
- :mod:`~cyo_adventure.storyplan.checks` holds the structural checks SP-0 to
  SP-9 and the computed ``must_not_assert`` sets.
- :mod:`~cyo_adventure.storyplan.schema_export` writes
  ``schema/storyplan.schema.json``.
"""

from __future__ import annotations

from cyo_adventure.storyplan.models import (
    PLAN_VERSION,
    StoryPlan,
    is_supported_plan_version,
    shape_hash,
)

__all__ = [
    "PLAN_VERSION",
    "StoryPlan",
    "is_supported_plan_version",
    "shape_hash",
]
