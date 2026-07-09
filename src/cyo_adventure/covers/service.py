"""Orchestrate cover generation: prompt -> generate -> optimize -> upload."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import structlog
from sqlalchemy import select

from cyo_adventure.covers.optimize import optimize_cover as _optimize_cover
from cyo_adventure.covers.prompt import build_cover_prompt
from cyo_adventure.covers.provider import generate_cover_image
from cyo_adventure.covers.storage import upload_cover
from cyo_adventure.db.models import Concept, GenerationJob, StorybookVersion

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.core.config import Settings

_logger = structlog.get_logger(__name__)


class _OptimizeFn(Protocol):
    def __call__(
        self,
        source: bytes,
        /,
        *,
        max_width: int = ...,
        quality: int = ...,
        max_bytes: int = ...,
    ) -> bytes: ...


async def _recover_protagonist_name(
    session: AsyncSession, storybook_id: str
) -> str | None:
    """Recover the protagonist name via storybook -> job -> concept.brief."""
    # #ASSUME: data integrity: GenerationJob.storybook_id is not a FK and a story
    # may have >1 job row; take the earliest and degrade to None on any gap.
    # #VERIFY: ORDER BY created_at LIMIT 1 + isinstance guards at each hop.
    brief = await session.scalar(
        select(Concept.brief)
        .join(GenerationJob, GenerationJob.concept_id == Concept.id)
        .where(GenerationJob.storybook_id == storybook_id)
        .order_by(GenerationJob.created_at)
        .limit(1)
    )
    if not isinstance(brief, dict):
        return None
    protagonist = brief.get("protagonist")
    if not isinstance(protagonist, dict):
        return None
    name = protagonist.get("name")
    return name if isinstance(name, str) and name else None


def _maybe_backup(
    source: bytes, storybook_id: str, version: int, settings: Settings
) -> None:
    """Best-effort full-res backup to a local dir; never fails the job."""
    # #EDGE: external resources: this writes to a local filesystem path that
    # may not exist, may not be writable, or may live on a container volume
    # wiped at redeploy; it is a convenience copy, not durable storage.
    # #VERIFY: OSError is caught and logged; the cover job's status transition
    # never depends on this write succeeding.
    if not settings.covers_backup_dir:
        return
    try:
        target = Path(settings.covers_backup_dir) / storybook_id
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{version}.png").write_bytes(source)
    except OSError:
        _logger.warning(
            "cover_backup_failed", storybook_id=storybook_id, version=version
        )


async def generate_cover(
    storybook_id: str,
    version: int,
    *,
    session: AsyncSession,
    settings: Settings,
    generate: Callable[[str, Settings], bytes] = generate_cover_image,
    optimize: _OptimizeFn = _optimize_cover,
    upload: Callable[[bytes, str, Settings], Awaitable[str]] = upload_cover,
) -> None:
    """Generate, optimize, upload, and record a cover for one story version.

    Sets ``cover_status`` to ``generating`` first (committed), then ``ready`` on
    success or ``failed`` on any error. Never raises; mirrors the generation
    worker's own-session/explicit-commit discipline.
    """
    # #CRITICAL: concurrency: this runs in the worker's own AsyncSession, not the
    # request unit-of-work; it commits explicitly at each state transition.
    # #VERIFY: sets generating->commit, then ready->commit, or failed->commit.
    row = await session.get(StorybookVersion, (storybook_id, version))
    if row is None:
        _logger.warning(
            "cover_target_missing", storybook_id=storybook_id, version=version
        )
        return
    row.cover_status = "generating"
    await session.commit()
    try:
        protagonist = await _recover_protagonist_name(session, storybook_id)
        blob = row.blob if isinstance(row.blob, dict) else {}
        prompt = build_cover_prompt(blob, protagonist)
        source = await asyncio.to_thread(generate, prompt, settings)
        _maybe_backup(source, storybook_id, version, settings)
        optimized = await asyncio.to_thread(
            optimize,
            source,
            max_width=settings.cover_max_width,
            quality=settings.cover_quality,
            max_bytes=settings.cover_max_bytes,
        )
        key = f"{storybook_id}/{version}.webp"
        public_url = await upload(optimized, key, settings)
        row.cover_image_url = f"{public_url}?v={int(time.time())}"
        row.cover_status = "ready"
        await session.commit()
    except Exception:
        await session.rollback()
        fresh = await session.get(StorybookVersion, (storybook_id, version))
        if fresh is not None:
            fresh.cover_status = "failed"
            await session.commit()
        _logger.exception(
            "cover_generation_failed", storybook_id=storybook_id, version=version
        )
