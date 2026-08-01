"""Badge catalog and pure computation (W3.1, gamification recommendation 2.2).

Every function here is pure: it takes already-loaded ``Completion``/
``Rating``/``StoryRequest`` rows (real ORM instances, unit-testable by
constructing them directly with no session -- SQLAlchemy mapped classes are
plain Python objects until added to a session, same convention as
``tests/unit/test_notifications_registry.py``) plus plain dicts the caller
has already derived from storybook blobs, and returns plain dataclasses. No
query, no I/O, mirroring ``notifications/registry.py``'s "pure composer"
shape (see that module's docstring).

Badges 1-8, 10, 11 of the recommendation's table are implemented here. Badges
9 ("Wish Come True") and 12 ("Forty Days of Stories") are deliberately NOT in
``BADGE_CATALOG``: badge 9 needs ``story_request.resulting_storybook_id``
joined against a completion on the resulting book (a follow-up wiring task,
not a missing fact -- the column landed in
``supabase/migrations/20260801000000_add_story_request_resulting_storybook_id.sql``
today), and badge 12 needs real accrued rows in ``reading_activity_day``
(this same change's Task B table, whose data only starts flowing once
``POST /me/reading-time`` is live in the field). See
``docs/planning/kid-appeal-implementation-plan.md`` W3.5 ("Trailing
badges") and the recommendation's section 7 Q5 (the approved v1 cut line).
Extending this module for either badge is additive: add one ``BadgeDef`` to
``BADGE_CATALOG`` and one branch to ``compute_progress``'s result dict; no
existing entry needs to change.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cyo_adventure.progress.models import (
    BadgeDef,
    BookProgress,
    EarnedBadge,
    ProgressFacts,
    ProgressTotals,
)
from cyo_adventure.storybook.models import Valence

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from cyo_adventure.db.models import Completion, Rating, StoryRequest

# The story-themed badge names and conditions are pinned verbatim from
# gamification-recommendation-2026-08-01.md section 2.2's table; descriptions
# are this change's own kid-readable phrasing (the table gives conditions,
# not display copy).
BADGE_CATALOG: dict[str, BadgeDef] = {
    "first_ending": BadgeDef(
        "first_ending", "First Ending", "You found your very first story ending!"
    ),
    "path_not_taken": BadgeDef(
        "path_not_taken",
        "The Path Not Taken",
        "You went back into a story and found a different ending.",
    ),
    "every_path_walked": BadgeDef(
        "every_path_walked",
        "Every Path Walked",
        "You found every single ending in one book!",
    ),
    "bookworm": BadgeDef("bookworm", "Bookworm", "You started 5 different books."),
    "shelf_hero": BadgeDef(
        "shelf_hero", "Shelf Hero", "You finished 10 different books."
    ),
    "ending_collector": BadgeDef(
        "ending_collector",
        "Ending Collector",
        "You found 25 story endings altogether.",
    ),
    "brave_reader": BadgeDef(
        "brave_reader",
        "Brave Reader",
        "After a tricky ending, you tried again and found a new one.",
    ),
    "story_wisher": BadgeDef(
        "story_wisher", "Story Wisher", "You asked for your very own story idea."
    ),
    "star_giver": BadgeDef(
        "star_giver", "Star Giver", "You rated 3 different books."
    ),
    "series_finisher": BadgeDef(
        "series_finisher",
        "Series Finisher",
        "You finished every book in a series!",
    ),
}

# The badge count threshold each milestone badge fires at, named once
# alongside its catalog entry so the recommendation's numbers (5/10/25/3)
# live in exactly one place.
_BOOKWORM_THRESHOLD = 5
_SHELF_HERO_THRESHOLD = 10
_ENDING_COLLECTOR_THRESHOLD = 25
_STAR_GIVER_THRESHOLD = 3

_CHILD_INITIATOR = "child"


def _distinct_ending_first_times(
    completions: Sequence[Completion],
) -> dict[tuple[str, str], datetime]:
    """Return the earliest ``found_at`` per (storybook_id, ending_id).

    Version-agnostic by design, mirroring ``reading_history.py``'s own
    per-book ending dedup (``endings_by_book.setdefault(...).add(ending_id)``,
    which also ignores ``version``): an ending found under an older version
    still counts once it is found again under a newer one.
    """
    result: dict[tuple[str, str], datetime] = {}
    for completion in completions:
        key = (completion.storybook_id, completion.ending_id)
        current = result.get(key)
        if current is None or completion.found_at < current:
            result[key] = completion.found_at
    return result


def _book_first_completion_times(
    completions: Sequence[Completion],
) -> dict[str, datetime]:
    """Return the earliest ``found_at`` per storybook_id, across all endings."""
    result: dict[str, datetime] = {}
    for completion in completions:
        current = result.get(completion.storybook_id)
        if current is None or completion.found_at < current:
            result[completion.storybook_id] = completion.found_at
    return result


def _badge_first_ending(completions: Sequence[Completion]) -> datetime | None:
    """Badge 1: the moment of the very first completion, if any."""
    if not completions:
        return None
    return min(completion.found_at for completion in completions)


def _badge_path_not_taken(completions: Sequence[Completion]) -> datetime | None:
    """Badge 2: the moment any one book first reached 2 distinct endings."""
    by_book: dict[str, list[datetime]] = {}
    for (storybook_id, _ending_id), found_at in _distinct_ending_first_times(
        completions
    ).items():
        by_book.setdefault(storybook_id, []).append(found_at)
    earn_times = [
        sorted(times)[1] for times in by_book.values() if len(times) >= 2  # noqa: PLR2004
    ]
    return min(earn_times) if earn_times else None


def _badge_every_path_walked(
    completions: Sequence[Completion], ending_total_by_book: Mapping[str, int]
) -> datetime | None:
    """Badge 3: the moment any one book's every declared ending was found."""
    by_book: dict[str, list[datetime]] = {}
    for (storybook_id, _ending_id), found_at in _distinct_ending_first_times(
        completions
    ).items():
        by_book.setdefault(storybook_id, []).append(found_at)
    earn_times: list[datetime] = []
    for storybook_id, times in by_book.items():
        total = ending_total_by_book.get(storybook_id, 0)
        if total > 0 and len(times) >= total:
            earn_times.append(sorted(times)[total - 1])
    return min(earn_times) if earn_times else None


