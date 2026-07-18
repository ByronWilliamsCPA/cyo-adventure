"""Library and story-fetch endpoints.

A child sees only published stories in their own family, plus any
visibility='catalog' story assigned to their profile (WS-E Task 13). Per-profile
age-band and reading-level cap filtering is a Phase 4a concern; Phase 1 lists
every published story in the family (or the catalog) and enforces
profile/family/assignment access. Listing additionally requires admin approval:
only versions whose ``approved_by IS NOT NULL`` (the recorded human approver)
are returned. Story fetch returns the immutable Storybook JSON blob for a
specific version: a global admin may read any version cross-family (to review
drafts), a visibility='catalog' book is readable cross-family too, while a
guardian or child otherwise receives 404 (not 403, so a draft's existence is not
revealed) for any unpublished, unapproved, or non-current version.
"""

from __future__ import annotations

import math
import uuid
from typing import TYPE_CHECKING, TypeGuard

from fastapi import APIRouter
from sqlalchemy import and_, exists, or_, select, tuple_

from cyo_adventure.api.deps import (
    CurrentPrincipal,
    DbSession,
    Role,
    authorize_family,
    authorize_profile,
)
from cyo_adventure.api.schemas import (
    LibraryItem,
    LibraryProgress,
    LibraryView,
    error_responses,
)
from cyo_adventure.core.exceptions import ResourceNotFoundError, ValidationError
from cyo_adventure.db.models import (
    Rating,
    ReadingState,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
)
from cyo_adventure.publishing.state_machine import Visibility
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Mapping

_logger = get_logger(__name__)

router = APIRouter(
    prefix="/api/v1", tags=["library"], responses=error_responses(401, 403)
)

_PUBLISHED = "published"


def _is_real_number(value: object) -> TypeGuard[int | float]:
    """Return whether value is a real int/float (a bool is rejected).

    Args:
        value: The candidate metadata value.

    Returns:
        TypeGuard[int | float]: ``True`` for an ``int`` or ``float`` that is not
        a ``bool``, narrowing the value for the caller.
    """
    # bool is a subclass of int in Python; a True/False slipped into a numeric
    # metadata field must not read as 1/0.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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


def _str_field(raw: object, default: str, field: str, malformed: list[str]) -> str:
    """Return a string field, recording a fallback when the value is malformed.

    Args:
        raw: The raw value from the blob.
        default: The fallback when ``raw`` is not a string.
        field: The field name, appended to ``malformed`` on a non-null fallback.
        malformed: The accumulator of malformed field names (mutated).

    Returns:
        str: ``raw`` if it is a string, else ``default``.
    """
    if isinstance(raw, str):
        return raw
    if raw is not None:
        malformed.append(field)
    return default


def _tier_field(raw: object, malformed: list[str]) -> int:
    """Return the tier int, rejecting bool and recording a fallback otherwise.

    Args:
        raw: The raw ``tier`` value.
        malformed: The accumulator of malformed field names (mutated).

    Returns:
        int: ``raw`` if it is a non-bool int, else 0.
    """
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    if raw is not None:
        malformed.append("tier")
    return 0


def _reading_level_target(meta: Mapping[str, object], malformed: list[str]) -> float:
    """Return a finite reading-level target, recording any malformed input.

    A non-dict ``reading_level``, a non-numeric or bool ``target``, or a
    non-finite float (NaN/Inf) all fall back to 0.0 and record the field. The
    finite guard matters because Starlette serializes with ``allow_nan=False``,
    so a single NaN/Inf would 500 the whole listing.

    Args:
        meta: The metadata mapping.
        malformed: The accumulator of malformed field names (mutated).

    Returns:
        float: A finite target, or 0.0 on any malformed input.
    """
    reading_level = meta.get("reading_level")
    if not isinstance(reading_level, dict):
        if reading_level is not None:
            malformed.append("reading_level")
        return 0.0
    raw_target = reading_level.get("target")
    if _is_real_number(raw_target):
        candidate = float(raw_target)
        if math.isfinite(candidate):
            return candidate
    if raw_target is not None:
        malformed.append("reading_level.target")
    return 0.0


def _node_count(blob: Mapping[str, object], malformed: list[str]) -> int:
    """Return the number of story nodes, recording a malformed ``nodes`` field.

    Args:
        blob: The stored Storybook content blob.
        malformed: The accumulator of malformed field names (mutated).

    Returns:
        int: The node count, or 0 if ``nodes`` is missing or not a list.
    """
    nodes = blob.get("nodes")
    if isinstance(nodes, list):
        return len(nodes)
    if nodes is not None:
        malformed.append("nodes")
    return 0


def _current_node_is_ending(blob: Mapping[str, object], current_node: str) -> bool:
    """Return True when ``current_node`` is an ending node in the blob (UX-K5).

    Read-only over the already-loaded blob: no extra query. A branching story
    touches only a fraction of its nodes, so "reached an ending" is the honest
    signal for "finished", not visit-count / total-node-count.
    """
    nodes = blob.get("nodes")
    if not isinstance(nodes, list):
        return False
    for node in nodes:
        if isinstance(node, dict) and node.get("id") == current_node:
            return bool(node.get("is_ending", False))
    return False


