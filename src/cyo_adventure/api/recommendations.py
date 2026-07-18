"""K17 recommendation feed: ring 1 (family) and ring 2 (connected families).

ADR-016 replaces the flat "no social features" exclusion with three rings; this
module implements the two that are backend-servable today. Ring 1: within a
profile's own family, another profile's 4-5 star rating on a book the caller
can already see is a recommendation, no consent needed (the family is the
trust boundary). Ring 2: a rating from a profile in a family with an ACTIVE,
dual-guardian-consented ``FamilyConnection`` where the caller's family is the
viewer. Ring 3 (anonymized global aggregate) is not built; nothing here
approximates it.

This is the ENFORCED guard register G17's note calls for: PR #267 shipped the
connection substrate with the constraint holding "by omission" (nothing read
it, so it never leaked); this module is the first reader, and it never treats
a connection as live without checking both consent columns explicitly (see
``_dual_consented_connected_family_ids``'s #CRITICAL tag below).

A recommendation payload is intentionally minimal: a book pointer, a rating,
and a recommender display name. No free text, no other profile attribute
(age band, reading level, content flags) ever leaves this module.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter
from sqlalchemy import and_, exists, or_, select, tuple_

from cyo_adventure.api.deps import CurrentPrincipal, DbSession, authorize_profile
from cyo_adventure.api.schemas import RecommendationItem, RecommendationsView
from cyo_adventure.core.exceptions import ResourceNotFoundError, ValidationError
from cyo_adventure.db.models import (
    ChildProfile,
    FamilyConnection,
    Rating,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
)
from cyo_adventure.publishing.state_machine import Visibility

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1", tags=["recommendations"])

_PUBLISHED = "published"
# ADR-016 Decision section, ring 1/ring 2: "ratings >= 4" is the recommendation
# threshold; K18's 1-5 scale keeps 4 and 5 as the "loved it" band.
_MIN_RECOMMENDATION_RATING = 4


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

    Mirrors ``reading_history.py::_book_title``; duplicated rather than
    imported across the module boundary (both are small, private helpers on
    the same stored-blob shape).

    Args:
        blob: The pinned version's stored Storybook content blob.
        storybook_id: The story id (title fallback).

    Returns:
        str: ``blob["title"]`` when it is a non-empty string, else ``storybook_id``.
    """
    title = blob.get("title")
    return title if isinstance(title, str) and title else storybook_id


async def _visible_books(
    session: AsyncSession, profile_id: uuid.UUID, family_id: uuid.UUID
) -> dict[str, int]:
    """Return the published-version map of every book this profile can see.

    Mirrors ``library.py::list_library``'s own gate exactly: published,
    approved, current version, (this profile's family OR catalog visibility),
    and assigned to this specific profile. A cross-family (ring 2) book only
    ever reaches this profile through the catalog + assignment path, the same
    surface a guardian already uses to assign a cross-family catalog book.

    Args:
        session: The request session.
        profile_id: The child profile whose visible-book set is computed.
        family_id: The profile's own family id.

    Returns:
        dict[str, int]: storybook_id -> current published version, for every
        book this profile is authorized to see.
    """
    rows = await session.execute(
        select(Storybook.id, Storybook.current_published_version)
        .join(
            StorybookVersion,
            and_(
                StorybookVersion.storybook_id == Storybook.id,
                StorybookVersion.version == Storybook.current_published_version,
            ),
        )
        .where(
            or_(
                Storybook.family_id == family_id,
                Storybook.visibility == Visibility.CATALOG.value,
            ),
            Storybook.status == _PUBLISHED,
            Storybook.current_published_version.is_not(None),
            StorybookVersion.approved_by.is_not(None),
            exists().where(
                StorybookAssignment.storybook_id == Storybook.id,
                StorybookAssignment.child_profile_id == profile_id,
            ),
        )
    )
    return {
        storybook_id: version
        for storybook_id, version in rows.all()
        if version is not None
    }


def _is_dual_consented(connection: FamilyConnection) -> bool:
    """Return whether both guardians have actively consented (ADR-016).

    Mirrors ``family_connections.py::_is_active`` exactly; duplicated rather
    than imported, since that function is private to its own module's route
    handlers (same small-helper-duplication convention as ``_book_title``
    above).

    Args:
        connection: The connection row.

    Returns:
        bool: ``True`` only when both ``consented_by_viewer_user_id`` and
        ``consented_by_sharer_user_id`` are set.
    """
    return (
        connection.consented_by_viewer_user_id is not None
        and connection.consented_by_sharer_user_id is not None
    )


