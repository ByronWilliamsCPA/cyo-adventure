"""Admin re-moderation endpoint (moderation review redesign, design doc section 4 item 1).

``POST /api/v1/admin/remoderate/{storybook_id}/{version}`` re-runs the FULL
moderation pipeline (``moderation.pipeline.run_moderation_pipeline``) over one
already-published storybook version and returns the outcome synchronously.
This is the catalog-remediation entry point that lets an admin replace a
mock-moderated or otherwise stale report with a fresh one produced by the
currently configured review provider, without waiting for a guardian to
trigger it through the ordinary generation path.

Scope: PUBLISHED versions only
-------------------------------
This endpoint deliberately rejects any storybook whose status is not
``published`` (``BusinessLogicError``, 400). ``run_moderation_pipeline``'s
terminal step always calls ``publishing.service.submit`` (clean/repaired
report) or ``auto_reject`` (hard block); for a draft or needs-revision story
those calls would actually MOVE the story through the state machine, which is
a different, already-served workflow (the ordinary generation pipeline, or
``api/rescreen.py`` for a lighter-weight published-book policy sweep). Scoping
this endpoint to published-only keeps its contract to exactly one thing: "give
me a fresh moderation report for a book that already shipped," never a state
transition.

Why the pipeline's own state-transition call is caught, not avoided
---------------------------------------------------------------------
``run_moderation_pipeline`` is not modified (out of scope; owned by workstream
B2/B3 for other reasons in this concurrent effort, and a stable contract this
module deliberately does not fork). Calling it unmodified on a published book
means its own terminal ``service.submit``/``service.auto_reject`` call ALWAYS
raises ``StateTransitionError``, because ``(PUBLISHED, SUBMIT)`` and
``(PUBLISHED, AUTO_REJECT)`` are not legal hops in
``publishing/state_machine.py::LEGAL_TRANSITIONS``. That is caught here rather
than propagated: by the time it is raised, ``_persist_report`` has already
overwritten ``version_row.moderation_report`` with the fresh, merged report
(pipeline.py's own code order runs persistence before the state-transition
call), so the catch discards only the (always-illegal, for this scope) attempt
to move the book, never the freshly written report.

# #CRITICAL: security: ADR-005 (mandatory human approval) requires a
# published book to remain the guardian/admin's approved artifact until a
# human explicitly acts on it again; this endpoint must never itself flip
# status. #VERIFY: no line in this module (or the pipeline it calls, for the
# published-only scope this module allows) sets ``storybook.status``; a
# published book is BusinessLogicError-rejected before the call for any
# other status, and StateTransitionError is caught, never reraised, for the
# one status this endpoint allows through.

Residual risk: bounded auto-repair can still rewrite the published blob
--------------------------------------------------------------------------
``run_moderation_pipeline`` has one behavior this endpoint inherits and cannot
suppress without forking the pipeline (out of scope): if the fresh report has
a soft ``FLAG`` and no hard ``BLOCK``, the pipeline attempts one bounded
LLM-driven auto-repair and, if adopted, rewrites ``version_row.blob`` in
place -- the actual published story content -- with no additional human gate
beyond what the ordinary generation-time pipeline already provides. For a
book a guardian has already approved and a child may already be reading
offline, this means a re-moderation call can silently alter the text a family
has on their shelf. This is accepted, inherited pipeline behavior, not
something this endpoint adds; it is flagged here rather than worked around
because the fix (an ``allow_repair`` opt-out on the pipeline) touches
``moderation/pipeline.py``, which this task is not permitted to modify. See
the Stage D handoff report for the follow-up recommendation.
# #ASSUME: data-integrity: an admin invoking re-moderation on a published,
# previously-clean book accepts that a newly-introduced soft flag (e.g. a
# stricter model or updated policy) may trigger a silent content rewrite.
# #VERIFY: none in this module; tracked as an open follow-up, not closed here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from cyo_adventure.api.deps import Context
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    ResourceNotFoundError,
    StateTransitionError,
)
from cyo_adventure.db.models import ChildProfile, Storybook, StorybookVersion
from cyo_adventure.events import ADMIN_ACTOR_ROLE, Actor, EventType, record_event
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import build_provider
from cyo_adventure.moderation.pipeline import run_moderation_pipeline
from cyo_adventure.publishing.state_machine import Status
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.core.config import Settings

router = APIRouter(prefix="/api/v1", tags=["remoderate"])

_logger = get_logger(__name__)


def _require_admin(ctx: Context) -> None:
    """Reject non-admin callers before the request touches any row.

    Args:
        ctx: The request context (principal + session).

    Raises:
        AuthorizationError: If the caller is not an admin (403).
    """
    # #CRITICAL: security: re-moderation reads and re-classifies a published
    # book's full prose and can rewrite its content (see module docstring's
    # repair-risk note); the role gate runs before any query, mirroring
    # api/rescreen.py::_require_admin and api/approval.py::_load_admin_story.
    # #VERIFY: tests/unit/test_remoderate_unit.py::test_non_admin_rejected_with_403.
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg, required_permission="admin")


@dataclass(frozen=True, slots=True)
class RemoderateContext:
    """Bundles the request-invariant collaborators into one value.

    Keeps :func:`remoderate_storybook_version` within the project's
    4-argument function limit (``session``, ``storybook_id``, ``version``,
    ``ctx``), mirroring ``moderation/rescreen.py``'s ``_SweepContext``.
    Public (not leading-underscore), unlike ``_SweepContext``: the ops sweep
    script (``scripts/remoderate_books.py``) constructs one directly since it
    calls :func:`remoderate_storybook_version` outside the HTTP router,
    stamping ``Actor.system()`` instead of an admin principal's actor.
    """

    settings: Settings
    actor: Actor


@dataclass(frozen=True, slots=True)
class RemoderateResult:
    """One re-moderation call's outcome (service-layer value)."""

    storybook_id: str
    version: int
    status: str
    overall_verdict: str
    verdict_counts: dict[str, int]
    structural_count: int
    duration_seconds: float
    prior_reviewer_independent: bool | None


