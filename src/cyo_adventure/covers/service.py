"""Orchestrate cover generation: prompt -> generate -> optimize -> upload."""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import structlog
from sqlalchemy import select

from cyo_adventure.core.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    ResourceNotFoundError,
)
from cyo_adventure.covers.optimize import optimize_cover as _optimize_cover
from cyo_adventure.covers.prompt import build_cover_prompt
from cyo_adventure.covers.provider import generate_cover_image
from cyo_adventure.covers.storage import cover_object_key, upload_cover
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

    from cyo_adventure.api.deps import Principal
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

    Sets ``cover_status`` to ``generating`` first (committed), then
    ``pending_review`` on success or ``failed`` on any error. Never raises;
    mirrors the generation worker's own-session/explicit-commit discipline.

    A successful generation deliberately stops at ``pending_review``, not
    ``ready`` (H2, security-hardening-plan-2026-07.md): before this fix, a
    generated image reached every assigned child's library card the moment
    the provider returned it, with the only safety net being the provider's
    own refusal behavior and the prose guardrails in
    ``covers/prompt.py``. ``covers.service.approve_cover`` is now the sole
    path from ``pending_review`` to ``ready``, and every API read path that
    can hand a client a cover URL gates on ``cover_status == "ready"``
    (``api/library.py``, ``api/recommendations.py``, ``api/covers.py``), so
    no API response carries a pending_review cover's URL until that
    approval happens.

    Scope of that guarantee: it covers the API surface, not the stored
    bytes. Keeping the R2 bucket private (no public custom domain or r2.dev
    binding) is the primary control on the stored image, and is
    infrastructure-side, not code (see the ``#CRITICAL: security`` invariant
    at the top of ``covers/storage.py``; UW-M07 records the 2026-07-28
    incident where that binding was live and the 2026-07-30 fix). This
    function additionally mints a random ``cover_object_salt`` per cover
    (defense in depth, not a substitute for the bucket being private): the
    R2 key folds it in via ``covers/storage.py::cover_object_key``, so
    knowing ``storybook_id`` and ``version`` alone is no longer sufficient
    to reach the object even if the public binding is ever mistakenly
    restored.
    """
    # #CRITICAL: concurrency: this runs in the worker's own AsyncSession, not the
    # request unit-of-work; it commits explicitly at each state transition.
    # #VERIFY: sets generating->commit, then pending_review->commit, or
    # failed->commit.
    # #CRITICAL: security: H2 fix, human-approval half. An automated
    # image-safety classifier (the moderation/ analogue of the story-text
    # gate) does NOT exist in this codebase yet and is deliberately out of
    # scope for this change (a real image-classifier integration is a much
    # larger, separately-scoped piece of work); human approval via
    # approve_cover is the sole gate right now, not a second independent
    # layer the way text has validator+moderation+approval.
    # #VERIFY: before removing this marker, confirm an automated
    # image-safety check runs (and can BLOCK) between the provider's
    # response and cover_status="pending_review" below, then update this
    # docstring and the H2 status line in
    # docs/planning/security-hardening-plan-2026-07.md accordingly.
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
        # #CRITICAL: security: UW-M07 defense-in-depth stopgap -- a fresh
        # 128-bit token per cover, so the R2 key (below) is not derivable
        # from (storybook_id, version) alone. See this function's docstring
        # and covers/storage.py::cover_object_key for the full rationale;
        # this does not replace the bucket needing to stay private.
        # #VERIFY: tests/integration/test_cover_service.py::
        # test_generate_cover_stores_a_random_object_salt.
        salt = secrets.token_hex(16)
        key = cover_object_key(storybook_id, version, salt)
        public_url = await upload(optimized, key, settings)
        row.cover_object_salt = salt
        row.cover_image_url = f"{public_url}?v={int(time.time())}"
        row.cover_status = "pending_review"
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


async def approve_cover(
    session: AsyncSession,
    principal: Principal,
    storybook_id: str,
    version: int,
) -> StorybookVersion:
    """Approve a pending-review cover, stamping approval provenance.

    The human-approval half of the H2 fix
    (``docs/planning/security-hardening-plan-2026-07.md``): a generated
    cover stops at ``cover_status == "pending_review"`` (``generate_cover``,
    above) and cannot become ``"ready"``, the only status api/library.py
    will surface to a child's library card, without an explicit admin
    approval recorded here. Mirrors how ``publishing.service.approve``
    stamps ``approved_by``/``published_at`` for story text.

    Args:
        session: The request session (caller owns the transaction; this
            function flushes but never commits, per the package's
            handlers-never-commit unit-of-work convention).
        principal: The approving admin.
        storybook_id: The story whose cover is being approved.
        version: The version number of the cover being approved.

    Returns:
        StorybookVersion: The stamped version row.

    Raises:
        AuthorizationError: If ``principal`` does not hold the admin
            capability. api/covers.py's ``_require_admin`` already gates on
            this before calling; this is a defense-in-depth re-check at the
            service boundary, mirroring ``publishing.service.approve``.
        ResourceNotFoundError: If the version row does not exist.
        BusinessLogicError: If the cover is not currently
            ``"pending_review"`` (never generated, already approved, or a
            failed/in-flight generation) -- ``rule="cover_approve_not_pending"``.
    """
    # #CRITICAL: security: this is the SOLE path that may set
    # cover_status="ready", and it stamps cover_approved_by/cover_approved_at
    # in the same operation, so no API read path serves a cover URL to a
    # child's library card without a recorded human approver (the H2 fix's
    # core invariant, mirroring the approved_by invariant
    # publishing.service.approve holds for story text). Direct object-storage
    # access to the deterministic R2 key is out of this invariant's reach and
    # is controlled by keeping the bucket private (covers/storage.py).
    # #VERIFY: tests/integration/test_cover_service.py::
    # test_approve_cover_sets_ready_and_stamps_approver; a non-admin/wrong-status
    # rejection is covered by test_approve_cover_rejects_non_admin and
    # test_approve_cover_rejects_when_not_pending_review.
    if not principal.is_admin:
        msg = "admin role required to approve a cover"
        raise AuthorizationError(msg, required_permission="admin")
    row = await session.get(StorybookVersion, (storybook_id, version))
    if row is None:
        msg = f"version {version} of storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(
            msg,
            resource_type="StorybookVersion",
            resource_id=f"{storybook_id}:{version}",
        )
    if row.cover_status != "pending_review":
        msg = "cannot approve a cover that is not pending review"
        raise BusinessLogicError(
            msg,
            rule="cover_approve_not_pending",
            context={"cover_status": row.cover_status},
        )
    row.cover_status = "ready"
    row.cover_approved_by = principal.user_id
    row.cover_approved_at = datetime.now(UTC)
    await session.flush()
    return row
