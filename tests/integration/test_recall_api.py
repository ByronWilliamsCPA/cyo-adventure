"""Integration tests for `RS-C1`: recalling a published book to the human gate.

Recall is the recoverable counterpart of archive, and the claims worth pinning
here are the ones a comment cannot prove:

- A recalled book actually leaves every child-facing surface. The state change
  is one column, and every read path is expected to gate on it independently;
  that is an assumption about five other modules, so it is asserted against
  live endpoints rather than reasoned about.
- The assignment row survives, so re-approval restores the shelf with nothing
  to reassign. This is the whole difference from archive, which is absorbing.
- ``current_published_version`` survives. Clearing it would look tidy and would
  break series anchoring and re-screening.
- A recalled book lands where a reviewer will find it (the admin review queue).
  A recall that hides the book from the queue would be a silent trap.

The ``seed`` fixture already provides exactly the starting state recall needs:
a published, admin-approved, assigned story in family A, plus admin, guardian,
dual-role and child tokens.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import sqlalchemy as sa

from cyo_adventure.db.models import (
    PipelineEvent,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
)
from tests.conftest import make_clean_moderation_report

from .conftest import auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from .conftest import Seed

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _recall(
    client: AsyncClient, seed: Seed, *, reason_code: str = "threshold_change"
) -> None:
    """Recall the seeded story as the admin, asserting the call succeeded."""
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/recall",
        headers=auth(seed.admin_token),
        json={"reason_code": reason_code},
    )
    assert resp.status_code == 200, resp.text


async def _status(
    sessions: async_sessionmaker[AsyncSession], storybook_id: str
) -> tuple[str, int | None]:
    """Return the storybook's (status, current_published_version) from the DB."""
    async with sessions() as session:
        row = await session.get(Storybook, storybook_id)
        assert row is not None
        return row.status, row.current_published_version


async def test_admin_recalls_a_published_book(client: AsyncClient, seed: Seed) -> None:
    """The happy path: 200, in_review, and the response echoes what happened."""
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/recall",
        headers=auth(seed.admin_token),
        json={"reason_code": "threshold_change"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == seed.storybook_id
    assert body["status"] == "in_review"
    assert body["reason_code"] == "threshold_change"


async def test_recall_leaves_current_published_version_set(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """The column survives, and the response says so.

    Cited by ``publishing/service.py::recall``. It is not an access grant (every
    read path ANDs it with the status), and three surfaces need it: series
    anchoring reads the published sibling, ``moderation/rescreen.py`` errors out
    on a published book without one, and the guardian device-download inventory
    resolves titles through it.
    """
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/recall",
        headers=auth(seed.admin_token),
        json={"reason_code": "curation"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["current_published_version"] == seed.version

    status, published_version = await _status(sessions, seed.storybook_id)
    assert status == "in_review"
    assert published_version == seed.version


async def test_a_recalled_book_leaves_every_child_facing_surface(
    client: AsyncClient, seed: Seed
) -> None:
    """The blast-radius claim, asserted against live endpoints.

    Each of these paths gates on ``status == "published"`` in a different
    module, so a single status flip is only sufficient if all of them really do.
    The before/after pairing matters: asserting only the "after" state would
    pass even if the child had never been able to reach the book at all.
    """
    shelf_before = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert shelf_before.status_code == 200, shelf_before.text
    assert seed.storybook_id in {s["id"] for s in shelf_before.json()["stories"]}

    read_before = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}",
        headers=auth(seed.child_token),
    )
    assert read_before.status_code == 200, read_before.text

    await _recall(client, seed)

    shelf_after = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert shelf_after.status_code == 200, shelf_after.text
    assert seed.storybook_id not in {s["id"] for s in shelf_after.json()["stories"]}

    read_after = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}",
        headers=auth(seed.child_token),
    )
    assert read_after.status_code == 404, read_after.text


