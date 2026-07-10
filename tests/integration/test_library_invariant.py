"""The no-unapproved-publish invariant across both library read paths."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import (
    ChildProfile,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
)

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


async def test_guardian_library_excludes_unassigned_story(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A guardian listing a child's library also sees only assigned stories.

    Unlike the version-fetch gate (child-only), the ``list_library`` assignment
    EXISTS gate is bound to the requested ``profile_id``, not the caller's role,
    so it applies to a guardian too. This pins that contract: a future refactor
    that exempts guardians from the list gate would leak the unassigned story
    here and fail this test. The positive control (the assigned seed story shows)
    isolates the gate as the sole cause of the exclusion.
    """
    unassigned_id = await _add_approved_unassigned_story(sessions, seed)
    resp = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 200
    listed = {item["id"] for item in resp.json()["stories"]}
    assert seed.storybook_id in listed  # the assigned seed story shows
    assert unassigned_id not in listed  # unassigned excluded even for a guardian


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


# ---------------------------------------------------------------------------
# Child read paths honor catalog visibility (Task 13, post-final-review
# amendment): an assigned cross-family visibility='catalog' book must be fully
# readable through all three child surfaces (listing, direct blob fetch,
# rating); an unassigned one stays hidden through the same three surfaces; a
# cross-family visibility='family' book stays blocked exactly as before, even
# when an assignment row exists, isolating the family filter (not the
# assignment gate) as the cause of that denial.
# ---------------------------------------------------------------------------


async def _add_cross_family_catalog_book(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    story_id: str,
    *,
    assign: bool,
) -> str:
    """Insert an approved, published, visibility='catalog' book owned by Family B.

    Optionally assigns it to Family A's seeded child profile.
    """
    async with sessions() as session:
        profile_b = await session.get(ChildProfile, seed.other_child_profile_id)
        assert profile_b is not None
        session.add(
            Storybook(
                id=story_id,
                family_id=profile_b.family_id,
                current_published_version=1,
                status="published",
                visibility="catalog",
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
        if assign:
            session.add(
                StorybookAssignment(
                    child_profile_id=seed.child_profile_id,
                    storybook_id=story_id,
                )
            )
        await session.commit()
        return story_id


async def test_child_reads_assigned_cross_family_catalog_book(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """An assigned catalog book from another family clears all three child gates.

    The book is Family B's, so it fails a plain own-family filter; the
    assignment row is what makes it visible, matching the guardian-assign
    parity ratified for WS-E's catalog feature (E5 amendment).
    """
    story_id = await _add_cross_family_catalog_book(
        sessions, seed, "catalog-cross-family-assigned", assign=True
    )
    listing = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert listing.status_code == 200, listing.text
    assert story_id in {item["id"] for item in listing.json()["stories"]}
    blob = await client.get(
        f"/api/v1/storybooks/{story_id}/versions/1",
        headers=auth(seed.child_token),
    )
    assert blob.status_code == 200, blob.text
    rating = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": story_id,
            "value": 4,
        },
        headers=auth(seed.child_token),
    )
    assert rating.status_code == 200, rating.text


async def test_child_cannot_read_unassigned_cross_family_catalog_book(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """An unassigned catalog book from another family stays hidden on all three gates.

    Widening the family filter must not widen the assignment gate: the
    StorybookAssignment EXISTS clause (listing) and the child assignment check
    (blob fetch, ratings.py) remain the required gate for catalog books too.
    """
    story_id = await _add_cross_family_catalog_book(
        sessions, seed, "catalog-cross-family-unassigned", assign=False
    )
    listing = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert listing.status_code == 200, listing.text
    assert story_id not in {item["id"] for item in listing.json()["stories"]}
    blob = await client.get(
        f"/api/v1/storybooks/{story_id}/versions/1",
        headers=auth(seed.child_token),
    )
    assert blob.status_code == 404, blob.text
    rating = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": story_id,
            "value": 4,
        },
        headers=auth(seed.child_token),
    )
    assert rating.status_code == 403, rating.text


async def test_child_cannot_read_cross_family_private_book(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A cross-family visibility='family' book stays blocked (regression guard).

    An assignment row is added despite the book being private, so the denial on
    every surface is attributable to the family filter alone, not a missing
    assignment; the widened catalog gate must not accidentally widen the
    family-visibility case too.
    """
    story_id = "private-cross-family"
    async with sessions() as session:
        profile_b = await session.get(ChildProfile, seed.other_child_profile_id)
        assert profile_b is not None
        session.add(
            Storybook(
                id=story_id,
                family_id=profile_b.family_id,
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
        session.add(
            StorybookAssignment(
                child_profile_id=seed.child_profile_id,
                storybook_id=story_id,
            )
        )
        await session.commit()
    listing = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert listing.status_code == 200, listing.text
    assert story_id not in {item["id"] for item in listing.json()["stories"]}
    blob = await client.get(
        f"/api/v1/storybooks/{story_id}/versions/1",
        headers=auth(seed.child_token),
    )
    assert blob.status_code == 403, blob.text
    rating = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": story_id,
            "value": 4,
        },
        headers=auth(seed.child_token),
    )
    assert rating.status_code == 403, rating.text


async def test_guardian_reads_catalog_blob_but_not_private_cross_family(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """Guardian parity for the visibility branch in ``get_storybook_version``.

    The child-perspective tests above pin the catalog widening through the
    assignment-gated child surfaces; this pins the other arm asserted only in a
    comment on ``get_storybook_version`` (``api/library.py``): a guardian of
    Family A may fetch a published, approved, ``visibility='catalog'`` book
    owned by Family B with no assignment row at all (the assignment gate is
    child-only), while a Family B book left at the default ``visibility='family'``
    still 403s for the same guardian, exactly as the plain family-ownership rule
    always required.
    """
    catalog_id = await _add_cross_family_catalog_book(
        sessions, seed, "catalog-cross-family-guardian", assign=False
    )
    catalog_blob = await client.get(
        f"/api/v1/storybooks/{catalog_id}/versions/1",
        headers=auth(seed.guardian_token),
    )
    assert catalog_blob.status_code == 200, catalog_blob.text

    private_id = "private-cross-family-guardian"
    async with sessions() as session:
        profile_b = await session.get(ChildProfile, seed.other_child_profile_id)
        assert profile_b is not None
        session.add(
            Storybook(
                id=private_id,
                family_id=profile_b.family_id,
                current_published_version=1,
                status="published",
            )
        )
        session.add(
            StorybookVersion(
                storybook_id=private_id,
                version=1,
                blob={"id": private_id},
                approved_by=seed.admin_user_id,
            )
        )
        await session.commit()
    private_blob = await client.get(
        f"/api/v1/storybooks/{private_id}/versions/1",
        headers=auth(seed.guardian_token),
    )
    assert private_blob.status_code == 403, private_blob.text
