"""Async generation worker: loads a job from the DB and runs the pipeline.

This module contains two entry points:

* :func:`run_generation_job` -- the async core logic, directly testable
  without Redis or RQ by injecting a provider and session factory.
* :func:`run_generation_job_sync` -- a thin synchronous wrapper that
  ``asyncio.run`` dispatches to the async core; this is what RQ calls.

Session ownership
-----------------
The worker opens its own :class:`~sqlalchemy.ext.asyncio.AsyncSession` and
commits explicitly. It does NOT share the request unit-of-work. This is
intentional: background jobs have a different transaction boundary than API
requests. The RAD marker below captures this contract.

PII guard placement
-------------------
:func:`~cyo_adventure.generation.pii.assert_prompt_pii_safe` runs inside
:func:`~cyo_adventure.generation.orchestrator.generate_story` before every
provider call. No PII leaves this process before the guard fires.
"""

from __future__ import annotations

import asyncio
import dataclasses
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from cyo_adventure.core.config import settings as _default_settings
from cyo_adventure.core.database import get_session
from cyo_adventure.core.exceptions import ResourceNotFoundError
from cyo_adventure.db.models import (
    ChildProfile,
    Concept,
    GenerationJob,
)
from cyo_adventure.generation.concept import ConceptBrief
from cyo_adventure.generation.fidelity_gate import run_stage1_gate
from cyo_adventure.generation.orchestrator import fill_skeleton, generate_story
from cyo_adventure.generation.persistence import StorybookParams, persist_storybook
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import build_provider
from cyo_adventure.generation.skeleton import load_skeleton
from cyo_adventure.middleware.correlation import (
    generate_correlation_id,
    set_correlation_id,
)
from cyo_adventure.moderation import run_moderation_pipeline
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.generation.orchestrator import GenerationOutcome
    from cyo_adventure.generation.provider import GenerationProvider

__all__ = [
    "run_generation_job",
    "run_generation_job_sync",
]

# Prompt version label stamped on every StorybookVersion row produced by this
# worker. Bump when prompt templates change in a way that affects output shape.
_PROMPT_VERSION = "v1"

# Each generation job produces a fresh Storybook, so its sole version is 1.
# Re-running generation creates a new job and a new Storybook id, not a new
# version under an existing id.
_FIRST_VERSION = 1

# Fallback model label for a provider that exposes no real model identifier
# (the in-phase mock). Phase 2b providers carry their own model name.
_MOCK_MODEL_LABEL = "mock"

logger = get_logger(__name__)


def _model_label(provider: GenerationProvider) -> str:
    """Return the model identifier for the provider that actually ran.

    The mock provider has no real model name, so it falls back to a stable
    ``"mock"`` label rather than ``None``. Phase 2b providers may expose a
    ``model`` attribute carrying the real model id.

    Args:
        provider: The provider used for this generation run.

    Returns:
        str: The model identifier, never ``None``.
    """
    return getattr(provider, "model", None) or _MOCK_MODEL_LABEL


def _provider_label(provider: GenerationProvider) -> str:
    """Return the provider name for the provider that actually ran.

    Prefers a ``name`` attribute on the provider so an injected non-default
    provider is recorded accurately; falls back to the configured default
    provider name only when the provider exposes no name.

    Args:
        provider: The provider used for this generation run.

    Returns:
        str: The provider name actually used for this run.
    """
    return getattr(provider, "name", None) or _default_settings.generation_provider


# #CRITICAL: concurrency: the worker owns its own session/transaction, separate
# from any request unit-of-work. Never pass a request-scoped session into this
# function; doing so creates cross-transaction contamination.
# #VERIFY: worker is always called with its own session_factory, either the
# default (production) or an injected factory (tests). A request-scoped session
# must never be passed here.

# #CRITICAL: security: PII guard (assert_prompt_pii_safe) runs inside
# generate_story before every provider.complete call. No child name or birthdate
# reaches the provider unless the guard clears it. This chokepoint must not be
# bypassed when wiring real providers in Phase 2b.
# #VERIFY: integration test asserts PiiContext is populated from real child rows
# and that mock story generation does not include any real-child name in prompts.


