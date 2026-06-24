"""Rating endpoints: a child rates a storybook 1-5.

A rating is a per-child fact about a *book* (not a specific version) and is
mutable: re-rating overwrites the prior value. This is a deliberately coarser
grain than ``Completion``; see the ``Rating`` model docstring. All access is
scoped to the principal's own family and profile.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import Context, authorize_family, authorize_profile
from cyo_adventure.api.schemas import RatingBody, RatingListView, RatingView
from cyo_adventure.core.exceptions import ResourceNotFoundError, ValidationError
from cyo_adventure.db.models import Rating, Storybook

router = APIRouter(prefix="/api/v1", tags=["ratings"])


def _parse_uuid(raw: str, field: str) -> uuid.UUID:
    """Parse a UUID field, raising a 422-mapped error on bad input."""
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        msg = f"{field} must be a UUID"
        raise ValidationError(msg, field=field, value=raw) from exc


def _rating_view(row: Rating) -> RatingView:
    """Build the response view from a Rating row."""
    return RatingView(
        child_profile_id=str(row.child_profile_id),
        storybook_id=row.storybook_id,
        value=row.value,
        rated_at=row.rated_at,
        updated_at=row.updated_at,
    )


@router.post("/ratings")
async def record_rating(body: RatingBody, ctx: Context) -> RatingView:
    """Set or update the calling child's rating of a storybook.

    Args:
        body: The rating request (profile, storybook, value 1-5).
        ctx: The request context (principal + unit-of-work session).

    Returns:
        RatingView: The stored rating.

    Raises:
        ValidationError: If profile_id is not a UUID.
        AuthorizationError: If the profile or storybook is not the caller's.
        ResourceNotFoundError: If the storybook does not exist.
    """
    # #CRITICAL: security: authorize the profile AND the storybook's family
    # before any write, so a child cannot rate another profile's or family's
    # book (IDOR).
    # #VERIFY: authorize_profile / authorize_family raise AuthorizationError -> 403.
    profile_id = _parse_uuid(body.profile_id, "profile_id")
    authorize_profile(ctx.principal, profile_id)
    # Note: the 404-if-missing check precedes authorize_family, so a caller can
    # tell "exists in another family" (403) from "does not exist" (404). This
    # matches reading.py's precedent and is accepted for Phase A (storybook ids
    # are not secret). Revisit before Phase B adds cross-family reads.
    book = await ctx.session.get(Storybook, body.storybook_id)
    if book is None:
        msg = f"storybook '{body.storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    authorize_family(ctx.principal, book.family_id)
    # #EDGE: concurrency: two simultaneous first-ratings for the same
    # (child_profile_id, storybook_id) can both see no existing row and both
    # INSERT, raising a PK violation at flush (a 500). This is vanishingly rare
    # for a single child's rating UI, so we accept it rather than locking.
    # #VERIFY: if concurrent first-ratings become real, switch to a Postgres
    # INSERT ... ON CONFLICT DO UPDATE (true upsert), or SELECT FOR UPDATE as in
    # reading.py's reading-state handler.
    row = await ctx.session.get(Rating, (profile_id, body.storybook_id))
    if row is None:
        row = Rating(
            child_profile_id=profile_id,
            storybook_id=body.storybook_id,
            value=body.value,
        )
        ctx.session.add(row)
    else:
        row.value = body.value
    # The unit-of-work dependency commits on success; flush + refresh to read
    # back server-generated timestamps without an explicit commit here.
    await ctx.session.flush()
    await ctx.session.refresh(row, ["rated_at", "updated_at"])
    return _rating_view(row)


@router.get("/ratings/{profile_id}")
async def list_ratings(profile_id: str, ctx: Context) -> RatingListView:
    """List all ratings recorded by a child profile.

    Args:
        profile_id: The child profile whose ratings are requested.
        ctx: The request context (principal + session).

    Returns:
        RatingListView: The profile's ratings.

    Raises:
        ValidationError: If profile_id is not a UUID.
        AuthorizationError: If the profile is not the caller's.
    """
    # #CRITICAL: security: a caller may only read ratings for a profile it owns.
    # #VERIFY: authorize_profile raises AuthorizationError -> 403.
    parsed = _parse_uuid(profile_id, "profile_id")
    authorize_profile(ctx.principal, parsed)
    # Order by most-recently-updated so the response is deterministic across
    # calls; an unordered SELECT returns DB-dependent row order, which causes
    # client-side list flicker and defeats response diffing/caching. storybook_id
    # (unique per profile via the PK) is a stable tie-breaker when two ratings
    # share an updated_at timestamp.
    rows = await ctx.session.scalars(
        select(Rating)
        .where(Rating.child_profile_id == parsed)
        .order_by(Rating.updated_at.desc(), Rating.storybook_id.asc())
    )
    return RatingListView(ratings=[_rating_view(row) for row in rows.all()])
