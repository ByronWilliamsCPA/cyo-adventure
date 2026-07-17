"""Reading-history read endpoints (register K6/G9; debt U5).

``Completion`` and ``ReadingState`` rows are written by ``api/reading.py`` but,
until this module, nothing read them back. Two consumers need a read path:

* K6, the kid endings tracker ("found 3 of 7 endings" per book):
  ``GET /reading-history/{profile_id}``.
* G9, guardian engagement visibility (per-child activity signals, never
  reading content): ``GET /families/me/reading-summary``.

Both endpoints are read-only projections over existing rows; neither writes
anything. The privacy model for G9 is signals, not surveillance: the family
summary carries counts and timestamps only, no story titles, node ids, or
choice content.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

from fastapi import APIRouter
from sqlalchemy import select, tuple_

from cyo_adventure.api.deps import CurrentPrincipal, DbSession, authorize_profile
from cyo_adventure.api.schemas import (
    ChildEngagementItem,
    FamilyReadingSummaryView,
    ReadingHistoryItem,
    ReadingHistoryView,
)
from cyo_adventure.core.exceptions import AuthorizationError, ValidationError
from cyo_adventure.db.models import (
    ChildProfile,
    Completion,
    ReadingState,
    Storybook,
    StorybookVersion,
)
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

_logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["reading-history"])

_KeyT = TypeVar("_KeyT")


def _bump(acc: dict[_KeyT, datetime], key: _KeyT, value: datetime) -> None:
    """Keep the maximum timestamp seen for ``key`` in ``acc``.

    Generic over the key type: callers key by storybook id (a ``str``) or
    child profile id (a ``uuid.UUID``).

    Args:
        acc: The accumulator, mutated in place.
        key: The storybook or profile id.
        value: The candidate timestamp.
    """
    current = acc.get(key)
    if current is None or value > current:
        acc[key] = value


def _parse_profile_id(raw: str) -> uuid.UUID:
    """Parse a profile id, raising a 422-mapped error on bad input.

    Args:
        raw: The raw profile id string.

    Returns:
        uuid.UUID: The parsed id.

    Raises:
        ValidationError: If the value is not a valid UUID.
    """
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        msg = "profile_id must be a UUID"
        raise ValidationError(msg, field="profile_id", value=raw) from exc


def _book_title(blob: Mapping[str, object], storybook_id: str) -> str:
    """Return the blob's title, falling back to the storybook id.

    Args:
        blob: The pinned version's stored Storybook content blob.
        storybook_id: The story id (title fallback).

    Returns:
        str: ``blob["title"]`` when it is a non-empty string, else ``storybook_id``.
    """
    title = blob.get("title")
    return title if isinstance(title, str) and title else storybook_id


def _ending_count(blob: Mapping[str, object], storybook_id: str, version: int) -> int:
    """Return the pinned version's declared ending count, defaulting to 0.

    # #ASSUME: data integrity: ``metadata.ending_count`` is enforced to equal
    # the story's real ending count at validation time (validator/layer1.py
    # L1-7), so a published version's value is trustworthy. A missing or
    # malformed field still degrades to 0 (never raises) so one corrupt row
    # cannot 500 the whole history/summary listing, mirroring library.py's
    # defensive metadata reads.
    # #VERIFY: a malformed value is logged, not silently swallowed.

    Args:
        blob: The pinned version's stored Storybook content blob.
        storybook_id: The story id, for the warning log.
        version: The pinned version number, for the warning log.

    Returns:
        int: The declared ending count, or 0 if absent/malformed.
    """
    metadata = blob.get("metadata")
    if not isinstance(metadata, dict):
        return 0
    count = metadata.get("ending_count")
    if isinstance(count, int) and not isinstance(count, bool):
        return count
    if count is not None:
        _logger.warning(
            "reading_history_malformed_ending_count",
            storybook_id=storybook_id,
            version=version,
        )
    return 0


def _is_ending_node(blob: Mapping[str, object], node_id: str) -> bool:
    """Return whether ``node_id`` is a terminal (ending) node in ``blob``.

    # #ASSUME: data integrity: a node absent from a malformed/truncated
    # ``nodes`` list, or a ``node_id`` that no longer exists in the pinned
    # version, defaults to "not an ending" (matching the Node model's own
    # ``is_ending: bool = False`` default), so ``in_progress`` stays True
    # rather than falsely reporting a book as finished.
    # #VERIFY: tests/unit/test_reading_history_api_unit.py covers a missing
    # node id and a non-list ``nodes`` field.

    Args:
        blob: The stored Storybook content blob for the state's pinned version.
        node_id: The reading state's ``current_node``.

    Returns:
        bool: ``True`` only if a matching node is found with ``is_ending`` set.
    """
    nodes = blob.get("nodes")
    if not isinstance(nodes, list):
        return False
    for node in nodes:
        if isinstance(node, dict) and node.get("id") == node_id:
            return node.get("is_ending") is True
    return False


@router.get("/reading-history/{profile_id}")
async def get_reading_history(
    profile_id: str,
    principal: CurrentPrincipal,
    session: DbSession,
) -> ReadingHistoryView:
    """Return a profile's per-storybook reading history (K6 endings tracker).

    Args:
        profile_id: The child profile whose history is requested.
        principal: The authenticated principal.
        session: The request session.

    Returns:
        ReadingHistoryView: One row per storybook the profile has any
        ``Completion`` or ``ReadingState`` row for.

    Raises:
        ValidationError: If ``profile_id`` is not a UUID.
        AuthorizationError: If a non-admin principal does not own the profile.
    """
    # #CRITICAL: security: mirrors library.py::list_library's gate exactly
    # (authorize_profile), widened with an explicit admin bypass so a global
    # admin may read any profile's history (register K6/G9 spec: "admin
    # any"), same shape as get_storybook_version's `if not principal.is_admin`
    # branch in library.py.
    # #VERIFY: tests/unit/test_reading_history_api_unit.py::
    # test_child_cannot_read_another_profile_history and
    # test_admin_reads_any_profile_history.
    parsed = _parse_profile_id(profile_id)
    if not principal.is_admin:
        authorize_profile(principal, parsed)

    completion_rows = list(
        await session.scalars(
            select(Completion).where(Completion.child_profile_id == parsed)
        )
    )
    state_rows = list(
        await session.scalars(
            select(ReadingState).where(ReadingState.child_profile_id == parsed)
        )
    )
    if not completion_rows and not state_rows:
        return ReadingHistoryView(profile_id=str(parsed), books=[])

    endings_by_book: dict[str, set[str]] = {}
    last_completion_by_book: dict[str, datetime] = {}
    for completion in completion_rows:
        endings_by_book.setdefault(completion.storybook_id, set()).add(
            completion.ending_id
        )
        _bump(last_completion_by_book, completion.storybook_id, completion.found_at)

    states_by_book: dict[str, ReadingState] = {
        state.storybook_id: state for state in state_rows
    }
    book_ids = set(endings_by_book) | set(states_by_book)

    # #ASSUME: external resources: one bulk Storybook fetch and one bulk
    # StorybookVersion fetch cover every book this profile has touched, so
    # the listing stays a fixed four queries total regardless of library
    # size (no N+1 over blobs), mirroring library.py::list_library.
    # #VERIFY: tests/unit/test_reading_history_api_unit.py asserts exactly
    # four session.scalars() calls on the happy path.
    books = {
        book.id: book
        for book in await session.scalars(
            select(Storybook).where(Storybook.id.in_(book_ids))
        )
    }

    version_keys: set[tuple[str, int]] = set()
    for book_id, book in books.items():
        if book.current_published_version is not None:
            version_keys.add((book_id, book.current_published_version))
    for book_id, state in states_by_book.items():
        version_keys.add((book_id, state.version))

    versions: dict[tuple[str, int], StorybookVersion] = {}
    if version_keys:
        version_rows = await session.scalars(
            select(StorybookVersion).where(
                tuple_(StorybookVersion.storybook_id, StorybookVersion.version).in_(
                    version_keys
                )
            )
        )
        versions = {(row.storybook_id, row.version): row for row in version_rows}

    items = [
        _history_item(
            book_id,
            books.get(book_id),
            versions,
            _BookActivity(
                state=states_by_book.get(book_id),
                found_endings=endings_by_book.get(book_id, set()),
                last_completion_at=last_completion_by_book.get(book_id),
            ),
        )
        for book_id in book_ids
    ]
    # Stable two-pass sort: newest activity first, storybook id breaks ties.
    items.sort(key=lambda item: item.storybook_id)
    items.sort(key=lambda item: item.last_activity_at, reverse=True)
    return ReadingHistoryView(profile_id=str(parsed), books=items)


@dataclass(frozen=True, slots=True)
class _BookActivity:
    """This profile's per-storybook activity, pre-aggregated from raw rows.

    Bundled into one value so ``_history_item`` stays within the project's
    argument-count lint budget (PLR0913).

    Attributes:
        state: This profile's ``ReadingState`` row for the book, or ``None``.
        found_endings: The distinct ending ids this profile has completed.
        last_completion_at: The most recent completion timestamp, or ``None``.
    """

    state: ReadingState | None
    found_endings: set[str]
    last_completion_at: datetime | None


def _history_item(
    book_id: str,
    book: Storybook | None,
    versions: dict[tuple[str, int], StorybookVersion],
    activity: _BookActivity,
) -> ReadingHistoryItem:
    """Build one ``ReadingHistoryItem`` from the pre-loaded per-book rows.

    # #EDGE: data integrity: a book with no current published version (never
    # published, or archived) has no pinned version to read title/ending_count
    # from; title falls back to the storybook id and total_endings is 0. This
    # is expected for a book read under a version that was later archived.
    # #VERIFY: tests/unit/test_reading_history_api_unit.py::
    # test_book_with_no_current_published_version_degrades.

    Args:
        book_id: The storybook id.
        book: The ``Storybook`` row, or ``None`` if it vanished (defensive;
            a completion/state always cites a real storybook via its FK, so
            this is belt-and-suspenders against a concurrent hard delete).
        versions: All loaded ``StorybookVersion`` rows, keyed by
            ``(storybook_id, version)``.
        activity: This profile's pre-aggregated state/completions for the book.

    Returns:
        ReadingHistoryItem: The assembled row.
    """
    state = activity.state
    pinned_version = book.current_published_version if book is not None else None
    pinned_row = (
        versions.get((book_id, pinned_version)) if pinned_version is not None else None
    )
    title = _book_title(pinned_row.blob, book_id) if pinned_row is not None else book_id
    total_endings = (
        _ending_count(pinned_row.blob, book_id, pinned_version)
        if pinned_row is not None and pinned_version is not None
        else 0
    )

    in_progress = False
    if state is not None:
        state_row = versions.get((book_id, state.version))
        # #ASSUME: data integrity: a reading state always cites a real,
        # persisted version via its composite FK (models.py), so state_row
        # should never be None here; treat a defensive miss as "not an
        # ending" (in_progress True) rather than raising.
        # #VERIFY: the composite ForeignKeyConstraint on ReadingState.
        in_progress = state_row is None or not _is_ending_node(
            state_row.blob, state.current_node
        )

    candidates = [
        t
        for t in (
            state.updated_at if state is not None else None,
            activity.last_completion_at,
        )
        if t is not None
    ]
    # #CRITICAL: data integrity: book_id only ever reaches this function via
    # `book_ids = set(endings_by_book) | set(states_by_book)`, so at least one
    # of state/last_completion_at is always set; `max()` on an empty list
    # would raise ValueError and 500 the whole listing.
    # #VERIFY: test_history_item_always_has_at_least_one_activity_timestamp.
    last_activity_at = max(candidates)

    return ReadingHistoryItem(
        storybook_id=book_id,
        title=title,
        endings_found=len(activity.found_endings),
        ending_ids=sorted(activity.found_endings),
        total_endings=total_endings,
        in_progress=in_progress,
        last_activity_at=last_activity_at,
    )


@router.get("/families/me/reading-summary")
async def get_family_reading_summary(
    principal: CurrentPrincipal,
    session: DbSession,
) -> FamilyReadingSummaryView:
    """Return per-child engagement signals for the caller's own family (G9).

    Args:
        principal: The authenticated principal.
        session: The request session.

    Returns:
        FamilyReadingSummaryView: One row per child profile in the caller's
        family, ordered like ``profiles.py::list_profiles`` (creation order).

    Raises:
        AuthorizationError: If the caller is neither a guardian nor an admin.
    """
    # #CRITICAL: security: "me" is always the CALLER's own family_id, never a
    # client-supplied id, so there is no cross-family parameter to IDOR; a
    # child token is rejected outright (this is an engagement-visibility
    # surface for the adults in the family, not a kid-facing one).
    # #VERIFY: tests/unit/test_reading_history_api_unit.py::
    # test_child_cannot_read_family_summary.
    if not (principal.is_guardian or principal.is_admin):
        msg = "guardian or admin role required"
        raise AuthorizationError(msg)

    profiles = list(
        await session.scalars(
            select(ChildProfile)
            .where(ChildProfile.family_id == principal.family_id)
            .order_by(ChildProfile.created_at.asc(), ChildProfile.id.asc())
        )
    )
    if not profiles:
        return FamilyReadingSummaryView(children=[])

    profile_ids = [p.id for p in profiles]
    # #ASSUME: external resources: two bulk queries (states, completions)
    # scoped to the whole family's profile ids cover every child in one
    # round-trip each, regardless of family size (no N+1 per child).
    # #VERIFY: tests/unit/test_reading_history_api_unit.py asserts exactly
    # three session.scalars() calls (profiles, states, completions).
    state_rows = list(
        await session.scalars(
            select(ReadingState).where(ReadingState.child_profile_id.in_(profile_ids))
        )
    )
    completion_rows = list(
        await session.scalars(
            select(Completion).where(Completion.child_profile_id.in_(profile_ids))
        )
    )

    started: dict[uuid.UUID, set[str]] = {}
    activity: dict[uuid.UUID, datetime] = {}
    for state in state_rows:
        started.setdefault(state.child_profile_id, set()).add(state.storybook_id)
        _bump(activity, state.child_profile_id, state.updated_at)

    finished: dict[uuid.UUID, set[str]] = {}
    endings_found: dict[uuid.UUID, int] = {}
    for completion in completion_rows:
        started.setdefault(completion.child_profile_id, set()).add(
            completion.storybook_id
        )
        finished.setdefault(completion.child_profile_id, set()).add(
            completion.storybook_id
        )
        endings_found[completion.child_profile_id] = (
            endings_found.get(completion.child_profile_id, 0) + 1
        )
        _bump(activity, completion.child_profile_id, completion.found_at)

    children = [
        ChildEngagementItem(
            profile_id=str(profile.id),
            display_name=profile.display_name,
            books_started=len(started.get(profile.id, set())),
            books_finished=len(finished.get(profile.id, set())),
            total_endings_found=endings_found.get(profile.id, 0),
            last_activity_at=activity.get(profile.id),
        )
        for profile in profiles
    ]
    return FamilyReadingSummaryView(children=children)
