"""Unit tests for the publishing state machine (pure, no DB)."""

from __future__ import annotations

import pytest

from cyo_adventure.core.exceptions import StateTransitionError
from cyo_adventure.publishing.state_machine import (
    LEGAL_TRANSITIONS,
    Action,
    Status,
    assert_transition,
)

# Every legal hop: (from_state, action, expected_to_state).
_LEGAL = [
    (Status.DRAFT, Action.SUBMIT, Status.IN_REVIEW),
    (Status.DRAFT, Action.AUTO_REJECT, Status.NEEDS_REVISION),
    (Status.NEEDS_REVISION, Action.SUBMIT, Status.IN_REVIEW),
    (Status.IN_REVIEW, Action.APPROVE, Status.PUBLISHED),
    (Status.IN_REVIEW, Action.SEND_BACK, Status.NEEDS_REVISION),
    (Status.PUBLISHED, Action.ARCHIVE, Status.ARCHIVED),
]


@pytest.mark.parametrize(("current", "action", "expected"), _LEGAL)
def test_legal_transitions_return_target(
    current: Status, action: Action, expected: Status
) -> None:
    """Each legal (state, action) returns its documented target state."""
    assert assert_transition(current, action) == expected


def test_legal_transitions_table_matches_cases() -> None:
    """The exported table contains exactly the legal hops under test."""
    assert {(c, a): t for c, a, t in _LEGAL} == dict(LEGAL_TRANSITIONS)


def test_illegal_pairs_raise() -> None:
    """Every (state, action) not in the legal table raises StateTransitionError."""
    legal = {(c, a) for c, a, _ in _LEGAL}
    for state in Status:
        for action in Action:
            if (state, action) in legal:
                continue
            with pytest.raises(StateTransitionError):
                assert_transition(state, action)


def test_error_message_does_not_disclose_internal_state() -> None:
    """The client-facing message must not name the internal current state."""
    with pytest.raises(StateTransitionError) as exc_info:
        assert_transition(Status.DRAFT, Action.APPROVE)
    message = str(exc_info.value)
    assert "draft" not in message
    # The full detail is retained in details["context"] for the server log.
    assert exc_info.value.details["context"] == {
        "from": Status.DRAFT,
        "action": Action.APPROVE,
    }
