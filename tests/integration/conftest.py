"""Integration-test fixtures: a real Postgres (testcontainers) and seeded data.

The app's ``get_db_session`` unit-of-work is overridden to bind to the container
engine. A fresh schema is created per test for isolation. The seed fixture builds
two families with a guardian, a child user + profile, and a published lantern
story, which the authorization and reading-state tests reuse. A separate
``stranger`` fixture seeds a third, unrelated family (no shared storybook,
assignment, or profile with the seed families) for the cross-tenant IDOR
sweeps (P6-10).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, insert, make_url, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

from cyo_adventure.api.deps import (
    get_db_session,
    get_session_factory,
    request_unit_of_work,
)
from cyo_adventure.app import app
from cyo_adventure.core.database import Base
from cyo_adventure.db.models import (
    CATALOG_FAMILY_ID,
    CATALOG_FAMILY_NAME,
    Character,
    ChildProfile,
    Family,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
    User,
)
from cyo_adventure.middleware.security import RateLimitMiddleware
from tests.integration._docker_probe import start_or_probe_error

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator, Iterator

    from sqlalchemy.engine import URL
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
    from sqlalchemy.sql.dml import Insert

_LANTERN = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "storybook"
    / "valid"
    / "03_tier2_lantern.json"
)


def _consented(display_name: str) -> dict[str, object]:
    """Kwargs marking a fixture guardian as having already completed VPC consent.

    Every guardian the fixtures below construct goes straight into the
    database via the ORM, bypassing ``POST /onboarding`` entirely -- so
    without this, every seeded guardian would read back with
    ``consent_accepted_at IS NULL`` and trip ``api/profiles.py::
    _require_consent`` (Phase 2 / ADR-018 D1) the first time a test calls
    ``POST /api/v1/profiles``. This represents "a guardian who already
    completed onboarding," the realistic baseline for nearly every test
    scenario; a test that specifically exercises the consent gate itself
    constructs its own unconsented guardian instead (see
    ``test_profiles.py::test_create_profile_requires_recorded_consent``).

    Args:
        display_name: A human-readable signer name distinguishing which
            fixture guardian this is, for debugging only.

    Returns:
        dict[str, object]: The four ``User.consent_*`` kwargs.
    """
    return {
        "consent_accepted_at": datetime.now(UTC),
        "consent_policy_version": "test-fixture",
        "consent_signer_name": display_name,
        "consent_ip": "127.0.0.1",
    }


@dataclass(frozen=True)
class Seed:
    """Identifiers and tokens for the seeded fixture data.

    ``dual_token`` belongs to a family-A adult with the guardian base role
    AND the admin capability (``is_admin=True``), pinning the dual-role
    model: one login identity that passes both guardian-only and admin-only
    gates.
    """

    family_id: uuid.UUID
    admin_user_id: uuid.UUID
    admin_token: str
    guardian_token: str
    dual_token: str
    child_token: str
    child_profile_id: uuid.UUID
    other_guardian_token: str
    other_child_token: str
    other_child_profile_id: uuid.UUID
    storybook_id: str
    version: int
    character_id: uuid.UUID


def _seed_catalog_family_stmt() -> Insert:
    """Build the catalog-family insert shared by the session and per-test setup."""
    return insert(Family.__table__).values(
        id=CATALOG_FAMILY_ID, name=CATALOG_FAMILY_NAME
    )


def _prepare_external_database(external_url: str) -> str:
    """Build this worker's own database on an already-running Postgres server.

    The ``CYO_TEST_PG_URL`` escape hatch exists for environments where the Docker
    daemon runs but registry image pulls are blocked (Claude Code on the web is
    the motivating case: ``docker pull postgres:17-alpine`` 403s at the layer
    fetch, so ``start_or_probe_error`` cannot help). The full
    ``supabase/migrations`` chain applies cleanly to a vanilla Postgres
    cluster, so a locally-started server is a faithful substitute. Verified on
    16 (the only major installable in that environment); the container path
    below is what exercises 17.

    Two constraints on the server this points at, both load-bearing:

    * Its bootstrap superuser must NOT be named ``postgres``. The baseline dump
      creates ``postgres`` as an ordinary table-owning role, and
      ``test_worker_role_posture.py`` asserts that role is clean on the
      ``rolbypassrls``/``rolsuper`` path and dirty only on the ownership path.
      A cluster initialised with ``-U postgres`` makes that role the superuser
      and inverts the finding ADR-021 exists to measure. Use ``-U test``, which
      is what ``PostgresContainer`` does.
    * The suite must run serially (``-n0``). See the #CRITICAL note below.

    #CRITICAL: concurrency: Postgres roles are CLUSTER-global, but every xdist
    worker gets its own testcontainers *server*, so ``migrate_and_connect_as``
    can ``ALTER ROLE <role> LOGIN PASSWORD`` freely. Pointed at one shared
    server instead, two workers promoting the same migrated role overwrite each
    other's password and both hold a DSN that no longer authenticates. Measured:
    1026 errors at ``-n=auto`` against 0 at ``-n0``.
    #VERIFY: enforced below rather than documented. ``pyproject.toml``'s
    ``addopts`` carries ``-n=auto``, so the DEFAULT invocation violates this
    constraint and a reader who never reaches this docstring gets the 1026-error
    run; the guard turns that into one legible failure at setup. Per-worker
    DATABASES (below) are necessary but not sufficient, because the collision is
    on roles, which no database boundary isolates.

    Args:
        external_url: Admin ``postgresql+asyncpg://`` URL for a running server,
            taken verbatim from ``CYO_TEST_PG_URL``.

    Returns:
        str: An asyncpg URL for this worker's freshly created database, with the
        ORM schema built and the catalog family seeded.

    Raises:
        RuntimeError: If pytest-xdist is active, since cluster-global role
            collisions make this path unsafe under any worker count above one.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "")
    if worker:
        msg = (
            "CYO_TEST_PG_URL is set and pytest-xdist is active "
            f"(PYTEST_XDIST_WORKER={worker!r}). This path points every worker at "
            "ONE Postgres server, and roles are cluster-global, so concurrent "
            "ALTER ROLE ... LOGIN PASSWORD calls overwrite each other and leave "
            "workers holding DSNs that no longer authenticate (measured: 1026 "
            "errors at -n=auto, 0 at -n0). Re-run with -n0; pyproject.toml's "
            "addopts sets -n=auto, so -n0 must be passed explicitly."
        )
        raise RuntimeError(msg)
    # Serial-only by the guard above, so there is exactly one database and the
    # name is a fixed literal rather than an interpolated worker id. That is
    # also what makes the CREATE DATABASE below safe: DDL takes no bind
    # parameters, and there is no longer any environment-derived text in it.
    db_name = "cyo_test_gw0"

    def _sync(url: URL) -> str:
        return url.set(drivername="postgresql+psycopg").render_as_string(
            hide_password=False
        )

    admin_url = make_url(external_url)
    admin = create_engine(_sync(admin_url), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        admin.dispose()

    worker_url = admin_url.set(database=db_name)
    # A fresh database needs no drop_all; create_all alone mirrors what the
    # container branch below leaves behind.
    sync_engine = create_engine(_sync(worker_url))
    try:
        Base.metadata.create_all(sync_engine)
        with sync_engine.begin() as conn:
            conn.execute(_seed_catalog_family_stmt())
    finally:
        sync_engine.dispose()
    return worker_url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def _pg_url() -> Iterator[str]:
    """Start a Postgres 17 container and create its schema once per session.

    The major tracks production, which runs Postgres 17.6 (Supabase, read
    2026-08-13). It was ``postgres:16-alpine``, one major behind, so every
    schema-parity and RLS test in this suite was asserting against a different
    engine than the one the assertions are about.

    Skips the integration suite when no Docker daemon is reachable so a developer
    without Docker is not blocked; CI runners provide Docker for testcontainers.
    Set ``CYO_TEST_PG_URL`` to run against an already-started server instead; see
    ``_prepare_external_database`` for the two constraints that path carries.

    # #CRITICAL: external-resources: a CI runner that silently skips the whole
    # integration suite (rather than failing) would let a real Docker/testcontainers
    # regression pass CI unnoticed, since a skip and a pass both show green.
    # #VERIFY: when the ``CI`` environment variable is set to a truthy value
    # (GitHub Actions sets ``CI=true`` on every runner), fail loudly instead of
    # skipping. Match on truthy tokens rather than mere presence so an explicit
    # ``CI=false`` from a local shell keeps the developer-friendly skip.
    """
    external_url = os.environ.get("CYO_TEST_PG_URL", "").strip()
    if external_url:
        yield _prepare_external_database(external_url)
        return
    container, probe_error = start_or_probe_error(
        lambda: PostgresContainer("postgres:17-alpine", driver="asyncpg")
    )
    if container is None:
        if os.environ.get("CI", "").strip().lower() in {"1", "true", "yes", "on"}:
            pytest.fail(
                "Docker unavailable in CI runner; integration tests would "
                f"silently skip: {probe_error}"
            )
        pytest.skip(f"Docker/Postgres testcontainer unavailable: {probe_error}")
    try:
        # Schema DDL (drop_all/create_all) is real round-trip work against
        # Postgres; doing it once per session here, instead of once per test
        # in the `engine` fixture below, is the whole point of this split. A
        # throwaway SYNC engine (psycopg -- already a dependency for
        # testcontainers' own readiness checks) keeps this from entangling
        # with any test's asyncio event loop: it runs to completion and is
        # disposed before any test starts, so the per-test `engine` fixture
        # still gets its own fresh asyncpg connection (NullPool) tied to
        # that test's own loop, exactly as before.
        sync_engine = create_engine(container.get_connection_url(driver="psycopg"))
        try:
            Base.metadata.drop_all(sync_engine)
            Base.metadata.create_all(sync_engine)
            with sync_engine.begin() as conn:
                # See the `engine` fixture: create_all builds tables only,
                # with no baseline data, so catalog-origin request tests
                # would otherwise fail their family_id FK insert. Reseeded
                # per-test there (after each TRUNCATE), not just here.
                conn.execute(_seed_catalog_family_stmt())
        finally:
            sync_engine.dispose()
        yield container.get_connection_url()
    finally:
        container.stop()


@pytest.fixture(scope="session")
def pg_url(_pg_url: str) -> str:
    """Public alias for the session-scoped ``_pg_url`` container fixture.

    ``_pg_url`` is named with a leading underscore by this module's own
    convention; consuming it directly as a test parameter trips Ruff's PT019
    (a leading-underscore parameter is treated as fixture-for-side-effect-only,
    not a value the test reads). Tests that need the actual URL string (e.g.
    the schema-parity gate in ``test_schema_parity.py``, which builds sibling
    databases on the same container) should depend on this alias instead.
    """
    return _pg_url


@pytest_asyncio.fixture
async def engine(_pg_url: str) -> AsyncIterator[AsyncEngine]:
    """Provide an async engine with all tables truncated for test isolation.

    The schema (tables/constraints/indexes) is created once per session by
    `_pg_url`; each test only needs its DATA reset, not the structure rebuilt
    from scratch. A single multi-table ``TRUNCATE ... CASCADE`` resets every
    table atomically regardless of listing order (unlike per-table DELETE,
    which needs FK-respecting order), and is materially cheaper than a
    drop_all/create_all DDL cycle since it never touches table/constraint/
    index definitions.

    Table names are interpolated directly (not bound as SQL parameters)
    because they come from this project's own ``Base.metadata``, never from
    external input; TRUNCATE also does not support parameterized identifiers.

    ``NullPool`` ensures every operation uses a fresh connection bound to the
    current test's event loop, which keeps asyncpg from reusing a connection
    created on a prior (closed) loop.
    """
    eng = create_async_engine(_pg_url, poolclass=NullPool)
    try:
        table_names = ", ".join(
            f'"{table.name}"' for table in Base.metadata.sorted_tables
        )
        async with eng.begin() as conn:
            await conn.execute(
                text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE")
            )
            # Seed the well-known system catalog family (#173) that a
            # TRUNCATE just removed. Production gets this row from
            # supabase/migrations; nothing else provides baseline data, so
            # catalog-origin request tests would otherwise fail their
            # family_id FK insert.
            await conn.execute(_seed_catalog_family_stmt())
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Provide a session factory bound to the test engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


# ADR-021/ADR-022 RLS-enforcement harness note.
#
# The fixtures above connect as the container's owner superuser, which holds
# implicit BYPASSRLS: no RLS policy can ever be seen filtering rows through
# them, so the IDOR sweeps prove only the app-layer authz, never the database
# floor. The RLS-enforcement tests (``test_rls_service_roles.py``,
# ``test_rls_tier1_enforcement.py``) instead build a fully migrated database
# and connect as the least-privilege ``cyo_api`` role via
# ``_migration_utils.migrate_and_connect_as`` -- policies live in
# ``supabase/migrations``, never in ``Base.metadata``, so only a migrated
# schema (not the ORM ``create_all`` fixtures here) can exercise them.


def _reset_rate_limiter() -> None:
    """Clear the singleton app's in-memory rate-limiter bucket.

    The app is a module-level singleton whose ``RateLimitMiddleware`` keeps
    per-IP request timestamps. Integration tests share one app instance and one
    client IP, so the 60-rpm bucket would otherwise leak across tests and cause
    order-dependent 429 responses (a request budget exhausted by an earlier
    test). Resetting it gives each test a fresh budget, matching the
    fresh-schema-per-test isolation the harness already provides. Building the
    stack on first use pins the same instance that subsequently serves requests.
    """
    if app.middleware_stack is None:
        app.middleware_stack = app.build_middleware_stack()
    node: object | None = app.middleware_stack
    while node is not None:
        if isinstance(node, RateLimitMiddleware):
            node.requests.clear()
        node = getattr(node, "app", None)


@pytest.fixture(autouse=True)
def _child_session_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure a child-session signing secret on the shared app singleton.

    The module-level ``settings`` singleton carries no secret by default (local
    dev needs none), so any endpoint that mints or verifies a child session
    would raise ConfigurationError. Applying it suite-wide keeps mint/verify
    deterministic for every integration test (including the authz matrix). The
    value is >=32 bytes to avoid PyJWT's InsecureKeyLengthWarning, which the
    suite's ``filterwarnings = ["error"]`` would otherwise escalate to a
    failure.
    """
    from pydantic import SecretStr

    from cyo_adventure.core.config import settings

    monkeypatch.setattr(
        settings,
        "child_session_secret",
        SecretStr("integration-child-session-secret-0123456789ab"),
    )


@pytest.fixture(autouse=True)
def _device_grant_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure a device-grant signing secret on the shared app singleton.

    Mirrors ``_child_session_secret``: the module-level ``settings`` singleton
    carries no secret by default, so any endpoint that mints or verifies a
    device grant would raise ConfigurationError. A DISTINCT value from the
    child-session secret pins that the two token families never accidentally
    share a signing key.
    """
    from pydantic import SecretStr

    from cyo_adventure.core.config import settings

    monkeypatch.setattr(
        settings,
        "device_grant_secret",
        SecretStr("integration-device-grant-secret-0123456789abcdef"),
    )


@pytest_asyncio.fixture
async def client(
    sessions: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    """Provide an HTTP client with the DB session dependency overridden."""

    # Only the SESSION is swapped, for the container engine; the unit-of-work
    # semantics come from the same context manager production uses, so the
    # commit still lands where UnitOfWorkMiddleware puts it (before the
    # response is sent) rather than in a copy of the logic that can drift.
    async def _override(request: Request) -> AsyncIterator[AsyncSession]:
        async with request_unit_of_work(request, sessions()) as session:
            yield session

    app.dependency_overrides[get_db_session] = _override
    # A route whose database work outlives the handler call cannot use the
    # request-scoped unit of work above and takes a session FACTORY instead
    # (api/notifications.py's SSE stream: see deps.get_session_factory). That
    # factory is a dependency precisely so it can be bound to the container
    # engine here; without this override such a route would silently fall
    # back to the module-level factory and talk to the real engine mid-test.
    app.dependency_overrides[get_session_factory] = lambda: sessions

    _reset_rate_limiter()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seed(sessions: async_sessionmaker[AsyncSession]) -> Seed:
    """Seed two families, users, a child profile, and a published story."""
    blob = json.loads(_LANTERN.read_text(encoding="utf-8"))
    async with sessions() as session:
        fam_a = Family(name="Family A")
        fam_b = Family(name="Family B")
        session.add_all([fam_a, fam_b])
        await session.flush()

        profile_a = ChildProfile(
            family_id=fam_a.id, display_name="Reader A", age_band="10-13"
        )
        profile_b = ChildProfile(
            family_id=fam_b.id, display_name="Reader B", age_band="10-13"
        )
        session.add_all([profile_a, profile_b])
        await session.flush()

        admin_a = User(
            family_id=fam_a.id, role="admin", is_admin=True, authn_subject="admin-a"
        )
        session.add_all(
            [
                admin_a,
                User(
                    family_id=fam_a.id,
                    role="guardian",
                    authn_subject="guardian-a",
                    **_consented("Guardian A"),
                ),
                User(
                    family_id=fam_a.id,
                    role="guardian",
                    is_admin=True,
                    authn_subject="dual-a",
                    **_consented("Dual-Role Guardian A"),
                ),
                User(
                    family_id=fam_a.id,
                    role="child",
                    authn_subject="child-a",
                    child_profile_id=profile_a.id,
                ),
                User(
                    family_id=fam_b.id,
                    role="child",
                    authn_subject="child-b",
                    child_profile_id=profile_b.id,
                ),
                User(
                    family_id=fam_b.id,
                    role="guardian",
                    authn_subject="guardian-b",
                    **_consented("Guardian B"),
                ),
                User(
                    family_id=fam_a.id,
                    role="child",
                    authn_subject="child-noprofile",
                    child_profile_id=None,
                ),
            ]
        )
        await session.flush()

        # ADR-028: a pre-existing character on profile_a, owned by family A,
        # for the authz matrix's load-then-authorize routes (PATCH/activate/
        # retire), which need a real row in the path to exercise the
        # "disallowed role gets exactly 403" invariant rather than a 404 from
        # a random id that never reaches the ownership check.
        character_a = Character(
            child_profile_id=profile_a.id,
            family_id=fam_a.id,
            name="Route Matrix Rowan",
            archetype="scout",
            look="avatar_01",
        )
        session.add(character_a)
        await session.flush()

        story_id = str(blob["id"])
        version = int(blob["version"])
        session.add(
            Storybook(
                id=story_id,
                family_id=fam_a.id,
                current_published_version=version,
                status="published",
            )
        )
        session.add(
            StorybookVersion(
                storybook_id=story_id,
                version=version,
                blob=blob,
                approved_by=admin_a.id,
                published_at=datetime.now(UTC),
            )
        )
        session.add(
            StorybookAssignment(
                child_profile_id=profile_a.id,
                storybook_id=story_id,
            )
        )
        await session.commit()

        return Seed(
            family_id=fam_a.id,
            admin_user_id=admin_a.id,
            admin_token="admin-a",
            guardian_token="guardian-a",
            dual_token="dual-a",
            child_token="child-a",
            child_profile_id=profile_a.id,
            other_guardian_token="guardian-b",
            other_child_token="child-b",
            other_child_profile_id=profile_b.id,
            storybook_id=story_id,
            version=version,
            character_id=character_a.id,
        )


def auth(token: str) -> dict[str, str]:
    """Build an Authorization header for a bearer token."""
    return {"Authorization": f"Bearer {token}"}


async def mint_device_token(client: AsyncClient, guardian_token: str) -> str:
    """Mint a device grant for a guardian's family and return the raw JWT.

    Shared helper (ADR-014 phase 2) for every module that needs a live
    ``DEVICE`` principal token: the child-session-mint, profiles-list, and
    authz-matrix suites exercising the two endpoints a device grant may
    reach, mirroring ``test_device_grants.py``'s own round-trip tests.

    Args:
        client: The HTTP client fixture.
        guardian_token: The minting guardian's dev-stub token; the resulting
            device grant is scoped to that guardian's own family.

    Returns:
        str: The signed device grant JWT (``cyo-device-grant`` audience).
    """
    resp = await client.post(
        "/api/v1/device-grants",
        json={},
        headers=auth(guardian_token),
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["token"]
    assert isinstance(token, str)
    return token


@dataclass(frozen=True)
class Stranger:
    """Identifiers and tokens for a third family with zero ties to A or B.

    P6-10: the IDOR/authz suite's two-family fixture (``seed``, family A and
    B) catches a query that checks "is this OTHER specific family" but misses
    a query filtered by "not mine" (e.g. ``family_id != caller_family_id``)
    or a handler that forgets to filter by family at all and happens to pass
    only because family B's rows sort after family A's. A completely
    unrelated third family (no shared storybook, assignment, or profile with
    A or B) catches both of those bug classes: any code path that reaches
    family C's data cannot be explained by an accidental A/B adjacency.
    """

    family_id: uuid.UUID
    guardian_token: str
    child_token: str
    child_profile_id: uuid.UUID
    character_id: uuid.UUID


@pytest_asyncio.fixture
async def stranger(sessions: async_sessionmaker[AsyncSession]) -> Stranger:
    """Seed a third, stranger family (family C): a guardian and one child.

    Deliberately minimal: no storybook, assignment, or story request ties
    family C to family A or B. Tests that need one of those attach it
    directly to ``stranger.family_id``/``stranger.child_profile_id``.
    """
    async with sessions() as session:
        fam_c = Family(name="Family C (stranger)")
        session.add(fam_c)
        await session.flush()

        profile_c = ChildProfile(
            family_id=fam_c.id, display_name="Reader C", age_band="10-13"
        )
        session.add(profile_c)
        await session.flush()

        session.add_all(
            [
                User(
                    family_id=fam_c.id,
                    role="guardian",
                    authn_subject="guardian-c",
                    **_consented("Guardian C"),
                ),
                User(
                    family_id=fam_c.id,
                    role="child",
                    authn_subject="child-c",
                    child_profile_id=profile_c.id,
                ),
            ]
        )

        # ADR-028: a character on profile_c, owned by family C, so the
        # id-addressed character routes (PATCH/activate/retire) in
        # _CROSS_FAMILY_CHILD_ROUTE_KEYS have a real, stranger-owned
        # character_id to substitute into the reverse-direction IDOR test
        # (test_family_a_child_cannot_reach_stranger_family_profile).
        character_c = Character(
            child_profile_id=profile_c.id,
            family_id=fam_c.id,
            name="Stranger Character",
            archetype="scout",
            look="avatar_01",
        )
        session.add(character_c)
        await session.commit()

        return Stranger(
            family_id=fam_c.id,
            guardian_token="guardian-c",
            child_token="child-c",
            child_profile_id=profile_c.id,
            character_id=character_c.id,
        )
