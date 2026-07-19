"""Orchestrate cover generation: prompt -> generate -> optimize -> upload."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import structlog
from sqlalchemy import select

from cyo_adventure.covers.optimize import optimize_cover as _optimize_cover
from cyo_adventure.covers.prompt import build_cover_prompt
from cyo_adventure.covers.provider import generate_cover_image
from cyo_adventure.covers.storage import upload_cover
from cyo_adventure.db.models import (
    ChildProfile,
    Concept,
    GenerationJob,
    StorybookVersion,
)
from cyo_adventure.generation.pii import PiiContext, assert_prompt_pii_safe

if TYPE_CHECKING:
    import uuid
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


@dataclass(frozen=True, slots=True)
class _ConceptContext:
    """The pieces of the owning concept a cover prompt/guard needs.

    Attributes:
        protagonist_name: The fictional protagonist name from the brief, or
            None if it could not be recovered.
        family_id: The owning family's id, or None if it could not be
            recovered (e.g. no Concept/GenerationJob row links to this
            storybook). A None family_id means the PII guard below has no
            registered names to screen against; the pattern-based checks in
            assert_prompt_pii_safe still run regardless.
    """

    protagonist_name: str | None
    family_id: uuid.UUID | None


async def _recover_concept_context(
    session: AsyncSession, storybook_id: str
) -> _ConceptContext:
    """Recover the protagonist name and owning family id via storybook -> job -> concept.

    Both pieces come from the same Concept row, so they are fetched in one
    query rather than two.
    """
    # #ASSUME: data integrity: GenerationJob.storybook_id is not a FK and a story
    # may have >1 job row; take the earliest and degrade to None on any gap.
    # #VERIFY: ORDER BY created_at LIMIT 1 + isinstance guards at each hop.
    row = (
        await session.execute(
            select(Concept.brief, Concept.family_id)
            .join(GenerationJob, GenerationJob.concept_id == Concept.id)
            .where(GenerationJob.storybook_id == storybook_id)
            .order_by(GenerationJob.created_at)
            .limit(1)
        )
    ).first()
    if row is None:
        return _ConceptContext(protagonist_name=None, family_id=None)
    brief, family_id = row
    protagonist_name: str | None = None
    if isinstance(brief, dict):
        protagonist = brief.get("protagonist")
        if isinstance(protagonist, dict):
            name = protagonist.get("name")
            protagonist_name = name if isinstance(name, str) and name else None
    return _ConceptContext(
        protagonist_name=protagonist_name,
        family_id=family_id,
    )


async def _pii_context_for_family(
    session: AsyncSession, family_id: uuid.UUID | None
) -> PiiContext:
    """Build a PiiContext from a family's registered real child display names.

    Mirrors the same query shape used at concept-creation time
    (api/generation.py::create_concept, story_requests/service.py::_build_concept)
    so the cover-art path is screened against the same registered-identifier
    set as every other egress point. A None family_id (context could not be
    recovered) yields an empty-names context; the pattern-based checks in
    assert_prompt_pii_safe still run regardless.
    """
    if family_id is None:
        return PiiContext(child_names=frozenset())
    rows = await session.scalars(
        select(ChildProfile.display_name).where(ChildProfile.family_id == family_id)
    )
    return PiiContext(child_names=frozenset(rows.all()))


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
        concept_context = await _recover_concept_context(session, storybook_id)
        blob = row.blob if isinstance(row.blob, dict) else {}
        prompt = build_cover_prompt(blob, concept_context.protagonist_name)
        # #CRITICAL: security: PII egress guard -- the cover-art prompt is sent
        # to an external image provider (Gemini) and, before this guard, was
        # the one path in the generation pipeline with zero PII screening: it
        # is built from story content (title, protagonist name, an excerpt),
        # any of which could echo a real child's registered name. Screen it
        # with the same guard every other provider call already goes through.
        # #VERIFY: test_service.py::test_generate_cover_blocks_on_pii_in_prompt.
        pii = await _pii_context_for_family(session, concept_context.family_id)
        assert_prompt_pii_safe(prompt, forbidden=pii)
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
