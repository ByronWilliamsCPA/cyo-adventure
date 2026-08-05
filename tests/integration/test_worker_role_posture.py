"""The worker's ADR-021 role-posture probe, against a real PostgreSQL server.

Two things in this area cannot be proven by a stubbed or SQLite-backed test,
which is why this file exists alongside
``tests/unit/test_worker_main.py::TestWorkerRolePosture``:

1. **Aborted-transaction semantics.** The probe and the stranded-job reclaim
   sweep share one transaction, and the probe deliberately runs first. When a
   probe statement fails, PostgreSQL refuses every subsequent statement on that
   transaction until it is rolled back (SQLSTATE 25P02,
   ``InFailedSQLTransactionError``). That is server-side behaviour: no stub
   implements it, and neither does SQLite, which happily continues after a
   failed statement. A unit test that monkeypatches ``measure_role_posture`` to
   raise before touching the session can therefore assert the probe "never
   stops the worker" while the real thing crash-loops. The tests below drive a
   genuine statement error through a genuine session.

2. **That ``CONNECTED_ROLE_QUERY`` is valid SQL that returns what the dataclass
   expects.** The query is a module-level string executed with no bind
   parameters; the unit tests stub the session, so nothing else in the suite
   ever asks PostgreSQL to parse it. A typo in a ``pg_class``/``pg_roles``
   column name would ship green and then fail closed at runtime, reporting
   every environment as "posture unknown".

The bypass paths are then measured one at a time, which needs two different
schemas because the default fixtures cannot express all three states:

* The default fixtures build the schema from ``Base.metadata`` and connect as
  the container's owner superuser. That gives a true positive on the ROLE
  ATTRIBUTE path (``rolsuper``) and, necessarily, a true negative on the
  OWNERSHIP path: ``create_all`` never enables RLS, because policies live only
  in ``supabase/migrations`` (see the ADR-021/ADR-022 note in ``conftest.py``).
* A migrated sibling database, built the same way ``test_rls_service_roles.py``
  builds one, supplies the other two states. ``cyo_worker`` is clean on both
  paths, which is the affirmative verdict production claims. The dump's
  ``postgres`` owner role is clean on the attribute path and dirty on the
  ownership path, which is the pre-ADR-021 state and the one a
  ``rolbypassrls``-only check misses entirely.

Keeping ownership and attribute assertions on separate roles is deliberate: on a
superuser the two are always both true, so a broken ownership ``EXISTS`` clause
would hide behind ``rolsuper``.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from cyo_adventure.core.rls_posture import CONNECTED_ROLE_QUERY, measure_role_posture
from cyo_adventure.generation import worker_main
from tests.integration._migration_utils import migrate_and_connect_as

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _install_fake_engines(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub out the module-level engine disposal in ``_run_worker_startup``.

    ``_run_worker_startup``'s ``finally`` block disposes the real
    module-level API and worker engines, which point at the configured
    deployment DSN rather than at this test's container. Disposal of a
    never-connected engine is harmless, but stubbing it keeps the test from
    depending on that being true.
    """
    for name in ("get_engine", "get_worker_engine"):
        fake = MagicMock(spec=AsyncEngine)
        fake.dispose = AsyncMock()
        monkeypatch.setattr(worker_main, name, lambda fake=fake: fake)


def _failing_probe() -> tuple[str, object]:
    """Build a probe replacement that fails the way a real probe fails.

    Returns:
        tuple[str, object]: The unique relation name it references (useful in
        assertion messages) and the async probe callable itself.
    """
    missing = f"absent_relation_{uuid.uuid4().hex[:12]}"

    async def _probe(session: AsyncSession) -> object:
        # A statement error inside the probe's own transaction, which is what
        # actually happens when the worker's role cannot read pg_class or the
        # pooler rejects the statement. Raising a bare Python exception instead
        # (as the unit test does) leaves the transaction clean and cannot
        # reproduce this failure mode at all.
        await session.execute(text(f"SELECT 1 FROM {missing}"))  # noqa: S608
        msg = "unreachable: the statement above must raise"
        raise AssertionError(msg)

    return missing, _probe


