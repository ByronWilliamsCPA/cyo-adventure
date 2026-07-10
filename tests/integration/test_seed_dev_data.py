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

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import and_, exists, select

from cyo_adventure.db.models import (
    ChildProfile,
    Family,
    Series,
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
_ADMIN_SUBJECT = "dev-admin"
_REVIEW_STORY_ID = "s_bridge_builder"
_UNRELATED_PROFILE_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


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

        # 2 tier stories + 1 in-review story + 2 series books ("Ember Trail" 1/2).
        versions = (await session.scalars(select(StorybookVersion))).all()
        assert len(versions) == 5
        published_versions = [v for v in versions if v.storybook_id != _REVIEW_STORY_ID]
        for version in published_versions:
            assert version.approved_by == guardian.id
            assert version.published_at is not None

        assignments = (await session.scalars(select(StorybookAssignment))).all()
        assert len(assignments) == 5
        assert {a.child_profile_id for a in assignments} == {profile.id}
        assert {a.storybook_id for a in assignments} == {
            v.storybook_id for v in versions
        }

    story_ids = await _library_storybook_ids(sessions, profile.id)
    assert set(story_ids) == {v.storybook_id for v in published_versions}


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
        assert len(assignments) == 5
        assert len(versions) == 5


async def test_seed_dev_data_seeds_admin_and_review_story(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The seed provides an admin principal and an approvable in-review story."""
    await seed_dev_data(engine=engine, session_factory=sessions)
    async with sessions() as session:
        admin = await session.scalar(
            select(User).where(User.authn_subject == _ADMIN_SUBJECT)
        )
        assert admin is not None
        assert admin.role == "admin"

        profile = await session.scalar(
            select(ChildProfile).where(ChildProfile.display_name == "Dev Reader")
        )
        assert profile is not None

        review = await session.scalar(
            select(Storybook).where(Storybook.id == _REVIEW_STORY_ID)
        )
        assert review is not None
        assert review.status == "in_review"
        assert review.current_published_version is None

        version = await session.scalar(
            select(StorybookVersion).where(
                StorybookVersion.storybook_id == _REVIEW_STORY_ID
            )
        )
        assert version is not None
        # approve() refuses a version without a moderation report (service.py),
        # so the seed must carry one; a flag finding makes the review surface
        # render a flagged passage.
        assert version.moderation_report is not None
        assert version.moderation_report["summary"]["soft_flag"] is True
        assert version.approved_by is None

        assignment = await session.scalar(
            select(StorybookAssignment).where(
                StorybookAssignment.storybook_id == _REVIEW_STORY_ID
            )
        )
        assert assignment is not None

    # Not yet approved: must NOT clear the kid library gate.
    story_ids = await _library_storybook_ids(sessions, profile.id)
    assert _REVIEW_STORY_ID not in story_ids


async def test_seed_dev_data_seeds_unrelated_family_profile(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The seed provides a second family's child profile, genuinely isolated
    from the guardian's own family, for naive-kid-misuse-real.spec.ts to prove
    authorize_profile rejects a cross-family profile id."""
    await seed_dev_data(engine=engine, session_factory=sessions)
    async with sessions() as session:
        guardian_profile = await session.scalar(
            select(ChildProfile).where(ChildProfile.display_name == "Dev Reader")
        )
        assert guardian_profile is not None

        unrelated_profile = await session.scalar(
            select(ChildProfile).where(ChildProfile.id == _UNRELATED_PROFILE_ID)
        )
        assert unrelated_profile is not None
        assert unrelated_profile.display_name == "Unrelated Reader"

        assert unrelated_profile.family_id != guardian_profile.family_id

        unrelated_family = await session.scalar(
            select(Family).where(Family.id == unrelated_profile.family_id)
        )
        guardian_family = await session.scalar(
            select(Family).where(Family.id == guardian_profile.family_id)
        )
        assert unrelated_family is not None
        assert guardian_family is not None
        assert unrelated_family.id != guardian_family.id


async def test_seed_dev_data_seeds_series_chain(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The dev seed creates a two-book, state-carrying series for the dev profile."""
    await seed_dev_data(engine=engine, session_factory=sessions)

    async with sessions() as session:
        profile = await session.scalar(
            select(ChildProfile).where(ChildProfile.display_name == "Dev Reader")
        )
        assert profile is not None

        series = await session.scalar(
            select(Series).where(Series.title == "Ember Trail")
        )
        assert series is not None
        assert series.carries_state is True

        books = (
            await session.scalars(
                select(Storybook).where(Storybook.series_id == series.id)
            )
        ).all()
        books_by_id = {book.id: book for book in books}
        assert set(books_by_id) == {"s_dev_ember_1", "s_dev_ember_2"}

        for story_id, expected_index in (
            ("s_dev_ember_1", 1),
            ("s_dev_ember_2", 2),
        ):
            book = books_by_id[story_id]
            assert book.status == "published"
            assert book.current_published_version == 1
            assert book.book_index == expected_index

            version = await session.scalar(
                select(StorybookVersion).where(
                    StorybookVersion.storybook_id == story_id
                )
            )
            assert version is not None
            meta = version.blob["metadata"]
            assert isinstance(meta, dict)
            series_block = meta["series"]
            assert isinstance(series_block, dict)
            assert series_block["series_id"] == str(series.id)
            assert series_block["series_entry_node"] == version.blob["start_node"]

            assignment = await session.scalar(
                select(StorybookAssignment).where(
                    StorybookAssignment.storybook_id == story_id,
                    StorybookAssignment.child_profile_id == profile.id,
                )
            )
            assert assignment is not None