def _nth_smallest_book_time(
    completions: Sequence[Completion], n: int
) -> datetime | None:
    """Return the time the n-th distinct book was first touched, or None."""
    times = sorted(_book_first_completion_times(completions).values())
    if len(times) < n:
        return None
    return times[n - 1]


def _badge_bookworm(completions: Sequence[Completion]) -> datetime | None:
    """Badge 4: the moment the 5th distinct book got its first ending."""
    return _nth_smallest_book_time(completions, _BOOKWORM_THRESHOLD)


def _badge_shelf_hero(completions: Sequence[Completion]) -> datetime | None:
    """Badge 5: the moment the 10th distinct book got its first ending."""
    return _nth_smallest_book_time(completions, _SHELF_HERO_THRESHOLD)


def _badge_ending_collector(completions: Sequence[Completion]) -> datetime | None:
    """Badge 6: the moment the 25th distinct (book, ending) pair was found."""
    times = sorted(_distinct_ending_first_times(completions).values())
    if len(times) < _ENDING_COLLECTOR_THRESHOLD:
        return None
    return times[_ENDING_COLLECTOR_THRESHOLD - 1]


def _badge_brave_reader(
    completions: Sequence[Completion],
    ending_valence: Mapping[tuple[str, int, str], str],
) -> datetime | None:
    """Badge 7: after a negative-valence ending, found a different one.

    # #ASSUME: data integrity: a completion whose (storybook_id, version,
    # ending_id) triple is absent from ``ending_valence`` (a blob the caller
    # could not load, or a version whose blob is malformed) is treated as
    # non-negative, the safe default (never fabricates a "brave" moment from
    # missing data).
    # #VERIFY: tests/unit/test_progress_badges.py::
    # test_brave_reader_missing_valence_data_never_earns.

    Walks each book's completions in chronological order; once a
    negative-valence ending is seen, the first LATER completion in that same
    book with a DIFFERENT ending id is the earn moment ("went back and found
    another ending", not a repeat visit to the same negative ending).
    """
    by_book: dict[str, list[Completion]] = {}
    for completion in completions:
        by_book.setdefault(completion.storybook_id, []).append(completion)
    earn_times: list[datetime] = []
    for storybook_id, rows in by_book.items():
        ordered = sorted(rows, key=lambda c: c.found_at)
        seen_negative = False
        negative_ending_id: str | None = None
        for completion in ordered:
            if seen_negative and completion.ending_id != negative_ending_id:
                earn_times.append(completion.found_at)
                break
            valence = ending_valence.get(
                (storybook_id, completion.version, completion.ending_id)
            )
            if valence == Valence.NEGATIVE.value:
                seen_negative = True
                negative_ending_id = completion.ending_id
    return min(earn_times) if earn_times else None


def _badge_story_wisher(
    story_requests: Sequence[StoryRequest],
) -> datetime | None:
    """Badge 8: the moment of this profile's first child-initiated request."""
    times = [
        request.created_at
        for request in story_requests
        if request.initiator_role == _CHILD_INITIATOR
    ]
    return min(times) if times else None


def _badge_star_giver(ratings: Sequence[Rating]) -> datetime | None:
    """Badge 10: the moment the 3rd distinct book got its first rating."""
    by_book: dict[str, datetime] = {}
    for rating in ratings:
        current = by_book.get(rating.storybook_id)
        if current is None or rating.rated_at < current:
            by_book[rating.storybook_id] = rating.rated_at
    times = sorted(by_book.values())
    if len(times) < _STAR_GIVER_THRESHOLD:
        return None
    return times[_STAR_GIVER_THRESHOLD - 1]


