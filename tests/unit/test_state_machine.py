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
    (Status.PUBLISHED, Action.RECALL, Status.IN_REVIEW),
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


def test_recall_moves_a_published_book_back_to_in_review() -> None:
    """`RS-C1`: the one hop that leaves a reader-facing state without ending it.

    Named separately from the parametrized sweep above because the state
    machine's docstring cites this test by name for the claim that recall is
    recoverable where archive is not.
    """
    assert assert_transition(Status.PUBLISHED, Action.RECALL) == Status.IN_REVIEW


def test_recall_is_not_a_second_exit_from_archived() -> None:
    """``archived`` stays absorbing; recall does not resurrect a dead book.

    The distinction recall exists to draw only holds if the two exits from
    ``published`` stay different in kind: archive ends the book's life, recall
    suspends it. Admitting ``(archived, recall)`` would collapse them.
    """
    with pytest.raises(StateTransitionError):
        assert_transition(Status.ARCHIVED, Action.RECALL)


def test_recall_does_not_change_which_statuses_are_remoderatable() -> None:
    """The re-moderation admission rule survives the new hop.

    ``api/remoderate.py::REMODERATABLE_STATUSES`` admits a status only when
    BOTH ``(status, SUBMIT)`` and ``(status, AUTO_REJECT)`` are absent from
    ``LEGAL_TRANSITIONS``, which is what makes that endpoint structurally
    unable to move a book. Adding a ``published`` hop keyed on a THIRD action
    leaves that rule intact, but the state machine's own comment claims so, and
    a claim about another module's admission rule has to be re-derived from the
    table rather than assumed.
    """
    from cyo_adventure.api.remoderate import REMODERATABLE_STATUSES

    for status in REMODERATABLE_STATUSES:
        assert (status, Action.SUBMIT) not in LEGAL_TRANSITIONS
        assert (status, Action.AUTO_REJECT) not in LEGAL_TRANSITIONS
    # And the converse: every status the rule would admit is actually listed,
    # so a newly added hop cannot silently widen or narrow the set without this
    # failing. `archived` is the deliberate exception the constant documents.
    admissible = {
        status
        for status in Status
        if (status, Action.SUBMIT) not in LEGAL_TRANSITIONS
        and (status, Action.AUTO_REJECT) not in LEGAL_TRANSITIONS
    }
    assert admissible - REMODERATABLE_STATUSES == {Status.ARCHIVED}


def test_recall_arrives_in_the_only_status_that_permits_auto_repair() -> None:
    """Pin the consequence the new hop actually has, so it cannot go unnoticed.

    ``api/remoderate.py::_allow_repair_for`` permits LLM auto-repair for
    ``in_review`` alone. Recall's target is ``in_review``, so a recalled book
    becomes repairable where, one action earlier, it was not. That is the state
    machine's documented intent; this test exists so a future reader sees the
    coupling stated as an executable fact rather than only in a comment.
    """
    from cyo_adventure.api.remoderate import _allow_repair_for

    target = assert_transition(Status.PUBLISHED, Action.RECALL)
    assert _allow_repair_for(target.value) is True
    assert _allow_repair_for(Status.PUBLISHED.value) is False