@pytest.mark.security
async def test_statement_error_in_probe_still_lets_the_sweep_run(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed probe leaves the shared transaction usable for the sweep.

    This is the test the ``#CRITICAL`` marker on
    ``worker_main._log_worker_role_posture`` names. The probe is documented as
    never gating startup; without a rollback in its ``except`` branch that
    promise is false in exactly the case it is written for, because the sweep
    is the next statement on the transaction the probe just aborted, and
    ``restart_policy: on-failure`` turns the resulting crash into an uncapped
    loop.

    #CRITICAL: security: the failure is silent in the sense that matters. The
    worker logs ``rls_posture_unknown`` and then dies on an unrelated-looking
    sweep traceback, so the operator sees a queue outage rather than a broken
    diagnostic.
    #VERIFY: test_sweep_dies_when_the_probe_rollback_is_removed below is the
    positive control proving this test can fail.
    """
    missing, probe = _failing_probe()

    async with sessions() as session:

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[AsyncSession]:
            yield session

        monkeypatch.setattr(worker_main, "get_worker_session", _fake_get_session)
        monkeypatch.setattr(worker_main, "measure_role_posture", probe)
        _install_fake_engines(monkeypatch)

        # The real sweep, not a stub: its SELECT against generation_job is the
        # statement that PostgreSQL rejects on an aborted transaction.
        reclaimed = await worker_main._run_worker_startup()

        assert reclaimed == 0, f"empty schema after probe on {missing} must sweep 0"

        # The transaction is genuinely usable afterwards, not merely unraised.
        assert (await session.execute(text("SELECT 1"))).scalar_one() == 1


@pytest.mark.security
async def test_sweep_dies_when_the_probe_rollback_is_removed(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Positive control: the rollback in the probe is load-bearing.

    Neutralises ``session.rollback`` for the duration of the probe and asserts
    the sweep then fails. Without this, the test above would keep passing if
    someone deleted the rollback and PostgreSQL had quietly changed its
    aborted-transaction behaviour, or if the fixture's session were not really
    shared between probe and sweep. A guard whose removal breaks nothing
    observable is indistinguishable from dead code.
    """
    _, probe = _failing_probe()

    async with sessions() as session:
        # Swallow only the probe's rollback, leaving the session otherwise real.
        monkeypatch.setattr(session, "rollback", AsyncMock())

        @asynccontextmanager
        async def _fake_get_session() -> AsyncGenerator[AsyncSession]:
            yield session

        monkeypatch.setattr(worker_main, "get_worker_session", _fake_get_session)
        monkeypatch.setattr(worker_main, "measure_role_posture", probe)
        _install_fake_engines(monkeypatch)

        with pytest.raises(SQLAlchemyError) as excinfo:
            await worker_main._run_worker_startup()

        # Pin the mechanism, not just "something raised": the sweep must fail
        # BECAUSE the transaction the probe aborted was never rolled back.
        assert _is_aborted_transaction_error(excinfo.value), (
            f"expected an aborted-transaction failure, got {excinfo.value!r}"
        )


def _is_aborted_transaction_error(exc: BaseException) -> bool:
    """Whether ``exc`` reports work refused on an already-aborted transaction.

    Measured on this stack (SQLAlchemy 2.x + asyncpg + PostgreSQL 16), the
    sweep's statement reaches the SERVER and comes back as::

        sqlalchemy.exc.DBAPIError
          orig: asyncpg.exceptions.InFailedSQLTransactionError:
                current transaction is aborted, commands ignored until end of
                transaction block

    so this is genuine SQLSTATE 25P02, not SQLAlchemy's client-side bookkeeping.
    That matters for interpreting the control test: the failure is a property of
    PostgreSQL, which is why no stub and no SQLite backend can reproduce it.

    ``PendingRollbackError`` is also accepted, because SQLAlchemy short-circuits
    on a deactivated transaction in some session states and that would mean the
    same thing here. It is not what fires today; do not read its presence in
    this list as a description of current behaviour.

    Args:
        exc: The exception raised by the sweep.

    Returns:
        True when the failure is an aborted/deactivated-transaction refusal.
    """
    text_form = f"{type(exc).__name__}: {exc}"
    if isinstance(exc, DBAPIError) and exc.orig is not None:
        text_form += f" | orig={type(exc.orig).__name__}: {exc.orig}"
    lowered = text_form.lower()
    return (
        "infailedsqltransaction" in lowered
        or "25p02" in lowered
        or "current transaction is aborted" in lowered
        or "pendingrollback" in lowered
        or "invalid transaction is rolled back" in lowered
    )


@pytest.mark.security
async def test_connected_role_query_parses_and_detects_the_owner_bypass(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """``CONNECTED_ROLE_QUERY`` is valid SQL and flags a bypassing connection.

    The default fixtures connect as the container's owner superuser, which is a
    true positive on two independent bypass paths at once: ``rolsuper`` and
    ownership of RLS-enabled ``public`` tables that do not set FORCE ROW LEVEL
    SECURITY. Both are asserted separately so a query edit that breaks the
    ownership ``EXISTS`` clause cannot hide behind the ``rolsuper`` result.

    #CRITICAL: security: this is the only test in the suite that asks
    PostgreSQL to parse this query. Every other caller is stubbed, so a
    misspelled catalog column would ship green and then degrade every
    environment to "posture unknown" at runtime, which the worker treats as
    non-fatal and logs rather than surfacing.
    """
    async with sessions() as session:
        posture = await measure_role_posture(session)

        assert posture.role_name, "current_user must not be empty"
        assert posture.via_role_attribute is True, (
            f"{posture.role_name} is the container superuser and must be "
            "detected via rolsuper/rolbypassrls"
        )
        # Deliberately asserted as False, and not a weaker "don't care": these
        # fixtures build the schema from Base.metadata, which never enables RLS
        # (policies live only in supabase/migrations, see the ADR-021/ADR-022
        # note in conftest.py). With no relrowsecurity table in the database,
        # the ownership EXISTS clause has nothing to match and MUST report
        # false. A true here would mean the clause matches on something other
        # than an RLS-enabled table. The ownership path's positive case is
        # covered on a migrated schema below.
        assert posture.via_table_ownership is False, (
            "Base.metadata builds no RLS-enabled table, so the ownership "
            "clause cannot legitimately fire here"
        )
        assert posture.bypasses_rls is True

        # The three column names the dataclass reads must all be present; a
        # renamed alias would otherwise surface as an AttributeError only on
        # the branch that happens to read it.
        row = (await session.execute(text(CONNECTED_ROLE_QUERY))).one()
        assert set(row._mapping) == {
            "role_name",
            "role_bypasses_rls",
            "owns_rls_table",
        }


@pytest.mark.security
@pytest.mark.parametrize(
    ("role", "expect_attribute", "expect_ownership"),
    [
        ("cyo_worker", False, False),
        # The baseline dump is a pg_dump from a live Supabase project where
        # every table is OWNER TO "postgres", and _migration_utils creates that
        # role bare: no rolsuper, no rolbypassrls, but owner of every
        # RLS-enabled table. That is precisely the pre-ADR-021 production state,
        # and it isolates the ownership bypass path with the role-attribute path
        # switched OFF. Asserting ownership on a superuser instead would let a
        # broken EXISTS clause hide behind rolsuper.
        ("postgres", False, True),
    ],
    ids=["cut-over-worker-role", "pre-cutover-table-owner"],
)
async def test_posture_on_a_migrated_schema_separates_the_bypass_paths(
    pg_url: str, role: str, expect_attribute: bool, expect_ownership: bool
) -> None:
    """Each bypass path is measured independently on a production-shaped schema.

    The owner-superuser test above would still pass if
    ``measure_role_posture`` hard-coded ``bypasses_rls = True``, so this is the
    other half, on a fully migrated database where RLS is actually enabled:

    * ``cyo_worker`` must come back clean on both paths. That is the state
      ``generation_worker.role_least_privileged`` claims in production, and
      nothing else in the suite proves the query can report it at all.
    * ``postgres`` must come back clean on the ROLE ATTRIBUTE path and dirty on
      the OWNERSHIP path. This is the finding ADR-021 exists to close, and the
      one a ``rolbypassrls``-only check misses entirely.

    #CRITICAL: security: a regression that made the ownership clause always
    return false would leave every pre-cutover deployment reporting
    ``role_least_privileged``, which is worse than no probe: it is an
    affirmative all-clear for a worker that sees every family's rows.
    """
    _admin_url, role_url = await migrate_and_connect_as(
        pg_url, f"posture_{role}_{uuid.uuid4().hex[:8]}", role
    )
    engine = create_async_engine(role_url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            posture = await measure_role_posture(session)
    finally:
        await engine.dispose()

    assert posture.role_name == role
    assert posture.via_role_attribute is expect_attribute, (
        f"{role}: rolbypassrls/rolsuper path expected "
        f"{expect_attribute}, got {posture.via_role_attribute}"
    )
    assert posture.via_table_ownership is expect_ownership, (
        f"{role}: table-ownership path expected "
        f"{expect_ownership}, got {posture.via_table_ownership}"
    )
    assert posture.bypasses_rls is (expect_attribute or expect_ownership)
