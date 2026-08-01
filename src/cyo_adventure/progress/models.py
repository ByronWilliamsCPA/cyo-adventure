"""Value types for the kid progress projection (W3.1).

Every type here is a plain, DB-free dataclass, mirroring
``notifications/models.py``: none touch a session or an ORM row's live
state; ``progress/badges.py`` builds them from data ``api/progress.py`` has
already read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True, slots=True)
class BadgeDef:
    """Static kid-readable metadata for one badge catalog entry.

    Attributes:
        id: The stable, closed-vocabulary badge id (wire format).
        name: The story-themed display name (gamification recommendation
            section 2.2).
        description: A short, kid-readable sentence explaining how the badge
            is earned.
    """

    id: str
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class EarnedBadge:
    """One badge a profile has earned, with the moment it first became true.

    Attributes:
        id: The badge id (``BadgeDef.id``).
        name: The badge's display name.
        description: The badge's kid-readable description.
        earned_at: The timestamp of the fact that first satisfied the badge's
            condition (e.g. the completion that made it true), not the time
            this projection happened to be computed.
    """

    id: str
    name: str
    description: str
    earned_at: datetime


@dataclass(frozen=True, slots=True)
class BookProgress:
    """One book's collection state for a profile (the Endings Gallery, K6).

    Attributes:
        storybook_id: The story id.
        title: The pinned published version's title, or the story id as a
            fallback (mirrors ``reading_history.py::_book_title``).
        endings_found: Distinct ending ids this profile has found in this
            book, across every version played (mirrors
            ``reading_history.py``'s own version-agnostic dedup).
        total_endings: The current published version's declared ending
            count, or 0 if unavailable (mirrors ``reading_history.py``).
        finished: Whether at least one ending has been found (the "Finished"
            ribbon; gamification recommendation section 2.1).
        every_path_walked: Whether every declared ending has been found (the
            "Every path walked!" ribbon).
    """

    storybook_id: str
    title: str
    endings_found: int
    total_endings: int
    finished: bool
    every_path_walked: bool


@dataclass(frozen=True, slots=True)
class ProgressTotals:
    """Lifetime totals across every book a profile has touched.

    Attributes:
        books_finished: Distinct books with at least one ending found.
        endings_found: Distinct (book, ending) pairs found, across every
            book and version.
    """

    books_finished: int
    endings_found: int


@dataclass(frozen=True, slots=True)
class ProgressFacts:
    """The full computed progress projection for one profile.

    Attributes:
        badges: Earned badges, oldest-earned first.
        books: Per-book collection state, one row per book with at least one
            completion, sorted by storybook id for stable output.
        totals: Lifetime totals.
    """

    badges: list[EarnedBadge]
    books: list[BookProgress]
    totals: ProgressTotals
