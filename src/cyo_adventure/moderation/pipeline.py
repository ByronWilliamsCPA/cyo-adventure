"""The moderation pipeline: run stages, persist findings, drive the state machine.

Invoked from the generation worker after the draft rows are persisted and before
the request commit. Reads the persisted version's blob, runs Stage 0 then the LLM
stages, persists the aggregated report, and drives ``submit`` / ``auto_reject``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from pydantic import ValidationError

from cyo_adventure.core.exceptions import ResourceNotFoundError
from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.generation.guarded import PiiGuardedProvider
from cyo_adventure.moderation.classifiers import run_classifiers
from cyo_adventure.moderation.repair import attempt_repair
from cyo_adventure.moderation.report import (
    Finding,
    ModerationReport,
    Source,
    Verdict,
)
from cyo_adventure.moderation.review_provider import (
    ReviewProvider,
    build_review_provider,
)
from cyo_adventure.moderation.stages import (
    run_coherence_stage,
    run_engagement_stage,
    run_readability_stage,
    run_safety_stage,
)
from cyo_adventure.publishing import service
from cyo_adventure.storybook.models import Storybook as StoryModel
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.core.config import Settings
    from cyo_adventure.generation.pii import PiiContext
    from cyo_adventure.generation.provider import GenerationProvider

_logger = get_logger(__name__)
_MAX_REVIEW_TOKENS = 1024
_MAX_REPAIR_TOKENS = 32000


async def run_moderation_pipeline(
    *,
    session: AsyncSession,
    story_id: str,
    version: int,
    settings: Settings,
    generation_provider: GenerationProvider,
    pii: PiiContext,
) -> None:
    """Screen a persisted draft story and drive it to in_review or needs_revision.

    Args:
        session: The request session (caller owns the transaction).
        story_id: The persisted storybook id.
        version: The persisted version number.
        settings: Application settings (review provider and classifier keys).
        generation_provider: Provider used for the bounded auto-repair re-prompt.
        pii: PII context for the egress guard on review and repair prompts.

    Raises:
        ResourceNotFoundError: when the story or version row is missing.
    """
    # #CRITICAL: data-integrity: the rows must exist (just persisted as draft) or
    # the state-machine transition has nothing to act on.
    # #VERIFY: both session.get results are checked for None.
    storybook = await session.get(Storybook, story_id)
    version_row = await session.get(StorybookVersion, (story_id, version))
    if storybook is None or version_row is None:
        msg = f"storybook '{story_id}' v{version} not found for moderation"
        raise ResourceNotFoundError(msg)

    report = ModerationReport()
    review_provider, independent = build_review_provider(
        settings,
        generator_provider=settings.generation_provider,
        generator_model=version_row.model,
    )
    # #CRITICAL: security: every review prompt egresses story prose; the reviewer
    # MUST be PII-guarded exactly like generation before any stage runs.
    # #VERIFY: stages receive guarded_review, never the bare provider.
    guarded_review = PiiGuardedProvider(review_provider, forbidden=pii)
    report.reviewer_independent = independent
    if not independent:
        report.add(
            Finding(
                stage=0,
                source=Source.PIPELINE,
                category="reviewer_independence",
                verdict=Verdict.ADVISORY,
                message="reviewer is the same backend+model as the generator",
            )
        )

    # #CRITICAL: data-integrity: a corrupted stored blob must not crash the worker
    # and strand the story in draft; an invalid story is force-blocked so it routes
    # to auto_reject (needs_revision) below, preserving the submit-or-reject invariant.
    # #VERIFY: the except adds a hard-block Finding that routing sends to auto_reject.
    try:
        await _run_all_stages(
            report=report,
            blob=version_row.blob,
            settings=settings,
            review_provider=guarded_review,
        )
    except ValidationError:
        _logger.warning("moderation.invalid_blob", story_id=story_id)
        report.add(
            Finding(
                stage=0,
                source=Source.PIPELINE,
                category="invalid_story",
                verdict=Verdict.BLOCK,
                message="story blob failed schema validation",
            )
        )

    # Soft gate: one bounded auto-repair, then re-moderate once.
    if report.has_soft_flag and not report.has_hard_block:
        revised = await attempt_repair(
            blob=version_row.blob,
            report=report,
            generation_provider=generation_provider,
            pii=pii,
            max_tokens=_MAX_REPAIR_TOKENS,
        )
        if revised is not None:
            # Re-moderate into a separate report; only adopt it (and persist the
            # revised blob) if the repair is schema-valid. A malformed repair is
            # discarded so the original soft-flagged report drives the routing.
            repaired_report = ModerationReport(reviewer_independent=independent)
            try:
                await _run_all_stages(
                    report=repaired_report,
                    blob=revised,
                    settings=settings,
                    review_provider=guarded_review,
                )
            except ValidationError:
                # #ASSUME: data-integrity: attempt_repair guarantees only a JSON
                # object, not a schema-valid story; an invalid revision is dropped.
                # #VERIFY: report and version_row.blob are left unchanged here.
                _logger.warning("moderation.repair_invalid_blob", story_id=story_id)
            else:
                repaired_report.repaired = True
                report = repaired_report
                version_row.blob = revised

    version_row.moderation_report = report.to_dict()

    # #CRITICAL: security: guardian is the FINAL gate (ADR-005); this pipeline
    # calls ONLY submit (clean/repaired) or auto_reject (hard block). It MUST NEVER
    # call approve or publish directly.
    # #VERIFY: no code path in this module sets status="published".
    if report.has_hard_block:
        await service.auto_reject(session, storybook)
    else:
        await service.submit(session, storybook)


async def _run_all_stages(
    *,
    report: ModerationReport,
    blob: dict[str, object],
    settings: Settings,
    review_provider: ReviewProvider,
) -> None:
    """Run Stage 0 classifiers then the four LLM stages, appending to report.

    Args:
        report: The accumulating report; findings are added in place.
        blob: The story JSON blob to validate.
        settings: Application settings supplying classifier credentials.
        review_provider: The PII-guarded review provider for LLM stages.
    """
    # #ASSUME: data-integrity: blob was persisted as a valid Storybook JSON;
    # model_validate raises ValidationError if the schema was corrupted at rest.
    # #VERIFY: run_moderation_pipeline wraps both calls in try/except ValidationError
    # (initial -> hard-block + auto_reject; repair -> discard the revision).
    story = StoryModel.model_validate(blob)
    nodes = [(node.id, node.body) for node in story.nodes]

    # #CRITICAL: external-resource: classifier APIs are network calls that can fail;
    # the pipeline degrades gracefully if both keys are None (both classifiers skip).
    # #VERIFY: run_classifiers documents per-call try/except that logs and continues.
    # The classifier calls set per-request timeouts (_CLASSIFIER_TIMEOUT = 20 s);
    # the client-level timeout is a belt-and-suspenders backstop for connect+pool.
    async with httpx.AsyncClient(timeout=30.0) as client:
        for finding in await run_classifiers(
            nodes=nodes,
            openai_key=settings.openai_api_key,
            perspective_key=settings.perspective_api_key,
            client=client,
        ):
            report.add(finding)

    # Short-circuit: a Stage-0 bright-line block skips all LLM spend.
    if report.has_hard_block:
        return

    age_band = story.metadata.age_band.value
    for finding in await run_safety_stage(
        provider=review_provider,
        nodes=nodes,
        age_band=age_band,
        max_tokens=_MAX_REVIEW_TOKENS,
    ):
        report.add(finding)
    if report.has_hard_block:
        return

    for finding in await run_readability_stage(
        provider=review_provider,
        nodes=nodes,
        reading_target=story.metadata.reading_level.target,
        tolerance=story.metadata.reading_level.tolerance,
        max_tokens=_MAX_REVIEW_TOKENS,
    ):
        report.add(finding)
    for finding in await run_coherence_stage(
        provider=review_provider,
        nodes=nodes,
        max_tokens=_MAX_REVIEW_TOKENS,
    ):
        report.add(finding)
    for finding in await run_engagement_stage(
        provider=review_provider,
        nodes=nodes,
        max_tokens=_MAX_REVIEW_TOKENS,
    ):
        report.add(finding)
