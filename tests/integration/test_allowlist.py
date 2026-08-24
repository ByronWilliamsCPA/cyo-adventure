"""Integration tests for is_enabled_allowlist_pair (needs a real session)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from cyo_adventure.db.models import ProviderModelAllowlist
from cyo_adventure.generation.allowlist import is_enabled_allowlist_pair

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_enabled_pair_is_enabled(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """An enabled row for the exact pair returns True.

    Uses ``openrouter`` deliberately: the default lane is the restrictive
    ``"family"`` one, so a positive case has to name a provider that lane
    permits. The direct-anthropic case is covered below, on both lanes.
    """
    async with sessions() as session:
        session.add(
            ProviderModelAllowlist(
                provider="openrouter",
                model_id="deepseek/deepseek-v4-pro",
                enabled=True,
            )
        )
        await session.commit()
        assert await is_enabled_allowlist_pair(
            session, "openrouter", "deepseek/deepseek-v4-pro"
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


# ---------------------------------------------------------------------------
# The D1 family-lane rule on the READ path (`UW-C350` part (a))
# ---------------------------------------------------------------------------
#
# Every row below is seeded straight through the session rather than through
# `api/provider_allowlist.py`, because since `d1fb0b7b` that endpoint returns
# 422 for exactly this shape. A forbidden-but-enabled row can now only arrive
# from a migration, `scripts/seed_dev_data.py`, or raw SQL, which is precisely
# the state this defence exists for, so seeding it directly is what makes
# these tests mean anything.
#
# "anthropic" and "openrouter" are written out as literals rather than derived
# from `FAMILY_LANE_PROVIDERS` (`AL-591`): a test whose expectation is computed
# from the same constant the production code reads moves whenever that constant
# moves and can never fail. `tests/unit/test_allowlist.py::
# test_the_direct_anthropic_provider_is_outside_the_family_lane` is the guard
# that these literals still describe the ruling.


# The at-rest half of the same rule (`UW-C350` part (b), landed alongside
# this): an ENABLED row naming a provider the family lane forbids now violates
# a CHECK, so the ORM can no longer insert one. Reaching the state the read
# path defends against therefore means removing that CHECK first, which is the
# honest description of what this defence is for: a database where the
# constraint has not been applied (one migrated before it existed, or one a DBA
# has dropped) still gets a correct answer from the read path.
_FAMILY_LANE_CHECK = "ck_provider_model_allowlist_enabled_family_lane"


async def _seed_direct_anthropic(session: AsyncSession, *, enabled: bool) -> None:
    """Insert a direct-anthropic allowlist row at the given enabled state.

    FLUSHED, never committed, and for the enabled case the at-rest CHECK is
    dropped inside this same transaction. PostgreSQL DDL is transactional, so
    closing the session without a commit restores the constraint and discards
    the row together: no test that runs later in this worker's database can see
    either. The flushed row is still visible to `is_enabled_allowlist_pair`,
    which reads through this same session.
    """
    if enabled:
        await session.execute(
            text(
                f"ALTER TABLE provider_model_allowlist DROP CONSTRAINT {_FAMILY_LANE_CHECK}"
            )
        )
    session.add(
        ProviderModelAllowlist(
            provider="anthropic", model_id="claude-sonnet-4-6", enabled=enabled
        )
    )
    await session.flush()


async def test_family_lane_refuses_an_enabled_row_it_forbids(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """An enabled row for a forbidden provider is still False on the family lane.

    This is the read-path half of D1: the row says enabled, and the answer is
    still no, because a kid- or guardian-triggered job may not reach the
    operator's direct Anthropic account whatever the table says.
    """
    async with sessions() as session:
        await _seed_direct_anthropic(session, enabled=True)
        assert not await is_enabled_allowlist_pair(
            session, "anthropic", "claude-sonnet-4-6", lane="family"
        )


async def test_the_default_lane_is_the_restrictive_one(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A caller that names no lane gets the family answer, not an exemption.

    Mirrors `build_provider`'s default so a call site added later is restricted
    by omission rather than exempt by omission.
    """
    async with sessions() as session:
        await _seed_direct_anthropic(session, enabled=True)
        assert not await is_enabled_allowlist_pair(
            session, "anthropic", "claude-sonnet-4-6"
        )


async def test_admin_lane_accepts_an_enabled_row_the_family_lane_forbids(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Out-of-band admin generation may still use the direct Anthropic leg.

    D1 withdrew direct Anthropic from family-triggered work only, so the lane
    has to be a parameter: hardcoding the family rule inside the helper would
    make this legitimate answer unreachable.
    """
    async with sessions() as session:
        await _seed_direct_anthropic(session, enabled=True)
        assert await is_enabled_allowlist_pair(
            session, "anthropic", "claude-sonnet-4-6", lane="admin"
        )


async def test_admin_lane_still_requires_the_row_to_be_enabled(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The admin lane relaxes the lane rule, never the enabled check.

    Without this, ``lane="admin"`` would read as a general bypass of the
    allowlist rather than as an exemption from one specific rule.
    """
    async with sessions() as session:
        await _seed_direct_anthropic(session, enabled=False)
        assert not await is_enabled_allowlist_pair(
            session, "anthropic", "claude-sonnet-4-6", lane="admin"
        )
