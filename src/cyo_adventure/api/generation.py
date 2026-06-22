"""Guardian-only generation endpoints: concepts, jobs, and the validate gate.

All four endpoints require the guardian role. Child tokens receive 403
immediately. Resources are scoped to the authenticated principal's family;
cross-family access returns 403 (via ``authorize_family`` raising
``AuthorizationError``), which matches the existing convention in
``library.py`` and ``reading.py``.

Cross-family status code choice
---------------------------------
``authorize_family`` raises ``AuthorizationError``, which the app's exception
handler maps to 403. A missing row raises ``ResourceNotFoundError``, which
maps to 404. This is consistent with ``library.py`` / ``reading.py``: a row
that genuinely does not exist is 404; a row that exists but belongs to another
family is 403 (the caller's token is valid but lacks permission). Returning
404 on a cross-family hit would also be acceptable for existence-hiding, but
the project's existing routers already use 403, so we match that pattern here
(docs/planning/authorization-matrix.md: "cross-family 403").

Redis / enqueue resilience
--------------------------
``enqueue_generation`` connects to Redis lazily. If Redis is unreachable the
``GenerationJob`` row is still created (status ``queued``) and a 202 is
returned. The narrow ``except`` around the enqueue call logs the failure but
does not surface it as a 5xx because the row is the durable record and a
worker restart or retry can process it later.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from sqlalchemy import select

from cyo_adventure.api.deps import Context, authorize_family
from cyo_adventure.api.schemas import (
    ConceptCreatedResponse,
    ConceptCreateRequest,
    GenerationEnqueuedResponse,
    GenerationJobResponse,
    ValidateResponse,
)
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import AuthorizationError, ResourceNotFoundError
from cyo_adventure.db.models import (
    ChildProfile,
    Concept,
    GenerationJob,
    Storybook,
    StorybookVersion,
)
from cyo_adventure.generation.pii import PiiContext, assert_prompt_pii_safe
from cyo_adventure.generation.queue import enqueue_generation
from cyo_adventure.validator.gate import run_gate

router = APIRouter(prefix="/api/v1", tags=["generation"])

_log = logging.getLogger(__name__)

_GUARDIAN_REQUIRED = "guardian role required for this endpoint"


@router.post("/concepts", status_code=201)
async def create_concept(
    body: ConceptCreateRequest,
    ctx: Context,
) -> ConceptCreatedResponse:
    """Create a concept brief for story generation.

    The brief is PII-screened against the family's real child names before
    being persisted. A brief that embeds a real child's display name is
    rejected with 422.

    Args:
        body: The request body containing the validated ``ConceptBrief``.
        ctx: The request context (principal and session).

    Returns:
        ConceptCreatedResponse: The id of the newly created concept.

    Raises:
        AuthorizationError: If the principal is not a guardian (-> 403).
        ValidationError: If the brief contains a real child name (-> 422).
    """
    # #CRITICAL: security: guardian-only; child tokens must never reach
    # authoring or generation endpoints (authorization-matrix.md).
    # #VERIFY: test_generation_api::test_child_token_rejected confirms 403 for
    # all four endpoints when called with a child token.
    if not ctx.principal.is_guardian:
        raise AuthorizationError(_GUARDIAN_REQUIRED)

    # #CRITICAL: security: PII egress guard -- screen the assembled brief text
    # against the family's real child display names before persisting. Any
    # match raises ValidationError (-> 422). The guard must run before the
    # Concept row is written so that a brief embedding a real name never
    # reaches the generation queue.
    # #VERIFY: test_generation_api::test_pii_in_brief_rejected covers this path.
    rows = await ctx.session.scalars(
        select(ChildProfile.display_name).where(
            ChildProfile.family_id == ctx.principal.family_id
        )
    )
    child_names = frozenset(rows.all())
    pii = PiiContext(child_names=child_names, birthdates=frozenset())
    assert_prompt_pii_safe(body.brief.model_dump_json(), forbidden=pii)

    concept = Concept(
        family_id=ctx.principal.family_id,
        brief=body.brief.model_dump(mode="json"),
    )
    ctx.session.add(concept)
    await ctx.session.flush()
    return ConceptCreatedResponse(concept_id=str(concept.id))


@router.post("/concepts/{concept_id}/generate", status_code=202)
async def enqueue_concept_generation(
    concept_id: str,
    ctx: Context,
) -> GenerationEnqueuedResponse:
    """Enqueue a generation job for an existing concept.

    Creates a ``GenerationJob`` row with status ``queued`` and attempts to
    push the job onto the RQ queue. If Redis is unreachable the row is still
    created and a 202 is returned (best-effort enqueue).

    Args:
        concept_id: The UUID string of the concept to generate from.
        ctx: The request context (principal and session).

    Returns:
        GenerationEnqueuedResponse: The new job id and initial status.

    Raises:
        AuthorizationError: If the principal is not a guardian (-> 403) or if
            the concept belongs to another family (-> 403).
        ResourceNotFoundError: If the concept does not exist (-> 404).
    """
    # #CRITICAL: security: guardian-only (authorization-matrix.md).
    # #VERIFY: test_generation_api::test_child_token_rejected.
    if not ctx.principal.is_guardian:
        raise AuthorizationError(_GUARDIAN_REQUIRED)

    # #CRITICAL: security: family-scoped IDOR guard -- must verify the concept
    # belongs to the principal's family before creating a job row.
    # #VERIFY: test_generation_api::test_cross_family_blocked.
    concept = await ctx.session.get(Concept, concept_id)
    if concept is None:
        msg = f"concept '{concept_id}' not found"
        raise ResourceNotFoundError(msg)
    authorize_family(ctx.principal, concept.family_id)

    job = GenerationJob(concept_id=concept.id, status="queued")
    ctx.session.add(job)
    await ctx.session.flush()

    # Best-effort enqueue: a Redis connection error must not 500 the request
    # because the job row is the durable record. The worker can consume it
    # once Redis is available.
    # #ASSUME: external-resources: Redis may be unreachable in test/dev
    # environments; the row is the source of truth, not the queue entry.
    # #VERIFY: test_generation_api::test_enqueue_returns_202_without_redis.
    try:
        enqueue_generation(str(job.id), settings)
    except Exception:  # noqa: BLE001
        _log.warning(
            "enqueue_generation failed for job %s; row created but not queued",
            job.id,
        )

    return GenerationEnqueuedResponse(job_id=str(job.id), status=job.status)


@router.get("/generation-jobs/{job_id}")
async def get_generation_job(
    job_id: str,
    ctx: Context,
) -> GenerationJobResponse:
    """Return the status and report for a generation job.

    Args:
        job_id: The UUID string of the job to fetch.
        ctx: The request context (principal and session).

    Returns:
        GenerationJobResponse: Status, report, storybook link, and error.

    Raises:
        AuthorizationError: If the principal is not a guardian (-> 403) or if
            the job's concept belongs to another family (-> 403).
        ResourceNotFoundError: If the job or its concept does not exist (-> 404).
    """
    # #CRITICAL: security: guardian-only (authorization-matrix.md).
    # #VERIFY: test_generation_api::test_child_token_rejected.
    if not ctx.principal.is_guardian:
        raise AuthorizationError(_GUARDIAN_REQUIRED)

    # #CRITICAL: security: IDOR guard -- load the job then its concept to check
    # family ownership. A valid token for family B must not read family A's jobs.
    # #VERIFY: test_generation_api::test_cross_family_blocked.
    job = await ctx.session.get(GenerationJob, job_id)
    if job is None:
        msg = f"generation job '{job_id}' not found"
        raise ResourceNotFoundError(msg)
    concept = await ctx.session.get(Concept, job.concept_id)
    if concept is None:
        msg = f"concept for job '{job_id}' not found"
        raise ResourceNotFoundError(msg)
    authorize_family(ctx.principal, concept.family_id)

    return GenerationJobResponse(
        id=str(job.id),
        status=job.status,
        report=job.report,
        storybook_id=job.storybook_id,
        version=job.version,
        error=job.error,
    )


@router.post("/storybooks/{storybook_id}/versions/{version}/validate")
async def validate_storybook_version(
    storybook_id: str,
    version: int,
    ctx: Context,
) -> ValidateResponse:
    """Re-run the validation gate on a stored storybook version.

    Args:
        storybook_id: The story id.
        version: The version number to validate.
        ctx: The request context (principal and session).

    Returns:
        ValidateResponse: Whether the version is blocked plus the gate report.

    Raises:
        AuthorizationError: If the principal is not a guardian (-> 403) or if
            the storybook belongs to another family (-> 403).
        ResourceNotFoundError: If the storybook or version does not exist (-> 404).
    """
    # #CRITICAL: security: guardian-only (authorization-matrix.md).
    # #VERIFY: test_generation_api::test_child_token_rejected.
    if not ctx.principal.is_guardian:
        raise AuthorizationError(_GUARDIAN_REQUIRED)

    # #CRITICAL: security: IDOR guard -- load the storybook to verify family
    # ownership before returning any version data or gate results.
    # #VERIFY: test_generation_api::test_validate_cross_family_blocked.
    book = await ctx.session.get(Storybook, storybook_id)
    if book is None:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)
    authorize_family(ctx.principal, book.family_id)

    sv = await ctx.session.get(StorybookVersion, (storybook_id, version))
    if sv is None:
        msg = f"version {version} of storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(msg)

    result = run_gate(sv.blob)
    return ValidateResponse(
        blocked=result.blocked,
        report=result.report.to_dict(),
    )