class RemoderateResultView(BaseModel):
    """A re-moderation call's outcome, on the wire."""

    storybook_id: str
    version: int
    status: str
    overall_verdict: str
    verdict_counts: dict[str, int]
    structural_count: int
    duration_seconds: float
    prior_reviewer_independent: bool | None


def _view(result: RemoderateResult) -> RemoderateResultView:
    """Adapt the service-layer :class:`RemoderateResult` to its wire view."""
    return RemoderateResultView(
        storybook_id=result.storybook_id,
        version=result.version,
        status=result.status,
        overall_verdict=result.overall_verdict,
        verdict_counts=result.verdict_counts,
        structural_count=result.structural_count,
        duration_seconds=result.duration_seconds,
        prior_reviewer_independent=result.prior_reviewer_independent,
    )


async def _family_child_names(
    session: AsyncSession, family_id: object
) -> frozenset[str]:
    """Return the real display names of a family's child profiles.

    Duplicated (not imported) from ``api/node_edit.py``'s private helper of
    the same name and shape: that function is module-private to node_edit.py
    and importing a leading-underscore name across modules is the pattern
    this codebase avoids elsewhere (see events/models.py's Protocol note on
    why it duck-types instead of importing across a similar boundary).

    Args:
        session: The request session.
        family_id: The owning family's id (the story's family, not
            necessarily the caller's, since re-moderation is a global admin
            action).

    Returns:
        frozenset[str]: Every child display name in the family, for the PII
        egress guard on the re-review and repair prompts.
    """
    rows = await session.scalars(
        select(ChildProfile.display_name).where(ChildProfile.family_id == family_id)
    )
    return frozenset(rows.all())


def _prior_reviewer_independent(report: dict[str, object] | None) -> bool | None:
    """Return the stored report's ``reviewer_independent`` marker, if present.

    Read from the STORED (pre-call) report before ``run_moderation_pipeline``
    overwrites ``version_row.moderation_report`` in place; a mock-moderated
    book's prior report carries ``reviewer_independent: False`` (design doc
    2.4's durable mock-reviewer stamp), which is the provenance signal the
    audit event (decision 4) is meant to preserve.
    """
    if report is None:
        return None
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return None
    value = cast("dict[str, object]", summary).get("reviewer_independent")
    return value if isinstance(value, bool) else None


