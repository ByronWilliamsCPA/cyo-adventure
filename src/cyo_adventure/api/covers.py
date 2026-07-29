"""Admin cover-generation endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from cyo_adventure.api.deps import CurrentPrincipal, DbSession
from cyo_adventure.api.schemas import error_responses
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ConfigurationError,
    ExternalServiceError,
    ResourceNotFoundError,
)
from cyo_adventure.covers.service import approve_cover as _approve_cover
from cyo_adventure.covers.storage import generate_presigned_cover_url
from cyo_adventure.covers.worker import enqueue_cover
from cyo_adventure.db.models import StorybookVersion
from cyo_adventure.middleware.correlation import get_correlation_id

router = APIRouter(
    prefix="/api/v1", tags=["covers"], responses=error_responses(401, 403, 404)
)


class CoverStatusView(BaseModel):
    """Cover generation status for one story version.

    ``cover_approved_by``/``cover_approved_at`` are None until an admin
    approves a ``pending_review`` cover (H2, ``approve_cover`` endpoint
    below); they mirror ``ApprovedView.approved_by``/``published_at`` for
    story text.
    """

    cover_status: str
    cover_url: str | None = None
    cover_approved_by: str | None = None
    cover_approved_at: datetime | None = None


def _require_admin(principal: CurrentPrincipal) -> None:
    if not principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg, required_permission="admin")


async def _cover_url(row: StorybookVersion) -> str | None:
    """Return a fresh presigned cover URL, or None if no cover is ready yet.

    Args:
        row: The storybook version row.

    Returns:
        str | None: A short-lived signed GET URL when ``cover_status`` is
        ``"ready"`` or ``"pending_review"``; otherwise None. Never reads
        ``row.cover_image_url`` directly (that column is an upload-time
        audit value, not a URL to serve to readers -- see
        ``covers/storage.py``'s module note).
    """
    # #CRITICAL: security: covers are private-by-default in R2 (Phase 1d); the
    # only way a client legitimately learns a cover's URL is a freshly
    # generated, short-lived signed GET URL, computed here rather than read
    # from the stored (permanent, audit-only) cover_image_url column.
    # A pending_review cover is deliberately included here even though
    # api/library.py's child-facing read gate excludes it (cover_status ==
    # "ready" only): this function backs the three admin-only endpoints in
    # this module (request_cover, cover_status, approve_cover), all gated by
    # _require_admin before they ever call it, and the reviewer cannot judge
    # a cover it cannot see. library.py and recommendations.py compute their
    # own presigned URLs independently (via generate_presigned_cover_urls)
    # and are unaffected by this widening.
    # #VERIFY: test_covers_api.py::test_cover_status_returns_presigned_url_when_ready,
    # ::test_cover_status_returns_presigned_url_when_pending_review.
    if row.cover_status not in ("ready", "pending_review"):
        return None
    return await generate_presigned_cover_url(row.storybook_id, row.version, settings)


async def _status_view(row: StorybookVersion) -> CoverStatusView:
    """Build the wire view for a cover status row, including approval provenance."""
    return CoverStatusView(
        cover_status=row.cover_status,
        cover_url=await _cover_url(row),
        cover_approved_by=(
            str(row.cover_approved_by) if row.cover_approved_by is not None else None
        ),
        cover_approved_at=row.cover_approved_at,
    )


@router.post(
    "/storybooks/{storybook_id}/versions/{version}/cover",
    responses=error_responses(400),
)
async def request_cover(
    storybook_id: str,
    version: int,
    principal: CurrentPrincipal,
    session: DbSession,
) -> CoverStatusView:
    """Enqueue cover generation for a story version (admin only)."""
    # #CRITICAL: security: admin-only; validate config before enqueuing so a
    # doomed job is never queued.
    # #VERIFY: is_admin check + ConfigurationError when credentials are unset.
    _require_admin(principal)
    if (
        not settings.gemini_api_key
        or not settings.r2_account_id
        or not settings.r2_access_key_id
        or not settings.r2_secret_access_key
        or not settings.r2_public_base_url
    ):
        msg = "cover generation is not configured"
        raise ConfigurationError(msg)
    row = await session.get(StorybookVersion, (storybook_id, version))
    if row is None:
        msg = "storybook version not found"
        raise ResourceNotFoundError(msg)
    # #EDGE: concurrency: a cover already in flight must not be re-enqueued; a
    # duplicate admin click or aggressive poll would otherwise queue a second
    # billable Gemini job and reset visible progress. Treat in-flight as a no-op.
    # #VERIFY: test_request_cover_already_generating asserts no second enqueue.
    if row.cover_status == "generating":
        return CoverStatusView(
            cover_status="generating", cover_url=await _cover_url(row)
        )
    # #CRITICAL: timing dependencies: the console starts polling ~2s after this
    # response, but the shared "generation" queue can sit busy for 10-30s
    # before a worker dequeues the job and sets cover_status itself. Persist
    # "generating" here, before enqueueing, so the first poll never reads a
    # stale status (which would break the poll loop and invite a duplicate
    # click -> duplicate job). This intentionally deviates from the
    # handlers-never-commit unit-of-work convention (see deps.get_db_session):
    # committing here, before enqueue_cover, guarantees the worker's DB
    # connection can see "generating" the instant it dequeues. Enqueueing
    # before this commit would risk an orphaned job if the commit then failed;
    # committing first and letting enqueue fail after is the safer order,
    # tolerated by the 60s poll cap in ReviewDetailPage.
    # #VERIFY: test_admin_enqueues asserts the persisted row, not just the
    # response body.
    row.cover_status = "generating"
    await session.commit()
    # #CRITICAL: external resources: if the RQ broker is unreachable, enqueue
    # raises; roll the row off "generating" to "failed" (committed) before
    # surfacing the error so the console shows the retry affordance rather than
    # a spinner that never resolves.
    # #VERIFY: test_request_cover_enqueue_failure asserts cover_status=="failed".
    try:
        enqueue_cover(storybook_id, version, settings, get_correlation_id())
    except Exception as exc:
        row.cover_status = "failed"
        await session.commit()
        msg = "cover queue is unavailable"
        raise ExternalServiceError(msg) from exc
    return CoverStatusView(cover_status="generating", cover_url=await _cover_url(row))


@router.get("/storybooks/{storybook_id}/versions/{version}/cover")
async def cover_status(
    storybook_id: str,
    version: int,
    principal: CurrentPrincipal,
    session: DbSession,
) -> CoverStatusView:
    """Return current cover status/URL for polling (admin only)."""
    # #CRITICAL: security: admin-only status read; a non-admin must never learn
    # whether a cover exists or is in flight for a given story version.
    # #VERIFY: _require_admin raises AuthorizationError before any DB read.
    _require_admin(principal)
    row = await session.get(StorybookVersion, (storybook_id, version))
    if row is None:
        msg = "storybook version not found"
        raise ResourceNotFoundError(msg)
    return await _status_view(row)


@router.post(
    "/storybooks/{storybook_id}/versions/{version}/cover/approve",
    responses=error_responses(400, 404),
)
async def approve_cover(
    storybook_id: str,
    version: int,
    principal: CurrentPrincipal,
    session: DbSession,
) -> CoverStatusView:
    """Approve a pending-review cover so it becomes visible to children (admin only).

    H2 fix (security-hardening-plan-2026-07.md): the human-approval gate that
    ``generate_cover`` stops short of. A cover generated successfully sits at
    ``cover_status == "pending_review"``. ``_cover_url`` presigns it for this
    admin review surface only, and it stays withheld from every child library
    card (see ``api/library.py``'s ``cover_status == "ready"`` filter) until an
    admin calls this endpoint. That holds for every API read path; it says
    nothing about direct access to the stored object, whose key is
    deterministic and whose exposure is governed by the bucket-privacy
    invariant in ``covers/storage.py``.
    """
    # #CRITICAL: security: admin-only; covers.service.approve_cover re-checks
    # is_admin as defense in depth, mirroring approval.py::approve_storybook's
    # relationship with publishing.service.approve.
    # #VERIFY: test_cover_api.py::test_approve_cover_non_admin_forbidden.
    _require_admin(principal)
    row = await _approve_cover(session, principal, storybook_id, version)
    return await _status_view(row)
