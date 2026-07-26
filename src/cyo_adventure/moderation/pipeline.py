"""The moderation pipeline: run stages, persist findings, drive the state machine.

Invoked from the generation worker after the draft rows are persisted and before
the request commit. Reads the persisted version's blob, runs Stage 0 then the LLM
stages, persists the aggregated report, and drives ``submit`` / ``auto_reject``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import httpx
from pydantic import ValidationError
from sqlalchemy import select

from cyo_adventure.core.exceptions import ResourceNotFoundError
from cyo_adventure.core.exceptions import ValidationError as CoreValidationError
from cyo_adventure.db.models import GenerationJob, Storybook, StorybookVersion
from cyo_adventure.events import Actor, EventType, record_event
from cyo_adventure.generation.authoring_metadata import (
    SKELETON_BAND_KEY,
    SKELETON_SLUG_KEY,
)
from cyo_adventure.generation.binding import load_contract_for, personalizable_slot_ids
from cyo_adventure.generation.guarded import PiiGuardedProvider
from cyo_adventure.generation.pii import assert_prompt_pii_safe
from cyo_adventure.generation.skeleton import load_skeleton
from cyo_adventure.generation.skeleton_match import resolve_skeleton_path
from cyo_adventure.moderation.classifiers import run_classifiers
from cyo_adventure.moderation.leaf_diversity import run_leaf_diversity_check
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
from cyo_adventure.storybook.sentinels import strip_sentinels
from cyo_adventure.utils.logging import get_logger
from cyo_adventure.validator.gate import run_gate
from cyo_adventure.validator.sentinel_integrity import check_sentinel_integrity_at_rest

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

    # #CRITICAL: security: universal at-rest sentinel-integrity backstop
    # (Task 6a). Before this check, Variant B ran ONLY inside
    # _repair_is_adoptable (the repair path), so a cleanly-moderating blob
    # (e.g. a cyo-author import that never soft-flags) got ZERO automated
    # sentinel checks. Resolve the story's personalizable-slot set ONCE,
    # here, against the ORIGINAL blob, before any staging/adoption decision;
    # REUSE this same resolution for the repair gate below rather than
    # re-resolving it (avoids a second DB/file lookup per moderation pass).
    # Fail closed on either an unrecoverable contract (`None`) or a
    # violation, using the SAME BLOCK-verdict Finding mechanism the
    # existing invalid-blob path (below) uses to force auto_reject: never
    # auto-adopt or auto-publish a blob whose sentinel content cannot be
    # proven safe. Variant B cannot catch a DROPPED sentinel: this is a
    # forged/unknown/malformed/in-label/in-title backstop, not a full check.
    # A dropped sentinel on the cyo-author import/resume path is instead
    # caught pre-persist by the Variant A reorder in
    # generation/import_story.py::resume_manual_fill (Task 6b), which
    # compares the pre-fill bound reference against the filled blob before
    # anything is persisted; that closes the gap this backstop cannot.
    # #VERIFY: tests/unit/test_moderation_pipeline.py::
    # test_entry_forged_sentinel_in_clean_blob_routes_to_human_review,
    # ::test_entry_contract_unrecoverable_routes_to_human_review, and
    # ::test_clean_story_routes_to_submit (dormancy: a sentinel-free blob
    # with no GenerationJob on record, `_load`'s default, adds no finding).
    personalizable_slots = await _personalizable_slot_ids_for_story(session, story_id)
    if personalizable_slots is None:
        _logger.warning(
            "moderation.entry_sentinel_integrity_violation",
            story_id=story_id,
            reason="contract_unrecoverable",
        )
        report.add(
            Finding(
                stage=0,
                source=Source.PIPELINE,
                category="sentinel_integrity_violation",
                verdict=Verdict.BLOCK,
                message=(
                    "personalizable-slot contract could not be recovered; "
                    "failing closed"
                ),
            )
        )
    else:
        entry_integrity = check_sentinel_integrity_at_rest(
            version_row.blob, personalizable_slots
        )
        if not entry_integrity.ok:
            _logger.warning(
                "moderation.entry_sentinel_integrity_violation",
                story_id=story_id,
                reason="violations_found",
                violations=[
                    {"node_id": v.node_id, "kind": v.kind, "token": v.token}
                    for v in entry_integrity.violations
                ],
            )
            report.add(
                Finding(
                    stage=0,
                    source=Source.PIPELINE,
                    category="sentinel_integrity_violation",
                    verdict=Verdict.BLOCK,
                    message="sentinel integrity violated at moderation entry",
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
            pii=pii,
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

    # Advisory leaf-diversity guard (WS-1): deterministic, local, fail-open.
    # Runs BEFORE the soft gate so an ATG FAIL's per-node FLAGs ride the same
    # single bounded repair as any stage flag; skipped when a hard block has
    # already decided routing (has_soft_flag would ignore the FLAGs anyway).
    await _apply_leaf_diversity_findings(
        session=session, storybook=storybook, version_row=version_row, report=report
    )

    # Soft gate: one bounded auto-repair, then re-moderate once.
    # #ASSUME: data-integrity: `personalizable_slots is not None` is, in
    # practice, always true here: a `None` resolution already added a
    # BLOCK finding above, making `not report.has_hard_block` False. The
    # explicit check is kept anyway as a second, independent fail-closed
    # guard (belt-and-suspenders) and to narrow the type for
    # `_attempt_and_adopt_repair` without a bare `assert` (Bandit B101 in
    # `src/`).
    # #VERIFY: tests/unit/test_moderation_pipeline.py::
    # test_entry_contract_unrecoverable_routes_to_human_review confirms the
    # repair path is never entered when personalizable_slots is None.
    if (
        report.has_soft_flag
        and not report.has_hard_block
        and personalizable_slots is not None
    ):
        report = await _attempt_and_adopt_repair(
            session=session,
            story_id=story_id,
            version=version,
            version_row=version_row,
            report=report,
            generation_provider=generation_provider,
            settings=settings,
            guarded_review=guarded_review,
            pii=pii,
            independent=independent,
            personalizable_slots=personalizable_slots,
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


async def _attempt_and_adopt_repair(
    *,
    session: AsyncSession,
    story_id: str,
    version: int,
    version_row: StorybookVersion,
    report: ModerationReport,
    generation_provider: GenerationProvider,
    settings: Settings,
    guarded_review: ReviewProvider,
    pii: PiiContext,
    independent: bool,
    personalizable_slots: frozenset[str],
) -> ModerationReport:
    """Attempt one bounded auto-repair and adopt it if it re-passes moderation.

    Extracted from :func:`run_moderation_pipeline` (S3776): isolates the
    nested repair-attempt / re-moderate / adopt-if-valid branch, the
    function's deepest nesting, behind one call.

    Args:
        session: The request session (caller owns the transaction).
        story_id: The persisted storybook id.
        version: The persisted version number.
        version_row: The version row; ``blob`` is updated in place on adoption.
        report: The original (soft-flagged) report.
        generation_provider: Provider used for the bounded auto-repair re-prompt.
        settings: Application settings (review provider and classifier keys).
        guarded_review: The PII-guarded review provider for re-moderation.
        pii: PII context for the egress guard on repair and review prompts.
        independent: Whether the review backend is independent of the generator.
        personalizable_slots: The story's declared personalizable slot ids,
            already resolved ONCE by the caller (:func:`run_moderation_pipeline`,
            Task 6a) via :func:`_personalizable_slot_ids_for_story` for the
            entry-level sentinel-integrity backstop; reused here rather than
            re-resolved, so a moderation pass never does the GenerationJob/
            contract lookup twice. The caller only enters this function when
            that resolution was non-``None`` (see the caller's own fail-closed
            guard), so this parameter is never a placeholder guess.

    Returns:
        ModerationReport: ``report`` unchanged when no repair was produced,
            the repair was invalid, or the repair was not adoptable; a new
            report (``repaired = True``) when adopted, in which case
            ``version_row.blob`` is updated in place and a
            ``REPAIR_APPLIED`` event is recorded.
    """
    revised = await attempt_repair(
        blob=version_row.blob,
        report=report,
        generation_provider=generation_provider,
        pii=pii,
        max_tokens=_MAX_REPAIR_TOKENS,
    )
    if revised is None:
        return report

    # Re-moderate into a separate report; only adopt it (and persist the
    # revised blob) if the repair is schema-valid AND passes the deterministic
    # validation gate. A malformed or gate-failing repair is discarded so the
    # original soft-flagged report drives routing.
    repaired_report = ModerationReport(reviewer_independent=independent)
    try:
        await _run_all_stages(
            report=repaired_report,
            blob=revised,
            settings=settings,
            review_provider=guarded_review,
            pii=pii,
        )
    except ValidationError:
        # #ASSUME: data-integrity: attempt_repair guarantees only a JSON
        # object, not a schema-valid story; an invalid revision is dropped.
        # #VERIFY: report and version_row.blob are left unchanged here.
        _logger.warning("moderation.repair_invalid_blob", story_id=story_id)
        return report

    # A repair is adopted only if it re-proves its structure on the
    # deterministic gate AND preserves the story's identity; both checks (and
    # their rejection logging) live in _repair_is_adoptable. A rejected repair
    # is discarded exactly like a schema-invalid one: report and
    # version_row.blob stay at their pre-repair values, so routing falls
    # through to the pre-repair report's own verdict. Never silently accepts a
    # broken or swapped repair, never auto-publishes.
    if not _repair_is_adoptable(
        revised=revised,
        original=version_row.blob,
        story_id=story_id,
        personalizable_slot_ids=personalizable_slots,
    ):
        return report

    repaired_report.repaired = True
    version_row.blob = revised
    # #ASSUME: data-integrity: the event log must record a repair the moment
    # the revised blob is adopted, before moderation_report is overwritten by
    # the caller, so repair_applied always precedes moderation_completed in
    # occurred_at order for this version.
    # #VERIFY: tests/integration/test_pipeline_event_instrumentation.py::
    # test_repaired_moderation_writes_repair_applied_then_completed asserts
    # exactly one repair_applied row when repair occurs.
    await record_event(
        session,
        Actor.system(),
        entity_type="storybook_version",
        entity_id=f"{story_id}:{version}",
        event_type=EventType.REPAIR_APPLIED,
        payload={"stage": "moderation"},
    )
    return repaired_report


async def _apply_leaf_diversity_findings(
    *,
    session: AsyncSession,
    storybook: Storybook,
    version_row: StorybookVersion,
    report: ModerationReport,
) -> None:
    """Append the leaf-diversity guard's findings to ``report``, if any.

    Skipped entirely when a hard block has already decided routing: the
    guard is advisory and ``has_soft_flag`` would ignore its FLAGs anyway,
    so running it would spend two DB reads for no observable effect.

    Args:
        session: The pipeline's own open async session.
        storybook: The db row under moderation.
        version_row: The persisted version under moderation.
        report: The accumulating report; findings are added in place.
    """
    if report.has_hard_block:
        return
    for finding in await run_leaf_diversity_check(
        session=session, storybook=storybook, version_row=version_row
    ):
        report.add(finding)


def _tier_of(blob: dict[str, object]) -> object:
    """Return a blob's declared tier, or ``None`` if absent/malformed."""
    metadata = blob.get("metadata")
    if not isinstance(metadata, dict):
        return None
    return cast("dict[str, object]", metadata).get("tier")


