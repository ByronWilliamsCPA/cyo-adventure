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

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import (
    Context,
    Principal,
    Role,
    authorize_profile,
    parse_uuid,
)
from cyo_adventure.api.schemas import (
    ContentFlagCaps,
    ProfileCreateBody,
    ProfileListView,
    ProfileUpdateBody,
    ProfileView,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
)
from cyo_adventure.core.pin import hash_pin
from cyo_adventure.db.models import ChildProfile
from cyo_adventure.storybook.models import AgeBand

router = APIRouter(prefix="/api/v1", tags=["profiles"])


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
        has_pin=row.pin_hash is not None,
        content_flag_caps=ContentFlagCaps.model_validate(
            row.allowed_content_flags or {}
        ),
        banned_themes=list(row.banned_themes or []),
        created_at=row.created_at,
    )


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
    # #CRITICAL: security: a DEVICE principal carries no profile_ids (ADR-014
    # phase 1 design: the grant is family-scoped, not profile-scoped), so it
    # is handled as its own branch, scoped strictly to principal.family_id
    # (never a client-supplied id) rather than falling through to the
    # profile_ids-based query below, which would otherwise always yield an
    # empty list for a device token.
    # #VERIFY: test_profiles.py::test_device_grant_lists_own_family_profiles
    # asserts the family's profiles are returned and a second family's are not.
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
        return ProfileListView(profiles=[_view(row) for row in rows.all()])
    # #CRITICAL: security: scope strictly to principal.profile_ids (resolved at
    # the auth boundary in deps.py), never to a client-supplied family or
    # profile id, so no cross-family row can ever appear (IDOR). profile_ids
    # already excludes deactivated profiles (_resolve_profiles).
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


@router.post("/profiles", status_code=201)
async def create_profile(body: ProfileCreateBody, ctx: Context) -> ProfileView:
    """Create a child profile in the calling guardian's family.

    Args:
        body: The new profile's fields.
        ctx: The request context (principal + unit-of-work session).

    Returns:
        ProfileView: The stored profile.

    Raises:
        AuthorizationError: If the caller is not a guardian.
    """
    _require_guardian(ctx.principal)
    # #ASSUME: data integrity: family_id comes from the verified principal,
    # never from the request body (extra=forbid also rejects it there).
    # #VERIFY: test_profiles.py::test_create_rejects_unknown_fields.
    # #ASSUME: data integrity: an omitted content_flag_caps/banned_themes on
    # create means "no override" (an empty caps dict / no theme list), not
    # "inherit some other default"; there is nothing else to inherit from at
    # creation time.
    # #VERIFY: test_profiles.py::test_create_defaults_g2_fields_to_empty.
    row = ChildProfile(
        family_id=ctx.principal.family_id,
        display_name=body.display_name,
        age_band=body.age_band.value,
        reading_level_cap=body.reading_level_cap,
        avatar=body.avatar,
        tts_enabled=body.tts_enabled,
        allowed_content_flags=(
            body.content_flag_caps.model_dump(exclude_none=True)
            if body.content_flag_caps is not None
            else {}
        ),
        banned_themes=(
            list(body.banned_themes) if body.banned_themes is not None else None
        ),
    )
    ctx.session.add(row)
    # The unit-of-work dependency commits on success; flush + refresh to read
    # back the server-generated id and timestamp (same pattern as ratings.py).
    await ctx.session.flush()
    await ctx.session.refresh(row, ["created_at"])
    return _view(row)


@router.patch("/profiles/{profile_id}")
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
    # #ASSUME: data integrity: an explicit null on the four non-avatar fields
    # is a deliberate no-op, not a clear; none of them has a legitimate empty
    # state (a profile always has a name, band, cap, and TTS setting), so the
    # is-not-None gates below silently ignore null rather than 422-ing.
    # #VERIFY: test_profiles.py::test_update_ignores_explicit_null_on_non_avatar_fields
    # pins the no-op; revisit if any of these fields ever gains clear semantics.
    if body.display_name is not None:
        row.display_name = body.display_name
    if body.age_band is not None:
        row.age_band = body.age_band.value
    if body.reading_level_cap is not None:
        row.reading_level_cap = body.reading_level_cap
    if body.tts_enabled is not None:
        row.tts_enabled = body.tts_enabled
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
    _apply_g2_content_controls(row, body)
    await ctx.session.flush()
    return _view(row)
