"""Storybook approval service: transitions that stamp provenance.

Each function wraps a state-machine transition and mutates ORM rows, then
``await session.flush()``. The request unit-of-work (api/deps.py) commits once
at request end; these never commit. ``approve`` is the ONLY path that may set
``status="published"``, and it always stamps ``approved_by`` in the same
operation, which is the single-write-path leg of the no-unapproved-publish
invariant.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from cyo_adventure.core.exceptions import BusinessLogicError, ResourceNotFoundError
from cyo_adventure.db.models import StorybookVersion
from cyo_adventure.events import Actor, EventType, record_event
from cyo_adventure.publishing.state_machine import Action, Status, assert_transition
from cyo_adventure.utils.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.api.deps import Principal
    from cyo_adventure.db.models import Storybook

_logger = get_logger(__name__)


async def submit(session: AsyncSession, storybook: Storybook) -> None:
    """Move a draft or needs-revision story into review.

    Args:
        session: The request session (caller owns the transaction).
        storybook: The story to submit.

    Raises:
        StateTransitionError: If the story is not in ``draft``/``needs_revision``.
        BusinessLogicError: If the story's latest version has never been
            screened by the moderation pipeline (``moderation_report is None``).
    """
    # #CRITICAL: data integrity: status is the ORM boundary for the lifecycle;
    # assert_transition is the only gate that may change it. The ORM string is
    # coerced through Status() so an unmodeled DB status raises (closed-world).
    # #VERIFY: assert_transition raises StateTransitionError -> 409 on illegal hops.
    target = assert_transition(Status(storybook.status), Action.SUBMIT)
    # #CRITICAL: security: mirrors the moderation-report gate approve() already
    # enforces (closes #57). Without this check, the admin submit endpoint
    # (api/approval.py::submit_storybook) could move a draft straight to
    # in_review without moderation ever having run on its latest version.
    # Refusing here, at the sole function that performs the submit
    # transition, makes "no unscreened version reaches in_review" hold
    # structurally regardless of how many routes call submit().
    # #VERIFY: test_submit_without_moderation_report_raises and
    # test_submit_with_moderation_report_succeeds in
    # tests/unit/test_publishing_service_unit.py.
    latest_version = await session.scalar(
        select(func.max(StorybookVersion.version)).where(
            StorybookVersion.storybook_id == storybook.id
        )
    )
    # #ASSUME: data-integrity: a storybook with zero version rows skips the
    # moderation gate. persist_storybook (generation/persistence.py) is the sole
    # creation path and always inserts the first StorybookVersion in the same
    # flush, so latest_version is None only for a not-yet-persisted storybook,
    # which cannot reach submit(). If a future path creates a versionless
    # storybook, this branch would let it submit unscreened.
    # #VERIFY: guarded by test_submit_without_moderation_report_raises and the
    # integration test_submit_without_moderation_raises.
    if latest_version is not None:
        version_row = await session.get(
            StorybookVersion, (storybook.id, latest_version)
        )
        if version_row is not None and version_row.moderation_report is None:
            msg = "cannot submit a version that has never been screened by moderation"
            raise BusinessLogicError(msg, rule="submit_without_moderation")
    storybook.status = target.value
    await session.flush()


async def auto_reject(session: AsyncSession, storybook: Storybook) -> None:
    """Route a hard-blocked story to needs_revision without human review.

    Driven by the slice-2 moderation pipeline on a Stage-0 bright-line hit or a
    Stage-1 ``block``. There is no principal: the rejector is the machine, not a
    guardian, so nothing is stamped on the version row.

    Args:
        session: The request session (caller owns the transaction).
        storybook: The draft story being machine-rejected.

    Raises:
        StateTransitionError: If the story is not in ``draft``.
    """
    # #CRITICAL: security: this is the machine-side rejection path; it must never
    # set status="published" and only fires on a recorded hard-block finding. The
    # ORM string is coerced through Status() so an unmodeled DB status raises.
    # #VERIFY: assert_transition rejects any from-state except "draft".
    storybook.status = assert_transition(
        Status(storybook.status), Action.AUTO_REJECT
    ).value
    _logger.info("storybook_auto_rejected", storybook_id=storybook.id)
    await session.flush()


async def approve(
    session: AsyncSession,
    principal: Principal,
    storybook: Storybook,
    version: int,
) -> StorybookVersion:
    """Approve and publish a specific version, stamping approval provenance.

    Args:
        session: The request session (caller owns the transaction).
        principal: The approving admin.
        storybook: The story being approved.
        version: The version number to publish.

    Returns:
        StorybookVersion: The stamped version row.

    Raises:
        StateTransitionError: If the story is not in ``in_review``.
        ResourceNotFoundError: If the version row does not exist.
        BusinessLogicError: If the version has never been screened by the
            moderation pipeline (``moderation_report is None``).
    """
    # #CRITICAL: security: this is the SOLE path that sets status="published",
    # and it stamps approved_by in the same operation, so no story is published
    # without a recorded approver (the slice-1 invariant).
    # #VERIFY: test_no_publish_without_approver drives every endpoint path.
    # #CRITICAL: concurrency: `storybook` arrives already locked (SELECT ... FOR
    # UPDATE, same transaction) for every caller of this module's transitions:
    # api/approval.py::_load_admin_story for the admin path, and
    # moderation/pipeline.py::run_moderation_pipeline for the worker path. So
    # this in-memory status re-check is race-free for all of them: a second
    # transaction blocks on that lock until the first commits, then re-reads
    # the post-commit status here and assert_transition raises instead of both
    # callers passing the check and the last writer overwriting approved_by
    # below (closes #129 / audit Finding 3).
    # #VERIFY: tests/integration/test_approval_api.py::
    # test_second_approve_rejected_and_approved_by_not_overwritten (sequential
    # regression, not a true concurrent-transaction race; a two-session test is
    # accepted debt per the #129 issue thread). Lock presence for both callers:
    # tests/unit/test_approval_unit.py::test_load_admin_story_locks_row_for_update
    # and tests/unit/test_moderation_pipeline.py::
    # test_pipeline_locks_storybook_row_for_update.
    target = assert_transition(Status(storybook.status), Action.APPROVE)
    version_row = await session.get(StorybookVersion, (storybook.id, version))
    if version_row is None:
        msg = f"version {version} of storybook '{storybook.id}' not found"
        raise ResourceNotFoundError(msg)
    # #CRITICAL: security: closes C3-SAFETY Finding 2 (adversarial-safety-
    # evaluation.md): the admin submit endpoint (api/approval.py::submit_storybook)
    # can still move a draft straight to in_review without ever running
    # moderation (Finding 1 closed the import path's own unmoderated route; this
    # endpoint is untouched by that fix). This guard is the single choke point
    # (the sole publish path) that makes "no unmoderated path reaches published"
    # hold structurally, regardless of how many routes can reach in_review.
    # #VERIFY: test_approve_without_moderation_report_raises.
    if version_row.moderation_report is None:
        msg = "cannot approve a version that has never been screened by moderation"
        raise BusinessLogicError(msg, rule="approve_without_moderation")
    storybook.status = target.value
    storybook.current_published_version = version
    version_row.approved_by = principal.user_id
    version_row.published_at = datetime.now(UTC)
    # #CRITICAL: data-integrity: this is the WS-D event-log record of the
    # publish transition; record_event's internal flush lands it in the same
    # pending transaction as the status/approved_by/published_at writes above,
    # so the event and the state change are atomic (both commit or both roll
    # back with the caller's unit of work).
    # #VERIFY: tests/integration/test_pipeline_event_instrumentation.py::
    # test_approve_writes_released_event asserts exactly one "released" row.
    await record_event(
        session,
        Actor.from_principal(principal),
        entity_type="storybook",
        entity_id=storybook.id,
        event_type=EventType.RELEASED,
        from_state="in_review",
        to_state="published",
    )
    return version_row


async def send_back(
    session: AsyncSession,
    principal: Principal,
    storybook: Storybook,
    reason: str,
) -> None:
    """Send an in-review story back for revision, recording the reason.

    Args:
        session: The request session (caller owns the transaction).
        principal: The admin sending it back.
        storybook: The story being returned.
        reason: Why it was sent back (logged in slice 1; persisted in slice 2).

    Raises:
        StateTransitionError: If the story is not in ``in_review``.
    """
    # #ASSUME: data integrity: the reason is logged (not persisted) in slice 1;
    # slice 2 stores it on the moderation report.
    # #VERIFY: structured log carries storybook_id + reason + actor.
    storybook.status = assert_transition(
        Status(storybook.status), Action.SEND_BACK
    ).value
    _logger.info(
        "storybook_sent_back",
        storybook_id=storybook.id,
        reason=reason,
        actor=str(principal.user_id),
    )
    # #ASSUME: data-integrity: the send-back reason is logged above (structured
    # log, not persisted) but deliberately NOT copied into the event payload;
    # SENT_BACK's allowlist is empty (spec D3, PII-free payload contract), so
    # the storybook/version entity_id is the only durable reference to this
    # transition.
    # #VERIFY: tests/integration/test_pipeline_event_instrumentation.py::
    # test_send_back_writes_sent_back_event asserts payload == {}.
    await record_event(
        session,
        Actor.from_principal(principal),
        entity_type="storybook",
        entity_id=storybook.id,
        event_type=EventType.SENT_BACK,
        from_state="in_review",
        to_state="needs_revision",
    )


async def archive(
    session: AsyncSession, principal: Principal, storybook: Storybook
) -> None:
    """Archive a published story (removes it from the child-facing library).

    Args:
        session: The request session (caller owns the transaction).
        principal: The admin archiving it.
        storybook: The story being archived.

    Raises:
        StateTransitionError: If the story is not in ``published``.
    """
    # #CRITICAL: data integrity: archiving only flips status; the library read
    # path already excludes any status != "published".
    # #VERIFY: list query filters status == _PUBLISHED.
    storybook.status = assert_transition(Status(storybook.status), Action.ARCHIVE).value
    _logger.info(
        "storybook_archived", storybook_id=storybook.id, actor=str(principal.user_id)
    )
    await session.flush()
