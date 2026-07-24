"""ADR-022 Tier 1 RLS enforcement, exercised as the NOBYPASSRLS ``cyo_api`` role.

These tests are the database-floor counterpart to the app-layer IDOR sweeps:
where those prove FastAPI's ``authorize_family`` refuses a cross-family read,
these prove that even if the app layer were bypassed, a Tier 1 table's RLS
policy filters rows by the caller's ``app.family_id`` context. They connect as
the least-privilege ``cyo_api`` role production uses, because the default
superuser fixtures hold BYPASSRLS and would render every policy invisible.

Real-migration schema, not ORM ``create_all``: the ADR-022 policies and the
``ENABLE ROW LEVEL SECURITY`` they depend on live in ``supabase/migrations``,
never in ``Base.metadata``. So the ``engine``/``sessions`` fixtures (tables
only) could never make these assertions bite. Each test therefore builds a
fresh migrated database via ``migrate_and_connect_as`` (the same helper
``test_rls_service_roles.py`` and the schema-parity gate use), which runs the
full migration chain and hands back both an owner DSN (RLS-bypassing, to seed
baseline rows) and a ``cyo_api`` DSN (RLS-subject, to assert enforcement).

The three enforcement assertions are the fail-closed keystone (no context =>
zero rows), the positive per-family scope (context => only own family), and
the admin escape hatch (``app.is_admin='true'`` => all families), which
together pin every branch of the ``family_scoped`` policy predicate.
``test_cyo_api_role_is_not_bypassrls`` guards the one role property the whole
suite rests on: were ``cyo_api`` ever BYPASSRLS, every assertion below would
pass-through and silently prove nothing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from cyo_adventure.core.database import apply_family_rls_context
from cyo_adventure.db.models import ChildProfile as ChildProfileModel
from cyo_adventure.db.models import Family
from tests.integration._migration_utils import migrate_and_connect_as

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# ADR-021 least-privilege role the FOR-cyo_api Tier 1 policy targets. The tests
# MUST connect as this exact role: a policy is role-scoped, so any other
# NOBYPASSRLS role would match no policy and see zero rows for the wrong reason.
_CYO_API_ROLE = "cyo_api"

# ADR-022 candidate Tier 1 table: children's PII, hard NOT NULL family_id,
# never crosses families. The canonical table the enforcement contract targets.
_TIER1_TABLE = "child_profile"


@dataclass(frozen=True)
class _Tier1Env:
    """A migrated database seeded with two families, reachable as ``cyo_api``."""

    sessions: async_sessionmaker[AsyncSession]
    family_a: uuid.UUID
    family_b: uuid.UUID


@pytest_asyncio.fixture
async def tier1_env(pg_url: str) -> AsyncIterator[_Tier1Env]:
    """Build a migrated DB, seed families A and B, yield a ``cyo_api`` factory.

    Baseline rows are seeded through the RLS-bypassing owner connection so that
    BOTH families' child profiles exist regardless of any policy; the tests
    then read through the NOBYPASSRLS ``cyo_api`` connection, where the Tier 1
    ``family_scoped`` policy is what decides which of those rows are visible.
    """
    admin_url, role_url = await migrate_and_connect_as(
        pg_url, "rls_tier1_enforcement", _CYO_API_ROLE
    )
    family_a = uuid.uuid4()
    family_b = uuid.uuid4()

    admin_engine = create_async_engine(admin_url, poolclass=NullPool)
    admin_sessions = async_sessionmaker(admin_engine, expire_on_commit=False)
    try:
        async with admin_sessions() as session:
            session.add_all(
                [
                    Family(id=family_a, name="Family A"),
                    Family(id=family_b, name="Family B"),
                ]
            )
            await session.flush()
            session.add_all(
                [
                    ChildProfileModel(
                        family_id=family_a, display_name="Reader A", age_band="8-11"
                    ),
                    ChildProfileModel(
                        family_id=family_b, display_name="Reader B", age_band="8-11"
                    ),
                ]
            )
            await session.commit()
    finally:
        await admin_engine.dispose()

    api_engine = create_async_engine(role_url, poolclass=NullPool)
    api_sessions = async_sessionmaker(api_engine, expire_on_commit=False)
    try:
        yield _Tier1Env(sessions=api_sessions, family_a=family_a, family_b=family_b)
    finally:
        await api_engine.dispose()


async def test_cyo_api_role_is_not_bypassrls(tier1_env: _Tier1Env) -> None:
    """The role the suite connects as must not bypass RLS, or every policy is moot.

    Guards the single property the whole enforcement suite rests on: if
    ``cyo_api`` were ever provisioned (here or in production) with BYPASSRLS,
    the tests below would pass-through and silently prove nothing.
    """
    async with tier1_env.sessions() as session:
        bypass = (
            await session.execute(
                text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
            )
        ).scalar_one()
    assert bypass is False


async def test_tier1_unset_context_returns_zero_rows(tier1_env: _Tier1Env) -> None:
    """With no ``app.family_id`` set, a Tier 1 table must expose zero rows.

    The fail-closed keystone (ADR-022): the fixture commits child profiles for
    families A and B, but a ``cyo_api`` caller that never set its family context
    matches the policy's ``family_id = current_setting(...)`` predicate against
    NULL, which is never true, so it sees nothing rather than every family's
    children. This is the one assertion ``test_rls_service_roles.py`` cannot
    make, because that test always sets context before it reads.
    """
    async with tier1_env.sessions() as session:
        count = (
            await session.execute(text(f"SELECT count(*) FROM {_TIER1_TABLE}"))  # noqa: S608
        ).scalar_one()
    assert count == 0


async def test_tier1_context_scopes_reads_to_caller_family(
    tier1_env: _Tier1Env,
) -> None:
    """Setting ``app.family_id`` exposes only the caller's own family rows.

    The positive counterpart to the fail-closed test, driven through the
    production helper (``apply_family_rls_context``) rather than a raw
    ``set_config`` so the request path's exact mechanism is what is exercised:
    with the context set to family A, family A's own child profile is visible
    and family B's is not. ``set_config(..., true)`` is transaction-local and
    the session autobegins a transaction on first execute, so the setting and
    the read share one transaction.
    """
    async with tier1_env.sessions() as session:
        await apply_family_rls_context(
            session, family_id=tier1_env.family_a, is_admin=False
        )
        visible = (
            (await session.execute(text(f"SELECT family_id FROM {_TIER1_TABLE}")))  # noqa: S608
            .scalars()
            .all()
        )
    assert visible, "family A's own profile must be visible with its context set"
    assert all(str(fid) == str(tier1_env.family_a) for fid in visible), (
        "a foreign family's rows leaked past the Tier 1 policy"
    )


async def test_tier1_admin_context_reads_across_families(
    tier1_env: _Tier1Env,
) -> None:
    """The ``app.is_admin='true'`` escape hatch reads across all families.

    ADR-022's sole cross-family reach in the predicate (ADR-016 admin
    moderation): an admin principal sets ``is_admin=True`` and sees BOTH
    families' profiles, where a same-family non-admin (the test above) sees
    only its own. Pins the ``OR current_setting('app.is_admin', true) = 'true'``
    branch that a fail-closed-only suite would leave unexercised.
    """
    async with tier1_env.sessions() as session:
        await apply_family_rls_context(
            session, family_id=tier1_env.family_a, is_admin=True
        )
        count = (
            await session.execute(text(f"SELECT count(*) FROM {_TIER1_TABLE}"))  # noqa: S608
        ).scalar_one()
    assert count == 2, "the admin escape hatch must read across families"