async def test_a_recalled_book_cannot_be_newly_assigned(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian cannot put a recalled book on another child's shelf.

    ``api/assignments.py`` gates assignment creation on published status, so
    recall closes the door on new access as well as existing access. Without
    this, a guardian could re-add a book an admin had just pulled.
    """
    await _recall(client, seed)
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/assignments",
        headers=auth(seed.guardian_token),
        json={"profile_ids": [str(seed.child_profile_id)]},
    )
    assert resp.status_code >= 400, resp.text


async def test_recall_keeps_the_assignment_row_so_reapproval_restores_the_shelf(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """The recoverability claim, end to end: recall, re-approve, shelf is back.

    This is the entire reason recall exists rather than archive-and-regenerate.
    Asserted through the real approve endpoint, not by writing the status back,
    so the round trip is proven to work through the ordinary human gate.
    """
    # The seeded version carries no moderation report, and approve() refuses to
    # publish without a usable one. Stamp a clean report so the re-approval
    # exercises the ordinary path rather than the missing-report refusal.
    async with sessions() as session:
        version_row = await session.get(
            StorybookVersion, (seed.storybook_id, seed.version)
        )
        assert version_row is not None
        version_row.moderation_report = make_clean_moderation_report()
        await session.commit()

    await _recall(client, seed)

    async with sessions() as session:
        rows = await session.execute(
            sa.select(StorybookAssignment).where(
                StorybookAssignment.storybook_id == seed.storybook_id
            )
        )
        assignments = list(rows.scalars())
    assert [a.child_profile_id for a in assignments] == [seed.child_profile_id]

    reapprove = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/approve",
        headers=auth(seed.admin_token),
    )
    assert reapprove.status_code == 200, reapprove.text

    shelf = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert shelf.status_code == 200, shelf.text
    assert seed.storybook_id in {s["id"] for s in shelf.json()["stories"]}


async def test_a_recalled_book_appears_in_the_admin_review_queue(
    client: AsyncClient, seed: Seed
) -> None:
    """Recall must put the book where a reviewer will actually find it.

    The queue lists ``in_review`` only, which is why recall targets that status
    rather than inventing a sixth one. A recall that left the book off the queue
    would be a button whose effect nobody could see.
    """
    before = await client.get("/api/v1/review-queue", headers=auth(seed.admin_token))
    assert before.status_code == 200, before.text
    assert seed.storybook_id not in {i["storybook_id"] for i in before.json()["items"]}

    await _recall(client, seed)

    after = await client.get("/api/v1/review-queue", headers=auth(seed.admin_token))
    assert after.status_code == 200, after.text
    assert seed.storybook_id in {i["storybook_id"] for i in after.json()["items"]}


async def test_a_guardian_cannot_recall_a_published_book(
    client: AsyncClient, seed: Seed
) -> None:
    """403 for a guardian, matching submit/approve/send_back/archive.

    Cited by ``api/approval.py::recall_storybook``: authorization is
    ``_load_admin_story`` and nothing in the handler body.
    """
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/recall",
        headers=auth(seed.guardian_token),
        json={"reason_code": "safety_concern"},
    )
    assert resp.status_code == 403, resp.text


async def test_a_child_cannot_recall_a_published_book(
    client: AsyncClient, seed: Seed
) -> None:
    """403 for a child token."""
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/recall",
        headers=auth(seed.child_token),
        json={"reason_code": "safety_concern"},
    )
    assert resp.status_code == 403, resp.text


async def test_a_rejected_recall_leaves_the_book_published(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A 403 must not have moved the status.

    Authorization runs before the service call, so this is a pin on the ordering
    rather than on the status code: a handler that recalled first and checked
    the role afterwards would still return 403 while the book was gone.
    """
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/recall",
        headers=auth(seed.guardian_token),
        json={"reason_code": "safety_concern"},
    )
    assert resp.status_code == 403

    status, _ = await _status(sessions, seed.storybook_id)
    assert status == "published"


async def test_recall_requires_a_reason_code(client: AsyncClient, seed: Seed) -> None:
    """An empty body is a 422; the code is required, not defaulted."""
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/recall",
        headers=auth(seed.admin_token),
        json={},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize(
    "reason_code",
    ["unsatisfying_ending", "not_a_real_code", "", "THRESHOLD_CHANGE"],
)
async def test_recall_rejects_a_code_outside_its_own_vocabulary(
    client: AsyncClient, seed: Seed, reason_code: str
) -> None:
    """422 at the boundary, including for a valid SEND-BACK code.

    ``unsatisfying_ending`` is in the send-back vocabulary and must not be
    accepted here: it critiques a draft and cannot motivate pulling a live book.
    """
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/recall",
        headers=auth(seed.admin_token),
        json={"reason_code": reason_code},
    )
    assert resp.status_code == 422, resp.text
    # app.py::_handle_request_validation_error keeps only type/loc/msg, so the
    # refused value never returns to the caller (CWE-209). The msg does name the
    # permitted vocabulary, which is what makes the 422 actionable, so assert
    # both halves: the caller learns what IS allowed without being told back
    # what they sent.
    body = resp.text
    # The empty-string case is exempt from the echo check only because ``""``
    # is a substring of everything, not because it is echoed.
    assert not reason_code or reason_code not in body, body
    assert "threshold_change" in body, body


async def test_recall_rejects_an_unmodelled_field(
    client: AsyncClient, seed: Seed
) -> None:
    """``extra="forbid"``: a free-text reason is not silently swallowed.

    RecallRequest deliberately has no prose field. A caller that sends one
    should be told, not have it dropped on the floor.
    """
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/recall",
        headers=auth(seed.admin_token),
        json={"reason_code": "other", "reason": "because I said so"},
    )
    assert resp.status_code == 422, resp.text


async def test_recalling_a_book_twice_returns_409(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """The second recall is an illegal transition out of ``in_review``.

    Also the practical idempotency question: recall is not idempotent, and a
    double-click gets a 409 rather than a second event on the same book.
    """
    await _recall(client, seed)
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/recall",
        headers=auth(seed.admin_token),
        json={"reason_code": "threshold_change"},
    )
    assert resp.status_code == 409, resp.text

    async with sessions() as session:
        rows = await session.execute(
            sa.select(sa.func.count())
            .select_from(PipelineEvent)
            .where(PipelineEvent.event_type == "storybook_recalled")
        )
        assert rows.scalar_one() == 1
