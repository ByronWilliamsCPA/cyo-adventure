"""Integration tests for is_enabled_allowlist_pair (needs a real session)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import ProviderModelAllowlist
from cyo_adventure.generation.allowlist import is_enabled_allowlist_pair

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_enabled_pair_is_enabled(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """An enabled row for the exact pair returns True."""
    async with sessions() as session:
        session.add(
            ProviderModelAllowlist(
                provider="anthropic", model_id="claude-sonnet-4-6", enabled=True
            )
        )
        await session.commit()
        assert await is_enabled_allowlist_pair(
            session, "anthropic", "claude-sonnet-4-6"
        )


async def test_disabled_pair_is_not_enabled(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A disabled row for the exact pair returns False, not a stale True."""
    async with sessions() as session:
        session.add(
            ProviderModelAllowlist(
                provider="anthropic", model_id="claude-sonnet-4-6", enabled=False
            )
        )
        await session.commit()
        assert not await is_enabled_allowlist_pair(
            session, "anthropic", "claude-sonnet-4-6"
        )


async def test_unknown_pair_is_not_enabled(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A pair with no row at all returns False (never raises)."""
    async with sessions() as session:
        assert not await is_enabled_allowlist_pair(
            session, "anthropic", "not-a-real-model"
        )


async def test_mock_is_never_a_row_and_therefore_never_enabled(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """mock has no allowlist row (the CHECK forbids inserting one)."""
    async with sessions() as session:
        assert not await is_enabled_allowlist_pair(session, "mock", "mock")
