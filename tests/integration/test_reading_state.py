"""Integration tests for the library, reading-state, and completion endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient


def _save_body(
    version: int, *, node: str, revision: int, **extra: object
) -> dict[str, object]:
    """Build a reading-state PUT body."""
    return {
        "version": version,
        "current_node": node,
        "var_state": {"has_lantern": True},
        "path": ["n_entrance", node],
        "visit_set": ["n_entrance", node],
        "save_slots": {},
        "state_revision": revision,
        **extra,
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_library_lists_published_story(client: AsyncClient, seed: Seed) -> None:
    """A child sees the family's published story in its library."""
    resp = await client.get(
        "/api/v1/library",
        params={"profile_id": str(seed.child_profile_id)},
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()["stories"]]
    assert seed.storybook_id in ids


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_storybook_version_returns_blob(
    client: AsyncClient, seed: Seed
) -> None:
    """Fetching a story version returns its Storybook JSON blob."""
    resp = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == seed.storybook_id
    assert "nodes" in body


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reading_state_round_trip(client: AsyncClient, seed: Seed) -> None:
    """A saved reading state can be read back with an incremented revision."""
    put = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{seed.storybook_id}",
        json=_save_body(seed.version, node="n_cave_fork", revision=0),
        headers=auth(seed.child_token),
    )
    assert put.status_code == 200, put.text
    assert put.json()["state_revision"] == 1
    got = await client.get(
        f"/api/v1/reading-state/{seed.child_profile_id}/{seed.storybook_id}",
        headers=auth(seed.child_token),
    )
    assert got.status_code == 200
    assert got.json()["current_node"] == "n_cave_fork"
    assert got.json()["state_revision"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stale_revision_returns_409(client: AsyncClient, seed: Seed) -> None:
    """A PUT with a stale base revision loses the race and gets a 409."""
    url = f"/api/v1/reading-state/{seed.child_profile_id}/{seed.storybook_id}"
    first = await client.put(
        url,
        json=_save_body(seed.version, node="n_cave_fork", revision=0),
        headers=auth(seed.child_token),
    )
    assert first.status_code == 200
    stale = await client.put(
        url,
        json=_save_body(seed.version, node="n_treasure", revision=0),
        headers=auth(seed.child_token),
    )
    assert stale.status_code == 409
    body = stale.json()
    assert body["current_row"]["state_revision"] == 1
    assert "use_newer_progress" in body["options"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_version_mismatch_returns_409(client: AsyncClient, seed: Seed) -> None:
    """A save against a different version than the session started on is a 409."""
    url = f"/api/v1/reading-state/{seed.child_profile_id}/{seed.storybook_id}"
    await client.put(
        url,
        json=_save_body(seed.version, node="n_cave_fork", revision=0),
        headers=auth(seed.child_token),
    )
    mismatch = await client.put(
        url,
        json=_save_body(seed.version + 1, node="n_cave_fork", revision=1),
        headers=auth(seed.child_token),
    )
    assert mismatch.status_code == 409
    assert "version" in mismatch.json()["detail"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_idempotent_event_replay(client: AsyncClient, seed: Seed) -> None:
    """Replaying a PUT with the same event_id does not double-apply."""
    url = f"/api/v1/reading-state/{seed.child_profile_id}/{seed.storybook_id}"
    body = _save_body(seed.version, node="n_cave_fork", revision=0, event_id="evt-1")
    first = await client.put(url, json=body, headers=auth(seed.child_token))
    assert first.status_code == 200
    assert first.json()["state_revision"] == 1
    replay = await client.put(url, json=body, headers=auth(seed.child_token))
    assert replay.status_code == 200
    assert replay.json()["state_revision"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reading_state_not_found_404(client: AsyncClient, seed: Seed) -> None:
    """Reading state that was never saved returns 404."""
    resp = await client.get(
        f"/api/v1/reading-state/{seed.child_profile_id}/{seed.storybook_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_completion_recorded(client: AsyncClient, seed: Seed) -> None:
    """A completion with a valid ending id is recorded."""
    resp = await client.post(
        "/api/v1/completions",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "version": seed.version,
            "ending_id": "e_treasure_found",
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ending_id"] == "e_treasure_found"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sequential_updates_increment_revision(
    client: AsyncClient, seed: Seed
) -> None:
    """Two successful saves walk the revision forward (create then update)."""
    url = f"/api/v1/reading-state/{seed.child_profile_id}/{seed.storybook_id}"
    first = await client.put(
        url,
        json=_save_body(seed.version, node="n_cave_fork", revision=0),
        headers=auth(seed.child_token),
    )
    assert first.json()["state_revision"] == 1
    second = await client.put(
        url,
        json=_save_body(seed.version, node="n_treasure", revision=1),
        headers=auth(seed.child_token),
    )
    assert second.status_code == 200
    assert second.json()["state_revision"] == 2
    assert second.json()["current_node"] == "n_treasure"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_profile_id_is_422(client: AsyncClient, seed: Seed) -> None:
    """A non-UUID profile id is rejected with 422 (library and reading-state)."""
    lib = await client.get(
        "/api/v1/library",
        params={"profile_id": "not-a-uuid"},
        headers=auth(seed.guardian_token),
    )
    assert lib.status_code == 422
    state = await client.get(
        f"/api/v1/reading-state/not-a-uuid/{seed.storybook_id}",
        headers=auth(seed.guardian_token),
    )
    assert state.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unknown_storybook_is_404(client: AsyncClient, seed: Seed) -> None:
    """Reading state for an unknown story returns 404."""
    resp = await client.get(
        f"/api/v1/reading-state/{seed.child_profile_id}/s_missing",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unknown_version_blob_is_404(client: AsyncClient, seed: Seed) -> None:
    """Fetching a non-existent version returns 404."""
    resp = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/999",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_completion_unknown_version_is_404(
    client: AsyncClient, seed: Seed
) -> None:
    """A completion citing a non-existent version returns 404."""
    resp = await client.post(
        "/api/v1/completions",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "version": 999,
            "ending_id": "e_treasure_found",
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_completion_invalid_ending_422(client: AsyncClient, seed: Seed) -> None:
    """A completion citing an unknown ending id is rejected."""
    resp = await client.post(
        "/api/v1/completions",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "version": seed.version,
            "ending_id": "e_not_real",
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 422
