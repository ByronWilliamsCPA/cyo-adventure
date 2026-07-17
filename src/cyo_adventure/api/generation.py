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
import uuid
from typing import TYPE_CHECKING, Literal, cast

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import func, select
from sqlalchemy.orm import defer

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.api.deps import Context, authorize_family
from cyo_adventure.api.schemas import (
    ConceptCreatedResponse,
    ConceptCreateRequest,
    GenerationEnqueuedResponse,
    GenerationJobListItem,
    GenerationJobListView,
    GenerationJobResponse,
    JobStatusLiteral,
    ValidateResponse,
    error_responses,
)
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
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

router = APIRouter(
    prefix="/api/v1", tags=["generation"], responses=error_responses(401, 403)
)

_log = logging.getLogger(__name__)

_GUARDIAN_REQUIRED = "guardian role required for this endpoint"

# Max active (queued+running) generation jobs per family before a new enqueue
# is refused (audit Finding 9). Mirrors MAX_PENDING_PER_PROFILE
# (story_requests/service.py): an abuse throttle, not a correctness invariant.
MAX_ACTIVE_JOBS_PER_FAMILY = 2

# Lifecycle states that count as "active" for the per-family throttle: a job
# that has already finished (passed/needs_review/failed) no longer occupies a
# generation slot.
_ACTIVE_JOB_STATUSES = ("queued", "running")


async def count_active_jobs_for_family(session: AsyncSession, family_id: object) -> int:
    """Return the count of queued+running GenerationJob rows for a family.

    Args:
        session: The request session.
        family_id: The family id to scope the count to.

    Returns:
        int: Count of active (queued or running) job rows joined through
            their Concept's family.
    """
    # #CRITICAL: concurrency: two concurrent enqueue requests could both read
    # count=N-1 and both create a job (a benign one-over race). The cap is an
    # abuse throttle, not a correctness invariant; mirrors
    # story_requests.service.count_pending_for_profile.
    # #VERIFY: a strict guarantee would need a partial unique index or
    # advisory lock; deferred as unnecessary for R1, matching the mirrored
    # pending-request cap.
    total = await session.scalar(
        select(func.count())
        .select_from(GenerationJob)
        .join(Concept, GenerationJob.concept_id == Concept.id)
        .where(
            Concept.family_id == family_id,
            GenerationJob.status.in_(_ACTIVE_JOB_STATUSES),
        )
    )
    return int(total or 0)


def _parse_uuid(raw: str, field: str) -> uuid.UUID:
    """Parse a UUID path value, mapping a malformed value to a 422 error.

    Mirrors ``reading.py``'s helper so a non-UUID path parameter raises a
    client-friendly ``ValidationError`` (422) instead of leaking a driver error
    as a 500.

    Args:
        raw: The raw path value.
        field: The name of the path parameter, for the error payload.

    Returns:
        uuid.UUID: The parsed UUID.

    Raises:
        ValidationError: If ``raw`` is not a valid UUID (-> 422).
    """
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        msg = f"{field} must be a UUID"
        raise ValidationError(msg, field=field, value=raw) from exc


def _enqueue_safely(job_id: str) -> None:
    """Best-effort RQ enqueue, run as a background task after the commit.

    Running here (a FastAPI ``BackgroundTask``) rather than inline fixes two
    issues: it runs AFTER the request unit-of-work commits, so the worker can
    never observe a job row that is not yet durable; and FastAPI runs a sync
    background callable in its threadpool, keeping the blocking Redis client off
    the event loop.

    Args:
        job_id: The UUID string of the GenerationJob row to enqueue.
    """
    # #ASSUME: external-resources: Redis may be unreachable; the GenerationJob
    # row is the durable record, so a failed enqueue is logged, not raised.
    # #VERIFY: generation/queue.py::requeue_stranded_jobs re-queues rows
    # stranded in the "queued" state by this failure (or any other outage);
    # run once at worker-process startup (generation/worker_main.py::main).
    try:
        enqueue_generation(job_id, settings)
    except Exception:  # noqa: BLE001 -- best-effort enqueue; row is the source of truth
        _log.exception(
            "enqueue_generation failed for job %s; row committed but not queued",
            job_id,
        )


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
        # Stamp creator provenance: the worker later propagates this into
        # Storybook.created_by, so an unset value loses attribution end-to-end.
        created_by=ctx.principal.user_id,
    )
    ctx.session.add(concept)
    await ctx.session.flush()
    return ConceptCreatedResponse(concept_id=str(concept.id))


