"""Family child-profile management (C4a-2).

Profiles gate what a child can read (age band, reading-level cap, content
flags), so create/update is a guardian-role action; the list endpoint returns
exactly the profiles the calling principal may act on (guardian: all family
profiles, child: their own), which is what both the kid-surface Profile
Picker and the guardian management page need.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import Context
from cyo_adventure.api.schemas import ProfileListView, ProfileView
from cyo_adventure.db.models import ChildProfile

router = APIRouter(prefix="/api/v1", tags=["profiles"])


def _view(row: ChildProfile) -> ProfileView:
    """Build the response view from a ChildProfile row.

    Args:
        row: The ORM row.

    Returns:
        ProfileView: The wire-safe view.
    """
    return ProfileView(
        id=str(row.id),
        display_name=row.display_name,
        age_band=row.age_band,
        reading_level_cap=row.reading_level_cap,
        avatar=row.avatar,
        tts_enabled=row.tts_enabled,
        created_at=row.created_at,
    )


@router.get("/profiles")
async def list_profiles(ctx: Context) -> ProfileListView:
    """List the child profiles the calling principal may act on.

    Args:
        ctx: The request context (principal + unit-of-work session).

    Returns:
        ProfileListView: All family profiles for a guardian; the single
            assigned profile for a child; empty if the principal has none.
    """
    # #CRITICAL: security: scope strictly to principal.profile_ids (resolved at
    # the auth boundary in deps.py), never to a client-supplied family or
    # profile id, so no cross-family row can ever appear (IDOR).
    # #VERIFY: test_profiles.py::test_guardian_lists_own_family_profiles asserts
    # family B's profile is absent from guardian A's list.
    if not ctx.principal.profile_ids:
        return ProfileListView(profiles=[])
    rows = await ctx.session.scalars(
        select(ChildProfile)
        .where(ChildProfile.id.in_(ctx.principal.profile_ids))
        # Stable order: creation order matches the wireframe's grid intent and
        # avoids DB-dependent row order flicker; id breaks created_at ties.
        .order_by(ChildProfile.created_at.asc(), ChildProfile.id.asc())
    )
    return ProfileListView(profiles=[_view(row) for row in rows.all()])
