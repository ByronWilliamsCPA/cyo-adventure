"""Unit tests for the publishing state machine (pure, no DB)."""

from __future__ import annotations

import pytest

from cyo_adventure.core.exceptions import StateTransitionError
from cyo_adventure.publishing.state_machine import (
    LEGAL_TRANSITIONS,
    STATES,
    assert_transition,
)

# Every legal hop: (from_state, action, expected_to_state).
_LEGAL = [
    ("draft", "submit", "in_review"),
    ("draft", "auto_reject", "needs_revision"),
    ("needs_revision", "submit", "in_review"),
    ("in_review", "approve", "published"),
    ("in_review", "send_back", "needs_revision"),
    ("published", "archive", "archived"),
]


@pytest.mark.parametrize(("current", "action", "expected"), _LEGAL)
def test_legal_transitions_return_target(
    current: str, action: str, expected: str
) -> None:
    """Each legal (state, action) returns its documented target state."""
    assert assert_transition(current, action) == expected


def test_legal_transitions_table_matches_cases() -> None:
    """The exported table contains exactly the legal hops under test."""
    assert {(c, a): t for c, a, t in _LEGAL} == dict(LEGAL_TRANSITIONS)


@pytest.mark.parametrize(("current", "action", "_expected"), _LEGAL)
def test_illegal_pairs_raise(current: str, action: str, _expected: str) -> None:
    """Every (state, action) not in the legal table raises StateTransitionError."""
    legal = {(c, a) for c, a, _ in _LEGAL}
    actions = {a for _, a, _ in _LEGAL}
    for state in STATES:
        for act in actions:
            if (state, act) in legal:
                continue
            with pytest.raises(StateTransitionError):
                assert_transition(state, act)


def test_unknown_action_raises() -> None:
    """An action outside the vocabulary raises rather than KeyError."""
    with pytest.raises(StateTransitionError):
        assert_transition("draft", "frobnicate")


def test_unknown_state_raises() -> None:
    """A state outside the vocabulary raises rather than KeyError."""
    with pytest.raises(StateTransitionError):
        assert_transition("nonexistent", "submit")
