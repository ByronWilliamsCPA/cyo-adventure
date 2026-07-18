"""Child and authored story-request endpoints: submit, list, approve, decline.

The kid surface runs under the guardian token in R1, so submission is
guardian-scoped (the body carries the profile_id and authorize_profile gates it).
GET /story-requests is family-scoped for EVERY caller (the surface selects the
scope, not the caller's maximal privilege); the global review queue is the
explicit admin surface GET /admin/story-requests. Approve and decline are
guardian-own-family or admin-global; a request outside the caller's scope
returns 404 (existence hiding), which deliberately diverges from
generation.py's cross-family 403 for this lower-value, child-facing resource.
Approve builds a ConceptBrief and enqueues generation through the service
layer, so it never touches the guardian-only POST /concepts gate. The
authored-create endpoint (WS-B PR 2) lets a guardian or admin submit a
pre-approved request, optionally on a child's behalf (profile_id may be null);
family_id is optional and defaults to the caller's own family, while naming a
foreign family requires the admin capability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast, get_args

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import select

from cyo_adventure.api.deps import Context, authorize_profile, parse_uuid
from cyo_adventure.api.schemas import (
    AlternativeView,
    AuthoringPlanRequest,
    AuthoringPlanResponse,
    ChildEnvelopeUsageView,
    FamilyBudgetView,
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
    CATALOG_FAMILY_ID,
    ChildProfile,
    Concept,
    Family,
    StoryRequest,
)
from cyo_adventure.events import ADMIN_ACTOR_ROLE, Actor, EventType, record_event
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

router = APIRouter(
    prefix="/api/v1", tags=["story-requests"], responses=error_responses(401, 403)
)

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


@router.post("/story-requests", status_code=201, responses=error_responses(404, 409))
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

    ADR-015 G3: a non-blocked request auto-approves through the SAME
    ``service.approve_story_request`` path a guardian's explicit click uses
    (see the call below) when the profile has pre-authorization
    (``request_auto_approve``) AND its own monthly envelope is not yet
    exhausted AND the family's monthly quota is not yet exhausted (see
    ``service.can_auto_approve``); otherwise the row rests ``pending`` as
    before. Auto-approval uses the profile's own band, a ``short`` length,
    and ``prose`` style -- it never overrides a guardian's stated
    preference, since there is no guardian input to override.

    Args:
        body: The profile id, request text, and optional series proposal or
            continuation anchor.
        ctx: The request context (principal and session).

    Returns:
        StoryRequestCreatedView: The new request id and its status after
        screening AND, when applicable, G3 auto-approval (``approved``
        rather than ``pending``).

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
    await record_event(
        ctx.session,
        Actor.from_principal(ctx.principal),
        entity_type="story_request",
        entity_id=str(request.id),
        event_type=EventType.REQUEST_CREATED,
        to_state=request.status,
        payload={"initiator_role": request.initiator_role},
    )

    # ADR-015 G3: a blocked screening never auto-approves (checked via the
    # `status == "pending"` guard: a blocked row's status is already
    # "blocked" here, never "pending"), matching "blocked-screening never
    # auto-approves" as a hard rule, not a quota/envelope outcome.
    # #CRITICAL: payment/financial: can_auto_approve re-verifies both the
    # envelope AND the family quota; approve_story_request re-verifies the
    # family quota A THIRD time (enforce_family_quota) before building the
    # concept. Belt-and-suspenders is deliberate here: this is the one path
    # where a CHILD principal (not a guardian/admin click) can cause
    # generation spend, so every layer re-checks rather than trusting an
    # earlier layer's read.
    # #VERIFY: tests/unit/test_story_requests.py::TestAutoApprove covers the
    # auto-approve-within-envelope, envelope-exhausted-falls-back-to-pending,
    # family-quota-exhausted-falls-back-to-pending, and
    # blocked-never-auto-approves cases.
    if request.status == "pending":
        family = await ctx.session.get(Family, ctx.principal.family_id)
        # #ASSUME: data-integrity: a profile's family_id is a NOT NULL FK to a
        # live family row (the auth seam already resolved ctx.principal from
        # that same family), so `family is None` should be unreachable; kept
        # as a defensive skip (fall back to pending) rather than a 500.
        if family is not None and await service.can_auto_approve(
            ctx.session, profile, family
        ):
            await service.approve_story_request(
                ctx.session,
                ctx.principal,
                request,
                confirmation=service.ApprovalConfirmation(
                    age_band=AgeBand(profile.age_band),
                    length=Length.SHORT,
                    narrative_style=NarrativeStyle.PROSE,
                ),
                auto_approved=True,
            )

    return StoryRequestCreatedView(
        id=str(request.id), status=cast("StoryRequestStatus", request.status)
    )


async def _resolve_authored_family(
    ctx: Context, body: StoryRequestAuthoredCreateBody
) -> uuid.UUID:
    """Resolve the target family for an authored request (WS-B PR 2, #173).

    ``family_id`` is optional for every adult: omitted, it resolves to the
    caller's own family for an adult with the guardian base role; omitted by an
    admin-only adult (no guardianship of their own), it means a catalog-origin
    request and resolves to the system catalog family
    (``CATALOG_FAMILY_ID``, #173). Supplied, ``family_id`` may name the caller's
    own family (harmless self-reference for a guardian) or, with the admin
    capability, any existing family (including the catalog family). Only an
    admin can ever target the catalog family, since it is nobody's own family
    and naming a non-own family requires the admin capability.

    Args:
        ctx: The request context (principal and session).
        body: The authored-create body.

    Returns:
        uuid.UUID: The resolved target family (a real family, or the system
        catalog family for an admin-only catalog-origin request).

    Raises:
        AuthorizationError: If a caller without the admin capability names
            a family other than their own (-> 403).
        ResourceNotFoundError: If an admin-named family does not exist.
        ValidationError: If ``family_id`` is supplied but malformed.
    """
    # #CRITICAL: security: a guardian without the admin capability can never
    # author into another family: naming a foreign family_id is 403 outright
    # (existence is not probed first, so this is not a family-id oracle), and
    # an omitted family_id resolves to the caller's own family. An admin-only
    # adult who omits family_id is seeding the catalog (#173): the request is
    # owned by the system catalog family, which only an admin can reach, so the
    # "catalog-origin implies admin-initiated" invariant holds without a
    # nullable family_id or a magic-UUID CHECK. The catalog family row is
    # guaranteed to exist by the seed migration (and the integration conftest),
    # so this UUID is always a valid family_id FK.
    # #VERIFY: test_admin_omitted_family_targets_catalog_family,
    # test_guardian_cannot_target_catalog_family, test_guardian_foreign_family_is_403,
    # test_guardian_may_name_own_family, test_dual_role_omitted_family_targets_own.
    if body.family_id is None:
        if not ctx.principal.is_guardian:
            return CATALOG_FAMILY_ID
        return ctx.principal.family_id
    family_uuid = parse_uuid(body.family_id, "family_id")
    if family_uuid == ctx.principal.family_id and ctx.principal.is_guardian:
        return family_uuid
    if not ctx.principal.is_admin:
        msg = "family_id is not accessible to this principal"
        raise AuthorizationError(msg, resource=body.family_id)
    family = await ctx.session.get(Family, family_uuid)
    if family is None:
        msg = "family not found"
        raise ResourceNotFoundError(msg)
    return family_uuid


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


@router.post(
    "/story-requests/authored", status_code=201, responses=error_responses(404)
)
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
        ValidationError: If a supplied ``family_id`` is malformed, the anchor
            storybook is not published or not series-linked, the body's age
            band does not match the anchor's series, or the built brief trips
            the PII backstop in ``_build_concept`` (-> 422). An admin-only
            adult omitting ``family_id`` is a catalog-origin request, not an
            error (#173).
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


def _validate_status_filter(status: str | None) -> None:
    """Reject an out-of-enum status filter with a 422-mapped error.

    Args:
        status: The raw status query parameter, or None for no filter.

    Raises:
        ValidationError: If ``status`` is outside the closed status set.
    """
    if status is not None and status not in _VALID_STATUSES:
        msg = "status must be pending, approved, declined, or blocked"
        raise ValidationError(msg, field="status", value=status)


@router.get("/story-requests")
async def list_story_requests(
    ctx: Context,
    status: str | None = None,
    profile_id: str | None = None,
) -> StoryRequestListView:
    """List the caller's own family's story requests, newest first.

    This is the guardian/kid surface: it is family-scoped for EVERY caller,
    including one holding the admin capability (the surface selects the
    scope, not the caller's maximal privilege); the global queue lives at
    ``GET /admin/story-requests``. Flag surfacing depth still follows the
    capability: an admin sees every well-formed flag on their own family's
    rows, per the invariant that thresholds only filter what guardians see.

    Args:
        ctx: The request context (principal and session).
        status: Optional status filter (pending/approved/declined/blocked).
        profile_id: Optional profile filter (the kid status view passes this).

    Returns:
        StoryRequestListView: The caller's family's requests.

    Raises:
        AuthorizationError: If a guardian filters on an inaccessible profile.
        ValidationError: If ``status`` or ``profile_id`` is malformed (-> 422).
    """
    stmt = select(StoryRequest).order_by(StoryRequest.created_at.desc())
    # #CRITICAL: security: this surface is family-scoped for every caller.
    # Before the dual-role change an admin token was global here, which
    # would silently widen a dual-role guardian's everyday list to every
    # family; the global queue is now an explicit admin surface below.
    # #VERIFY: test_guardian_lists_family_requests,
    # test_list_is_family_scoped_for_every_caller.
    stmt = stmt.where(StoryRequest.family_id == ctx.principal.family_id)
    # #CRITICAL: security: a child session is scoped to its own profile(s), never
    # the whole family. Without this, a child token listing with no profile_id
    # would read every sibling's request text (only the family filter above
    # would apply). Guardians and admins legitimately see the whole family; a
    # child's profile_ids is the singleton from its signed session claim (an
    # empty set for a profileless child, which then correctly sees nothing).
    # #VERIFY: test_child_lists_only_own_profile_requests.
    if not (ctx.principal.is_guardian or ctx.principal.is_admin):
        stmt = stmt.where(StoryRequest.profile_id.in_(ctx.principal.profile_ids))
    _validate_status_filter(status)
    if status is not None:
        stmt = stmt.where(StoryRequest.status == status)
    if profile_id is not None:
        profile_uuid = parse_uuid(profile_id, "profile_id")
        # A guardian may only filter to a profile it can access; a child is
        # already constrained to its own profile(s) above; the family WHERE
        # bounds an admin-only caller.
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


@router.get("/admin/story-requests")
async def list_story_requests_admin(
    ctx: Context,
    status: str | None = None,
    family_id: str | None = None,
) -> StoryRequestListView:
    """List story requests across every family (the admin review queue).

    The global counterpart of ``GET /story-requests``: the admin console's
    request queue reads this surface, so holding the admin capability never
    changes what the family-scoped guardian surface returns.

    Args:
        ctx: The request context (principal and session).
        status: Optional status filter (pending/approved/declined/blocked).
        family_id: Optional family filter for drilling into one family.

    Returns:
        StoryRequestListView: The matching requests, newest first, with
        every well-formed moderation flag surfaced (no threshold filtering).

    Raises:
        AuthorizationError: If the caller lacks the admin capability (-> 403).
        ValidationError: If ``status`` or ``family_id`` is malformed (-> 422).
    """
    # #CRITICAL: security: the admin capability gates the global scope; this
    # runs before any row is loaded so a non-admin gets an exact 403.
    # #VERIFY: test_authz_matrix.py pins GET /api/v1/admin/story-requests
    # as admin-only.
    if not ctx.principal.is_admin:
        msg = "admin access required"
        raise AuthorizationError(msg)
    stmt = select(StoryRequest).order_by(StoryRequest.created_at.desc())
    _validate_status_filter(status)
    if status is not None:
        stmt = stmt.where(StoryRequest.status == status)
    if family_id is not None:
        stmt = stmt.where(StoryRequest.family_id == parse_uuid(family_id, "family_id"))
    rows = (await ctx.session.scalars(stmt)).all()
    policy = await load_threshold_policy(ctx.session)
    requests = [_to_view(request, policy=policy, surface_all=True) for request in rows]
    return StoryRequestListView(requests=requests)


@router.get("/families/me/budget")
async def get_family_budget(ctx: Context) -> FamilyBudgetView:
    """Return the caller's own family's monthly story budget (ADR-015 G7/G3).

    Numbers only, no balance-display styling: the guardian/kid-facing
    balance UI is a later, separately-scoped piece (see the CLAUDE.md
    task note). ``spent_this_month`` is derived, not stored (ADR-015 G13,
    interim): a count of the family's story requests that entered
    ``approved`` in the current UTC calendar month
    (``story_requests/service.py::family_monthly_spend``), not a decremented
    ledger balance.

    Args:
        ctx: The request context (principal and session).

    Returns:
        FamilyBudgetView: The family's quota, this month's spend, remaining
        headroom (floored at 0, never negative even if a quota was lowered
        below an already-spent month), and each child's own envelope usage.

    Raises:
        AuthorizationError: If the caller is neither a guardian nor an admin
            (a child or device token; this is an adults-only surface, same
            gate as ``GET /families/me/reading-summary``) (-> 403).
        ResourceNotFoundError: If the caller's family row is missing
            (-> 404; not expected in practice, see the inline note).
    """
    # #CRITICAL: security: "me" is always the CALLER's own family_id, never a
    # client-supplied id, so there is no cross-family parameter to IDOR here;
    # mirrors reading_history.py::get_family_reading_summary's identical gate
    # and identical reasoning (an adults-only signal, not a kid-facing one).
    # #VERIFY: test_authz_matrix.py pins GET /api/v1/families/me/budget to
    # guardian/admin; tests/unit/test_story_requests.py pins the 403 for
    # child and device tokens directly.
    if not (ctx.principal.is_guardian or ctx.principal.is_admin):
        msg = "guardian or admin role required"
        raise AuthorizationError(msg)
    family = await ctx.session.get(Family, ctx.principal.family_id)
    if family is None:
        # #ASSUME: data-integrity: every authenticated guardian/admin
        # principal resolves from a User row whose family_id is a live
        # family (the auth seam itself depends on it); this branch is a
        # defensive 404, not an expected runtime path.
        msg = "family not found"
        raise ResourceNotFoundError(msg)
    quota = service.resolve_family_quota(family)
    spent = await service.family_monthly_spend(ctx.session, family.id)
    profiles = (
        await ctx.session.scalars(
            select(ChildProfile)
            .where(ChildProfile.family_id == family.id)
            .order_by(ChildProfile.created_at.asc(), ChildProfile.id.asc())
        )
    ).all()
    usage_by_profile = await service.profile_monthly_spend_by_family(
        ctx.session, family.id
    )
    children = [
        ChildEnvelopeUsageView(
            profile_id=str(profile.id),
            display_name=profile.display_name,
            request_auto_approve=profile.request_auto_approve,
            monthly_request_envelope=profile.monthly_request_envelope,
            used_this_month=usage_by_profile.get(profile.id, 0),
        )
        for profile in profiles
    ]
    return FamilyBudgetView(
        quota=quota,
        spent_this_month=spent,
        remaining=max(quota - spent, 0),
        children=children,
    )


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


@router.post(
    "/story-requests/{request_id}/approve", responses=error_responses(404, 409)
)
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


@router.post(
    "/story-requests/{request_id}/authoring-plan",
    status_code=201,
    responses=error_responses(404, 409),
)
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
        AuthoringPlanResponse: The created job id, status, matched or
        overridden skeleton (if any), every in-cell skeleton_alternatives,
        and any non-blocking eligibility/override warnings.

    Raises:
        AuthorizationError: If the caller is not an admin (-> 403).
        ResourceNotFoundError: If the request is out of scope, or its concept
            is missing (-> 404).
        StateTransitionError: If the request is not approved, or a job
            already exists for its concept (-> 409).
        ValidationError: On an invalid method/mechanism combination, an
            unrecognized skill-mechanism model, no matching skeleton, or an
            unknown skeleton_slug override (-> 422).
    """
    # #CRITICAL: security: admin-only -- a guardian may approve a request but
    # must not choose its authoring backend or model (a child token is already
    # rejected by is_guardian/is_admin below, matching the approve endpoint).
    # #VERIFY: test_guardian_forbidden, test_child_forbidden.
    if not ctx.principal.is_admin:
        msg = "admin access required"
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

    result = await build_authoring_plan(
        ctx.session,
        request,
        concept,
        body,
        # Admin-only endpoint: stamp the capacity that authorized the action,
        # not a dual-role caller's guardian base persona.
        actor=Actor.from_principal(ctx.principal, acting_role=ADMIN_ACTOR_ROLE),
    )

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
        skeleton_alternatives=[
            AlternativeView(slug=slug) for slug in result.skeleton_alternatives
        ],
        warnings=result.warnings,
    )


@router.post(
    "/story-requests/{request_id}/decline", responses=error_responses(404, 409)
)
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
    await service.decline_story_request(ctx.session, ctx.principal, request)
    return StoryRequestDeclinedView(
        id=str(request.id), status=cast("Literal['declined']", request.status)
    )
