"""RLS + service-role regression guard (ADR-021).

Proves the landmine this ADR closes stays closed: a connection authenticated
as ``cyo_api`` or ``cyo_worker`` (the two roles created by
``20260720170100_create_service_roles.sql``) can perform the full pipeline
CRUD chain against every RLS-enabled table, while a connection with no
ADR-021 grant (``anon``/``authenticated``, the Supabase/PostgREST roles) is
denied. It also enforces a coverage invariant: every table where
``20260711200745_enable_rls_all_tables.sql`` turned RLS on must carry a
``service_rw`` policy naming both roles, and both roles must hold the actual
SELECT/INSERT/UPDATE/DELETE privilege (a policy with no underlying GRANT is
inert, and a GRANT with no policy is blocked by RLS; both halves are needed).

Builds one migrated sibling database (via
``tests.integration._migration_utils.create_migrated_database``, the same
helper ``test_schema_parity.py`` uses) on the session-scoped testcontainers
Postgres server, then ``ALTER ROLE ... LOGIN PASSWORD`` with process-local
random passwords so this test can authenticate as each role directly. Roles
are cluster-wide in Postgres, so this mutates cluster state for the
lifetime of the container; harmless, since the whole container is torn down
at session end and no other test authenticates as these roles.
"""

from __future__ import annotations

import secrets
import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import make_url, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from cyo_adventure.db.models import (
    ChildProfile as ChildProfileModel,
)
from cyo_adventure.db.models import (
    Concept,
    Family,
    GenerationJob,
    PipelineEvent,
    Rating,
    Storybook,
    StorybookVersion,
    StoryRequest,
    User,
)
from tests.integration._migration_utils import create_migrated_database

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# The two ADR-021 service roles (created NOLOGIN by
# 20260720170100_create_service_roles.sql; this test flips them to LOGIN with
# a process-local password so it can connect directly as each one).
_SERVICE_ROLES = ("cyo_api", "cyo_worker")

# The two Supabase/PostgREST roles that must remain denied. Real Supabase
# projects create these platform-wide; the testcontainers image does not, so
# this test creates them itself (idempotently, mirroring the "postgres" role
# bootstrap in _migration_utils.create_migrated_database) rather than special-
# casing "role does not exist" as a third acceptable outcome.
_UNPRIVILEGED_ROLES = ("anon", "authenticated")

# Every table 20260711200745_enable_rls_all_tables.sql turned RLS on for, used
# as a sanity floor for the coverage-invariant sweep below (the sweep itself
# queries pg_tables directly rather than trusting this list, so a future
# migration that enables RLS on a new table without a matching service_rw
# policy still fails the sweep even if this constant is never updated).
_MIN_EXPECTED_RLS_TABLE_COUNT = 22


async def _create_role_if_absent(conn: AsyncConnection, role: str) -> None:
    """Idempotently create a NOLOGIN role, mirroring the migration's own DO block.

    Args:
        conn: An autocommit admin connection (superuser).
        role: The role name. Always one of this module's own constants
            (``_UNPRIVILEGED_ROLES``), never external input, but the DO block
            still can't accept a bind parameter for a role name (DDL
            identifiers aren't parameterizable), so this is interpolated.
    """
    await conn.execute(
        text(
            f'DO $$ BEGIN CREATE ROLE "{role}" NOLOGIN; '
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        )
    )


async def _grant_login_password(
    conn: AsyncConnection, role: str, password: str
) -> None:
    """Flip a NOLOGIN role to LOGIN with a test-only password.

    Args:
        conn: An autocommit admin connection (superuser).
        role: The role name (from this module's own constants only).
        password: A `secrets.token_urlsafe` value: URL-safe base64 alphabet
            only (no quotes), so it is safe to interpolate directly.
            ``ALTER ROLE ... PASSWORD`` does not accept a bind parameter in
            that position (it is a string literal in the grammar, not an
            expression), so parameterizing it is not an option here.
    """
    # #ASSUME: security: this is a throwaway password on a throwaway
    # role/database that lives only inside the session-scoped testcontainers
    # Postgres instance, destroyed when the container stops; it is never
    # written to disk, logged, or reused across roles.
    # #VERIFY: passwords are generated fresh per role per test run via
    # secrets.token_urlsafe (cryptographically random), never a fixed literal.
    await conn.execute(text(f"ALTER ROLE \"{role}\" LOGIN PASSWORD '{password}'"))


