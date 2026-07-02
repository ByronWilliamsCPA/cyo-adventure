"""Library listing enrichment: per-profile progress and ratings (C4a-3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# The seed story (03_tier2_lantern.json) starts here; a never-saved reading
# state returns 404 (see test_reading_state_not_found_404), so the PUT body is
# built from scratch rather than round-tripping a GET.
_START_NODE = "n_entrance"


async def test_library_reports_progress_and_rating(
    client: AsyncClient, seed: Seed
) -> None:
    """A saved reading state and rating both surface on the library listing."""
    profile = str(seed.child_profile_id)
    state_url = f"/api/v1/reading-state/{profile}/{seed.storybook_id}"
    put = await client.put(
        state_url,
        headers=auth(seed.child_token),
        json={
            "version": seed.version,
            "current_node": _START_NODE,
            "var_state": {"has_lantern": True},
            "path": [_START_NODE],
            "visit_set": [_START_NODE],
            "save_slots": {},
            "state_revision": 0,
        },
    )
    assert put.status_code == 200, put.text
    rate = await client.post(
        "/api/v1/ratings",
        headers=auth(seed.child_token),
        json={"profile_id": profile, "storybook_id": seed.storybook_id, "value": 5},
    )
    assert rate.status_code == 200, rate.text

    listing = await client.get(
        f"/api/v1/library?profile_id={profile}", headers=auth(seed.child_token)
    )
    assert listing.status_code == 200
    stories = listing.json()["stories"]
    item = next(s for s in stories if s["id"] == seed.storybook_id)
    assert item["rating"] == 5
    assert item["node_count"] > 0
    assert item["progress"] is not None
    assert item["progress"]["nodes_visited"] >= 1
    assert item["progress"]["current_node"] == _START_NODE


async def test_other_childs_activity_not_leaked(
    client: AsyncClient, seed: Seed
) -> None:
    """Sibling/other-family state must never appear under this profile."""
    profile = str(seed.child_profile_id)
    listing = await client.get(
        f"/api/v1/library?profile_id={profile}", headers=auth(seed.child_token)
    )
    assert listing.status_code == 200
    for story in listing.json()["stories"]:
        assert story["rating"] is None
        assert story["progress"] is None
