"""Principal introspection and guardian self-service account actions.

The frontend app shell (C4a-1) needs ``GET /me`` to decide which layout (kid vs
guardian) and nav to render; it must not attempt to parse a bearer token
itself, since that token is opaque locally and a signed JWT elsewhere.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter
from sqlalchemy import select, update

from cyo_adventure.api.deps import Context, Role
from cyo_adventure.api.schemas import FamilyExportView, MeResponse, error_responses
from cyo_adventure.core.exceptions import AuthorizationError, BusinessLogicError
from cyo_adventure.db.models import (
    CATALOG_FAMILY_ID,
    ChildProfile,
    Completion,
    Family,
    KidFlag,
    Rating,
    ReadingState,
    StorybookAssignment,
    StoryRequest,
    User,
)
from cyo_adventure.events import Actor, EventType, record_event

if TYPE_CHECKING:
    import uuid

router = APIRouter(prefix="/api/v1", tags=["me"], responses=error_responses(401))


@router.get("/me")
async def whoami(ctx: Context) -> MeResponse:
    """Return the authenticated caller's own identity and role.

    Args:
        ctx: The request context (principal + unit-of-work session).

    Returns:
        MeResponse: The principal's subject, role, family, and profile ids.
    """
    # #ASSUME: security: /me returns identity only for an already-verified
    # principal (require_principal ran and resolved a Principal); no token
    # parsing happens here.
    # #VERIFY: tests/integration/test_me.py::test_me_requires_authentication
    # asserts 401 without a bearer.
    principal = ctx.principal
    return MeResponse(
        subject=principal.subject,
        role=principal.role.value,
        is_admin=principal.is_admin,
        family_id=str(principal.family_id),
        profile_ids=[str(pid) for pid in principal.profile_ids],
    )


def _profile_dict(
    row: ChildProfile, nested: dict[str, list[dict[str, object]]]
) -> dict[str, object]:
    """Build the full export dict for a child profile, nested lists included.

    Args:
        row: The child profile row.
        nested: This profile's ``{"reading_state": [...], "completions": [...],
            "ratings": [...], "assignments": [...]}`` lists, pre-grouped by
            the caller.
    """
    return {
        "id": str(row.id),
        "display_name": row.display_name,
        "age_band": row.age_band,
        "reading_level_cap": row.reading_level_cap,
        "avatar": row.avatar,
        "tts_enabled": row.tts_enabled,
        "content_flag_caps": row.allowed_content_flags,
        "banned_themes": row.banned_themes,
        "created_at": row.created_at.isoformat(),
        "deactivated_at": row.deactivated_at.isoformat()
        if row.deactivated_at is not None
        else None,
        **nested,
    }


async def _assemble_family_export(
    ctx: Context, family_id: uuid.UUID
) -> FamilyExportView:
    """Assemble the full family export (Phase 3c).

    Args:
        ctx: The request context (principal + session).
        family_id: The family to export.

    Returns:
        FamilyExportView: Every record tied to the family and its profiles.
    """
    family = await ctx.session.get(Family, family_id)
    guardian_rows = (
        await ctx.session.scalars(
            select(User)
            .where(User.family_id == family_id)
            .order_by(User.created_at.asc())
        )
    ).all()
    profile_rows = (
        await ctx.session.scalars(
            select(ChildProfile)
            .where(ChildProfile.family_id == family_id)
            .order_by(ChildProfile.created_at.asc())
        )
    ).all()
    profile_ids = [row.id for row in profile_rows]
    state_by_profile: dict[uuid.UUID, list[dict[str, object]]] = defaultdict(list)
    completions_by_profile: dict[uuid.UUID, list[dict[str, object]]] = defaultdict(list)
    ratings_by_profile: dict[uuid.UUID, list[dict[str, object]]] = defaultdict(list)
    assignments_by_profile: dict[uuid.UUID, list[dict[str, object]]] = defaultdict(list)
    if profile_ids:
        state_rows = await ctx.session.scalars(
            select(ReadingState).where(ReadingState.child_profile_id.in_(profile_ids))
        )
        for state in state_rows:
            state_by_profile[state.child_profile_id].append(
                {
                    "storybook_id": state.storybook_id,
                    "version": state.version,
                    "current_node": state.current_node,
                    "state_revision": state.state_revision,
                    "created_at": state.created_at.isoformat(),
                    "updated_at": state.updated_at.isoformat(),
                }
            )
        completion_rows = await ctx.session.scalars(
            select(Completion).where(Completion.child_profile_id.in_(profile_ids))
        )
        for completion in completion_rows:
            completions_by_profile[completion.child_profile_id].append(
                {
                    "storybook_id": completion.storybook_id,
                    "version": completion.version,
                    "ending_id": completion.ending_id,
                    "found_at": completion.found_at.isoformat(),
                }
            )
        rating_rows = await ctx.session.scalars(
            select(Rating).where(Rating.child_profile_id.in_(profile_ids))
        )
        for rating in rating_rows:
            ratings_by_profile[rating.child_profile_id].append(
                {
                    "storybook_id": rating.storybook_id,
                    "value": rating.value,
                    "rated_at": rating.rated_at.isoformat(),
                }
            )
        assignment_rows = await ctx.session.scalars(
            select(StorybookAssignment).where(
                StorybookAssignment.child_profile_id.in_(profile_ids)
            )
        )
        for assignment in assignment_rows:
            assignments_by_profile[assignment.child_profile_id].append(
                {
                    "storybook_id": assignment.storybook_id,
                    "created_at": assignment.created_at.isoformat(),
                }
            )
    request_rows = await ctx.session.scalars(
        select(StoryRequest)
        .where(StoryRequest.family_id == family_id)
        .order_by(StoryRequest.created_at.asc())
    )
    return FamilyExportView(
        exported_at=datetime.now(UTC),
        family={
            "id": str(family_id),
            "name": family.name if family is not None else None,
            "created_at": family.created_at.isoformat() if family is not None else None,
        },
        guardians=[
            {
                "id": str(row.id),
                "role": row.role,
                "is_admin": row.is_admin,
                "email": row.email,
                "created_at": row.created_at.isoformat(),
            }
            for row in guardian_rows
        ],
        profiles=[
            _profile_dict(
                row,
                {
                    "reading_state": state_by_profile[row.id],
                    "completions": completions_by_profile[row.id],
                    "ratings": ratings_by_profile[row.id],
                    "assignments": assignments_by_profile[row.id],
                },
            )
            for row in profile_rows
        ],
        story_requests=[
            {
                "id": str(row.id),
                "profile_id": str(row.profile_id) if row.profile_id else None,
                # #CRITICAL: security: a blocked request's raw text is never
                # exported, mirroring api/story_requests.py's redaction of
                # request_text/proposed_series_title for blocked rows -- this
                # export must not become a side channel around that redaction.
                "request_text": row.request_text if row.status != "blocked" else None,
                "status": row.status,
                "age_band": row.age_band,
                "length": row.length,
                "narrative_style": row.narrative_style,
                "created_at": row.created_at.isoformat(),
                "reviewed_at": row.reviewed_at.isoformat()
                if row.reviewed_at is not None
                else None,
                "approved_at": row.approved_at.isoformat()
                if row.approved_at is not None
                else None,
            }
            for row in request_rows
        ],
    )


@router.get("/me/export", responses=error_responses(403))
async def export_my_family(ctx: Context) -> FamilyExportView:
    """Export every record tied to the caller's family and its child profiles.

    COPPA 312.6(a) access / GDPR Article 20 portability (remediation plan
    Phase 3c). Deliberately excludes ``generation_job.report`` (raw
    multi-stage LLM output): that field is admin-only everywhere else in this
    API (``api/generation.py::get_generation_job``), and a plain guardian's
    export must not become a side channel around that restriction.

    Args:
        ctx: The request context (principal + unit-of-work session).

    Returns:
        FamilyExportView: The full family export.

    Raises:
        AuthorizationError: If the caller is not a guardian.
    """
    # #CRITICAL: security: guardian-only, own family only (family_id is taken
    # from the verified principal, never a client-supplied parameter, so
    # there is no cross-family export IDOR to guard against separately).
    # #VERIFY: tests/integration/test_deletion_drill.py::
    # test_export_my_family_rejects_non_guardian.
    if ctx.principal.role is not Role.GUARDIAN:
        msg = "guardian role required"
        raise AuthorizationError(msg)
    return await _assemble_family_export(ctx, ctx.principal.family_id)


@router.delete("/me/family", status_code=204, responses=error_responses(400, 403))
async def delete_my_family(ctx: Context) -> None:
    """Permanently erase the caller's entire family account.

    GDPR Article 17 / COPPA 312.10 (remediation plan Phase 3b). ADR-018's
    already-decided item 4 frames account deletion as family-scoped ("in-app
    account deletion erases the family"): this is the single guardian-facing
    deletion action, and it satisfies Article 17 for the calling guardian as
    a data subject in their own right (not only as the parent exercising a
    child's rights), since every ``user`` row in the family -- including the
    caller's own -- cascades away with it (Phase 3a).

    Every family-owned table (series, storybooks and their versions, child
    profiles and everything linked to them, concepts, story requests, device
    grants, kid flags, and every guardian/admin/child login row) cascades at
    the database level. One thing cannot cascade cleanly: a ``kid_flag`` row
    this family's admin(s) resolved may belong to a DIFFERENT family
    entirely (any admin can resolve any family's flags), and
    ``ck_kid_flag_resolved_pairing`` requires ``resolved_by``/``resolved_at``
    to be null together, so a bare cascade would violate that CHECK. Those
    flags are explicitly reopened (both columns nulled) here, before the
    family delete, rather than left to a cascade that cannot express it.

    Args:
        ctx: The request context (principal + unit-of-work session).

    Raises:
        AuthorizationError: If the caller is not a guardian.
        BusinessLogicError: If the caller's family is the sentinel catalog
            family (should be unreachable: no real guardian ever belongs to
            it, but guarded explicitly as defense in depth).
    """
    # #CRITICAL: security: guardian-only; an admin-only adult with no family
    # guardianship has no family of their own to delete via this route.
    # #VERIFY: tests/integration/test_deletion_drill.py::
    # test_delete_my_family_rejects_non_guardian.
    if ctx.principal.role is not Role.GUARDIAN:
        msg = "guardian role required"
        raise AuthorizationError(msg)
    family_id = ctx.principal.family_id
    # #CRITICAL: data-integrity: the catalog family (#173) owns admin-curated
    # catalog content, not a household; it must never be deletable through a
    # guardian self-service route. Unreachable in practice (no User row ever
    # carries this family_id), kept as an explicit guard rather than relying
    # solely on that invariant holding forever.
    if family_id == CATALOG_FAMILY_ID:
        msg = "the catalog family cannot be deleted"
        raise BusinessLogicError(msg)
    # #CRITICAL: data-integrity: reopen (not delete) every kid_flag this
    # family's users resolved on ANY family's flag, before the cascade delete
    # below, so ck_kid_flag_resolved_pairing never sees resolved_by go null
    # while resolved_at stays set. See the docstring's #CRITICAL note.
    # #VERIFY: tests/integration/test_deletion_drill.py::
    # test_delete_my_family_reopens_kid_flags_resolved_by_its_admins.
    await ctx.session.execute(
        update(KidFlag)
        .where(
            KidFlag.resolved_by.in_(select(User.id).where(User.family_id == family_id))
        )
        .values(resolved_by=None, resolved_at=None, resolution=None)
    )
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal),
        entity_type="family",
        entity_id=str(family_id),
        event_type=EventType.FAMILY_MANAGED,
        payload={"action": "deleted"},
    )
    row = await ctx.session.get(Family, family_id)
    if row is not None:
        await ctx.session.delete(row)
        await ctx.session.flush()
