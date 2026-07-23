"""Seed script publishes the "Ember Trail" series to the shared CATALOG.

Exercises the actual `scripts.seed_series_catalog.seed` coroutine against a
testcontainers Postgres (the same pattern `tests/integration/test_seed_dev_data.py`
uses), asserting: the series and its two books land under `CATALOG_FAMILY_ID`
with `visibility="catalog"`, each `StorybookVersion.approved_by` is set (the
library read gate filters on it), the blob embeds the real `Series.id` and
passes `Storybook.model_validate`, and each book is assigned to the resolved
test child profile. Also pins the fail-safe resolution guards: the script must
refuse to run rather than guess when zero or multiple test-family child
profiles exist, when no admin user exists, and when required environment
variables (including the production confirmation gate) are absent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cyo_adventure.db.models import (
    ChildProfile,
    Family,
    Series,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
    User,
)
from cyo_adventure.storybook.models import Storybook as StorybookDoc
from scripts.seed_series_catalog import seed

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_BOOK_IDS = ("s_dev_ember_1", "s_dev_ember_2")


def _set_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    values = {
        "ENVIRONMENT": "staging",
        "CYO_ADVENTURE_DATABASE_URL": "postgresql+asyncpg://u:p@host:5432/postgres",
        **overrides,
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


async def _seed_family_with_child(
    session: AsyncSession, family_name: str, display_name: str = "E2E Test Reader"
) -> tuple[Family, ChildProfile]:
    """Insert a family and one child profile under it, flushed for real ids."""
    family = Family(name=family_name)
    session.add(family)
    await session.flush()
    profile = ChildProfile(
        family_id=family.id, display_name=display_name, age_band="10-13"
    )
    session.add(profile)
    await session.flush()
    return family, profile


async def _seed_admin(
    session: AsyncSession, family_id: uuid.UUID, subject: str
) -> User:
    """Insert an is_admin=True user attributed to the given family."""
    admin = User(
        family_id=family_id, role="admin", is_admin=True, authn_subject=subject
    )
    session.add(admin)
    await session.flush()
    return admin


async def test_seed_series_catalog_inserts_series_books_and_assignment(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A full seed inserts one Series, two catalog books, and their assignments."""
    _set_env(monkeypatch)
    async with sessions() as session:
        family, profile = await _seed_family_with_child(session, "E2E Test Family")
        admin = await _seed_admin(session, family.id, "series-admin")
        await session.commit()
        admin_id, profile_id = admin.id, profile.id

    await seed(engine=engine, session_factory=sessions)

    async with sessions() as session:
        series = await session.scalar(
            select(Series).where(Series.title == "Ember Trail")
        )
        assert series is not None
        assert series.age_band == "10-13"
        assert series.carries_state is True
        assert series.created_by == admin_id

        books = (
            await session.scalars(
                select(Storybook).where(Storybook.series_id == series.id)
            )
        ).all()
        books_by_id = {book.id: book for book in books}
        assert set(books_by_id) == set(_BOOK_IDS)

        for story_id, expected_index in (("s_dev_ember_1", 1), ("s_dev_ember_2", 2)):
            book = books_by_id[story_id]
            assert book.status == "published"
            assert book.visibility == "catalog"
            assert book.current_published_version == 1
            assert book.book_index == expected_index
            assert book.created_by == admin_id

            version = await session.scalar(
                select(StorybookVersion).where(
                    StorybookVersion.storybook_id == story_id
                )
            )
            assert version is not None
            assert version.approved_by == admin_id
            assert version.published_at is not None
            # #ASSUME: data-integrity: every reading-state PUT re-validates the
            # pinned blob via Storybook.model_validate (api/reading.py ->
            # player/replay.py::_parse); a seeded blob that fails the schema
            # gate would 422 every progress save on the real stack.
            # #VERIFY: this call fails the test on a future fixture edit that
            # breaks the schema gate.
            StorybookDoc.model_validate(version.blob)
            meta = version.blob["metadata"]
            assert isinstance(meta, dict)
            series_block = meta["series"]
            assert isinstance(series_block, dict)
            assert series_block["series_id"] == str(series.id)
            assert series_block["book_index"] == expected_index

            assignment = await session.scalar(
                select(StorybookAssignment).where(
                    StorybookAssignment.storybook_id == story_id,
                    StorybookAssignment.child_profile_id == profile_id,
                )
            )
            assert assignment is not None
            assert assignment.assigned_by == admin_id