async def _run_skeleton_fill(
    authoring: dict[str, object],
    brief: ConceptBrief,
    effective_provider: GenerationProvider,
    pii: PiiContext,
) -> GenerationOutcome:
    """Run the automated skeleton-fill pipeline (Stage B') for one job.

    Loads the matched skeleton library file, fills it via
    :func:`~cyo_adventure.generation.orchestrator.fill_skeleton`, then runs
    the Stage 1 fidelity gate. A fidelity violation downgrades an
    otherwise-``"passed"`` outcome to ``"needs_review"`` without discarding
    the produced storybook, so a guardian/admin can still review the fill.

    Args:
        authoring: The job's ``authoring_metadata`` dict (set by
            ``story_requests/authoring_plan.py::build_authoring_plan`` for
            ``method="skeleton_fill"`` + ``mechanism="automated_provider"``).
        brief: The concept brief; only its ``age_band`` is used, to resolve
            the skeleton library path.
        effective_provider: The provider used for the fill/repair calls.
        pii: PII context for the egress guard on every prompt.

    Returns:
        The :class:`~cyo_adventure.generation.orchestrator.GenerationOutcome`,
        with ``report`` augmented when a Stage 1 fidelity violation downgrades
        the status.

    Raises:
        ResourceNotFoundError: If ``authoring["skeleton_slug"]`` is missing or
            not a string.
        ValidationError: If the matched skeleton file fails structural
            validation (see :func:`~cyo_adventure.generation.skeleton.load_skeleton`).
    """
    skeleton_slug = authoring.get("skeleton_slug")
    theme_brief = authoring.get("theme_brief")
    # #ASSUME: data-integrity: authoring_metadata for a method="skeleton_fill"
    # job always carries a string skeleton_slug (see
    # story_requests/authoring_plan.py); a missing/wrong-typed value here
    # means the job was constructed outside that path.
    # #VERIFY: test_worker_runs_fill_skeleton_for_authoring_metadata_jobs.
    if not isinstance(skeleton_slug, str):
        msg = "authoring_metadata.skeleton_slug is missing or not a string"
        raise ResourceNotFoundError(msg)
    skeleton_path = Path("skeletons") / brief.age_band.value / f"{skeleton_slug}.json"
    skeleton = load_skeleton(skeleton_path)
    theme_brief_dict = theme_brief if isinstance(theme_brief, dict) else {}
    outcome = await fill_skeleton(skeleton, theme_brief_dict, effective_provider, pii)
    if outcome.storybook is None:
        return outcome

    # Only a clean "passed" fill is eligible for a Stage 1 downgrade. Skip the
    # paid semantic fidelity call entirely for an outcome that is already
    # "needs_review"/"failed": its result is consumed only on the passed branch
    # below, so calling run_stage1_gate here would spend a review-model request
    # whose violations are then discarded.
    if outcome.status != "passed":
        return outcome

    review_stage1_model = authoring.get("review_stage1_model")
    stage1_violations = await run_stage1_gate(
        skeleton,
        outcome.storybook,
        review_stage1_model=review_stage1_model
        if isinstance(review_stage1_model, str)
        else None,
        settings=_default_settings,
        pii=pii,
    )
    if stage1_violations:
        return dataclasses.replace(
            outcome,
            status="needs_review",
            report={**outcome.report, "stage1_fidelity_violations": stage1_violations},
        )
    return outcome


def _should_persist_storybook(outcome: GenerationOutcome) -> bool:
    """Decide whether ``run_generation_job`` should persist ``outcome.storybook``.

    Always true for a clean ``"passed"`` outcome. Also true for a
    ``"needs_review"`` outcome, but ONLY when the downgrade came from
    :func:`_run_skeleton_fill`'s own Stage 1 fidelity check on an
    otherwise-clean fill: that function adds the
    ``"stage1_fidelity_violations"`` key to ``outcome.report`` only when it
    performs this specific downgrade (never for any other cause), so the
    key's presence is an exact signal that the base outcome was clean before
    Stage 1 touched it. This lets an admin reach the real story behind a
    Stage-1-flagged fill instead of a job row pointing at nothing.

    Any OTHER ``"needs_review"`` (safety-flagged, or gate-blocked-with-doc
    after exhausting repairs -- both produced by
    :func:`~cyo_adventure.generation.orchestrator._build_outcome`, for either
    ``generate_story`` or ``fill_skeleton``'s own pre-Stage-1 outcome) and
    every ``"failed"`` outcome must keep NOT persisting a storybook: this is
    pre-existing, non-Plan-2 semantics that this widened gate must not
    change.

    Args:
        outcome: The pipeline outcome (from ``generate_story`` or
            ``_run_skeleton_fill``) about to be persisted onto the job row.

    Returns:
        True if a Storybook/StorybookVersion should be created for this
        outcome.
    """
    if outcome.storybook is None:
        return False
    stage1_downgraded = "stage1_fidelity_violations" in outcome.report
    return outcome.status == "passed" or (
        outcome.status == "needs_review" and stage1_downgraded
    )


