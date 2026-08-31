"""Storybook approval service: transitions that stamp provenance.

Each function wraps a state-machine transition and mutates ORM rows, and the
transaction is flushed before it returns: either directly via
``await session.flush()`` or indirectly through ``record_event``, which
flushes as part of writing the pipeline event row. The request unit-of-work
(api/deps.py) commits once at request end; these never commit. Within
``src/`` ``approve`` is the only path that sets ``status="published"``:
``publishing/catalog_publish.py`` promotes a catalog story by calling it
rather than by writing the column, and it always stamps ``approved_by`` in
the same operation, which is the single-write-path leg of the
no-unapproved-publish invariant.

The offline seed scripts are outside that guarantee. ``scripts/seed_staging.py``,
``scripts/seed_dev_data.py`` (two sites), and ``scripts/seed_series_catalog.py``
each construct a ``Storybook`` row with ``status="published"`` directly, and
each stamps ``approved_by`` in the same constructor, so those uphold the
invariant by convention rather than by routing through this module. A change
to what ``approve`` guarantees has to be mirrored there by hand.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select

from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    BusinessLogicError,
    ResourceNotFoundError,
)
from cyo_adventure.db.models import (
    GenerationJob,
    Storybook,
    StorybookVersion,
    StoryRequest,
)
from cyo_adventure.events import Actor, EventType, record_event
from cyo_adventure.moderation.report import (
    SevereFindingCounts,
    moderation_coverage_incomplete,
    moderation_report_unusable,
    severe_finding_counts,
)
from cyo_adventure.publishing.reason_codes import (
    validate_reason_code,
    validate_recall_reason_code,
)
from cyo_adventure.publishing.state_machine import (
    Action,
    Status,
    Visibility,
    assert_transition,
)
from cyo_adventure.storybook.models import Storybook as StorybookDoc
from cyo_adventure.utils.logging import get_logger
from cyo_adventure.validator.series import validate_series

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from cyo_adventure.api.deps import Principal

_logger = get_logger(__name__)

# #CRITICAL: security: the staging Moderation QA corpus
# (moderation-review-redesign-2026-07-28.md section 5) namespaces every
# fixture storybook id with this prefix precisely so a single string check
# can gate publishing everywhere it matters, regardless of how the id got
# into the approve() call (admin misclick, a future automation, a copy-pasted
# storybook id). See _reject_mqa_fixture_outside_staging below.
# #VERIFY: test_approve_rejects_mqa_fixture_outside_staging and
# test_approve_allows_mqa_fixture_in_staging in
# tests/unit/test_publishing_service_unit.py.
_MODERATION_QA_PREFIX = "mqa_"


def _reject_mqa_fixture_outside_staging(storybook_id: str) -> None:
    """Refuse to publish a Moderation QA fixture anywhere but staging.

    Defense in depth (moderation-review-redesign-2026-07-28.md section 5,
    point 3): the seed script (scripts/seed_moderation_qa.py) never calls
    approve/publish itself, and its own environment guard already prevents
    the fixtures from being inserted outside staging. This is the second,
    independent layer at the sole publish path itself, so an admin who
    somehow acquires an ``mqa_``-prefixed storybook row outside staging (a
    misclick, a copied id, a future automation) still cannot publish it.

    Args:
        storybook_id: The id of the storybook being approved.

    Raises:
        BusinessLogicError: If the id carries the ``mqa_`` containment prefix
            and the running environment is not ``staging``.
    """
    if (
        storybook_id.startswith(_MODERATION_QA_PREFIX)
        and settings.environment != "staging"
    ):
        msg = (
            f"cannot approve or publish moderation QA fixture '{storybook_id}' "
            f"outside staging (current environment: {settings.environment!r}); "
            "this id is reserved for deliberately off-band and bright-line "
            "test content that must never reach a real reader"
        )
        raise BusinessLogicError(msg, rule="mqa_fixture_outside_staging")


async def submit(session: AsyncSession, storybook: Storybook, *, actor: Actor) -> None:
    """Move a draft or needs-revision story into review.

    Args:
        session: The request session (caller owns the transaction).
        storybook: The story to submit.
        actor: Who caused the entry. ``Actor.system()`` for the moderation
            pipeline's own submit, a real principal for a human resubmitting
            a sent-back story. Required rather than defaulted so a new caller
            has to state which it is; a default would silently attribute a
            person's action to the machine.

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
    from_state = storybook.status
    storybook.status = target.value
    # No flush here: record_event flushes internally, so the status write and
    # the event row land in one round trip and one transaction, exactly as
    # approve() below does it. An explicit flush at this point bought no extra
    # atomicity (the caller's unit of work already spans both) and only split
    # one round trip into two.
    # #CRITICAL: data-integrity: this is the ONLY marker of a story entering the
    # review queue, and R-11 approval duration is measured from it. The
    # moderation pipeline's MODERATION_COMPLETED marks the first entry only;
    # a resubmission after a send-back re-runs no moderation, so without this
    # row every review round past the first has no start timestamp and its
    # duration is unrecoverable from the event log.
    # #VERIFY: test_resubmit_after_send_back_writes_submitted_event and
    # test_moderation_submit_stamps_the_system_actor in
    # tests/integration/test_pipeline_event_instrumentation.py.
    await record_event(
        session,
        actor,
        entity_type="storybook",
        entity_id=storybook.id,
        event_type=EventType.SUBMITTED,
        from_state=from_state,
        to_state=target.value,
    )


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