@router.post(
    "/concepts/{concept_id}/generate",
    status_code=202,
    responses=error_responses(404, 409),
)
async def enqueue_concept_generation(
    concept_id: str,
    ctx: Context,
    background_tasks: BackgroundTasks,
) -> GenerationEnqueuedResponse:
    """Enqueue a generation job for an existing concept.

    Creates a ``GenerationJob`` row with status ``queued`` and schedules a
    best-effort RQ enqueue as a background task. If Redis is unreachable the row
    is still created and a 202 is returned.

    Args:
        concept_id: The UUID string of the concept to generate from.
        ctx: The request context (principal and session).
        background_tasks: FastAPI background-task collector; the enqueue runs
            here so it fires after the request unit-of-work commits.

    Returns:
        GenerationEnqueuedResponse: The new job id and initial status.

    Raises:
        AuthorizationError: If the principal is not a guardian (-> 403) or if
            the concept belongs to another family (-> 403).
        ResourceNotFoundError: If the concept does not exist (-> 404).
        StateTransitionError: If the family is at its active-job cap (-> 409).
        ValidationError: If ``concept_id`` is not a valid UUID (-> 422).
    """
    # #CRITICAL: security: guardian-only (authorization-matrix.md).
    # #VERIFY: test_generation_api::test_child_token_rejected.
    if not ctx.principal.is_guardian:
        raise AuthorizationError(_GUARDIAN_REQUIRED)

    # #CRITICAL: security: family-scoped IDOR guard -- must verify the concept
    # belongs to the principal's family before creating a job row.
    # #VERIFY: test_generation_api::test_cross_family_blocked.
    concept_uuid = _parse_uuid(concept_id, "concept_id")
    concept = await ctx.session.get(Concept, concept_uuid)
    if concept is None:
        msg = f"concept '{concept_id}' not found"
        raise ResourceNotFoundError(msg)
    authorize_family(ctx.principal, concept.family_id)

    # #CRITICAL: security: enforce the per-family active-job cap before insert
    # (audit Finding 9). A rare off-by-one under concurrent enqueues is
    # accepted here (see count_active_jobs_for_family); the cap is an abuse
    # throttle, not a correctness invariant.
    # #VERIFY: test_enqueue_family_at_cap_rejected / test_enqueue_family_under_cap_allowed.
    active = await count_active_jobs_for_family(ctx.session, concept.family_id)
    if active >= MAX_ACTIVE_JOBS_PER_FAMILY:
        msg = "too many active generation jobs for this family"
        raise StateTransitionError(msg)

    job = GenerationJob(concept_id=concept.id, status="queued")
    ctx.session.add(job)
    await ctx.session.flush()

    # Enqueue AFTER the request commits (background task) so the worker never
    # races the not-yet-durable row, and so the blocking Redis client stays off
    # the event loop. Best-effort: a Redis outage logs but does not 500 the
    # request, because the job row is the durable source of truth.
    # #VERIFY: test_generation_api::test_enqueue_returns_202_without_redis.
    background_tasks.add_task(_enqueue_safely, str(job.id))

    # #ASSUME: data integrity: job.status is "queued" immediately after
    # construction above; cast (not the model default) keeps this response
    # consistent with get_generation_job below, reading and revalidating the
    # real value rather than assuming the default matches it.
    # #VERIFY: GenerationJob's only status at construction is "queued"
    # (db/models.py); a future non-"queued" initial state would surface here
    # as a ResponseValidationError instead of a silently-wrong response.
    return GenerationEnqueuedResponse(
        job_id=str(job.id), status=cast("Literal['queued']", job.status)
    )


# Cap the number of jobs returned so the list stays a bounded, single query.
_JOB_LIST_LIMIT = 50

# Longest premise prefix shown as a row label; keeps the payload compact and
# avoids echoing a long free-text brief back into the list view.
_PREMISE_SNIPPET_LEN = 120


def _str_or_none(value: object) -> str | None:
    """Return ``value`` if it is a non-empty string, else ``None``.

    The brief is stored as loosely-typed JSON (Concept.brief), so a reader must
    tolerate missing or wrong-typed keys rather than trust the shape.
    """
    return value if isinstance(value, str) and value else None