def _summarize_report(
    report: dict[str, object] | None,
) -> tuple[str, dict[str, int], int]:
    """Derive (overall_verdict, verdict_counts, structural_count) from a persisted report.

    Reads the FRESH (post-call) persisted report's own ``summary.hard_block``/
    ``summary.soft_flag`` flags for the overall verdict, the same gating
    logic ``moderation/pipeline.py::_overall_verdict`` applies to the
    in-memory report (that function is private to pipeline.py and operates
    on a report object this module never holds, since
    ``run_moderation_pipeline`` returns nothing; the persisted dict is the
    only artifact available here).
    """
    if report is None:
        return "pass", {}, 0
    summary = cast("dict[str, object]", report.get("summary", {}))
    if summary.get("hard_block"):
        overall = "block"
    elif summary.get("soft_flag"):
        overall = "flag"
    else:
        overall = "pass"
    findings = cast("list[dict[str, object]]", report.get("findings", []))
    counts: dict[str, int] = {}
    structural = 0
    for finding in findings:
        verdict = cast("str", finding.get("verdict", "unknown"))
        counts[verdict] = counts.get(verdict, 0) + 1
        if finding.get("structural"):
            structural += 1
    return overall, counts, structural


async def remoderate_storybook_version(
    session: AsyncSession,
    storybook_id: str,
    version: int,
    ctx: RemoderateContext,
) -> RemoderateResult:
    """Re-run the moderation pipeline over one published storybook version.

    Args:
        session: The request session (caller owns the transaction).
        storybook_id: The storybook id from the path.
        version: The version number from the path.
        ctx: Settings + the audited actor.

    Returns:
        RemoderateResult: The fresh report's verdict summary; the book's
        status is guaranteed unchanged (see module docstring).

    Raises:
        ResourceNotFoundError: If the storybook or version does not exist (404).
        BusinessLogicError: If the storybook is not currently published (400).
    """
    # #CRITICAL: concurrency: loads and locks the storybook row under the same
    # SELECT ... FOR UPDATE pattern api/approval.py::_load_admin_story and
    # moderation/pipeline.py::run_moderation_pipeline both use, so a
    # concurrent approve/archive/second-re-moderate call on the same
    # storybook blocks here until this transaction commits, instead of both
    # reading a stale status and racing to write moderation_report /
    # storybook.status. run_moderation_pipeline (below) re-acquires the same
    # row lock inside the same transaction, which Postgres treats as a
    # harmless re-lock, not a self-deadlock.
    # #VERIFY: SELECT ... FOR UPDATE on Postgres;
    # tests/unit/test_remoderate_unit.py::test_locks_storybook_row_for_update
    # asserts the lock clause is present, mirroring
    # tests/unit/test_approval_unit.py::test_load_admin_story_locks_row_for_update.
    stmt = select(Storybook).where(Storybook.id == storybook_id).with_for_update()
    storybook = (await session.execute(stmt)).scalar_one_or_none()
    if storybook is None:
        msg = f"storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(
            msg, resource_type="Storybook", resource_id=storybook_id
        )
    version_row = await session.get(StorybookVersion, (storybook_id, version))
    if version_row is None:
        msg = f"storybook '{storybook_id}' has no version {version}"
        raise ResourceNotFoundError(
            msg,
            resource_type="StorybookVersion",
            resource_id=f"{storybook_id}:{version}",
        )
    if storybook.status != Status.PUBLISHED.value:
        msg = (
            f"cannot re-moderate storybook '{storybook_id}': its status is "
            f"{storybook.status!r}, not 'published' (see module docstring "
            "for the published-only scope)"
        )
        raise BusinessLogicError(
            msg,
            rule="remoderate_requires_published",
            context={"storybook_id": storybook_id, "status": storybook.status},
        )

    prior_reviewer_independent = _prior_reviewer_independent(
        version_row.moderation_report
    )

    child_names = await _family_child_names(session, storybook.family_id)
    pii = PiiContext(child_names=child_names)
    generation_provider = build_provider(
        ctx.settings,
        provider_override=version_row.provider,
        model_override=version_row.model,
    )

    started = time.monotonic()
    try:
        await run_moderation_pipeline(
            session=session,
            story_id=storybook_id,
            version=version,
            settings=ctx.settings,
            generation_provider=generation_provider,
            pii=pii,
        )
    except StateTransitionError:
        # #CRITICAL: security: expected and swallowed for every call this
        # endpoint's published-only scope admits: (PUBLISHED, SUBMIT) and
        # (PUBLISHED, AUTO_REJECT) are not legal hops
        # (publishing/state_machine.py::LEGAL_TRANSITIONS), so
        # assert_transition always raises here, BEFORE storybook.status is
        # touched. The fresh report was already persisted to version_row by
        # the pipeline's _persist_report call, which runs before its
        # terminal submit/auto_reject attempt, so nothing written is lost.
        # #VERIFY: tests/unit/test_remoderate_unit.py::
        # test_published_status_unchanged_after_remoderation asserts
        # storybook.status is still "published" and moderation_report was
        # replaced with the fresh (not mocked) pipeline's real output.
        _logger.info(
            "remoderate.state_transition_swallowed",
            storybook_id=storybook_id,
            version=version,
        )
    duration = time.monotonic() - started

    overall_verdict, verdict_counts, structural_count = _summarize_report(
        version_row.moderation_report
    )

    # #CRITICAL: data-integrity: this is the sole durable audit-trail record
    # of this re-moderation, since the pipeline's own MODERATION_COMPLETED
    # event is never reached for a published book (its emission sits after
    # the submit/auto_reject call this function just caught). The payload is
    # restricted to enum-derived verdicts, an int-valued count mapping, and a
    # bool by record_event's allowlist (events/writer.py), never finding
    # messages or story prose.
    # #VERIFY: tests/unit/test_remoderate_unit.py::
    # test_event_records_prior_reviewer_independent_provenance;
    # tests/unit/test_pipeline_event_check_vocab.py's drift guard covers the
    # new EventType member.
    await record_event(
        session,
        ctx.actor,
        entity_type="storybook_version",
        entity_id=f"{storybook_id}:{version}",
        event_type=EventType.STORYBOOK_REMODERATED,
        to_state=storybook.status,
        payload={
            "overall_verdict": overall_verdict,
            "counts": verdict_counts,
            "prior_reviewer_independent": prior_reviewer_independent,
        },
    )

    return RemoderateResult(
        storybook_id=storybook_id,
        version=version,
        status=storybook.status,
        overall_verdict=overall_verdict,
        verdict_counts=verdict_counts,
        structural_count=structural_count,
        duration_seconds=duration,
        prior_reviewer_independent=prior_reviewer_independent,
    )


