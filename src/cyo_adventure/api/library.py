"""Library and story-fetch endpoints.

A child sees only published stories in their own family. Per-profile age-band and
reading-level cap filtering is a Phase 4a concern; Phase 1 lists every published
story in the family and enforces profile/family access. Story fetch returns the
immutable Storybook JSON blob for a specific version.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import (
    CurrentPrincipal,
    DbSession,
    authorize_family,
    authorize_profile,
)
from cyo_adventure.api.schemas import LibraryItem, LibraryView
from cyo_adventure.core.exceptions import ResourceNotFoundError, ValidationError
from cyo_adventure.db.models import Storybook, StorybookVersion

if TYPE_CHECKING:
    from collections.abc import Mapping

router = APIRouter(prefix="/api/v1", tags=["library"])

_PUBLISHED = "published"


def _parse_profile_id(raw: str) -> uuid.UUID:
    """Parse a profile id, raising a 422-mapped error on bad input.

    Args:
        raw: The raw profile id string.

    Returns:
        uuid.UUID: The parsed id.

    Raises:
        ValidationError: If the value is not a valid UUID.
    """
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        msg = "profile_id must be a UUID"
        raise ValidationError(msg, field="profile_id", value=raw) from exc


def _library_item(
    storybook_id: str, blob: Mapping[str, object], version: int
) -> LibraryItem:
    """Build a library item from a stored Storybook blob."""
    metadata = blob.get("metadata") if isinstance(blob.get("metadata"), dict) else {}
    meta: Mapping[str, object] = metadata if isinstance(metadata, dict) else {}
    reading_level = meta.get("reading_level")
    target = 0.0
    if isinstance(reading_level, dict):
        raw_target = reading_level.get("target")
        target = float(raw_target) if isinstance(raw_target, (int, float)) else 0.0
    title = blob.get("title")
    age_band = meta.get("age_band")
    tier = meta.get("tier")
    return LibraryItem(
        id=storybook_id,
        title=title if isinstance(title, str) else storybook_id,
        version=version,
        age_band=age_band if isinstance(age_band, str) else "",
        tier=tier if isinstance(tier, int) else 0,
        reading_level_target=target,
    )


@router.get("/library", response_model=LibraryView)
async def list_library(
    profile_id: str,
    principal: CurrentPrincipal,
    session: DbSession,
) -> LibraryView:
    """List published stories visible to the given profile.

    Args:
        profile_id: The child profile requesting its library.
        principal: The authenticated principal.
        session: The request session.

    Returns:
        LibraryView: The published stories in the profile's family.
    """
    parsed = _parse_profile_id(profile_id)
    authorize_profile(principal, parsed)
    rows = await session.scalars(
        select(Storybook).where(
            Storybook.family_id == principal.family_id,
            Storybook.status == _PUBLISHED,
            Storybook.current_published_version.is_not(None),
        )
    )
    items: list[LibraryItem] = []
    for book in rows.all():
        published_version = book.current_published_version
        if published_version is None:
            continue
        version_row = await session.get(StorybookVersion, (book.id, published_version))
        if version_row is not None:
            items.append(_library_item(book.id, version_row.blob, published_version))
    return LibraryView(stories=items)


@router.get("/storybooks/{storybook_id}/versions/{version}")
async def get_storybook_version(
    storybook_id: str,
    version: int,
    principal: CurrentPrincipal,
    session: DbSession,
) -> dict[str, object]:
    """Return the immutable Storybook JSON for a specific version.

    Args:
        storybook_id: The story id.
        version: The story version.
        principal: The authenticated principal.
        session: The request session.

    Returns:
        dict[str, object]: The Storybook content blob.

    Raises:
        ResourceNotFoundError: If the story or version does not exist.
    """
    book = await session.get(Storybook, storybook_id)
    if book is None:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    authorize_family(principal, book.family_id)
    version_row = await session.get(StorybookVersion, (storybook_id, version))
    if version_row is None:
        msg = f"version {version} of storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    return version_row.blob