def _role_url(base_url: str, role: str, password: str) -> str:
    """Rewrite a SQLAlchemy DSN's username/password to authenticate as ``role``.

    Args:
        base_url: A ``postgresql+asyncpg://`` URL for the migrated database
            (same host/port/database, admin credentials).
        role: The role to connect as.
        password: That role's just-set LOGIN password.

    Returns:
        str: The rewritten URL, rendered with the real password (never
        masked; masking is only a ``str()``/``repr()`` display concern, not a
        stored-value concern, and this string is fed straight into
        ``create_async_engine``, which needs the real password).
    """
    return (
        make_url(base_url)
        .set(username=role, password=password)
        .render_as_string(hide_password=False)
    )


async def _rowsecurity_tables(conn: AsyncConnection) -> list[str]:
    """List every public-schema table with row-level security enabled."""
    result = await conn.execute(
        text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND rowsecurity = true "
            "ORDER BY tablename"
        )
    )
    return [row[0] for row in result.fetchall()]


async def _policy_role_names(conn: AsyncConnection, table: str) -> set[str]:
    """Union of every role named by any policy defined on ``table``."""
    result = await conn.execute(
        text(
            "SELECT roles FROM pg_policies "
            "WHERE schemaname = 'public' AND tablename = :table"
        ),
        {"table": table},
    )
    names: set[str] = set()
    for (roles,) in result.fetchall():
        names.update(roles)
    return names


async def _has_privilege(
    conn: AsyncConnection, role: str, table: str, privilege: str
) -> bool:
    """Whether ``role`` holds ``privilege`` on ``public.<table>`` (GRANT layer)."""
    result = await conn.execute(
        text("SELECT has_table_privilege(:role, :qualified, :priv)"),
        {"role": role, "qualified": f"public.{table}", "priv": privilege},
    )
    return bool(result.scalar_one())


async def _assert_role_denied(engine: AsyncEngine, table: str) -> None:
    """Prove a role with no ADR-021 grant cannot read a sensitive table.

    Accepts either outcome named in the ADR-021 test contract: this role has
    no GRANT at all here, so the expected outcome is a hard permission-denied
    error (SQLSTATE 42501, ``insufficient_privilege``); a query that somehow
    succeeds with zero rows is also accepted (RLS silently filtering every
    row is likewise "denied" in effect, and this test should not fail if a
    future migration adds a narrower read grant instead of none at all).

    Args:
        engine: An engine authenticated as the role under test.
        table: The bare table name (no schema qualifier); always one of this
            module's own literals ("user", "child_profile"), never external
            input, so the f-string interpolation below is safe despite Ruff's
            generic S608 heuristic.
    """
    denied_with: DBAPIError | None = None
    rows: Sequence[object] = []
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(f'SELECT * FROM public."{table}"')  # noqa: S608
            )
            rows = result.fetchall()
    except DBAPIError as exc:
        denied_with = exc
    finally:
        await engine.dispose()

    if denied_with is not None:
        # #ASSUME: external resources: SQLAlchemy's asyncpg dialect never
        # re-raises the raw asyncpg exception class; it wraps every driver
        # error in its own ``sqlalchemy.exc`` shim (chained via ``raise ...
        # from``), so ``.orig`` is that shim, not
        # ``asyncpg.exceptions.InsufficientPrivilegeError``. An
        # ``isinstance`` check against the asyncpg class is therefore always
        # False and silently passes regardless of the actual failure mode.
        # #VERIFY: check the wrapped exception's SQLSTATE instead
        # (asyncpg exposes ``sqlstate``; ``.orig`` is typed ``BaseException |
        # None`` in the SQLAlchemy stubs, so ``getattr`` rather than direct
        # attribute access, matching db/integrity.py's own SQLSTATE check).
        sqlstate = getattr(denied_with.orig, "sqlstate", None)
        assert sqlstate == "42501", (  # 42501 = insufficient_privilege
            f"expected insufficient_privilege denying access to {table!r}, "
            f"got {denied_with.orig!r} instead"
        )
    else:
        assert rows == [], (
            f"{table!r} returned {len(rows)} row(s) to a role with no ADR-021 "
            "grant; RLS/GRANT regression"
        )


