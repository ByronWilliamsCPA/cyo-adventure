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

# A version that has been screened clean, for fixtures that need approve() to
# succeed. approve() now refuses to publish a version with moderation_report
# is None (C3-SAFETY Findings 1-2); tests exercising the illegal-transition,
# authorization, or not-found paths never reach that check, so they do not
# need this.
_CLEAN_REPORT: dict[str, object] = {
    "findings": [],
    "summary": {
        "count": 0,
        "hard_block": False,
        "soft_flag": False,
        "repaired": False,
        "reviewer_independent": True,
    },
}


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
            StorybookVersion(
                storybook_id=story_id,
                version=1,
                blob={"id": story_id},
                moderation_report=_CLEAN_REPORT,
            )
        )
        await session.commit()
        return story_id


async def _seed_draft(
    sessions: async_sessionmaker[AsyncSession],
) -> str:
    """Seed Family A (admin + guardian + child) and a draft single-version story."""
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
        story_id = "draft-me"
        session.add(Storybook(id=story_id, family_id=fam.id, status="draft"))
        session.add(
            StorybookVersion(storybook_id=story_id, version=1, blob={"id": story_id})
        )
        await session.commit()
        return story_id


async def _seed_published(
    sessions: async_sessionmaker[AsyncSession],
) -> str:
    """Seed Family A (admin + guardian + child) and a published single-version story."""
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
        story_id = "pub-me"
        session.add(
            Storybook(
                id=story_id,
                family_id=fam.id,
                status="published",
                current_published_version=1,
            )
        )
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


async def test_approve_unscreened_story_returns_400(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Approving an in-review story with no moderation_report returns 400.

    Closes C3-SAFETY Findings 1-2: a story that reached in_review without
    ever being screened (the import path, or a direct admin submit) must not
    be publishable via this endpoint.
    """
    async with sessions() as session:
        fam = Family(name="A")
        session.add(fam)
        await session.flush()
        session.add(User(family_id=fam.id, role="admin", authn_subject="admin-a"))
        story_id = "unscreened-me"
        session.add(Storybook(id=story_id, family_id=fam.id, status="in_review"))
        session.add(
            StorybookVersion(storybook_id=story_id, version=1, blob={"id": story_id})
        )
        await session.commit()
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/approve", headers=auth("admin-a")
    )
    assert resp.status_code == 400
    async with sessions() as session:
        book = await session.get(Storybook, story_id)
        assert book is not None
        assert book.status == "in_review"


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


async def test_non_admin_on_missing_story_returns_403_not_404(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A non-admin acting on an unknown id gets 403, not 404.

    The role check must precede the DB load so a non-admin can never probe
    whether a storybook exists (existence is not disclosed).
    """
    await _seed_in_review(sessions)
    resp = await client.post(
        "/api/v1/storybooks/does-not-exist/approve", headers=auth("child-a")
    )
    assert resp.status_code == 403


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


async def test_admin_submits_draft_story(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """An admin submits a draft story for review -> 200, in_review."""
    story_id = await _seed_draft(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/submit", headers=auth("admin-a")
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_review"


async def test_admin_archives_published_story(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """An admin archives a published story -> 200, archived."""
    story_id = await _seed_published(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/archive", headers=auth("admin-a")
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


async def test_child_cannot_submit(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A child token gets 403 on submit."""
    story_id = await _seed_in_review(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/submit", headers=auth("child-a")
    )
    assert resp.status_code == 403


async def test_guardian_cannot_submit(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A guardian token gets 403 on submit."""
    story_id = await _seed_in_review(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/submit", headers=auth("guardian-a")
    )
    assert resp.status_code == 403


async def test_child_cannot_send_back(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A child token gets 403 on send-back."""
    story_id = await _seed_in_review(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/send-back",
        headers=auth("child-a"),
        json={"reason": "x"},
    )
    assert resp.status_code == 403


async def test_guardian_cannot_send_back(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A guardian token gets 403 on send-back."""
    story_id = await _seed_in_review(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/send-back",
        headers=auth("guardian-a"),
        json={"reason": "x"},
    )
    assert resp.status_code == 403


async def test_child_cannot_archive(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A child token gets 403 on archive."""
    story_id = await _seed_in_review(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/archive", headers=auth("child-a")
    )
    assert resp.status_code == 403


async def test_guardian_cannot_archive(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A guardian token gets 403 on archive."""
    story_id = await _seed_in_review(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/archive", headers=auth("guardian-a")
    )
    assert resp.status_code == 403


async def test_archive_non_published_returns_409(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Archiving a draft story (illegal transition) returns 409."""
    story_id = await _seed_draft(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/archive", headers=auth("admin-a")
    )
    assert resp.status_code == 409


async def test_no_publish_without_approver(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The only way to reach published stamps approved_by; the row proves it."""
    story_id = await _seed_in_review(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/approve", headers=auth("admin-a")
    )
    assert resp.status_code == 200
    async with sessions() as session:
        book = await session.get(Storybook, story_id)
        assert book is not None
        assert book.status == "published"
        assert book.current_published_version is not None
        version_row = await session.get(
            StorybookVersion, (story_id, book.current_published_version)
        )
        assert version_row is not None
        assert (
            version_row.approved_by is not None
        )  # invariant: never published w/o approver
        assert version_row.published_at is not None