def _repair_preserves_identity(
    original: dict[str, object], revised: dict[str, object]
) -> bool:
    """Return ``True`` only if the repaired blob is the same story, revised.

    A soft-gate repair is contracted to revise prose while preserving the exact
    node ids, choices, and branching structure, so the revised blob must keep the
    original's identity: same story ``id``, same ``metadata.tier``, and the same
    node count. This is a provider-agnostic backstop against a repair that
    returns a schema-valid but UNRELATED story (e.g. a mock/stub generator whose
    canned story passes the gate) silently replacing the imported content. Any of
    the three mismatching is sufficient to reject the swap.

    Args:
        original: The pre-repair blob (the content being protected).
        revised: The candidate repaired blob returned by the generator.

    Returns:
        ``True`` when id, tier, and node count all match; ``False`` otherwise.
    """
    if original.get("id") != revised.get("id"):
        return False
    if _tier_of(original) != _tier_of(revised):
        return False
    original_nodes = original.get("nodes")
    revised_nodes = revised.get("nodes")
    if not isinstance(original_nodes, list) or not isinstance(revised_nodes, list):
        return False
    return len(cast("list[object]", original_nodes)) == len(
        cast("list[object]", revised_nodes)
    )


def _repair_is_adoptable(
    *,
    revised: dict[str, object],
    original: dict[str, object],
    story_id: str,
    personalizable_slot_ids: frozenset[str],
) -> bool:
    """Return ``True`` only if a repaired blob may replace the pre-repair one.

    Three provider-agnostic gates, any one failing rejects the swap:

    1. **Structure re-proven.** The repair prompt asks the generator to preserve
       node ids, choices, and branching structure while revising prose, but
       nothing enforces that promise, and a clean re-moderation says nothing about
       topology, forbidden endings, or the L1-7 budget. So the revised blob must
       pass the deterministic validation gate here, the same gate the original
       draft passed, not merely be trusted (owner ruling 2026-07-16).
    2. **Identity preserved.** A repair revises prose only; it must not swap the
       story's identity. A generation provider (notably an all-mock local setup,
       whose stub story is schema-valid and gate-clean) can return an UNRELATED
       story that would then wholesale-replace the imported blob. That silent swap
       is the exact unreachable-version hazard import_story.py warns about
       (storybook.id no longer matching version.blob.id) and breaks series
       approval (SR-6) when a Tier-1 stub lands in a carries_state chain.
    3. **Sentinel integrity re-proven (ADR-023 plan 3.3).** The repair prompt
       (``moderation/repair.py``'s ``_REPAIR_SYSTEM``) asks the generator to
       preserve any ``{~NAME:Word~}`` sentinel verbatim, but nothing enforces
       that promise either. A repair that drops, mutates, migrates, forges, or
       relocates a sentinel into a choice label must be rejected exactly like a
       gate failure: a human already approved the pre-repair sentinel as
       static, and a repair pass must never silently alter it.

    Rejection is logged and returns ``False``; the caller then keeps the
    pre-repair report and blob, routing to the human guardian intact.

    Args:
        revised: The candidate repaired blob.
        original: The pre-repair blob being protected.
        story_id: The story id, for structured rejection logging.
        personalizable_slot_ids: The story's declared personalizable slot ids
            (see :func:`_personalizable_slot_ids_for_story`), passed to
            :func:`~cyo_adventure.validator.sentinel_integrity.check_sentinel_integrity_at_rest`.

    Returns:
        ``True`` when the revised blob passes the gate, preserves identity,
        and preserves sentinel integrity.

    Notes:
        tests/unit/test_moderation_pipeline.py::
        test_repair_failing_gate_is_discarded_and_routes_to_human_review,
        ::test_repair_identity_mismatch_is_discarded,
        ::test_repair_passing_gate_is_adopted, and
        ::test_repair_forged_sentinel_is_discarded_and_routes_to_human_review
        assert all four branches.
    """
    gate_result = run_gate(revised)
    if gate_result.blocked:
        _logger.warning(
            "moderation.repair_failed_gate",
            story_id=story_id,
            rule_ids=[f.rule_id for f in gate_result.report.errors],
        )
        return False
    if not _repair_preserves_identity(original, revised):
        _logger.warning("moderation.repair_identity_mismatch", story_id=story_id)
        return False
    # #CRITICAL: security: a repair pass must not introduce or relocate a
    # sentinel a human approved as static.
    # #VERIFY: check_sentinel_integrity_at_rest fail-closed here, mirroring
    # the fail-closed posture Task 4a wired into
    # generation/worker.py::_run_skeleton_fill for the fresh-fill path.
    integrity_result = check_sentinel_integrity_at_rest(
        revised, personalizable_slot_ids
    )
    if not integrity_result.ok:
        _logger.warning(
            "moderation.repair_failed_sentinel_integrity",
            story_id=story_id,
            violations=[
                {"node_id": v.node_id, "kind": v.kind, "token": v.token}
                for v in integrity_result.violations
            ],
        )
        return False
    return True


