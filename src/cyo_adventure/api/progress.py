"""Kid-scoped progress projection (W3.1): badges, gallery, lifetime totals.

``GET /me/progress`` computes badges 1-8/10/11 (gamification recommendation
section 2.2), per-book collection state (the Endings Gallery / Finished
Shelf, section 2.1), and lifetime totals entirely on read, from
``Completion``/``Rating``/``StoryRequest`` rows this module loads and the
pure ``progress/`` package composes -- zero new tables for this half of the
recommendation (section 5: "starting derived means zero migrations for the
entire badge and collection layer").

Child-only in this v1 slice, not the "guardian may also call for a specific
profile they own" variant the plan names as an option: this route has no
path parameter (mirrors ``api/me.py::whoami``'s "me" shape), so a guardian
caller would need a profile id parameter this route deliberately omits to
keep the child-ownership check trivial (structural: a CHILD principal is
always scoped to exactly one profile, ``api/deps.py::Principal``). Badges
are family-visible per the plan's adopted defaults, but no guardian-facing
badge surface exists yet (W3.2, frontend, is out of scope for this change);
when one lands it can call this same pure ``progress.badges.compute_progress``
with a guardian-supplied profile id rather than duplicate the projection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from sqlalchemy import select, tuple_

from cyo_adventure.api.deps import CurrentPrincipal, DbSession, Role
from cyo_adventure.api.schemas import (
    BookProgressView,
    EarnedBadgeView,
    ProgressTotalsView,
    ProgressView,
    error_responses,
)
from cyo_adventure.core.exceptions import AuthorizationError
from cyo_adventure.db.models import (
    Completion,
    Rating,
    Storybook,
    StorybookVersion,
    StoryRequest,
)
from cyo_adventure.progress.badges import compute_progress
from cyo_adventure.progress.blob import book_title, ending_count, ending_valence_map
from cyo_adventure.progress.models import BookFacts

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.api.deps import Principal
    from cyo_adventure.progress.models import ProgressFacts

router = APIRouter(prefix="/api/v1", tags=["progress"], responses=error_responses(401))


def _require_child_profile(principal: Principal) -> uuid.UUID:
    """Return the caller's own profile id, rejecting a non-child principal.

    Args:
        principal: The authenticated principal.

    Returns:
        uuid.UUID: The child's own profile id.

    Raises:
        AuthorizationError: If the principal is not a child (see module
            docstring for why this endpoint has no guardian/admin path).
    """
    # #CRITICAL: security: this is the endpoint's entire authorization gate.
    # A CHILD Principal is structurally scoped to exactly one profile
    # (api/deps.py::Principal.__post_init__ / _child_principal), so taking
    # the single element of profile_ids can never leak a sibling's data; a
    # non-child principal is rejected outright rather than guessing which
    # profile it might mean.
    # #VERIFY: tests/unit/test_progress_api_unit.py::
    # test_guardian_and_admin_rejected; tests/integration/test_authz_matrix.py
    # ROUTE_TABLE entry for GET /me/progress.
    if principal.role != Role.CHILD:
        msg = "this endpoint is child-scoped; no guardian/admin surface exists yet"
        raise AuthorizationError(msg)
    return next(iter(principal.profile_ids))


@router.get("/me/progress")
async def get_my_progress(
    principal: CurrentPrincipal, session: DbSession
) -> ProgressView:
    """Return the caller's own badges, collection state, and lifetime totals.

    Args:
        principal: The authenticated principal (must be a child token).
        session: The request session.

    Returns:
        ProgressView: Earned badges, per-book collection state, and lifetime
        totals for the caller's own profile.

    Raises:
        AuthorizationError: If the caller is not a child.
    """
    profile_id = _require_child_profile(principal)

    completions = list(
        await session.scalars(
            select(Completion).where(Completion.child_profile_id == profile_id)
        )
    )
    ratings = list(
        await session.scalars(
            select(Rating).where(Rating.child_profile_id == profile_id)
        )
    )
    story_requests = list(
        await session.scalars(
            select(StoryRequest).where(StoryRequest.profile_id == profile_id)
        )
    )

    facts = await _build_progress_facts(session, completions, ratings, story_requests)
    return _to_view(facts)


async def _load_touched_books(
    session: AsyncSession, completions: list[Completion]
) -> dict[str, Storybook]:
    """Bulk-load every ``Storybook`` a profile's completions reference."""
    book_ids = {completion.storybook_id for completion in completions}
    if not book_ids:
        return {}
    return {
        book.id: book
        for book in await session.scalars(
            select(Storybook).where(Storybook.id.in_(book_ids))
        )
    }


