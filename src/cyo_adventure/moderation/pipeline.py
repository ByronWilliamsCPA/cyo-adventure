"""The moderation pipeline: run stages, persist findings, drive the state machine.

Invoked from the generation worker after the draft rows are persisted and before
the request commit. Reads the persisted version's blob, runs Stage 0 then the LLM
stages, persists the aggregated report, and drives ``submit`` / ``auto_reject``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

import httpx
from pydantic import ValidationError
from sqlalchemy import select

from cyo_adventure.core.exceptions import ResourceNotFoundError
from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.events import Actor, EventType, record_event
from cyo_adventure.generation.guarded import PiiGuardedProvider
from cyo_adventure.generation.metered import MeteredProvider, ledger_of
from cyo_adventure.generation.pii import assert_prompt_pii_safe
from cyo_adventure.moderation.classifiers import run_classifiers
from cyo_adventure.moderation.leaf_diversity import run_leaf_diversity_check
from cyo_adventure.moderation.personalizable_slots import (
    PERSONALIZABLE_SLOTS_UNSET,
    PersonalizableSlotsArg,
    PersonalizableSlotsUnrecoverable,
    PersonalizableSlotsUnset,
    personalizable_slot_ids_for_story,
)
from cyo_adventure.moderation.prose_craft import findings_from_prose_craft
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
    run_safety_stage,
)
from cyo_adventure.moderation.synthesis import merge_findings
from cyo_adventure.publishing import service
from cyo_adventure.storybook.models import Storybook as StoryModel
from cyo_adventure.storybook.reinsertion import (
    build_manifest,
    manifest_carries_tokens,
)
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

# The personalizable-slot tri-state contract (the ``PERSONALIZABLE_SLOTS_UNSET``
# marker, its ``PersonalizableSlotsUnset`` type, the ``PersonalizableSlotsArg``
# override type, and the two resolvers) lives in
# :mod:`cyo_adventure.moderation.personalizable_slots` so cross-package
# consumers (``generation/import_story.py``, ``api/node_edit.py``) import a
# public name from a dedicated module instead of this module's internals.


#: Sentinel distinguishing "this provider declares no `resolved_provider`, so
#: it is not a cascade and its own name is authoritative" from "this cascade
#: declares one and its value is `None`, so no leg has answered yet". A plain
#: `None` default cannot express that difference, and conflating the two is
#: what grants a fresh cascade unconditional reviewer independence.
_NO_CASCADE: Final = object()


def _build_guarded_review(
    review_settings: Settings,
    *,
    generator_provider: str,
    generator_model: str | None,
    pii: PiiContext,
    generation_provider: GenerationProvider,
) -> tuple[PiiGuardedProvider, bool]:
    """Build the review provider, guard it, and bill it to the job's ledger.

    Args:
        review_settings: Review-backend settings, already resolved.
        generator_provider: The CONFIGURED generator backend name, used only
            when the resolved provider declares no label of its own.
        generator_model: The model that wrote the version under review.
        pii: PII context for the egress guard on every review prompt.
        generation_provider: The generation provider the caller passed in.
            Read for the ledger it may carry and for the backend it actually
            resolved to.

    Returns:
        The guarded (and, when the run is metered, metered) review provider,
        and whether the reviewer is independent of the generator.
    """
    # #CRITICAL: security: independence must be judged against the backend the
    # job ACTUALLY ran on, not the configured default. The worker can resolve a
    # per-job provider override before calling this pipeline, and when it does,
    # comparing the reviewer against `settings.generation_provider` asks about a
    # backend that never wrote the story. That misjudges in the dangerous
    # direction as readily as the safe one: an override onto the review backend
    # would be persisted as `reviewer_independent=True`, so a model would review
    # its own output and the report would attest that it had not.
    # A cascade adds a second way to get this wrong: FallbackProvider.name is a
    # label like "fallback[openrouter:haiku,openrouter:sonnet,modal]", which
    # equals no configured backend, so judging on it makes "different backend"
    # unconditionally true and grants tier-1 independence to every cascade run
    # whatever answered. Only the leg that answered may speak for a cascade.
    # #CRITICAL: security: the two cases below are told apart by the PRESENCE
    # of `resolved_provider`, never by its truthiness. A cascade that has not
    # answered reports `None`, and collapsing that to the provider's own `name`
    # (as `resolved or name` would) reinstates the composite label and the
    # unconditional independence it grants. This is reachable in production:
    # api/remoderate.py and generation/import_story.py both build a FRESH
    # cascade that has answered nothing at the moment this runs. An
    # unresolvable cascade therefore falls through to the CONFIGURED backend,
    # the same safe comparison a provider declaring no name already gets,
    # which fails closed when the reviewer shares that backend.
    # #VERIFY: tests/unit/test_review_metering.py::
    # test_independence_is_judged_against_the_resolved_generator_backend,
    # ::test_the_configured_backend_is_used_when_the_provider_declares_no_name,
    # ::test_a_cascade_is_judged_on_the_leg_that_answered,
    # ::test_an_unanswered_cascade_does_not_grant_independence,
    # ::test_a_metered_cascade_is_judged_on_the_leg_that_answered and
    # ::test_metering_does_not_invent_a_resolution_for_a_plain_provider.
    resolved: object = getattr(generation_provider, "resolved_provider", _NO_CASCADE)
    if resolved is _NO_CASCADE:
        # Not a cascade: this provider's own name IS the backend that ran.
        candidate: object = getattr(generation_provider, "name", None)
    else:
        # A cascade: the answering leg, or nothing. Never its own label.
        candidate = resolved
    effective_generator = (
        candidate if isinstance(candidate, str) and candidate else generator_provider
    )
    review_provider, independent = build_review_provider(
        review_settings,
        generator_provider=effective_generator,
        generator_model=generator_model,
    )
    # #CRITICAL: payment/financial: the review provider is built HERE rather
    # than passed in, so its calls escape the job's ledger entirely unless they
    # are metered on this path. Review is a large share of a job's calls
    # (safety stages plus any repair), and the omission would not read as a
    # gap: the persisted totals would look complete and simply be too small,
    # which is the one failure this subsystem exists to prevent. The ledger
    # comes from the generation provider the caller already passed, so review
    # spend bills to the same job.
    # #VERIFY: tests/unit/test_review_metering.py::
    # test_review_calls_are_billed_to_the_generation_jobs_ledger.
    job_ledger = ledger_of(generation_provider)
    metered: GenerationProvider = (
        review_provider
        if job_ledger is None
        else MeteredProvider(review_provider, ledger=job_ledger)
    )
    # #CRITICAL: security: every review prompt egresses story prose; the
    # reviewer MUST be PII-guarded exactly like generation before any stage
    # runs, and the guard stays OUTERMOST so a rejected prompt reaches neither
    # the meter nor the backend.
    # #VERIFY: stages receive the guarded provider, never the bare one.
    return PiiGuardedProvider(metered, forbidden=pii), independent


async def run_moderation_pipeline(
    *,
    session: AsyncSession,
    story_id: str,
    version: int,
    settings: Settings,
    generation_provider: GenerationProvider,
    pii: PiiContext,
    review_model_override: str | None = None,
    personalizable_slots: PersonalizableSlotsArg = PERSONALIZABLE_SLOTS_UNSET,
    allow_repair: bool = True,
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
        personalizable_slots: Task 6c override for the story's declared
            personalizable slot ids. Left at its default
            (:data:`PERSONALIZABLE_SLOTS_UNSET`) by every caller except the
            cyo-author resume path (``generation/import_story.py::
            resume_manual_fill``, via ``import_filled_story``'s own
            pass-through), which resolves this itself -- using the
            in-memory ``GenerationJob`` and its own correctly-resolved band
            (``_resolve_resume_band``'s brief-band fallback) -- BEFORE the
            job is linked to ``story_id`` in the database, closing the
            resume-path timing gap (I1) and bad-band-recovery divergence
            (I2) the whole-branch review found in the Task 6a backstop.
            When left at the default, this function resolves the slot set
            itself via :func:`personalizable_slot_ids_for_story`, exactly
            as it always has (dormant for every other caller). An explicit
            :data:`PERSONALIZABLE_SLOTS_UNRECOVERABLE` (as opposed to the
            default) is honored VERBATIM and still fails closed below: it
            means the caller itself already determined personalization was
            possible but the contract could not be recovered (M1).
        allow_repair: When False, skip the bounded auto-repair entirely and
            report on the story exactly as it stands. Every generation-path
            caller leaves this True (a pre-publish draft is repairable by
            definition). ``api/remoderate.py`` passes False because its
            subject is an already-PUBLISHED book: see the repair branch
            below for why that distinction is load-bearing.

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
    guarded_review, independent = _build_guarded_review(
        review_settings,
        generator_provider=settings.generation_provider,
        generator_model=version_row.model,
        pii=pii,
        generation_provider=generation_provider,
    )
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
    # #CRITICAL: security: a report produced by the mock reviewer ran no
    # real safety review at all, in EVERY environment. The escape hatch
    # (CYO_ADVENTURE_ALLOW_MOCK_REVIEW=1,
    # config._require_real_reviewer_outside_local) is what lets such a run
    # BOOT outside local; it has never been what triggers this stamp, and
    # reading it as the trigger is precisely the mistake that left the stamp
    # gated on `environment != "local"` (third block below). The trigger is
    # `review_provider == "mock"` and nothing else. Overriding
    # `reviewer_independent` here (build_review_provider always reports the
    # mock backend as independent) plus a structural advisory finding is what
    # makes such a report self-identifying forever (gap G1, design doc
    # section 2.4), even after it is persisted and the escape hatch is later
    # unset.
    # #CRITICAL: security: the stamp must survive the REPAIR path too. An
    # adopted repair replaces `report` wholesale with the fresh report built
    # in `_attempt_and_adopt_repair`, so stamping only this pre-repair report
    # would persist an unstamped report on every mock-moderated story that
    # repaired. `mock_reviewer` is therefore threaded into that
    # function, which re-applies the identical stamp via `_stamp_mock_reviewer`.
    # #VERIFY: tests/unit/test_moderation_pipeline.py::
    # test_mock_review_escape_hatch_stamps_report_as_not_independent (no
    # repair) and ::test_mock_review_stamp_survives_adopted_repair (adopted
    # repair; asserts the PERSISTED report keeps both halves of the stamp).
    # #CRITICAL: security: this must NOT be gated on `environment != "local"`.
    # It was, and `config._require_real_reviewer_outside_local` is gated on the
    # same predicate, so the two defenses shared one point of failure: both
    # `review_provider` and `environment` are read from the process
    # environment by the same Settings object, which declares no `env_file`
    # (config.py:218) and therefore reads nothing but exported variables. A
    # process started without them exported falls back to
    # `review_provider="mock"` (config.py's default) AND `environment="local"`
    # in the same instant, from the same absence. The guard then does not
    # raise, this stamp does not apply, and the persisted report claims an
    # independent reviewer over nodes the mock never judged. That is what put
    # twelve books at the review gate on 2026-07-21 with 2,916 fail-safe nodes
    # and `reviewer_independent: true` (docs/planning/safety/
    # moderation-review-current-state-2026-08-25.md section 6).
    # A mock review is not an independent review in local either, so the
    # stamp applies unconditionally. That is not a free change, and calling
    # the stamp "verdict-neutral" would only be half true: the ADVISORY
    # finding never gates, but the stamp's other half,
    # `reviewer_independent = False`, is a hard gate.
    # `moderation_report_unusable` returns True on that arm alone and
    # `publishing/service.py` then refuses the approval outright, with no
    # `override_reason` path (that argument gates only the later
    # severe-finding check). A story moderated locally with the mock is
    # therefore permanently unapprovable, which is the intended posture: it
    # was never reviewed. The surfaces that hit it are the local cyo-author
    # authoring loop and scripts/series_e2e_local.py's import-then-approve
    # path, both of which must now run a real reviewer to reach published.
    # #VERIFY: tests/unit/test_moderation_pipeline.py::
    # test_mock_review_stamps_report_as_not_independent_in_local and
    # ::test_mock_review_escape_hatch_stamps_report_as_not_independent.
    mock_reviewer = review_settings.review_provider == "mock"
    if mock_reviewer:
        _stamp_mock_reviewer(report)

    # #CRITICAL: security: universal at-rest sentinel-integrity backstop
    # (Task 6a). Before this check, Variant B ran ONLY inside
    # _repair_is_adoptable (the repair path), so a cleanly-moderating blob
    # (e.g. a cyo-author import that never soft-flags) got ZERO automated
    # sentinel checks. Resolve the story's personalizable-slot set ONCE,
    # here, against the ORIGINAL blob, before any staging/adoption decision;
    # REUSE this same resolution for the repair gate below rather than
    # re-resolving it (avoids a second DB/file lookup per moderation pass).
    # Fail closed on either an unrecoverable contract
    # (`PERSONALIZABLE_SLOTS_UNRECOVERABLE`) or a
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
    #
    # #CRITICAL: data-integrity: Task 6c. `personalizable_slots` starts as
    # `PERSONALIZABLE_SLOTS_UNSET` for every caller except the cyo-author
    # resume path (see this parameter's own docstring above); only THAT
    # branch below re-resolves it from the story id, exactly as before. A
    # caller-supplied value -- a real `frozenset` OR an explicit
    # `PERSONALIZABLE_SLOTS_UNRECOVERABLE` -- is never second-guessed or
    # re-resolved here.
    # #VERIFY: tests/unit/test_moderation_pipeline.py::
    # test_run_moderation_pipeline_honors_explicit_personalizable_slots,
    # ::test_run_moderation_pipeline_explicit_unrecoverable_fails_closed, and
    # ::test_run_moderation_pipeline_default_resolves_from_story (dormancy).
    if isinstance(personalizable_slots, PersonalizableSlotsUnset):
        personalizable_slots = await personalizable_slot_ids_for_story(
            session, story_id
        )
    # #CRITICAL: security: `None` is deliberately caught here even though it is
    # NOT a member of `PersonalizableSlotsArg`. It is the retired spelling of
    # this exact fail-closed state; `tests/` is type-checked by no gate in this
    # repo (pyproject's basedpyright `include = ["src"]`), so an untyped or
    # stale caller can still supply it; and an unexpected value arriving at a
    # security control must fail closed rather than be reinterpreted as a
    # recovered contract. Without this arm `None` satisfies NEITHER isinstance,
    # falls through to the `else` below, and is handed to
    # `check_sentinel_integrity_at_rest` in place of a resolved `frozenset`,
    # which reports ok=True on a sentinel-free blob: fail-OPEN, the story
    # submits clean with no entry-level check at all.
    # #VERIFY: tests/unit/test_moderation_pipeline.py::
    # test_run_moderation_pipeline_none_slots_fails_closed.
    if personalizable_slots is None or isinstance(
        personalizable_slots, PersonalizableSlotsUnrecoverable
    ):
        # Distinct event name from the blob-integrity violation logged below:
        # this is a CONTRACT-recovery failure (the personalizable-slot set could
        # not be resolved), not a sentinel violation in the story blob. Sharing
        # one event name made the two fail-closed paths indistinguishable in
        # logs.
        _logger.warning(
            "moderation.entry_contract_unrecoverable",
            story_id=story_id,
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
                # #ASSUME: security: the raw sentinel token is redacted from
                # the log line as defense-in-depth. node_id + kind already
                # locate and classify the violation; server-side the token
                # carries only a generic default, never resolved child data.
                # #VERIFY: keep sentinel tokens out of every log/response sink.
                violations=[
                    {"node_id": v.node_id, "kind": v.kind}
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
    # #ASSUME: data-integrity: the `PersonalizableSlotsUnrecoverable` check is,
    # in practice, always satisfied here: a fail-closed resolution already
    # added a BLOCK finding above, making `not report.has_hard_block` False.
    # The explicit check is kept anyway as a second, independent fail-closed
    # guard (belt-and-suspenders) and to narrow the type for
    # `_attempt_and_adopt_repair` without a bare `assert` (Bandit B101 in
    # `src/`). It is an `isinstance`, never a truthiness test: an EMPTY
    # frozenset is a legitimate, benign resolution that must still reach the
    # repair path, and `if not personalizable_slots` would send it away with
    # the unrecoverable one (see PersonalizableSlotsUnrecoverable's docstring).
    # #VERIFY: tests/unit/test_moderation_pipeline.py::
    # test_entry_contract_unrecoverable_routes_to_human_review confirms the
    # repair path is never entered on an unrecoverable contract.
    # #CRITICAL: security: `allow_repair=False` is the guard that keeps this
    # pipeline from rewriting an ALREADY-PUBLISHED book's prose.
    # `_attempt_and_adopt_repair` assigns `version_row.blob = revised`, and
    # adoption is gated only by deterministic checks, never by a human. On the
    # generation path that is correct (the draft has not been approved by
    # anyone yet, and a guardian still reviews the result). On a published
    # book it would silently alter text a guardian already approved and a
    # child may be reading offline, defeating ADR-005. The same rule is
    # enforced structurally elsewhere for the same reason: see
    # api/node_edit.py::_EDITABLE_STATUSES ("immutable once released,
    # ADR-005"), generation/series_link.py's `embed_into_approved_blob`, and
    # moderation/rescreen.py ("a re-screen tool must never silently rewrite
    # already-published, already-approved content").
    # #VERIFY: tests/unit/test_remoderate_unit.py::
    # test_published_blob_unchanged_when_repair_disallowed asserts the blob is
    # byte-identical after a soft-FLAG re-moderation through api/remoderate.py.
    if (
        allow_repair
        and report.has_soft_flag
        and not report.has_hard_block
        and not isinstance(personalizable_slots, PersonalizableSlotsUnrecoverable)
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
            mock_reviewer=mock_reviewer,
            personalizable_slots=personalizable_slots,
        )

    # Advisory prose-craft guard (UW-C313, UW-C328): deterministic, local, and
    # ADVISORY only, so unlike the ATG above it adds no repair targets and
    # cannot move routing; see moderation/prose_craft.py for why a FLAG would
    # be wrong here.
    # #CRITICAL: data-integrity: this runs AFTER the repair branch, not beside
    # the ATG. An adopted repair returns a FRESH ModerationReport that replaces
    # `report` wholesale and rewrites `version_row.blob`, so measuring earlier
    # would both DISCARD every advisory on exactly the books that repaired and
    # describe prose that is no longer stored. The same wholesale-replacement
    # hazard is what `mock_reviewer` is threaded into
    # `_attempt_and_adopt_repair` to survive. `_apply_prose_craft_findings`
    # early-returns on a hard block, which still holds here: after an adopted
    # repair the flag reflects the repaired report's own verdict.
    # #VERIFY: tests/unit/test_moderation_pipeline.py::
    # test_prose_craft_advisory_survives_an_adopted_repair and
    # ::test_prose_craft_measures_the_repaired_blob.
    _apply_prose_craft_findings(version_row=version_row, report=report)

    _persist_report(version_row, report)

    # #CRITICAL: security: guardian is the FINAL gate (ADR-005); this pipeline
    # calls ONLY submit (clean/repaired) or auto_reject (hard block). It MUST NEVER
    # call approve or publish directly.
    # #VERIFY: no code path in this module sets status="published".
    if report.has_hard_block:
        await service.auto_reject(session, storybook)
    else:
        await service.submit(session, storybook, actor=Actor.system())

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


def _persist_report(version_row: StorybookVersion, report: ModerationReport) -> None:
    """Persist the report's merged findings, never the raw unmerged report.

    Runs the deterministic merge stage (design doc 2.2) on a COPY used only
    for persistence; the caller's in-memory ``report`` keeps its raw,
    unmerged findings so gating flags (``has_hard_block``, ``has_soft_flag``)
    and the repair loop, which read ``report`` before and after this call,
    are unaffected.

    This is the pipeline's only write to ``moderation_report``, but NOT the
    repo's: ``api/node_edit.py::_merge_moderation_report`` rebuilds the
    stored payload after a node edit and is the second writer. That path
    deliberately does not re-run the merge (it splices fresh single-node
    findings into an already-merged report), so a reader must handle a
    payload where merged findings carrying ``node_ids`` sit beside fresh ones
    without it. Any third writer must be added to that list here.

    Args:
        version_row: The storybook version row whose ``moderation_report``
            JSONB column is written.
        report: The pipeline's accumulated (unmerged) report.
    """
    persisted_report = ModerationReport(
        findings=merge_findings(report.findings),
        repaired=report.repaired,
        reviewer_independent=report.reviewer_independent,
        nodes_reviewed=report.nodes_reviewed,
    )
    version_row.moderation_report = persisted_report.to_dict()


def _stamp_mock_reviewer(report: ModerationReport) -> None:
    """Mark ``report`` as produced by the mock reviewer, in any environment.

    The single definition of the gap-G1 stamp (design doc section 2.4), so
    every report the pipeline can persist carries an identical mark whether it
    came from the first moderation pass or from an adopted repair's fresh
    report. Both halves matter: ``reviewer_independent = False`` is what the
    dashboard and threshold flywheel read, and the structural ADVISORY finding
    is what a human reading the stored report sees. ADVISORY never gates, so
    stamping is verdict-neutral and safe to apply before the stages run.

    Args:
        report: The report to stamp, mutated in place.
    """
    report.reviewer_independent = False
    report.add(
        Finding(
            stage=0,
            source=Source.PIPELINE,
            category="pipeline",
            verdict=Verdict.ADVISORY,
            message="moderated with the mock reviewer; no real safety review ran",
            structural=True,
            concern="mock_reviewer_active",
        )
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
    mock_reviewer: bool,
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
        mock_reviewer: Whether the resolved review settings select the mock
            reviewer, in ANY environment. When True the repaired report is
            stamped with the same gap-G1 mark the caller applied to the
            pre-repair report, so an ADOPTED repair (which replaces the
            caller's report wholesale) cannot launder a mock-moderated story
            into a report that reads as reviewed.
        personalizable_slots: The story's declared personalizable slot ids,
            already resolved ONCE by the caller (:func:`run_moderation_pipeline`,
            Task 6a) via :func:`personalizable_slot_ids_for_story` for the
            entry-level sentinel-integrity backstop; reused here rather than
            re-resolved, so a moderation pass never does the GenerationJob/
            contract lookup twice. The caller only enters this function when
            that resolution landed on the ``frozenset`` arm, never on
            :data:`PERSONALIZABLE_SLOTS_UNRECOVERABLE` (see the caller's own
            fail-closed guard), so this parameter is never a placeholder guess.

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
    if mock_reviewer:
        _stamp_mock_reviewer(repaired_report)
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
    # #CRITICAL: data-integrity: the blob just changed under a flag derived
    # from the PREVIOUS blob. `personalization_eligible` is written once at
    # persist time (generation/persistence.py) and read verbatim by
    # api/library.py, so an adopted repair that drops the story's last
    # sentinel would otherwise leave the column advertising a personalization
    # affordance the blob can no longer honor. `_repair_is_adoptable` does not
    # close this: its sentinel check "cannot catch a DROPPED sentinel" (see
    # the module note above). Re-derive from the blob actually being stored.
    # `sentinel_manifest` is deliberately NOT refreshed here; that is the open
    # half of Task R3 recorded on the column itself in db/models.py, and
    # widening it is out of this change's scope.
    # #VERIFY: tests/unit/test_moderation_pipeline.py::
    # test_adopted_repair_clears_personalization_eligible_when_sentinels_lost.
    version_row.personalization_eligible = bool(
        personalizable_slots
    ) and manifest_carries_tokens(build_manifest(revised))
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


def _apply_prose_craft_findings(
    *,
    version_row: StorybookVersion,
    report: ModerationReport,
) -> None:
    """Append the prose-craft advisories to ``report``, if any.

    Skipped once a hard block has decided routing, for a different reason than
    the ATG's: these findings never gate, so their only value is being read by
    the human approver an auto-rejected book will never reach.

    Args:
        version_row: The persisted version under moderation, read for its blob.
        report: The accumulating report; findings are added in place.
    """
    if report.has_hard_block:
        return
    for finding in findings_from_prose_craft(version_row.blob):
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
            (see :func:`personalizable_slot_ids_for_story`), passed to
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
    # AL-325: a repair that returns a "<<FILL" directive has un-authored the
    # node it was asked to fix, which PL-27 catches only under this posture.
    gate_result = run_gate(revised, context="fill_result")
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
            # Redact the raw sentinel token (see the entry-integrity log
            # above for the rationale); node_id + kind suffice to diagnose.
            violations=[
                {"node_id": v.node_id, "kind": v.kind}
                for v in integrity_result.violations
            ],
        )
        return False
    return True


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
# durable event log payload; it MUST stay a str -> int mapping over a small
# CLOSED vocabulary and never include a finding's ``category``, ``message``,
# or ``node_id``, any of which could carry story-derived text. The vocabulary
# is the Verdict StrEnum's own values (block/flag/advisory/pass) plus the
# single literal key ``"structural"`` written below, which tallies a boolean
# field rather than naming a verdict. Any future key must likewise be a
# literal defined in this module, never a value read off a Finding.
# #VERIFY: values are plain ints; the only keys are ``Verdict(...).value`` and
# the literal ``"structural"``; no string field from Finding other than the
# enum's own ``.value`` is read here.
def _verdict_counts(report: ModerationReport) -> dict[str, int]:
    """Return a PII-free count of findings per verdict, plus a structural tally.

    Args:
        report: The report whose findings are tallied.

    Returns:
        A mapping of verdict value (for example ``"flag"``) to occurrence
        count, plus a ``"structural"`` key counting findings with
        ``Finding.structural is True`` (design doc section 2.5): a
        pipeline-condition fail-safe (reviewer unavailable, classifier
        outage, mock reviewer) rather than a genuine content judgment. The
        ``"structural"`` key is present only when its count is nonzero, the
        same convention every verdict key already follows, so a clean
        report's payload stays ``{}`` and existing exact-equality event
        assertions are unaffected.
    """
    counts: dict[str, int] = {}
    structural_count = 0
    for finding in report.findings:
        key = finding.verdict.value
        counts[key] = counts.get(key, 0) + 1
        if finding.structural:
            structural_count += 1
    if structural_count:
        counts["structural"] = structural_count
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
    # Efficiency (Task 6b, carried from the 6a review): a report that is
    # ALREADY hard-blocked when this function is entered (e.g. the
    # moderation-entry sentinel-integrity backstop, Task 6a, or a repeat
    # invocation on a second pass) has already decided auto_reject; nothing
    # below this point can change that verdict. Mirrors the
    # `if report.has_hard_block: return` short-circuit already used between
    # the LLM stages further down, but applied at entry so the Stage 0
    # classifier calls (OpenAI Moderation / Google Perspective, real network
    # egress) are never made for a verdict that is already fixed. Skips the
    # WHOLE function, not only the classifier loop, since schema validation
    # and the PII egress check below feed only the classifiers/LLM stages
    # this skips anyway. Behavior-preserving for the verdict: still
    # auto_reject either way. Dormant until a hard block can exist before
    # this call (i.e. once a personalizable contract is live and Task 6a's
    # backstop can fire).
    # #VERIFY: tests/unit/test_moderation_pipeline.py::
    # test_stage0_classifiers_skipped_when_already_hard_blocked_at_entry
    # asserts the classifier HTTP transport is never reached; the pre-existing
    # ::test_hard_block_routes_to_auto_reject proves Stage 0 still runs as
    # before when there is no pre-existing hard block.
    if report.has_hard_block:
        return

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

    # #CRITICAL: security: the classifier call below is a distinct egress path
    # from the LLM review stages (which are protected structurally by
    # PiiGuardedProvider via review_provider). Screen every node body here so
    # OpenAI Moderation gets the same guard every other external call in this
    # pipeline already has, instead of receiving raw generated prose
    # unconditionally.
    # #VERIFY: test_moderation_pipeline.py::test_classifier_call_blocked_on_pii_in_node_body
    # asserts run_classifiers is never reached when a node body matches.
    for _node_id, body in nodes:
        assert_prompt_pii_safe(body, forbidden=pii)

    # #CRITICAL: external-resource: the classifier API is a network call that can
    # fail; the pipeline degrades gracefully if the key is None (the classifier
    # skips). Google Perspective was retired as a Stage-0 signal source
    # (ratified sunset); OpenAI Moderation is the only classifier run_classifiers
    # calls now.
    # #VERIFY: run_classifiers documents per-call try/except that logs and continues.
    # The classifier calls set per-request timeouts (_CLASSIFIER_TIMEOUT = 20 s);
    # the client-level timeout is a belt-and-suspenders backstop for connect+pool.
    async with httpx.AsyncClient(timeout=30.0) as client:
        for finding in await run_classifiers(
            nodes=nodes,
            openai_key=settings.openai_api_key,
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
        batch_size=settings.review_batch_size,
    ):
        report.add(finding)
    if report.has_hard_block:
        return

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

    # #CRITICAL: data-integrity: nodes_reviewed is the denominator the persisted
    # "aggregate" block gives the PASS-count rollup (design doc 2.1), and it is
    # the ONLY coverage signal left once PASS rows stop being persisted. It is
    # therefore set here, past the last stage, rather than beside the node list:
    # every `return` above (the entry short-circuit, a Stage-0 bright-line block,
    # a Stage-1 block) leaves the review INCOMPLETE, and an early assignment
    # would persist full coverage for a story whose safety reviewer never ran.
    # A short-circuited pass keeps the 0 default, which reads correctly as "no
    # complete review coverage" and matches the empty pass_counts beside it.
    # #VERIFY: tests/unit/test_moderation_pipeline.py::
    # test_nodes_reviewed_zero_when_stage0_block_short_circuits and
    # ::test_nodes_reviewed_counts_every_node_on_a_complete_pass.
    report.nodes_reviewed = len(nodes)
