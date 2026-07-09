"""Admin cover-generation endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from cyo_adventure.api.deps import CurrentPrincipal, DbSession
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ConfigurationError,
    ResourceNotFoundError,
)
from cyo_adventure.covers.worker import enqueue_cover
from cyo_adventure.db.models import StorybookVersion

router = APIRouter(prefix="/api/v1", tags=["covers"])


class CoverStatusView(BaseModel):
    """Cover generation status for one story version."""

    cover_status: str
    cover_url: str | None = None


def _require_admin(principal: CurrentPrincipal) -> None:
    if not principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg, required_permission="admin")


@router.post("/storybooks/{storybook_id}/versions/{version}/cover")
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
        or not settings.supabase_service_key
        or not settings.supabase_url
    ):
        msg = "cover generation is not configured"
        raise ConfigurationError(msg)
    row = await session.get(StorybookVersion, (storybook_id, version))
    if row is None:
        msg = "storybook version not found"
        raise ResourceNotFoundError(msg)
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
    enqueue_cover(storybook_id, version, settings)
    return CoverStatusView(cover_status="generating", cover_url=row.cover_image_url)


@router.get("/storybooks/{storybook_id}/versions/{version}/cover")
async def cover_status(
    storybook_id: str,
    version: int,
    principal: CurrentPrincipal,
    session: DbSession,
) -> CoverStatusView:
    """Return current cover status/URL for polling (admin only)."""
    _require_admin(principal)
    row = await session.get(StorybookVersion, (storybook_id, version))
    if row is None:
        msg = "storybook version not found"
        raise ResourceNotFoundError(msg)
    return CoverStatusView(cover_status=row.cover_status, cover_url=row.cover_image_url)
