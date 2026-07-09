"""Child and authored story-request endpoints: submit, list, approve, decline.

The kid surface runs under the guardian token in R1, so submission is
guardian-scoped (the body carries the profile_id and authorize_profile gates it).
List is family-scoped for a guardian (optional profile filter) and global for an
admin. Approve and decline are guardian-own-family or admin-global; a request
outside the caller's scope returns 404 (existence hiding), which deliberately
diverges from generation.py's cross-family 403 for this lower-value, child-facing
resource. Approve builds a ConceptBrief and enqueues generation through the
service layer, so it never touches the guardian-only POST /concepts gate. The
authored-create endpoint (WS-B PR 2) lets a guardian or admin submit a
pre-approved request, optionally on a child's behalf (profile_id may be null),
targeting their own family (guardian) or a family named by id (admin).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast, get_args

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import select

from cyo_adventure.api.deps import Context, authorize_profile, parse_uuid
from cyo_adventure.api.schemas import (
    AuthoringPlanRequest,
    AuthoringPlanResponse,
    JobStatusLiteral,
    StoryRequestApproveBody,
    StoryRequestApprovedView,
    StoryRequestAuthoredCreateBody,
    StoryRequestAuthoredCreatedView,
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
from cyo_adventure.db.models import ChildProfile, Concept, Family, StoryRequest
from cyo_adventure.generation.queue import enqueue_generation
from cyo_adventure.moderation.report import Verdict
from cyo_adventure.moderation.thresholds import ThresholdPolicy, load_threshold_policy
from cyo_adventure.story_requests import service
from cyo_adventure.story_requests.anchoring import resolve_anchor
from cyo_adventure.story_requests.authoring_plan import build_authoring_plan
from cyo_adventure.story_requests.screening import screen_request_text
from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle

if TYPE_CHECKING:
    import uuid

router = APIRouter(prefix="/api/v1", tags=["story-requests"])

_log = logging.getLogger(__name__)

_VALID_STATUSES: frozenset[str] = frozenset(get_args(StoryRequestStatus))


def _enqueue_safely(job_id: str) -> None:
    """Best-effort RQ enqueue, run as a background task after the commit.

    Mirrors api/generation.py::_enqueue_safely: the GenerationJob row is the
    durable record, so a failed enqueue is logged, not raised.

    Args:
        job_id: The UUID string of the GenerationJob row to enqueue.
    """
    # #ASSUME: external-resources: Redis may be unreachable; the row is durable,
    # so a failed enqueue is logged, not raised. No automatic reconciler
    # re-enqueues stale queued rows yet, so recovery from a lost enqueue is
    # currently manual.
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


@dataclass(frozen=True, slots=True)
class _FlagContext:
    """Per-request state needed to parse and threshold-filter one flag.

    Bundles the four call-site-invariant values that :func:`_parse_flag`
    would otherwise need as separate keyword arguments, keeping it under the
    project's max-args lint limit.

    Attributes:
        request_id: The owning story request's id, used only for the
            out-of-enum-verdict warning log.
        age_band: The request's age band (WS-B: request-sourced, backfilled
            for historical rows), used to resolve the surfacing threshold
            for each flag.
        policy: The loaded threshold policy (surfaces flag+above by default).
        surface_all: When True (admin caller), every well-formed flag is
            returned regardless of the age-band/category threshold: admins
            see every finding, per the design invariant that thresholds only
            filter what guardians see. When False (guardian caller), a flag
            below the resolved threshold is dropped.
    """

    request_id: uuid.UUID
    age_band: str
    policy: ThresholdPolicy
    surface_all: bool


def _parse_flag(item: object, ctx: _FlagContext) -> StoryRequestFlag | None:
    """Parse and threshold-filter one raw moderation-flag entry.

    Args:
        item: One raw entry from ``moderation_flags["flags"]`` (untyped
            JSONB), expected to be a dict with string ``verdict``,
            ``category``, and ``message`` keys.
        ctx: The owning request's id, age band, threshold policy, and
            admin-bypass flag; see :class:`_FlagContext`.

    Returns:
        StoryRequestFlag | None: The parsed flag, or None if the entry is
        malformed, carries a verdict outside the Verdict enum, or is dropped
        by the threshold filter.
    """
    if not isinstance(item, dict):
        return None
    verdict = item.get("verdict")
    category = item.get("category")
    message = item.get("message")
    if not (
        isinstance(verdict, str)
        and isinstance(category, str)
        and isinstance(message, str)
    ):
        return None
    # #ASSUME: data-integrity: moderation_flags is unconstrained JSONB, so
    # a stored verdict outside the Verdict enum (legacy row or manual edit)
    # must not 500 the whole list; skip the malformed flag and log.
    # #VERIFY: test_to_view_skips_malformed_verdict.
    try:
        parsed_verdict = Verdict(verdict)
    except ValueError:
        _log.warning(
            "story_request %s has out-of-enum verdict %r; skipping flag",
            ctx.request_id,
            verdict,
        )
        return None
    # Stored request flags carry no score, so an admin-configured
    # min_score override never gates story-request flags (only
    # storybook flags carry real classifier scores); verdict-level
    # filtering only.
    # #CRITICAL: security: thresholds filter what a GUARDIAN sees;
    # an admin bypasses this check (surface_all) and sees every
    # well-formed flag, per the design invariant "admins see every
    # finding regardless of threshold."
    # #VERIFY: test_admin_sees_all_flags_guardian_sees_filtered.
    if not ctx.surface_all and not ctx.policy.surfaces(
        age_band=ctx.age_band,
        category=category,
        verdict=parsed_verdict,
        score=None,
    ):
        return None
    return StoryRequestFlag(category=category, verdict=parsed_verdict, message=message)


def _to_view(
    request: StoryRequest,
    *,
    policy: ThresholdPolicy,
    surface_all: bool,
) -> StoryRequestView:
    """Project a row to the caller's view; hide raw text for blocked rows.

    Args:
        request: The story request row.
        policy: The loaded threshold policy (surfaces flag+above by default).
        surface_all: When True (admin caller), every well-formed flag is
            included regardless of the age-band/category threshold: admins
            see every finding, per the design invariant that thresholds only
            filter what guardians see. When False (guardian caller), flags
            below the resolved threshold are dropped.

    Returns:
        StoryRequestView: The caller-facing projection. For a guardian,
        filtered to flags that meet the age-band/category threshold; for an
        admin, unfiltered.
    """
    # #CRITICAL: security: the raw text of a blocked (bright-line) request is
    # never surfaced; only the redacted flags cross the boundary.
    # #VERIFY: test_blocked_request_hides_raw_text.
    raw = request.moderation_flags if isinstance(request.moderation_flags, dict) else {}
    flags_raw = raw.get("flags")
    flags: list[StoryRequestFlag] = []
    if isinstance(flags_raw, list):
        ctx = _FlagContext(
            request_id=request.id,
            age_band=request.age_band,
            policy=policy,
            surface_all=surface_all,
        )
        for item in flags_raw:
            flag = _parse_flag(item, ctx)
            if flag is not None:
                flags.append(flag)
    return StoryRequestView(
        id=str(request.id),
        profile_id=str(request.profile_id) if request.profile_id is not None else None,
        status=cast("StoryRequestStatus", request.status),
        request_text=None if request.status == "blocked" else request.request_text,
        moderation_flags=flags,
        created_at=request.created_at,
        initiator_role=cast(
            "Literal['child', 'guardian', 'admin']", request.initiator_role
        ),
        age_band=AgeBand(request.age_band),
        length=Length(request.length) if request.length is not None else None,
        narrative_style=NarrativeStyle(request.narrative_style),
        series_id=str(request.series_id) if request.series_id is not None else None,
        proposed_series_title=(
            None if request.status == "blocked" else request.proposed_series_title
        ),
        anchor_storybook_id=request.anchor_storybook_id,
    )


@router.post("/story-requests", status_code=201)
async def create_story_request(
    body: StoryRequestCreateBody, ctx: Context
) -> StoryRequestCreatedView:
    """Submit a child's free-text story request (guardian-scoped in R1).

    ``body.proposed_series_title`` and ``body.anchor_storybook_id`` are
    mutually exclusive (schema XOR): the former proposes a brand-new,
    unratified series name (screened alongside the request text and stored
    for a guardian to ratify or decline at approval); the latter asks for a
    soft continuation anchored to an existing, published, series-linked
    storybook in the caller's own family and profile band (WS-B PR 3).

    Args:
        body: The profile id, request text, and optional series proposal or
            continuation anchor.
        ctx: The request context (principal and session).

    Returns:
        StoryRequestCreatedView: The new request id and post-screening status.

    Raises:
        AuthorizationError: If the caller may not act on the profile (-> 403).
        ResourceNotFoundError: If the profile no longer exists, or the anchor
            storybook is missing or outside the caller's family (-> 404).
        StateTransitionError: If the profile is at its pending cap (-> 409).
        ValidationError: If ``profile_id`` is not a valid UUID; if the anchor
            storybook is not published or not series-linked; or if the
            profile's age band does not match the anchor's series (-> 422).
    """
    profile_uuid = parse_uuid(body.profile_id, "profile_id")
    # #CRITICAL: security: guardian may act on any family profile, a child only
    # on its own; admin has no profiles so cannot submit. 403 on mismatch.
    # #VERIFY: test_create_rejects_cross_family_profile.
    authorize_profile(ctx.principal, profile_uuid)

    # #CRITICAL: data integrity: age_band has no column default (WS-B); every
    # creation path must stamp it explicitly from the requesting profile so a
    # missed path fails loudly at flush rather than persisting a drifted band.
    # #VERIFY: test_story_requests_api.py create-flow tests flush this row.
    profile = await ctx.session.get(ChildProfile, profile_uuid)
    if profile is None:
        msg = "profile not found"
        raise ResourceNotFoundError(msg)

    # #CRITICAL: concurrency: enforce the per-profile pending cap before insert.
    # A rare off-by-one under concurrent submits is accepted here (see
    # service.count_pending_for_profile); the cap is an abuse throttle, not a
    # correctness invariant.
    # #VERIFY: test_pending_cap_returns_409.
    pending = await service.count_pending_for_profile(ctx.session, profile_uuid)
    if pending >= service.MAX_PENDING_PER_PROFILE:
        msg = "too many pending requests for this profile"
        raise StateTransitionError(msg)

    series_id: uuid.UUID | None = None
    if body.anchor_storybook_id is not None:
        # #CRITICAL: security: the anchor is validated against the caller's own
        # family and the profile's band before anything persists; a kid cannot
        # anchor onto another family's book or fork a series onto a new band.
        # #VERIFY: test_series_requests.py anchor matrix (404/422 cases).
        series = await resolve_anchor(
            ctx.session,
            body.anchor_storybook_id,
            family_id=ctx.principal.family_id,
            expected_band=profile.age_band,
        )
        series_id = series.id

    child_names = await _family_child_names(ctx, ctx.principal.family_id)
    screen_input = (
        f"{body.proposed_series_title}\n{body.request_text}"
        if body.proposed_series_title is not None
        else body.request_text
    )
    result = await screen_request_text(
        screen_input,
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
        age_band=profile.age_band,
        initiator_role="child",
        series_id=series_id,
        anchor_storybook_id=body.anchor_storybook_id,
        proposed_series_title=body.proposed_series_title,
    )
    ctx.session.add(request)
    await ctx.session.flush()
    return StoryRequestCreatedView(
        id=str(request.id), status=cast("StoryRequestStatus", status)
    )


async def _resolve_authored_family(
    ctx: Context, body: StoryRequestAuthoredCreateBody
) -> uuid.UUID:
    """Resolve the target family for an authored request (WS-B PR 2).

    Args:
        ctx: The request context (principal and session).
        body: The authored-create body.

    Returns:
        uuid.UUID: The principal's own family for a guardian, or the body's
        named family for an admin.

    Raises:
        ResourceNotFoundError: If an admin-named family does not exist.
        ValidationError: If a guardian supplies ``family_id``, an admin omits
            it, or the supplied id is malformed.
    """
    # #CRITICAL: security: the target family comes from the principal for
    # guardians and from the body for admins (decision B3); a guardian naming
    # any family_id is rejected outright so cross-family authoring is
    # impossible even with a correct-looking id.
    # #VERIFY: test_guardian_must_omit_family_id, test_admin_requires_family_id.
    if ctx.principal.is_admin:
        if body.family_id is None:
            msg = "family_id is required for admin-initiated requests"
            raise ValidationError(msg, field="family_id", value=None)
        family_uuid = parse_uuid(body.family_id, "family_id")
        family = await ctx.session.get(Family, family_uuid)
        if family is None:
            msg = "family not found"
            raise ResourceNotFoundError(msg)
        return family_uuid
    if body.family_id is not None:
        msg = "family_id is server-derived for guardians"
        raise ValidationError(msg, field="family_id", value=body.family_id)
    return ctx.principal.family_id


async def _resolve_authored_profile(
    ctx: Context, body: StoryRequestAuthoredCreateBody, family_uuid: uuid.UUID
) -> ChildProfile | None:
    """Validate and load the optional target profile for an authored request.

    Args:
        ctx: The request context.
        body: The authored-create body.
        family_uuid: The resolved target family.

    Returns:
        ChildProfile | None: The validated profile, or None for a request
        with no target child.

    Raises:
        AuthorizationError: If a guardian names an inaccessible profile, or
            the profile does not belong to the target family.
        ResourceNotFoundError: If the named profile does not exist.
    """
    if body.profile_id is None:
        return None
    profile_uuid = parse_uuid(body.profile_id, "profile_id")
    # #CRITICAL: security: guardians are checked against their own profile
    # set BEFORE any lookup (authorize_profile), so a guardian cannot use
    # this endpoint to distinguish "exists in another family" (403) from
    # "does not exist" (404); a nonexistent id and another family's id are
    # both 403 for guardians. Admins have global visibility, so the
    # existence-then-membership order below is not an oracle for them, and
    # the family check also covers the admin-named family (IDOR).
    # #VERIFY: test_guardian_rejects_cross_family_profile,
    # test_guardian_unknown_profile_is_403,
    # test_admin_cross_family_profile_is_403.
    if not ctx.principal.is_admin:
        authorize_profile(ctx.principal, profile_uuid)
    profile = await ctx.session.get(ChildProfile, profile_uuid)
    if profile is None:
        msg = "profile not found"
        raise ResourceNotFoundError(msg)
    if profile.family_id != family_uuid:
        msg = "profile does not belong to the target family"
        raise AuthorizationError(msg, resource=str(profile_uuid))
    return profile


@router.post("/story-requests/authored", status_code=201)
async def create_authored_story_request(
    body: StoryRequestAuthoredCreateBody, ctx: Context
) -> StoryRequestAuthoredCreatedView:
    """Create a pre-approved request as a guardian or admin (WS-B PR 2).

    The author sets band, length, and style at creation, so the guardian
    approval step is skipped: the row is created ``approved`` with its Concept
    built immediately, ready for the admin authoring-plan step. Screening
    still runs; a blocked outcome persists a ``blocked`` row with no concept.

    ``body.series_title`` and ``body.anchor_storybook_id`` are mutually
    exclusive (schema XOR, WS-B PR 3): the former creates a brand-new series
    immediately, but only for a non-blocked outcome, so a blocked row never
    leaves an orphan series; the latter continues an existing, published,
    series-linked storybook in the target family and body's age band.

    Args:
        body: The request text, band/length/style, optional profile, and
            (admin-only) target family, plus an optional series title or
            continuation anchor.
        ctx: The request context (principal and session).

    Returns:
        StoryRequestAuthoredCreatedView: Id, post-screening status, concept id.

    Raises:
        AuthorizationError: If the caller is a child, or the profile does not
            belong to the target family (-> 403).
        ResourceNotFoundError: If the named family, profile, or anchor
            storybook is missing, or the anchor is outside the target family
            (-> 404).
        ValidationError: If a guardian supplies ``family_id``, an admin omits
            it, a UUID is malformed, the anchor storybook is not published or
            not series-linked, the body's age band does not match the
            anchor's series, or the built brief trips the PII backstop in
            ``_build_concept`` (-> 422).
    """
    # #CRITICAL: security: children cannot author pre-approved requests; the
    # authored path bypasses guardian review by design, so the role gate is the
    # only thing standing between a child token and an unreviewed concept.
    # #VERIFY: test_story_requests_authored.py::test_child_cannot_author.
    if not (ctx.principal.is_guardian or ctx.principal.is_admin):
        msg = "guardian or admin role required"
        raise AuthorizationError(msg)

    family_uuid = await _resolve_authored_family(ctx, body)
    profile = await _resolve_authored_profile(ctx, body, family_uuid)

    series_id: uuid.UUID | None = None
    if body.anchor_storybook_id is not None:
        anchor_series = await resolve_anchor(
            ctx.session,
            body.anchor_storybook_id,
            family_id=family_uuid,
            expected_band=body.age_band.value,
        )
        series_id = anchor_series.id

    child_names = await _family_child_names(ctx, family_uuid)
    screen_input = (
        f"{body.series_title}\n{body.request_text}"
        if body.series_title is not None
        else body.request_text
    )
    result = await screen_request_text(
        screen_input,
        child_names=child_names,
        openai_key=settings.openai_api_key,
        perspective_key=settings.perspective_api_key,
    )

    if not result.blocked and body.series_title is not None:
        series = await service.create_series(
            ctx.session,
            ctx.principal,
            title=body.series_title,
            family_id=family_uuid,
            age_band=body.age_band.value,
        )
        series_id = series.id

    request, concept_id = await service.create_authored_request(
        ctx.session,
        ctx.principal,
        family_id=family_uuid,
        profile=profile,
        request_text=body.request_text,
        confirmation=service.ApprovalConfirmation(
            age_band=body.age_band,
            length=body.length,
            narrative_style=body.narrative_style,
        ),
        screening=result,
        series_id=series_id,
        anchor_storybook_id=body.anchor_storybook_id,
    )
    return StoryRequestAuthoredCreatedView(
        id=str(request.id),
        status=cast("StoryRequestStatus", request.status),
        concept_id=concept_id,
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
    policy = await load_threshold_policy(ctx.session)
    requests = [
        _to_view(request, policy=policy, surface_all=ctx.principal.is_admin)
        for request in rows
    ]
    return StoryRequestListView(requests=requests)


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
    request_id: str, body: StoryRequestApproveBody, ctx: Context
) -> StoryRequestApprovedView:
    """Approve a pending request, creating its concept (guardian or admin).

    No GenerationJob is created here; an admin picks the authoring method,
    mechanism, and model afterward via POST .../authoring-plan, which is what
    creates the job (see story_requests/authoring_plan.py).

    ``body.series_title`` ratifies or edits a series for a non-anchored
    request (WS-B PR 3): supplying it creates a new series row and links the
    request to it; omitting it declines the kid's proposal (no series is
    created, and ``proposed_series_title`` remains stored on the request as
    an audit trail). An anchored (continuation) request is re-validated
    against the confirmed band and rejects a supplied ``series_title``
    outright (a continuation cannot also fork a new series).

    Args:
        request_id: The request id from the path.
        body: The guardian's band/length/style confirmation (WS-B); this
            becomes the request's stored band and length, overriding
            whatever was stamped at creation. A gamebook style below the
            teen bands (13-16, 16+) is rejected here with a 422 before the
            service layer runs. ``series_title``, if present, is screened
            here before the service layer runs, so a blocked title never
            reaches the row.
        ctx: The request context.

    Returns:
        StoryRequestApprovedView: The linked concept id.

    Raises:
        ResourceNotFoundError: If the request is out of scope (-> 404).
        StateTransitionError: If the request is not pending (-> 409).
        AuthorizationError: If a child token reaches this endpoint (-> 403).
        ValidationError: If ``series_title`` fails content screening; if an
            anchored request also carries a ``series_title``; or if the
            confirmed age band does not match the anchor's series band
            (-> 422).
    """
    # #CRITICAL: security: only a guardian (own family) or an admin may approve;
    # a child principal must never approve its own request.
    # #VERIFY: authorization-matrix; a child token is rejected here.
    if not (ctx.principal.is_guardian or ctx.principal.is_admin):
        msg = "guardian or admin role required"
        raise AuthorizationError(msg)
    request = await _load_scoped_request(ctx, request_id, for_update=True)
    if body.series_title is not None:
        child_names = await _family_child_names(ctx, request.family_id)
        title_screen = await screen_request_text(
            body.series_title,
            child_names=child_names,
            openai_key=settings.openai_api_key,
            perspective_key=settings.perspective_api_key,
        )
        if title_screen.blocked:
            # #CRITICAL: security: never echo blocked content back; the message
            # and value are both generic (same redaction as blocked requests).
            # #VERIFY: test_series_requests.py::test_approve_blocked_title_is_422.
            msg = "series title failed content screening"
            raise ValidationError(msg, field="series_title", value=None)
    concept_id = await service.approve_story_request(
        ctx.session,
        ctx.principal,
        request,
        confirmation=service.ApprovalConfirmation(
            age_band=body.age_band,
            length=body.length,
            narrative_style=body.narrative_style,
        ),
        series_title=body.series_title,
    )
    return StoryRequestApprovedView(
        id=str(request.id),
        status=cast("Literal['approved']", request.status),
        concept_id=concept_id,
    )


@router.post("/story-requests/{request_id}/authoring-plan", status_code=201)
async def create_authoring_plan(
    request_id: str,
    body: AuthoringPlanRequest,
    ctx: Context,
    background_tasks: BackgroundTasks,
) -> AuthoringPlanResponse:
    """Choose an authoring method/mechanism/model for an approved request.

    Admin-only: a guardian may approve a request but does not pick its
    authoring backend or model.

    Args:
        request_id: The request id from the path.
        body: The chosen method, mechanism, and prep model.
        ctx: The request context.
        background_tasks: The enqueue (fresh_generation only) runs here so it
            fires after commit.

    Returns:
        AuthoringPlanResponse: The created job id, status, matched skeleton
        (if any), and any non-blocking eligibility warnings.

    Raises:
        AuthorizationError: If the caller is not an admin (-> 403).
        ResourceNotFoundError: If the request is out of scope, or its concept
            is missing (-> 404).
        StateTransitionError: If the request is not approved, or a job
            already exists for its concept (-> 409).
        ValidationError: On an invalid method/mechanism combination, an
            unrecognized skill-mechanism model, or no matching skeleton
            (-> 422).
    """
    # #CRITICAL: security: admin-only -- a guardian may approve a request but
    # must not choose its authoring backend or model (a child token is already
    # rejected by is_guardian/is_admin below, matching the approve endpoint).
    # #VERIFY: test_guardian_forbidden, test_child_forbidden.
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg)

    request = await _load_scoped_request(ctx, request_id, for_update=True)
    if request.status != "approved":
        msg = f"story request is '{request.status}', not approved"
        raise StateTransitionError(msg)
    if request.concept_id is None:
        msg = f"approved story request '{request_id}' has no linked concept"
        raise ResourceNotFoundError(msg)
    concept = await ctx.session.get(Concept, request.concept_id)
    if concept is None:
        msg = f"concept for story request '{request_id}' not found"
        raise ResourceNotFoundError(msg)

    result = await build_authoring_plan(ctx.session, request, concept, body)

    if result.job.status == "queued":
        background_tasks.add_task(_enqueue_safely, str(result.job.id))

    return AuthoringPlanResponse(
        request_id=str(request.id),
        concept_id=str(concept.id),
        job_id=str(result.job.id),
        method=body.method,
        mechanism=body.mechanism,
        status=cast("JobStatusLiteral", result.job.status),
        skeleton_slug=result.skeleton_slug,
        warnings=result.warnings,
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
