"""The closed recall reason vocabulary, its guard, and the quiet allow-list.

Three things are under test here, mirroring
``tests/unit/test_send_back_reason_codes.py``:

- ``publishing/reason_codes.py``'s recall half: the vocabulary, the derived
  set, ``QUIET_RECALL_REASON_CODES``, and ``validate_recall_reason_code``.
- That ``publishing/service.py::recall`` applies the guard, and applies it
  *before* the state transition, so a rejected code cannot pull a book out of
  every child's library with no event written to explain why.
- That the two vocabularies stay separate sets. A shared list would let a
  recall be labelled with a drafting critique, or a send-back with a reason
  only a published book can have, and both land on an append-only event.

Docker-independent: a mocked ``AsyncSession``, no real database.
"""

from __future__ import annotations

import uuid
from typing import get_args
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.api import schemas
from cyo_adventure.api.deps import Principal
from cyo_adventure.core.exceptions import StateTransitionError, ValidationError
from cyo_adventure.db.models import Storybook
from cyo_adventure.publishing import service
from cyo_adventure.publishing.reason_codes import (
    QUIET_RECALL_REASON_CODES,
    RECALL_REASON_CODES,
    SEND_BACK_REASON_CODES,
    RecallReasonCodeLiteral,
    validate_recall_reason_code,
)

# No module-level asyncio mark: this module mixes sync and async tests, and a
# module-level mark applied to a sync test raises a PytestWarning that this
# project's filterwarnings = ["error"] turns into a failure (tests/CLAUDE.md).


def _principal(role: str) -> Principal:
    """Build a minimal Principal with the given role."""
    return Principal(
        subject=f"{role}-x",
        user_id=uuid.uuid4(),
        role=role,
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
    )


def _story(status: str) -> Storybook:
    """Construct a Storybook ORM instance without a session."""
    return Storybook(
        id="s1",
        family_id=uuid.uuid4(),
        status=status,
        current_published_version=3,
    )


@pytest.mark.unit
def test_recall_reason_code_set_matches_the_literal() -> None:
    """The derived set and the Literal cannot drift apart."""
    assert frozenset(get_args(RecallReasonCodeLiteral)) == RECALL_REASON_CODES
    assert len(RECALL_REASON_CODES) == 5


@pytest.mark.unit
def test_api_schema_reexports_the_domain_recall_vocabulary() -> None:
    """api/schemas.py names the same object, not a second copy of the list."""
    assert schemas.RecallReasonCodeLiteral is RecallReasonCodeLiteral


@pytest.mark.unit
@pytest.mark.parametrize("code", sorted(RECALL_REASON_CODES))
def test_validate_recall_reason_code_accepts_every_vocabulary_member(
    code: str,
) -> None:
    """Every declared code passes and is returned unchanged."""
    assert validate_recall_reason_code(code) == code


@pytest.mark.unit
def test_validate_recall_reason_code_rejects_unknown_code() -> None:
    """An out-of-vocabulary code raises rather than reaching the event log."""
    with pytest.raises(ValidationError) as excinfo:
        validate_recall_reason_code("looks_plausible_but_is_not_a_code")

    assert excinfo.value.details["field"] == "reason_code"


@pytest.mark.unit
def test_a_send_back_code_is_not_a_valid_recall_code() -> None:
    """The two vocabularies are separate sets, and the guards enforce that.

    ``unsatisfying_ending`` is a real send-back code and a nonsense recall
    reason: it critiques a draft, and cannot motivate pulling a live book. If
    the vocabularies were ever merged, this is the assertion that fails.
    """
    assert "unsatisfying_ending" in SEND_BACK_REASON_CODES
    with pytest.raises(ValidationError):
        validate_recall_reason_code("unsatisfying_ending")


@pytest.mark.unit
def test_a_recall_code_is_not_a_valid_send_back_code() -> None:
    """The separation holds in both directions.

    Asserted both ways deliberately: a one-sided check passes even if one
    vocabulary becomes a superset of the other, which is exactly how two
    "separate" lists quietly merge.
    """
    from cyo_adventure.publishing.reason_codes import validate_reason_code

    assert "threshold_change" in RECALL_REASON_CODES
    with pytest.raises(ValidationError):
        validate_reason_code("threshold_change")


@pytest.mark.unit
def test_the_two_vocabularies_overlap_only_where_intended() -> None:
    """The overlap is exactly ``safety_concern`` plus the shared escape hatch.

    Pinned as a set equality rather than as two membership checks: a new member
    added to one vocabulary that happens to already exist in the other is the
    drift this catches, and a membership check would not see it.
    """
    expected_overlap = {"safety_concern", "other"}
    assert expected_overlap == RECALL_REASON_CODES & SEND_BACK_REASON_CODES


@pytest.mark.unit
def test_the_quiet_set_is_a_subset_of_the_vocabulary() -> None:
    """A quiet reason that is not a real reason would never be reachable.

    Without this, a typo in ``QUIET_RECALL_REASON_CODES`` would silently make
    every recall alert-severity, which fails safe but is not what was intended
    and would be invisible.
    """
    assert QUIET_RECALL_REASON_CODES < RECALL_REASON_CODES


@pytest.mark.unit
def test_every_reason_outside_the_quiet_set_alerts() -> None:
    """The severity rule is an allow-list, so unknown reasons alert.

    Asserted at the set level rather than through the composer so the invariant
    is stated where the sets are defined; the composer's own behaviour is
    covered in tests/unit/test_notifications_registry.py.
    """
    loud = RECALL_REASON_CODES - QUIET_RECALL_REASON_CODES
    assert loud == {"threshold_change", "safety_concern", "other"}
    assert "safety_concern" not in QUIET_RECALL_REASON_CODES


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recall_rejects_unknown_reason_code() -> None:
    """recall() applies the guard for callers that bypass the API layer.

    The motivating caller for recall is a threshold-change sweep script, which
    reaches the service directly and never sees pydantic.
    """
    story = _story("published")
    session = AsyncMock(spec=AsyncSession)
    # Built outside the raises block so the block holds exactly one call: a
    # second construction call inside it could be what raised (S5778).
    principal = _principal("admin")

    with pytest.raises(ValidationError):
        await service.recall(session, principal, story, reason_code="not_a_real_code")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recall_rejects_before_transitioning_the_storybook() -> None:
    """A rejected code leaves the book published and writes no event.

    Validating after the transition would strand a book in ``in_review``,
    invisible to every child who had it, with nothing in the event log to say
    why or to point at whoever did it.
    """
    story = _story("published")
    session = AsyncMock(spec=AsyncSession)
    # Built outside the raises block so the block holds exactly one call: a
    # second construction call inside it could be what raised (S5778).
    principal = _principal("admin")

    with pytest.raises(ValidationError):
        await service.recall(session, principal, story, reason_code="not_a_real_code")

    assert story.status == "published"
    session.add.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recall_transitions_and_keeps_the_published_version() -> None:
    """The happy path: status moves, current_published_version is untouched."""
    story = _story("published")
    session = AsyncMock(spec=AsyncSession)

    await service.recall(
        session, _principal("admin"), story, reason_code="threshold_change"
    )

    assert story.status == "in_review"
    assert story.current_published_version == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_recall_refuses_a_book_that_is_not_published() -> None:
    """Only a published book can be recalled; the rest raise, not silently pass."""
    principal = _principal("admin")

    for status in ("draft", "in_review", "needs_revision", "archived"):
        story = _story(status)
        session = AsyncMock(spec=AsyncSession)
        with pytest.raises(StateTransitionError):
            await service.recall(session, principal, story, reason_code="curation")
        assert story.status == status