async def _stamp_resulting_storybook_id(
    session: AsyncSession, storybook: Storybook, version: int
) -> None:
    """Link the originating request to the just-published storybook (W0.4).

    Resolves the ``GenerationJob`` that produced this ``(storybook_id,
    version)`` pair to its ``concept_id``, then ``StoryRequest WHERE
    concept_id == that concept_id`` -- the same two-hop request -> concept ->
    job -> storybook resolution ``generation/worker.py::
    _stamp_request_interpretation`` already uses for the K19 interpretation
    write, reused here rather than adding a third way to walk that chain.

    Deliberately called only from :func:`approve`, the sole path that sets
    ``status="published"``: a story is fully moderated and human-approved by
    the time this stamp lands, so a kid who later sees a non-``None``
    ``resulting_storybook_id`` (``api/story_requests.py::_to_view``) never
    learns of an unpublished or rejected draft. Never re-stamped: a request
    produces at most one storybook in practice (a retry after failure
    creates a new ``GenerationJob``/``Storybook`` pair under the same
    ``concept_id``, but only the run that actually reaches ``approve()``
    calls this).

    Does NOT commit: the caller's terminal commit records it in the same
    transaction as the rest of ``approve()``'s writes.

    # #ASSUME: data-integrity: neither ``(GenerationJob.storybook_id,
    # GenerationJob.version)`` nor ``StoryRequest.concept_id`` carries a
    # unique constraint at the database level (mirroring the same gap
    # documented on ``_stamp_request_interpretation``); a genuinely
    # duplicated row would make ``scalar_one_or_none()`` raise
    # ``MultipleResultsFound`` and abort the publish rather than silently
    # stamping the wrong request. No try/except here, deliberately matching
    # ``_stamp_request_interpretation``'s own convention for this exact join:
    # fail loud on corrupted data instead of guessing.
    # #VERIFY: test_approve_stamps_resulting_storybook_id and
    # test_approve_resulting_storybook_id_noop_without_request in
    # tests/unit/test_publishing_service_unit.py.

    Args:
        session: The request session (caller owns the transaction).
        storybook: The story being approved.
        version: The version number being published.
    """
    concept_result = await session.execute(
        select(GenerationJob.concept_id).where(
            GenerationJob.storybook_id == storybook.id,
            GenerationJob.version == version,
        )
    )
    concept_id = concept_result.scalar_one_or_none()
    if concept_id is None:
        return
    request_result = await session.execute(
        select(StoryRequest).where(StoryRequest.concept_id == concept_id)
    )
    request_row = request_result.scalar_one_or_none()
    if request_row is None:
        return
    request_row.resulting_storybook_id = storybook.id


