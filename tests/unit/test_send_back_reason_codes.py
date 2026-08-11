"""The closed send-back reason vocabulary and its domain-side guard.

Two things are under test here:

- ``publishing/reason_codes.py`` itself: the vocabulary, the derived set, and
  ``validate_reason_code``.
- That ``publishing/service.py::send_back`` actually applies the guard, and
  applies it *before* the state transition, so a rejected code cannot leave a
  storybook in ``needs_revision`` with no event explaining why.

Docker-independent: a mocked ``AsyncSession``, no real database, matching
``tests/unit/test_publishing_service_unit.py``.
"""

from __future__ import annotations

import uuid
from typing import get_args
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.api import schemas
from cyo_adventure.api.deps import Principal
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import Storybook
from cyo_adventure.publishing import service
from cyo_adventure.publishing.reason_codes import (
    SEND_BACK_REASON_CODES,
    SendBackReasonCodeLiteral,
    validate_reason_code,
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
        current_published_version=None,
    )


@pytest.mark.unit
def test_reason_code_set_matches_the_literal() -> None:
    """The derived set and the Literal cannot drift apart."""
    assert frozenset(get_args(SendBackReasonCodeLiteral)) == SEND_BACK_REASON_CODES
    assert len(SEND_BACK_REASON_CODES) == 10


@pytest.mark.unit
def test_api_schema_reexports_the_domain_vocabulary() -> None:
    """api/schemas.py names the same object, not a second copy of the list.

    A second copy would let the wire contract and the persisted payload drift,
    which is the exact failure the move into the domain exists to prevent.
    """
    assert schemas.SendBackReasonCodeLiteral is SendBackReasonCodeLiteral


@pytest.mark.unit
@pytest.mark.parametrize("code", sorted(SEND_BACK_REASON_CODES))
def test_validate_reason_code_accepts_every_vocabulary_member(code: str) -> None:
    """Every declared code passes and is returned unchanged."""
    assert validate_reason_code(code) == code


@pytest.mark.unit
def test_validate_reason_code_rejects_unknown_code() -> None:
    """An out-of-vocabulary code raises rather than reaching the event log."""
    with pytest.raises(ValidationError) as excinfo:
        validate_reason_code("looks_plausible_but_is_not_a_code")

    assert excinfo.value.details["field"] == "reason_code"


@pytest.mark.unit
@pytest.mark.parametrize("code", ["", "SAFETY_CONCERN", "safety concern"])
def test_validate_reason_code_rejects_near_misses(code: str) -> None:
    """Empty, wrong-case, and wrong-separator variants are all rejected.

    The vocabulary is matched exactly; nothing normalizes case or whitespace
    on the way in, so a caller cannot half-hit a code and get it stored.
    """
    with pytest.raises(ValidationError):
        validate_reason_code(code)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_back_rejects_unknown_reason_code() -> None:
    """send_back() applies the guard for callers that bypass the API layer."""
    story = _story("in_review")
    session = AsyncMock(spec=AsyncSession)
    principal = _principal("admin")

    with pytest.raises(ValidationError):
        await service.send_back(
            session,
            principal,
            story,
            "the ending does not land",
            reason_code="not_a_real_code",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_back_rejects_before_transitioning_the_storybook() -> None:
    """A rejected code leaves the storybook in_review and writes no event.

    Validating after the transition would strand a story in needs_revision
    with no SENT_BACK event to explain it, which is precisely the state the
    retention exemption keys on.
    """
    story = _story("in_review")
    session = AsyncMock(spec=AsyncSession)
    principal = _principal("admin")

    with pytest.raises(ValidationError):
        await service.send_back(
            session,
            principal,
            story,
            "the ending does not land",
            reason_code="not_a_real_code",
        )

    assert story.status == "in_review"
    session.add.assert_not_called()
    session.flush.assert_not_awaited()
