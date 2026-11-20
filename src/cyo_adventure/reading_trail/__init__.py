"""Reading trail: per-read step capture (privacy-model.md "Reading trail").

Pure, database-free helpers used by ``api/reading.py``'s ingest route and by
``scripts/report_reading_trail.py``: the closed step vocabulary, validation of
a batch against the pinned storybook version, and the idempotent merge.
"""

from __future__ import annotations

from cyo_adventure.reading_trail.steps import (
    MAX_ELAPSED_SECONDS,
    MAX_STEPS_PER_BATCH,
    OPENING_KINDS,
    StepKind,
    StoryIndex,
    TrailStep,
    ending_of,
    merge_steps,
    validate_steps,
)

__all__ = [
    "MAX_ELAPSED_SECONDS",
    "MAX_STEPS_PER_BATCH",
    "OPENING_KINDS",
    "StepKind",
    "StoryIndex",
    "TrailStep",
    "ending_of",
    "merge_steps",
    "validate_steps",
]
