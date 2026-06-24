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
import uuid
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
from cyo_adventure.generation.orchestrator import generate_story
from cyo_adventure.generation.persistence import StorybookParams, persist_storybook
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import build_provider
from cyo_adventure.middleware.correlation import (
    generate_correlation_id,
    set_correlation_id,
)
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    from sqlalchemy.ext.asyncio import AsyncSession

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

    On ``"needs_review"`` or ``"failed"``: records the report and error on the
    job row; no Storybook or StorybookVersion is created.

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
        try:
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

        if outcome.status == "passed" and outcome.storybook is not None:
            # Mint a per-job storybook id so successive passing jobs never
            # collide on the storybook primary key. The mock provider returns a
            # fixed blob id ("s_mock_generated"), so reusing it would raise an
            # IntegrityError on the second passing job. Stamp the same id back
            # onto the stored blob so the blob's "id" matches its DB row.
            story_id = f"s_{job_id}"

            await persist_storybook(
                session,
                StorybookParams(
                    story_id=story_id,
                    blob=outcome.storybook,
                    family_id=concept_row.family_id,
                    created_by=concept_row.created_by,
                    model=job_row.model,
                    prompt_version=_PROMPT_VERSION,
                    validation_report=dict(outcome.report),
                    version=_FIRST_VERSION,
                ),
            )

            job_row.storybook_id = story_id
            job_row.version = _FIRST_VERSION

            logger.info(
                "generation_job.passed",
                job_id=str(job_id),
                storybook_id=story_id,
            )
        else:
            logger.info(
                "generation_job.not_passed",
                job_id=str(job_id),
                status=outcome.status,
                attempts=outcome.attempts,
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
