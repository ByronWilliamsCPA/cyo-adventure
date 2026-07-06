"""IDOR and authorization negative tests (authorization-matrix.md)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.integration.conftest import Seed, auth

pytestmark = [pytest.mark.security]

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_cannot_read_other_profile_state(
    client: AsyncClient, seed: Seed
) -> None:
    """Child A cannot read child B's reading state (IDOR)."""
    resp = await client.get(
        f"/api/v1/reading-state/{seed.other_child_profile_id}/{seed.storybook_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_cannot_read_other_profile_library(
    client: AsyncClient, seed: Seed
) -> None:
    """Child A cannot list child B's library by passing B's profile id."""
    resp = await client.get(
        "/api/v1/library",
        params={"profile_id": str(seed.other_child_profile_id)},
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_cannot_write_other_profile_state(
    client: AsyncClient, seed: Seed
) -> None:
    """Child A cannot PUT reading state for child B's profile (path is authoritative)."""
    resp = await client.put(
        f"/api/v1/reading-state/{seed.other_child_profile_id}/{seed.storybook_id}",
        json={
            "version": seed.version,
            "current_node": "n_cave_fork",
            "var_state": {},
            "path": ["n_entrance"],
            "visit_set": ["n_entrance"],
            "save_slots": {},
            "state_revision": 0,
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cross_family_guardian_cannot_fetch_story(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian from another family cannot fetch family A's story (403)."""
    resp = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}",
        headers=auth(seed.other_guardian_token),
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_missing_token_is_401(client: AsyncClient, seed: Seed) -> None:
    """A request with no bearer token is rejected with 401."""
    resp = await client.get(
        f"/api/v1/reading-state/{seed.child_profile_id}/{seed.storybook_id}",
    )
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unknown_subject_is_401(client: AsyncClient, seed: Seed) -> None:
    """A bearer token for an unknown subject is rejected with 401."""
    resp = await client.get(
        f"/api/v1/reading-state/{seed.child_profile_id}/{seed.storybook_id}",
        headers=auth("nobody-here"),
    )
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_without_profile_is_403(client: AsyncClient, seed: Seed) -> None:
    """A child user with no assigned profile can access nothing (empty set)."""
    resp = await client.get(
        f"/api/v1/reading-state/{seed.child_profile_id}/{seed.storybook_id}",
        headers=auth("child-noprofile"),
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardian_can_read_family_profile(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian may act on any profile within its own family."""
    resp = await client.get(
        "/api/v1/library",
        params={"profile_id": str(seed.child_profile_id)},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 200
