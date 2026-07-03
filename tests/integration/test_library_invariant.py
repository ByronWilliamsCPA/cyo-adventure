"""The no-unapproved-publish invariant across both library read paths."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import Storybook, StorybookVersion

from .conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _add_unapproved_published_story(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> str:
    """Insert a status='published' story in Family A whose version is unapproved."""
    async with sessions() as session:
        story_id = "unapproved-but-published"
        session.add(
            Storybook(
                id=story_id,
                family_id=seed.family_id,
                current_published_version=1,
                status="published",
            )
        )
        session.add(
            StorybookVersion(storybook_id=story_id, version=1, blob={"id": story_id})
        )
        await session.commit()
        return story_id


async def _add_approved_unassigned_story(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> str:
    """Insert an approved, published story in Family A with no profile assignment."""
    async with sessions() as session:
        story_id = "approved-but-unassigned"
        session.add(
            Storybook(
                id=story_id,
                family_id=seed.family_id,
                current_published_version=1,
                status="published",
            )
        )
        session.add(
            StorybookVersion(
                storybook_id=story_id,
                version=1,
                blob={"id": story_id},
                approved_by=seed.admin_user_id,
            )
        )
        await session.commit()
        return story_id


async def test_unassigned_story_not_in_library(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """An approved published story unassigned to the profile is excluded (Task 6).

    Pins the assignment gate behaviorally: the story clears every other predicate
    (family, published, approved, current), so its absence proves the EXISTS on
    storybook_assignment, not another filter, is what withholds it.
    """
    unassigned_id = await _add_approved_unassigned_story(sessions, seed)
    resp = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200
    listed = {item["id"] for item in resp.json()["stories"]}
    assert seed.storybook_id in listed  # the assigned seed story shows
    assert unassigned_id not in listed  # the unassigned one does not leak


async def test_unapproved_story_not_in_library(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A published-status but unapproved story is excluded from the list."""
    bad_id = await _add_unapproved_published_story(sessions, seed)
    resp = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200
    listed = {item["id"] for item in resp.json()["stories"]}
    assert seed.storybook_id in listed  # the approved seed story shows
    assert bad_id not in listed  # the unapproved one does not


async def test_child_cannot_fetch_unapproved_version(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A child fetching an unapproved version blob gets 404 (existence hidden)."""
    bad_id = await _add_unapproved_published_story(sessions, seed)
    resp = await client.get(
        f"/api/v1/storybooks/{bad_id}/versions/1",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404


async def test_guardian_cannot_fetch_unapproved_version(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A guardian (parent) cannot read drafts in slice 1; only the admin can."""
    bad_id = await _add_unapproved_published_story(sessions, seed)
    resp = await client.get(
        f"/api/v1/storybooks/{bad_id}/versions/1",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 404


async def test_admin_can_fetch_unapproved_version(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """The global admin may fetch an unapproved version blob to review it."""
    bad_id = await _add_unapproved_published_story(sessions, seed)
    resp = await client.get(
        f"/api/v1/storybooks/{bad_id}/versions/1",
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == bad_id


async def test_child_can_fetch_approved_seed_version(
    client: AsyncClient, seed: Seed
) -> None:
    """The approved seed story's version is fetchable by a child (regression)."""
    resp = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200


async def test_child_cannot_fetch_unassigned_version(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A child fetching an approved+published but UNASSIGNED version gets 404 (Task 7).

    Pins the read-path assignment gate behaviorally: the story clears every other
    predicate (family, published, approved, current), so the 404 proves the
    missing storybook_assignment row, not another filter, is what withholds it.
    """
    unassigned_id = await _add_approved_unassigned_story(sessions, seed)
    resp = await client.get(
        f"/api/v1/storybooks/{unassigned_id}/versions/1",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404


async def test_guardian_can_fetch_unassigned_version(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A guardian fetching an approved+published unassigned version is unaffected.

    The assignment gate is child-only; a guardian reads any approved current
    version in their family regardless of per-profile assignment.
    """
    unassigned_id = await _add_approved_unassigned_story(sessions, seed)
    resp = await client.get(
        f"/api/v1/storybooks/{unassigned_id}/versions/1",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == unassigned_id