def _badge_series_finisher(
    completions: Sequence[Completion],
    series_by_book: Mapping[str, str | None],
    series_membership: Mapping[str, frozenset[str]],
) -> datetime | None:
    """Badge 11: the moment every book of some series had been finished.

    "Finished" reuses the recommendation's own Finished-Shelf definition
    (section 2.1): at least one ending found, not every ending.
    """
    book_times = _book_first_completion_times(completions)
    finished_books = frozenset(book_times)
    touched_series_ids = {
        series_by_book[book_id]
        for book_id in finished_books
        if series_by_book.get(book_id) is not None
    }
    earn_times: list[datetime] = []
    for series_id in touched_series_ids:
        if series_id is None:  # pragma: no cover - defensive, set excludes None above
            continue
        members = series_membership.get(series_id, frozenset())
        if members and members <= finished_books:
            earn_times.append(max(book_times[book_id] for book_id in members))
    return min(earn_times) if earn_times else None


def _book_states(
    completions: Sequence[Completion],
    ending_total_by_book: Mapping[str, int],
    book_titles: Mapping[str, str],
) -> list[BookProgress]:
    """Build one ``BookProgress`` per book with at least one completion."""
    endings_by_book: dict[str, set[str]] = {}
    for completion in completions:
        endings_by_book.setdefault(completion.storybook_id, set()).add(
            completion.ending_id
        )
    books = [
        BookProgress(
            storybook_id=storybook_id,
            title=book_titles.get(storybook_id, storybook_id),
            endings_found=len(ending_ids),
            total_endings=ending_total_by_book.get(storybook_id, 0),
            finished=len(ending_ids) >= 1,
            every_path_walked=(
                ending_total_by_book.get(storybook_id, 0) > 0
                and len(ending_ids) >= ending_total_by_book.get(storybook_id, 0)
            ),
        )
        for storybook_id, ending_ids in endings_by_book.items()
    ]
    books.sort(key=lambda book: book.storybook_id)
    return books


def compute_progress(
    *,
    completions: Sequence[Completion],
    ratings: Sequence[Rating],
    child_story_requests: Sequence[StoryRequest],
    ending_valence: Mapping[tuple[str, int, str], str],
    ending_total_by_book: Mapping[str, int],
    book_titles: Mapping[str, str],
    series_by_book: Mapping[str, str | None],
    series_membership: Mapping[str, frozenset[str]],
) -> ProgressFacts:
    """Compute one profile's full progress projection from pre-loaded rows.

    Args:
        completions: Every ``Completion`` row for this profile.
        ratings: Every ``Rating`` row for this profile.
        child_story_requests: Every ``StoryRequest`` row for this profile
            (both child- and adult-initiated; badge 8 filters internally).
        ending_valence: ``(storybook_id, version, ending_id) -> valence``,
            derived from each played version's stored blob (badge 7 only).
        ending_total_by_book: ``storybook_id -> declared ending count`` of
            the CURRENT published version (0 when unavailable), mirroring
            ``reading_history.py``.
        book_titles: ``storybook_id -> display title`` of the current
            published version, falling back to the id.
        series_by_book: ``storybook_id -> series_id`` for every touched book
            (``None`` for a standalone book).
        series_membership: ``series_id -> every storybook_id in that
            series`` (not only the ones this profile has touched), needed to
            know whether a series is fully finished.

    Returns:
        ProgressFacts: Earned badges, per-book collection state, and lifetime
        totals.
    """
    raw_earned: dict[str, datetime | None] = {
        "first_ending": _badge_first_ending(completions),
        "path_not_taken": _badge_path_not_taken(completions),
        "every_path_walked": _badge_every_path_walked(
            completions, ending_total_by_book
        ),
        "bookworm": _badge_bookworm(completions),
        "shelf_hero": _badge_shelf_hero(completions),
        "ending_collector": _badge_ending_collector(completions),
        "brave_reader": _badge_brave_reader(completions, ending_valence),
        "story_wisher": _badge_story_wisher(child_story_requests),
        "star_giver": _badge_star_giver(ratings),
        "series_finisher": _badge_series_finisher(
            completions, series_by_book, series_membership
        ),
    }
    badges = [
        EarnedBadge(
            id=badge_id,
            name=BADGE_CATALOG[badge_id].name,
            description=BADGE_CATALOG[badge_id].description,
            earned_at=earned_at,
        )
        for badge_id, earned_at in raw_earned.items()
        if earned_at is not None
    ]
    badges.sort(key=lambda badge: (badge.earned_at, badge.id))

    totals = ProgressTotals(
        books_finished=len(_book_first_completion_times(completions)),
        endings_found=len(_distinct_ending_first_times(completions)),
    )
    return ProgressFacts(
        badges=badges,
        books=_book_states(completions, ending_total_by_book, book_titles),
        totals=totals,
    )