def _review_stage2_override(authoring: dict[str, object] | None) -> str | None:
    """Return the Stage 2 review-model override recorded on the job, if valid.

    Args:
        authoring: The job's ``authoring_metadata`` dict, or ``None`` for a
            fresh (non-skeleton) generation that carries no override.

    Returns:
        The override model id when ``authoring`` carries a string
        ``review_stage2_model``; otherwise ``None`` (moderation uses its
        default reviewer).
    """
    if authoring is None:
        return None
    value = authoring.get("review_stage2_model")
    return value if isinstance(value, str) else None


@dataclasses.dataclass(frozen=True, slots=True)
class _PersistContext:
    """The per-job context :func:`_persist_and_moderate` needs to persist + moderate.

    Bundled into one object (mirroring
    :class:`~cyo_adventure.generation.persistence.StorybookParams`) so the helper
    stays under the argument-count limit while keeping each field explicit.

    Attributes:
        job_id: The job's UUID (the source of the per-job storybook id and the
            re-fetch key). Passed explicitly rather than read off ``job_row`` so
            the storybook id matches the id the job was loaded by, exactly as the
            pre-refactor inline code used it.
        job_row: The job row being processed (mutated in place).
        concept_row: The job's concept (supplies family/creator for the persist).
        effective_provider: The provider that actually ran (labels + review).
        authoring: The job's ``authoring_metadata``, or ``None`` for a fresh
            (non-skeleton) generation.
        pii: The PII guard context passed through to moderation.
    """

    job_id: uuid.UUID
    job_row: GenerationJob
    concept_row: Concept
    effective_provider: GenerationProvider
    authoring: dict[str, object] | None
    pii: PiiContext


async def _persist_and_moderate(
    session: AsyncSession, ctx: _PersistContext, outcome: GenerationOutcome
) -> None:
    """Persist a persist-eligible outcome's storybook and run moderation on it.

    For a non-persist-eligible outcome (see :func:`_should_persist_storybook`)
    this logs and returns without touching the store, so the caller's single
    ``session.commit()`` still records the job's status/report/error. For a
    persist-eligible outcome it creates the Storybook/StorybookVersion, links
    them to the job, and drives the moderation pipeline; a moderation failure
    rolls back the unreviewed persist and records the failure on a re-fetched
    row before re-raising (see the inline RAD markers).

    Args:
        session: The worker's owned session (caller commits on the happy path).
        ctx: The per-job persist/moderate context (see :class:`_PersistContext`).
        outcome: The pipeline outcome about to be recorded on the job.

    Raises:
        Exception: Re-raises any moderation-pipeline failure after rolling back
            the persist and recording the failure on the job row.
    """
    job_id = ctx.job_id
    # The `outcome.storybook is not None` half is redundant with
    # _should_persist_storybook's own None check, but is repeated so BasedPyright
    # narrows outcome.storybook to dict[str, object] for the persist call below.
    if not (_should_persist_storybook(outcome) and outcome.storybook is not None):
        logger.info(
            "generation_job.not_passed",
            job_id=str(job_id),
            status=outcome.status,
            attempts=outcome.attempts,
        )
        return

    # Mint a per-job storybook id so successive passing jobs never collide on the
    # storybook primary key. The mock provider returns a fixed blob id
    # ("s_mock_generated"), so reusing it would raise an IntegrityError on the
    # second passing job. Stamp the same id back onto the stored blob so the
    # blob's "id" matches its DB row.
    story_id = f"s_{job_id}"

    await persist_storybook(
        session,
        StorybookParams(
            story_id=story_id,
            blob=outcome.storybook,
            family_id=ctx.concept_row.family_id,
            created_by=ctx.concept_row.created_by,
            model=ctx.job_row.model,
            prompt_version=_PROMPT_VERSION,
            validation_report=dict(outcome.report),
            version=_FIRST_VERSION,
        ),
    )

    ctx.job_row.storybook_id = story_id
    ctx.job_row.version = _FIRST_VERSION

    logger.info(
        "generation_job.storybook_persisted",
        job_id=str(job_id),
        storybook_id=story_id,
        status=ctx.job_row.status,
    )

    # #CRITICAL: security: a passed story is only a draft; it must be screened
    # and submitted/auto-rejected before commit so no unreviewed story rests in
    # a state a guardian could approve.
    # #VERIFY: run_moderation_pipeline drives submit or auto_reject on the row.
    try:
        await run_moderation_pipeline(
            session=session,
            story_id=story_id,
            version=_FIRST_VERSION,
            settings=_default_settings,
            generation_provider=ctx.effective_provider,
            pii=ctx.pii,
            review_model_override=_review_stage2_override(ctx.authoring),
        )
    except Exception as exc:
        # #CRITICAL: external-resource: a live review backend can raise
        # (timeout, 5xx, auth). Roll back the unreviewed storybook persist
        # first: the per-job story_id (f"s_{job_id}") would otherwise collide
        # on an RQ retry of this same job. Then record the failure on a
        # re-fetched row and commit, so the committed job state is "failed"
        # (not a stale "running") and the row agrees with the queue.
        # #VERIFY: rollback discards the persist; failure is committed before
        # the re-raise.
        error_text = str(exc)[:512]
        await session.rollback()
        failed_row = await session.get(GenerationJob, job_id)
        if failed_row is not None:
            failed_row.status = "failed"
            failed_row.error = error_text
            failed_row.provider = _provider_label(ctx.effective_provider)
            failed_row.prompt_version = _PROMPT_VERSION
            await session.commit()
        else:
            # The "record failed" half of the invariant could not run: the row
            # vanished post-rollback (concurrent delete, or a rollback that
            # unwound its visibility). Surface it so the queue/DB divergence the
            # rollback is meant to prevent is observable, not silent.
            logger.exception(
                "generation_job.failure_record_lost",
                job_id=str(job_id),
                error=error_text,
            )
        logger.exception(
            "generation_job.moderation_error",
            job_id=str(job_id),
            error=error_text,
        )
        raise


