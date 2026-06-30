"""Integration tests for the admin approval router."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import Family, Storybook, StorybookVersion, User

from .conftest import auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _seed_in_review(
    sessions: async_sessionmaker[AsyncSession],
) -> str:
    """Seed Family A (admin + guardian + child) and an in-review single-version story."""
    async with sessions() as session:
        fam = Family(name="A")
        session.add(fam)
        await session.flush()
        session.add_all(
            [
                User(family_id=fam.id, role="admin", authn_subject="admin-a"),
                User(family_id=fam.id, role="guardian", authn_subject="guardian-a"),
                User(family_id=fam.id, role="child", authn_subject="child-a"),
            ]
        )
        story_id = "review-me"
        session.add(Storybook(id=story_id, family_id=fam.id, status="in_review"))
        session.add(
            StorybookVersion(storybook_id=story_id, version=1, blob={"id": story_id})
        )
        await session.commit()
        return story_id


async def test_admin_approves_in_review_story(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """An admin approves an in-review story -> 200, published, stamped."""
    story_id = await _seed_in_review(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/approve", headers=auth("admin-a")
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "published"
    assert body["current_published_version"] == 1
    assert body["approved_by"] is not None


async def test_child_cannot_approve(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A child token gets 403 on approve."""
    story_id = await _seed_in_review(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/approve", headers=auth("child-a")
    )
    assert resp.status_code == 403


async def test_guardian_cannot_approve(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A guardian (parent) cannot approve in slice 1; approval is admin-only."""
    story_id = await _seed_in_review(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/approve", headers=auth("guardian-a")
    )
    assert resp.status_code == 403


async def test_admin_can_approve_across_families(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A global admin seeded in another family can still approve the story."""
    story_id = await _seed_in_review(sessions)
    async with sessions() as session:
        fam_b = Family(name="B")
        session.add(fam_b)
        await session.flush()
        session.add(User(family_id=fam_b.id, role="admin", authn_subject="admin-b"))
        await session.commit()
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/approve", headers=auth("admin-b")
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"


async def test_illegal_transition_returns_409(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Approving a story that is not in review returns 409."""
    story_id = await _seed_in_review(sessions)
    # Send it back first so it is in needs_revision, then approve illegally.
    await client.post(
        f"/api/v1/storybooks/{story_id}/send-back",
        headers=auth("admin-a"),
        json={"reason": "revise"},
    )
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/approve", headers=auth("admin-a")
    )
    assert resp.status_code == 409


async def test_missing_story_returns_404(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """An admin acting on an unknown storybook id returns 404."""
    await _seed_in_review(sessions)
    resp = await client.post(
        "/api/v1/storybooks/does-not-exist/approve", headers=auth("admin-a")
    )
    assert resp.status_code == 404


async def test_submit_and_send_back_flow(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """send-back echoes the reason and moves the story to needs_revision."""
    story_id = await _seed_in_review(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/send-back",
        headers=auth("admin-a"),
        json={"reason": "too scary for 6yo"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "needs_revision"
    assert body["reason"] == "too scary for 6yo"