@router.post("/admin/remoderate/{storybook_id}/{version}")
async def trigger_remoderate(
    storybook_id: str, version: int, ctx: Context
) -> RemoderateResultView:
    """Re-run moderation over one published storybook version (admin only).

    Runs synchronously and returns the fresh report's verdict summary. The
    book's ``status`` is never changed by this call (ADR-005: a published
    book stays published; the guardian/admin remains the only path that can
    ever move it again). See the module docstring for the published-only
    scope and the inherited auto-repair content-mutation risk.

    Args:
        storybook_id: The storybook id from the path.
        version: The version number from the path.
        ctx: The request context (principal + session).

    Returns:
        RemoderateResultView: The fresh report's verdict summary.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ResourceNotFoundError: If the storybook or version does not exist (404).
        BusinessLogicError: If the storybook is not currently published (400).
    """
    _require_admin(ctx)
    # #CRITICAL: security: the actor is stamped "admin" (not the principal's
    # base role) on the pipeline event this call writes, mirroring
    # api/rescreen.py::trigger_rescreen: a dual-role guardian+admin is
    # audited in the capacity that authorized the re-moderation.
    # #VERIFY: tests/unit/test_remoderate_unit.py::test_event_actor_role_is_admin.
    actor = Actor.from_principal(ctx.principal, acting_role=ADMIN_ACTOR_ROLE)
    result = await remoderate_storybook_version(
        ctx.session,
        storybook_id,
        version,
        RemoderateContext(settings=settings, actor=actor),
    )
    return _view(result)