async def run_generation_job(
    job_id: uuid.UUID,
    *,
    provider: GenerationProvider | None = None,
    session_factory: (
        Callable[[], AbstractAsyncContextManager[AsyncSession]] | None
    ) = None,
) -> None:
    """Run the generation pipeline for a single job, persisting the outcome.

    This is the testable async core. Tests inject ``provider`` and
    ``session_factory`` directly; production uses the defaults built from
    application settings.

    Lifecycle transitions::

        queued -> running -> passed | needs_review | failed

    On ``"passed"``: creates a :class:`~cyo_adventure.db.models.Storybook` row
    and a :class:`~cyo_adventure.db.models.StorybookVersion` row, then links
    both back to the job.

    On ``"needs_review"`` when the downgrade came from a Stage 1 fidelity
    check on an otherwise-clean fill (signaled by
    ``"stage1_fidelity_violations"`` in ``outcome.report``, the exact key
    :func:`_run_skeleton_fill` adds only for this downgrade): the same
    Storybook/StorybookVersion creation and linking happens as for
    ``"passed"``, and the moderation pipeline still runs on the result, so a
    guardian/admin can review a real, queryable story instead of a job row
    pointing at nothing.

    On any OTHER ``"needs_review"`` (safety-flagged by
    :func:`~cyo_adventure.generation.orchestrator._build_outcome`, or
    gate-blocked-with-doc after exhausting repairs) or on ``"failed"``:
    records the report and error on the job row; no Storybook or
    StorybookVersion is created.

    On unexpected exception: sets ``job.status = "failed"``, records the error,
    commits, then re-raises so RQ marks the job failed in its own bookkeeping.

    Args:
        job_id: UUID of the :class:`~cyo_adventure.db.models.GenerationJob` to
            process. Raises :class:`~cyo_adventure.core.exceptions.ResourceNotFoundError`
            if the row is missing.
        provider: Optional injected :class:`~cyo_adventure.generation.provider.GenerationProvider`.
            When ``None``, the production provider is built from
            :data:`~cyo_adventure.core.config.settings`.
        session_factory: Optional callable returning an async context manager
            that yields an :class:`~sqlalchemy.ext.asyncio.AsyncSession`. When
            ``None``, the production :func:`~cyo_adventure.core.database.get_session`
            factory is used.

    Raises:
        ResourceNotFoundError: If no GenerationJob row exists for ``job_id``.
        Exception: Re-raises any unexpected exception after recording the
            failure on the job row, so RQ can mark the job failed.
    """
    set_correlation_id(generate_correlation_id())

    # Resolve defaults: use injected factory or the production session factory.
    # #ASSUME: external-resources: get_session() opens a DB connection on first
    # use; an unreachable database surfaces here as a connection error.
    # #VERIFY: readiness probe on api/health.check_database catches DB outages
    # before jobs are dispatched.
    _factory = session_factory or get_session

    effective_provider = provider or build_provider(_default_settings)

    async with _factory() as session:  # type: ignore[attr-defined]
        # ------------------------------------------------------------------
        # Load and mark the job as running.
        # ------------------------------------------------------------------
        job_row = await session.get(GenerationJob, job_id)
        if job_row is None:
            msg = f"GenerationJob {job_id} not found"
            raise ResourceNotFoundError(
                msg, resource_type="GenerationJob", resource_id=str(job_id)
            )

        job_row.status = "running"
        await session.flush()

        logger.info(
            "generation_job.started",
            job_id=str(job_id),
            concept_id=str(job_row.concept_id),
        )

        # ------------------------------------------------------------------
        # Load the concept brief.
        # ------------------------------------------------------------------
        concept_row = await session.get(Concept, job_row.concept_id)
        if concept_row is None:
            # Record the failure on the job row before raising. Without this
            # commit the "running" flush above is discarded on session close,
            # leaving the job visibly "queued" with no error while RQ marks it
            # failed; the row and the queue would disagree permanently.
            msg = f"Concept {job_row.concept_id} not found"
            job_row.status = "failed"
            job_row.error = msg[:512]
            await session.commit()
            raise ResourceNotFoundError(
                msg,
                resource_type="Concept",
                resource_id=str(job_row.concept_id),
            )

        brief = ConceptBrief.model_validate(concept_row.brief)

        # ------------------------------------------------------------------
        # Build PiiContext from the family's real child names.
        # ChildProfile has no birthdate column; leave birthdates empty.
        # ------------------------------------------------------------------
        child_result = await session.execute(
            select(ChildProfile.display_name).where(
                ChildProfile.family_id == concept_row.family_id
            )
        )
        child_names: frozenset[str] = frozenset(
            row for (row,) in child_result.all() if row
        )
        pii = PiiContext(child_names=child_names, birthdates=frozenset())

        # ------------------------------------------------------------------
        # Run the generation pipeline. Wrap to persist failures.
        # ------------------------------------------------------------------
        authoring = (
            job_row.authoring_metadata
            if isinstance(job_row.authoring_metadata, dict)
            else None
        )
        try:
            if authoring is not None:
                outcome = await _run_skeleton_fill(
                    authoring, brief, effective_provider, pii
                )
            else:
                outcome = await generate_story(brief, effective_provider, pii)
        except Exception as exc:
            # Record failure and re-raise so RQ marks the job failed.
            error_text = str(exc)[:512]
            job_row.status = "failed"
            job_row.error = error_text
            job_row.provider = _provider_label(effective_provider)
            job_row.prompt_version = _PROMPT_VERSION
            await session.commit()
            logger.exception(
                "generation_job.pipeline_error",
                job_id=str(job_id),
                error=error_text,
            )
            raise

        # ------------------------------------------------------------------
        # Persist outcome onto the job row.
        # ------------------------------------------------------------------
        job_row.status = outcome.status
        job_row.report = dict(outcome.report)
        job_row.provider = _provider_label(effective_provider)
        job_row.prompt_version = _PROMPT_VERSION
        # Record the model of the provider that actually ran. Deriving this from
        # the injected-arg presence recorded None in production (where provider
        # is None but the mock still runs); _model_label reflects the real run.
        job_row.model = _model_label(effective_provider)

        await _persist_and_moderate(
            session,
            _PersistContext(
                job_id=job_id,
                job_row=job_row,
                concept_row=concept_row,
                effective_provider=effective_provider,
                authoring=authoring,
                pii=pii,
            ),
            outcome,
        )

        await session.commit()


def run_generation_job_sync(job_id_str: str) -> None:
    """Synchronous RQ entrypoint that dispatches to the async worker.

    RQ calls this function in a worker process. It converts ``job_id_str`` to
    a :class:`uuid.UUID` and delegates to :func:`run_generation_job` via
    :func:`asyncio.run`, which creates a fresh event loop per call (safe for
    RQ's process-per-job model).

    Args:
        job_id_str: The UUID string of the job to process, as stored when the
            job was enqueued by :func:`~cyo_adventure.generation.queue.enqueue_generation`.

    Raises:
        ValueError: If ``job_id_str`` is not a valid UUID string.
        Exception: Propagates any exception from :func:`run_generation_job`
            so RQ can record the failure.
    """
    asyncio.run(run_generation_job(uuid.UUID(job_id_str)))
