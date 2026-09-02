"""Integration tests for `RS-C2`/`RS-C3`: decisions the review queue never shows.

What only a live database can settle here is the QUERY, and specifically its
version resolution. Two claims are asserted against real SQL because no unit
test can reach them:

- The correlated latest-version subquery and the published/latest CASE resolve
  the version a decision is actually about. A bare
  ``coalesce(current_published_version, latest)`` passes every reasonable unit
  test and is still wrong, because `RS-C1`'s recall deliberately leaves
  ``current_published_version`` set on a book it moves off the shelf.
- One corrupt-at-rest report isolates its own book instead of 422-ing the whole
  listing, which is the same posture ``get_review_queue`` takes and matters more
  here: this surface is the ONLY place these decisions appear.

These tests seed their own families and books rather than using the ``seed``
fixture, because the point of every case is a status/version/report combination
the shared fixture does not have.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from cyo_adventure.db.models import (
    Family,
    Storybook,
    StorybookVersion,
    User,
)
from tests.conftest import make_clean_moderation_report

from .conftest import auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_URL = "/api/v1/admin/outstanding-decisions"


def _blob(title: str) -> dict[str, object]:
    """A minimal blob carrying the title and age band the surface projects."""
    return {"title": title, "metadata": {"age_band": "6-8"}, "nodes": []}


def _block_report() -> dict[str, object]:
    """A report whose verdict is a hard block on one node."""
    return {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "node_id": "n1",
                "verdict": "block",
                "score": None,
                "message": "graphic peril",
            }
        ],
        "summary": {
            "count": 1,
            "hard_block": True,
            "soft_flag": False,
            "repaired": False,
            "reviewer_independent": True,
        },
    }


def _corrupt_report() -> dict[str, object]:
    """A report that fails validation at rest (stage outside 0..4).

    The same shape ``test_approval_api.py::test_review_queue_isolates_corrupt_report``
    uses, deliberately: one corruption fixture for both admin listings means a
    change to what "corrupt" means cannot fix one surface and miss the other.
    """
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


async def _seed_admin_family(session: AsyncSession) -> Family:
    """Create a family with an admin user whose token is ``admin-a``."""
    fam = Family(name="A")
    session.add(fam)
    await session.flush()
    session.add(
        User(family_id=fam.id, role="admin", authn_subject="admin-a", is_admin=True)
    )
    return fam


def _add_book(
    session: AsyncSession,
    fam: Family,
    *,
    storybook_id: str,
    status: str,
    current_published_version: int | None,
    versions: list[dict[str, object]],
) -> None:
    """Add one storybook plus its version rows.

    Args:
        session: The open session.
        fam: The owning family.
        storybook_id: The story id.
        status: The lifecycle status to persist.
        current_published_version: The column value, set independently of
            ``status`` on purpose: the combinations these tests care about
            (a recalled book that still carries one, a published book whose
            latest version is newer than it) are exactly the ones a helper that
            derived it would refuse to build.
        versions: Per-version kwargs (``version``, ``moderation_report``,
            ``cover_status``).
    """
    session.add(
        Storybook(
            id=storybook_id,
            family_id=fam.id,
            status=status,
            current_published_version=current_published_version,
        )
    )
    for spec in versions:
        version = spec["version"]
        session.add(
            StorybookVersion(
                storybook_id=storybook_id,
                version=version,
                blob=_blob(f"{storybook_id} v{version}"),
                moderation_report=spec.get("moderation_report"),
                cover_status=spec.get("cover_status", "none"),
            )
        )


async def _get_items(client: AsyncClient, token: str = "admin-a") -> list[Any]:
    """GET the surface as an admin and return its items, asserting a 200."""
    resp = await client.get(_URL, headers=auth(token))
    assert resp.status_code == 200, resp.text
    items: list[Any] = resp.json()["items"]
    return items


async def test_outstanding_decisions_requires_admin(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A guardian gets 403, so no adult learns which books carry a live block."""
    async with sessions() as session:
        fam = await _seed_admin_family(session)
        session.add(User(family_id=fam.id, role="guardian", authn_subject="guardian-a"))
        _add_book(
            session,
            fam,
            storybook_id="blocked",
            status="published",
            current_published_version=1,
            versions=[{"version": 1, "moderation_report": _block_report()}],
        )
        await session.commit()

    resp = await client.get(_URL, headers=auth("guardian-a"))
    assert resp.status_code == 403


