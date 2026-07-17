"""Admin policy re-screen endpoint (register A4 first cut; roadmap Phase 5).

``POST /api/v1/admin/rescreen`` re-runs the deterministic policy/band gate
and the Stage-0 moderation classifiers over already-published family-tier
storybooks (``moderation.rescreen.rescreen_published_books``) and returns the
outcome synchronously. See that module's docstring for the full design
rationale (scope, no-auto-unpublish, no-report-overwrite).

Sync-only, no ``async_mode`` enqueue path
------------------------------------------
The task brief for this endpoint allows an optional RQ-backed ``async_mode``
IF the existing queue plumbing (``generation/queue.py``) can be reused
cleanly. It cannot: that module's ``enqueue_generation`` is hard-wired to one
worker entrypoint (``generation.worker.run_generation_job_sync``) that reads
a ``GenerationJob`` row shaped for the generation pipeline (provider, model,
prompt fields the rescreen sweep has no use for), and there is no
job-row/status-polling model for an arbitrary admin sweep. Building that
plumbing (a new job table, a new worker entrypoint, a status-polling
endpoint) is a second feature, not a clean reuse, and is out of scope for
this family-tier first cut. Every storybook in the catalog today IS the
family-tier catalog (the public App Store catalog is Phase 9), so the bound
on sweep size is small enough that a synchronous admin-triggered request is
acceptable; this is explicitly a decision to revisit if/when Phase 9's
larger public catalog makes a synchronous sweep impractical.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from pydantic import BaseModel, Field

from cyo_adventure.api.deps import Context
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import AuthorizationError
from cyo_adventure.events import ADMIN_ACTOR_ROLE, Actor
from cyo_adventure.moderation.rescreen import rescreen_published_books

if TYPE_CHECKING:
    from cyo_adventure.moderation.rescreen import BookVerdict, RescreenSummary

router = APIRouter(prefix="/api/v1", tags=["rescreen"])


def _require_admin(ctx: Context) -> None:
    """Reject non-admin callers before the sweep touches any row.

    Args:
        ctx: The request context (principal + session).

    Raises:
        AuthorizationError: If the caller is not an admin (403).
    """
    # #CRITICAL: security: a re-screen sweep reads and re-classifies every
    # published book's full prose and writes a pipeline event per book; the
    # role gate runs before any query, mirroring
    # api/moderation_thresholds.py::_require_admin and api/node_edit.py's
    # admin-or-guardian gate.
    # #VERIFY: tests/unit/test_rescreen_unit.py::test_non_admin_rejected_with_403.
    if not ctx.principal.is_admin:
        msg = "admin role required"
        raise AuthorizationError(msg, required_permission="admin")


class RescreenRequest(BaseModel):
    """POST body: an optional scope for the sweep.

    Attributes:
        storybook_ids: When given, restrict the sweep to these ids (ids that
            are not currently published are silently skipped, matching an
            ordinary filtered list). ``None`` (the default) screens every
            published storybook.
    """

    storybook_ids: list[str] | None = Field(default=None)


class BookVerdictView(BaseModel):
    """One published storybook's re-screen outcome, on the wire."""

    storybook_id: str
    version: int
    outcome: str
    reasons: list[str]
    error: str | None


class RescreenSummaryView(BaseModel):
    """The sweep's aggregate result, on the wire."""

    checked: int
    passed: int
    flagged: int
    errored: int
    results: list[BookVerdictView]


def _view(verdict: BookVerdict) -> BookVerdictView:
    """Adapt one service-layer :class:`BookVerdict` to its wire view."""
    return BookVerdictView(
        storybook_id=verdict.storybook_id,
        version=verdict.version,
        outcome=verdict.outcome,
        reasons=verdict.reasons,
        error=verdict.error,
    )


def _summary_view(summary: RescreenSummary) -> RescreenSummaryView:
    """Adapt the service-layer :class:`RescreenSummary` to its wire view."""
    return RescreenSummaryView(
        checked=summary.checked,
        passed=summary.passed,
        flagged=summary.flagged,
        errored=summary.errored,
        results=[_view(r) for r in summary.results],
    )


@router.post("/admin/rescreen")
async def trigger_rescreen(body: RescreenRequest, ctx: Context) -> RescreenSummaryView:
    """Re-screen published storybooks against the current policy/thresholds (admin only).

    Runs synchronously (see the module docstring for why no async/enqueue
    path is offered in this first cut) and returns the full summary in the
    response; a flagged book is never auto-archived (ADR-005) -- an admin
    reviews ``results`` and archives through the existing admin path if
    warranted.

    Args:
        body: The optional storybook id scope.
        ctx: The request context (principal + session).

    Returns:
        RescreenSummaryView: Checked/passed/flagged/errored counts plus every
        book's verdict.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
    """
    _require_admin(ctx)
    # #CRITICAL: security: the actor is stamped "admin" (not the principal's
    # base role) on every pipeline event this sweep writes, mirroring
    # api/moderation_thresholds.py's THRESHOLD_CHANGED events: a dual-role
    # guardian+admin is audited in the capacity that authorized the sweep.
    # #VERIFY: tests/unit/test_rescreen_unit.py::test_event_actor_role_is_admin.
    actor = Actor.from_principal(ctx.principal, acting_role=ADMIN_ACTOR_ROLE)
    summary = await rescreen_published_books(
        ctx.session,
        settings=settings,
        actor=actor,
        storybook_ids=body.storybook_ids,
    )
    return _summary_view(summary)
