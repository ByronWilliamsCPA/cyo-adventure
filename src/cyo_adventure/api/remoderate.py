"""Admin re-moderation endpoint (moderation review redesign, design doc section 4 item 1).

``POST /api/v1/admin/remoderate/{storybook_id}/{version}`` re-runs the FULL
moderation pipeline (``moderation.pipeline.run_moderation_pipeline``) over one
already-published or awaiting-review storybook version and returns the outcome
synchronously. This is the catalog-remediation entry point that lets an admin
replace a mock-moderated or otherwise stale report with a fresh one produced by
the currently configured review provider, without waiting for a guardian to
trigger it through the ordinary generation path.

Scope: PUBLISHED and IN_REVIEW versions
---------------------------------------
This endpoint admits exactly the statuses in ``REMODERATABLE_STATUSES`` and
rejects every other with ``BusinessLogicError`` (400).

The membership rule is not a preference, it is the state machine.
``run_moderation_pipeline``'s terminal step always calls
``publishing.service.submit`` (clean/repaired report) or ``auto_reject`` (hard
block). A status belongs in the admitted set only if BOTH ``(status, SUBMIT)``
and ``(status, AUTO_REJECT)`` are absent from
``publishing/state_machine.py::LEGAL_TRANSITIONS``, because that absence is
what makes the terminal call always raise and this endpoint structurally
incapable of moving a book. ``published`` and ``in_review`` both satisfy it.

``draft`` and ``needs_revision`` do not: for them those hops ARE legal and the
story would actually move, which is a different, already-served workflow (the
ordinary generation pipeline, or ``api/rescreen.py`` for a lighter-weight
published-book policy sweep). ``archived`` is out of scope. So the contract
stays exactly one thing: "give me a fresh set of automated verdicts for this
book," never a state transition.

``in_review`` was added because every whole-book re-derivation path in the
codebase was published-scoped, which left the books sitting at the human gate,
the ones whose verdicts a reviewer is about to act on, as the only ones with no
way to refresh them.

Synchronous, but NOT for api/rescreen.py's reason
--------------------------------------------------------------------------
The synchronous shape is borrowed from ``api/rescreen.py``, but that module's
justification for it does not transfer and must not be assumed here.
``moderation/rescreen.py`` is synchronous precisely BECAUSE it makes no LLM
review calls ("adding their LLM cost/latency to every sweep would buy no
signal"). This endpoint inverts that premise: it makes the full review-model
fan-out, which the design doc estimates at ~50-80 calls for a large book,
inside one HTTP request.

The consequences are accepted deliberately, not overlooked. There is no job
row and no status-polling path, so a client disconnect loses the RESULT VIEW
(the report itself is committed by the request's unit-of-work, and the
pipeline event records the verdict, so nothing is lost but the response).
Concurrency is bounded by the single-flight slot in ``trigger_remoderate``
rather than by a queue. If re-moderation ever needs to be fire-and-forget or
survive a disconnect, it wants the RQ path ``generation/queue.py`` already
provides, which is a bigger change than this endpoint.

Why the pipeline's own state-transition call is caught, not avoided
---------------------------------------------------------------------
``run_moderation_pipeline`` is not modified (out of scope; owned by workstream
B2/B3 for other reasons in this concurrent effort, and a stable contract this
module deliberately does not fork). Calling it unmodified on any status in
``REMODERATABLE_STATUSES`` means its own terminal
``service.submit``/``service.auto_reject`` call ALWAYS raises
``StateTransitionError``, because none of ``(PUBLISHED, SUBMIT)``,
``(PUBLISHED, AUTO_REJECT)``, ``(IN_REVIEW, SUBMIT)``, or
``(IN_REVIEW, AUTO_REJECT)`` is a legal hop in
``publishing/state_machine.py::LEGAL_TRANSITIONS`` (in_review's only legal
hops are APPROVE and SEND_BACK, both of which are human actions this endpoint
never takes). That is caught here rather than propagated: by the time it is
raised, ``_persist_report`` has already overwritten
``version_row.moderation_report`` with the fresh, merged report (pipeline.py's
own code order runs persistence before the state-transition call), so the catch
discards only the (always-illegal, for this scope) attempt to move the book,
never the freshly written report.

That absence is the whole admission rule, which is why widening the status
guard is safe without touching the pipeline: a status may only be added to
``REMODERATABLE_STATUSES`` while BOTH its SUBMIT and AUTO_REJECT hops stay
absent from ``LEGAL_TRANSITIONS``. Adding either hop later would silently turn
this endpoint into one that moves books, so
``tests/unit/test_remoderate_unit.py`` pins the invariant directly rather than
leaving it to review.

# #CRITICAL: security: ADR-005 (mandatory human approval) requires a book to
# reach a child only through a human decision, and to remain that human's
# artifact until a human acts again; this endpoint must never itself flip
# status. That binds both admitted statuses: a published book must stay
# published, and an in_review book must stay at the human gate rather than
# being approved or sent back by an automated sweep.
# #VERIFY: no line in this module (or the pipeline it calls, for the statuses
# this module admits) sets ``storybook.status``; every other status is
# BusinessLogicError-rejected before the call, and StateTransitionError is
# caught, never reraised, for the two statuses allowed through.

Auto-repair is disabled for PUBLISHED books, and enabled for IN_REVIEW ones
--------------------------------------------------------------------------
``run_moderation_pipeline`` will, for a soft ``FLAG`` with no hard ``BLOCK``,
attempt one bounded LLM-driven auto-repair and, if adopted, rewrite
``version_row.blob`` in place. Whether that is correct depends entirely on
whether a human has already approved the prose, which is exactly what status
records, so this endpoint forks on it (``_allow_repair_for``).

For a PUBLISHED book it is not correct: the subject is a book a guardian
approved and a child may be reading offline, so a silent rewrite would alter a
family's shelf with no human gate, defeating ADR-005. The published arm
therefore passes ``allow_repair=False``, matching the rule already enforced
structurally by ``api/node_edit.py::_EDITABLE_STATUSES`` ("immutable once
released, ADR-005"), ``generation/series_link.py``'s
``embed_into_approved_blob`` guard, and ``moderation/rescreen.py``
("a re-screen tool must never silently rewrite already-published,
already-approved content").

For an IN_REVIEW book none of that transfers. The book is not reader-facing,
nobody has approved it, and a human still gates it before it ever reaches a
child, which is precisely the situation the ordinary generation path already
applies repair in. Withholding repair there would mean handing a reviewer a
flagged book the pipeline could have fixed.

The consequence for a published book is unchanged and deliberate:
re-moderation REPORTS on it, it never edits it. A book whose fresh report
carries a soft flag stays published with that flag recorded, and moving it
(send back, archive, or edit via the node editor after a status change)
remains a human decision.
# #CRITICAL: security: re-moderation must never mutate PUBLISHED prose. The
# narrowing to "published" is load-bearing: in_review prose may be rewritten,
# by design, and only the state machine keeps the two populations apart.
# #VERIFY: tests/unit/test_remoderate_unit.py::
# test_published_blob_unchanged_when_repair_disallowed asserts the stored blob
# is byte-identical after a soft-FLAG re-moderation of a published book;
# ::test_published_book_still_disallows_repair pins the flag itself; and
# ::test_in_review_book_allows_repair pins the other arm.

What a hard BLOCK here does, and does not, do
--------------------------------------------------------------------------
Nothing automatic. The book stays ``published``, stays assigned, and stays
readable, including offline on a device that already synced it. That follows
from the same ADR-005 rule as everything above: only a human moves a book.

Be precise about where that leaves the signal, because no existing surface
shows it. ``api/approval.py``'s review queue filters to ``IN_REVIEW``, so a
published book never appears there. ``StorybookSummary`` (``api/schemas.py``)
has no verdict field, so a freshly-blocked book is indistinguishable from a
healthy one in the admin library listing. The signal is therefore exactly
three things, all added deliberately: the ``overall_verdict`` in this
endpoint's response, the ``storybook_remoderated`` pipeline event (which
carries the verdict in its payload), and a WARNING log line. The ops sweep
adds a fourth for its own callers, escalating a block to a nonzero exit
(``scripts/remoderate_books.py::main``).

A passive admin-console surface for "published books with a fresh block" is
a real gap and a real feature: it needs a response-schema field and frontend
work, so it is tracked separately rather than half-built here.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from anyio.to_thread import run_sync
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from cyo_adventure.api.deps import Context
from cyo_adventure.api.gate_limits import gate_limiter
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    ResourceNotFoundError,
    StateTransitionError,
)
from cyo_adventure.db.models import ChildProfile, Storybook, StorybookVersion
from cyo_adventure.events import ADMIN_ACTOR_ROLE, Actor, EventType, record_event
from cyo_adventure.generation.import_story import IMPORT_PROVIDER
from cyo_adventure.generation.pii import PiiContext
from cyo_adventure.generation.provider import build_provider
from cyo_adventure.moderation.personalizable_slots import (
    PERSONALIZABLE_SLOTS_UNSET,
    PersonalizableSlotsArg,
    personalizable_slot_ids_for_version,
)
from cyo_adventure.moderation.pipeline import run_moderation_pipeline
from cyo_adventure.publishing.state_machine import Status
from cyo_adventure.utils.logging import get_logger
from cyo_adventure.validator.gate import run_fill_gate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.core.config import Settings
    from cyo_adventure.validator.gate import GateResult


def _fresh_validation_report(gate_result: GateResult) -> dict[str, object]:
    """Build the stored ``validation_report`` payload from a gate result.

    Mirrors ``generation/worker.py``'s composition so the admin review surface
    is never comparing a report that records the posture it was produced under
    against one that silently omits it.

    Args:
        gate_result: The result of a :func:`run_fill_gate` call over the blob.

    Returns:
        dict[str, object]: The report dict, carrying its ``gate_context``.
    """
    # #CRITICAL: data-integrity: `GateReport.to_dict()` returns only
    # {ok, findings}; the posture the run was made under lives on the
    # GateResult, not the report. generation/worker.py stamps it as
    # `gate_context` before persisting, and a report written here without it
    # is indistinguishable, to the review surface, from one produced under the
    # catalog-time "skeleton" posture where a retained <<FILL>> is legal input.
    # #VERIFY: tests/unit/test_remoderate_unit.py::
    # test_remoderation_stamps_the_gate_context_on_the_stored_report.
    report: dict[str, object] = dict(gate_result.report.to_dict())
    report["gate_context"] = gate_result.context
    return report


def _allow_repair_for(status: str) -> bool:
    """Return whether auto-repair may run for a storybook in ``status``.

    The one place this endpoint's behaviour forks on status, named so the fork
    is greppable rather than buried in an inline conditional at the pipeline
    call.

    Args:
        status: The storybook's current status value.

    Returns:
        True for a pre-publish book a human still gates, False otherwise.
    """
    # #CRITICAL: security: published stays False, absolutely. A published book
    # is a guardian-approved artifact a child may be reading offline, so a
    # silent rewrite defeats ADR-005; the same rule is enforced structurally by
    # api/node_edit.py::_EDITABLE_STATUSES, generation/series_link.py's
    # embed_into_approved_blob guard, and moderation/rescreen.py.
    # That reason does not transfer to in_review: the book is not reader-facing,
    # a human still gates it before it ever is, and repair is exactly what the
    # ordinary generation path already applies to a pre-publish draft.
    # #VERIFY: tests/unit/test_remoderate_unit.py::
    # test_published_blob_unchanged_when_repair_disallowed and
    # ::test_published_book_still_disallows_repair pin the published arm;
    # ::test_in_review_book_allows_repair pins the other.
    #
    # #CRITICAL: security: an ALLOW-list, not `!= PUBLISHED`. The negation was
    # default-open over an open enum: every status absent from
    # LEGAL_TRANSITIONS' submit/auto_reject hops satisfies this module's
    # admission criterion, and `archived` satisfies it too. Under the negation,
    # admitting `archived` to REMODERATABLE_STATUSES would silently authorise
    # LLM prose rewriting of a book that was published (and may sit in a
    # child's offline cache) with no guardian approval, and both pinning tests
    # below would stay green while it happened. The allow-list fails closed:
    # a newly admitted status gets repair only when someone writes it here.
    # #VERIFY: tests/unit/test_remoderate_unit.py::
    # test_repair_is_refused_for_any_status_other_than_in_review.
    return status == Status.IN_REVIEW.value


# #CRITICAL: security: the whole set of statuses this endpoint will re-moderate.
# Enumerated here rather than inline so a third status cannot be added at a call
# site without passing the state-machine argument in the module docstring: a
# status belongs here only if BOTH (status, SUBMIT) and (status, AUTO_REJECT)
# are absent from publishing/state_machine.py::LEGAL_TRANSITIONS, which is what
# makes the pipeline's terminal call always raise and this endpoint structurally
# incapable of moving a book. `draft` and `needs_revision` fail that test (for
# them the hop IS legal and the story would actually move, which is the ordinary
# generation path's job); `archived` is out of scope.
# #VERIFY: tests/unit/test_remoderate_unit.py::
# test_non_remoderatable_status_rejected pins the rejected set;
# ::test_in_review_status_is_not_changed_by_remoderation and
# ::test_published_state_unchanged_after_real_remoderation pin that neither
# admitted status can move.
# Public, not module-private: scripts/remoderate_books.py resolves an
# operator's explicit --book-id against this same set, so that the sweep
# refuses an inadmissible status BEFORE --execute touches any book rather
# than aborting mid-sweep on this module's 400. Two copies of a
# security-relevant admission set is the failure this avoids.
REMODERATABLE_STATUSES: frozenset[Status] = frozenset(
    {Status.PUBLISHED, Status.IN_REVIEW}
)

REMODERATABLE_STATUS_VALUES: frozenset[str] = frozenset(
    s.value for s in REMODERATABLE_STATUSES
)


router = APIRouter(prefix="/api/v1", tags=["remoderate"])

_logger = get_logger(__name__)

# Single-flight slot for the HTTP path only; see trigger_remoderate for why.
# The ops sweep (scripts/remoderate_books.py) calls
# remoderate_storybook_version directly and is deliberately NOT gated by this:
# it is an operator running one sequential loop, not a concurrency source.
_REMODERATION_SLOT = asyncio.Semaphore(1)


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
    repaired: bool


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
    # #ASSUME: data-integrity: the ONLY signal that this endpoint rewrote a
    # book's prose. Without it an operator sweeping the review queue sees
    # "succeeded: 17" and cannot tell which books an LLM edited, because the
    # pipeline's own MODERATION_COMPLETED event (which carries `repaired`) is
    # unreachable on this path.
    # #VERIFY: tests/unit/test_remoderate_unit.py::
    # test_repaired_is_read_from_the_report_summary_not_its_top_level asserts
    # both surfaces (the returned view and the audit event payload);
    # ::test_repaired_is_false_when_the_pipeline_adopted_no_repair proves the
    # flag discriminates rather than reporting True for every run.
    repaired: bool


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
        repaired=result.repaired,
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
    # #CRITICAL: security: this is the only value in this module that IS
    # children's PII rather than a reference to it, and its whole purpose is
    # to be handed to the moderation pipeline so the pipeline can keep those
    # names OUT of provider prompts. The direction matters: the names travel
    # inward as a denylist, never outward. Two properties keep that true and
    # both must survive any edit here.
    #
    # First, the value stays in-process. It is passed to
    # run_moderation_pipeline and is never logged, never placed in a
    # RemoderateResult, never written to the pipeline event payload, and
    # never reaches RemoderateResultView; the endpoint's response carries
    # only verdict counts. A log line or event payload added here would
    # exfiltrate exactly what the guard exists to protect, into a store with
    # a different retention and access model than the profile table.
    #
    # Second, the family scope is the STORY's family, not the caller's, and
    # that is deliberate rather than an oversight: an admin re-moderating
    # another family's book must still suppress THAT family's names, so the
    # query cannot be narrowed to the principal's own family without
    # silently disabling the guard for every cross-family sweep, which is
    # the case the ops script (scripts/remoderate_books.py) drives.
    # #VERIFY: tests/unit/test_remoderate_unit.py::
    # test_child_names_passed_to_pipeline_for_pii_guard asserts the names
    # reach the pipeline call; ::test_remoderate_response_excludes_child_names
    # asserts they appear in neither the response nor the recorded event.
    rows = await session.scalars(
        select(ChildProfile.display_name).where(ChildProfile.family_id == family_id)
    )
    return frozenset(rows.all())


def _report_repaired(report: dict[str, object] | None) -> bool:
    """Return whether the pipeline adopted a repair on this run.

    Args:
        report: The freshly stored moderation report, or None.

    Returns:
        bool: True only when the report explicitly records a repair.
    """
    # #CRITICAL: data-integrity: the flag lives at ``summary.repaired``, NOT at
    # the report's top level (moderation/report.py::to_dict nests it beside
    # hard_block and soft_flag). A top-level read here parses without error and
    # returns False for every book forever, which is the silent direction: the
    # response and the audit event would both assert "nothing was rewritten"
    # about a book whose prose the repair pass had in fact replaced. Read
    # defensively for the same reason _prior_reviewer_independent does: the
    # column is JSONB, so its runtime shape is whatever was stored.
    # #VERIFY: tests/unit/test_remoderate_unit.py::
    # test_repaired_is_read_from_the_report_summary_not_its_top_level.
    if report is None:
        return False
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return False
    return cast("dict[str, object]", summary).get("repaired") is True


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
    # #ASSUME: data-integrity: ``moderation_report`` is JSONB, so its runtime
    # shape is whatever was stored, not whatever the annotation claims.
    # ``cast`` is erased at runtime and validates nothing, so every read below
    # is isinstance-guarded rather than cast: a legacy row, a hand-edited
    # report, or a stored ``summary: null`` would otherwise raise
    # AttributeError/TypeError here, AFTER the pipeline has already written
    # its fresh report, turning a cosmetic summarization step into a failed
    # request. This mirrors _prior_reviewer_independent's defensive reads.
    # #VERIFY: tests/unit/test_remoderate_unit.py::
    # test_summarize_report_tolerates_malformed_shapes covers null summary,
    # non-dict findings, and a non-list findings value.
    if report is None:
        return "pass", {}, 0
    raw_summary = report.get("summary")
    summary: dict[str, object] = raw_summary if isinstance(raw_summary, dict) else {}
    if summary.get("hard_block"):
        overall = "block"
    elif summary.get("soft_flag"):
        overall = "flag"
    else:
        overall = "pass"
    raw_findings = report.get("findings")
    findings: list[object] = raw_findings if isinstance(raw_findings, list) else []
    counts: dict[str, int] = {}
    structural = 0
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        entry = cast("dict[str, object]", finding)
        raw_verdict = entry.get("verdict")
        verdict = raw_verdict if isinstance(raw_verdict, str) else "unknown"
        counts[verdict] = counts.get(verdict, 0) + 1
        if entry.get("structural"):
            structural += 1
    return overall, counts, structural


async def remoderate_storybook_version(
    session: AsyncSession,
    storybook_id: str,
    version: int,
    ctx: RemoderateContext,
) -> RemoderateResult:
    """Re-run the moderation pipeline over one re-moderatable storybook version.

    Args:
        session: The request session (caller owns the transaction).
        storybook_id: The storybook id from the path.
        version: The version number from the path.
        ctx: Settings + the audited actor.

    Returns:
        RemoderateResult: The fresh report's verdict summary; the book's
        status is guaranteed unchanged (see module docstring). The stored blob
        may have been repaired in place if the book was ``in_review``.

    Raises:
        ResourceNotFoundError: If the storybook or version does not exist (404).
        BusinessLogicError: If the storybook's status is not in
            ``REMODERATABLE_STATUSES`` (400).
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
    if storybook.status not in REMODERATABLE_STATUS_VALUES:
        allowed = ", ".join(sorted(REMODERATABLE_STATUS_VALUES))
        msg = (
            f"cannot re-moderate storybook '{storybook_id}': its status is "
            f"{storybook.status!r}, which is not re-moderatable (allowed: "
            f"{allowed}; see module docstring for the scope)"
        )
        raise BusinessLogicError(
            msg,
            rule="remoderate_requires_reviewable_status",
            context={"storybook_id": storybook_id, "status": storybook.status},
        )

    # #CRITICAL: data-integrity: re-derive the DETERMINISTIC half before the
    # generative half runs (moderation-review-redesign-2026-07-28.md, design
    # principle 4). The admin review surface reads the stored
    # validation_report and never re-runs the gate itself
    # (api/review_surface.py::_validator_findings is read-only by decision),
    # so without this line a book keeps displaying whatever the gate said on
    # the day it was imported, however many rule changes ago, and a reviewer
    # reads a stale verdict as a current one. Re-moderation is the only
    # admin-triggered path that re-derives a stored book's automated verdicts,
    # so it is the right place to re-derive both.
    #
    # run_fill_gate, not run_gate: the shared definition guarantees this
    # report is produced under the same posture as the import producer's
    # (generation/import_story.py), so the review surface is never ranking
    # reports built under different contexts against each other.
    # #VERIFY: tests/unit/test_remoderate_unit.py::
    # test_remoderation_refreshes_the_stored_validation_report proves the
    # stale report is replaced; tests/unit/test_gate.py::
    # test_run_fill_gate_reproduces_the_fill_result_posture pins the helper
    # to the posture the import producer uses.
    #
    # #CRITICAL: concurrency: offloaded via anyio.to_thread under the shared
    # gate_limiter(), never called inline. run_gate is pure synchronous CPU
    # measured at 49.6s worst case (see api/node_edit.py), so an inline call
    # here would stall the event loop for that window and block every other
    # in-flight request, including a child mid-read (AL-035). The limiter is
    # the same process-wide one api/node_edit.py and api/generation.py use,
    # so the three routes share one bound rather than three independent ones.
    # #VERIFY: tests/unit/test_gate_capacity_limiter.py::
    # test_both_gate_call_sites_share_one_limiter inspects this module.
    version_row.validation_report = _fresh_validation_report(
        await run_sync(run_fill_gate, version_row.blob, limiter=gate_limiter())
    )

    prior_reviewer_independent = _prior_reviewer_independent(
        version_row.moderation_report
    )

    child_names = await _family_child_names(session, storybook.family_id)
    pii = PiiContext(child_names=child_names)
    # #EDGE: data-integrity: StorybookVersion.provider is a provenance field,
    # not always a provider name: offline-authored books carry the "import"
    # sentinel (generation/import_story.py), which build_provider rightly
    # rejects. So for imported books fall back to the configured default
    # provider (the same fallback a NULL provider already gets) instead of
    # failing the whole re-moderation before any review happens. The stored
    # model is dropped with it: an import row's model column cannot name a
    # model usable by a provider the row does not name.
    # #CRITICAL: data-integrity: the generation provider on this path serves
    # the auto-repair re-prompt, which on the in_review arm actually RUNS.
    # This fallback therefore picks the model that may rewrite a book's prose,
    # and it does so for exactly the population that reaches it: an imported
    # book carries no usable provider of its own, so the configured default is
    # the only candidate, and it is the same default the generation path
    # itself uses. It is not a silent downgrade of a book's own provenance,
    # because an import row never had generation provenance to preserve.
    # #VERIFY: covered by test_import_provenance_falls_back_to_default_provider
    # in tests/unit/test_remoderate_unit.py; the repair fork itself is pinned
    # by ::test_in_review_book_allows_repair and
    # ::test_published_book_still_disallows_repair.
    if version_row.provider == IMPORT_PROVIDER:
        provider_override = None
        model_override = None
    else:
        provider_override = version_row.provider
        model_override = version_row.model
    # #EDGE: security: remoderation replays a stored version's provider, and the
    # book it re-reviews belongs to a family, so it runs on the restricted lane
    # (D1, 2026-08-23, UW-C346). A version whose stored provider is the direct
    # `anthropic` leg is therefore refused rather than replayed. Reachable only
    # for rows written before the lane rule; the live default has been an
    # OpenRouter cascade throughout.
    # #VERIFY: tests/unit/test_provider_lane.py pins what the lane refuses;
    # tracked at UW-C346 if a legacy row ever needs a documented fallback.
    generation_provider = build_provider(
        ctx.settings,
        provider_override=provider_override,
        model_override=model_override,
        lane="family",
    )

    allow_repair = _allow_repair_for(storybook.status)

    # #CRITICAL: data-integrity: resolved from the VERSION, and only for the
    # in_review arm this endpoint newly admits.
    #
    # Why the version at all: an in_review book here is an offline import with
    # no GenerationJob row (17 of 17 in production, 2026-08-24). The pipeline's
    # own fallback, personalizable_slot_ids_for_story, returns an EMPTY
    # frozenset for a story with no job row (not the fail-closed marker: see
    # that function's docstring for why empty is the right answer there), and an
    # empty declared set makes check_sentinel_integrity_at_rest report every
    # well-formed sentinel in the blob as "unknown_slot". No book currently in
    # review carries a sentinel, so this is defensive rather than a live fault
    # today; it stops being defensive the first time a sentinel-bearing book
    # reaches the review gate.
    #
    # Why NOT for published: passing an explicit value suppresses the job-row
    # lookup entirely. A published, generated, job-backed book whose version
    # predates the skeleton_slug column (the column is never backfilled)
    # resolves a real contract from its job today and would resolve an empty
    # set here, manufacturing exactly the block this argument exists to avoid,
    # on the arm this change is meant to leave alone. Leaving published UNSET
    # keeps its behaviour bit-identical to before this endpoint was widened.
    # #VERIFY: tests/unit/test_remoderate_unit.py::
    # test_slot_contract_resolved_from_the_version_not_a_job and
    # ::test_published_arm_leaves_the_slot_contract_to_the_pipeline.
    slot_contract: PersonalizableSlotsArg = PERSONALIZABLE_SLOTS_UNSET
    if storybook.status == Status.IN_REVIEW.value:
        # #ASSUME: timing: offloaded because this walks the skeleton catalog
        # directory and reads two JSON files; inline it would block the event
        # loop on a cold cache or a network-backed catalog volume. No gate
        # limiter: this is a short filesystem read, not the CPU-bound gate, so
        # it must not contend for the gate's bounded slots.
        # #VERIFY: no api module calls personalizable_slot_ids_for_version
        # outside a run_sync offload.
        slot_contract = await run_sync(personalizable_slot_ids_for_version, version_row)

    started = time.monotonic()
    try:
        await run_moderation_pipeline(
            session=session,
            story_id=storybook_id,
            version=version,
            settings=ctx.settings,
            generation_provider=generation_provider,
            pii=pii,
            allow_repair=allow_repair,
            # Resolved above, scoped to the in_review arm. See the marker
            # there for why the version and why not for published books.
            personalizable_slots=slot_contract,
        )
    except StateTransitionError:
        # #CRITICAL: security: expected and swallowed for every call this
        # endpoint's scope admits: (PUBLISHED, SUBMIT), (PUBLISHED,
        # AUTO_REJECT), (IN_REVIEW, SUBMIT), and (IN_REVIEW, AUTO_REJECT) are
        # all absent from publishing/state_machine.py::LEGAL_TRANSITIONS, so
        # assert_transition always raises here, BEFORE storybook.status is
        # touched. The catch is only ever correct while that stays true, which
        # is why REMODERATABLE_STATUSES is pinned against LEGAL_TRANSITIONS
        # by test rather than by convention. The fresh report was already
        # persisted to version_row by the pipeline's _persist_report call,
        # which runs before its
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
    except Exception as exc:
        # #CRITICAL: data-integrity: any OTHER failure (a provider timeout, a
        # DB error) propagates, and api/deps.py::get_db_session then rolls the
        # whole request transaction back. That rollback is the reason this
        # branch logs instead of calling record_event: an event row written
        # here would be discarded with everything else, so recording one would
        # only manufacture the appearance of an audit trail. This log line IS
        # the record of an attempted-but-failed re-moderation, and it is
        # correlation-ID stamped (utils/logging.py) so it joins the request.
        # The rollback also means the failure is clean: no half-written
        # moderation_report survives, and the published blob is untouched
        # regardless (see the auto-repair section of the module docstring).
        # #VERIFY: tests/unit/test_remoderate_unit.py::
        # test_provider_failure_logs_and_propagates asserts the exception
        # reaches the caller (so the unit-of-work rolls back) and that no
        # pipeline event is recorded.
        _logger.exception(
            "remoderate.failed",
            storybook_id=storybook_id,
            version=version,
            actor_role=ctx.actor.actor_role,
            error_type=type(exc).__name__,
        )
        raise
    duration = time.monotonic() - started

    if allow_repair:
        # #CRITICAL: data-integrity: the gate pass above runs BEFORE the
        # generative half by design (moderation-review-redesign-2026-07-28.md,
        # design principle 4: deterministic before generative), which was safe
        # only while allow_repair=False guaranteed the blob could not change
        # underneath it. On the repair-enabled path the pipeline may adopt a
        # repair and assign version_row.blob = revised, so without this second
        # pass moderation_report would describe the repaired prose while
        # validation_report described prose that no longer exists. That is a
        # worse staleness than the month-old reports this endpoint's re-gating
        # exists to fix, because it is invisible rather than merely old.
        #
        # Re-deriving unconditionally on this path is deliberate and cheaper
        # than detecting whether a repair was actually adopted:
        # run_moderation_pipeline returns None and signals nothing, and
        # run_fill_gate is deterministic and makes no LLM call.
        # #VERIFY: tests/unit/test_remoderate_unit.py::
        # test_repaired_blob_gets_a_matching_validation_report fails if this
        # block is deleted.
        #
        # #CRITICAL: concurrency: offloaded under the shared gate_limiter()
        # for the same reason as the entry re-gate above.
        # #VERIFY: tests/unit/test_gate_capacity_limiter.py::
        # test_both_gate_call_sites_share_one_limiter.
        version_row.validation_report = _fresh_validation_report(
            await run_sync(run_fill_gate, version_row.blob, limiter=gate_limiter())
        )

    overall_verdict, verdict_counts, structural_count = _summarize_report(
        version_row.moderation_report
    )
    repaired = _report_repaired(version_row.moderation_report)

    if overall_verdict == "block":
        # #CRITICAL: security: a hard block does not move the book, and how
        # loud that silence is depends entirely on which status it lands on.
        # ADR-005 reserves every status change for a human and this endpoint
        # deliberately never moves a book (see the module docstring), so the
        # verdict is recorded and nothing else happens.
        #
        # On an IN_REVIEW book that is tolerable: the review queue filters to
        # IN_REVIEW (api/approval.py), so the book is already in front of a
        # reviewer with its fresh report attached, and the block is exactly the
        # signal the queue exists to carry.
        #
        # On a PUBLISHED book nothing else surfaces it at all. The book stays
        # published, stays assigned, and stays readable offline until an admin
        # acts; the review queue never admits it, and StorybookSummary
        # (api/schemas.py) carries no verdict field, so a freshly-blocked book
        # renders identically to a healthy one in the admin library. For that
        # population this WARNING plus the event below are the whole signal;
        # the sweep script escalates the same verdict to a nonzero exit
        # (scripts/remoderate_books.py::main). ``status`` is logged so the two
        # populations are separable by an operator reading the stream, since
        # only one of them means "a child can read a blocked book right now".
        # #VERIFY: tests/unit/test_remoderate_unit.py::
        # test_hard_block_on_published_book_logs_warning and
        # ::test_hard_block_on_in_review_book_logs_its_own_status pin BOTH
        # values of that ``status`` kwarg; one alone leaves the distinction
        # the kwarg exists for unobserved. A passive admin-UI
        # surface for this state is deliberately NOT in this endpoint's scope;
        # it is a schema + frontend change tracked separately.
        _logger.warning(
            "remoderate.hard_block_without_status_change",
            storybook_id=storybook_id,
            version=version,
            status=storybook.status,
            structural_count=structural_count,
        )

    # #CRITICAL: data-integrity: this is the sole durable audit-trail record
    # of this re-moderation, since the pipeline's own MODERATION_COMPLETED
    # event is never reached for any status this endpoint admits (its emission
    # sits after the submit/auto_reject call this function just caught, and
    # that call always raises for both admitted statuses). The payload is
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
            "repaired": repaired,
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
        repaired=repaired,
    )


