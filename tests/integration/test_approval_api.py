"""Integration tests for the admin approval router."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import Family, Storybook, StorybookVersion, User
from tests.conftest import make_clean_moderation_report

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
            StorybookVersion(
                storybook_id=story_id,
                version=1,
                blob={"id": story_id},
                moderation_report=make_clean_moderation_report(),
            )
        )
        await session.commit()
        return story_id


async def _seed_draft(
    sessions: async_sessionmaker[AsyncSession],
    *,
    moderation_report: dict[str, object] | None = None,
) -> str:
    """Seed Family A (admin + guardian + child) and a draft single-version story.

    Args:
        sessions: The session factory fixture.
        moderation_report: The version's moderation_report; None (default)
            models a version never screened by moderation.
    """
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
            StorybookVersion(
                storybook_id=story_id,
                version=1,
                blob={"id": story_id},
                moderation_report=moderation_report,
            )
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
    """An admin submits a screened draft story for review -> 200, in_review."""
    story_id = await _seed_draft(
        sessions, moderation_report=make_clean_moderation_report()
    )
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/submit", headers=auth("admin-a")
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_review"


async def test_admin_submit_without_moderation_returns_400(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Submitting a draft never screened by moderation returns 400 (closes #57)."""
    story_id = await _seed_draft(sessions)
    resp = await client.post(
        f"/api/v1/storybooks/{story_id}/submit", headers=auth("admin-a")
    )
    assert resp.status_code == 400


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


def _flagged_report() -> dict[str, object]:
    """A moderation report with one soft-flag finding on node n1."""
    return {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n1",
                "verdict": "flag",
                "score": None,
                "message": "too scary",
            }
        ],
        "summary": {
            "count": 1,
            "hard_block": False,
            "soft_flag": True,
            "repaired": False,
            "reviewer_independent": True,
        },
    }