async def test_service_roles_full_pipeline_crud_under_rls(pg_url: str) -> None:
    """cyo_api and cyo_worker can CRUD the full pipeline chain under RLS.

    Builds a fresh migrated database, promotes the two ADR-021 service roles
    to LOGIN with random test passwords, then drives one family -> user ->
    child_profile -> story_request -> concept -> generation_job -> storybook
    -> storybook_version -> pipeline_event chain split across both roles
    (proving neither role is silently narrower than the other), plus one
    cross-role UPDATE and one cross-role DELETE (proving each role can see
    and mutate rows the other role wrote, which only holds if the
    ``service_rw`` policy's ``USING (true)`` is actually in effect).

    Args:
        pg_url: Public alias for the session-scoped testcontainers Postgres
            URL fixture (``tests/integration/conftest.py``).
    """
    mig_url = await create_migrated_database(pg_url, "rls_service_roles")

    admin_engine = create_async_engine(
        mig_url, poolclass=NullPool, isolation_level="AUTOCOMMIT"
    )
    passwords = {role: secrets.token_urlsafe(16) for role in _SERVICE_ROLES}
    try:
        async with admin_engine.connect() as conn:
            for role in _SERVICE_ROLES:
                await _grant_login_password(conn, role, passwords[role])
    finally:
        await admin_engine.dispose()

    api_engine = create_async_engine(
        _role_url(mig_url, "cyo_api", passwords["cyo_api"]), poolclass=NullPool
    )
    worker_engine = create_async_engine(
        _role_url(mig_url, "cyo_worker", passwords["cyo_worker"]), poolclass=NullPool
    )
    api_sessions = async_sessionmaker(api_engine, expire_on_commit=False)
    worker_sessions = async_sessionmaker(worker_engine, expire_on_commit=False)

    try:
        # --- cyo_api: family -> guardian user -> child profile -> request ---
        family_id = uuid.uuid4()
        guardian_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        request_id = uuid.uuid4()
        async with api_sessions() as session:
            session.add(Family(id=family_id, name="ADR-021 RLS test family"))
            await session.flush()
            session.add(
                User(
                    id=guardian_id,
                    family_id=family_id,
                    role="guardian",
                    is_admin=False,
                    authn_subject=f"rls-test-guardian-{guardian_id}",
                )
            )
            session.add(
                ChildProfileModel(
                    id=profile_id,
                    family_id=family_id,
                    display_name="RLS Test Kid",
                    age_band="8-11",
                )
            )
            await session.flush()
            session.add(
                StoryRequest(
                    id=request_id,
                    family_id=family_id,
                    profile_id=profile_id,
                    request_text="A dragon who learns to share.",
                    age_band="8-11",
                )
            )
            await session.commit()

        # --- cyo_worker: concept -> generation_job -> storybook -> version
        #     -> pipeline_event, all referencing rows cyo_api just wrote ---
        concept_id = uuid.uuid4()
        job_id = uuid.uuid4()
        storybook_id = f"rls-test-{uuid.uuid4().hex[:12]}"
        async with worker_sessions() as session:
            session.add(
                Concept(
                    id=concept_id,
                    family_id=family_id,
                    brief={"age_band": "8-11", "topic": "sharing"},
                    created_by=guardian_id,
                )
            )
            await session.flush()
            session.add(
                GenerationJob(id=job_id, concept_id=concept_id, status="queued")
            )
            session.add(Storybook(id=storybook_id, family_id=family_id))
            await session.flush()
            session.add(
                StorybookVersion(
                    storybook_id=storybook_id,
                    version=1,
                    blob={"nodes": {}, "start_node": "n1"},
                )
            )
            session.add(
                PipelineEvent(
                    actor_id=None,
                    actor_role="system",
                    entity_type="generation_job",
                    entity_id=str(job_id),
                    event_type="generation_started",
                    payload={},
                )
            )
            await session.commit()

        # --- cross-role UPDATE: cyo_api mutates a row cyo_worker inserted ---
        async with api_sessions() as session:
            job = await session.get(GenerationJob, job_id)
            assert job is not None, "cyo_api cannot see the row cyo_worker inserted"
            job.status = "passed"
            await session.commit()

        async with worker_sessions() as session:
            job = await session.get(GenerationJob, job_id)
            assert job is not None
            assert job.status == "passed", (
                "cyo_worker does not see cyo_api's UPDATE; USING (true) not in effect"
            )

        # --- cross-role INSERT + UPDATE + DELETE on a mutable, deletable
        #     table (Rating), proving DELETE works end to end, not just at
        #     the has_table_privilege layer ---
        async with worker_sessions() as session:
            session.add(
                Rating(child_profile_id=profile_id, storybook_id=storybook_id, value=3)
            )
            await session.commit()

        async with api_sessions() as session:
            rating = await session.get(Rating, (profile_id, storybook_id))
            assert rating is not None
            rating.value = 5
            await session.commit()

        async with worker_sessions() as session:
            rating = await session.get(Rating, (profile_id, storybook_id))
            assert rating is not None
            assert rating.value == 5
            await session.delete(rating)
            await session.commit()

        async with api_sessions() as session:
            assert await session.get(Rating, (profile_id, storybook_id)) is None, (
                "cyo_worker's DELETE did not take effect for cyo_api's connection"
            )
    finally:
        await api_engine.dispose()
        await worker_engine.dispose()


