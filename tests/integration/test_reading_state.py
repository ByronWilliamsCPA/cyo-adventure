"""Integration tests for the library, reading-state, and completion endpoints."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import (
    ChildProfile,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
)
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_LANTERN = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "storybook"
    / "valid"
    / "03_tier2_lantern.json"
)


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
async def test_list_completions_returns_profile_completions(
    client: AsyncClient, seed: Seed
) -> None:
    """A recorded completion appears in the profile's completion list (Phase 3d)."""
    await client.post(
        "/api/v1/completions",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "version": seed.version,
            "ending_id": "e_treasure_found",
        },
        headers=auth(seed.child_token),
    )
    resp = await client.get(
        f"/api/v1/completions/{seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text
    completions = resp.json()["completions"]
    assert any(
        c["storybook_id"] == seed.storybook_id and c["ending_id"] == "e_treasure_found"
        for c in completions
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_completions_other_profile_forbidden(
    client: AsyncClient, seed: Seed
) -> None:
    """A child cannot list another profile's completions (403)."""
    resp = await client.get(
        f"/api/v1/completions/{seed.other_child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_completions_invalid_profile_uuid_rejected(
    client: AsyncClient, seed: Seed
) -> None:
    """A non-UUID profile id is rejected with 422."""
    resp = await client.get(
        "/api/v1/completions/not-a-uuid",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text


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


# ---------------------------------------------------------------------------
# Reading-state and completion paths honor catalog visibility (Task 13
# follow-up, same E5 amendment ruling): an assigned cross-family
# visibility='catalog' book must accept the child's progress saves and
# completions; an unassigned one stays 403; a cross-family
# visibility='family' book stays 403 even with an assignment row (isolating
# the family filter, not the assignment gate, as the cause of that denial).
# ---------------------------------------------------------------------------


async def _add_cross_family_book(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    story_id: str,
    *,
    visibility: str,
    assign: bool,
) -> str:
    """Insert an approved, published book owned by Family B with a real blob.

    The version blob is the lantern fixture so the reading-state structural
    floor (validate_reading_state) and the completion ending check both pass;
    only the access gate under test can cause a denial.
    """
    blob = json.loads(_LANTERN.read_text(encoding="utf-8"))
    async with sessions() as session:
        profile_b = await session.get(ChildProfile, seed.other_child_profile_id)
        assert profile_b is not None
        session.add(
            Storybook(
                id=story_id,
                family_id=profile_b.family_id,
                current_published_version=1,
                status="published",
                visibility=visibility,
            )
        )
        session.add(
            StorybookVersion(
                storybook_id=story_id,
                version=1,
                blob=blob,
                approved_by=seed.admin_user_id,
            )
        )
        if assign:
            session.add(
                StorybookAssignment(
                    child_profile_id=seed.child_profile_id,
                    storybook_id=story_id,
                )
            )
        await session.commit()
        return story_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_saves_progress_on_assigned_catalog_book(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """An assigned cross-family catalog book accepts save, read-back, and completion.

    The book is Family B's, so it fails a plain own-family filter; the
    assignment row is what grants access (E5 amendment parity with the read
    and rating paths fixed in Task 13).
    """
    story_id = await _add_cross_family_book(
        sessions, seed, "catalog-rs-assigned", visibility="catalog", assign=True
    )
    put = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{story_id}",
        json=_save_body(1, node="n_cave_fork", revision=0),
        headers=auth(seed.child_token),
    )
    assert put.status_code == 200, put.text
    got = await client.get(
        f"/api/v1/reading-state/{seed.child_profile_id}/{story_id}",
        headers=auth(seed.child_token),
    )
    assert got.status_code == 200, got.text
    assert got.json()["current_node"] == "n_cave_fork"
    done = await client.post(
        "/api/v1/completions",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": story_id,
            "version": 1,
            "ending_id": "e_treasure_found",
        },
        headers=auth(seed.child_token),
    )
    assert done.status_code == 200, done.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_cannot_save_progress_on_unassigned_catalog_book(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """An unassigned cross-family catalog book is 403 on save, read, and completion.

    Widening the family filter must not widen the assignment gate: without an
    assignment row for the calling profile, the catalog book stays blocked.
    """
    story_id = await _add_cross_family_book(
        sessions, seed, "catalog-rs-unassigned", visibility="catalog", assign=False
    )
    put = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{story_id}",
        json=_save_body(1, node="n_cave_fork", revision=0),
        headers=auth(seed.child_token),
    )
    assert put.status_code == 403, put.text
    got = await client.get(
        f"/api/v1/reading-state/{seed.child_profile_id}/{story_id}",
        headers=auth(seed.child_token),
    )
    assert got.status_code == 403, got.text
    done = await client.post(
        "/api/v1/completions",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": story_id,
            "version": 1,
            "ending_id": "e_treasure_found",
        },
        headers=auth(seed.child_token),
    )
    assert done.status_code == 403, done.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_cannot_save_progress_on_cross_family_private_book(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A cross-family visibility='family' book stays 403 (regression guard).

    An assignment row is added despite the book being private, so the denial
    is attributable to the family filter alone; the widened catalog gate must
    not accidentally widen the family-visibility case too.
    """
    story_id = await _add_cross_family_book(
        sessions, seed, "private-rs", visibility="family", assign=True
    )
    put = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{story_id}",
        json=_save_body(1, node="n_cave_fork", revision=0),
        headers=auth(seed.child_token),
    )
    assert put.status_code == 403, put.text
    got = await client.get(
        f"/api/v1/reading-state/{seed.child_profile_id}/{story_id}",
        headers=auth(seed.child_token),
    )
    assert got.status_code == 403, got.text
    done = await client.post(
        "/api/v1/completions",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": story_id,
            "version": 1,
            "ending_id": "e_treasure_found",
        },
        headers=auth(seed.child_token),
    )
    assert done.status_code == 403, done.text


# ---------------------------------------------------------------------------
# True-concurrency contracts: overlapping requests, not sequential staleness.
# The save handler takes SELECT ... FOR UPDATE on the row, so overlapping
# saves must serialize at the database; these tests race real requests with
# asyncio.gather (each request gets its own session and connection from the
# client fixture's per-request override).
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_divergent_saves_have_exactly_one_winner(
    client: AsyncClient, seed: Seed
) -> None:
    """Two overlapping saves from one base revision: one 200, one 409.

    The FOR UPDATE row lock serializes the read-modify-write, so the loser
    re-reads after the winner's commit, fails the revision check, and gets
    the winner's row back in the 409 body; a lost update (both 200, one
    overwritten) must be impossible.
    """
    url = f"/api/v1/reading-state/{seed.child_profile_id}/{seed.storybook_id}"
    create = await client.put(
        url,
        json=_save_body(seed.version, node="n_cave_fork", revision=0),
        headers=auth(seed.child_token),
    )
    assert create.status_code == 200, create.text

    left, right = await asyncio.gather(
        client.put(
            url,
            json=_save_body(seed.version, node="n_treasure", revision=1),
            headers=auth(seed.child_token),
        ),
        client.put(
            url,
            json=_save_body(seed.version, node="n_entrance", revision=1),
            headers=auth(seed.child_token),
        ),
    )
    statuses = sorted((left.status_code, right.status_code))
    assert statuses == [200, 409], (left.text, right.text)
    winner = left if left.status_code == 200 else right
    loser = right if winner is left else left

    assert winner.json()["state_revision"] == 2
    conflict = loser.json()
    assert conflict["current_row"]["state_revision"] == 2
    assert conflict["current_row"]["current_node"] == winner.json()["current_node"]

    final = await client.get(url, headers=auth(seed.child_token))
    assert final.status_code == 200
    assert final.json()["state_revision"] == 2
    assert final.json()["current_node"] == winner.json()["current_node"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_duplicate_event_applies_exactly_once(
    client: AsyncClient, seed: Seed
) -> None:
    """The same event delivered twice concurrently is applied exactly once.

    A flaky network can retry a save while the original is still in flight.
    The loser of the row lock must observe last_event_id already recorded
    and return the current row idempotently (200), never a spurious 409 and
    never a double-applied revision bump.
    """
    url = f"/api/v1/reading-state/{seed.child_profile_id}/{seed.storybook_id}"
    create = await client.put(
        url,
        json=_save_body(seed.version, node="n_cave_fork", revision=0),
        headers=auth(seed.child_token),
    )
    assert create.status_code == 200, create.text

    body = _save_body(seed.version, node="n_treasure", revision=1, event_id="evt-race")
    first, second = await asyncio.gather(
        client.put(url, json=body, headers=auth(seed.child_token)),
        client.put(url, json=body, headers=auth(seed.child_token)),
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["state_revision"] == 2
    assert second.json()["state_revision"] == 2

    final = await client.get(url, headers=auth(seed.child_token))
    assert final.json()["state_revision"] == 2
    assert final.json()["current_node"] == "n_treasure"
