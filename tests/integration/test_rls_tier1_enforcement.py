"""ADR-022 Tier 1 RLS enforcement, exercised as the NOBYPASSRLS ``cyo_api`` role.

These tests are the database-floor counterpart to the app-layer IDOR sweeps:
where those prove FastAPI's ``authorize_family`` refuses a cross-family read,
these prove that even if the app layer were bypassed, a Tier 1 table's RLS
policy filters rows by the caller's ``app.family_id`` context. They connect
through ``cyo_api_sessions`` (see ``conftest.py``), the least-privilege role
production uses, because the default superuser fixtures hold BYPASSRLS and
would render every policy invisible.

Self-activating design: the two enforcement tests skip at runtime until the
ADR-022 migration has both ENABLEd row security on ``child_profile`` and
created a policy on it. This is a precondition skip (like the Docker-absent
skip in ``conftest.py``), not a static ``@pytest.mark.skip`` awaiting a ticket:
the moment the migration lands, ``_tier1_enforced`` returns True and the tests
run with no further edit. ``test_cyo_api_role_is_not_bypassrls`` runs
unconditionally today so the harness role's one indispensable property is
guarded now, not just after the migration.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from tests.integration.conftest import Seed

pytestmark = pytest.mark.asyncio

# ADR-022 candidate Tier 1 table: children's PII, hard NOT NULL family_id,
# never crosses families. The canonical table the enforcement contract targets.
_TIER1_TABLE = "child_profile"


async def _tier1_enforced(sessions: async_sessionmaker[AsyncSession]) -> bool:
    """Report whether ADR-022 Tier 1 enforcement is live on the candidate table.

    True only when BOTH conditions hold, because either alone leaves the table
    fully readable by ``cyo_api``: ``relrowsecurity`` must be on (RLS disabled
    means the GRANTs alone expose every row), and at least one policy must
    exist (RLS enabled with zero policies denies everything, which would make
    the positive-scoping test spuriously "pass" for the wrong reason).
    """
    async with sessions() as session:
        # Join pg_namespace rather than casting to ::regclass: a ":t::regclass"
        # token puts the ":t" bind param immediately before a "::" cast, which
        # SQLAlchemy's colon-based bind syntax cannot disambiguate.
        rls_on = (
            await session.execute(
                text(
                    "SELECT c.relrowsecurity FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE c.relname = :t AND n.nspname = 'public'"
                ),
                {"t": _TIER1_TABLE},
            )
        ).scalar()
        has_policy = (
            await session.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_policies "
                    "WHERE schemaname = 'public' AND tablename = :t)"
                ),
                {"t": _TIER1_TABLE},
            )
        ).scalar()
    return bool(rls_on) and bool(has_policy)


async def test_cyo_api_role_is_not_bypassrls(
    cyo_api_sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The provisioned harness role must not bypass RLS, or every policy is moot.

    Guards the single property the whole enforcement suite rests on: if
    ``cyo_api`` were ever provisioned (here or in production) with BYPASSRLS,
    the tests below would pass-through and silently prove nothing. This runs
    unconditionally so that regression is caught today.
    """
    async with cyo_api_sessions() as session:
        bypass = (
            await session.execute(
                text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
            )
        ).scalar_one()
    assert bypass is False


async def test_tier1_unset_context_returns_zero_rows(
    cyo_api_sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """With no ``app.family_id`` set, a Tier 1 table must expose zero rows.

    The fail-closed keystone (ADR-022): ``seed`` commits child profiles for
    families A and B, but a ``cyo_api`` caller that never set its family
    context matches the policy's ``family_id = current_setting(...)`` predicate
    against NULL, which is never true, so it sees nothing rather than every
    family's children.
    """
    if not await _tier1_enforced(cyo_api_sessions):
        pytest.skip(
            f"ADR-022 Tier 1 RLS not yet applied to {_TIER1_TABLE}; this "
            "enforcement test self-activates once the migration lands."
        )
    async with cyo_api_sessions() as session:
        count = (
            await session.execute(text(f"SELECT count(*) FROM {_TIER1_TABLE}"))  # noqa: S608
        ).scalar_one()
    assert count == 0


async def test_tier1_context_scopes_reads_to_caller_family(
    cyo_api_sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """Setting ``app.family_id`` exposes only the caller's own family rows.

    The positive counterpart to the fail-closed test: with the context set to
    family A, family A's own child profile is visible and family B's is not.
    ``set_config(..., true)`` is transaction-local, and the session autobegins
    a transaction on first execute, so the setting and the read share one
    transaction.
    """
    if not await _tier1_enforced(cyo_api_sessions):
        pytest.skip(
            f"ADR-022 Tier 1 RLS not yet applied to {_TIER1_TABLE}; this "
            "enforcement test self-activates once the migration lands."
        )
    async with cyo_api_sessions() as session:
        await session.execute(
            text("SELECT set_config('app.family_id', :fid, true)"),
            {"fid": str(seed.family_id)},
        )
        visible = (
            (
                await session.execute(text(f"SELECT family_id FROM {_TIER1_TABLE}"))  # noqa: S608
            )
            .scalars()
            .all()
        )
    assert visible, "family A's own profile must be visible with its context set"
    assert all(str(fid) == str(seed.family_id) for fid in visible), (
        "a foreign family's rows leaked past the Tier 1 policy"
    )