async def _personalizable_slot_ids_for_story(
    session: AsyncSession, story_id: str
) -> frozenset[str] | None:
    """Resolve a story's declared personalizable slot ids for the repair re-check.

    ``StorybookVersion`` carries ``skeleton_slug`` but no band, so the story's
    matched skeleton is recovered via its ``GenerationJob`` row, mirroring the
    same provenance chain :func:`~cyo_adventure.generation.worker._run_skeleton_fill`
    and :mod:`cyo_adventure.generation.import_story` already use.
    ``GenerationJob.storybook_id`` is not a FK (see that model's docstring);
    this uses the same degrade-on-missing pattern already established by
    :mod:`cyo_adventure.story_requests.anchoring` and
    :mod:`cyo_adventure.covers.service` (oldest job first, ``None`` on no match).

    Args:
        session: The pipeline's own open async session.
        story_id: The persisted storybook id under moderation.

    Returns:
        frozenset[str] | None: The declared personalizable slot ids. An EMPTY
            frozenset is returned (not a guess) whenever no personalizable
            slot could legitimately exist for this story: no ``GenerationJob``
            on record, a ``fresh_generation`` job (no ``skeleton_slug``), or a
            legacy skeleton with no theme-contract sidecar
            (:func:`~cyo_adventure.generation.binding.load_contract_for`
            returns ``None``). ``None`` is returned only when the job DOES
            carry a ``skeleton_slug`` (so a contract may genuinely declare
            personalizable slots) but the contract cannot be recovered (a
            missing ``skeleton_band``, or the skeleton/contract sidecar
            failing to load): the caller must fail closed rather than risk
            treating a real sentinel as forged with a guessed empty set.
    """
    job = (
        await session.execute(
            select(GenerationJob)
            .where(GenerationJob.storybook_id == story_id)
            .order_by(GenerationJob.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if job is None:
        return frozenset()
    authoring = (
        job.authoring_metadata if isinstance(job.authoring_metadata, dict) else {}
    )
    slug = authoring.get(SKELETON_SLUG_KEY)
    if not isinstance(slug, str):
        return frozenset()
    band = authoring.get(SKELETON_BAND_KEY)
    if not isinstance(band, str):
        _logger.warning(
            "moderation.repair_contract_band_missing", story_id=story_id, slug=slug
        )
        return None
    try:
        skeleton_path = resolve_skeleton_path(band, slug)
        skeleton = load_skeleton(skeleton_path)
        contract = load_contract_for(skeleton_path, skeleton)
    # #CRITICAL: external-resources: load_skeleton (generation/skeleton.py)
    # does json.loads(path.read_text(...)), which raises a raw
    # FileNotFoundError/OSError/JSONDecodeError (a ValueError subclass), NOT
    # a CoreValidationError, when the skeleton file a stale
    # GenerationJob.authoring_metadata points at has since moved or been
    # corrupted. Broadened here to mirror
    # generation/import_story.py::_load_resume_skeleton's handling of this
    # same resolve_skeleton_path -> load_skeleton chain, so a missing/corrupt
    # sidecar fails this function closed (None) instead of crashing the
    # entire moderation pass.
    # #VERIFY: test_repair_contract_file_missing_is_discarded_and_routes_to_human_review.
    except (FileNotFoundError, OSError, ValueError, CoreValidationError) as exc:
        _logger.warning(
            "moderation.repair_contract_load_failed",
            story_id=story_id,
            slug=slug,
            band=band,
            error=str(exc)[:500],
        )
        return None
    if contract is None:
        return frozenset()
    return personalizable_slot_ids(contract)


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
    pii: PiiContext,
) -> None:
    """Run Stage 0 classifiers then the four LLM stages, appending to report.

    Args:
        report: The accumulating report; findings are added in place.
        blob: The story JSON blob to validate.
        settings: Application settings supplying classifier credentials.
        review_provider: The PII-guarded review provider for LLM stages.
        pii: PII context for the egress guard on classifier inputs. The LLM
            review stages get this protection structurally via
            ``review_provider`` already being a ``PiiGuardedProvider``; the
            classifier calls below are a separate egress path (OpenAI
            Moderation, Google Perspective) that needs its own explicit check.

    Raises:
        cyo_adventure.core.exceptions.ValidationError: If a node body contains
            a forbidden real-child identifier or PII-shaped content. Not
            caught here; propagates like a ``guarded_review`` PII trip does,
            so the caller's job-failure/retry handling applies uniformly.
    """
    # #ASSUME: data-integrity: blob was persisted as a valid Storybook JSON;
    # model_validate raises ValidationError if the schema was corrupted at rest.
    # #VERIFY: run_moderation_pipeline wraps both calls in try/except ValidationError
    # (initial -> hard-block + auto_reject; repair -> discard the revision).
    story = StoryModel.model_validate(blob)
    # #CRITICAL: data-integrity: strip any personalization sentinel from the
    # text fed to the classifiers and LLM review stages below (Task 6a),
    # mirroring moderation/rescreen.py's own strip. Without this, the FIRST
    # moderation pass would score sentinel-noisy text (`{~SLOTID:Value~}`
    # literally present in the prompt) while a later rescreen of the same
    # published content scores stripped text, the exact comparability break
    # rescreen's strip exists to prevent. This copy is used ONLY for the
    # classifier/review calls below; `blob` (and thus the persisted
    # `version_row.blob` the caller holds) is never touched here.
    # #VERIFY: tests/unit/test_moderation_pipeline.py::
    # test_classifier_and_review_stage_receive_stripped_sentinel_text asserts
    # no `{~` reaches either the classifier HTTP body or the review prompts;
    # dormancy (sentinel-free text) is covered by every other pre-existing
    # test in this module, which are all unmodified by this change.
    nodes = [(node.id, strip_sentinels(node.body)) for node in story.nodes]

    # #CRITICAL: security: the classifier calls below are a distinct egress path
    # from the LLM review stages (which are protected structurally by
    # PiiGuardedProvider via review_provider). Screen every node body here so
    # OpenAI Moderation and Google Perspective get the same guard every other
    # external call in this pipeline already has, instead of receiving raw
    # generated prose unconditionally.
    # #VERIFY: test_moderation_pipeline.py::test_classifier_call_blocked_on_pii_in_node_body
    # asserts run_classifiers is never reached when a node body matches.
    for _node_id, body in nodes:
        assert_prompt_pii_safe(body, forbidden=pii)

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
