"""Child story-request endpoints: submit, list, approve, decline.

The kid surface runs under the guardian token in R1, so submission is
guardian-scoped (the body carries the profile_id and authorize_profile gates it).
List is family-scoped for a guardian (optional profile filter) and global for an
admin. Approve and decline are guardian-own-family or admin-global; a request
outside the caller's scope returns 404 (existence hiding), which deliberately
diverges from generation.py's cross-family 403 for this lower-value, child-facing
resource. Approve builds a ConceptBrief and enqueues generation through the
service layer, so it never touches the guardian-only POST /concepts gate.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal, cast

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import select

from cyo_adventure.api.deps import Context, authorize_profile, parse_uuid
from cyo_adventure.api.schemas import (
    StoryRequestApprovedView,
    StoryRequestCreateBody,
    StoryRequestCreatedView,
    StoryRequestDeclinedView,
    StoryRequestFlag,
    StoryRequestListView,
    StoryRequestStatus,
    StoryRequestView,
)
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
from cyo_adventure.db.models import ChildProfile, StoryRequest
from cyo_adventure.generation.queue import enqueue_generation
from cyo_adventure.moderation.report import Verdict
from cyo_adventure.story_requests import service
from cyo_adventure.story_requests.screening import screen_request_text

if TYPE_CHECKING:
    import uuid

router = APIRouter(prefix="/api/v1", tags=["story-requests"])

_log = logging.getLogger(__name__)

_VALID_STATUSES: frozenset[str] = frozenset(
    {"pending", "approved", "declined", "blocked"}
)


def _enqueue_safely(job_id: str) -> None:
    """Best-effort RQ enqueue, run as a background task after the commit.

    Mirrors api/generation.py::_enqueue_safely: the GenerationJob row is the
    durable record, so a failed enqueue is logged, not raised.

    Args:
        job_id: The UUID string of the GenerationJob row to enqueue.
    """
    # #ASSUME: external-resources: Redis may be unreachable; the row is durable,
    # so a failed enqueue is logged and a later sweep/retry can process it.
    # #VERIFY: test coverage in test_generation_api::test_enqueue_returns_202.
    try:
        enqueue_generation(job_id, settings)
    except Exception:  # noqa: BLE001 -- best-effort; the row is the source of truth
        _log.exception("enqueue_generation failed for job %s; row committed", job_id)


async def _family_child_names(ctx: Context, family_id: uuid.UUID) -> frozenset[str]:
    """Return the family's real child display names for the PII guard.

    Args:
        ctx: The request context (principal and session).
        family_id: The family whose child display names are collected.

    Returns:
        frozenset[str]: The family's child display names.
    """
    rows = await ctx.session.scalars(
        select(ChildProfile.display_name).where(ChildProfile.family_id == family_id)
    )
    return frozenset(rows.all())


def _to_view(request: StoryRequest) -> StoryRequestView:
    """Project a row to the guardian view; hide raw text for blocked rows.

    Args:
        request: The story request row.

    Returns:
        StoryRequestView: The guardian-facing projection.
    """
    # #CRITICAL: security: the raw text of a blocked (bright-line) request is
    # never surfaced; only the redacted flags cross the boundary.
    # #VERIFY: test_blocked_request_hides_raw_text.
    raw = request.moderation_flags if isinstance(request.moderation_flags, dict) else {}
    flags_raw = raw.get("flags")
    flags: list[StoryRequestFlag] = []
    if isinstance(flags_raw, list):
        for item in flags_raw:
            if not isinstance(item, dict):
                continue
            verdict = item.get("verdict")
            category = item.get("category")
            message = item.get("message")
            if (
                isinstance(verdict, str)
                and isinstance(category, str)
                and isinstance(message, str)
            ):
                flags.append(
                    StoryRequestFlag(
                        category=category,
                        verdict=Verdict(verdict),
                        message=message,
                    )
                )
    return StoryRequestView(
        id=str(request.id),
        profile_id=str(request.profile_id),
        status=cast("StoryRequestStatus", request.status),
        request_text=None if request.status == "blocked" else request.request_text,
        moderation_flags=flags,
        created_at=request.created_at,
    )


@router.post("/story-requests", status_code=201)
async def create_story_request(
    body: StoryRequestCreateBody, ctx: Context
) -> StoryRequestCreatedView:
    """Submit a child's free-text story request (guardian-scoped in R1).

    Args:
        body: The profile id and request text.
        ctx: The request context (principal and session).

    Returns:
        StoryRequestCreatedView: The new request id and post-screening status.

    Raises:
        AuthorizationError: If the caller may not act on the profile (-> 403).
        StateTransitionError: If the profile is at its pending cap (-> 409).
        ValidationError: If ``profile_id`` is not a valid UUID (-> 422).
    """
    profile_uuid = parse_uuid(body.profile_id, "profile_id")
    # #CRITICAL: security: guardian may act on any family profile, a child only
    # on its own; admin has no profiles so cannot submit. 403 on mismatch.
    # #VERIFY: test_create_rejects_cross_family_profile.
    authorize_profile(ctx.principal, profile_uuid)

    # #CRITICAL: concurrency: enforce the per-profile pending cap before insert.
    # A rare off-by-one under concurrent submits is accepted here (see
    # service.count_pending_for_profile); the cap is an abuse throttle, not a
    # correctness invariant.
    # #VERIFY: test_pending_cap_returns_409.
    pending = await service.count_pending_for_profile(ctx.session, profile_uuid)
    if pending >= service.MAX_PENDING_PER_PROFILE:
        msg = "too many pending requests for this profile"
        raise StateTransitionError(msg)

    child_names = await _family_child_names(ctx, ctx.principal.family_id)
    result = await screen_request_text(
        body.request_text,
        child_names=child_names,
        openai_key=settings.openai_api_key,
        perspective_key=settings.perspective_api_key,
    )
    status = "blocked" if result.blocked else "pending"
    flags_payload = {
        "blocked": result.blocked,
        "flags": [f.model_dump(mode="json") for f in result.flags],
    }
    request = StoryRequest(
        family_id=ctx.principal.family_id,
        profile_id=profile_uuid,
        request_text=body.request_text,
        status=status,
        moderation_flags=flags_payload,
    )
    ctx.session.add(request)
    await ctx.session.flush()
    return StoryRequestCreatedView(
        id=str(request.id), status=cast("StoryRequestStatus", status)
    )


@router.get("/story-requests")
async def list_story_requests(
    ctx: Context,
    status: str | None = None,
    profile_id: str | None = None,
) -> StoryRequestListView:
    """List story requests visible to the caller, newest first.

    Args:
        ctx: The request context (principal and session).
        status: Optional status filter (pending/approved/declined/blocked).
        profile_id: Optional profile filter (the kid status view passes this).

    Returns:
        StoryRequestListView: The visible requests.

    Raises:
        AuthorizationError: If a guardian filters on an inaccessible profile.
        ValidationError: If ``status`` or ``profile_id`` is malformed (-> 422).
    """
    stmt = select(StoryRequest).order_by(StoryRequest.created_at.desc())
    # #CRITICAL: security: admin is global; a guardian is family-scoped. A child
    # token (used directly) would also be family-scoped via family_id.
    # #VERIFY: test_guardian_lists_family_requests.
    if not ctx.principal.is_admin:
        stmt = stmt.where(StoryRequest.family_id == ctx.principal.family_id)
    if status is not None:
        if status not in _VALID_STATUSES:
            msg = "status must be pending, approved, declined, or blocked"
            raise ValidationError(msg, field="status", value=status)
        stmt = stmt.where(StoryRequest.status == status)
    if profile_id is not None:
        profile_uuid = parse_uuid(profile_id, "profile_id")
        # A guardian may only filter to a profile it can access; admin is global.
        if not ctx.principal.is_admin:
            authorize_profile(ctx.principal, profile_uuid)
        stmt = stmt.where(StoryRequest.profile_id == profile_uuid)
    rows = (await ctx.session.scalars(stmt)).all()
    return StoryRequestListView(requests=[_to_view(r) for r in rows])


async def _load_scoped_request(
    ctx: Context, request_id: str, *, for_update: bool = False
) -> StoryRequest:
    """Load a request the caller may act on, else 404 (existence hiding).

    Args:
        ctx: The request context.
        request_id: The path id.
        for_update: When True, lock the row (``SELECT ... FOR UPDATE``) for a
            read-modify-write caller (approve/decline). List/read callers
            never set this.

    Returns:
        StoryRequest: The scoped request.

    Raises:
        ResourceNotFoundError: If the request does not exist, or belongs to
            another family and the caller is not an admin (-> 404).
        ValidationError: If ``request_id`` is not a valid UUID (-> 422).
    """
    request_uuid = parse_uuid(request_id, "request_id")
    stmt = select(StoryRequest).where(StoryRequest.id == request_uuid)
    if for_update:
        # #CRITICAL: concurrency: lock the row before the pending-guard check so
        # two concurrent approve calls for the same request cannot both pass
        # service.ensure_pending and both create a Concept + GenerationJob (a
        # double paid generation). Mirrors reading.py's with_for_update pattern
        # for the same reason (read-modify-write serialization on Postgres).
        # #VERIFY: service.approve_story_request's #CRITICAL tag documents that
        # its in-memory pending guard relies on this caller-held row lock.
        stmt = stmt.with_for_update()
    request = await ctx.session.scalar(stmt)
    # #CRITICAL: security: 404-over-403 for a request outside the caller's scope
    # (existence hiding); admin is global. Diverges from generation.py's 403 by
    # design for this child-facing resource (authorization-matrix + brief item 4).
    # #VERIFY: test_approve_cross_family_is_404.
    if request is None or (
        not ctx.principal.is_admin and request.family_id != ctx.principal.family_id
    ):
        msg = f"story request '{request_id}' not found"
        raise ResourceNotFoundError(msg)
    return request


@router.post("/story-requests/{request_id}/approve")
async def approve_story_request_endpoint(
    request_id: str, ctx: Context, background_tasks: BackgroundTasks
) -> StoryRequestApprovedView:
    """Approve a pending request and enqueue generation (guardian or admin).

    Args:
        request_id: The request id from the path.
        ctx: The request context.
        background_tasks: The enqueue runs here so it fires after commit.

    Returns:
        StoryRequestApprovedView: The linked concept and generation job ids.

    Raises:
        ResourceNotFoundError: If the request is out of scope (-> 404).
        StateTransitionError: If the request is not pending (-> 409).
        AuthorizationError: If a child token reaches this endpoint (-> 403).
    """
    # #CRITICAL: security: only a guardian (own family) or an admin may approve;
    # a child principal must never approve its own request.
    # #VERIFY: authorization-matrix; a child token is rejected here.
    if not (ctx.principal.is_guardian or ctx.principal.is_admin):
        msg = "guardian or admin role required"
        raise AuthorizationError(msg)
    request = await _load_scoped_request(ctx, request_id, for_update=True)
    concept_id, job_id = await service.approve_story_request(
        ctx.session, ctx.principal, request
    )
    background_tasks.add_task(_enqueue_safely, job_id)
    return StoryRequestApprovedView(
        id=str(request.id),
        status=cast("Literal['approved']", request.status),
        concept_id=concept_id,
        job_id=job_id,
    )


@router.post("/story-requests/{request_id}/decline")
async def decline_story_request_endpoint(
    request_id: str, ctx: Context
) -> StoryRequestDeclinedView:
    """Decline a pending request (guardian own-family or admin global).

    Args:
        request_id: The request id from the path.
        ctx: The request context.

    Returns:
        StoryRequestDeclinedView: The declined request id and status.

    Raises:
        ResourceNotFoundError: If the request is out of scope (-> 404).
        StateTransitionError: If the request is not pending (-> 409).
        AuthorizationError: If a child token reaches this endpoint (-> 403).
    """
    if not (ctx.principal.is_guardian or ctx.principal.is_admin):
        msg = "guardian or admin role required"
        raise AuthorizationError(msg)
    request = await _load_scoped_request(ctx, request_id, for_update=True)
    service.decline_story_request(ctx.principal, request)
    return StoryRequestDeclinedView(
        id=str(request.id), status=cast("Literal['declined']", request.status)
    )