@router.post("/admin/remoderate/{storybook_id}/{version}")
async def trigger_remoderate(
    storybook_id: str, version: int, ctx: Context
) -> RemoderateResultView:
    """Re-run moderation over one storybook version (admin only).

    Accepts a version whose storybook is ``published`` or ``in_review``, and
    runs synchronously, returning the fresh report's verdict summary. The
    book's ``status`` is never changed by this call (ADR-005: a published book
    stays published, an in_review book stays at the human gate; the
    guardian/admin remains the only path that can ever move either one).

    Auto-repair follows the status: a ``published`` book is reported on and
    never rewritten, while an ``in_review`` book may have a soft-flagged node
    repaired in place, exactly as on the generation path that produced it,
    because a human still reviews the result before any child sees it. See the
    module docstring for the full scope rule and what a hard block does not do.

    Args:
        storybook_id: The storybook id from the path.
        version: The version number from the path.
        ctx: The request context (principal + session).

    Returns:
        RemoderateResultView: The fresh report's verdict summary.

    Raises:
        AuthorizationError: If the caller is not an admin (403).
        ResourceNotFoundError: If the storybook or version does not exist (404).
        BusinessLogicError: If the storybook's status is neither ``published``
            nor ``in_review``, or if a re-moderation is already in flight on
            this worker (400).
    """
    _require_admin(ctx)
    # #CRITICAL: external-resources: this is the most expensive action any
    # admin can trigger (the design doc estimates ~50-80 review-model calls
    # for a large book, all inside one HTTP request), and the app-wide
    # RateLimitMiddleware default of 60 req/min per IP does nothing to bound
    # it: 60 accepted requests would be 60 concurrent pipelines. This slot
    # caps a process at one in-flight re-moderation and REJECTS rather than
    # queues, because queueing inside the request would pile up connections
    # and turn a burst into a pool exhaustion instead of a clear error.
    # The check-then-acquire is atomic despite the two steps: acquiring an
    # uncontended asyncio.Semaphore returns without yielding, so no other
    # task can run between `locked()` and the `async with`.
    # #ASSUME: concurrency: this is per-PROCESS, not cluster-wide. With more
    # than one worker it caps N concurrent re-moderations, not one. That is
    # the honest bound of an in-process guard; a global cap needs the Redis
    # backend RateLimitMiddleware already talks to, which is a shared-
    # middleware change deliberately not made here.
    # #VERIFY: tests/unit/test_remoderate_unit.py::
    # test_second_concurrent_remoderation_is_rejected.
    if _REMODERATION_SLOT.locked():
        msg = (
            "a re-moderation is already running on this worker; "
            "re-moderation is single-flight because one run makes dozens of "
            "review-model calls. Retry when it finishes."
        )
        raise BusinessLogicError(msg, rule="remoderate_already_running")
    # #CRITICAL: security: the actor is stamped "admin" (not the principal's
    # base role) on the pipeline event this call writes, mirroring
    # api/rescreen.py::trigger_rescreen: a dual-role guardian+admin is
    # audited in the capacity that authorized the re-moderation.
    # #VERIFY: tests/unit/test_remoderate_unit.py::test_event_actor_role_is_admin.
    actor = Actor.from_principal(ctx.principal, acting_role=ADMIN_ACTOR_ROLE)
    async with _REMODERATION_SLOT:
        result = await remoderate_storybook_version(
            ctx.session,
            storybook_id,
            version,
            RemoderateContext(settings=settings, actor=actor),
        )
    return _view(result)
