"""Value types for the kid progress projection (W3.1).

Every type here is a plain, DB-free dataclass, mirroring
``notifications/models.py``: none touch a session or an ORM row's live
state; ``progress/badges.py`` builds them from data ``api/progress.py`` has
already read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
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
class BookFacts:
    """Blob/series facts resolved by ``api/progress.py`` for compute_progress.

    Bundled into one value so ``compute_progress`` stays within this
    project's argument-count lint budget (PLR0913), mirroring
    ``reading_history.py``'s own ``_BookActivity`` bundling.

    Attributes:
        ending_valence: ``(storybook_id, version, ending_id) -> valence``,
            derived from each PLAYED version's stored blob (badge 7 only;
            not necessarily the current published version).
        ending_total_by_book: ``storybook_id -> declared ending count`` of
            the CURRENT published version (0 when unavailable).
        book_titles: ``storybook_id -> display title`` of the current
            published version, falling back to the id.
        series_by_book: ``storybook_id -> series_id`` for every touched
            book (``None`` for a standalone book).
        series_membership: ``series_id -> every storybook_id in that
            series`` (not only the ones this profile has touched).

    Every field is typed ``Mapping``, not ``dict``. ``frozen=True`` stops a
    caller rebinding ``facts.book_titles``, but it does nothing about
    ``facts.book_titles["s1"] = "..."``, so a ``dict`` annotation on a frozen
    dataclass advertises an immutability the class does not have. ``Mapping``
    is the honest type and costs nothing: every consumer in ``badges.py``
    already declares its own parameters as ``Mapping`` and only reads
    (``.get``/``[]``/iteration), and ``api/progress.py`` still builds plain
    ``dict``s to pass in, since a ``dict`` IS a ``Mapping``. This buys real
    checking rather than a comment: mutating through one of these fields is
    now a BasedPyright error at the mutation site.
    """

    # Each default_factory is the PARAMETERIZED dict, not a bare ``dict``. A
    # bare factory is inferred from the declared type, and ``Mapping`` gives it
    # nothing concrete to infer, so BasedPyright reports each default as
    # ``dict[Unknown, Unknown]``. Spelling the factory out keeps this module at
    # zero warnings; ``dict[K, V]()`` builds an ordinary empty dict at runtime.
    ending_valence: Mapping[tuple[str, int, str], str] = field(
        default_factory=dict[tuple[str, int, str], str]
    )
    ending_total_by_book: Mapping[str, int] = field(default_factory=dict[str, int])
    book_titles: Mapping[str, str] = field(default_factory=dict[str, str])
    series_by_book: Mapping[str, str | None] = field(
        default_factory=dict[str, "str | None"]
    )
    series_membership: Mapping[str, frozenset[str]] = field(
        default_factory=dict[str, frozenset[str]]
    )


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
