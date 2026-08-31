"""Pure storybook lifecycle state machine.

A dependency-free transition table over ``storybook.status``. No DB, no I/O.
``assert_transition`` is the single source of truth for what hops are legal:

    draft --submit--> in_review --approve--> published --archive--> archived
      |                  |  ^                        |
      └--auto_reject--┐  send_back │ submit (resubmit)│
                      v  v         └-----recall-------┘
                   needs_revision

The ``draft --auto_reject--> needs_revision`` hop exists so the moderation
pipeline can route a hard-blocked story without it ever passing through
``in_review`` or reaching a human. It IS driven today, by
``moderation/pipeline.py`` on a classifier hard BLOCK; this docstring
previously said it had "no slice-1 caller", which went stale when slice 2
landed and was then relied on by a retention predicate that would have
preserved every machine-rejected story's raw output indefinitely.

``published --recall--> in_review`` (`RS-C1`) is the one hop that moves a book
BACKWARDS out of a reader-facing state without ending its life. It exists
because ``archive`` was previously the only exit from ``published`` and
``archived`` is absorbing, so a threshold change that invalidated a published
book's stored verdict left an owner with a choice between killing the book and
leaving it live. Recall is recoverable where archive is not: assignment rows
survive it (nothing keys on them for content access, only ``status`` does), so
re-approval restores the book to exactly the shelves it was on.

#CRITICAL: security: recall is NOT an incident-response tool, and neither is
archive. Both take effect server-side immediately, but a copy already
downloaded to a device is only evicted by the next successful ``/v1/library``
fetch (``frontend/src/offline/revocation.ts``, which reconciles on the online
path only; there is no push channel). A device that never reconnects keeps
reading. Anything that needs a hard, immediate pull needs a mechanism this
state machine does not have.
#VERIFY: tests/unit/test_state_machine.py::
test_recall_moves_a_published_book_back_to_in_review.

#CRITICAL: data-integrity: ``needs_revision`` therefore does NOT imply that a
human saw the story. Anything keying on "a reviewer decided" must key on the
``SENT_BACK`` pipeline event, which only ``publishing/service.py::send_back``
writes, never on this status.
#VERIFY: tests/unit/test_report_retention.py::
test_amendment_migration_exempts_send_back_via_event_not_status.
"""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

from cyo_adventure.core.exceptions import StateTransitionError

if TYPE_CHECKING:
    from collections.abc import Mapping


class Status(StrEnum):
    """The five resting states of a storybook.

    ``approved`` is collapsed into the ``approve`` action (it is not a distinct
    resting state). This closed enum is the application-boundary type for
    ``storybook.status``; coercing an ORM string through ``Status(...)`` rejects
    any value the database somehow holds outside this set.
    """

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    NEEDS_REVISION = "needs_revision"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Visibility(StrEnum):
    """Who may browse and assign a published book (WS-E, decision E1).

    Chosen by the admin at release approval and stored on ``storybook.visibility``.
    ``family`` restricts the book to its owning family; ``catalog`` shares it with
    every family's guardian browse-and-assign surface. Coercing the ORM string
    through ``Visibility(...)`` rejects any value outside this closed set.
    """

    FAMILY = "family"
    CATALOG = "catalog"


class Action(StrEnum):
    """The lifecycle actions that drive a storybook between states."""

    SUBMIT = "submit"
    APPROVE = "approve"
    SEND_BACK = "send_back"
    ARCHIVE = "archive"
    AUTO_REJECT = "auto_reject"
    RECALL = "recall"


# (from_state, action) -> to_state. Frozen; the single source of truth.
LEGAL_TRANSITIONS: Mapping[tuple[Status, Action], Status] = MappingProxyType(
    {
        (Status.DRAFT, Action.SUBMIT): Status.IN_REVIEW,
        (Status.DRAFT, Action.AUTO_REJECT): Status.NEEDS_REVISION,
        (Status.NEEDS_REVISION, Action.SUBMIT): Status.IN_REVIEW,
        (Status.IN_REVIEW, Action.APPROVE): Status.PUBLISHED,
        (Status.IN_REVIEW, Action.SEND_BACK): Status.NEEDS_REVISION,
        (Status.PUBLISHED, Action.ARCHIVE): Status.ARCHIVED,
        # #CRITICAL: security: this hop adds a SECOND arrival path into
        # ``in_review``, and one thing forks on that status:
        # ``api/remoderate.py::_allow_repair_for`` permits LLM auto-repair for
        # ``in_review`` and refuses it for ``published``. A recalled book is
        # therefore repairable where it was not a moment earlier. That is
        # intended and safe for the reason that allow-list already states: the
        # book is no longer reader-facing server-side and a human must approve
        # it again before it is. What it does NOT do is reach a copy already on
        # a device; that copy holds the previously approved prose, never the
        # repaired prose, because a repair writes a new version the device only
        # sees after a re-approval it cannot skip.
        # #VERIFY: tests/unit/test_remoderate_unit.py::
        # test_repair_is_refused_for_any_status_other_than_in_review pins the
        # fork; tests/unit/test_state_machine.py::
        # test_recall_does_not_change_which_statuses_are_remoderatable pins
        # that this hop leaves REMODERATABLE_STATUSES' admission rule intact.
        (Status.PUBLISHED, Action.RECALL): Status.IN_REVIEW,
    }
)


def assert_transition(current: Status, action: Action) -> Status:
    """Return the target state for a legal transition, or raise.

    Args:
        current: The storybook's current ``status``.
        action: The lifecycle action being attempted (``submit``, ``approve``,
            ``send_back``, ``archive``, ``auto_reject``, ``recall``).

    Returns:
        Status: The resulting status if the transition is legal.

    Raises:
        StateTransitionError: If ``(current, action)`` is not a legal hop. The
            client-facing message does not name the internal ``current`` state
            (CWE-209); the full detail is retained in ``context`` for the log.
    """
    target = LEGAL_TRANSITIONS.get((current, action))
    if target is None:
        msg = f"cannot {action!r} a storybook in its current state"
        raise StateTransitionError(
            msg,
            rule="invalid_state_transition",
            context={"from": current, "action": action},
        )
    return target
