"""Pure storybook lifecycle state machine.

A dependency-free transition table over ``storybook.status``. No DB, no I/O.
``assert_transition`` is the single source of truth for what hops are legal:

    draft --submit--> in_review --approve--> published --archive--> archived
      |                  |  ^
      └--auto_reject--┐  send_back │ submit (resubmit)
                      v  v
                   needs_revision

The ``draft --auto_reject--> needs_revision`` hop has no slice-1 caller; it
exists so the slice-2 moderation pipeline can route a hard-blocked story
without it ever passing through ``in_review`` or reaching a human.
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


class Action(StrEnum):
    """The lifecycle actions that drive a storybook between states."""

    SUBMIT = "submit"
    APPROVE = "approve"
    SEND_BACK = "send_back"
    ARCHIVE = "archive"
    AUTO_REJECT = "auto_reject"


# (from_state, action) -> to_state. Frozen; the single source of truth.
LEGAL_TRANSITIONS: Mapping[tuple[Status, Action], Status] = MappingProxyType(
    {
        (Status.DRAFT, Action.SUBMIT): Status.IN_REVIEW,
        (Status.DRAFT, Action.AUTO_REJECT): Status.NEEDS_REVISION,
        (Status.NEEDS_REVISION, Action.SUBMIT): Status.IN_REVIEW,
        (Status.IN_REVIEW, Action.APPROVE): Status.PUBLISHED,
        (Status.IN_REVIEW, Action.SEND_BACK): Status.NEEDS_REVISION,
        (Status.PUBLISHED, Action.ARCHIVE): Status.ARCHIVED,
    }
)


def assert_transition(current: Status, action: Action) -> Status:
    """Return the target state for a legal transition, or raise.

    Args:
        current: The storybook's current ``status``.
        action: The lifecycle action being attempted (``submit``, ``approve``,
            ``send_back``, ``archive``, ``auto_reject``).

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
