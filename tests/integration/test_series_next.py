"""Integration tests for GET /api/v1/series-next (WS-G PR 2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import (
    Series,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
)
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    import uuid

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _blob(
    story_id: str,
    *,
    series_id: str | None,
    book_index: int,
    entry: str = "n_start",
) -> dict[str, object]:
    """A minimal schema-valid two-node story blob, optionally series-embedded."""
    metadata: dict[str, object] = {"age_band": "10-13"}
    if series_id is not None:
        metadata["series"] = {
            "series_id": series_id,
            "book_index": book_index,
            "series_entry_node": entry,
            "is_final": False,
            "carries_state": True,
        }
    return {
        "schema_version": "2.0",
        "id": story_id,
        "version": 1,
        "title": f"Book {book_index}",
        "metadata": metadata,
        "variables": [
            {"name": "courage", "type": "int", "initial": 0, "min": 0, "max": 5}
        ],
        "start_node": "n_start",
        "nodes": [
            {
                "id": "n_start",
                "body": "Onward.",
                "is_ending": False,
                "choices": [{"id": "c_go", "label": "Go", "target": "n_end"}],
            },
            {
                "id": "n_end",
                "body": "Done.",
                "is_ending": True,
                "ending": {
                    "id": "e_done",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The End",
                },
                "choices": [],
            },
        ],
    }


async def _seed_series(
    session: AsyncSession, family_id: uuid.UUID, created_by: uuid.UUID
) -> Series:
    series = Series(
        family_id=family_id,
        title="Ember Trail",
        age_band="10-13",
        carries_state=True,
        created_by=created_by,
    )
    session.add(series)
    await session.flush()
    return series


async def _seed_book(
    session: AsyncSession,
    series: Series,
    seed: Seed,
    *,
    story_id: str,
    book_index: int,
    status: str = "published",
    published: bool = True,
    embed: bool = True,
    visibility: str = "family",
    assign_to: uuid.UUID | None = None,
) -> Storybook:
    book = Storybook(
        id=story_id,
        family_id=seed.family_id,
        status=status,
        visibility=visibility,
        current_published_version=1 if published else None,
        series_id=series.id,
        book_index=book_index,
    )
    session.add(book)
    session.add(
        StorybookVersion(
            storybook_id=story_id,
            version=1,
            blob=_blob(
                story_id,
                series_id=str(series.id) if embed else None,
                book_index=book_index,
            ),
            approved_by=seed.admin_user_id,
        )
    )
    if assign_to is not None:
        session.add(
            StorybookAssignment(
                child_profile_id=assign_to,
                storybook_id=story_id,
                assigned_by=seed.admin_user_id,
            )
        )
    await session.flush()
    return book


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_returns_next_published_book(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Book 1 of an own-family series resolves book 2 with its declared entry node."""
    async with sessions() as session:
        series = await _seed_series(session, seed.family_id, seed.admin_user_id)
        await _seed_book(session, series, seed, story_id="s_next_a1", book_index=1)
        await _seed_book(session, series, seed, story_id="s_next_a2", book_index=2)
        await session.commit()
    resp = await client.get(
        f"/api/v1/series-next/{seed.child_profile_id}/s_next_a1",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text
    nxt = resp.json()["next"]
    assert nxt == {
        "storybook_id": "s_next_a2",
        "version": 1,
        "title": "Book 2",
        "series_entry_node": "n_start",
        "carries_state": True,
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_null_for_non_series_book(
    client: AsyncClient, seed: Seed
) -> None:
    """A storybook with no series linkage answers next: null."""
    resp = await client.get(
        f"/api/v1/series-next/{seed.child_profile_id}/{seed.storybook_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200
    assert resp.json() == {"next": None}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_null_for_last_book(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The top-index book has no next; expected absence is null, not an error."""
    async with sessions() as session:
        series = await _seed_series(session, seed.family_id, seed.admin_user_id)
        await _seed_book(session, series, seed, story_id="s_next_b1", book_index=1)
        await _seed_book(session, series, seed, story_id="s_next_b2", book_index=2)
        await session.commit()
    resp = await client.get(
        f"/api/v1/series-next/{seed.child_profile_id}/s_next_b2",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200
    assert resp.json() == {"next": None}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_null_when_next_unpublished(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """An in-review next book is invisible to the reader."""
    async with sessions() as session:
        series = await _seed_series(session, seed.family_id, seed.admin_user_id)
        await _seed_book(session, series, seed, story_id="s_next_c1", book_index=1)
        await _seed_book(
            session,
            series,
            seed,
            story_id="s_next_c2",
            book_index=2,
            status="in_review",
            published=False,
        )
        await session.commit()
    resp = await client.get(
        f"/api/v1/series-next/{seed.child_profile_id}/s_next_c1",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200
    assert resp.json() == {"next": None}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_unassigned_catalog_sibling_is_null(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A cross-family catalog next book without an assignment answers null."""
    async with sessions() as session:
        series = await _seed_series(session, seed.family_id, seed.admin_user_id)
        await _seed_book(
            session,
            series,
            seed,
            story_id="s_next_d1",
            book_index=1,
            visibility="catalog",
            assign_to=seed.other_child_profile_id,
        )
        await _seed_book(
            session,
            series,
            seed,
            story_id="s_next_d2",
            book_index=2,
            visibility="catalog",
        )
        await session.commit()
    resp = await client.get(
        f"/api/v1/series-next/{seed.other_child_profile_id}/s_next_d1",
        headers=auth(seed.other_child_token),
    )
    assert resp.status_code == 200
    assert resp.json() == {"next": None}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_assigned_catalog_sibling_returned(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Assigning the catalog next book makes it resolvable for that profile."""
    async with sessions() as session:
        series = await _seed_series(session, seed.family_id, seed.admin_user_id)
        await _seed_book(
            session,
            series,
            seed,
            story_id="s_next_e1",
            book_index=1,
            visibility="catalog",
            assign_to=seed.other_child_profile_id,
        )
        await _seed_book(
            session,
            series,
            seed,
            story_id="s_next_e2",
            book_index=2,
            visibility="catalog",
            assign_to=seed.other_child_profile_id,
        )
        await session.commit()
    resp = await client.get(
        f"/api/v1/series-next/{seed.other_child_profile_id}/s_next_e1",
        headers=auth(seed.other_child_token),
    )
    assert resp.status_code == 200
    assert resp.json()["next"]["storybook_id"] == "s_next_e2"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_legacy_sibling_has_null_entry_node(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A pre-WS-G next book (no embedded block) is returned with entry null."""
    async with sessions() as session:
        series = await _seed_series(session, seed.family_id, seed.admin_user_id)
        await _seed_book(session, series, seed, story_id="s_next_f1", book_index=1)
        await _seed_book(
            session, series, seed, story_id="s_next_f2", book_index=2, embed=False
        )
        await session.commit()
    resp = await client.get(
        f"/api/v1/series-next/{seed.child_profile_id}/s_next_f1",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200
    nxt = resp.json()["next"]
    assert nxt["storybook_id"] == "s_next_f2"
    assert nxt["series_entry_node"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_other_familys_profile_forbidden(
    client: AsyncClient, seed: Seed
) -> None:
    """A child token cannot query another family's profile id."""
    resp = await client.get(
        f"/api/v1/series-next/{seed.other_child_profile_id}/{seed.storybook_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_series_next_unknown_current_book_is_404(
    client: AsyncClient, seed: Seed
) -> None:
    """The CURRENT book being unknown is an error, not an expected absence."""
    resp = await client.get(
        f"/api/v1/series-next/{seed.child_profile_id}/s_does_not_exist",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404
