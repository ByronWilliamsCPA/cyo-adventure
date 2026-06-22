"""Unit tests for the auth seam and the session unit-of-work in api.deps."""

from __future__ import annotations

import uuid

import pytest

from cyo_adventure.api import deps
from cyo_adventure.api.deps import Principal
from cyo_adventure.core.exceptions import AuthenticationError


class _FakeSession:
    """A minimal async session double recording lifecycle calls."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        self.closed = True


def _principal(role: str, profiles: frozenset[uuid.UUID]) -> Principal:
    """Build a Principal for tests."""
    return Principal(
        subject="s",
        user_id=uuid.uuid4(),
        role=role,
        family_id=uuid.uuid4(),
        profile_ids=profiles,
    )


@pytest.mark.unit
def test_is_guardian_true_and_false() -> None:
    """The is_guardian property reflects the role."""
    assert _principal("guardian", frozenset()).is_guardian is True
    assert _principal("child", frozenset()).is_guardian is False


@pytest.mark.unit
def test_can_access_profile() -> None:
    """A principal can access only profiles in its set."""
    pid = uuid.uuid4()
    principal = _principal("child", frozenset({pid}))
    assert principal.can_access_profile(pid) is True
    assert principal.can_access_profile(uuid.uuid4()) is False


@pytest.mark.unit
def test_extract_subject_valid() -> None:
    """A well-formed bearer header yields the token."""
    assert deps._extract_subject("Bearer abc123") == "abc123"


@pytest.mark.unit
@pytest.mark.parametrize("header", [None, "Token abc", "Bearer ", "Bearer    "])
def test_extract_subject_rejects_bad_headers(header: str | None) -> None:
    """Missing, non-bearer, or empty tokens raise an authentication error."""
    with pytest.raises(AuthenticationError):
        deps._extract_subject(header)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_db_session_commits_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unit-of-work commits and closes when the request body succeeds."""
    fake = _FakeSession()
    monkeypatch.setattr(deps, "get_session", lambda: fake)
    agen = deps.get_db_session()
    session = await agen.__anext__()
    assert session is fake
    with pytest.raises(StopAsyncIteration):
        await agen.__anext__()
    assert fake.committed
    assert fake.closed
    assert not fake.rolled_back


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_db_session_rolls_back_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The unit-of-work rolls back and closes when the request body raises."""
    fake = _FakeSession()
    monkeypatch.setattr(deps, "get_session", lambda: fake)
    agen = deps.get_db_session()
    await agen.__anext__()
    with pytest.raises(ValueError, match="boom"):
        await agen.athrow(ValueError("boom"))
    assert fake.rolled_back
    assert fake.closed
    assert not fake.committed