def _assert_report_permits_approval(
    *,
    storybook_id: str,
    version: int,
    version_row: StorybookVersion,
    override_reason: str | None,
) -> SevereFindingCounts:
    """Raise unless the stored moderation report permits approving this version.

    Four independent refusals, asked before any state changes, in increasing
    order of what they concede to the human reviewer: no report at all, a
    report with no genuine judgment in it, a report whose reviewer did not see
    every node, and finally a report carrying a severe finding, which a human
    MAY approve over but only with a recorded reason.

    Extracted from :func:`approve` rather than inlined: the four checks are one
    cohesive question about one artifact, and keeping them together is what
    makes "no unmoderated path reaches published" reviewable in a single place
    instead of spread through the transition logic.

    Args:
        storybook_id: The storybook being approved; named in all four
            refusal messages so a 400 identifies the refused artifact.
        version: The version being approved; likewise named in the messages.
        version_row: The loaded version row carrying ``moderation_report``.
        override_reason: The caller's justification, if any.

    Returns:
        SevereFindingCounts: The tallied severe findings, returned rather than
        recomputed by the caller so the audit log can only ever report the
        counts this gate actually judged.

    Raises:
        BusinessLogicError: On any of the four refusals, each with its own
            ``rule`` so callers can distinguish them.
    """
    # Interpolated into all four refusals below rather than deleted. The
    # parameters were previously dropped with a `del`, which satisfied Ruff's
    # unused-argument rule while leaving a docstring that claimed they were
    # "for the message only" and four messages that named no artifact. A 400
    # from a bulk approve is far more useful when it says WHICH version it
    # refused.
    subject = f"version {version} of storybook '{storybook_id}'"
    # #CRITICAL: security: closes C3-SAFETY Finding 2 (adversarial-safety-
    # evaluation.md): the admin submit endpoint (api/approval.py::submit_storybook)
    # can still move a draft straight to in_review without ever running
    # moderation (Finding 1 closed the import path's own unmoderated route; this
    # endpoint is untouched by that fix). This guard is the single choke point
    # (the sole publish path) that makes "no unmoderated path reaches published"
    # hold structurally, regardless of how many routes can reach in_review.
    # #VERIFY: test_approve_without_moderation_report_raises.
    if version_row.moderation_report is None:
        msg = f"cannot approve {subject}: it has never been screened by moderation"
        raise BusinessLogicError(msg, rule="approve_without_moderation")
    # #CRITICAL: security: a stored report can exist yet carry no genuine
    # content judgment: a mock-reviewer run (reviewer_independent=False) or a
    # legacy report whose findings are all fail-safe/structural artifacts.
    # moderation_report_unusable() (moderation/report.py, Task 1) is the
    # shared predicate for that check; approve() is its first consumer.
    # #VERIFY: test_approve_fail_safe_report_returns_400.
    if moderation_report_unusable(version_row.moderation_report):
        msg = (
            f"cannot approve {subject}: the stored moderation report contains "
            "no genuine content judgment (fail-safe or mock-reviewer artifacts "
            "only); re-run moderation for this version first"
        )
        raise BusinessLogicError(msg, rule="approve_with_unusable_moderation")
    # #CRITICAL: security: a coverage gap is not a verdict, so it is checked
    # here and NOT left to the D2 override gate below. D2 lets a human approve
    # OVER an automated block or high-severity flag with a recorded reason,
    # which is right when a judgment exists and the human disagrees with it.
    # An unreviewed node carries no judgment to disagree with, so an override
    # reason would be justifying a decision nobody made. Before this gate, a
    # report naming eight nodes the reviewer never saw approved with HTTP 200
    # under any non-empty reason, because the unusable-report predicate above
    # is all-or-nothing: one genuine finding beside the gap made the whole
    # report read as usable. Four books in the live catalog held that shape.
    # #VERIFY: the test named
    # test_approve_with_unreviewed_nodes_returns_400_even_with_a_reason, in
    # tests/integration/test_approval_api.py, supplies a valid override_reason
    # precisely to prove D2 is not what stops the request.
    if moderation_coverage_incomplete(version_row.moderation_report):
        msg = (
            f"cannot approve {subject}: the stored moderation report admits "
            "the reviewer never saw part of this story (incomplete coverage). "
            "An override reason cannot substitute for a judgment that was "
            "never made; re-run moderation for this version first"
        )
        raise BusinessLogicError(msg, rule="approve_with_incomplete_coverage")
    # #CRITICAL: security: ADR-005 amendment (2026-08-25, gate D2): a human
    # remains free to approve over an automated block or high-severity flag,
    # but only with a recorded justification, so silent overrides end while
    # the human stays the final authority. severe_finding_counts()
    # (moderation/report.py, Task 1) never counts advisories, matching the
    # SOP contract that advisories never gate.
    # #VERIFY: test_approve_over_block_without_reason_returns_400 and
    # test_approve_over_block_with_reason_publishes_and_audits in
    # tests/integration/test_approval_api.py.
    severe_counts = severe_finding_counts(version_row.moderation_report)
    # #ASSUME: data-integrity: a whitespace-only override_reason ("   ") must
    # not satisfy this gate. Truthiness alone accepts any non-empty string,
    # including one that carries no actual justification once stripped;
    # requiring a non-empty stripped value keeps the audit log's free-text
    # reason meaningful rather than a rubber stamp.
    # For API callers this is now a backstop: ApproveBody strips before its
    # own min_length check, so a whitespace-only reason fails validation with
    # 422 before reaching here. It is still the ONLY such guard for callers
    # that never build an ApproveBody, which now includes
    # publishing/catalog_publish.py's CLI; do not remove it as redundant.
    # #VERIFY: tests/integration/test_approval_api.py::
    # test_approve_over_block_with_whitespace_only_reason_returns_422.
    if (severe_counts.block_count or severe_counts.high_severity_flag_count) and not (
        override_reason and override_reason.strip()
    ):
        msg = (
            f"approving {subject} over a block or high-severity finding "
            "requires an override reason; it is recorded in the audit log"
        )
        raise BusinessLogicError(msg, rule="approve_requires_override_reason")
    return severe_counts


