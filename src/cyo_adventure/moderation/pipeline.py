"""The moderation pipeline: run stages, persist findings, drive the state machine.

Invoked from the generation worker after the draft rows are persisted and before
the request commit. Reads the persisted version's blob, runs Stage 0 then the LLM
stages, persists the aggregated report, and drives ``submit`` / ``auto_reject``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
from pydantic import ValidationError
from sqlalchemy import select

from cyo_adventure.core.exceptions import ResourceNotFoundError
from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.events import Actor, EventType, record_event
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
    resolve_review_settings,
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
from cyo_adventure.validator.gate import run_gate

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
    review_model_override: str | None = None,
) -> None:
    """Screen a persisted draft story and drive it to in_review or needs_revision.

    Args:
        session: The request session (caller owns the transaction).
        story_id: The persisted storybook id.
        version: The persisted version number.
        settings: Application settings (review provider and classifier keys).
        generation_provider: Provider used for the bounded auto-repair re-prompt.
        pii: PII context for the egress guard on review and repair prompts.
        review_model_override: Optional admin-chosen override for the review
            model (see story_requests/authoring_plan.py::AuthoringPlanRequest's
            review_stage2_model). None uses the configured settings model.

    Raises:
        ResourceNotFoundError: when the story or version row is missing.
    """
    # #CRITICAL: concurrency: this worker path drives the same submit/auto_reject
    # transitions that api/approval.py's admin path drives (publishing/service.py),
    # so it must load the storybook under the same SELECT ... FOR UPDATE lock.
    # Without it, a worker re-moderating a story and an admin sending it back (or
    # another worker run) could both read a stale in-memory status, both pass
    # assert_transition, and the last writer would silently clobber the other's
    # transition, the same #129 race api/approval.py::_load_admin_story closed
    # for the admin path.
    # #VERIFY: SELECT ... FOR UPDATE on Postgres;
    # tests/unit/test_moderation_pipeline.py::test_pipeline_locks_storybook_row_for_update
    # asserts the lock clause is present.
    # #CRITICAL: data-integrity: the rows must exist (just persisted as draft) or
    # the state-machine transition has nothing to act on.
    # #VERIFY: both loads are checked for None.
    stmt = select(Storybook).where(Storybook.id == story_id).with_for_update()
    storybook = (await session.execute(stmt)).scalar_one_or_none()
    version_row = await session.get(StorybookVersion, (story_id, version))
    if storybook is None or version_row is None:
        msg = f"storybook '{story_id}' v{version} not found for moderation"
        raise ResourceNotFoundError(msg)

    report = ModerationReport()
    review_settings = resolve_review_settings(settings, review_model_override)
    review_provider, independent = build_review_provider(
        review_settings,
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
    # NB: only ValidationError is caught here. A review-backend outage (ProviderError)
    # or mock exhaustion (BusinessLogicError) propagates INTENTIONALLY to the worker,
    # which rolls back the unreviewed persist and records the job failed for RQ retry,
    # rather than submitting a partially-reviewed story. The "Stage 1 fail-safe -> FLAG"
    # invariant covers a garbled/unknown verdict in a *returned* body, not an outage.
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
            # revised blob) if the repair is schema-valid AND passes the
            # deterministic validation gate. A malformed or gate-failing repair
            # is discarded so the original soft-flagged report drives routing.
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
                # #CRITICAL: data-integrity: the repair prompt asks the generator
                # to "preserve node ids, choices, and branching structure" while
                # revising prose, but nothing enforces that promise; a clean
                # re-moderation pass says nothing about topology, forbidden
                # endings, or the L1-7 node/word budget. The repaired blob's
                # structure must be re-proven by the deterministic gate at this
                # seam (the point it would replace version_row.blob), the same
                # gate the original draft passed before it ever reached
                # moderation, not just trusted because re-moderation was clean.
                # #VERIFY: a blocked gate here is treated exactly like a
                # schema-invalid revision: the revised blob is discarded and
                # ``report``/``version_row.blob`` stay at their pre-repair
                # values, so routing below falls through to the pre-repair
                # report's own verdict (submit if soft-flagged, auto_reject if
                # the pre-repair report already hard-blocked). This never
                # silently accepts a structurally-broken repair and never
                # auto-publishes.
                # tests/unit/test_moderation_pipeline.py::
                # test_repair_failing_gate_is_discarded_and_routes_to_human_review
                # and ::test_repair_passing_gate_is_adopted assert both branches.
                gate_result = run_gate(revised)
                if gate_result.blocked:
                    _logger.warning(
                        "moderation.repair_failed_gate",
                        story_id=story_id,
                        rule_ids=[f.rule_id for f in gate_result.report.errors],
                    )
                else:
                    repaired_report.repaired = True
                    report = repaired_report
                    version_row.blob = revised
                    # #ASSUME: data-integrity: the event log must record a repair
                    # the moment the revised blob is adopted, before
                    # moderation_report is overwritten below, so repair_applied
                    # always precedes moderation_completed in occurred_at order
                    # for this version.
                    # #VERIFY: tests/integration/test_pipeline_event_instrumentation.py::
                    # test_repaired_moderation_writes_repair_applied_then_completed
                    # asserts exactly one repair_applied row when repair occurs.
                    await record_event(
                        session,
                        Actor.system(),
                        entity_type="storybook_version",
                        entity_id=f"{story_id}:{version}",
                        event_type=EventType.REPAIR_APPLIED,
                        payload={"stage": "moderation"},
                    )

    version_row.moderation_report = report.to_dict()

    # #CRITICAL: security: guardian is the FINAL gate (ADR-005); this pipeline
    # calls ONLY submit (clean/repaired) or auto_reject (hard block). It MUST NEVER
    # call approve or publish directly.
    # #VERIFY: no code path in this module sets status="published".
    if report.has_hard_block:
        await service.auto_reject(session, storybook)
    else:
        await service.submit(session, storybook)

    # #CRITICAL: data-integrity: this is the durable audit-trail record of the
    # moderation outcome (spec D3); the payload is restricted to enum verdicts,
    # a bool, and integer counts by record_event's allowlist, never finding
    # messages or story prose, so the append-only log cannot leak PII.
    # #VERIFY: tests/integration/test_pipeline_event_instrumentation.py::
    # test_clean_moderation_writes_moderation_completed and
    # ::test_repaired_moderation_writes_repair_applied_then_completed assert a
    # single moderation_completed row with the resulting to_state and a
    # PII-free counts payload.
    await record_event(
        session,
        Actor.system(),
        entity_type="storybook_version",
        entity_id=f"{story_id}:{version}",
        event_type=EventType.MODERATION_COMPLETED,
        to_state=storybook.status,
        payload={
            "overall_verdict": _overall_verdict(report),
            "repaired": report.repaired,
            "counts": _verdict_counts(report),
        },
    )


def _overall_verdict(report: ModerationReport) -> str:
    """Return the report's single gating verdict for the event payload.

    Derived from the report's own gating properties (``has_hard_block`` /
    ``has_soft_flag``), not a stored field: ``ModerationReport`` has no
    ``overall_verdict`` attribute of its own, only per-finding verdicts.

    Args:
        report: The final report driving the submit/auto_reject routing.

    Returns:
        ``"block"`` when any finding hard-blocks, ``"flag"`` when any finding
        soft-flags (and none blocks), otherwise ``"pass"``.
    """
    if report.has_hard_block:
        return Verdict.BLOCK.value
    if report.has_soft_flag:
        return Verdict.FLAG.value
    return Verdict.PASS.value


# #CRITICAL: security: _verdict_counts is the only aggregate that reaches the
# durable event log payload; it MUST stay a verdict-name -> int mapping (a
# small closed vocabulary: block/flag/advisory/pass) and never include a
# finding's ``category``, ``message``, or ``node_id``, any of which could
# carry story-derived text.
# #VERIFY: values are plain ints from a fixed StrEnum key set below; no string
# field from Finding other than the enum's own ``.value`` is read here.
def _verdict_counts(report: ModerationReport) -> dict[str, int]:
    """Return a PII-free count of findings per verdict.

    Args:
        report: The report whose findings are tallied.

    Returns:
        A mapping of verdict value (for example ``"flag"``) to occurrence count.
    """
    counts: dict[str, int] = {}
    for finding in report.findings:
        key = finding.verdict.value
        counts[key] = counts.get(key, 0) + 1
    return counts


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
            # Deployed tiers flag an unconfigured classifier as degraded so the
            # reviewer sees the net was off; local/dev skip silently.
            require_classifiers=settings.environment != "local",
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
