"""Guardian storage/download view endpoints (G15 remainder).

The other G15 half (device list/revoke) already ships via
``api/device_grants.py``; this module is the missing piece, letting the
client report which books are cached offline on which device
(``frontend/src/offline/db.ts``'s ``storybooks`` IndexedDB store) so a
guardian has something to see. ``device_id`` here is a client-generated
persistent id, a separate identity from ``device_grant.jti`` (the kid-mode
device-authorization token); see ``DeviceDownload``'s docstring in
``db/models.py`` for why the two do not coincide.

Report/remove is ownership-scoped like ``flags.py``: a guardian or a child
may report for a profile they own (``authorize_profile``). List is
guardian/admin-only and family-scoped, mirroring
``device_grants.py::list_device_grants``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from cyo_adventure.api.deps import Context, authorize_profile, parse_uuid
from cyo_adventure.api.schemas import (
    DeviceDownloadReportBody,
    DeviceDownloadView,
    error_responses,
)
from cyo_adventure.core.exceptions import AuthorizationError, ResourceNotFoundError
from cyo_adventure.db.models import (
    ChildProfile,
    DeviceDownload,
    Storybook,
    StorybookVersion,
)

router = APIRouter(prefix="/api/v1", tags=["offline-downloads"])

_ADULT_ROLE_REQUIRED = "guardian or admin role required"


@router.put("/device-downloads", status_code=204, responses=error_responses(403, 404))
async def report_device_download(body: DeviceDownloadReportBody, ctx: Context) -> None:
    """Report that a device has (or still has) a book cached offline.

    Upserts on ``(device_id, profile_id, storybook_id)``: a first report
    creates the row (``created_at`` = now); a repeat report (a later re-open
    of the same cached book, or a periodic re-confirm) only advances
    ``updated_at``, the guardian-visible "last confirmed" signal.

    Unlike ``flags.py``'s assignment gate, this endpoint does NOT require
    the book still be assigned: a book unassigned after it was downloaded
    should still show up as "still cached" until the client's own eviction
    (``revocation.ts``) reports it gone, since that removal path is the
    thing this table exists to make visible, not something this endpoint
    should race ahead of.

    Args:
        body: The reporting device, profile, and book.
        ctx: The request context (principal and session).

    Raises:
        AuthorizationError: If the caller may not act on the profile (-> 403).
        ResourceNotFoundError: If the profile or the book does not exist
            (-> 404).
    """
    profile_uuid = parse_uuid(body.profile_id, "profile_id")
    # #CRITICAL: security: guardian may report for any family profile, a
    # child only for its own; mirrors flags.py::create_flag.
    # #VERIFY: test_offline_downloads_api.py::test_report_wrong_profile_is_403.
    authorize_profile(ctx.principal, profile_uuid)

    profile = await ctx.session.get(ChildProfile, profile_uuid)
    if profile is None:
        msg = "profile not found"
        raise ResourceNotFoundError(msg)

    # #ASSUME: data-integrity: storybook_id is a client-supplied string
    # carrying a real FK to storybook.id. Without this check an unknown id
    # reaches the INSERT and surfaces as an unhandled ForeignKeyViolation
    # (app.py registers no IntegrityError handler), so the caller gets a bare
    # 500 where the profile branch two lines above correctly gives a 404.
    # #VERIFY: test_offline_downloads_api.py::test_report_unknown_book_is_404.
    if await ctx.session.get(Storybook, body.storybook_id) is None:
        msg = "storybook not found"
        raise ResourceNotFoundError(msg)

    # #CRITICAL: concurrency: two concurrent reports for the same
    # (device_id, profile_id, storybook_id) key (e.g. two tabs re-confirming
    # a cached book at once) would both observe "no existing row" under a
    # plain read-then-insert and both attempt INSERT, raising a UNIQUE
    # violation on uq_device_download_device_profile_book. An atomic
    # upsert closes the race instead of merely narrowing it.
    # #VERIFY: test_offline_downloads_api.py::test_concurrent_reports_do_not_conflict.
    stmt = pg_insert(DeviceDownload).values(
        family_id=profile.family_id,
        child_profile_id=profile_uuid,
        device_id=body.device_id,
        storybook_id=body.storybook_id,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_device_download_device_profile_book",
        set_={"updated_at": datetime.now(UTC)},
    )
    await ctx.session.execute(stmt)


@router.delete("/device-downloads", status_code=204)
async def remove_device_download(
    device_id: str, storybook_id: str, ctx: Context
) -> None:
    """Report that a device no longer has a book cached offline.

    Takes no ``profile_id``, because the client's own eviction paths
    (``downloadBudget.ts``'s space-pressure eviction,
    ``revocation.ts``'s server-directed removal) operate on
    ``deleteStorybooksById``, which removes every cached version of a book
    ID for every profile on the device at once, not one profile at a time.
    Removes every matching row the caller may act on, which is more than one
    whenever two profiles the caller controls both had it downloaded on that
    device.

    Scope is the principal's own profile set, not the whole family. A
    guardian's set covers the family, so an adult eviction still clears every
    profile's row as the client paths expect; a child's set covers only
    itself, so a sibling's row survives its eviction and is left to go stale
    like any other unreported removal (see ``DeviceDownload``'s
    best-effort-snapshot contract).

    Args:
        device_id: The reporting device's persistent id (query param).
        storybook_id: The no-longer-cached book (query param).
        ctx: The request context (principal and session).
    """
    # #CRITICAL: security: family scoping alone is not authorization here.
    # Every principal carries a family_id, including CHILD and DEVICE, and
    # this endpoint's only other inputs are a device_id and a storybook_id,
    # neither of which is secret within a family. Scoping solely on family
    # would let any child delete a sibling's download rows on any device by
    # naming them. Constraining to the principal's own profile set is the
    # same rule authorize_profile applies to the PUT, expressed as a filter
    # because this endpoint is deliberately multi-row.
    # #VERIFY: test_offline_downloads_api.py::
    # test_remove_does_not_touch_another_profiles_row_for_a_child_principal.
    rows = await ctx.session.scalars(
        select(DeviceDownload).where(
            DeviceDownload.device_id == device_id,
            DeviceDownload.storybook_id == storybook_id,
            DeviceDownload.family_id == ctx.principal.family_id,
            DeviceDownload.child_profile_id.in_(ctx.principal.profile_ids),
        )
    )
    for row in rows:
        await ctx.session.delete(row)


@router.get("/device-downloads", responses=error_responses(403))
async def list_device_downloads(ctx: Context) -> list[DeviceDownloadView]:
    """List the caller's family's offline-download inventory.

    Guardian/admin only, family-scoped (mirrors
    ``device_grants.py::list_device_grants``); a device or child principal
    has no guardian-console use for this view.

    Args:
        ctx: The request context (principal and session).

    Returns:
        list[DeviceDownloadView]: Every download row for the family, newest
        first. The frontend groups by ``device_id`` for display; this
        endpoint does not group, since a single flat list is simpler to
        project and test, and grouping is presentation, not data.

    Raises:
        AuthorizationError: If a device or child principal reaches this
            endpoint (-> 403).
    """
    if not (ctx.principal.is_guardian or ctx.principal.is_admin):
        msg = _ADULT_ROLE_REQUIRED
        raise AuthorizationError(msg)
    rows = await ctx.session.scalars(
        select(DeviceDownload)
        .where(DeviceDownload.family_id == ctx.principal.family_id)
        .order_by(DeviceDownload.updated_at.desc())
    )
    downloads = list(rows.all())
    if not downloads:
        return []

    profile_ids = {row.child_profile_id for row in downloads}
    profiles = await ctx.session.scalars(
        select(ChildProfile).where(ChildProfile.id.in_(profile_ids))
    )
    names = {profile.id: profile.display_name for profile in profiles}

    storybook_ids = {row.storybook_id for row in downloads}
    books = await ctx.session.scalars(
        select(Storybook).where(Storybook.id.in_(storybook_ids))
    )
    pairs = [
        (book.id, book.current_published_version)
        for book in books
        if book.current_published_version is not None
    ]
    titles: dict[str, str] = {}
    if pairs:
        versions = await ctx.session.scalars(
            select(StorybookVersion).where(
                StorybookVersion.storybook_id.in_([p[0] for p in pairs])
            )
        )
        wanted = dict(pairs)
        for version in versions:
            if version.version != wanted.get(version.storybook_id):
                continue
            blob = version.blob
            title = blob.get("title") if isinstance(blob, dict) else None
            if isinstance(title, str) and title:
                titles[version.storybook_id] = title

    return [
        DeviceDownloadView(
            id=str(row.id),
            device_id=row.device_id,
            profile_id=str(row.child_profile_id),
            profile_name=names.get(row.child_profile_id, "Unknown"),
            storybook_id=row.storybook_id,
            storybook_title=titles.get(row.storybook_id),
            downloaded_at=row.created_at,
            last_confirmed_at=row.updated_at,
        )
        for row in downloads
    ]
