"""Service layer for story-request decisions (approve, decline, pending cap).

Approve builds a ConceptBrief and creates the Concept directly, so both
guardian and admin approvals reuse one path WITHOUT touching the
guardian-only POST /concepts API gate. It no longer creates a GenerationJob;
that happens later, when an admin picks an authoring method/mechanism/model
via POST /story-requests/{id}/authoring-plan (see
story_requests/authoring_plan.py::build_authoring_plan). The caller (the
endpoint) is responsible for authorization before invoking these functions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from cyo_adventure.core.exceptions import ResourceNotFoundError, StateTransitionError
from cyo_adventure.db.models import ChildProfile, Concept, StoryRequest
from cyo_adventure.generation.pii import PiiContext, assert_prompt_pii_safe
from cyo_adventure.story_requests.brief import brief_from_request
from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.api.deps import Principal

# Max pending requests per profile before a new submission is refused (Decision 5).
MAX_PENDING_PER_PROFILE = 5


@dataclass(frozen=True, slots=True)
class ApprovalConfirmation:
    """The guardian's band/length/style confirmation captured at approval.

    One value object because the three fields are a single decision made
    together at approve time (WS-B); they are stamped onto the request as a
    unit before the brief builds.
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


async def approve_story_request(
    session: AsyncSession,
    principal: Principal,
    request: StoryRequest,
    *,
    confirmation: ApprovalConfirmation,
) -> str:
    """Approve a pending request: build a concept (no job created yet).

    Args:
        session: The request session (caller owns the transaction).
        principal: The approving guardian or admin.
        request: The pending story request.
        confirmation: The guardian's band/length/style confirmation, stamped
            onto the request before the brief builds (WS-B derivation flip).

    Returns:
        str: The new concept id.

    Raises:
        StateTransitionError: If the request is not pending (-> 409).
        ResourceNotFoundError: If the requesting profile is missing (-> 404).
        ValidationError: If the built brief still trips the PII guard (-> 422).
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
    profile: ChildProfile | None = None
    if request.profile_id is not None:
        profile = await session.get(ChildProfile, request.profile_id)
        if profile is None:
            msg = "requesting profile no longer exists"
            raise ResourceNotFoundError(msg)

    # WS-B: the guardian's confirmation is stamped onto the request BEFORE the
    # brief builds, keeping the request the single source of truth from here on.
    request.age_band = confirmation.age_band.value
    request.length = confirmation.length.value
    request.narrative_style = confirmation.narrative_style.value

    brief = brief_from_request(request, profile)
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
        forbidden=PiiContext(child_names=child_names, birthdates=frozenset()),
    )

    concept = Concept(
        family_id=request.family_id,
        brief=brief.model_dump(mode="json"),
        created_by=principal.user_id,
    )
    session.add(concept)
    await session.flush()

    request.concept_id = concept.id
    request.status = "approved"
    request.reviewed_by = principal.user_id
    request.reviewed_at = datetime.now(UTC)

    return str(concept.id)


def decline_story_request(principal: Principal, request: StoryRequest) -> None:
    """Decline a pending request (records the reviewer and timestamp).

    Args:
        principal: The declining guardian or admin.
        request: The pending story request.

    Raises:
        StateTransitionError: If the request is not pending (-> 409).
    """
    ensure_pending(request)
    request.status = "declined"
    request.reviewed_by = principal.user_id
    request.reviewed_at = datetime.now(UTC)
