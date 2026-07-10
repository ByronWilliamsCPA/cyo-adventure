"""Storybook approval service: transitions that stamp provenance.

Each function wraps a state-machine transition and mutates ORM rows, and the
transaction is flushed before it returns: either directly via
``await session.flush()`` or indirectly through ``record_event``, which
flushes as part of writing the pipeline event row. The request unit-of-work
(api/deps.py) commits once at request end; these never commit. ``approve`` is
the ONLY path that may set ``status="published"``, and it always stamps
``approved_by`` in the same operation, which is the single-write-path leg of
the no-unapproved-publish invariant.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select

from cyo_adventure.core.exceptions import BusinessLogicError, ResourceNotFoundError
from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.events import Actor, EventType, record_event
from cyo_adventure.publishing.state_machine import Action, Status, assert_transition
from cyo_adventure.storybook.models import Storybook as StorybookDoc
from cyo_adventure.utils.logging import get_logger
from cyo_adventure.validator.series import validate_series

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.api.deps import Principal

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


async def _series_chain_docs(
    session: AsyncSession,
    storybook: Storybook,
    version_row: StorybookVersion,
) -> list[StorybookDoc] | None:
    """Load the parsed chain-so-far for a series approval, or None to skip.

    The chain is every sibling that retains a published version (including
    archived books, which keep ``current_published_version`` and their
    ``book_index`` slot; excluding them would break SR-2 contiguity and
    permanently block later approvals once any earlier book is archived) plus
    the version under approval. Grandfather rule (WS-G G4): if ANY chain member
    predates WS-G (no embedded series block) or no longer parses against the
    current schema, return None so the gate is skipped with a warning;
    approved blobs are immutable, so a legacy chain can never be made to
    pass and must not block new approvals.

    Args:
        session: The request session (caller owns the transaction).
        storybook: The story being approved.
        version_row: The version row under approval.

    Returns:
        list[StorybookDoc] | None: The parsed chain-so-far, or ``None`` when
        the gate must be skipped for a legacy or unparseable member.
    """
    siblings = (
        (
            await session.execute(
                select(StorybookVersion)
                .join(
                    Storybook,
                    (StorybookVersion.storybook_id == Storybook.id)
                    & (StorybookVersion.version == Storybook.current_published_version),
                )
                .where(
                    Storybook.series_id == storybook.series_id,
                    Storybook.id != storybook.id,
                    # #EDGE: data-integrity: archived siblings still occupy
                    # their book_index slot and there is no archived->published
                    # transition, so filtering on status=="published" would
                    # make SR-2 fail forever once an earlier book is archived.
                    # #VERIFY: test_archived_sibling_still_counts_in_chain.
                    Storybook.current_published_version.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    docs: list[StorybookDoc] = []
    for row in [*siblings, version_row]:
        try:
            doc = StorybookDoc.model_validate(row.blob)
        except PydanticValidationError:
            # A persisted (and for siblings, previously approved) blob failing
            # full schema parse signals data corruption or a schema regression,
            # never the expected legacy shape; log at ERROR with the parse
            # traceback so a systemic break that silently disables this gate is
            # distinguishable from the benign missing-series-block skip below.
            _logger.exception(
                "series_gate.skipped_unparseable_blob",
                storybook_id=row.storybook_id,
                version=row.version,
                series_id=str(storybook.series_id),
                approving_storybook_id=storybook.id,
            )
            return None
        if doc.metadata.series is None:
            _logger.warning(
                "series_gate.skipped_legacy_chain",
                storybook_id=row.storybook_id,
                version=row.version,
                series_id=str(storybook.series_id),
                approving_storybook_id=storybook.id,
            )
            return None
        docs.append(doc)
    return docs


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
        BusinessLogicError: With ``rule="approve_without_moderation"`` when
            the version has never been screened by the moderation pipeline
            (``moderation_report is None``), or with
            ``rule="series_validation"`` when chain-so-far series validation
            fails for a series book (legacy pre-WS-G chains are grandfathered
            and skip this check).
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
    # #ASSUME: data-integrity: the chain read and the approval write share the
    # session's transaction; siblings are selected by a non-null
    # current_published_version, so a chain member mid-approval in another
    # transaction is simply not yet part of the chain-so-far.
    # #EDGE: concurrency: two same-series approvals racing can make the later
    # gate read a stale chain and fail SR-2 spuriously; the admin retries
    # after the first commit. No cross-series lock is taken for this.
    # #VERIFY: test_out_of_order_approval_blocked_sr2 covers the sequential
    # equivalent of that ordering rule.
    if storybook.series_id is not None:
        chain = await _series_chain_docs(session, storybook, version_row)
        if chain is not None:
            series_report = validate_series(chain)
            if not series_report.ok:
                detail = "; ".join(f.message for f in series_report.errors)
                msg = f"series chain validation failed: {detail}"
                raise BusinessLogicError(msg, rule="series_validation")
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
