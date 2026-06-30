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

from types import MappingProxyType
from typing import TYPE_CHECKING

from cyo_adventure.core.exceptions import StateTransitionError

if TYPE_CHECKING:
    from collections.abc import Mapping

# The five resting states of a storybook. ``approved`` is collapsed into the
# ``approve`` action (it is not a distinct resting state).
STATES: frozenset[str] = frozenset(
    {"draft", "in_review", "needs_revision", "published", "archived"}
)

# (from_state, action) -> to_state. Frozen; the single source of truth.
LEGAL_TRANSITIONS: Mapping[tuple[str, str], str] = MappingProxyType(
    {
        ("draft", "submit"): "in_review",
        ("draft", "auto_reject"): "needs_revision",
        ("needs_revision", "submit"): "in_review",
        ("in_review", "approve"): "published",
        ("in_review", "send_back"): "needs_revision",
        ("published", "archive"): "archived",
    }
)


def assert_transition(current: str, action: str) -> str:
    """Return the target state for a legal transition, or raise.

    Args:
        current: The storybook's current ``status``.
        action: The lifecycle action being attempted (``submit``, ``approve``,
            ``send_back``, ``archive``, ``auto_reject``).

    Returns:
        str: The resulting status if the transition is legal.

    Raises:
        StateTransitionError: If ``(current, action)`` is not a legal hop.
    """
    target = LEGAL_TRANSITIONS.get((current, action))
    if target is None:
        msg = f"cannot {action!r} a storybook in state {current!r}"
        raise StateTransitionError(
            msg,
            rule="invalid_state_transition",
            context={"from": current, "action": action},
        )
    return target
