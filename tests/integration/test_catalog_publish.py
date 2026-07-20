"""Integration tests for the catalog-publish CLI's DB-backed scoping boundary.

``_load_catalog_story_for_update`` runs a real ``SELECT ... FOR UPDATE``
against Postgres, so it is exercised here (rather than the fake-session unit
coverage in ``tests/unit/test_catalog_publish.py``) against the real schema.
The catalog family row (``CATALOG_FAMILY_ID``) is seeded automatically by the
``engine`` fixture's per-test setup (see ``tests/integration/conftest.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.core.exceptions import ResourceNotFoundError
from cyo_adventure.db.models import (
    CATALOG_FAMILY_ID,
    Family,
    Storybook,
    StorybookVersion,
    User,
)
from cyo_adventure.publishing.catalog_publish import (
    _load_admin_principal,
    _load_catalog_story_for_update,
    promote_catalog_story,
)
from tests.conftest import make_clean_moderation_report

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_promote_catalog_story_refuses_a_non_catalog_story(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A storybook owned by a real (non-catalog) family is refused.

    Asserts requirement (a): ``_load_catalog_story_for_update`` is this
    command's entire safety boundary, so a story that exists but belongs to
    an ordinary family must raise the same ResourceNotFoundError as a
    genuinely missing id, never a distinguishing "wrong family" error.
    """
    async with sessions() as session:
        family = Family(name="A Real Family")
        session.add(family)
        await session.flush()
        book = Storybook(
            id="real-family-story",
            family_id=family.id,
            status="in_review",
        )
        session.add(book)
        await session.flush()

        with pytest.raises(ResourceNotFoundError, match="real-family-story"):
            await _load_catalog_story_for_update(session, "real-family-story")


async def test_promote_catalog_story_promotes_a_catalog_story_to_catalog_visibility(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The full assembly (story load + admin check + approve) succeeds end to end.

    Covers the happy path this module exists to serve: a catalog-owned,
    in_review, moderation-clean story promoted by a real admin user comes
    back published with visibility=catalog.
    """
    async with sessions() as session:
        admin_family = Family(name="Admin Family")
        session.add(admin_family)
        await session.flush()
        admin = User(
            family_id=admin_family.id,
            role="admin",
            is_admin=True,
            authn_subject="catalog-publish-admin",
        )
        session.add(admin)
        await session.flush()

        book = Storybook(
            id="catalog-story-1",
            family_id=CATALOG_FAMILY_ID,
            status="in_review",
        )
        session.add(book)
        await session.flush()
        session.add(
            StorybookVersion(
                storybook_id="catalog-story-1",
                version=1,
                blob={"id": "catalog-story-1"},
                moderation_report=make_clean_moderation_report(),
            )
        )
        await session.flush()

        version_row = await promote_catalog_story(session, "catalog-story-1", admin.id)

        assert book.status == "published"
        assert book.visibility == "catalog"
        assert version_row.approved_by == admin.id
        assert version_row.published_at is not None


async def test_load_admin_principal_accepts_a_real_admin_user(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A real, persisted admin User builds an is_admin Principal (DB round trip).

    Complements the fake-session unit coverage in
    ``tests/unit/test_catalog_publish.py`` with one assertion against a real
    row loaded through ``session.get``.
    """
    async with sessions() as session:
        family = Family(name="Admin Family 2")
        session.add(family)
        await session.flush()
        admin = User(
            family_id=family.id,
            role="admin",
            is_admin=True,
            authn_subject="another-admin",
        )
        session.add(admin)
        await session.flush()

        principal = await _load_admin_principal(session, admin.id)

        assert principal.is_admin is True
        assert principal.user_id == admin.id
