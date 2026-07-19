"""Service layer for story-request decisions (approve, decline, pending cap).

Approve builds a ConceptBrief and creates the Concept directly, so both
guardian and admin approvals reuse one path WITHOUT touching the
guardian-only POST /concepts API gate. It no longer creates a GenerationJob;
that happens later, when an admin picks an authoring method/mechanism/model
via POST /story-requests/{id}/authoring-plan (see
story_requests/authoring_plan.py::build_authoring_plan). Authored creation
(WS-B PR 2) shares the same concept-building tail as approval: a guardian- or
admin-initiated request skips the pending queue and calls it directly. The
caller (the endpoint) is responsible for authorization before invoking these
functions.

ADR-015 budget-consent delta (G7/G13/G3): a request may not spend generation
budget (i.e. may not reach ``_build_concept``, which is the only place a
``Concept`` is created) until a guardian of its family has consented, unless
the acting principal is spending platform budget (an admin acting in the
admin capacity, see ``_bypasses_family_quota``). ``enforce_family_quota`` is
the single gate both ``approve_story_request`` (the guardian/admin approve
endpoint) and ``create_authored_request`` (the guardian/admin authored-create
endpoint) call before building a concept. There is no ledger table yet
(G13, interim): monthly spend is derived by counting rows that entered
``approved`` in the current UTC calendar month (``StoryRequest.approved_at``),
never by decrementing a stored balance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from sqlalchemy import func, select

from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    ResourceNotFoundError,
    StateTransitionError,
    ValidationError,
)
from cyo_adventure.db.models import ChildProfile, Concept, Family, Series, StoryRequest
from cyo_adventure.events import Actor, EventType, record_event
from cyo_adventure.generation.pii import PiiContext, assert_prompt_pii_safe
from cyo_adventure.story_requests.anchoring import load_anchor_context, resolve_anchor
from cyo_adventure.story_requests.brief import brief_from_request

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.api.deps import Principal
    from cyo_adventure.story_requests.screening import ScreeningResult
    from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle

# Max pending requests per profile before a new submission is refused (Decision 5).
MAX_PENDING_PER_PROFILE = 5

# ADR-011 band rule: young bands run episodic series that carry no state.
_EPISODIC_BANDS = frozenset({"3-5", "5-8"})


# ---------------------------------------------------------------------------
# ADR-015 budget-consent delta: family/child monthly spend derivation and the
# guardian-cost-gate enforcement point.
# ---------------------------------------------------------------------------


def _month_start(now: datetime) -> datetime:
    """Return the start (00:00:00 UTC) of ``now``'s calendar month.

    Args:
        now: A timezone-aware UTC instant.

    Returns:
        datetime: The first instant of that UTC calendar month.
    """
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def _approved_count_since(
    session: AsyncSession,
    *,
    since: datetime,
    family_id: uuid.UUID | None = None,
    profile_id: uuid.UUID | None = None,
) -> int:
    """Count rows that entered ``approved`` at or after ``since``.

    Args:
        session: The request session.
        since: The inclusive lower bound (a UTC calendar-month start).
        family_id: Scope to one family, or None for no family filter.
        profile_id: Scope to one profile, or None for no profile filter.

    Returns:
        int: The matching row count.
    """
    # #ASSUME: data-integrity: this is the ENTIRE spend ledger (ADR-015 G13,
    # interim): there is no separate balance/ledger table yet, so "spend" is
    # always re-derived by counting approved_at timestamps rather than by
    # reading or decrementing a stored counter. A row's approved_at is
    # stamped exactly once (_build_concept) and a request's status never
    # regresses out of "approved" (see StoryRequest.approved_at's docstring),
    # so this count is stable for a past month and monotonically
    # non-decreasing for the current one.
    # #VERIFY: tests/unit/test_story_requests.py::TestBudget pins the
    # month-boundary behavior with injected `now` values; a real ledger table
    # is tracked as a G13 follow-up once spend needs finer-grained accounting
    # (partial refunds, credits) than a monthly approval count can express.
    stmt = (
        select(func.count())
        .select_from(StoryRequest)
        .where(
            StoryRequest.status == "approved",
            StoryRequest.approved_at.is_not(None),
            StoryRequest.approved_at >= since,
        )
    )
    if family_id is not None:
        stmt = stmt.where(StoryRequest.family_id == family_id)
    if profile_id is not None:
        stmt = stmt.where(StoryRequest.profile_id == profile_id)
    total = await session.scalar(stmt)
    return int(total or 0)


async def family_monthly_spend(
    session: AsyncSession, family_id: uuid.UUID, *, now: datetime | None = None
) -> int:
    """Return a family's approved-request count for the current UTC month.

    Args:
        session: The request session.
        family_id: The family whose spend is counted.
        now: Injection point for "the current instant" (tests); defaults to
            the current UTC time.

    Returns:
        int: The family's monthly spend (ADR-015 G7/G13).
    """
    now = now or datetime.now(UTC)
    return await _approved_count_since(
        session, family_id=family_id, since=_month_start(now)
    )


async def profile_monthly_spend(
    session: AsyncSession, profile_id: uuid.UUID, *, now: datetime | None = None
) -> int:
    """Return one child's approved-request count for the current UTC month.

    Args:
        session: The request session.
        profile_id: The child profile whose spend is counted.
        now: Injection point for "the current instant" (tests); defaults to
            the current UTC time.

    Returns:
        int: The profile's monthly spend against its own envelope (ADR-015 G3).
    """
    now = now or datetime.now(UTC)
    return await _approved_count_since(
        session, profile_id=profile_id, since=_month_start(now)
    )


async def profile_monthly_spend_by_family(
    session: AsyncSession, family_id: uuid.UUID, *, now: datetime | None = None
) -> dict[uuid.UUID, int]:
    """Return ``{profile_id: approved-this-month count}`` for a whole family.

    A single bulk, grouped query rather than one ``profile_monthly_spend``
    call per child (mirrors ``api/reading_history.py::get_family_reading_summary``'s
    "one round-trip per signal, not per child" convention), backing the
    ``GET /families/me/budget`` endpoint's per-child envelope-usage list.

    Args:
        session: The request session.
        family_id: The family whose children's spend is counted.
        now: Injection point for "the current instant" (tests); defaults to
            the current UTC time.

    Returns:
        dict[uuid.UUID, int]: Profile id to its approved-this-month count. A
        profile with zero approved requests this month is simply absent (not
        a zero entry); callers should default a missing key to 0.
    """
    now = now or datetime.now(UTC)
    since = _month_start(now)
    rows = await session.execute(
        select(StoryRequest.profile_id, func.count())
        .where(
            StoryRequest.family_id == family_id,
            StoryRequest.status == "approved",
            StoryRequest.approved_at.is_not(None),
            StoryRequest.approved_at >= since,
            StoryRequest.profile_id.is_not(None),
        )
        .group_by(StoryRequest.profile_id)
    )
    # The WHERE clause above excludes a NULL profile_id, so every row's first
    # element is a real UUID; the cast narrows SQLAlchemy's positional
    # 2-column select() (which loses precise per-element typing) rather than
    # re-checking a condition already enforced in SQL.
    typed_rows = cast("list[tuple[uuid.UUID, int]]", rows.all())
    return dict(typed_rows)


def resolve_family_quota(family: Family) -> int:
    """Return a family's effective monthly quota (its override, or the platform default).

    Args:
        family: The family row.

    Returns:
        int: ``family.monthly_story_quota`` if set, else
        ``settings.default_monthly_story_quota`` (ADR-015 G7).
    """
    if family.monthly_story_quota is not None:
        return family.monthly_story_quota
    return settings.default_monthly_story_quota


def _bypasses_family_quota(principal: Principal, family_id: uuid.UUID) -> bool:
    """Whether the acting principal spends platform budget, not family budget.

    ADR-015: "Admin-initiated catalog requests bypass the family cost gate
    because they spend platform budget, not family budget." Compared by
    string value (rather than importing ``api.deps.Role``) to avoid a needless
    import into this lower-level module; ``Principal.acting_role`` already
    returns ``"admin"`` exactly when the principal is acting in the admin
    capacity for this family (a pure admin-only adult always; a dual-role
    guardian+admin only when acting OUTSIDE their own family -- see
    ``Principal.acting_role``'s docstring).

    Args:
        principal: The approving/authoring principal.
        family_id: The family the request belongs to.

    Returns:
        bool: True if this action is exempt from the family quota.
    """
    return principal.acting_role(family_id).value == "admin"


async def enforce_family_quota(
    session: AsyncSession,
    principal: Principal,
    family_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> None:
    """Raise 409 if this family's monthly spend already meets its quota.

    The single guardian-cost-gate enforcement point (ADR-015 G7): both
    ``approve_story_request`` and ``create_authored_request`` call this
    before ``_build_concept`` runs, so a blocked call creates neither a
    ``Concept`` nor (later) a ``GenerationJob``. A no-op for a principal
    acting in the admin capacity (platform-funded catalog requests bypass
    the family gate).

    Args:
        session: The request session.
        principal: The approving/authoring principal.
        family_id: The family the request belongs to.
        now: Injection point for "the current instant" (tests); defaults to
            the current UTC time.

    Raises:
        ResourceNotFoundError: If the family no longer exists.
        StateTransitionError: If the family's monthly spend already meets or
            exceeds its quota (-> 409, "monthly story budget reached").
    """
    # #CRITICAL: payment/financial: this is the guardian cost gate itself
    # (ADR-015 G7); every non-admin path that can create a Concept MUST run
    # this check first. A missed call site would let a request spend
    # generation budget with no guardian consent recorded.
    # #VERIFY: tests/unit/test_story_requests.py::TestBudget pins the block
    # (nothing created past this point) and the admin-bypass exemption;
    # tests/integration/test_story_requests_budget.py pins it end to end
    # through both the approve and authored-create HTTP endpoints.
    if _bypasses_family_quota(principal, family_id):
        return
    family = await session.get(Family, family_id)
    if family is None:
        msg = "family no longer exists"
        raise ResourceNotFoundError(msg)
    quota = resolve_family_quota(family)
    spent = await family_monthly_spend(session, family_id, now=now)
    if spent >= quota:
        msg = "monthly story budget reached"
        raise StateTransitionError(msg)


async def can_auto_approve(
    session: AsyncSession,
    profile: ChildProfile,
    family: Family,
    *,
    now: datetime | None = None,
) -> bool:
    """Whether a child's own pre-authorization envelope currently permits auto-approval.

    ADR-015 G3: pre-authorization delegates the CLICK, never the liability,
    so three independent conditions must all hold: the guardian opted this
    child in (``request_auto_approve``), gave it an envelope
    (``monthly_request_envelope`` is not None -- None means "no envelope
    set", which blocks auto-approval even when ``request_auto_approve`` is
    True, never "unlimited"), and that envelope is not yet exhausted for the
    month; AND the family's own monthly quota is not exhausted (the spend
    still draws from guardian-controlled family budget). A caller must still
    call ``enforce_family_quota`` itself when it goes on to approve: this
    function is a pre-check used to decide whether to ATTEMPT auto-approval,
    not a substitute for the enforcement point.

    Args:
        session: The request session.
        profile: The requesting child's profile.
        family: The profile's family.
        now: Injection point for "the current instant" (tests); defaults to
            the current UTC time.

    Returns:
        bool: True if a fresh request for this profile may be auto-approved
        right now.
    """
    # #ASSUME: concurrency: this is a read-then-decide check with no row
    # lock; a rare concurrent double-submit could both pass this pre-check
    # and both then call approve_story_request, spending one extra unit of
    # envelope/quota (the same class of benign off-by-one already accepted
    # by count_pending_for_profile above). Auto-approval is a convenience
    # path with a human-set ceiling behind it (the guardian's own envelope
    # choice), not a hard financial ledger, so this is accepted for R1.
    # #VERIFY: tests/unit/test_story_requests.py::TestBudget covers the
    # single-request decision matrix; a stricter guarantee would need a
    # partial unique index or advisory lock, deferred as unnecessary here.
    if not profile.request_auto_approve or profile.monthly_request_envelope is None:
        return False
    now = now or datetime.now(UTC)
    since = _month_start(now)
    profile_spent = await _approved_count_since(
        session, profile_id=profile.id, since=since
    )
    if profile_spent >= profile.monthly_request_envelope:
        return False
    quota = resolve_family_quota(family)
    family_spent = await _approved_count_since(
        session, family_id=family.id, since=since
    )
    return family_spent < quota


@dataclass(frozen=True, slots=True)
class ApprovalConfirmation:
    """The author's band/length/style choice, stamped onto the request.

    One value object because the three fields are a single decision made
    together (WS-B); they are stamped onto the request as a unit before the
    brief builds. Captured at approve time for the guardian-approval flow,
    and at creation time for authored requests (WS-B PR 2), which are
    pre-approved and never pass through the pending queue.
    """

    age_band: AgeBand
    length: Length
    narrative_style: NarrativeStyle


def ensure_pending(request: StoryRequest) -> None:
    """Raise a 409-mapped error if the request is not awaiting a decision.

    Args:
        request: The story request being approved or declined.

    Raises:
        StateTransitionError: If ``status`` is not ``"pending"``.
    """
    if request.status != "pending":
        msg = f"story request is '{request.status}', not pending"
        raise StateTransitionError(msg)


async def count_pending_for_profile(session: AsyncSession, profile_id: object) -> int:
    """Return the number of pending requests for a profile.

    Args:
        session: The request session.
        profile_id: The child profile id.

    Returns:
        int: Count of ``pending`` rows for the profile.
    """
    # #CRITICAL: concurrency: two concurrent submits could both read count=N-1
    # and both insert (a benign one-over race). The cap is an abuse throttle,
    # not a correctness invariant, so an occasional off-by-one is acceptable.
    # #VERIFY: a strict guarantee would need a partial unique index or advisory
    # lock; deferred as unnecessary for R1.
    total = await session.scalar(
        select(func.count())
        .select_from(StoryRequest)
        .where(
            StoryRequest.profile_id == profile_id,
            StoryRequest.status == "pending",
        )
    )
    return int(total or 0)


async def create_series(
    session: AsyncSession,
    principal: Principal,
    *,
    title: str,
    family_id: uuid.UUID,
    age_band: str,
) -> Series:
    """Create a series row (guardian ratification or authored creation).

    Args:
        session: The request session (caller owns the transaction).
        principal: The ratifying guardian or admin.
        title: The screened series title.
        family_id: The owning family (NOT NULL, decision B3).
        age_band: The band every book in the series will target;
            ``carries_state`` derives from it (ADR-011: episodic for 3-5 and
            5-8, state-carry for higher bands).

    Returns:
        Series: The flushed row (id assigned).
    """
    series = Series(
        family_id=family_id,
        title=title,
        age_band=age_band,
        carries_state=age_band not in _EPISODIC_BANDS,
        created_by=principal.user_id,
    )
    session.add(series)
    await session.flush()
    return series


async def approve_story_request(
    session: AsyncSession,
    principal: Principal,
    request: StoryRequest,
    *,
    confirmation: ApprovalConfirmation,
    series_title: str | None = None,
    auto_approved: bool = False,
    now: datetime | None = None,
) -> str:
    """Approve a pending request: build a concept (no job created yet).

    Args:
        session: The request session (caller owns the transaction).
        principal: The approving guardian or admin, OR (ADR-015 G3
            auto-approval) the requesting child's own principal when
            ``auto_approved`` is True: the guardian's pre-authorization
            (``ChildProfile.request_auto_approve`` + its envelope) is what
            delegates the click, so the initiator stamp legitimately stays
            the child.
        request: The pending story request.
        confirmation: The guardian's band/length/style confirmation, stamped
            onto the request before the brief builds (WS-B derivation flip).
        series_title: A guardian-ratified series title for a non-anchored
            request (WS-B PR 3), or None to leave the request standalone.
            Ignored (and rejected, see Raises) for an anchored (continuation)
            request, which already carries its series. The endpoint screens
            this text before calling this function.
        auto_approved: True when this call is the G3 pre-authorization path
            (api/story_requests.py::create_story_request auto-approving its
            own just-created row) rather than an explicit guardian/admin
            click; stamped onto the emitted event's payload as an audit
            marker (ADR-015: "pre-authorization delegates the click, never
            the liability").
        now: Injection point for "the current instant" (tests); defaults to
            the current UTC time. Threaded through to the family-quota check
            and the ``approved_at``/``reviewed_at`` stamps so a test can pin
            a month boundary.

    Returns:
        str: The new concept id.

    Raises:
        StateTransitionError: If the request is not pending, or the family's
            monthly story budget is already reached (-> 409, ADR-015 G7).
        ResourceNotFoundError: If the requesting profile is missing, the
            family no longer exists, or the anchor storybook is missing or
            outside the family (-> 404).
        ValidationError: If the built brief still trips the PII guard; if an
            anchored request also carries a ``series_title``; if the anchor
            storybook is no longer published; or if the confirmed age band
            does not match the anchor's series band (-> 422).
    """
    # #CRITICAL: concurrency: ensure_pending's guard is an in-memory read of the
    # ``request`` object passed in by the caller; it is not itself a lock. Two
    # concurrent approvals of the same request could both read status="pending"
    # and both create a Concept (a duplicate concept for one request) unless
    # the caller holds a row lock across the read-check-write.
    # #VERIFY: the API endpoint (api/story_requests.py::_load_scoped_request)
    # loads the row with ``.with_for_update()`` before calling this function, so
    # a second concurrent approval blocks on the row lock until the first
    # transaction commits (making its ensure_pending see the now-"approved"
    # status). Any other caller of this function must hold an equivalent lock.
    ensure_pending(request)
    # #CRITICAL: payment/financial: the guardian cost gate (ADR-015 G7) runs
    # BEFORE any series/anchor/profile work below, so a quota-blocked request
    # never creates a Series row, never re-syncs an anchor's series_id, and
    # never reaches _build_concept (no Concept, and therefore no later
    # GenerationJob, is ever created for a blocked approval).
    # #VERIFY: tests/unit/test_story_requests.py::TestBudget asserts a 409
    # AND that no Concept row exists afterward.
    await enforce_family_quota(session, principal, request.family_id, now=now)
    profile: ChildProfile | None = None
    if request.profile_id is not None:
        profile = await session.get(ChildProfile, request.profile_id)
        if profile is None:
            msg = "requesting profile no longer exists"
            raise ResourceNotFoundError(msg)

    # WS-B PR 3: series ratification. An anchored (continuation) request
    # already carries its series; the guardian's confirmed band must match the
    # series band (a mismatch would silently fork the series). A non-anchored
    # request may ratify the kid's proposal, or any guardian-chosen title.
    series_created = False
    anchor_resolved = False
    if request.anchor_storybook_id is not None:
        if series_title is not None:
            msg = "a continuation request cannot also create a new series"
            raise ValidationError(msg, field="series_title", value=series_title)
        series = await resolve_anchor(
            session,
            request.anchor_storybook_id,
            family_id=request.family_id,
            expected_band=confirmation.age_band.value,
        )
        # Keep the request authoritative for downstream generation: re-sync
        # series_id from the freshly resolved anchor rather than trusting a
        # value set at create time (which a data fix or future bug could drift
        # from the anchor's actual series). series_link uses request.series_id.
        request.series_id = series.id
        anchor_resolved = True
    elif series_title is not None:
        series = await create_series(
            session,
            principal,
            title=series_title,
            family_id=request.family_id,
            age_band=confirmation.age_band.value,
        )
        request.series_id = series.id
        series_created = True

    # WS-B: the guardian's confirmation is stamped onto the request BEFORE the
    # brief builds, keeping the request the single source of truth from here on.
    request.age_band = confirmation.age_band.value
    request.length = confirmation.length.value
    request.narrative_style = confirmation.narrative_style.value

    return await _build_concept(
        session,
        principal,
        request,
        profile,
        emit_approved_event=True,
        series_created=series_created,
        anchor_resolved=anchor_resolved,
        auto_approved=auto_approved,
        now=now,
    )


async def _build_concept(
    session: AsyncSession,
    principal: Principal,
    request: StoryRequest,
    profile: ChildProfile | None,
    *,
    emit_approved_event: bool = False,
    series_created: bool = False,
    anchor_resolved: bool = False,
    auto_approved: bool = False,
    now: datetime | None = None,
) -> str:
    """Build the brief, run the PII backstop, persist the Concept, approve.

    Shared tail of guardian approval and authored creation: both end with the
    request ``approved``, ``reviewed_by``/``approved_at`` stamped, and a
    Concept linked. An anchored request gets its soft-continuation context
    loaded here too, so both entry points produce the same anchor-aware brief.
    Both entry points MUST call ``enforce_family_quota`` before reaching this
    function (ADR-015 G7): this is the sole place a ``Concept`` (and,
    therefore, the eventual generation spend) is created, so it is the
    consent seam.

    ``emit_approved_event`` is True only for the guardian/admin approval path
    (``approve_story_request``): an authored request is pre-approved at
    creation and never makes a pending-to-approved transition, so it emits a
    ``request_created`` event only (see ``create_authored_request``), not a
    second ``request_approved`` event for the same row.

    ``auto_approved`` marks the emitted event's payload for the ADR-015 G3
    pre-authorization path (ignored when ``emit_approved_event`` is False,
    since an authored request emits no approval event to mark).
    """
    anchor_context = None
    if request.anchor_storybook_id is not None:
        anchor_context = await load_anchor_context(session, request.anchor_storybook_id)
    brief = brief_from_request(request, profile, anchor_context=anchor_context)
    # #CRITICAL: security: belt-and-suspenders PII backstop on the assembled
    # brief before persisting a concept; the raw text was already screened at
    # submission, so this only trips on a defect.
    # #VERIFY: story_requests/screening.py blocks a PII request at POST.
    child_names = frozenset(
        (
            await session.scalars(
                select(ChildProfile.display_name).where(
                    ChildProfile.family_id == request.family_id
                )
            )
        ).all()
    )
    assert_prompt_pii_safe(
        brief.model_dump_json(),
        forbidden=PiiContext(child_names=child_names),
    )

    concept = Concept(
        family_id=request.family_id,
        brief=brief.model_dump(mode="json"),
        created_by=principal.user_id,
    )
    session.add(concept)
    await session.flush()

    stamp = now or datetime.now(UTC)
    request.concept_id = concept.id
    request.status = "approved"
    request.reviewed_by = principal.user_id
    request.reviewed_at = stamp
    # #CRITICAL: payment/financial: approved_at is the sole timestamp
    # ADR-015's monthly spend derivation (family_monthly_spend/
    # profile_monthly_spend) reads; stamped exactly once, here, on the one
    # code path that ever transitions a request into "approved".
    # #VERIFY: tests/unit/test_story_requests.py asserts approved_at is set
    # on both the guardian-approve and authored-create paths.
    request.approved_at = stamp

    if emit_approved_event:
        # Stamp the capacity that authorized the approval: a dual-role adult
        # approving another family's request can only be acting as admin.
        await record_event(
            session,
            Actor.from_principal(
                principal,
                acting_role=principal.acting_role(request.family_id).value,
            ),
            entity_type="story_request",
            entity_id=str(request.id),
            event_type=EventType.REQUEST_APPROVED,
            from_state="pending",
            to_state="approved",
            payload={
                "series_created": series_created,
                "anchor_resolved": anchor_resolved,
                "series_id": str(request.series_id) if request.series_id else None,
                # ADR-015 G3: True marks this REQUEST_APPROVED event as a
                # pre-authorization auto-approval (a guardian's standing
                # envelope, not a fresh explicit click); reusing the existing
                # event type with a payload marker rather than adding a new
                # EventType/CHECK-constraint migration for it.
                "auto_approved": auto_approved,
            },
        )

    return str(concept.id)


async def create_authored_request(
    session: AsyncSession,
    principal: Principal,
    *,
    family_id: uuid.UUID,
    profile: ChildProfile | None,
    request_text: str,
    confirmation: ApprovalConfirmation,
    screening: ScreeningResult,
    series_id: uuid.UUID | None = None,
    anchor_storybook_id: str | None = None,
    now: datetime | None = None,
) -> tuple[StoryRequest, str | None]:
    """Create a guardian- or admin-initiated request, pre-approved (WS-B PR 2).

    The caller (the endpoint) has already authorized the principal, resolved
    the target family, validated the optional profile, and screened the text.
    A blocked screening persists a ``blocked`` row with no concept; otherwise
    the guardian cost gate runs (ADR-015 G7: a guardian-authored request
    counts against the family's quota exactly like an approved one; an
    admin-authored one bypasses it, see ``enforce_family_quota``) and, if it
    passes, the row is approved and its Concept built in the same
    transaction.

    Args:
        session: The request session (caller owns the transaction).
        principal: The authoring guardian or admin.
        family_id: The resolved target family (the principal's own family for
            guardians; the admin-chosen family for admins, decision B3).
        profile: The validated target child profile, or None.
        request_text: The already-screened request text.
        confirmation: The author's band/length/style, stamped at creation.
        screening: The screening outcome for ``request_text``.
        series_id: The series this authored request joins, or None (WS-B
            PR 3). Endpoint-resolved: the endpoint validates the anchor and
            creates the series row only for non-blocked outcomes.
        anchor_storybook_id: The continuation anchor, or None. Also
            endpoint-resolved, for the same reason.
        now: Injection point for "the current instant" (tests); defaults to
            the current UTC time.

    Returns:
        tuple[StoryRequest, str | None]: The persisted row and the new concept
            id (None when the request was blocked or the family's monthly
            story budget was already reached).

    Raises:
        StateTransitionError: If the family's monthly story budget is already
            reached (-> 409, ADR-015 G7). Nothing is committed for this
            outcome: the request's own unit-of-work
            (``api/deps.py::get_db_session``) rolls back the whole
            transaction on any raised exception, so a quota-blocked authored
            request never persists, unlike a guardian-authored request that
            reaches ``pending`` through the create+approve two-step.
        ValidationError: If the built brief trips the PII backstop (-> 422).
    """
    # #CRITICAL: security: initiator_role is derived from the authenticated
    # principal, never from the request body, so a guardian cannot mint an
    # admin-attributed row (and vice versa). The stamp records the capacity
    # that authorized the write: a dual-role adult authoring into a foreign
    # family is stamped "admin", into their own family "guardian".
    # #VERIFY: test_story_requests_authored.py asserts the persisted role per
    # token; api/schemas.py::StoryRequestAuthoredCreateBody forbids the field.
    # #ASSUME: concurrency: two concurrent authored submits (a retry, a second
    # tab, or a direct API call) can each persist an approved row plus Concept;
    # there is no idempotency key, and MAX_PENDING_PER_PROFILE does not apply
    # because authored rows never rest in "pending". Accepted for trusted
    # guardian/admin actors: the blast radius is duplicate admin-queue rows and
    # duplicate screening calls, not duplicate story generation (generation is
    # enqueued by the separate authoring-plan step).
    # #VERIFY: RequestStoryForm.tsx's submit guard is the only client-side
    # mitigation; add a server-side idempotency key before exposing this path
    # to less-trusted roles or higher volumes.
    request = StoryRequest(
        family_id=family_id,
        profile_id=profile.id if profile is not None else None,
        request_text=request_text,
        status="blocked" if screening.blocked else "pending",
        moderation_flags={
            "blocked": screening.blocked,
            "flags": [f.model_dump(mode="json") for f in screening.flags],
        },
        age_band=confirmation.age_band.value,
        length=confirmation.length.value,
        narrative_style=confirmation.narrative_style.value,
        initiator_role=principal.acting_role(family_id).value,
        series_id=series_id,
        anchor_storybook_id=anchor_storybook_id,
    )
    session.add(request)
    await session.flush()
    await record_event(
        session,
        Actor.from_principal(principal, acting_role=request.initiator_role),
        entity_type="story_request",
        entity_id=str(request.id),
        event_type=EventType.REQUEST_CREATED,
        to_state=request.status,
        payload={"initiator_role": request.initiator_role},
    )
    if screening.blocked:
        return request, None
    # #CRITICAL: payment/financial: the guardian cost gate (ADR-015 G7) runs
    # here too, not only in approve_story_request: an authored request skips
    # the pending queue but a guardian-authored one still spends FAMILY
    # budget, so it must clear the same quota check before _build_concept
    # ever creates a Concept. An admin-authored request bypasses it (platform
    # budget), exactly like the approve path (see _bypasses_family_quota).
    # #VERIFY: tests/integration/test_story_requests_authored.py pins the
    # guardian-over-quota 409 and the admin-bypass pass-through.
    await enforce_family_quota(session, principal, family_id, now=now)
    concept_id = await _build_concept(session, principal, request, profile, now=now)
    return request, concept_id


async def decline_story_request(
    session: AsyncSession, principal: Principal, request: StoryRequest
) -> None:
    """Decline a pending request and record the transition.

    Args:
        session: The request session (caller owns the transaction).
        principal: The declining guardian or admin.
        request: The pending story request.

    Raises:
        StateTransitionError: If the request is not pending (-> 409).
    """
    # #CRITICAL: security: only the guardian's own family or an admin may decline;
    # the endpoint enforces this before calling (api/story_requests.py).
    # #VERIFY: covered by existing decline authorization tests.
    ensure_pending(request)
    request.status = "declined"
    request.reviewed_by = principal.user_id
    request.reviewed_at = datetime.now(UTC)
    await record_event(
        session,
        Actor.from_principal(
            principal, acting_role=principal.acting_role(request.family_id).value
        ),
        entity_type="story_request",
        entity_id=str(request.id),
        event_type=EventType.REQUEST_DECLINED,
        from_state="pending",
        to_state="declined",
    )