def _library_item(
    storybook_id: str,
    blob: Mapping[str, object],
    version: int,
    *,
    rating: int | None = None,
    state: ReadingState | None = None,
    series_id: str | None = None,
    book_index: int | None = None,
    cover_url: str | None = None,
) -> LibraryItem:
    """Build a library item from a stored Storybook blob.

    Every field is read defensively: a malformed value falls back to a safe
    default rather than propagating into the response. A non-finite reading
    level (NaN/Inf) is rejected too, because Starlette serializes with
    ``allow_nan=False`` and a single bad float would 500 the whole listing.

    Args:
        storybook_id: The story id (also the title fallback).
        blob: The stored Storybook content blob.
        version: The published version number.
        rating: The profile's 1-5 rating of this story, if any.
        state: The profile's saved reading state for this story, if any.
        series_id: The book's series, or None for a standalone story (WS-B
            PR 3). Sourced from the ``Storybook`` row, not the blob.
        book_index: The book's 1-based position in its series, or None.
        cover_url: The generated cover image URL, or None if not yet
            generated. Sourced from ``StorybookVersion.cover_image_url``.

    Returns:
        LibraryItem: The listing item with safe, finite, correctly typed fields.
    """
    # #ASSUME: data integrity: an APPROVED published blob is well-formed, but a
    # malformed metadata field (wrong type, bool-as-number, NaN/Inf) must degrade
    # to a default AND surface a warning rather than 500 the listing silently.
    # #VERIFY: every fallback appends to ``malformed`` and emits one structured
    # warning; non-finite floats are caught by math.isfinite in the helper.
    metadata = blob.get("metadata")
    meta: Mapping[str, object] = metadata if isinstance(metadata, dict) else {}
    malformed: list[str] = []

    title = _str_field(blob.get("title"), storybook_id, "title", malformed)
    age_band = _str_field(meta.get("age_band"), "", "age_band", malformed)
    tier = _tier_field(meta.get("tier"), malformed)
    target = _reading_level_target(meta, malformed)
    node_count = _node_count(blob, malformed)

    if malformed:
        _logger.warning(
            "library_item_malformed_metadata",
            storybook_id=storybook_id,
            version=version,
            fields=malformed,
        )

    progress: LibraryProgress | None = None
    if state is not None:
        # #EDGE: data integrity: the saved state may be pinned to an older
        # version than the currently published one, so nodes_visited can exceed
        # node_count after a republish; the frontend clamps percent at 100.
        # #VERIFY: frontend bookCardUtils.percentComplete clamps at 100.
        visit_set = state.visit_set if isinstance(state.visit_set, list) else []
        progress = LibraryProgress(
            current_node=state.current_node,
            nodes_visited=len(visit_set),
            updated_at=state.updated_at,
            completed=_current_node_is_ending(blob, state.current_node),
        )

    return LibraryItem(
        id=storybook_id,
        title=title,
        version=version,
        age_band=age_band,
        tier=tier,
        reading_level_target=target,
        node_count=node_count,
        rating=rating,
        progress=progress,
        series_id=series_id,
        book_index=book_index,
        cover_url=cover_url,
    )


