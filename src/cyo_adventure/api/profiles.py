"""Family child-profile management (C4a-2).

Profiles gate what a child can read: age band, reading-level cap, and the G2
per-child content controls (``content_flag_caps``, ``banned_themes``), so
create/update is a guardian-role action; the list endpoint returns exactly
the profiles the calling principal may act on (guardian: all family profiles,
child: their own), which is what both the kid-surface Profile Picker and the
guardian management page need.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import (
    Context,
    Principal,
    Role,
    authorize_family,
    authorize_profile,
    parse_uuid,
)
from cyo_adventure.api.personalization import purge_profile_personalization
from cyo_adventure.api.schemas import (
    ContentFlagCaps,
    ProfileCreateBody,
    ProfileListView,
    ProfileStoryStatusListView,
    ProfileStoryStatusView,
    ProfileUpdateBody,
    ProfileView,
    error_responses,
)
from cyo_adventure.consent import has_usable_verification
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.core.pin import hash_pin
from cyo_adventure.db.models import ChildProfile, StorybookAssignment, User
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.validator.slots import (
    band_mandatory_bundles,
    denylisted_bundles,
    structural_value_violations,
)

if TYPE_CHECKING:
    import uuid

# W1.4 (design review 4.1 / kid-appeal-implementation-plan.md): the window a
# StorybookAssignment counts as "new" for the profile-picker pill.
#
# #ASSUME: data-integrity: "new" is defined as "assigned within the last N
# days", NOT "assigned since this profile's last child session", because no
# child-session-start timestamp is ever persisted -- a child session token is
# a self-contained, backend-signed JWT verified with zero database round-trip
# (api/deps.py::_child_principal's docstring), so there is no row to compare
# against. Falls back to the same 7-day window the shelf's own "new" badge
# already uses (frontend/src/library/bookCardUtils.ts::NEW_BADGE_WINDOW_MS),
# so a child does not see two different definitions of "new" between the
# picker pill and the shelf they land on next.
# #VERIFY: tests/integration/test_profiles.py::
# test_story_status_true_for_assignment_within_seven_days,
# ::test_story_status_excludes_assignment_older_than_seven_days pin this
# window server-side; frontend/src/library/bookCardUtils.test.ts pins the
# 7-day constant on its own side (no cross-language test ties the two, so a
# future change to either must update this comment by hand).
_NEW_STORY_WINDOW = timedelta(days=7)

router = APIRouter(
    prefix="/api/v1", tags=["profiles"], responses=error_responses(401, 403)
)


def _view(row: ChildProfile) -> ProfileView:
    """Build the response view from a ChildProfile row.

    Args:
        row: The ORM row.

    Returns:
        ProfileView: The wire-safe view.
    """
    # #CRITICAL: security: pin_hash is write-only credential material; the view
    # exposes only the derived has_pin bool, never the encoded hash (P6-07).
    # #VERIFY: test_profiles.py::test_pin_hash_never_serialized asserts the raw
    # response JSON never contains "pin_hash".
    # #ASSUME: data integrity: allowed_content_flags/banned_themes are None or
    # an unset-key dict/None on a profile written before G2 (or an in-memory
    # row pre-flush); both read back as "no override" rather than raising.
    # #VERIFY: test_profiles.py::test_list_profile_predating_g2_has_no_overrides.
    return ProfileView(
        id=str(row.id),
        display_name=row.display_name,
        age_band=AgeBand(row.age_band),
        reading_level_cap=row.reading_level_cap,
        avatar=row.avatar,
        tts_enabled=row.tts_enabled,
        reduce_motion=row.reduce_motion,
        has_pin=row.pin_hash is not None,
        content_flag_caps=ContentFlagCaps.model_validate(
            row.allowed_content_flags or {}
        ),
        banned_themes=list(row.banned_themes or []),
        request_auto_approve=row.request_auto_approve,
        monthly_request_envelope=row.monthly_request_envelope,
        processing_restricted=row.processing_restricted_at is not None,
        ring_enabled=row.ring_enabled,
        ring_goal_days=row.ring_goal_days,
        badges_enabled=row.badges_enabled,
        time_capture_paused=row.time_capture_paused,
        created_at=row.created_at,
    )


def _apply_simple_fields(row: ChildProfile, body: ProfileUpdateBody) -> None:
    """Apply the non-null-applies scalar fields of a PATCH (extracted for complexity).

    display_name/age_band/reading_level_cap/tts_enabled/reduce_motion have no
    legitimate "clear" semantics, so an explicit null on any of them is a
    deliberate no-op; see ``ProfileUpdateBody``'s docstring and
    ``test_update_ignores_explicit_null_on_non_avatar_fields``.

    Args:
        row: The profile row being updated (mutated in place).
        body: The PATCH body.
    """
    # #ASSUME: data integrity: an explicit null on any of these five non-avatar
    # scalar fields is a deliberate no-op, not a clear; only a present, non-null
    # value is written to the ORM row.
    # #VERIFY: test_profiles.py::test_update_ignores_explicit_null_on_non_avatar_fields
    # age_band is applied BEFORE display_name is validated: a single PATCH
    # may change both together, and the denylist check must run against the
    # row's resulting age_band, not a now-stale prior one.
    if body.age_band is not None:
        row.age_band = body.age_band.value
    if body.display_name is not None:
        # #CRITICAL: security: display_name renders directly into a child's
        # own story prose (ADR-023 plan 5.2); names set before this feature
        # shipped were never checked, so this validates on every write, not
        # only new profiles.
        # #VERIFY: tests/integration/test_personalization_api.py::
        # test_update_profile_rejects_denylisted_display_name.
        validate_display_name(body.display_name, row.age_band)
        row.display_name = body.display_name
    if body.reading_level_cap is not None:
        row.reading_level_cap = body.reading_level_cap
    if body.tts_enabled is not None:
        row.tts_enabled = body.tts_enabled
    if body.reduce_motion is not None:
        row.reduce_motion = body.reduce_motion


def _apply_g2_content_controls(row: ChildProfile, body: ProfileUpdateBody) -> None:
    """Apply the G2 content-flag-cap and banned-themes fields of a PATCH.

    Both fields share the avatar/pin "explicit null clears, omitted leaves
    unchanged, non-null value REPLACES wholesale (no per-key merge)"
    contract; split out of ``update_profile`` to keep that function's
    cyclomatic complexity within the repo's Ruff C901 budget.

    Args:
        row: The profile row being updated (mutated in place).
        body: The PATCH body; ``model_fields_set`` distinguishes omitted from
            explicit null.
    """
    fields = body.model_fields_set
    if "content_flag_caps" in fields:
        # #VERIFY: test_profiles.py::test_update_content_flag_caps_replaces_wholesale,
        # ::test_update_content_flag_caps_clears_via_explicit_null.
        row.allowed_content_flags = (
            body.content_flag_caps.model_dump(exclude_none=True)
            if body.content_flag_caps is not None
            else {}
        )
    if "banned_themes" in fields:
        # #VERIFY: test_profiles.py::test_update_banned_themes_clears_via_explicit_null.
        row.banned_themes = (
            list(body.banned_themes) if body.banned_themes is not None else None
        )
    # G3 (ADR-015 envelope): toggle follows non-null-applies; envelope follows
    # explicit-null-clears. A cleared envelope makes auto-approve inert even
    # with the toggle on (enforced in story_requests.service.can_auto_approve).
    # #CRITICAL: payment/financial: these fields authorize automatic
    # generation spend; guardian-only via _require_guardian on the route.
    # #VERIFY: test_profiles.py::test_create_and_update_envelope_fields.
    if body.request_auto_approve is not None:
        row.request_auto_approve = body.request_auto_approve
    if "monthly_request_envelope" in fields:
        row.monthly_request_envelope = body.monthly_request_envelope


def _apply_gamification_settings(row: ChildProfile, body: ProfileUpdateBody) -> None:
    """Apply the W3.4 gamification-toggle fields of a PATCH.

    ``ring_enabled``/``ring_goal_days`` follow the avatar/pin "explicit null
    clears (back to the P-A band default), omitted leaves unchanged"
    contract; ``badges_enabled``/``time_capture_paused`` follow the
    non-null-applies contract, since they always have a concrete default and
    no legitimate "clear" state.

    Args:
        row: The profile row being updated (mutated in place).
        body: The PATCH body; ``model_fields_set`` distinguishes omitted from
            explicit null.
    """
    fields = body.model_fields_set
    # #CRITICAL: data-integrity: an explicit null here must land as a stored
    # NULL (band default resumes), not be silently dropped -- resolution
    # happens downstream in api/progress.py, not here, so this write path
    # must preserve the "no override" state precisely.
    # #VERIFY: tests/integration/test_profiles.py::
    # test_update_ring_settings_explicit_null_clears_to_band_default.
    if "ring_enabled" in fields:
        row.ring_enabled = body.ring_enabled
    if "ring_goal_days" in fields:
        row.ring_goal_days = body.ring_goal_days
    if body.badges_enabled is not None:
        row.badges_enabled = body.badges_enabled
    if body.time_capture_paused is not None:
        row.time_capture_paused = body.time_capture_paused


def validate_display_name(display_name: str, age_band: str) -> None:
    """Reject a display name that fails the write-time validation gate.

    ADR-023 implementation plan section 5.2: ``display_name`` gets the same
    structural and band-mandatory-denylist checks a personalization slot
    value gets, applied at every write point, because names set before this
    feature shipped were never checked.

    Public rather than module-private because ``api/admin_profiles.py`` has
    two more display_name write points (admin create, admin PATCH) and must
    apply the identical gate. #CRITICAL: security: display_name is the one
    personalization value that reaches prose without going through
    ``storybook/personalization_values.py``, so an unguarded write point lets
    a name like ``{~PET:cat~}`` inject a sentinel that manifest verification
    never anticipated.
    #VERIFY: every assignment to ``ChildProfile.display_name`` in ``api/``
    is preceded by a call to this function.

    Args:
        display_name: The candidate name.
        age_band: The profile's age band, as the ORM's stored string value
            (the row's current value, which may differ from a stale request
            body value if age_band and display_name change together).

    Raises:
        ValidationError: If the name fails the structural guard or matches a
            band-mandatory denylisted term (422).
    """
    band = AgeBand(age_band)
    violations = [v.message for v in structural_value_violations(display_name)]
    hit_bundles = denylisted_bundles(display_name, band_mandatory_bundles(band))
    violations.extend(
        f"display_name matches a denylisted term in bundle '{bundle_id}'"
        for bundle_id in sorted(hit_bundles)
    )
    if violations:
        msg = "; ".join(violations)
        raise ValidationError(msg, field="display_name", value=msg)


def _require_guardian(principal: Principal) -> None:
    """Reject principals that may not manage family profiles.

    Args:
        principal: The authenticated caller.

    Raises:
        AuthorizationError: If the caller does not hold the guardian role.
    """
    # #CRITICAL: security: profile caps (age band, reading level) gate what a
    # child can read; only the guardian role may create or change them. Child
    # and admin tokens are rejected here before any write.
    # #VERIFY: tests/integration/test_profiles.py::test_child_cannot_create_profile,
    # ::test_child_cannot_update_profile, ::test_admin_cannot_create_profile,
    # and ::test_admin_cannot_update_profile assert 403 for both roles.
    if not principal.is_guardian:
        msg = "guardian role required"
        raise AuthorizationError(msg)


async def _require_consent(ctx: Context) -> None:
    """Reject profile creation until the calling guardian has recorded VPC consent.

    Phase 2 / ADR-018 D1: the concrete "block child-data collection until a
    consent record exists" gate the remediation plan calls for.
    ``api/onboarding.py::_record_consent`` is the sole writer of
    ``User.consent_accepted_at``; this reader turns its absence into a hard
    stop for the guardian-facing create path.

    There is a second child-data collection point,
    ``api/admin_profiles.py::create_admin_profile``, guarded by that module's
    own ``_require_family_consent``. The two gates ask deliberately different
    questions: this one reads the CALLER's consent (correct, because the
    caller is the child's parent), while the admin one reads the TARGET
    family's (correct, because the caller is not).

    Where ``settings.kws_verification_required`` is on, the gate becomes two
    independent questions rather than one: is there a consent record, and is
    there a usable KWS verification. They are kept independent, rather than
    the second being read off ``User.consent_verification_id``, because a
    guardian who consented before verification existed has the first and not
    the second. Composing them lets that guardian satisfy the gate by
    verifying once, with nothing rewriting the consent record they already
    hold, which the "never overwritten" contract on those columns forbids
    anyway.

    Args:
        ctx: The request context (principal + unit-of-work session).

    Raises:
        BusinessLogicError: If the calling guardian's own ``User`` row has no
            recorded consent, or (when verification is required) no usable
            KWS verification (400).
    """
    # #CRITICAL: security: a guardian who signed in before completing the
    # consent step (or whose client skipped it) must not be able to create a
    # child profile by calling this endpoint directly; this is the only
    # enforcement point on the guardian-facing path.
    # #VERIFY: tests/integration/test_profiles.py::
    # test_create_profile_requires_recorded_consent.
    user = await ctx.session.get(User, ctx.principal.user_id)
    if user is None or user.consent_accepted_at is None:
        msg = (
            "verifiable parental consent must be recorded (see POST "
            "/onboarding) before creating a child profile"
        )
        raise BusinessLogicError(msg, rule="vpc_required")
    # #CRITICAL: security: ADR-018 D1. Checked here rather than only at the
    # sign-in surface, for the same reason the consent check is: this is the
    # enforcement point a client cannot skip by calling the endpoint directly.
    # #VERIFY: tests/integration/test_profiles.py::
    # test_create_profile_requires_a_usable_verification_when_required and
    # ::test_create_profile_allows_a_verified_guardian.
    if settings.kws_verification_required and not await has_usable_verification(
        ctx.session, (user.id,)
    ):
        msg = (
            "parent verification must be completed (see POST "
            "/consent/kws/start) before creating a child profile"
        )
        raise BusinessLogicError(msg, rule="vpc_verification_required")


async def _listable_profiles(ctx: Context) -> list[ChildProfile]:
    """Return the ChildProfile rows the calling principal may list.

    The SOLE scoping logic for "which profiles can this caller see at all",
    shared by ``list_profiles`` and ``list_profile_story_status`` so the two
    endpoints can never drift apart on who is in scope: the story-status pill
    endpoint deliberately re-derives its profile set from this exact function
    rather than re-implementing the DEVICE/guardian branch, so a future change
    to one endpoint's scoping cannot silently widen the other's.

    Args:
        ctx: The request context (principal + unit-of-work session).

    Returns:
        list[ChildProfile]: All family profiles for a guardian or a DEVICE
            principal (ADR-014 phase 2: the picker needs the family's
            profiles to offer without a live guardian bearer); the single
            assigned profile for a child; empty if the principal has none.
    """
    # #CRITICAL: security: a DEVICE principal carries no profile_ids (ADR-014
    # phase 1 design: the grant is family-scoped, not profile-scoped), so it
    # is handled as its own branch, scoped strictly to principal.family_id
    # (never a client-supplied id) rather than falling through to the
    # profile_ids-based query below, which would otherwise always yield an
    # empty list for a device token.
    # #VERIFY: test_profiles.py::test_device_grant_lists_own_family_profiles
    # asserts the family's profiles are returned and a second family's are not;
    # tests/integration/test_profiles.py::
    # test_story_status_device_grant_scoped_to_own_family covers the same
    # invariant for the story-status endpoint built on this helper.
    if ctx.principal.role is Role.DEVICE:
        # #ASSUME: data-integrity: a deactivated profile (WS-J) is excluded
        # here too, mirroring _resolve_profiles, so a shared device's picker
        # never offers a profile an admin has taken offline.
        # #VERIFY: tests/integration/test_admin_profiles_api.py::
        # test_deactivated_profile_excluded_from_device_listing.
        rows = await ctx.session.scalars(
            select(ChildProfile)
            .where(
                ChildProfile.family_id == ctx.principal.family_id,
                ChildProfile.deactivated_at.is_(None),
            )
            .order_by(ChildProfile.created_at.asc(), ChildProfile.id.asc())
        )
        return list(rows.all())
    # #CRITICAL: security: scope strictly to principal.profile_ids (resolved at
    # the auth boundary in deps.py), never to a client-supplied family or
    # profile id, so no cross-family row can ever appear (IDOR). profile_ids
    # already excludes deactivated profiles (_resolve_profiles).
    # #VERIFY: test_profiles.py::test_guardian_lists_own_family_profiles asserts
    # family B's profile is absent from guardian A's list; tests/integration/
    # test_profiles.py::test_story_status_guardian_scoped_to_own_profile_ids
    # covers the same invariant for the story-status endpoint.
    if not ctx.principal.profile_ids:
        return []
    rows = await ctx.session.scalars(
        select(ChildProfile)
        .where(ChildProfile.id.in_(ctx.principal.profile_ids))
        # Stable order: creation order matches the wireframe's grid intent and
        # avoids DB-dependent row order flicker; id breaks created_at ties.
        .order_by(ChildProfile.created_at.asc(), ChildProfile.id.asc())
    )
    return list(rows.all())


@router.get("/profiles")
async def list_profiles(ctx: Context) -> ProfileListView:
    """List the child profiles the calling principal may act on.

    Args:
        ctx: The request context (principal + unit-of-work session).

    Returns:
        ProfileListView: All family profiles for a guardian or a DEVICE
            principal (ADR-014 phase 2: the picker needs the family's
            profiles to offer without a live guardian bearer); the single
            assigned profile for a child; empty if the principal has none.
    """
    rows = await _listable_profiles(ctx)
    return ProfileListView(profiles=[_view(row) for row in rows])


@router.get("/profiles/story-status")
async def list_profile_story_status(ctx: Context) -> ProfileStoryStatusListView:
    """Bulk "new story ready" pill status for every listable profile (W1.4).

    Serves the profile picker (design review 4.1): a device-grant or
    not-yet-handed-off guardian principal, called BEFORE any child session is
    minted, so a per-profile ``GET /library`` (which a picker-stage principal
    could not even authorize for a sibling child, per
    ``ProfilePickerPage.tsx``'s own deferred-work comment) is never an option
    here. ``has_new_story`` is a plain boolean derived purely from
    ``storybook_assignment`` timing; see ``_NEW_STORY_WINDOW`` for the "new"
    definition and why it is a 7-day fallback rather than a last-session
    comparison.

    Args:
        ctx: The request context (principal + unit-of-work session).

    Returns:
        ProfileStoryStatusListView: One boolean-only entry per profile
        ``_listable_profiles`` returns for this caller -- never more, never a
        title or count. A profile with no recent assignment reads
        ``has_new_story=False``, not merely absent.
    """
    # #CRITICAL: security: profile scope is derived from the EXACT SAME
    # ``_listable_profiles`` helper ``GET /profiles`` uses, not a
    # re-implementation, so this endpoint can never show a caller a profile
    # (or, by extension, that profile's pill state) it could not already list
    # by name. No sibling-library read ever happens: only
    # ``storybook_assignment`` rows for ids already in this scoped set are
    # queried.
    # #VERIFY: tests/integration/test_authz_matrix.py ROUTE_TABLE entry for
    # ("GET", "/api/v1/profiles/story-status") pins the same allowed-role set
    # as ("GET", "/api/v1/profiles"); tests/integration/test_profiles.py::
    # test_story_status_cross_family_profile_never_appears.
    rows = await _listable_profiles(ctx)
    if not rows:
        return ProfileStoryStatusListView(statuses=[])
    profile_ids = [row.id for row in rows]
    cutoff = datetime.now(UTC) - _NEW_STORY_WINDOW
    # #CRITICAL: security: the response never carries storybook_id or title --
    # only the profile_id already in `profile_ids` (itself already
    # caller-scoped above) and a bool. Even if a future edit widened this
    # query's SELECT list by mistake, ProfileStoryStatusView's schema (extra
    # fields silently dropped by Pydantic on construction, since only
    # profile_id/has_new_story are ever passed to it below) is the second
    # layer that keeps a title from ever reaching the wire.
    # #VERIFY: tests/integration/test_profiles.py::
    # test_story_status_response_never_carries_a_title_or_count.
    new_rows = await ctx.session.scalars(
        select(StorybookAssignment.child_profile_id)
        .where(
            StorybookAssignment.child_profile_id.in_(profile_ids),
            StorybookAssignment.created_at >= cutoff,
        )
        .distinct()
    )
    return _build_story_status_view(profile_ids, set(new_rows.all()))


def _build_story_status_view(
    profile_ids: list[uuid.UUID], new_profile_ids: set[uuid.UUID]
) -> ProfileStoryStatusListView:
    """Assemble the boolean-only response from a scoped id list and a "new" set.

    Pure and DB-free (mirrors ``notifications/registry.py``'s composer
    pattern), so it is unit-testable with plain constructed fixtures -- no
    session, no ASGI, no principal. Kept as the sole place that turns "is this
    id in the new set" into a ``ProfileStoryStatusView``, so a future field
    added to that view can never accidentally be sourced from anything other
    than ``profile_id``/membership.

    Args:
        profile_ids: The caller-scoped profile ids, in display order
            (``_listable_profiles``'s own ordering is preserved end to end).
        new_profile_ids: The subset with a ``storybook_assignment`` inside
            ``_NEW_STORY_WINDOW``.

    Returns:
        ProfileStoryStatusListView: One entry per ``profile_ids``, in order.
    """
    return ProfileStoryStatusListView(
        statuses=[
            ProfileStoryStatusView(
                profile_id=str(profile_id),
                has_new_story=profile_id in new_profile_ids,
            )
            for profile_id in profile_ids
        ]
    )


@router.post("/profiles", status_code=201, responses=error_responses(400))
async def create_profile(body: ProfileCreateBody, ctx: Context) -> ProfileView:
    """Create a child profile in the calling guardian's family.

    Args:
        body: The new profile's fields.
        ctx: The request context (principal + unit-of-work session).

    Returns:
        ProfileView: The stored profile.

    Raises:
        AuthorizationError: If the caller is not a guardian.
        BusinessLogicError: If the calling guardian has no recorded VPC
            consent (Phase 2 / ADR-018 D1).
    """
    _require_guardian(ctx.principal)
    await _require_consent(ctx)
    # #ASSUME: data integrity: family_id comes from the verified principal,
    # never from the request body (extra=forbid also rejects it there).
    # #VERIFY: test_profiles.py::test_create_rejects_unknown_fields.
    # #ASSUME: data integrity: an omitted content_flag_caps/banned_themes on
    # create means "no override" (an empty caps dict / no theme list), not
    # "inherit some other default"; there is nothing else to inherit from at
    # creation time.
    # #VERIFY: test_profiles.py::test_create_defaults_g2_fields_to_empty.
    # #CRITICAL: security: display_name renders directly into a child's own
    # story prose (ADR-023 plan 5.2); validated before the row is built.
    # #VERIFY: tests/integration/test_personalization_api.py::
    # test_create_profile_rejects_denylisted_display_name.
    validate_display_name(body.display_name, body.age_band.value)
    row = ChildProfile(
        family_id=ctx.principal.family_id,
        display_name=body.display_name,
        age_band=body.age_band.value,
        reading_level_cap=body.reading_level_cap,
        avatar=body.avatar,
        tts_enabled=body.tts_enabled,
        reduce_motion=body.reduce_motion,
        allowed_content_flags=(
            body.content_flag_caps.model_dump(exclude_none=True)
            if body.content_flag_caps is not None
            else {}
        ),
        banned_themes=(
            list(body.banned_themes) if body.banned_themes is not None else None
        ),
        # #CRITICAL: payment/financial: the G3 envelope fields authorize
        # automatic generation spend (ADR-015); they are guardian-set only,
        # and enforcement lives in story_requests.service.can_auto_approve.
        # #VERIFY: test_profiles.py::test_create_and_update_envelope_fields.
        request_auto_approve=body.request_auto_approve,
        monthly_request_envelope=body.monthly_request_envelope,
        # W3.4: omitted at creation means "no override, follow the P-A band
        # default" (see ProfileCreateBody's field docstring).
        ring_enabled=body.ring_enabled,
        ring_goal_days=body.ring_goal_days,
        badges_enabled=body.badges_enabled,
        time_capture_paused=body.time_capture_paused,
    )
    ctx.session.add(row)
    # UnitOfWorkMiddleware commits on success, just before the response is sent
    # (the dependency's teardown commit is only the fallback); flush + refresh
    # to read back the server-generated id and timestamp (same pattern as
    # ratings.py).
    await ctx.session.flush()
    await ctx.session.refresh(row, ["created_at"])
    return _view(row)


@router.patch("/profiles/{profile_id}", responses=error_responses(404))
async def update_profile(
    profile_id: str, body: ProfileUpdateBody, ctx: Context
) -> ProfileView:
    """Partially update a child profile in the guardian's own family.

    Args:
        profile_id: The profile to update.
        body: The fields to change; omitted fields are untouched. An explicit
            ``null`` clears only ``avatar`` and ``pin``; on the other fields
            it is a no-op (see ProfileUpdateBody).
        ctx: The request context (principal + unit-of-work session).

    Returns:
        ProfileView: The updated profile.

    Raises:
        ValidationError: If profile_id is not a UUID.
        AuthorizationError: If the caller is not a guardian, or the profile is
            not in the caller's family (or does not exist; both are 403 so the
            endpoint leaks nothing about other families' ids).
        ResourceNotFoundError: If the row vanished between authorization and
            load (concurrent delete).
    """
    _require_guardian(ctx.principal)
    parsed = parse_uuid(profile_id, "profile_id")
    # #CRITICAL: security: authorize_profile checks the id against the
    # principal's own family set, so cross-family ids and unknown ids are both
    # 403 (no existence oracle).
    # #VERIFY: test_profiles.py::test_guardian_cannot_update_other_familys_profile.
    authorize_profile(ctx.principal, parsed)
    row = await ctx.session.get(ChildProfile, parsed)
    if row is None:
        msg = f"profile '{profile_id}' not found"
        raise ResourceNotFoundError(msg)
    fields = body.model_fields_set
    _apply_simple_fields(row, body)
    if "avatar" in fields:
        # Explicit null clears; omitted leaves unchanged (model_fields_set).
        row.avatar = body.avatar
    if "pin" in fields:
        # P6-07: a PinCode-validated 4-8 digit string sets or replaces the
        # picker PIN; an explicit null removes it; omitted leaves it unchanged.
        # Only the derived hash is stored; the raw PIN is discarded here.
        # #CRITICAL: timing: hash_pin runs 600k PBKDF2 iterations (100-300ms
        # of pure CPU); calling it inline would stall the single-process
        # event loop for every concurrent request. Offload to a worker
        # thread (repo idiom: covers/service.py, covers/storage.py).
        # #VERIFY: tests/integration/test_profiles.py PIN set/clear paths.
        if body.pin is not None:
            row.pin_hash = await asyncio.to_thread(hash_pin, body.pin)
        else:
            row.pin_hash = None
    # GDPR Article 18/21: non-null-applies (see ProfileUpdateBody). True sets
    # processing_restricted_at; False clears it. Idempotent either way (no
    # error re-setting an already-restricted profile, mirroring how
    # request_auto_approve's toggle behaves).
    if body.processing_restricted is not None:
        row.processing_restricted_at = (
            datetime.now(UTC) if body.processing_restricted else None
        )
    _apply_g2_content_controls(row, body)
    _apply_gamification_settings(row, body)
    await ctx.session.flush()
    return _view(row)


@router.delete(
    "/profiles/{profile_id}", status_code=204, responses=error_responses(404)
)
async def delete_profile(profile_id: str, ctx: Context) -> None:
    """Permanently erase a child profile and all data linked to it.

    GDPR Article 17 / COPPA 312.10 (remediation plan Phase 3b). Every table
    keyed on this profile (reading state, completions, ratings, storybook
    assignments, kid flags, and its own login row if the child has one)
    cascades at the database level (Phase 3a); story requests the child
    submitted are de-linked (``profile_id`` set null) rather than deleted,
    since they remain family-owned content and may already have produced a
    published story.

    ``purge_profile_personalization`` (ADR-028) is called explicitly before
    the row delete: its two target tables (``child_profile_personalization``
    and ``character``) both already cascade at the database level, so this
    call changes nothing about what ends up erased, but it makes
    ``PURGE_TARGETS``'s claim about where the character_name slot's value
    lives an assertion this route actually exercises, rather than one that
    is only true because a foreign key happens to agree with it.

    Unlike ``update_profile``, this deliberately checks family ownership
    (``authorize_family``) rather than ``authorize_profile``: a profile a
    guardian has already deactivated is excluded from
    ``principal.profile_ids`` (see ``api/deps.py::_resolve_profiles``), but
    an erasure request must still succeed for a deactivated profile -- that
    is, if anything, the MORE likely case for a real deletion request.

    Args:
        profile_id: The child profile to delete (path).
        ctx: The request context (principal + unit-of-work session).

    Raises:
        AuthorizationError: If the caller is not a guardian, or the profile
            is not in the caller's family.
        ResourceNotFoundError: If no profile with this id exists.
    """
    _require_guardian(ctx.principal)
    parsed = parse_uuid(profile_id, "profile_id")
    row = await ctx.session.get(ChildProfile, parsed)
    if row is None:
        msg = f"profile '{profile_id}' not found"
        raise ResourceNotFoundError(msg)
    # #CRITICAL: security: family ownership, not profile_ids membership (see
    # docstring): a deactivated profile must still be deletable by its own
    # family's guardian.
    # #VERIFY: tests/integration/test_deletion_drill.py::
    # test_delete_profile_removes_child_linked_rows,
    # ::test_delete_profile_rejects_cross_family_profile.
    authorize_family(ctx.principal, row.family_id)
    await purge_profile_personalization(ctx.session, row.id)
    await ctx.session.delete(row)
    await ctx.session.flush()
