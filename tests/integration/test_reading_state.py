"""Integration tests for the library, reading-state, and completion endpoints."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import (
    ChildProfile,
    ReadingState,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
)
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    import uuid

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
    assert got.json()["state"]["current_node"] == "n_cave_fork"
    assert got.json()["state"]["state_revision"] == 1


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
async def test_reading_state_null_when_never_saved(
    client: AsyncClient, seed: Seed
) -> None:
    """Reading state that was never saved returns 200 with state: null.

    A first-time reader is a normal condition, not an error; a 404 here
    would surface as an uncatchable browser console error before
    application code can handle it.
    """
    resp = await client.get(
        f"/api/v1/reading-state/{seed.child_profile_id}/{seed.storybook_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"state": None}


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
async def test_completion_response_reports_is_new_and_counts(
    client: AsyncClient, seed: Seed
) -> None:
    """A first-time completion reports is_new=True and the right found/total (W0.3).

    The lantern fixture (03_tier2_lantern.json) declares `ending_count: 4`
    in its metadata and has four ending nodes; this profile's first
    completion should report found=1, total=4.
    """
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
    body = resp.json()
    assert body["is_new"] is True
    assert body["found"] == 1
    assert body["total"] == 4


@pytest.mark.integration
@pytest.mark.asyncio
async def test_completion_repeat_reports_is_new_false(
    client: AsyncClient, seed: Seed
) -> None:
    """Posting the same (profile, storybook, version, ending) twice: is_new flips.

    The second post hits the existing PK row (no new insert) but `found`
    still reports the same distinct-ending count, not an inflated one.
    """
    body_json = {
        "profile_id": str(seed.child_profile_id),
        "storybook_id": seed.storybook_id,
        "version": seed.version,
        "ending_id": "e_treasure_found",
    }
    first = await client.post(
        "/api/v1/completions", json=body_json, headers=auth(seed.child_token)
    )
    assert first.status_code == 200, first.text
    assert first.json()["is_new"] is True

    second = await client.post(
        "/api/v1/completions", json=body_json, headers=auth(seed.child_token)
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["is_new"] is False
    assert second_body["found"] == 1
    assert second_body["total"] == 4


@pytest.mark.integration
@pytest.mark.asyncio
async def test_completion_second_distinct_ending_increments_found(
    client: AsyncClient, seed: Seed
) -> None:
    """A second, distinct ending for the same book raises found to 2, not is_new-gated."""
    first = await client.post(
        "/api/v1/completions",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "version": seed.version,
            "ending_id": "e_treasure_found",
        },
        headers=auth(seed.child_token),
    )
    assert first.status_code == 200, first.text
    assert first.json()["found"] == 1

    second = await client.post(
        "/api/v1/completions",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "version": seed.version,
            "ending_id": "e_safe_exit",
        },
        headers=auth(seed.child_token),
    )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["is_new"] is True
    assert second_body["found"] == 2
    assert second_body["total"] == 4


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
    assert got.json()["state"]["current_node"] == "n_cave_fork"
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
# M1 (security-hardening-plan-2026-07.md, register UW-E01): the assignment
# gate applies to OWN-family books too, and a first (create) save/completion
# must cite the book's current, published, approved version. Before this fix,
# an own-family book always passed _load_readable_storybook, so these two
# predicates never ran at all for the common case (only the cross-family
# catalog arm above was covered).
# ---------------------------------------------------------------------------


async def _add_own_family_book(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    story_id: str,
    *,
    status: str,
    current_published_version: int | None,
    version: int,
    approved_by: uuid.UUID | None,
    assign: bool,
) -> str:
    """Insert a Family-A-owned book/version row with independently-set fields.

    Bypasses the real publish/assign services (``publishing/``,
    ``api/assignments.py``) so ``status``, ``current_published_version``, and
    ``approved_by`` can each be set independently of the others, isolating
    which single M1 predicate (assignment, or current/published/approved) a
    given test exercises.
    """
    blob = json.loads(_LANTERN.read_text(encoding="utf-8"))
    async with sessions() as session:
        session.add(
            Storybook(
                id=story_id,
                family_id=seed.family_id,
                current_published_version=current_published_version,
                status=status,
            )
        )
        session.add(
            StorybookVersion(
                storybook_id=story_id,
                version=version,
                blob=blob,
                approved_by=approved_by,
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
async def test_get_reading_state_unassigned_own_family_story_404(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """An own-family published story with no assignment row is 404 on GET.

    Regression guard for the M1 gap: before this fix, an own-family book
    always passed the family/visibility gate with no assignment check, so a
    child could read reading-state for any published story in their family.
    A ReadingState row is hand-inserted (bypassing PUT) so a pass here proves
    the gate itself blocks the read, not merely that no row happens to exist
    yet: without this, GET would 404 either way (no assignment gate, vs. no
    saved state), and the test would pass for the wrong reason.
    """
    story_id = await _add_own_family_book(
        sessions,
        seed,
        "own-family-rs-unassigned-get",
        status="published",
        current_published_version=1,
        version=1,
        approved_by=seed.admin_user_id,
        assign=False,
    )
    async with sessions() as session:
        session.add(
            ReadingState(
                child_profile_id=seed.child_profile_id,
                storybook_id=story_id,
                version=1,
                current_node="n_entrance",
            )
        )
        await session.commit()
    resp = await client.get(
        f"/api/v1/reading-state/{seed.child_profile_id}/{story_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_put_reading_state_unassigned_own_family_story_404(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """An own-family published story with no assignment row is 404 on PUT."""
    story_id = await _add_own_family_book(
        sessions,
        seed,
        "own-family-rs-unassigned-put",
        status="published",
        current_published_version=1,
        version=1,
        approved_by=seed.admin_user_id,
        assign=False,
    )
    resp = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{story_id}",
        json=_save_body(1, node="n_cave_fork", revision=0),
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_record_completion_unassigned_own_family_story_404(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """An own-family published story with no assignment row is 404 on completion."""
    story_id = await _add_own_family_book(
        sessions,
        seed,
        "own-family-rs-unassigned-completion",
        status="published",
        current_published_version=1,
        version=1,
        approved_by=seed.admin_user_id,
        assign=False,
    )
    resp = await client.post(
        "/api/v1/completions",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": story_id,
            "version": 1,
            "ending_id": "e_treasure_found",
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dual_role_adult_is_gated_on_own_family(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """M1: the admin exemption is capacity-scoped, so a dual-role parent is gated.

    ``seed.dual_token`` is a family-A adult holding role=guardian AND
    is_admin=True. Keying the M1 exemption on the raw ``is_admin`` capability
    would exempt exactly this principal, and only this principal: an
    admin-ONLY adult carries an empty ``profile_ids`` set and 403s at
    ``authorize_profile`` before reaching the gate. The gate keys on
    ``acting_role(book.family_id)`` instead, which stays GUARDIAN for an
    own-family target, so an unassigned own-family book is 404 for a
    dual-role adult exactly as it is for a plain guardian or a child.
    """
    story_id = await _add_own_family_book(
        sessions,
        seed,
        "own-family-rs-unassigned-dual",
        status="published",
        current_published_version=1,
        version=1,
        approved_by=seed.admin_user_id,
        assign=False,
    )
    resp = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{story_id}",
        json=_save_body(1, node="n_cave_fork", revision=0),
        headers=auth(seed.dual_token),
    )
    assert resp.status_code == 404, resp.text

    completion = await client.post(
        "/api/v1/completions",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": story_id,
            "version": 1,
            "ending_id": "e_treasure_found",
        },
        headers=auth(seed.dual_token),
    )
    assert completion.status_code == 404, completion.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_put_reading_state_create_rejects_non_current_version_404(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A first save citing a superseded (non-current) version is 404.

    ``current_published_version`` is 2 while the cited version row is 1: the
    book has moved on, so a brand-new pin to the stale version must be
    rejected, not silently accepted.
    """
    story_id = await _add_own_family_book(
        sessions,
        seed,
        "own-family-rs-noncurrent",
        status="published",
        current_published_version=2,
        version=1,
        approved_by=seed.admin_user_id,
        assign=True,
    )
    resp = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{story_id}",
        json=_save_body(1, node="n_cave_fork", revision=0),
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_put_reading_state_create_rejects_unapproved_version_404(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A first save citing an unapproved version is 404 even if it is current."""
    story_id = await _add_own_family_book(
        sessions,
        seed,
        "own-family-rs-unapproved",
        status="published",
        current_published_version=1,
        version=1,
        approved_by=None,
        assign=True,
    )
    resp = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{story_id}",
        json=_save_body(1, node="n_cave_fork", revision=0),
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_put_reading_state_create_rejects_non_published_book_404(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A first save against a non-published book is 404.

    The assignment row is hand-inserted (the real assign endpoint already
    rejects a non-published book; see test_non_published_story_400 in
    test_assignments_api.py), isolating the current/published/approved check
    under test from the assignment check.
    """
    story_id = await _add_own_family_book(
        sessions,
        seed,
        "own-family-rs-not-published",
        status="in_review",
        current_published_version=None,
        version=1,
        approved_by=seed.admin_user_id,
        assign=True,
    )
    resp = await client.put(
        f"/api/v1/reading-state/{seed.child_profile_id}/{story_id}",
        json=_save_body(1, node="n_cave_fork", revision=0),
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_put_reading_state_update_allows_since_superseded_version(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """An update to an already-pinned row keeps working after a republish.

    Regression guard for the create/update split: the create-path check
    above must not be applied on every save, or continued reading on a
    since-superseded version (a supported, existing scenario) would start
    404ing on the very next save after a republish.
    """
    story_id = await _add_own_family_book(
        sessions,
        seed,
        "own-family-rs-update-superseded",
        status="published",
        current_published_version=1,
        version=1,
        approved_by=seed.admin_user_id,
        assign=True,
    )
    url = f"/api/v1/reading-state/{seed.child_profile_id}/{story_id}"
    create = await client.put(
        url,
        json=_save_body(1, node="n_cave_fork", revision=0),
        headers=auth(seed.child_token),
    )
    assert create.status_code == 200, create.text

    # Republish: version 2 becomes current; the row stays pinned to version 1.
    async with sessions() as session:
        book = await session.get(Storybook, story_id)
        assert book is not None
        book.current_published_version = 2
        blob = json.loads(_LANTERN.read_text(encoding="utf-8"))
        session.add(
            StorybookVersion(
                storybook_id=story_id,
                version=2,
                blob=blob,
                approved_by=seed.admin_user_id,
            )
        )
        await session.commit()

    update = await client.put(
        url,
        json=_save_body(1, node="n_treasure", revision=1),
        headers=auth(seed.child_token),
    )
    assert update.status_code == 200, update.text
    assert update.json()["current_node"] == "n_treasure"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_record_completion_rejects_non_current_version_404(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A completion citing a superseded version is 404.

    Unlike reading-state, completions have no update path (each call is a
    fresh pin), so the current/published/approved check runs unconditionally
    here, not behind a create/update split.
    """
    story_id = await _add_own_family_book(
        sessions,
        seed,
        "own-family-completion-noncurrent",
        status="published",
        current_published_version=2,
        version=1,
        approved_by=seed.admin_user_id,
        assign=True,
    )
    resp = await client.post(
        "/api/v1/completions",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": story_id,
            "version": 1,
            "ending_id": "e_treasure_found",
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404, resp.text


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
    assert final.json()["state"]["state_revision"] == 2
    assert final.json()["state"]["current_node"] == winner.json()["current_node"]


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
    assert final.json()["state"]["state_revision"] == 2
    assert final.json()["state"]["current_node"] == "n_treasure"