async def test_a_block_on_a_published_book_is_listed_and_recallable(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The case the surface exists for: a live book the review queue omits.

    A published book carrying a block appears in NO other admin list: the review
    queue is ``in_review`` only. Under ADR-005 that makes it invisible to the
    final gate, which is a safety defect rather than a missing convenience.
    """
    async with sessions() as session:
        fam = await _seed_admin_family(session)
        _add_book(
            session,
            fam,
            storybook_id="blocked",
            status="published",
            current_published_version=1,
            versions=[{"version": 1, "moderation_report": _block_report()}],
        )
        await session.commit()

    items = await _get_items(client)
    assert [(i["storybook_id"], i["kind"]) for i in items] == [
        ("blocked", "moderation")
    ]
    item = items[0]
    assert item["moderation"]["block_findings"] == 1
    assert item["moderation"]["report_unusable"] is False
    # The headline finding is what makes the row actionable without opening the
    # book, and recallable is what makes the action available.
    assert item["moderation"]["top_finding"] is not None
    assert item["recallable"] is True
    assert item["title"] == "blocked v1"
    assert item["age_band"] == "6-8"
    # Cross-check the premise: this book is genuinely absent from the queue, so
    # the surface is showing something no existing list showed.
    queue = await client.get("/api/v1/review-queue", headers=auth("admin-a"))
    assert queue.status_code == 200
    assert queue.json()["items"] == []


async def test_a_clean_published_book_is_absent(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A published book with a clean, usable report produces no row.

    The query admits every published book (filtering on a JSONB verdict in SQL
    would be a second routing implementation that could drift from the detail
    view), so this is the assertion that the list stays short in practice.
    """
    async with sessions() as session:
        fam = await _seed_admin_family(session)
        _add_book(
            session,
            fam,
            storybook_id="clean",
            status="published",
            current_published_version=1,
            versions=[
                {"version": 1, "moderation_report": make_clean_moderation_report()}
            ],
        )
        await session.commit()

    assert await _get_items(client) == []


async def test_a_recalled_book_reports_its_latest_version_not_the_published_one(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The version-resolution claim, asserted on both sides of a recall.

    Cited by ``approval.py::get_outstanding_decisions``. The book has two
    versions and ``current_published_version = 1``:

    - While PUBLISHED, the decision is about version 1, because api/library.py
      serves ``current_published_version`` and a verdict read off version 2
      would describe content no child can reach.
    - Once RECALLED, the decision is about version 2, because `RS-C1`
      deliberately leaves ``current_published_version`` set. A bare
      ``coalesce(current_published_version, latest)`` would keep naming version 1
      forever, which is why the CASE tests the status as well.

    Both halves are in one test because the contrast IS the invariant; asserting
    only the recalled state would pass against a query that always used latest.
    """
    async with sessions() as session:
        fam = await _seed_admin_family(session)
        _add_book(
            session,
            fam,
            storybook_id="two_versions",
            status="published",
            current_published_version=1,
            versions=[
                {
                    "version": 1,
                    "moderation_report": _block_report(),
                    "cover_status": "pending_review",
                },
                {
                    "version": 2,
                    "moderation_report": make_clean_moderation_report(),
                    "cover_status": "pending_review",
                },
            ],
        )
        await session.commit()

    published = await _get_items(client)
    assert {i["version"] for i in published} == {1}
    kinds = {i["kind"]: i for i in published}
    assert kinds["moderation"]["moderation"]["block_findings"] == 1
    # The pending cover on version 1 IS the art a child sees today, so it is
    # child-facing; version 2's identical pending cover is not.
    assert kinds["cover"]["cover"]["child_facing"] is True

    recall = await client.post(
        "/api/v1/storybooks/two_versions/recall",
        headers=auth("admin-a"),
        json={"reason_code": "threshold_change"},
    )
    assert recall.status_code == 200, recall.text

    recalled = await _get_items(client)
    # The recalled book is in_review, so its verdict now has a home in the
    # review queue and this surface contributes no moderation row; the cover
    # decision is still unmade and still listed.
    assert [(i["kind"], i["version"]) for i in recalled] == [("cover", 2)]
    assert recalled[0]["cover"]["child_facing"] is False
    # And the recall did not clear the column, which is what makes the CASE's
    # status test load-bearing rather than defensive.
    async with sessions() as session:
        book = await session.get(Storybook, "two_versions")
        assert book is not None
        assert book.current_published_version == 1


async def test_a_pending_cover_is_listed_at_every_status(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A cover awaiting review is an unmade decision whatever the book's status.

    Production has exactly this spread (two published books and one archived
    book parked at ``pending_review``), and only the published ones show a child
    a coverless card. The archived one is still a decision nobody made, so it is
    listed and ranked last rather than hidden.
    """
    async with sessions() as session:
        fam = await _seed_admin_family(session)
        _add_book(
            session,
            fam,
            storybook_id="pub_cover",
            status="published",
            current_published_version=1,
            versions=[
                {
                    "version": 1,
                    "moderation_report": make_clean_moderation_report(),
                    "cover_status": "pending_review",
                }
            ],
        )
        _add_book(
            session,
            fam,
            storybook_id="arch_cover",
            status="archived",
            current_published_version=1,
            versions=[
                {
                    "version": 1,
                    "moderation_report": make_clean_moderation_report(),
                    "cover_status": "pending_review",
                }
            ],
        )
        _add_book(
            session,
            fam,
            storybook_id="draft_no_cover",
            status="draft",
            current_published_version=None,
            versions=[{"version": 1, "cover_status": "none"}],
        )
        await session.commit()

    items = await _get_items(client)
    assert [(i["storybook_id"], i["cover"]["child_facing"]) for i in items] == [
        ("pub_cover", True),
        ("arch_cover", False),
    ]
    # An archived book cannot be recalled (archive is absorbing), and the flag
    # is derived from the transition table rather than from the status name.
    by_id = {i["storybook_id"]: i for i in items}
    assert by_id["arch_cover"]["recallable"] is False
    assert by_id["pub_cover"]["recallable"] is True


async def test_a_corrupt_report_isolates_only_its_own_book(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """One unparseable report drops its own book, not the listing.

    Deletion-sensitive: without the per-row try/except the corrupt row raises
    and the whole request 422s, which would hide every OTHER book's unresolved
    decision. That is strictly worse here than in the review queue, because
    this surface is the only place those decisions appear at all.
    """
    async with sessions() as session:
        fam = await _seed_admin_family(session)
        _add_book(
            session,
            fam,
            storybook_id="healthy",
            status="published",
            current_published_version=1,
            versions=[{"version": 1, "moderation_report": _block_report()}],
        )
        _add_book(
            session,
            fam,
            storybook_id="corrupt",
            status="published",
            current_published_version=1,
            versions=[{"version": 1, "moderation_report": _corrupt_report()}],
        )
        await session.commit()

    items = await _get_items(client)
    assert {i["storybook_id"] for i in items} == {"healthy"}


async def test_a_corrupt_report_still_surfaces_that_books_pending_cover(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A corrupt report drops that book's moderation row only, not its cover row.

    The cover decision derives entirely from ``cover_status`` and
    ``current_published_version``; nothing about it reads the moderation
    report. Isolating the corruption any wider than the moderation projection
    would silently retire a real pending cover decision on the same book, and
    the only symptom would be a row that never appears.
    """
    async with sessions() as session:
        fam = await _seed_admin_family(session)
        _add_book(
            session,
            fam,
            storybook_id="corrupt_with_cover",
            status="published",
            current_published_version=1,
            versions=[
                {
                    "version": 1,
                    "moderation_report": _corrupt_report(),
                    "cover_status": "pending_review",
                }
            ],
        )
        await session.commit()

    items = await _get_items(client)
    assert [(i["storybook_id"], i["kind"]) for i in items] == [
        ("corrupt_with_cover", "cover")
    ]
    assert items[0]["cover"]["child_facing"] is True


async def test_a_book_with_no_moderation_report_is_an_outstanding_decision(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A published book whose safety was never recorded is listed, not assumed clean.

    ``moderation_report_unusable(None)`` is True, and treating a missing report
    as a pass would be the single most dangerous default this surface could
    take: publishing/service.py::approve refuses a NULL report, so a published
    book carrying one means something bypassed the gate.
    """
    async with sessions() as session:
        fam = await _seed_admin_family(session)
        _add_book(
            session,
            fam,
            storybook_id="no_report",
            status="published",
            current_published_version=1,
            versions=[{"version": 1}],
        )
        await session.commit()

    items = await _get_items(client)
    assert [(i["storybook_id"], i["kind"]) for i in items] == [
        ("no_report", "moderation")
    ]
    assert items[0]["moderation"]["report_unusable"] is True
