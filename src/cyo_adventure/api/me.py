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

from cyo_adventure.api.admin_users import create_pending_invite, user_view
from cyo_adventure.api.deps import Context, Role
from cyo_adventure.api.schemas import (
    FamilyExportView,
    GuardianInviteBody,
    MeResponse,
    UserView,
    error_responses,
)
from cyo_adventure.core.exceptions import AuthorizationError, BusinessLogicError
from cyo_adventure.db.models import (
    CATALOG_FAMILY_ID,
    ChildProfile,
    ChildProfilePersonalization,
    Completion,
    Family,
    KidFlag,
    PersonalizationDisclosureConsent,
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
        # ADR-023 P4 (Task B3): this child's OWN real-name consent rings,
        # distinct from the per-slot rings inside "personalization" below.
        "real_name_ring1_enabled": row.real_name_ring1_enabled,
        "real_name_ring2_enabled": row.real_name_ring2_enabled,
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
    # #ASSUME: data-integrity: a sibling-slot ``value_profile_id`` is
    # validated at write time to name a profile in the SAME family (design
    # plan Task B5, step 4), so every referenced profile is already among
    # ``profile_rows`` and this map never has to fall back to a cross-family
    # lookup or a ``None`` display name for a live reference.
    # #VERIFY: tests/unit/test_personalization_values.py (Task B5) pins the
    # same-family invariant at write time.
    display_name_by_profile_id = {row.id: row.display_name for row in profile_rows}
    state_by_profile: dict[uuid.UUID, list[dict[str, object]]] = defaultdict(list)
    completions_by_profile: dict[uuid.UUID, list[dict[str, object]]] = defaultdict(list)
    ratings_by_profile: dict[uuid.UUID, list[dict[str, object]]] = defaultdict(list)
    assignments_by_profile: dict[uuid.UUID, list[dict[str, object]]] = defaultdict(list)
    personalization_by_profile: dict[uuid.UUID, list[dict[str, object]]] = defaultdict(
        list
    )
    consents_by_profile: dict[uuid.UUID, list[dict[str, object]]] = defaultdict(list)
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
        personalization_rows = await ctx.session.scalars(
            select(ChildProfilePersonalization).where(
                ChildProfilePersonalization.child_profile_id.in_(profile_ids)
            )
        )
        for personalization in personalization_rows:
            personalization_by_profile[personalization.child_profile_id].append(
                {
                    "slot_type": personalization.slot_type,
                    "value_text": personalization.value_text,
                    "value_enum": personalization.value_enum,
                    "value_profile_id": str(personalization.value_profile_id)
                    if personalization.value_profile_id is not None
                    else None,
                    "value_profile_display_name": display_name_by_profile_id.get(
                        personalization.value_profile_id
                    )
                    if personalization.value_profile_id is not None
                    else None,
                    "ring1_enabled": personalization.ring1_enabled,
                    "ring2_enabled": personalization.ring2_enabled,
                    "created_at": personalization.created_at.isoformat(),
                    "updated_at": personalization.updated_at.isoformat(),
                }
            )
        # #CRITICAL: security: this includes TOMBSTONED rows
        # (family_connection_id IS NULL) on purpose -- a guardian's own
        # export must be complete even after the connection they consented
        # on was deleted; the query below applies no filter on that column.
        # #VERIFY: tests/integration/test_deletion_drill.py::
        # test_export_includes_personalization_and_disclosure_consent_data.
        consent_rows = await ctx.session.scalars(
            select(PersonalizationDisclosureConsent).where(
                PersonalizationDisclosureConsent.child_profile_id.in_(profile_ids)
            )
        )
        for consent in consent_rows:
            consents_by_profile[consent.child_profile_id].append(
                {
                    "id": str(consent.id),
                    "family_connection_id": str(consent.family_connection_id)
                    if consent.family_connection_id is not None
                    else None,
                    "connected_family_label": consent.connected_family_label,
                    "covered_slot_types": consent.covered_slot_types,
                    "sibling_authority_attested": consent.sibling_authority_attested,
                    "consent_accepted_at": consent.consent_accepted_at.isoformat()
                    if consent.consent_accepted_at is not None
                    else None,
                    "consent_policy_version": consent.consent_policy_version,
                    "consent_signer_name": consent.consent_signer_name,
                    "consent_ip": consent.consent_ip,
                    "revoked_at": consent.revoked_at.isoformat()
                    if consent.revoked_at is not None
                    else None,
                    "created_at": consent.created_at.isoformat(),
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
                    "personalization": personalization_by_profile[row.id],
                    "disclosure_consents": consents_by_profile[row.id],
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

    Each profile also carries its ADR-023 P4 personalization data (Task B3):
    every ``ChildProfilePersonalization`` row (a sibling-slot row includes
    both the referenced profile's id and its display name), the two
    real-name consent-ring booleans, and every
    ``PersonalizationDisclosureConsent`` row, including a tombstoned one
    whose ``family_connection_id`` has gone ``NULL`` because the underlying
    connection was deleted -- the tombstone is evidence the guardian's own
    export must keep, not something to hide.

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


@router.post(
    "/me/family/invite-guardian",
    status_code=201,
    responses=error_responses(403, 409),
)
async def invite_guardian(body: GuardianInviteBody, ctx: Context) -> UserView:
    """Invite a co-parent into the caller's OWN family (guardian self-service; G14).

    Complements the admin-mediated ``POST /admin/users`` (WS-J), which can
    invite a second guardian into ANY family: this endpoint is the
    guardian-initiated counterpart the register flagged as the real gap, and
    it is deliberately narrower. It reuses
    ``api/admin_users.py::create_pending_invite``, the exact same pending-row
    creation and duplicate-email guard the admin path uses, so the two paths
    can never drift into inconsistent invite semantics.

    Args:
        body: The invitee's email; nothing else is caller-supplied.
        ctx: The request context (principal + unit-of-work session).

    The invited address is NOT thereby pulled into the caller's family. The
    row is created with ``status="pending_guardian_invite"``, which
    ``api/onboarding.py::_bind_pending_invite`` binds to
    ``"awaiting_approval"`` rather than ``"active"``: an admin must still
    approve before the invitee can authenticate at all. Only the
    admin-mediated ``POST /admin/users`` produces an invite that binds
    straight to ``"active"``.

    Returns:
        UserView: The created ``status="pending_guardian_invite"`` row,
        scoped to the caller's own family.

    Raises:
        AuthorizationError: If the caller is not a guardian (403).
        StateTransitionError: If a pending invite of either kind already
            exists for this email (409).
    """
    # #CRITICAL: security: the target family is ALWAYS ctx.principal.family_id,
    # never taken from the request body (GuardianInviteBody has no family_id
    # field at all); this is the one thing that makes this endpoint safe to
    # expose to a non-admin caller. A guardian must never be able to invite
    # into a family other than their own.
    # #VERIFY: tests/integration/test_me_invite_guardian_api.py::
    # test_invite_guardian_is_hard_scoped_to_callers_own_family.
    if ctx.principal.role is not Role.GUARDIAN:
        msg = "guardian role required"
        raise AuthorizationError(msg)
    # #ASSUME: security: the invited role is always "guardian", never "admin";
    # a guardian cannot use this path to grant the global admin capability to
    # anyone, including themselves. Only POST /admin/users (admin-only) can
    # create an admin row.
    # #VERIFY: tests/integration/test_me_invite_guardian_api.py::
    # test_invite_guardian_created_row_is_never_admin.
    # #CRITICAL: security: invited_by_admin=False is what stops this endpoint
    # from being a family-capture primitive. It selects
    # status='pending_guardian_invite', which onboarding binds to
    # 'awaiting_approval'; passing True here (or reusing the admin path's
    # 'pending') would let any guardian pre-claim an arbitrary email address
    # and have its real owner bound into this family as an ACTIVE guardian on
    # their first sign-in, exposing this family's child profiles to the
    # inviter. There is no invite expiry and no revoke surface, so this flag
    # is the only gate.
    # #VERIFY: tests/integration/test_me_invite_guardian_api.py::
    # test_guardian_invited_user_binds_to_awaiting_approval_not_active.
    user = await create_pending_invite(
        ctx.session,
        family_id=ctx.principal.family_id,
        role="guardian",
        is_admin=False,
        email=body.email,
        invited_by_admin=False,
    )
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal),
        entity_type="user",
        entity_id=str(user.id),
        event_type=EventType.USER_MANAGED,
        payload={"action": "invited", "role": "guardian", "status": user.status},
    )
    return user_view(user)