async def approve(
    session: AsyncSession,
    principal: Principal,
    storybook: Storybook,
    version: int,
    *,
    visibility: Visibility = Visibility.FAMILY,
    override_reason: str | None = None,
) -> StorybookVersion:
    """Approve and publish a specific version, stamping approval provenance.

    Args:
        session: The request session (caller owns the transaction).
        principal: The approving admin.
        storybook: The story being approved.
        version: The version number to publish.
        visibility: Who may browse/assign the published book (WS-E E2);
            defaults to family.
        override_reason: Required when the stored report carries a block or
            high-severity finding (``severe_finding_counts``); free text an
            admin types to justify approving over it. Logged, never
            persisted on the ``RELEASED`` audit event: ``events/writer.py``'s
            payload allowlist is PII-free by contract (spec D3), so only the
            structured overridden-finding counts are recorded there, mirroring
            how ``send_back`` below keeps its own free-text ``reason``
            log-only and persists only the closed-vocabulary ``reason_code``.

    Returns:
        StorybookVersion: The stamped version row.

    Raises:
        AuthorizationError: If ``principal`` does not hold the admin
            capability. Both current callers already gate on this before
            reaching here (see the #CRITICAL note below); this is a
            defense-in-depth re-check at the service boundary itself.
        StateTransitionError: If the story is not in ``in_review``.
        ResourceNotFoundError: If the version row does not exist.
        BusinessLogicError: With ``rule="approve_without_moderation"`` when
            the version has never been screened by the moderation pipeline
            (``moderation_report is None``), with
            ``rule="approve_with_unusable_moderation"`` when the stored
            report carries no genuine content judgment (fail-safe or
            mock-reviewer artifacts only), with
            ``rule="approve_requires_override_reason"`` when the report
            carries a block or high-severity finding and no
            ``override_reason`` was given, or with ``rule="series_validation"``
            when chain-so-far series validation fails for a series book
            (legacy pre-WS-G chains are grandfathered and skip this check).
    """
    # #CRITICAL: security: within src/ this is the sole path that sets
    # status="published" (catalog_publish.py calls it rather than writing the
    # column), and it stamps approved_by in the same operation, so no story
    # reaches a reader without a recorded approver (the slice-1 invariant).
    # The four offline seed sites named in this module's docstring write the
    # column directly and uphold the invariant only by convention.
    # #VERIFY: test_no_publish_without_approver drives every endpoint path. No
    # test covers the seed scripts' direct writes, so widening this invariant
    # means auditing those four sites by hand.
    # #CRITICAL: security: approve() now has two privileged callers --
    # api/approval.py::approve_storybook (HTTP, gated by
    # ctx.principal.is_admin in _load_admin_story) and
    # publishing/catalog_publish.py::promote_catalog_story (a standalone CLI
    # that mirrors the same admin check in its own _load_admin_principal).
    # Both callers already verify admin status before reaching here, but
    # relying solely on caller discipline means a future caller (or a bug in
    # an existing one) could skip that gate silently. This re-check enforces
    # the authorization invariant at the service boundary itself, so
    # "non-admin cannot publish" holds structurally regardless of how many
    # callers this function grows.
    # #VERIFY: test_approve_rejects_a_non_admin_principal in
    # tests/unit/test_publishing_service_unit.py.
    if not principal.is_admin:
        msg = "admin role required to approve a storybook"
        raise AuthorizationError(msg, required_permission="admin")
    _reject_mqa_fixture_outside_staging(storybook.id)
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
    severe_counts = _assert_report_permits_approval(
        storybook_id=storybook.id,
        version=version,
        version_row=version_row,
        override_reason=override_reason,
    )
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
    # #CRITICAL: security: visibility is stamped ONLY here, inside the sole
    # publish path, so the release transition and the sharing decision are
    # atomic (WS-E decision E2). A catalog value widens who can assign this
    # book (E5); it must never be settable outside an admin-gated approve.
    # #VERIFY: both callers are admin-gated (api/approval.py::approve_storybook
    # via ctx.principal.is_admin, and catalog_publish.py::promote_catalog_story
    # via its own _load_admin_principal), and the is_admin re-check near the
    # top of this function is now the third, service-level enforcement point.
    storybook.visibility = visibility.value
    version_row.approved_by = principal.user_id
    version_row.published_at = datetime.now(UTC)
    # #CRITICAL: data integrity: approve() deliberately does NOT null
    # GenerationJob.report. It used to, under ADR-007's original "immediately on
    # publish" rule, and that UPDATE was removed by ADR-007's 2026-08-11
    # amendment. Retention of a human-reviewed job's raw output is now decided in
    # exactly one place, the purge predicate in
    # 20260810000000_exempt_reviewed_generation_job_report_from_purge.sql, which
    # exempts a job whose storybook reached "published"/"archived" or carries a
    # sent_back pipeline_event. Nulling here defeated the approve half of that
    # exemption completely: the sweep spares a published book's report and this
    # UPDATE had already destroyed it, so the calibration corpus the exemption
    # exists to build could never contain an approval. Do not reintroduce a purge
    # on this path; change the migration's predicate instead, so retention stays
    # readable from one predicate rather than from a predicate minus a side
    # effect.
    # #VERIFY: test_approve_does_not_purge_generation_job_report and
    # test_approve_issues_no_update_statements in
    # tests/unit/test_report_retention.py assert this path emits no UPDATE at
    # all, which is the assertion that fails if the purge comes back.
    # #CRITICAL: data-integrity: W0.4 -- stamp story_request.resulting_
    # storybook_id in the same flush as the status/approved_by/published_at
    # writes above, so a rollback of the publish also rolls back the stamp
    # (both-or-neither). This used to read "mirroring the report-nulling UPDATE
    # just above"; that UPDATE was removed by ADR-007's 2026-08-11 amendment, so
    # the writes it mirrored are the three field assignments above instead.
    # #VERIFY: test_approve_stamps_resulting_storybook_id in
    # tests/unit/test_publishing_service_unit.py.
    await _stamp_resulting_storybook_id(session, storybook, version)
    # #CRITICAL: data-integrity: this is the WS-D event-log record of the
    # publish transition; record_event's internal flush lands it in the same
    # pending transaction as the status/approved_by/published_at writes above,
    # so the event and the state change are atomic (both commit or both roll
    # back with the caller's unit of work).
    # #VERIFY: tests/integration/test_pipeline_event_instrumentation.py::
    # test_approve_writes_released_event asserts exactly one "released" row.
    # #CRITICAL: security: stamp the persona the caller actually acted as, not
    # a blanket "admin". acting_role() returns the guardian base role when the
    # caller is reviewing their OWN family's content (the owner-as-admin
    # exception, ADR-005) and admin only for a genuine cross-family review, so
    # the audit log distinguishes self-review from four-eyes review.
    # #VERIFY: test_dual_role_{same,foreign}_family_publish_stamps_* in
    # tests/integration/test_pipeline_event_instrumentation.py.
    payload: dict[str, object] = {"visibility": visibility.value}
    if severe_counts.block_count or severe_counts.high_severity_flag_count:
        # #CRITICAL: security: RELEASED's payload is PII-free by contract
        # (events/writer.py's _PAYLOAD_ALLOWLIST, spec D3), so the free-text
        # override_reason an admin typed is logged here, never persisted on
        # the durable append-only event row; only the structured counts of
        # what was overridden are audited, mirroring send_back()'s own
        # free-text reason staying log-only below.
        _logger.info(
            "storybook_approved_over_severe_finding",
            storybook_id=storybook.id,
            version=version,
            overridden_block_count=severe_counts.block_count,
            overridden_high_count=severe_counts.high_severity_flag_count,
            override_reason=override_reason.strip()
            if override_reason
            else override_reason,
            actor=str(principal.user_id),
        )
        payload["overridden_block_count"] = severe_counts.block_count
        payload["overridden_high_count"] = severe_counts.high_severity_flag_count
    await record_event(
        session,
        Actor.from_principal(
            principal, acting_role=principal.acting_role(storybook.family_id).value
        ),
        entity_type="storybook",
        entity_id=storybook.id,
        event_type=EventType.RELEASED,
        from_state="in_review",
        to_state="published",
        payload=payload,
    )
    return version_row