async def test_seed_series_catalog_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A second run is a no-op: no duplicate rows, no raised exception.

    Guarded on the first book's fixed id, so the second call does not even
    need the test-family profile/admin to still exist.
    """
    _set_env(monkeypatch)
    async with sessions() as session:
        family, _profile = await _seed_family_with_child(session, "Test Family")
        await _seed_admin(session, family.id, "series-admin")
        await session.commit()

    await seed(engine=engine, session_factory=sessions)
    await seed(engine=engine, session_factory=sessions)

    async with sessions() as session:
        series_rows = (
            await session.scalars(select(Series).where(Series.title == "Ember Trail"))
        ).all()
        assert len(series_rows) == 1

        versions = (await session.scalars(select(StorybookVersion))).all()
        assert len(versions) == 2

        assignments = (await session.scalars(select(StorybookAssignment))).all()
        assert len(assignments) == 2


async def test_seed_series_catalog_fails_when_no_test_family_profile(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """No matching test-family child profile: refuse rather than guess."""
    _set_env(monkeypatch)
    async with sessions() as session:
        # Only a real-looking family exists; never a valid assignment target.
        family, _profile = await _seed_family_with_child(session, "Williams Family")
        await _seed_admin(session, family.id, "series-admin")
        await session.commit()

    with pytest.raises(SystemExit):
        await seed(engine=engine, session_factory=sessions)

    async with sessions() as session:
        series_count = await session.scalar(
            select(Series).where(Series.title == "Ember Trail")
        )
        assert series_count is None


async def test_seed_series_catalog_fails_when_multiple_test_family_profiles(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Two matching test-family profiles: ambiguous, refuse rather than guess."""
    _set_env(monkeypatch)
    async with sessions() as session:
        family_a, _profile_a = await _seed_family_with_child(
            session, "E2E Test Family", "Reader One"
        )
        _family_b, _profile_b = await _seed_family_with_child(
            session, "Test Family", "Reader Two"
        )
        await _seed_admin(session, family_a.id, "series-admin")
        await session.commit()

    with pytest.raises(SystemExit):
        await seed(engine=engine, session_factory=sessions)


async def test_seed_series_catalog_respects_assign_family_override(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """SEED_SERIES_ASSIGN_FAMILY replaces, not augments, the default allowlist."""
    _set_env(monkeypatch, SEED_SERIES_ASSIGN_FAMILY="Custom QA Family")
    async with sessions() as session:
        # A default-allowlist family also exists; the override must win and
        # resolve to the custom family's profile, not this one.
        default_family, _default_profile = await _seed_family_with_child(
            session, "E2E Test Family", "Default Reader"
        )
        await _seed_admin(session, default_family.id, "default-admin")
        custom_family, custom_profile = await _seed_family_with_child(
            session, "Custom QA Family", "Custom Reader"
        )
        await _seed_admin(session, custom_family.id, "custom-admin")
        await session.commit()
        custom_profile_id = custom_profile.id

    await seed(engine=engine, session_factory=sessions)

    async with sessions() as session:
        assignments = (await session.scalars(select(StorybookAssignment))).all()
        assert {a.child_profile_id for a in assignments} == {custom_profile_id}


async def test_seed_series_catalog_fails_when_no_admin_user(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A test-family profile exists but no admin user: refuse rather than
    attribute the series/books to no one."""
    _set_env(monkeypatch)
    async with sessions() as session:
        await _seed_family_with_child(session, "E2E Test Family")
        await session.commit()

    with pytest.raises(SystemExit):
        await seed(engine=engine, session_factory=sessions)


async def test_seed_series_catalog_prefers_admin_in_test_family(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """When multiple admins exist, the one in the resolved test family wins."""
    _set_env(monkeypatch)
    async with sessions() as session:
        other_family = Family(name="Other Family")
        session.add(other_family)
        await session.flush()
        await _seed_admin(session, other_family.id, "other-admin")

        family, _profile = await _seed_family_with_child(session, "Test Family")
        test_admin = await _seed_admin(session, family.id, "test-family-admin")
        await session.commit()
        test_admin_id = test_admin.id

    await seed(engine=engine, session_factory=sessions)

    async with sessions() as session:
        series = await session.scalar(
            select(Series).where(Series.title == "Ember Trail")
        )
        assert series is not None
        assert series.created_by == test_admin_id


async def test_seed_series_catalog_requires_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every required env var is named in the exit message when missing."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("CYO_ADVENTURE_DATABASE_URL", raising=False)

    with pytest.raises(SystemExit) as exc:
        await seed()
    message = str(exc.value)
    assert "ENVIRONMENT" in message
    assert "CYO_ADVENTURE_DATABASE_URL" in message


async def test_seed_series_catalog_rejects_invalid_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ENVIRONMENT outside {staging, production} is refused."""
    _set_env(monkeypatch, ENVIRONMENT="development")

    with pytest.raises(SystemExit) as exc:
        await seed()
    assert "development" in str(exc.value)


async def test_seed_series_catalog_requires_confirm_for_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ENVIRONMENT=production without SEED_CONFIRM=1 is refused."""
    _set_env(monkeypatch, ENVIRONMENT="production")
    monkeypatch.delenv("SEED_CONFIRM", raising=False)

    with pytest.raises(SystemExit) as exc:
        await seed()
    message = str(exc.value)
    assert "production" in message
    assert "SEED_CONFIRM" in message


async def test_seed_series_catalog_production_with_confirm_reaches_db(
    monkeypatch: pytest.MonkeyPatch,
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """ENVIRONMENT=production with SEED_CONFIRM=1 proceeds past the guard."""
    _set_env(monkeypatch, ENVIRONMENT="production", SEED_CONFIRM="1")
    async with sessions() as session:
        family, _profile = await _seed_family_with_child(session, "Test Family")
        await _seed_admin(session, family.id, "series-admin")
        await session.commit()

    await seed(engine=engine, session_factory=sessions)

    async with sessions() as session:
        series = await session.scalar(
            select(Series).where(Series.title == "Ember Trail")
        )
        assert series is not None
