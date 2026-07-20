"""Erasure drill: deleting a child profile or a whole family removes every
child-/family-linked row it owns (GDPR Article 17 / COPPA 312.10, remediation
plan Phase 3e), and the guardian-facing data export (Phase 3c) returns a
complete, portable snapshot before that happens.

Populates every child-/family-linked table the Phase 3a cascade design
covers, then asserts the delete endpoints (Phase 3b) remove exactly what the
design says should disappear and nothing more, and that the one edge case
requiring explicit handling (a kid_flag resolved by an admin from a
DIFFERENT family) is reopened rather than left to violate a CHECK
constraint.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cyo_adventure.db.models import (
    ChildProfile,
    Completion,
    Concept,
    DeviceGrant,
    KidFlag,
    Rating,
    ReadingState,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
    StoryRequest,
    User,
)
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _populate_child_linked_rows(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """Add a reading state, completion, rating, and (already-seeded) assignment.

    ``seed`` already assigns ``seed.storybook_id``/``version`` to
    ``seed.child_profile_id``; this adds the three tables the fixture does
    not populate.
    """
    async with sessions() as s:
        s.add(
            ReadingState(
                child_profile_id=seed.child_profile_id,
                storybook_id=seed.storybook_id,
                version=seed.version,
                current_node="n_start",
            )
        )
        s.add(
            Completion(
                child_profile_id=seed.child_profile_id,
                storybook_id=seed.storybook_id,
                version=seed.version,
                ending_id="e_treasure_found",
            )
        )
        s.add(
            Rating(
                child_profile_id=seed.child_profile_id,
                storybook_id=seed.storybook_id,
                value=5,
            )
        )
        await s.commit()


async def _populate_family_owned_rows(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """Add a concept, a story request linking it, and a device grant."""
    async with sessions() as s:
        concept = Concept(
            family_id=seed.family_id,
            brief={"protagonist": {"name": "Explorer"}, "topic": "dragons"},
        )
        s.add(concept)
        await s.flush()
        s.add(
            StoryRequest(
                family_id=seed.family_id,
                profile_id=seed.child_profile_id,
                request_text="a story about dragons",
                status="approved",
                age_band="10-13",
                concept_id=concept.id,
            )
        )
        s.add(
            DeviceGrant(
                family_id=seed.family_id,
                authorized_by=seed.admin_user_id,
                jti=uuid.uuid4(),
                expires_at=datetime.now(UTC) + timedelta(days=90),
            )
        )
        await s.commit()


@pytest.mark.asyncio
async def test_delete_profile_removes_child_linked_rows(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """Deleting a child profile cascades reading state, completions, ratings,
    assignments, and the child's own login row; de-links (not deletes) their
    story requests.
    """
    await _populate_child_linked_rows(sessions, seed)
    async with sessions() as s:
        s.add(
            StoryRequest(
                family_id=seed.family_id,
                profile_id=seed.child_profile_id,
                request_text="a story about dragons",
                status="approved",
                age_band="10-13",
            )
        )
        await s.commit()

    resp = await client.delete(
        f"/api/v1/profiles/{seed.child_profile_id}",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 204, resp.text

    async with sessions() as s:
        assert (await s.get(ChildProfile, seed.child_profile_id)) is None
        assert (
            await s.scalar(
                select(ReadingState).where(
                    ReadingState.child_profile_id == seed.child_profile_id
                )
            )
        ) is None
        assert (
            await s.scalar(
                select(Completion).where(
                    Completion.child_profile_id == seed.child_profile_id
                )
            )
        ) is None
        assert (
            await s.scalar(
                select(Rating).where(Rating.child_profile_id == seed.child_profile_id)
            )
        ) is None
        assert (
            await s.scalar(
                select(StorybookAssignment).where(
                    StorybookAssignment.child_profile_id == seed.child_profile_id
                )
            )
        ) is None
        # The child's own login row (child-a) is gone too.
        assert (
            await s.scalar(
                select(User).where(User.child_profile_id == seed.child_profile_id)
            )
        ) is None
        # The story request survives, de-linked rather than deleted: it is
        # family-owned content, not exclusively the child's.
        request = await s.scalar(
            select(StoryRequest).where(StoryRequest.family_id == seed.family_id)
        )
        assert request is not None
        assert request.profile_id is None


async def test_delete_profile_rejects_cross_family_profile(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian cannot delete another family's profile (403)."""
    resp = await client.delete(
        f"/api/v1/profiles/{seed.other_child_profile_id}",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 403, resp.text


async def test_delete_profile_requires_guardian_role(
    client: AsyncClient, seed: Seed
) -> None:
    """A child token cannot delete a profile, including its own (403)."""
    resp = await client.delete(
        f"/api/v1/profiles/{seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403, resp.text


async def test_delete_my_family_removes_everything(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """Deleting a family cascades every family- and child-owned row.

    Populates reading state, a completion, a rating, a concept, a story
    request, and a device grant on top of the fixture's own
    family/users/profile/storybook/version/assignment, then asserts nothing
    is left after the delete.
    """
    await _populate_child_linked_rows(sessions, seed)
    await _populate_family_owned_rows(sessions, seed)

    resp = await client.delete("/api/v1/me/family", headers=auth(seed.guardian_token))
    assert resp.status_code == 204, resp.text

    async with sessions() as s:
        assert (await s.get(ChildProfile, seed.child_profile_id)) is None
        assert (
            await s.scalar(select(User).where(User.family_id == seed.family_id))
        ) is None
        assert (await s.get(Storybook, seed.storybook_id)) is None
        assert (
            await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        ) is None
        assert (
            await s.scalar(
                select(ReadingState).where(
                    ReadingState.child_profile_id == seed.child_profile_id
                )
            )
        ) is None
        assert (
            await s.scalar(
                select(Completion).where(
                    Completion.child_profile_id == seed.child_profile_id
                )
            )
        ) is None
        assert (
            await s.scalar(
                select(Rating).where(Rating.child_profile_id == seed.child_profile_id)
            )
        ) is None
        assert (
            await s.scalar(select(Concept).where(Concept.family_id == seed.family_id))
        ) is None
        assert (
            await s.scalar(
                select(StoryRequest).where(StoryRequest.family_id == seed.family_id)
            )
        ) is None
        assert (
            await s.scalar(
                select(DeviceGrant).where(DeviceGrant.family_id == seed.family_id)
            )
        ) is None


async def test_delete_my_family_rejects_non_guardian(
    client: AsyncClient, seed: Seed
) -> None:
    """An admin-only (non-guardian) principal has no family of its own to delete."""
    resp = await client.delete("/api/v1/me/family", headers=auth(seed.admin_token))
    assert resp.status_code == 403, resp.text


async def test_delete_my_family_reopens_kid_flags_resolved_by_its_admins(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A kid_flag on ANOTHER family's book, resolved by this family's admin,
    is reopened (not left dangling) rather than blocking the delete.

    This is the one edge case Phase 3a's cascade design cannot express
    directly: ck_kid_flag_resolved_pairing requires resolved_by/resolved_at
    to go null together, so the delete endpoint must explicitly clear both
    (plus resolution) before the cascade runs.

    The flag's storybook is deliberately a FRESH family-B book, not the
    shared fixture book (which belongs to family A, the family under
    deletion): if the flag pointed at a family-A book, its own composite FK
    to storybook_version would cascade it away, which would silently pass
    the "does the flag still exist" assertion below for the wrong reason.
    """
    other_storybook_id = "other-family-book"
    async with sessions() as s:
        other_profile = await s.get(ChildProfile, seed.other_child_profile_id)
        assert other_profile is not None
        other_family_id = other_profile.family_id
        s.add(
            Storybook(
                id=other_storybook_id,
                family_id=other_family_id,
                current_published_version=1,
                status="published",
            )
        )
        s.add(
            StorybookVersion(
                storybook_id=other_storybook_id,
                version=1,
                blob={"id": other_storybook_id, "title": "Other Family's Book"},
            )
        )
        await s.flush()
        flag = KidFlag(
            family_id=other_family_id,
            profile_id=seed.other_child_profile_id,
            storybook_id=other_storybook_id,
            version=1,
            reason="scared_me",
            resolved_by=seed.admin_user_id,
            resolved_at=datetime.now(UTC),
            resolution="dismissed",
        )
        s.add(flag)
        await s.commit()
        flag_id = flag.id

    resp = await client.delete("/api/v1/me/family", headers=auth(seed.guardian_token))
    assert resp.status_code == 204, resp.text

    async with sessions() as s:
        reopened = await s.get(KidFlag, flag_id)
        assert reopened is not None, "the flag itself must survive family A's delete"
        assert reopened.resolved_by is None
        assert reopened.resolved_at is None
        assert reopened.resolution is None


async def test_export_my_family_returns_full_data(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """The export includes the family, guardians, profiles (with nested
    reading data), and story requests.
    """
    await _populate_child_linked_rows(sessions, seed)
    await _populate_family_owned_rows(sessions, seed)

    resp = await client.get("/api/v1/me/export", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["family"]["id"] == str(seed.family_id)
    guardian_ids = {g["id"] for g in body["guardians"]}
    assert str(seed.admin_user_id) in guardian_ids

    profile = next(p for p in body["profiles"] if p["id"] == str(seed.child_profile_id))
    assert any(
        rs["storybook_id"] == seed.storybook_id for rs in profile["reading_state"]
    )
    assert any(c["ending_id"] == "e_treasure_found" for c in profile["completions"])
    assert any(r["storybook_id"] == seed.storybook_id for r in profile["ratings"])
    assert any(a["storybook_id"] == seed.storybook_id for a in profile["assignments"])
    assert any(
        req["request_text"] == "a story about dragons" for req in body["story_requests"]
    )


async def test_export_my_family_rejects_non_guardian(
    client: AsyncClient, seed: Seed
) -> None:
    """An admin-only (non-guardian) principal cannot export via this route."""
    resp = await client.get("/api/v1/me/export", headers=auth(seed.admin_token))
    assert resp.status_code == 403, resp.text


async def test_export_excludes_blocked_request_text(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A blocked story request's raw text is never exported, mirroring the
    guardian-facing API's own redaction.
    """
    async with sessions() as s:
        s.add(
            StoryRequest(
                family_id=seed.family_id,
                profile_id=seed.child_profile_id,
                request_text="raw text that tripped the bright-line guard",
                status="blocked",
                age_band="10-13",
            )
        )
        await s.commit()

    resp = await client.get("/api/v1/me/export", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    blocked = next(
        req for req in resp.json()["story_requests"] if req["status"] == "blocked"
    )
    assert blocked["request_text"] is None