async def _seed_two_family_queue(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Family A: one flagged in_review + one draft. Family B: one clean in_review.

    Also seeds an admin in Family A (global authority) plus a guardian and child
    in each family for the 403 cases.
    """
    async with sessions() as session:
        fam_a = Family(name="A")
        fam_b = Family(name="B")
        session.add_all([fam_a, fam_b])
        await session.flush()
        session.add_all(
            [
                User(family_id=fam_a.id, role="admin", authn_subject="admin-a"),
                User(family_id=fam_a.id, role="guardian", authn_subject="guardian-a"),
                User(family_id=fam_a.id, role="child", authn_subject="child-a"),
                User(family_id=fam_b.id, role="guardian", authn_subject="guardian-b"),
            ]
        )
        # Family A: a flagged in_review story
        session.add(Storybook(id="flagged-a", family_id=fam_a.id, status="in_review"))
        session.add(
            StorybookVersion(
                storybook_id="flagged-a",
                version=1,
                blob={"title": "Scary A", "nodes": [{"id": "n1", "body": "Boo."}]},
                moderation_report=_flagged_report(),
            )
        )
        # Family A: a draft story (must NOT appear in the queue)
        session.add(Storybook(id="draft-a", family_id=fam_a.id, status="draft"))
        session.add(
            StorybookVersion(storybook_id="draft-a", version=1, blob={"id": "draft-a"})
        )
        # Family A: an in_review story that reached review WITHOUT screening
        # (moderation_report is None). It must appear in the queue but be pinned
        # unscreened so a route hardcoding screened=True cannot pass.
        session.add(
            Storybook(id="unscreened-a", family_id=fam_a.id, status="in_review")
        )
        session.add(
            StorybookVersion(
                storybook_id="unscreened-a",
                version=1,
                blob={"title": "Unscreened A", "nodes": []},
                moderation_report=None,
            )
        )
        # Family B: a clean in_review story (cross-family visibility for the admin)
        session.add(Storybook(id="clean-b", family_id=fam_b.id, status="in_review"))
        session.add(
            StorybookVersion(
                storybook_id="clean-b",
                version=1,
                blob={"title": "Clean B", "nodes": []},
                moderation_report=make_clean_moderation_report(),
            )
        )
        await session.commit()


async def test_admin_review_queue_lists_both_families(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The admin queue spans families and buckets flagged versus clean."""
    await _seed_two_family_queue(sessions)
    resp = await client.get("/api/v1/review-queue", headers=auth("admin-a"))
    assert resp.status_code == 200
    items = {item["storybook_id"]: item for item in resp.json()["items"]}
    # draft-a excluded; unscreened-a is in_review so it is queued.
    assert set(items) == {"flagged-a", "clean-b", "unscreened-a"}
    assert items["flagged-a"]["screened"] is True
    assert items["flagged-a"]["flagged_count"] == 1
    assert items["flagged-a"]["title"] == "Scary A"
    assert items["clean-b"]["screened"] is True
    assert items["clean-b"]["flagged_count"] == 0
    # An unscreened in_review item must be pinned screened=False with no summary
    # (guards against a route hardcoding screened=True).
    assert items["unscreened-a"]["screened"] is False
    assert items["unscreened-a"]["summary"] is None
    assert items["unscreened-a"]["flagged_count"] == 0


async def test_review_queue_excludes_needs_revision_and_published(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Only in_review stories are queued; needs_revision and published are not."""
    async with sessions() as session:
        fam = Family(name="A")
        session.add(fam)
        await session.flush()
        session.add(User(family_id=fam.id, role="admin", authn_subject="admin-a"))
        session.add(Storybook(id="nr", family_id=fam.id, status="needs_revision"))
        session.add(StorybookVersion(storybook_id="nr", version=1, blob={"id": "nr"}))
        session.add(
            Storybook(
                id="pub",
                family_id=fam.id,
                status="published",
                current_published_version=1,
            )
        )
        session.add(StorybookVersion(storybook_id="pub", version=1, blob={"id": "pub"}))
        await session.commit()
    resp = await client.get("/api/v1/review-queue", headers=auth("admin-a"))
    assert resp.status_code == 200
    assert resp.json()["items"] == []


async def test_child_cannot_read_review_queue(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A child token gets 403 on the review queue."""
    await _seed_two_family_queue(sessions)
    async with sessions() as session:
        fam = Family(name="C")
        session.add(fam)
        await session.flush()
        session.add(User(family_id=fam.id, role="child", authn_subject="child-c"))
        await session.commit()
    resp = await client.get("/api/v1/review-queue", headers=auth("child-c"))
    assert resp.status_code == 403


async def test_guardian_cannot_read_review_queue(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A guardian token gets 403; review is admin-only (ADR-005 amendment)."""
    await _seed_two_family_queue(sessions)
    resp = await client.get("/api/v1/review-queue", headers=auth("guardian-a"))
    assert resp.status_code == 403


def _corrupt_report() -> dict[str, object]:
    """A moderation report that fails validation at rest (stage outside 0..4)."""
    return {
        "findings": [
            {
                "stage": 99,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n1",
                "verdict": "flag",
                "score": None,
                "message": "corrupt",
            }
        ],
        "summary": None,
    }


async def test_review_queue_isolates_corrupt_report(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """One corrupt-at-rest report is dropped from the queue, not fatal to it.

    Seeds a healthy in_review story alongside one whose stored moderation_report
    is corrupt. The queue must return 200 with only the healthy story rather
    than 422-ing the whole response: the operator's only review surface must not
    be denied by a single bad row. Deletion-sensitive: without the per-row
    try/except in get_review_queue, the corrupt row raises and the request 422s.
    """
    async with sessions() as session:
        fam = Family(name="A")
        session.add(fam)
        await session.flush()
        session.add(User(family_id=fam.id, role="admin", authn_subject="admin-a"))
        session.add(Storybook(id="healthy", family_id=fam.id, status="in_review"))
        session.add(
            StorybookVersion(
                storybook_id="healthy",
                version=1,
                blob={"title": "Healthy", "nodes": []},
                moderation_report=make_clean_moderation_report(),
            )
        )
        session.add(Storybook(id="corrupt", family_id=fam.id, status="in_review"))
        session.add(
            StorybookVersion(
                storybook_id="corrupt",
                version=1,
                blob={"title": "Corrupt", "nodes": []},
                moderation_report=_corrupt_report(),
            )
        )
        await session.commit()
    resp = await client.get("/api/v1/review-queue", headers=auth("admin-a"))
    assert resp.status_code == 200
    ids = {item["storybook_id"] for item in resp.json()["items"]}
    assert ids == {"healthy"}


async def test_review_queue_drops_story_with_no_version(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """An in_review story with no version row is dropped, not fatal to the queue.

    Seeds a healthy in_review story alongside an in_review story that has no
    StorybookVersion rows (an integrity anomaly). The queue returns 200 with
    only the healthy story; the version-less one is logged and skipped.
    """
    async with sessions() as session:
        fam = Family(name="A")
        session.add(fam)
        await session.flush()
        session.add(User(family_id=fam.id, role="admin", authn_subject="admin-a"))
        session.add(Storybook(id="healthy", family_id=fam.id, status="in_review"))
        session.add(
            StorybookVersion(
                storybook_id="healthy",
                version=1,
                blob={"title": "Healthy", "nodes": []},
                moderation_report=make_clean_moderation_report(),
            )
        )
        # in_review but with no StorybookVersion rows at all.
        session.add(Storybook(id="orphan", family_id=fam.id, status="in_review"))
        await session.commit()
    resp = await client.get("/api/v1/review-queue", headers=auth("admin-a"))
    assert resp.status_code == 200
    ids = {item["storybook_id"] for item in resp.json()["items"]}
    assert ids == {"healthy"}


async def test_review_queue_all_unversioned_returns_empty(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """If every in_review story lacks a version row, the queue is empty, not 500.

    Exercises the empty-composite-IN short-circuit: with no version rows the key
    list is empty, so the handler returns [] rather than issuing a degenerate
    tuple_(...).in_([]) query.
    """
    async with sessions() as session:
        fam = Family(name="A")
        session.add(fam)
        await session.flush()
        session.add(User(family_id=fam.id, role="admin", authn_subject="admin-a"))
        session.add(Storybook(id="orphan", family_id=fam.id, status="in_review"))
        await session.commit()
    resp = await client.get("/api/v1/review-queue", headers=auth("admin-a"))
    assert resp.status_code == 200
    assert resp.json()["items"] == []
