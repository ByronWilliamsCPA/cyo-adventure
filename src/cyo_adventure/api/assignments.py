"""Assignment endpoints: a guardian grants a published story to child profiles.

Assigning is the read-gate for a story: a child's library listing and direct
version fetch both filter on ``storybook_assignment``, so a child sees only
stories explicitly assigned to their profile. This router is guardian-only; a
child token is rejected. It is add-only and idempotent (re-assigning an already
assigned profile is a no-op). There is no unassign endpoint: removing access has
reading-state and offline-cache implications deferred past the first release.

Error ordering follows the repo convention in ``ratings.py`` and
``library.py`` (``get_storybook_version``): an unknown storybook id is 404,
while an EXISTING storybook owned by another family is 403 via
``authorize_family``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import (
    Context,
    authorize_family,
    authorize_profile,
    parse_uuid,
)
from cyo_adventure.api.schemas import AssignmentCreateBody, AssignmentListView
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    ResourceNotFoundError,
)
from cyo_adventure.db.models import Storybook, StorybookAssignment

if TYPE_CHECKING:
    from collections.abc import Iterable

router = APIRouter(prefix="/api/v1", tags=["assignments"])

_PUBLISHED = "published"


def _assignment_list(
    storybook_id: str, profile_ids: Iterable[object]
) -> AssignmentListView:
    """Build the response view with sorted, stringified profile ids."""
    return AssignmentListView(
        storybook_id=storybook_id,
        profile_ids=sorted(str(pid) for pid in profile_ids),
    )


async def _require_guardian_family_book(ctx: Context, storybook_id: str) -> Storybook:
    """Return the storybook after guardian-only and same-family checks.

    Args:
        ctx: The request context (principal + session).
        storybook_id: The story id from the path.

    Returns:
        Storybook: The story owned by the guardian's family.

    Raises:
        AuthorizationError: If the caller is not a guardian, or the story
            belongs to another family (403).
        ResourceNotFoundError: If the story does not exist (404).
    """
    # #CRITICAL: security: guardian-only; a child token cannot read or widen
    # assignments, and an admin (a cross-family safety reviewer, not a family
    # assigner) is rejected here too. Error ordering matches ratings.py and
    # library.py (get_storybook_version): 404-if-missing precedes
    # authorize_family, so an unknown id is 404 and a cross-family book is 403.
    # #VERIFY: is_guardian gate -> 403; None -> 404; authorize_family -> 403.
    if not ctx.principal.is_guardian:
        msg = "only a guardian may manage assignments"
        raise AuthorizationError(msg)
    book = await ctx.session.get(Storybook, storybook_id)
    if book is None:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    authorize_family(ctx.principal, book.family_id)
    return book


@router.post("/storybooks/{storybook_id}/assignments")
async def assign_storybook(
    storybook_id: str, body: AssignmentCreateBody, ctx: Context
) -> AssignmentListView:
    """Assign a published story to one or more of the guardian's child profiles.

    Args:
        storybook_id: The story to assign.
        body: The requested profile ids.
        ctx: The request context (principal + unit-of-work session).

    Returns:
        AssignmentListView: The full current set of assigned profile ids.

    Raises:
        AuthorizationError: Non-guardian caller, a cross-family storybook, or a
            profile outside the family.
        ResourceNotFoundError: Unknown storybook id.
        BusinessLogicError: The story is not published.
        ValidationError: A profile id is not a UUID.
    """
    # #CRITICAL: security: validate role/family/profile scope BEFORE any write so
    # a guardian cannot assign a non-published story or a foreign profile.
    # #VERIFY: order is guardian(403) -> missing book(404) -> cross-family(403)
    # -> non-published(400) -> foreign profile(403).
    book = await _require_guardian_family_book(ctx, storybook_id)
    if book.status != _PUBLISHED:
        msg = "only a published story can be assigned"
        raise BusinessLogicError(msg)
    profile_ids = [parse_uuid(pid, "profile_ids") for pid in body.profile_ids]
    for pid in profile_ids:
        authorize_profile(ctx.principal, pid)
    # #EDGE: concurrency: two guardians assigning the same (profile, story) can
    # both read no existing row and both INSERT, raising a PK violation at flush
    # (a 500). Vanishingly rare for a family's assign UI; accepted rather than
    # locking. #VERIFY: switch to INSERT ... ON CONFLICT DO NOTHING if it recurs.
    existing = set(
        await ctx.session.scalars(
            select(StorybookAssignment.child_profile_id).where(
                StorybookAssignment.storybook_id == storybook_id
            )
        )
    )
    # Guarding each insert on ``existing`` (updated in-loop) makes the write
    # idempotent AND dedupes duplicate ids within one request: the second
    # occurrence of a repeated id finds it already present and is skipped.
    for pid in profile_ids:
        if pid not in existing:
            ctx.session.add(
                StorybookAssignment(
                    child_profile_id=pid,
                    storybook_id=storybook_id,
                    assigned_by=ctx.principal.user_id,
                )
            )
            existing.add(pid)
    await ctx.session.flush()
    return _assignment_list(storybook_id, existing)


@router.get("/storybooks/{storybook_id}/assignments")
async def list_assignments(storybook_id: str, ctx: Context) -> AssignmentListView:
    """List the child profiles a story is currently assigned to.

    Args:
        storybook_id: The story whose assignments are requested.
        ctx: The request context (principal + session).

    Returns:
        AssignmentListView: The current assigned profile ids.

    Raises:
        AuthorizationError: Non-guardian caller or cross-family storybook.
        ResourceNotFoundError: Unknown storybook id.
    """
    # #CRITICAL: security: same guardian-only/same-family gate as the POST path.
    # #VERIFY: _require_guardian_family_book raises 403 (role or cross-family)
    # or 404 (missing) before any read.
    await _require_guardian_family_book(ctx, storybook_id)
    rows = await ctx.session.scalars(
        select(StorybookAssignment.child_profile_id).where(
            StorybookAssignment.storybook_id == storybook_id
        )
    )
    return _assignment_list(storybook_id, rows)
