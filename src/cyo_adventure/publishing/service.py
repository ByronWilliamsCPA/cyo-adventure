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

from cyo_adventure.core.exceptions import BusinessLogicError, ResourceNotFoundError
from cyo_adventure.db.models import StorybookVersion
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
    """
    # #CRITICAL: data integrity: status is the ORM boundary for the lifecycle;
    # assert_transition is the only gate that may change it. The ORM string is
    # coerced through Status() so an unmodeled DB status raises (closed-world).
    # #VERIFY: assert_transition raises StateTransitionError -> 409 on illegal hops.
    storybook.status = assert_transition(Status(storybook.status), Action.SUBMIT).value
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
    await session.flush()
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
    await session.flush()


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
