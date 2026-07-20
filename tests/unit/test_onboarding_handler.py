"""Unit test for the onboarding handler's first-login race recovery (P6-03).

A genuine two-request race on the ``authn_subject`` unique index is
impractical to interleave deterministically in a single-threaded test, so this
drives the exact recovery branch with a fake session that reproduces the real
sequence: the pre-read misses, the guardian INSERT raises the unique-index
``IntegrityError``, and the re-read returns the winner. The endpoint under test
is the real ``onboard`` coroutine; only the session is a double.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError
from starlette.responses import Response

from cyo_adventure.api.deps import OnboardingIdentity
from cyo_adventure.api.onboarding import onboard
from cyo_adventure.db.models import User

pytestmark = [pytest.mark.unit, pytest.mark.security]


class _FakeSavepoint:
    """Async context manager that never suppresses the raised exception."""

    async def __aenter__(self) -> _FakeSavepoint:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        # Mirror SQLAlchemy's begin_nested(): roll back the savepoint and let
        # the IntegrityError propagate to the endpoint's except branch.
        return False


@pytest.mark.asyncio
async def test_onboarding_race_returns_winner_not_500() -> None:
    """A lost first-login race returns the winner's row with a 200, never a 500."""
    # status="awaiting_approval" mirrors what a real _provision_guardian
    # insert sets explicitly (the self-signup approval track); this test
    # constructs the winner directly rather than through a real session
    # flush, so nothing else would populate it.
    winner = User(
        id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        role="guardian",
        authn_subject="raced-subject",
        status="awaiting_approval",
    )

    unique_violation = IntegrityError(
        'INSERT INTO "user" ...',
        {},
        Exception(
            'duplicate key value violates unique constraint "ix_user_authn_subject"'
        ),
    )

    session = MagicMock()
    session.add = MagicMock()
    session.begin_nested = MagicMock(return_value=_FakeSavepoint())
    # First scalar: the pre-insert read misses (row not yet visible). Second
    # scalar: the post-conflict re-read returns the committed winner.
    session.scalar = AsyncMock(side_effect=[None, winner])
    # First flush: the Family insert succeeds. Second flush: the guardian
    # User insert loses the race and raises the unique-index violation.
    session.flush = AsyncMock(side_effect=[None, unique_violation])

    response = Response()
    result = await onboard(
        identity=OnboardingIdentity(subject="raced-subject", email=None),
        session=session,
        response=response,
        body=None,
    )

    assert response.status_code == 200
    assert result.created is False
    assert result.user_id == str(winner.id)
    assert result.family_id == str(winner.family_id)


@pytest.mark.asyncio
async def test_onboarding_non_unique_integrity_error_propagates() -> None:
    """An integrity error that is not the authn_subject race is not swallowed."""
    session = MagicMock()
    session.add = MagicMock()
    session.begin_nested = MagicMock(return_value=_FakeSavepoint())
    session.scalar = AsyncMock(side_effect=[None])
    fk_violation = IntegrityError(
        "INSERT ...",
        {},
        Exception('violates foreign key constraint "user_family_id_fkey"'),
    )
    session.flush = AsyncMock(side_effect=[fk_violation])

    with pytest.raises(IntegrityError):
        await onboard(
            identity=OnboardingIdentity(subject="s", email=None),
            session=session,
            response=Response(),
            body=None,
        )
