"""Series tagging and soft-continuation endpoints (WS-B PR 3, Task 5).

Covers the kid create (proposal/anchor), authored create (series/anchor), and
approve (ratify/decline/re-validate) endpoints, plus the view projections
that surface the new fields. Reuses the auth/client fixtures from
``test_story_requests_authored.py`` and the shared anchor-seeding helper from
``_series_utils.py`` (both already established by earlier WS-B PR 3 tasks).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select

from cyo_adventure.db.models import (
    ChildProfile,
    Series,
    Storybook,
    StorybookAssignment,
    StoryRequest,
)
from tests.integration.conftest import Seed, auth

from ._series_utils import seed_published_anchor

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_CREATE = "/api/v1/story-requests"
_AUTHORED = "/api/v1/story-requests/authored"

# Mirrors conftest.Seed's profile_a age band; keeps the confirmation body
# consistent with the seeded profile used across the kid-create matrix.
_CONFIRMATION = {"age_band": "10-13", "length": "medium", "narrative_style": "prose"}


async def _series_count(sessions: async_sessionmaker[AsyncSession]) -> int:
    """Return the total number of Series rows (fresh schema per test)."""
    async with sessions() as session:
        total = await session.scalar(select(func.count()).select_from(Series))
        return int(total or 0)


async def _child_name(
    sessions: async_sessionmaker[AsyncSession], profile_id: uuid.UUID
) -> str:
    """Read a seeded profile's real display name for PII-guard test bodies."""
    async with sessions() as session:
        profile = await session.get(ChildProfile, profile_id)
        assert profile is not None
        return profile.display_name


# ---------------------------------------------------------------------------
# Kid create: proposal / anchor
# ---------------------------------------------------------------------------