async def _load_versions(
    session: AsyncSession, completions: list[Completion], books: dict[str, Storybook]
) -> dict[tuple[str, int], StorybookVersion]:
    """Bulk-load every played version plus each book's current published one.

    The played versions feed badge 7's valence lookup (a completion's own
    version, not necessarily the current one); the current published
    versions feed the collection-state totals/titles (mirrors
    ``reading_history.py``).
    """
    version_keys: set[tuple[str, int]] = {
        (completion.storybook_id, completion.version) for completion in completions
    }
    for book in books.values():
        if book.current_published_version is not None:
            version_keys.add((book.id, book.current_published_version))
    if not version_keys:
        return {}
    version_rows = await session.scalars(
        select(StorybookVersion).where(
            tuple_(StorybookVersion.storybook_id, StorybookVersion.version).in_(
                version_keys
            )
        )
    )
    return {(row.storybook_id, row.version): row for row in version_rows}


def _build_ending_valence(
    versions: dict[tuple[str, int], StorybookVersion],
) -> dict[tuple[str, int, str], str]:
    """Flatten every played version's blob into (book, version, ending) valence."""
    ending_valence: dict[tuple[str, int, str], str] = {}
    for (storybook_id, version), row in versions.items():
        for ending_id, valence in ending_valence_map(row.blob).items():
            ending_valence[(storybook_id, version, ending_id)] = valence
    return ending_valence


def _build_current_version_facts(
    books: dict[str, Storybook], versions: dict[tuple[str, int], StorybookVersion]
) -> tuple[dict[str, int], dict[str, str]]:
    """Return (ending_total_by_book, book_titles) from each book's pinned version."""
    ending_total_by_book: dict[str, int] = {}
    book_titles: dict[str, str] = {}
    for book_id, book in books.items():
        pinned_version = book.current_published_version
        if pinned_version is None:
            continue
        pinned_row = versions.get((book_id, pinned_version))
        if pinned_row is None:
            continue
        ending_total_by_book[book_id] = ending_count(
            pinned_row.blob, book_id, pinned_version
        )
        book_titles[book_id] = book_title(pinned_row.blob, book_id, pinned_version)
    return ending_total_by_book, book_titles


async def _load_series_membership(
    session: AsyncSession, books: dict[str, Storybook]
) -> dict[str, frozenset[str]]:
    """Return ``series_id -> every storybook_id in that series`` (badge 11).

    Loads the FULL series roster, not only the books this profile has
    touched, since "finished every book in the series" must be checked
    against every book that exists in it.
    """
    series_ids = {
        book.series_id for book in books.values() if book.series_id is not None
    }
    if not series_ids:
        return {}
    series_rows = await session.scalars(
        select(Storybook).where(Storybook.series_id.in_(series_ids))
    )
    grouped: dict[str, set[str]] = {}
    for row in series_rows:
        if row.series_id is not None:
            grouped.setdefault(str(row.series_id), set()).add(row.id)
    return {sid: frozenset(ids) for sid, ids in grouped.items()}


async def _build_progress_facts(
    session: AsyncSession,
    completions: list[Completion],
    ratings: list[Rating],
    story_requests: list[StoryRequest],
) -> ProgressFacts:
    """Load the blob/series facts the pure composer needs, then compose.

    # #ASSUME: external resources: a fixed, small number of bulk queries
    # regardless of how many books this profile has touched (no N+1 over
    # blobs), mirroring reading_history.py::get_reading_history.
    # #VERIFY: tests/unit/test_progress_api_unit.py asserts the query count.
    """
    books = await _load_touched_books(session, completions)
    versions = await _load_versions(session, completions, books)
    ending_valence = _build_ending_valence(versions)
    ending_total_by_book, book_titles = _build_current_version_facts(books, versions)
    series_membership = await _load_series_membership(session, books)
    series_by_book = {
        book_id: (str(book.series_id) if book.series_id is not None else None)
        for book_id, book in books.items()
    }

    return compute_progress(
        completions=completions,
        ratings=ratings,
        child_story_requests=story_requests,
        book_facts=BookFacts(
            ending_valence=ending_valence,
            ending_total_by_book=ending_total_by_book,
            book_titles=book_titles,
            series_by_book=series_by_book,
            series_membership=series_membership,
        ),
    )


def _to_view(facts: ProgressFacts) -> ProgressView:
    """Convert the pure-computed facts into the wire response model."""
    return ProgressView(
        badges=[
            EarnedBadgeView(
                id=badge.id,
                name=badge.name,
                description=badge.description,
                earned_at=badge.earned_at,
            )
            for badge in facts.badges
        ],
        books=[
            BookProgressView(
                storybook_id=book.storybook_id,
                title=book.title,
                endings_found=book.endings_found,
                total_endings=book.total_endings,
                finished=book.finished,
                every_path_walked=book.every_path_walked,
            )
            for book in facts.books
        ],
        totals=ProgressTotalsView(
            books_finished=facts.totals.books_finished,
            endings_found=facts.totals.endings_found,
        ),
    )
