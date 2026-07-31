"""Route-level (real HTTP) proof that personalization sentinels are stripped.

ADR-023 P3 requires a raw ``{~SLOTID:GenericWord~}`` sentinel to strip to its
generic word on every non-opted-in read surface. The PR's own execution plan
(``docs/planning/story-personalization-execution-plan.md``, Tasks A4 and A5)
committed to INTEGRATION tests asserting on ``resp.content`` from real HTTP
calls; every "route" test that actually shipped instead calls the handler
coroutine directly with a hand-built context and a fake session, so nothing
in the PR ever crossed the FastAPI app or its response-serialization layer.
This module is that missing check.

Each test seeds a published, approved storybook whose stored blob carries a
sentinel in its title, hits the real endpoint over the ASGI transport (the
``client`` fixture from ``tests/integration/conftest.py``), and asserts on
the raw JSON text: no ``"{~"`` marker anywhere in the response body, and the
generic word present in its place. A response-text ``"{~" not in resp.text``
check is a whole-payload guard, not per-field, so it also catches a sentinel
leaking through an unexpected field the test did not think to name.

Surfaces covered (five of the six strip call sites in
``storybook/sentinels.py``'s consumers): library list
(``api/library.py::_library_item``), guardian books
(``api/assignments.py::list_guardian_books``), reading history
(``api/reading_history.py::_book_title``), recommendations
(``api/recommendations.py::_book_title``), and series-next
(``api/reading.py::get_series_next``). The sixth, notifications
(``api/notifications.py::list_notifications``), needs a ``pipeline_event``
row composed through ``notifications/registry.py``'s kind registry; that
setup is meaningfully heavier than the other five (an event row plus the
registry's entity-resolution path) and is deferred rather than rushed, per
this task's "partial honest coverage beats a broad test that does not
really exercise the app" instruction. See the module docstring note in the
last test below (the CONTRAST case) for why the raw version-blob endpoint is
proven NOT to strip, on the same footing as the five above.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import (
    ChildProfile,
    Completion,
    Rating,
    Series,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
)
from cyo_adventure.storybook.sentinels import wrap

from .conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_TOKEN = wrap("HERO", "Explorer")


def _sentinel_blob(title: str, **extra: object) -> dict[str, object]:
    """A minimal stored blob whose title carries a raw sentinel token.

    None of the surfaces under test here re-validate the blob against the
    full ``Storybook`` pydantic model (only the reading-state PUT path
    does), so a minimal, schema-light blob is sufficient: each handler
    reads ``title``/``metadata``/``nodes`` defensively off the raw dict.
    """
    blob: dict[str, object] = {
        "title": title,
        "metadata": {"age_band": "6-8", "tier": 1, "reading_level": {"target": 2.0}},
        "nodes": [{"id": "n1", "body": "Once upon a time.", "is_ending": True}],
    }
    blob.update(extra)
    return blob


async def test_library_list_strips_sentinel_over_http(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """GET /api/v1/library?profile_id=... never carries a raw sentinel marker."""
    async with sessions() as session:
        session.add(
            Storybook(
                id="sentinel-library",
                family_id=seed.family_id,
                status="published",
                current_published_version=1,
            )
        )
        session.add(
            StorybookVersion(
                storybook_id="sentinel-library",
                version=1,
                blob=_sentinel_blob(f"{_TOKEN}'s Bedtime Adventure"),
                approved_by=seed.admin_user_id,
            )
        )
        session.add(
            StorybookAssignment(
                child_profile_id=seed.child_profile_id,
                storybook_id="sentinel-library",
            )
        )
        await session.commit()

    resp = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text
    assert "{~" not in resp.text
    row = next(b for b in resp.json()["stories"] if b["id"] == "sentinel-library")
    assert "Explorer" in row["title"]


async def test_guardian_books_strips_sentinel_over_http(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """GET /api/v1/guardian/books never carries a raw sentinel marker."""
    async with sessions() as session:
        session.add(
            Storybook(
                id="sentinel-guardian",
                family_id=seed.family_id,
                status="published",
                current_published_version=1,
            )
        )
        session.add(
            StorybookVersion(
                storybook_id="sentinel-guardian",
                version=1,
                blob=_sentinel_blob(f"{_TOKEN} and the Lost City"),
                approved_by=seed.admin_user_id,
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/guardian/books", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    assert "{~" not in resp.text
    row = next(
        b for b in resp.json()["books"] if b["storybook_id"] == "sentinel-guardian"
    )
    assert "Explorer" in row["title"]


async def test_reading_history_strips_sentinel_over_http(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """GET /api/v1/reading-history/{profile_id} never carries a raw marker.

    A ``Completion`` row (not just a published+assigned book) is what makes
    the book appear in the history listing at all; ``get_reading_history``
    joins from the profile's completion/reading-state rows, not from
    ``StorybookAssignment``.
    """
    async with sessions() as session:
        session.add(
            Storybook(
                id="sentinel-history",
                family_id=seed.family_id,
                status="published",
                current_published_version=1,
            )
        )
        session.add(
            StorybookVersion(
                storybook_id="sentinel-history",
                version=1,
                blob=_sentinel_blob(f"{_TOKEN}'s Ending", metadata={"ending_count": 1}),
                approved_by=seed.admin_user_id,
            )
        )
        # The Completion row's composite FK targets storybook_version, whose
        # own FK targets storybook; a plain add() batch has no ORM
        # relationship() to derive that ordering from, so flush the parent
        # rows first (mirrors tests/integration/test_series_next.py's
        # per-book flush before adding a dependent assignment row).
        await session.flush()
        session.add(
            Completion(
                child_profile_id=seed.child_profile_id,
                storybook_id="sentinel-history",
                version=1,
                ending_id="e_done",
            )
        )
        await session.commit()

    resp = await client.get(
        f"/api/v1/reading-history/{seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text
    assert "{~" not in resp.text
    row = next(
        b for b in resp.json()["books"] if b["storybook_id"] == "sentinel-history"
    )
    assert "Explorer" in row["title"]


async def test_recommendations_strips_sentinel_over_http(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """GET /api/v1/recommendations/{profile_id} never carries a raw marker.

    Ring 1 (ADR-016): another profile in the SAME family rates the book 5,
    which is what makes it a recommendation for ``seed.child_profile_id``;
    the book must also be visible to (assigned to) the requesting profile.
    """
    async with sessions() as session:
        rater = ChildProfile(
            family_id=seed.family_id, display_name="Rater", age_band="6-8"
        )
        session.add(rater)
        await session.flush()

        session.add(
            Storybook(
                id="sentinel-reco",
                family_id=seed.family_id,
                status="published",
                current_published_version=1,
            )
        )
        session.add(
            StorybookVersion(
                storybook_id="sentinel-reco",
                version=1,
                blob=_sentinel_blob(f"{_TOKEN} Sails Away"),
                approved_by=seed.admin_user_id,
            )
        )
        session.add(
            StorybookAssignment(
                child_profile_id=seed.child_profile_id,
                storybook_id="sentinel-reco",
            )
        )
        # Rating's FK targets storybook directly; flush the parent row first
        # for the same reason as the reading-history test above.
        await session.flush()
        session.add(
            Rating(child_profile_id=rater.id, storybook_id="sentinel-reco", value=5)
        )
        await session.commit()

    resp = await client.get(
        f"/api/v1/recommendations/{seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text
    assert "{~" not in resp.text
    row = next(i for i in resp.json()["items"] if i["storybook_id"] == "sentinel-reco")
    assert "Explorer" in row["title"]


async def test_series_next_strips_sentinel_over_http(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """GET /api/v1/series-next/{profile_id}/{storybook_id} never carries a marker.

    Book 1 (the current book, no sentinel) resolves book 2 (the sibling,
    sentinel-bearing title); the response's ``next.title`` must be stripped.
    """
    async with sessions() as session:
        series = Series(
            family_id=seed.family_id,
            title="Sentinel Trail",
            age_band="10-13",
            carries_state=True,
            created_by=seed.admin_user_id,
        )
        session.add(series)
        await session.flush()

        session.add(
            Storybook(
                id="sentinel-series-1",
                family_id=seed.family_id,
                status="published",
                current_published_version=1,
                series_id=series.id,
                book_index=1,
            )
        )
        session.add(
            StorybookVersion(
                storybook_id="sentinel-series-1",
                version=1,
                blob=_sentinel_blob("Book One"),
                approved_by=seed.admin_user_id,
            )
        )
        session.add(
            StorybookAssignment(
                child_profile_id=seed.child_profile_id,
                storybook_id="sentinel-series-1",
            )
        )
        session.add(
            Storybook(
                id="sentinel-series-2",
                family_id=seed.family_id,
                status="published",
                current_published_version=1,
                series_id=series.id,
                book_index=2,
            )
        )
        session.add(
            StorybookVersion(
                storybook_id="sentinel-series-2",
                version=1,
                blob=_sentinel_blob(f"{_TOKEN}'s Return"),
                approved_by=seed.admin_user_id,
            )
        )
        session.add(
            StorybookAssignment(
                child_profile_id=seed.child_profile_id,
                storybook_id="sentinel-series-2",
            )
        )
        await session.commit()

    resp = await client.get(
        f"/api/v1/series-next/{seed.child_profile_id}/sentinel-series-1",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text
    assert "{~" not in resp.text
    nxt = resp.json()["next"]
    assert nxt is not None
    assert "Explorer" in nxt["title"]


async def test_raw_version_endpoint_returns_sentinel_verbatim_contrast(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """CONTRAST: GET .../storybooks/{id}/versions/{v} is NOT stripped.

    This is the artifact the client resolves personalization against
    (ADR-023 P3), so the raw sentinel token MUST survive verbatim. Pinning
    this alongside the five stripped surfaces above proves the two
    behaviors deliberately differ, rather than each being independently
    (and possibly accidentally) asserted in isolation.
    """
    async with sessions() as session:
        session.add(
            Storybook(
                id="sentinel-raw",
                family_id=seed.family_id,
                status="published",
                current_published_version=1,
            )
        )
        session.add(
            StorybookVersion(
                storybook_id="sentinel-raw",
                version=1,
                blob=_sentinel_blob(f"{_TOKEN}'s Untouched Title"),
                approved_by=seed.admin_user_id,
            )
        )
        # M2: the blob-fetch path requires an assignment row for one of the
        # caller's own profiles, guardians included; without it this seed is
        # an unassigned book and the endpoint correctly 404s before any
        # sentinel handling runs.
        session.add(
            StorybookAssignment(
                child_profile_id=seed.child_profile_id,
                storybook_id="sentinel-raw",
                assigned_by=seed.admin_user_id,
            )
        )
        await session.commit()

    resp = await client.get(
        "/api/v1/storybooks/sentinel-raw/versions/1",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 200, resp.text
    assert "{~HERO:Explorer~}" in resp.text
    assert resp.json()["title"] == f"{_TOKEN}'s Untouched Title"
