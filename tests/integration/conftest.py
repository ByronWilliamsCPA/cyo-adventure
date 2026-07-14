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
from docker.errors import DockerException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from cyo_adventure.api.deps import get_db_session
from cyo_adventure.app import app
from cyo_adventure.core.database import Base
from cyo_adventure.db.models import (
    ChildProfile,
    Family,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
    User,
)
from cyo_adventure.middleware.security import RateLimitMiddleware

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator, Iterator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

_LANTERN = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "storybook"
    / "valid"
    / "03_tier2_lantern.json"
)


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


@pytest.fixture(scope="session")
def _pg_url() -> Iterator[str]:
    """Start a Postgres 16 container for the test session.

    Skips the integration suite when no Docker daemon is reachable so a developer
    without Docker is not blocked; CI runners provide Docker for testcontainers.

    # #CRITICAL: external-resources: a CI runner that silently skips the whole
    # integration suite (rather than failing) would let a real Docker/testcontainers
    # regression pass CI unnoticed, since a skip and a pass both show green.
    # #VERIFY: when the ``CI`` environment variable is set to a truthy value
    # (GitHub Actions sets ``CI=true`` on every runner), fail loudly instead of
    # skipping. Match on truthy tokens rather than mere presence so an explicit
    # ``CI=false`` from a local shell keeps the developer-friendly skip.
    """
    try:
        container = PostgresContainer("postgres:16-alpine", driver="asyncpg")
        container.start()
    except (DockerException, OSError) as exc:
        if os.environ.get("CI", "").strip().lower() in {"1", "true", "yes", "on"}:
            pytest.fail(
                "Docker unavailable in CI runner; integration tests would "
                f"silently skip: {exc}"
            )
        pytest.skip(f"Docker/Postgres testcontainer unavailable: {exc}")
    try:
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
    """Provide an async engine with a freshly-created schema per test.

    ``NullPool`` ensures every operation uses a fresh connection bound to the
    current test's event loop, which keeps asyncpg from reusing a connection
    created on a prior (closed) loop.
    """
    eng = create_async_engine(_pg_url, poolclass=NullPool)
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Provide a session factory bound to the test engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


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

    async def _override() -> AsyncIterator[AsyncSession]:
        session = sessions()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    app.dependency_overrides[get_db_session] = _override
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
                User(family_id=fam_a.id, role="guardian", authn_subject="guardian-a"),
                User(
                    family_id=fam_a.id,
                    role="guardian",
                    is_admin=True,
                    authn_subject="dual-a",
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
                User(family_id=fam_b.id, role="guardian", authn_subject="guardian-b"),
                User(
                    family_id=fam_a.id,
                    role="child",
                    authn_subject="child-noprofile",
                    child_profile_id=None,
                ),
            ]
        )
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
                User(family_id=fam_c.id, role="guardian", authn_subject="guardian-c"),
                User(
                    family_id=fam_c.id,
                    role="child",
                    authn_subject="child-c",
                    child_profile_id=profile_c.id,
                ),
            ]
        )
        await session.commit()

        return Stranger(
            family_id=fam_c.id,
            guardian_token="guardian-c",
            child_token="child-c",
            child_profile_id=profile_c.id,
        )
