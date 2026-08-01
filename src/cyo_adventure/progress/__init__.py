"""Kid progress projection (W3.1): badges, collection state, lifetime totals.

Pure, DB-free composition over already-loaded ``Completion``/``Rating``/
``StoryRequest`` rows and pre-resolved blob-derived facts, following the same
"pure composer" shape as ``notifications/registry.py`` (module docstring
there): no session, no query, unit-testable with plain constructed fixtures.
``api/progress.py`` is the sole caller and owns every database read.
"""

from __future__ import annotations

from cyo_adventure.progress.badges import BADGE_CATALOG, compute_progress
from cyo_adventure.progress.models import (
    BadgeDef,
    BookFacts,
    BookProgress,
    EarnedBadge,
    ProgressFacts,
    ProgressTotals,
)

__all__ = [
    "BADGE_CATALOG",
    "BadgeDef",
    "BookFacts",
    "BookProgress",
    "EarnedBadge",
    "ProgressFacts",
    "ProgressTotals",
    "compute_progress",
]
