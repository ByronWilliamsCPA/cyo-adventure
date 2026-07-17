"""Admin cover-generation endpoints."""

from __future__ import annotations

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
from cyo_adventure.covers.worker import enqueue_cover
from cyo_adventure.db.models import StorybookVersion
from cyo_adventure.middleware.correlation import get_correlation_id

router = APIRouter(
    prefix="/api/v1", tags=["covers"], responses=error_responses(401, 403, 404)
)


class CoverStatusView(BaseModel):
    """Cover generation status for one story version."""

    cover_status: str
    cover_url: str | None = None


def _require_admin(principal: CurrentPrincipal) -> None:
    if not principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg, required_permission="admin")


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
        return CoverStatusView(cover_status="generating", cover_url=row.cover_image_url)
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
    return CoverStatusView(cover_status="generating", cover_url=row.cover_image_url)


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
    return CoverStatusView(cover_status=row.cover_status, cover_url=row.cover_image_url)
