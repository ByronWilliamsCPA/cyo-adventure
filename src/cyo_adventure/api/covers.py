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
    if not settings.gemini_api_key or not settings.supabase_service_key:
        msg = "cover generation is not configured"
        raise ConfigurationError(msg)
    row = await session.get(StorybookVersion, (storybook_id, version))
    if row is None:
        msg = "storybook version not found"
        raise ResourceNotFoundError(msg)
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