async def test_kid_create_stores_proposed_series_title(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    res = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a fox who learns to fish",
            "proposed_series_title": "The Fox Chronicles",
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "pending"
    async with sessions() as session:
        row = await session.get(StoryRequest, uuid.UUID(res.json()["id"]))
        assert row is not None
        assert row.proposed_series_title == "The Fox Chronicles"
        assert row.series_id is None
        assert row.anchor_storybook_id is None


async def test_kid_create_proposal_with_child_name_is_blocked(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A proposed title naming a real family child blocks the whole request.

    The combined screening input (title + text) covers the title, not just
    the request text.
    """
    child_name = await _child_name(sessions, seed.child_profile_id)
    res = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a fox who learns to fish",
            "proposed_series_title": f"{child_name}'s Big Adventures",
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "blocked"
    assert await _series_count(sessions) == 0


async def test_kid_create_proposal_and_anchor_is_422(
    client: AsyncClient, seed: Seed
) -> None:
    """Proposing a new series and anchoring to an existing one are exclusive."""
    res = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a fox tale",
            "proposed_series_title": "New Series",
            "anchor_storybook_id": "s_whatever",
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 422


async def test_kid_anchor_unknown_id_is_404(client: AsyncClient, seed: Seed) -> None:
    res = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "book two of the fox saga",
            "anchor_storybook_id": "s_does_not_exist",
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 404


async def test_kid_anchor_cross_family_is_404(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """An anchor from another family is 404, not 403 (existence hiding)."""
    async with sessions() as session:
        _series, storybook = await seed_published_anchor(
            session,
            family_id=seed.family_id,
            approved_by=seed.admin_user_id,
            age_band="10-13",
        )
        await session.commit()
        anchor_id = storybook.id

    res = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.other_child_profile_id),
            "request_text": "book two of the fox saga",
            "anchor_storybook_id": anchor_id,
        },
        headers=auth(seed.other_guardian_token),
    )
    assert res.status_code == 404


async def test_kid_anchor_unpublished_is_422(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    async with sessions() as session:
        session.add(Storybook(id="s_draft_anchor", family_id=seed.family_id))
        await session.commit()

    res = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "book two of the fox saga",
            "anchor_storybook_id": "s_draft_anchor",
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 422


async def test_kid_anchor_published_without_series_is_422(
    client: AsyncClient, seed: Seed
) -> None:
    """The seeded lantern story is published/approved but not series-linked."""
    res = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "book two of the fox saga",
            "anchor_storybook_id": seed.storybook_id,
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 422


async def test_kid_anchor_band_mismatch_is_422(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    async with sessions() as session:
        _series, storybook = await seed_published_anchor(
            session,
            family_id=seed.family_id,
            approved_by=seed.admin_user_id,
            age_band="8-11",
        )
        await session.commit()
        anchor_id = storybook.id

    res = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "book two of the fox saga",
            "anchor_storybook_id": anchor_id,
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 422


async def test_kid_anchor_happy_path(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    async with sessions() as session:
        series, storybook = await seed_published_anchor(
            session,
            family_id=seed.family_id,
            approved_by=seed.admin_user_id,
            age_band="10-13",
        )
        await session.commit()
        series_id, anchor_id = series.id, storybook.id

    res = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "book two of the fox saga",
            "anchor_storybook_id": anchor_id,
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "pending"
    async with sessions() as session:
        row = await session.get(StoryRequest, uuid.UUID(res.json()["id"]))
        assert row is not None
        assert row.series_id == series_id
        assert row.anchor_storybook_id == anchor_id


# ---------------------------------------------------------------------------
# Authored create: series / anchor
# ---------------------------------------------------------------------------


async def test_authored_series_title_episodic_band(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A '5-8' series carries no state (ADR-011 episodic bands)."""
    res = await client.post(
        _AUTHORED,
        json={
            "request_text": "a patient turtle",
            "age_band": "5-8",
            "length": "short",
            "series_title": "Turtle Tales",
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "approved"
    async with sessions() as session:
        row = await session.get(StoryRequest, uuid.UUID(res.json()["id"]))
        assert row is not None
        assert row.series_id is not None
        assert row.proposed_series_title is None
        series = await session.get(Series, row.series_id)
        assert series is not None
        assert series.title == "Turtle Tales"
        assert series.carries_state is False


async def test_authored_series_title_state_carrying_band(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A '13-16' series carries state (ADR-011 non-episodic bands)."""
    res = await client.post(
        _AUTHORED,
        json={
            "request_text": "a teen navigating a new school",
            "age_band": "13-16",
            "length": "short",
            "series_title": "New Beginnings",
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "approved"
    async with sessions() as session:
        row = await session.get(StoryRequest, uuid.UUID(res.json()["id"]))
        assert row is not None
        assert row.series_id is not None
        assert row.proposed_series_title is None
        series = await session.get(Series, row.series_id)
        assert series is not None
        assert series.title == "New Beginnings"
        assert series.carries_state is True


async def test_authored_series_title_blocked_creates_no_series(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    child_name = await _child_name(sessions, seed.child_profile_id)
    res = await client.post(
        _AUTHORED,
        json={
            "request_text": "a patient turtle",
            "age_band": "5-8",
            "length": "short",
            "series_title": f"{child_name}'s Turtle Tales",
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "blocked"
    assert res.json()["concept_id"] is None
    assert await _series_count(sessions) == 0


async def test_authored_anchor_happy_path(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    async with sessions() as session:
        series, storybook = await seed_published_anchor(
            session,
            family_id=seed.family_id,
            approved_by=seed.admin_user_id,
            age_band="10-13",
        )
        await session.commit()
        series_id, anchor_id = series.id, storybook.id

    res = await client.post(
        _AUTHORED,
        json={
            "request_text": "book two of the fox saga",
            "age_band": "10-13",
            "length": "short",
            "anchor_storybook_id": anchor_id,
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 201, res.text
    payload = res.json()
    assert payload["status"] == "approved"
    assert payload["concept_id"]
    async with sessions() as session:
        row = await session.get(StoryRequest, uuid.UUID(payload["id"]))
        assert row is not None
        assert row.series_id == series_id
        assert row.anchor_storybook_id == anchor_id


async def test_authored_anchor_band_mismatch_is_422(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    async with sessions() as session:
        _series, storybook = await seed_published_anchor(
            session,
            family_id=seed.family_id,
            approved_by=seed.admin_user_id,
            age_band="8-11",
        )
        await session.commit()
        anchor_id = storybook.id

    res = await client.post(
        _AUTHORED,
        json={
            "request_text": "book two of the fox saga",
            "age_band": "10-13",
            "length": "short",
            "anchor_storybook_id": anchor_id,
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# Approve: ratify / decline / re-validate
# ---------------------------------------------------------------------------


async def test_approve_series_title_edits_proposal(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    created = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a fox who learns to fish",
            "proposed_series_title": "The Fox Chronicles",
        },
        headers=auth(seed.guardian_token),
    )
    req_id = created.json()["id"]

    res = await client.post(
        f"{_CREATE}/{req_id}/approve",
        json={**_CONFIRMATION, "series_title": "The Fantastic Fox Saga"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200, res.text
    async with sessions() as session:
        row = await session.get(StoryRequest, uuid.UUID(req_id))
        assert row is not None
        assert row.series_id is not None
        assert row.proposed_series_title == "The Fox Chronicles"
        series = await session.get(Series, row.series_id)
        assert series is not None
        assert series.title == "The Fantastic Fox Saga"


async def test_approve_omits_series_title_declines_proposal(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    created = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a fox who learns to fish",
            "proposed_series_title": "The Fox Chronicles",
        },
        headers=auth(seed.guardian_token),
    )
    req_id = created.json()["id"]

    res = await client.post(
        f"{_CREATE}/{req_id}/approve",
        json=_CONFIRMATION,
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200, res.text
    async with sessions() as session:
        row = await session.get(StoryRequest, uuid.UUID(req_id))
        assert row is not None
        assert row.series_id is None
        assert row.proposed_series_title == "The Fox Chronicles"
    assert await _series_count(sessions) == 0


async def test_approve_anchored_matching_band_succeeds(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    async with sessions() as session:
        _series, storybook = await seed_published_anchor(
            session,
            family_id=seed.family_id,
            approved_by=seed.admin_user_id,
            age_band="10-13",
        )
        await session.commit()
        anchor_id = storybook.id

    created = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "book two of the fox saga",
            "anchor_storybook_id": anchor_id,
        },
        headers=auth(seed.guardian_token),
    )
    assert created.status_code == 201, created.text
    req_id = created.json()["id"]

    res = await client.post(
        f"{_CREATE}/{req_id}/approve",
        json=_CONFIRMATION,
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200, res.text


async def test_approve_anchored_band_mismatch_is_422(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    async with sessions() as session:
        _series, storybook = await seed_published_anchor(
            session,
            family_id=seed.family_id,
            approved_by=seed.admin_user_id,
            age_band="10-13",
        )
        await session.commit()
        anchor_id = storybook.id

    created = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "book two of the fox saga",
            "anchor_storybook_id": anchor_id,
        },
        headers=auth(seed.guardian_token),
    )
    assert created.status_code == 201, created.text
    req_id = created.json()["id"]

    res = await client.post(
        f"{_CREATE}/{req_id}/approve",
        json={**_CONFIRMATION, "age_band": "13-16"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422


async def test_approve_anchored_with_series_title_is_422(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    async with sessions() as session:
        _series, storybook = await seed_published_anchor(
            session,
            family_id=seed.family_id,
            approved_by=seed.admin_user_id,
            age_band="10-13",
        )
        await session.commit()
        anchor_id = storybook.id

    created = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "book two of the fox saga",
            "anchor_storybook_id": anchor_id,
        },
        headers=auth(seed.guardian_token),
    )
    assert created.status_code == 201, created.text
    req_id = created.json()["id"]

    res = await client.post(
        f"{_CREATE}/{req_id}/approve",
        json={**_CONFIRMATION, "series_title": "A New Fork"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422


async def test_approve_blocked_title_is_422(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A blocked series-title edit never echoes the submitted title back."""
    child_name = await _child_name(sessions, seed.child_profile_id)
    created = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a fox who learns to fish",
        },
        headers=auth(seed.guardian_token),
    )
    assert created.status_code == 201, created.text
    req_id = created.json()["id"]

    blocked_title = f"{child_name}'s Big Adventures"
    res = await client.post(
        f"{_CREATE}/{req_id}/approve",
        json={**_CONFIRMATION, "series_title": blocked_title},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422
    assert blocked_title not in res.text
    assert child_name not in res.text


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


async def test_guardian_list_shows_proposal_and_anchor_fields(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    async with sessions() as session:
        _series, storybook = await seed_published_anchor(
            session,
            family_id=seed.family_id,
            approved_by=seed.admin_user_id,
            age_band="10-13",
        )
        await session.commit()
        anchor_id = storybook.id

    with_title = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a fox who learns to fish",
            "proposed_series_title": "The Fox Chronicles",
        },
        headers=auth(seed.guardian_token),
    )
    assert with_title.status_code == 201, with_title.text
    with_title_id = with_title.json()["id"]

    with_anchor = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "book two of the fox saga",
            "anchor_storybook_id": anchor_id,
        },
        headers=auth(seed.guardian_token),
    )
    assert with_anchor.status_code == 201, with_anchor.text
    with_anchor_id = with_anchor.json()["id"]

    child_name = await _child_name(sessions, seed.child_profile_id)
    blocked = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": f"a story about {child_name}",
            "proposed_series_title": "Ignored Title",
        },
        headers=auth(seed.guardian_token),
    )
    assert blocked.status_code == 201, blocked.text
    assert blocked.json()["status"] == "blocked"
    blocked_id = blocked.json()["id"]

    res = await client.get(_CREATE, headers=auth(seed.guardian_token))
    assert res.status_code == 200
    rows = {r["id"]: r for r in res.json()["requests"]}

    assert rows[with_title_id]["proposed_series_title"] == "The Fox Chronicles"
    assert rows[with_title_id]["anchor_storybook_id"] is None

    assert rows[with_anchor_id]["anchor_storybook_id"] == anchor_id
    assert rows[with_anchor_id]["proposed_series_title"] is None

    assert rows[blocked_id]["proposed_series_title"] is None


async def test_kid_library_listing_surfaces_series_fields(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    async with sessions() as session:
        _series, storybook = await seed_published_anchor(
            session,
            family_id=seed.family_id,
            approved_by=seed.admin_user_id,
            age_band="10-13",
            book_index=1,
        )
        session.add(
            StorybookAssignment(
                child_profile_id=seed.child_profile_id,
                storybook_id=storybook.id,
            )
        )
        await session.commit()
        anchor_id = storybook.id

    res = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 200, res.text
    stories = {s["id"]: s for s in res.json()["stories"]}

    series_book = stories[anchor_id]
    assert series_book["series_id"] is not None
    assert series_book["book_index"] == 1

    standalone_book = stories[seed.storybook_id]
    assert standalone_book["series_id"] is None
    assert standalone_book["book_index"] is None
