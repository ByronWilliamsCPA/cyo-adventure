"""Integration tests for the guardian browse-and-assign books endpoint (Task 2.2).

GET /api/v1/guardian/books lists a guardian's own-family published, approved
books, each with a redacted content badge (screened + flagged_count) and the set
of child profiles it is assigned to. Guardian-only: a child or an admin is 403.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import Storybook, StorybookVersion

from .conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_guardian_lists_family_published_book(
    client: AsyncClient, seed: Seed
) -> None:
    """The owning guardian sees the seeded published book with its assignment.

    The seed story is Family A's, published, approved, current, and assigned to
    profile A, so it clears every visibility predicate. Its row must carry the
    storybook id, the assigned profile id, and a content badge.
    """
    resp = await client.get("/api/v1/guardian/books", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    books = resp.json()["books"]
    row = next(b for b in books if b["storybook_id"] == seed.storybook_id)
    assert row["version"] == seed.version
    assert str(seed.child_profile_id) in row["assigned_profile_ids"]
    # Badge keys are always present; the lantern fixture is unscreened here.
    assert "screened" in row
    assert row["flagged_count"] >= 0


async def test_child_cannot_list_guardian_books(
    client: AsyncClient, seed: Seed
) -> None:
    """A child token is 403 (guardian-only surface)."""
    resp = await client.get("/api/v1/guardian/books", headers=auth(seed.child_token))
    assert resp.status_code == 403, resp.text


async def test_admin_cannot_list_guardian_books(
    client: AsyncClient, seed: Seed
) -> None:
    """An admin token is 403: the browse-to-assign page is guardian-only.

    An admin is the cross-family safety reviewer, not a family assigner, and has
    no assign authority (assign_storybook rejects admins), so this actionless
    surface is closed to them, matching the guardian-only nav entry decision.
    """
    resp = await client.get("/api/v1/guardian/books", headers=auth(seed.admin_token))
    assert resp.status_code == 403, resp.text


async def test_cross_family_guardian_sees_only_own_books(
    client: AsyncClient, seed: Seed
) -> None:
    """Family B's guardian does not see Family A's published book.

    Family isolation is enforced by the WHERE family_id clause, not by
    information-hiding: guardian-b gets a 200 with a list that excludes Family
    A's seeded story.
    """
    resp = await client.get(
        "/api/v1/guardian/books", headers=auth(seed.other_guardian_token)
    )
    assert resp.status_code == 200, resp.text
    ids = {b["storybook_id"] for b in resp.json()["books"]}
    assert seed.storybook_id not in ids


async def test_unpublished_book_is_excluded(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A draft (non-published) family book never appears in the browse list."""
    async with sessions() as session:
        session.add(
            Storybook(id="draft-books", family_id=seed.family_id, status="draft")
        )
        await session.commit()
    resp = await client.get("/api/v1/guardian/books", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    ids = {b["storybook_id"] for b in resp.json()["books"]}
    assert "draft-books" not in ids


async def test_unapproved_published_book_is_excluded(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A published book whose current version lacks approved_by is excluded.

    Matches library.py's approved_by IS NOT NULL gate exactly: a status of
    published without a recorded approver must not surface.
    """
    async with sessions() as session:
        session.add(
            Storybook(
                id="unapproved-books",
                family_id=seed.family_id,
                status="published",
                current_published_version=1,
            )
        )
        session.add(
            StorybookVersion(
                storybook_id="unapproved-books",
                version=1,
                blob={"id": "unapproved-books", "title": "No Approver"},
                approved_by=None,
            )
        )
        await session.commit()
    resp = await client.get("/api/v1/guardian/books", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    ids = {b["storybook_id"] for b in resp.json()["books"]}
    assert "unapproved-books" not in ids


async def test_flagged_book_reports_its_badge(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A screened, flagged published book reports screened=True and a count."""
    async with sessions() as session:
        session.add(
            Storybook(
                id="flagged-books",
                family_id=seed.family_id,
                status="published",
                current_published_version=1,
            )
        )
        session.add(
            StorybookVersion(
                storybook_id="flagged-books",
                version=1,
                blob={
                    "id": "flagged-books",
                    "title": "Flagged Tale",
                    "nodes": [{"id": "n1", "body": "Prose."}],
                    "metadata": {"age_band": "8-11"},
                },
                approved_by=seed.admin_user_id,
                moderation_report={
                    "findings": [
                        {
                            "stage": 1,
                            "source": "llm_safety",
                            "category": "violence",
                            "node_id": "n1",
                            "verdict": "flag",
                            "score": None,
                            "message": "mild peril",
                        }
                    ],
                    "summary": {
                        "count": 1,
                        "hard_block": False,
                        "soft_flag": True,
                        "repaired": False,
                        "reviewer_independent": True,
                    },
                },
            )
        )
        await session.commit()
    resp = await client.get("/api/v1/guardian/books", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    row = next(b for b in resp.json()["books"] if b["storybook_id"] == "flagged-books")
    assert row["screened"] is True
    assert row["flagged_count"] == 1
    assert row["age_band"] == "8-11"
    assert row["title"] == "Flagged Tale"
    assert row["assigned_profile_ids"] == []


async def test_corrupt_report_row_degrades_not_500(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A book with a corrupt moderation_report degrades its badge, not the list.

    build_content_summary raises on an unrecognized verdict at rest; the endpoint
    must isolate that row (screened True since a report exists, flagged_count 0)
    and still return the whole list at 200.
    """
    async with sessions() as session:
        session.add(
            Storybook(
                id="corrupt-books",
                family_id=seed.family_id,
                status="published",
                current_published_version=1,
            )
        )
        session.add(
            StorybookVersion(
                storybook_id="corrupt-books",
                version=1,
                blob={"id": "corrupt-books", "title": "Corrupt Tale"},
                approved_by=seed.admin_user_id,
                moderation_report={
                    "findings": [
                        {
                            "stage": 1,
                            "source": "llm_safety",
                            "category": "violence",
                            "node_id": "n1",
                            "verdict": "not-a-real-verdict",
                            "score": None,
                            "message": "corrupt",
                        }
                    ]
                },
            )
        )
        await session.commit()
    resp = await client.get("/api/v1/guardian/books", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    row = next(b for b in resp.json()["books"] if b["storybook_id"] == "corrupt-books")
    assert row["screened"] is True
    assert row["flagged_count"] == 0
