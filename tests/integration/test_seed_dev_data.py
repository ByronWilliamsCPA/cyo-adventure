"""Seed script produces stories that pass the library read gates.

Exercises the actual `scripts.seed_dev_data.seed_dev_data` function against a
testcontainers Postgres (the same pattern `tests/integration/conftest.py`
uses for the app's own fixtures), then asserts the seeded rows clear the
library read gate: `StorybookVersion.approved_by` must be set and a
`StorybookAssignment` row must exist for the seeded profile (alongside a
published status and a current version). The missing `approved_by` and the
missing assignment were the root cause of every seeded story 404ing in a fresh
local dev database. `published_at` is stamped for data hygiene; the read gate
in `api/library.py` does not itself check it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import and_, exists, select

from cyo_adventure.db.models import (
    ChildProfile,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
    User,
)
from scripts.seed_dev_data import seed_dev_data

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# Mirrors scripts.seed_dev_data's private subject constants; duplicated here
# (rather than importing the underscore-prefixed names) to avoid a
# reportPrivateUsage warning for a cross-module private-name reference.
_GUARDIAN_SUBJECT = "dev-guardian"
_CHILD_SUBJECT = "dev-child"


async def _library_storybook_ids(
    sessions: async_sessionmaker[AsyncSession], profile_id: object
) -> list[str]:
    """Run the library-listing read-gate predicates directly against the schema.

    Reproduces the published/approved/assigned predicates `api/library.py`'s
    listing gate applies, scoped to the profile via the assignment EXISTS
    clause. It intentionally omits the endpoint's family scoping and HTTP auth:
    the test only needs to confirm the seeded rows clear the read-gate
    predicates, and the single seeded profile makes assignment scoping
    sufficient here.
    """
    async with sessions() as session:
        rows = await session.scalars(
            select(Storybook)
            .join(
                StorybookVersion,
                and_(
                    StorybookVersion.storybook_id == Storybook.id,
                    StorybookVersion.version == Storybook.current_published_version,
                ),
            )
            .where(
                Storybook.status == "published",
                Storybook.current_published_version.is_not(None),
                StorybookVersion.approved_by.is_not(None),
                exists().where(
                    StorybookAssignment.storybook_id == Storybook.id,
                    StorybookAssignment.child_profile_id == profile_id,
                ),
            )
        )
        return [book.id for book in rows.all()]


async def test_seed_dev_data_publishes_and_assigns_both_stories(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """After seeding, both stories satisfy the library read gates for the profile."""
    await seed_dev_data(engine=engine, session_factory=sessions)

    async with sessions() as session:
        profile = await session.scalar(
            select(ChildProfile).where(ChildProfile.display_name == "Dev Reader")
        )
        assert profile is not None
        guardian = await session.scalar(
            select(User).where(User.authn_subject == _GUARDIAN_SUBJECT)
        )
        assert guardian is not None
        child = await session.scalar(
            select(User).where(User.authn_subject == _CHILD_SUBJECT)
        )
        assert child is not None
        assert child.child_profile_id == profile.id

        versions = (await session.scalars(select(StorybookVersion))).all()
        assert len(versions) == 2
        for version in versions:
            assert version.approved_by == guardian.id
            assert version.published_at is not None

        assignments = (await session.scalars(select(StorybookAssignment))).all()
        assert len(assignments) == 2
        assert {a.child_profile_id for a in assignments} == {profile.id}
        assert {a.storybook_id for a in assignments} == {
            v.storybook_id for v in versions
        }

    story_ids = await _library_storybook_ids(sessions, profile.id)
    assert set(story_ids) == {v.storybook_id for v in versions}


async def test_seed_dev_data_is_idempotent(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A second run is a no-op: the guardian-existence guard returns early before
    re-inserting, so no composite-key/unique constraint is ever exercised twice."""
    await seed_dev_data(engine=engine, session_factory=sessions)
    await seed_dev_data(engine=engine, session_factory=sessions)

    async with sessions() as session:
        assignments = (await session.scalars(select(StorybookAssignment))).all()
        versions = (await session.scalars(select(StorybookVersion))).all()
        assert len(assignments) == 2
        assert len(versions) == 2