@router.get("/generation-jobs")
async def list_generation_jobs(ctx: Context) -> GenerationJobListView:
    """List the calling guardian's family generation jobs, newest first.

    Guardian-only. Scoped to the principal's family via the Concept join. The
    raw ``report`` column is never selected or returned (ADR-007): only status,
    the linked storybook id/status/version, the short error, and enough brief
    context to label the row.

    Args:
        ctx: The request context (principal and session).

    Returns:
        GenerationJobListView: Up to the 50 most recent jobs for the family.

    Raises:
        AuthorizationError: If the principal is not a guardian (-> 403).
    """
    # #CRITICAL: security: guardian-only; a child token must never enumerate
    # a family's generation jobs (authorization-matrix.md).
    # #VERIFY: test_generation_api::test_list_jobs_child_token_rejected.
    if not ctx.principal.is_guardian:
        raise AuthorizationError(_GUARDIAN_REQUIRED)

    # #CRITICAL: security: family-scoped IDOR guard -- the WHERE clause filters
    # on the joined Concept.family_id so family B never sees family A's jobs.
    # A single query with an outer join to Storybook avoids an N+1 status lookup.
    # #VERIFY: test_generation_api::test_list_jobs_is_family_scoped.
    #
    # #CRITICAL: security: never load the raw ``report`` JSON (ADR-007: admin/system
    # only) for the guardian list view. defer(..., raiseload=True) drops ``report``
    # from the emitted SELECT AND turns any accidental future access into a loud
    # error instead of a silent lazy-load, closing the leak-on-refactor hazard
    # structurally rather than relying on the response schema alone.
    # #VERIFY: test_generation_api::test_list_jobs_never_exposes_report.
    stmt = (
        select(GenerationJob, Concept.brief, Storybook.status)
        .join(Concept, GenerationJob.concept_id == Concept.id)
        .outerjoin(Storybook, GenerationJob.storybook_id == Storybook.id)
        .where(Concept.family_id == ctx.principal.family_id)
        # #ASSUME: data-integrity: created_at can tie for rows inserted within one
        # timestamp tick; the id tiebreaker makes ordering (and which row the
        # 50-cap drops at the boundary) deterministic instead of engine-defined.
        # #VERIFY: test_generation_api::test_list_jobs_cap_of_50.
        .order_by(GenerationJob.created_at.desc(), GenerationJob.id.desc())
        .limit(_JOB_LIST_LIMIT)
        .options(defer(GenerationJob.report, raiseload=True))
    )
    rows = (await ctx.session.execute(stmt)).all()

    items: list[GenerationJobListItem] = []
    for job, brief, storybook_status in rows:
        # #ASSUME: data-integrity: ``brief`` is loosely-typed JSON; read defensively.
        # #VERIFY: _str_or_none tolerates missing/wrong-typed premise/title/age_band.
        brief_map = brief if isinstance(brief, dict) else {}
        premise = _str_or_none(brief_map.get("premise")) or ""
        items.append(
            GenerationJobListItem(
                id=str(job.id),
                # #ASSUME: data-integrity: job.status is one of JobStatusLiteral's
                # five values (ck_generation_job_status); cast mirrors
                # get_generation_job so no new str->Literal error is introduced.
                # #VERIFY: JobStatusLiteral matches _GENERATION_JOB_STATUS_VALUES.
                status=cast("JobStatusLiteral", job.status),
                storybook_id=job.storybook_id,
                storybook_status=storybook_status,
                version=job.version,
                error=job.error,
                title=_str_or_none(brief_map.get("title")),
                premise_snippet=premise[:_PREMISE_SNIPPET_LEN],
                age_band=_str_or_none(brief_map.get("age_band")),
                created_at=job.created_at,
            )
        )
    return GenerationJobListView(jobs=items)


@router.get("/generation-jobs/{job_id}", responses=error_responses(404))
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
        ValidationError: If ``job_id`` is not a valid UUID (-> 422).
    """
    # #CRITICAL: security: guardian-only (authorization-matrix.md).
    # #VERIFY: test_generation_api::test_child_token_rejected.
    if not ctx.principal.is_guardian:
        raise AuthorizationError(_GUARDIAN_REQUIRED)

    # #CRITICAL: security: IDOR guard -- load the job then its concept to check
    # family ownership. A valid token for family B must not read family A's jobs.
    # #VERIFY: test_generation_api::test_cross_family_blocked.
    job_uuid = _parse_uuid(job_id, "job_id")
    job = await ctx.session.get(GenerationJob, job_uuid)
    if job is None:
        msg = f"generation job '{job_id}' not found"
        raise ResourceNotFoundError(msg)
    concept = await ctx.session.get(Concept, job.concept_id)
    if concept is None:
        msg = f"concept for job '{job_id}' not found"
        raise ResourceNotFoundError(msg)
    authorize_family(ctx.principal, concept.family_id)

    # #ASSUME: data-integrity: authoring_metadata is loosely-typed JSON written
    # by story_requests/authoring_plan.py::build_authoring_plan for
    # method="skeleton_fill" jobs only; read both keys defensively.
    # #VERIFY: test_get_job_exposes_skeleton_and_theme_brief_when_parked.
    authoring = (
        job.authoring_metadata if isinstance(job.authoring_metadata, dict) else {}
    )
    skeleton_slug = authoring.get("skeleton_slug")
    theme_brief = authoring.get("theme_brief")

    # #ASSUME: data integrity: job.status is one of JobStatusLiteral's five
    # values; the ck_generation_job_status CHECK (db/models.py) constrains the
    # stored value, and Pydantic revalidates it against JobStatusLiteral on
    # construction, so the cast asserts what the DB already guarantees rather
    # than performing the check itself.
    # #VERIFY: JobStatusLiteral's five values match
    # db/models.py's _GENERATION_JOB_STATUS_VALUES exactly (see
    # tests/unit/test_schemas.py::test_job_status_literal_matches_db_constraint).
    return GenerationJobResponse(
        id=str(job.id),
        status=cast("JobStatusLiteral", job.status),
        report=job.report,
        storybook_id=job.storybook_id,
        version=job.version,
        error=job.error,
        skeleton_slug=skeleton_slug if isinstance(skeleton_slug, str) else None,
        theme_brief=theme_brief if isinstance(theme_brief, dict) else None,
    )


@router.post(
    "/storybooks/{storybook_id}/versions/{version}/validate",
    responses=error_responses(404),
)
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