async def send_back(
    session: AsyncSession,
    principal: Principal,
    storybook: Storybook,
    reason: str,
    *,
    reason_code: str,
) -> None:
    """Send an in-review story back for revision, recording the reason.

    Args:
        session: The request session (caller owns the transaction).
        principal: The admin sending it back.
        storybook: The story being returned.
        reason: Why it was sent back (free text; logged, not persisted).
        reason_code: Calibration code for why it was sent back, persisted on
            the SENT_BACK pipeline event so it is queryable later. Must be a
            member of ``reason_codes.SEND_BACK_REASON_CODES``; this function
            validates it, so the closed vocabulary holds for every caller and
            not only for requests that arrive through the API boundary.

    Raises:
        StateTransitionError: If the story is not in ``in_review``.
        core.exceptions.ValidationError: If ``reason_code`` is outside the
            closed vocabulary. Qualified deliberately: the only ``ValidationError``
            name bound in this module is pydantic's, imported as
            ``PydanticValidationError``, so a bare ``ValidationError`` here would
            read as that one. ``validate_reason_code`` raises the project's.
    """
    # Validate before the state transition, so a bad code cannot leave the
    # storybook in needs_revision with no event written to explain it.
    checked_reason_code = validate_reason_code(reason_code)
    # #ASSUME: data integrity: the free-text reason is logged (not persisted)
    # as before; reason_code is the structured calibration signal, persisted
    # below on the event row.
    # #VERIFY: structured log carries storybook_id + reason + reason_code + actor.
    storybook.status = assert_transition(
        Status(storybook.status), Action.SEND_BACK
    ).value
    _logger.info(
        "storybook_sent_back",
        storybook_id=storybook.id,
        reason=reason,
        reason_code=checked_reason_code,
        actor=str(principal.user_id),
    )
    # #CRITICAL: data-integrity: reason_code is the review-scorecard
    # calibration corpus's structured label (closed vocabulary, D3-compliant:
    # an enum value, never free text), so it is persisted on the SENT_BACK
    # event's payload, not just logged. The free-text `reason` stays
    # log-only, unchanged from before.
    # #VERIFY: tests/integration/test_pipeline_event_instrumentation.py::
    # test_send_back_writes_sent_back_event asserts
    # payload == {"reason_code": ...}.
    # #CRITICAL: security: same own-family-aware persona stamping as the
    # RELEASED event above; send-back is a review action too, so an owner
    # sending back their own family's story records guardian, not admin.
    # #VERIFY: test_dual_role_{same,foreign}_family_send_back_stamps_* in
    # tests/integration/test_pipeline_event_instrumentation.py.
    await record_event(
        session,
        Actor.from_principal(
            principal, acting_role=principal.acting_role(storybook.family_id).value
        ),
        entity_type="storybook",
        entity_id=storybook.id,
        event_type=EventType.SENT_BACK,
        from_state="in_review",
        to_state="needs_revision",
        payload={"reason_code": checked_reason_code},
    )