@router.get("/library")
async def list_library(
    profile_id: str,
    principal: CurrentPrincipal,
    session: DbSession,
) -> LibraryView:
    """List published stories visible to the given profile.

    Args:
        profile_id: The child profile requesting its library.
        principal: The authenticated principal.
        session: The request session.

    Returns:
        LibraryView: The published stories in the profile's family.
    """
    # #CRITICAL: security: the library includes the principal's own family AND
    # any visibility='catalog' book (WS-E Task 13: a cross-family catalog book
    # must be listable once assigned), the requested profile is authorized,
    # only APPROVED published versions are listed, AND the story must be
    # assigned to this profile (the read-path leg of the no-unpermitted-story
    # invariant); the assignment EXISTS clause is the gate for catalog books
    # too, unchanged by this widening.
    # #VERIFY: the join requires approved_by IS NOT NULL; the EXISTS requires a
    # storybook_assignment row for (this story, this profile).
    parsed = _parse_profile_id(profile_id)
    authorize_profile(principal, parsed)
    rows = await session.scalars(
        select(Storybook)
        .join(
            StorybookVersion,
            and_(
                StorybookVersion.storybook_id == Storybook.id,
                StorybookVersion.version == Storybook.current_published_version,
            ),
        )
        .where(
            or_(
                Storybook.family_id == principal.family_id,
                Storybook.visibility == Visibility.CATALOG.value,
            ),
            Storybook.status == _PUBLISHED,
            Storybook.current_published_version.is_not(None),
            StorybookVersion.approved_by.is_not(None),
            exists().where(
                StorybookAssignment.storybook_id == Storybook.id,
                StorybookAssignment.child_profile_id == parsed,
            ),
        )
    )
    books = [
        (book.id, book.current_published_version, book.series_id, book.book_index)
        for book in rows.all()
        if book.current_published_version is not None
    ]
    if not books:
        return LibraryView(stories=[])
    # #ASSUME: external resources: load every published version in one query to
    # avoid an N+1 round-trip per story as a family's library grows.
    # #VERIFY: a composite (storybook_id, version) IN filter selects only the
    # published rows.
    version_rows = await session.scalars(
        select(StorybookVersion).where(
            tuple_(StorybookVersion.storybook_id, StorybookVersion.version).in_(
                [(b[0], b[1]) for b in books]
            )
        )
    )
    blobs: dict[tuple[str, int], dict[str, object]] = {}
    covers: dict[tuple[str, int], str | None] = {}
    for row in version_rows:
        blobs[(row.storybook_id, row.version)] = row.blob
        covers[(row.storybook_id, row.version)] = row.cover_image_url
    book_ids = [b[0] for b in books]
    # #ASSUME: external resources: per-profile state and ratings load in one
    # bulk query each (not per-book) so the listing stays two+2 queries total.
    # #VERIFY: both filters use IN on the published book ids and the single
    # authorized profile id.
    state_rows = await session.scalars(
        select(ReadingState).where(
            ReadingState.child_profile_id == parsed,
            ReadingState.storybook_id.in_(book_ids),
        )
    )
    states = {row.storybook_id: row for row in state_rows}
    rating_rows = await session.scalars(
        select(Rating).where(
            Rating.child_profile_id == parsed,
            Rating.storybook_id.in_(book_ids),
        )
    )
    ratings = {row.storybook_id: row.value for row in rating_rows}
    items = [
        _library_item(
            storybook_id,
            blobs[(storybook_id, version)],
            version,
            rating=ratings.get(storybook_id),
            state=states.get(storybook_id),
            series_id=str(series_id) if series_id is not None else None,
            book_index=book_index,
            cover_url=covers.get((storybook_id, version)),
        )
        for storybook_id, version, series_id, book_index in books
        if (storybook_id, version) in blobs
    ]
    return LibraryView(stories=items)


@router.get(
    "/storybooks/{storybook_id}/versions/{version}",
    responses=error_responses(404),
)
async def get_storybook_version(
    storybook_id: str,
    version: int,
    principal: CurrentPrincipal,
    session: DbSession,
) -> dict[str, object]:
    """Return the immutable Storybook JSON for a specific version.

    Args:
        storybook_id: The story id.
        version: The story version.
        principal: The authenticated principal.
        session: The request session.

    Returns:
        dict[str, object]: The Storybook content blob.

    Raises:
        ResourceNotFoundError: If the story or version does not exist.
    """
    book = await session.get(Storybook, storybook_id)
    if book is None:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    # #CRITICAL: security: a global admin may read any version of any family (to
    # review drafts). A visibility='catalog' book is readable cross-family too
    # (WS-E Task 13: guardian preview parity with the content-summary endpoint;
    # a child still needs the StorybookAssignment row checked below). Otherwise
    # a guardian or child is scoped to their own family and may read ONLY the
    # approved, published, current version; 404 (not 403) so a draft's
    # existence is not revealed.
    # #VERIFY: non-admin, non-catalog, cross-family -> 403; non-admin +
    # (unpublished | non-current | unapproved) -> 404; admin -> any blob.
    if not principal.is_admin and book.visibility != Visibility.CATALOG.value:
        authorize_family(principal, book.family_id)
    version_row = await session.get(StorybookVersion, (storybook_id, version))
    if version_row is None:
        msg = f"version {version} of storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    if not principal.is_admin and (
        book.status != _PUBLISHED
        or book.current_published_version != version
        or version_row.approved_by is None
    ):
        msg = f"version {version} of storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    # #CRITICAL: security: a child may fetch a story blob directly ONLY if it is
    # assigned to their profile; an unassigned (but published+approved) book is
    # 404 (existence hidden), matching the library-listing gate. A DEVICE
    # principal is routed through the SAME gate: it carries no profile_ids
    # (enforced in Principal.__post_init__), so the assignment lookup matches
    # nothing and every direct blob read is 404. Content reaches a device only
    # after it mints a child session, which then reads under its own assignment
    # scope; the device grant itself never reads story content. Guardian and
    # admin reads are unchanged (they skip this branch).
    # #VERIFY: child + unassigned -> 404; child + assigned -> blob; device -> 404.
    if principal.role in (Role.CHILD, Role.DEVICE):
        assigned = await session.scalar(
            select(StorybookAssignment.storybook_id).where(
                StorybookAssignment.storybook_id == storybook_id,
                StorybookAssignment.child_profile_id.in_(principal.profile_ids),
            )
        )
        if assigned is None:
            msg = f"version {version} of storybook '{storybook_id}' not found"
            raise ResourceNotFoundError(msg)
    return version_row.blob