async def _dual_consented_connected_family_ids(
    session: AsyncSession, family_id: uuid.UUID
) -> set[uuid.UUID]:
    """Return the sharer families whose ring-2 recommendations may be read.

    Args:
        session: The request session.
        family_id: The caller's family id (the would-be viewer).

    Returns:
        set[uuid.UUID]: ``connected_family_id`` for every ``FamilyConnection``
        row where ``family_id`` is the viewer AND both the viewer-side and
        sharer-side guardian have actively consented.
    """
    # #CRITICAL: security: ADR-016's Decision section is explicit that ring 2
    # requires ACTIVE consent from BOTH families' guardians; a connection row
    # existing (PR #267's admin CRUD) is a permission edge only, never
    # consent (register G17's "held by omission" note this module retires).
    # Every outgoing connection row is fetched first (no consent predicate in
    # the SQL), then ``_is_dual_consented`` is applied as an explicit Python
    # boolean per row: a connection missing either consent is provably
    # excluded by a plain, directly unit-testable check, not a WHERE clause a
    # future edit could silently loosen.
    # #VERIFY: tests/unit/test_recommendations_api_unit.py::
    # test_connection_missing_sharer_consent_contributes_nothing and
    # test_connection_missing_viewer_consent_contributes_nothing.
    rows = await session.scalars(
        select(FamilyConnection).where(FamilyConnection.family_id == family_id)
    )
    return {row.connected_family_id for row in rows if _is_dual_consented(row)}


@router.get("/recommendations/{profile_id}")
async def get_recommendations(
    profile_id: str,
    principal: CurrentPrincipal,
    session: DbSession,
) -> RecommendationsView:
    """Return a profile's book recommendations (ADR-016 rings 1-2).

    Args:
        profile_id: The child profile requesting recommendations.
        principal: The authenticated principal.
        session: The request session.

    Returns:
        RecommendationsView: Every 4-5 star rating from another profile, in
        the caller's own family (ring 1) or an actively dual-consented
        connected family where the caller's family is the viewer (ring 2), on
        a book this profile can already see. Sorted highest rating first,
        then title, for a stable feed order.

    Raises:
        ValidationError: If ``profile_id`` is not a UUID.
        AuthorizationError: If a non-admin principal does not own the profile
            (mirrors ``reading_history.py::get_reading_history``: child own
            profile, guardian family, admin any).
        ResourceNotFoundError: If no profile with this id exists (404).
    """
    parsed = _parse_profile_id(profile_id)
    if not principal.is_admin:
        authorize_profile(principal, parsed)

    profile = await session.get(ChildProfile, parsed)
    if profile is None:
        msg = f"profile '{profile_id}' not found"
        raise ResourceNotFoundError(msg)
    family_id = profile.family_id

    visible = await _visible_books(session, parsed, family_id)
    if not visible:
        return RecommendationsView(items=[])

    version_rows = await session.scalars(
        select(StorybookVersion).where(
            tuple_(StorybookVersion.storybook_id, StorybookVersion.version).in_(
                list(visible.items())
            )
        )
    )
    titles: dict[str, str] = {}
    covers: dict[str, str | None] = {}
    for row in version_rows:
        titles[row.storybook_id] = _book_title(row.blob, row.storybook_id)
        covers[row.storybook_id] = row.cover_image_url

    # Ring 1: every OTHER profile in the caller's own family.
    family_rater_ids = set(
        await session.scalars(
            select(ChildProfile.id).where(
                ChildProfile.family_id == family_id,
                ChildProfile.id != parsed,
            )
        )
    )

    # Ring 2: profiles in families with an ACTIVE dual-consented connection
    # where the caller's family is the viewer. An empty set here (no
    # connection, or one missing either consent) contributes zero raters,
    # not a partial/empty-but-present set of recommendations.
    connected_family_ids = await _dual_consented_connected_family_ids(
        session, family_id
    )
    connection_rater_ids: set[uuid.UUID] = set()
    if connected_family_ids:
        connection_rater_ids = set(
            await session.scalars(
                select(ChildProfile.id).where(
                    ChildProfile.family_id.in_(connected_family_ids)
                )
            )
        )

    rater_ids = family_rater_ids | connection_rater_ids
    if not rater_ids:
        return RecommendationsView(items=[])

    rating_rows = list(
        await session.scalars(
            select(Rating).where(
                Rating.storybook_id.in_(visible.keys()),
                Rating.child_profile_id.in_(rater_ids),
                Rating.value >= _MIN_RECOMMENDATION_RATING,
                # #ASSUME: data integrity: family_rater_ids/connection_rater_ids
                # are already built to exclude `parsed` (ring 1 by construction;
                # ring 2 by family disjointness), so this is belt-and-suspenders
                # against a future change to either set, not the sole guard.
                # #VERIFY: tests/unit/test_recommendations_api_unit.py::
                # test_own_rating_excluded.
                Rating.child_profile_id != parsed,
            )
        )
    )
    if not rating_rows:
        return RecommendationsView(items=[])

    rater_rows = await session.scalars(
        select(ChildProfile).where(
            ChildProfile.id.in_({r.child_profile_id for r in rating_rows})
        )
    )
    raters = {p.id: p for p in rater_rows}

    items: list[RecommendationItem] = []
    for rating in rating_rows:
        rater = raters.get(rating.child_profile_id)
        if rater is None:
            continue
        ring = "family" if rater.family_id == family_id else "connection"
        items.append(
            RecommendationItem(
                storybook_id=rating.storybook_id,
                title=titles.get(rating.storybook_id, rating.storybook_id),
                cover_url=covers.get(rating.storybook_id),
                recommender_name=rater.display_name,
                rating=rating.value,
                ring=ring,
            )
        )
    items.sort(key=lambda item: (-item.rating, item.title, item.storybook_id))
    return RecommendationsView(items=items)