async def test_unprivileged_roles_denied_on_sensitive_tables(pg_url: str) -> None:
    """anon and authenticated (no ADR-021 grant) cannot read any RLS-enabled table.

    These are the Supabase/PostgREST roles the RLS policies deliberately
    exclude (``20260720170200_add_service_role_policies.sql``'s module
    docstring: "anon and authenticated get NO policies"). This test creates
    them locally (the testcontainers image has no Supabase platform roles)
    and proves the deny-by-default posture holds across every RLS-enabled
    table in the schema, not just a hand-picked sample: the table list is
    discovered the same way the coverage-invariant test discovers it
    (``_rowsecurity_tables``, a live ``pg_tables`` query) rather than
    hardcoded, so a policy that accidentally attaches ``anon`` or
    ``authenticated`` to some other table is still caught here.

    Args:
        pg_url: Public alias for the session-scoped testcontainers Postgres
            URL fixture.
    """
    mig_url = await create_migrated_database(pg_url, "rls_unprivileged_roles")

    admin_engine = create_async_engine(
        mig_url, poolclass=NullPool, isolation_level="AUTOCOMMIT"
    )
    passwords = {role: secrets.token_urlsafe(16) for role in _UNPRIVILEGED_ROLES}
    try:
        async with admin_engine.connect() as conn:
            for role in _UNPRIVILEGED_ROLES:
                await _create_role_if_absent(conn, role)
                await _grant_login_password(conn, role, passwords[role])
            tables = await _rowsecurity_tables(conn)
    finally:
        await admin_engine.dispose()

    for role in _UNPRIVILEGED_ROLES:
        for table in tables:
            engine = create_async_engine(
                _role_url(mig_url, role, passwords[role]), poolclass=NullPool
            )
            await _assert_role_denied(engine, table)


async def test_every_rls_table_grants_both_service_roles(pg_url: str) -> None:
    """Coverage invariant: every RLS-enabled table grants both service roles full CRUD.

    Two independent checks per table, since either alone can silently regress:
    a ``service_rw`` policy naming both roles (the RLS-layer allow), and
    ``has_table_privilege`` confirming SELECT/INSERT/UPDATE/DELETE for both
    roles (the GRANT-layer allow; a policy with no underlying GRANT is inert).
    A future migration that enables RLS on a new table without updating
    ``20260720170100_create_service_roles.sql`` /
    ``20260720170200_add_service_role_policies.sql`` fails this test, which is
    the point: the checklist in the runbook's ADR-021 cutover section exists
    because this test would otherwise be the only thing that notices.

    Args:
        pg_url: Public alias for the session-scoped testcontainers Postgres
            URL fixture.
    """
    mig_url = await create_migrated_database(pg_url, "rls_coverage_invariant")

    admin_engine = create_async_engine(mig_url, poolclass=NullPool)
    try:
        async with admin_engine.connect() as conn:
            tables = await _rowsecurity_tables(conn)
            assert len(tables) >= _MIN_EXPECTED_RLS_TABLE_COUNT, (
                f"expected at least {_MIN_EXPECTED_RLS_TABLE_COUNT} RLS-enabled "
                f"tables, found {len(tables)}: {tables}"
            )

            for table in tables:
                policy_roles = await _policy_role_names(conn, table)
                missing_policy = [
                    role for role in _SERVICE_ROLES if role not in policy_roles
                ]
                assert not missing_policy, (
                    f"{table!r} has no service_rw-style policy granting "
                    f"{missing_policy}; policy roles found: {policy_roles}"
                )

                for role in _SERVICE_ROLES:
                    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                        assert await _has_privilege(conn, role, table, privilege), (
                            f"{role} lacks {privilege} on {table!r} "
                            "(GRANT-layer regression, independent of the "
                            "policy check above)"
                        )
    finally:
        await admin_engine.dispose()
