"""Story Plan: the per-book meaning layer of ADR-033.

A Story Plan is one JSON document per book that states who is in the story,
the one true answer to its question, a ledger of facts with what each node
requires and establishes, and the threads by which an early choice returns
later. It is an authoring-side artifact: the reader app never loads it and the
Storybook schema does not reference it.

The models, checks and shapes were offline-only through WP-2.2. Since WP-2.3
the generation worker imports :mod:`~cyo_adventure.storyplan.generate` for a
``plan_fill`` job (pitches, plan, SP checks, bounded repair); the gate and
moderation still do not import this package.

- :mod:`~cyo_adventure.storyplan.models` holds the Pydantic schema and the
  shape hash that binds a plan to a book's graph.
- :mod:`~cyo_adventure.storyplan.checks` holds the structural checks SP-0 to
  SP-9 and the computed ``must_not_assert`` sets.
- :mod:`~cyo_adventure.storyplan.shapes` loads the retained shapes (WP-2.2).
- :mod:`~cyo_adventure.storyplan.generate` turns a request into a checked
  plan on a retained shape (WP-2.3).
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