async def recall(
    session: AsyncSession,
    principal: Principal,
    storybook: Storybook,
    *,
    reason_code: str,
) -> None:
    """Recall a published story back to the human review gate (`RS-C1`).

    The recoverable counterpart of ``archive``. Both remove the book from every
    child-facing read path immediately, because every one of those paths gates
    on ``status == "published"`` and nothing else: the shelf query
    (``api/library.py``), the single-book read (same module), the reader
    (``api/reading.py``), the recommendation candidate set
    (``api/recommendations.py``), and new assignments (``api/assignments.py``).
    The difference is what survives: ``archived`` is absorbing, while a recalled
    book sits in ``in_review`` where the ordinary approve path can publish it
    again, and its assignment rows are untouched either way, so re-approval puts
    it back on exactly the shelves it left.

    Args:
        session: The request session (caller owns the transaction).
        principal: The admin recalling it.
        storybook: The published story being recalled.
        reason_code: Why it is being recalled. Must be a member of
            ``reason_codes.RECALL_REASON_CODES``; validated here so the closed
            vocabulary holds for every caller, not only for requests arriving
            through the API boundary. Persisted on the STORYBOOK_RECALLED event,
            and read by the guardian-notification composer to decide severity.

    Raises:
        StateTransitionError: If the story is not in ``published``.
        core.exceptions.ValidationError: If ``reason_code`` is outside the
            closed recall vocabulary. Qualified for the same reason
            ``send_back``'s docstring gives: the only bare ``ValidationError``
            bound in this module is pydantic's.
    """
    # Validate before the transition, so a bad code cannot leave a book out of
    # the library with no event written to explain why (send_back's ordering,
    # and the stakes here are higher: this one was reader-facing).
    checked_reason_code = validate_recall_reason_code(reason_code)
    # #CRITICAL: security: this does NOT reach an offline copy already on a
    # device. `frontend/src/offline/revocation.ts` evicts a book only when a
    # later successful `/v1/library` fetch no longer lists it, and there is no
    # push channel, so a device that stays offline keeps reading the version it
    # has. Recall does not introduce that window (archive has always had it),
    # but it must not be documented, surfaced, or messaged as an immediate pull.
    # #VERIFY: tests/unit/test_notifications_registry.py::
    # test_recall_notification_does_not_claim_offline_copies_are_gone asserts
    # the guardian-facing copy states the online-reconciliation condition.
    storybook.status = assert_transition(Status(storybook.status), Action.RECALL).value
    _logger.info(
        "storybook_recalled",
        storybook_id=storybook.id,
        reason_code=checked_reason_code,
        actor=str(principal.user_id),
    )
    # #CRITICAL: data-integrity: `current_published_version` is deliberately
    # LEFT SET, exactly as `archive` leaves it. It is not an access grant:
    # every read path ANDs it with `status == "published"`, so it grants
    # nothing on its own. Clearing it would instead break the surfaces that
    # legitimately need to know which version was the published one, including
    # `story_requests/anchoring.py` (series continuity reads the published
    # sibling), `moderation/rescreen.py` (which errors out on a published book
    # with no such version), and the guardian device-download inventory. The
    # re-approval writes the column again anyway.
    # #VERIFY: tests/integration/test_recall_api.py::
    # test_recall_leaves_current_published_version_set and
    # ::test_a_recalled_book_leaves_every_child_facing_surface.
    # #CRITICAL: security: same own-family-aware persona stamping as
    # approve()/send_back()/archive(): an owner recalling their own family's
    # story is stamped guardian (ADR-005 owner-as-admin exception), a genuine
    # cross-family recall is stamped admin.
    # #VERIFY: tests/integration/test_pipeline_event_instrumentation.py::
    # test_recall_writes_storybook_recalled_event.
    await record_event(
        session,
        Actor.from_principal(
            principal, acting_role=principal.acting_role(storybook.family_id).value
        ),
        entity_type="storybook",
        entity_id=storybook.id,
        event_type=EventType.STORYBOOK_RECALLED,
        from_state="published",
        to_state="in_review",
        payload={"reason_code": checked_reason_code},
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
    # #CRITICAL: security/data-integrity: this is the WS-D event-log record of
    # A5's incident/pull-everywhere path (docs/planning/capability-register.md):
    # archive() is the sole published->archived hop (state_machine.py), so this
    # is the one place a "content actually got pulled" fact can be recorded.
    # notifications/registry.py's composer turns it into an alert-severity
    # guardian notification (G10 delivery infra); the frontend needs no new
    # change, offline/revocation.ts already reconciles against the shelf
    # response on the next fetch. record_event's internal flush replaces the
    # standalone flush this function used to end with, same as
    # approve()/send_back() above.
    # #VERIFY: tests/integration/test_pipeline_event_instrumentation.py::
    # test_archive_writes_storybook_archived_event.
    # #CRITICAL: security: same own-family-aware persona stamping as
    # approve()/send_back(): an owner archiving their own family's story is
    # stamped guardian (ADR-005 owner-as-admin exception), a genuine
    # cross-family archive is stamped admin.
    # #VERIFY: test_dual_role_{same,foreign}_family_archive_stamps_* pattern,
    # mirroring the existing approve/send_back coverage in
    # tests/integration/test_pipeline_event_instrumentation.py.
    await record_event(
        session,
        Actor.from_principal(
            principal, acting_role=principal.acting_role(storybook.family_id).value
        ),
        entity_type="storybook",
        entity_id=storybook.id,
        event_type=EventType.STORYBOOK_ARCHIVED,
        from_state="published",
        to_state="archived",
    )
