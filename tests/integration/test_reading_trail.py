"""Reading-trail ingest, scoping, erasure-adjacent, RLS, purge, and report tests.

Runs against a real Postgres (testcontainers). The HTTP tests use the shared
``seed`` fixture: family A's child (``child-a``) is assigned the lantern story
(``s_lantern_cave`` v1); family B's child (``child-b``) is not. The RLS and
purge tests build a fully migrated sibling database, because policies and the
purge function live in ``supabase/migrations`` and not in ``Base.metadata``.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from cyo_adventure.api import reading as reading_api
from cyo_adventure.core.config import settings
from cyo_adventure.core.database import apply_family_rls_context
from cyo_adventure.db.models import (
    ChildProfile,
    Family,
    ReadingTrail,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
    User,
)
from tests.integration._migration_utils import migrate_and_connect_as
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.integration]

_ROOT = Path(__file__).resolve().parents[2]


def _s(
    seq: int, kind: str, node: str, choice: str | None = None, t: int = 0
) -> dict[str, object]:
    step: dict[str, object] = {
        "seq": seq,
        "kind": kind,
        "node_id": node,
        "elapsed_s": t,
    }
    if choice is not None:
        step["choice_id"] = choice
    return step


_FINISHED = [
    _s(0, "start", "n_open"),
    _s(1, "auto", "n_open", "c_n_open", 4),
    _s(2, "choice", "n_entrance", "c_take_lantern", 30),
    _s(3, "choice", "n_cave_fork", "c_dark_passage", 60),
    _s(4, "end", "n_treasure", None, 61),
]


@pytest.fixture
def capture_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch reading-trail capture on for one test."""
    monkeypatch.setattr(settings, "reading_trail_enabled", True)


def _url(seed: Seed, profile: uuid.UUID | None = None, book: str | None = None) -> str:
    return (
        f"/api/v1/reading-trail/{profile or seed.child_profile_id}/"
        f"{book or seed.storybook_id}"
    )


def _batch(
    seed: Seed, steps: list[dict[str, object]], read_id: str | None = None
) -> dict[str, object]:
    return {
        "read_id": read_id or str(uuid.uuid4()),
        "version": seed.version,
        "steps": steps,
    }


async def _trail_count(sessions: async_sessionmaker[AsyncSession]) -> int:
    async with sessions() as s:
        return int(await s.scalar(select(func.count()).select_from(ReadingTrail)) or 0)


async def _add_story(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    story_id: str,
    *,
    assign: bool,
) -> None:
    """Add a second published, approved story to family A (optionally assigned)."""
    async with sessions() as s:
        base = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert base is not None
        blob = {**base.blob, "id": story_id}
        s.add(
            Storybook(
                id=story_id,
                family_id=seed.family_id,
                current_published_version=1,
                status="published",
            )
        )
        s.add(
            StorybookVersion(
                storybook_id=story_id,
                version=1,
                blob=blob,
                approved_by=seed.admin_user_id,
                published_at=datetime.now(UTC),
            )
        )
        if assign:
            s.add(
                StorybookAssignment(
                    child_profile_id=seed.child_profile_id, storybook_id=story_id
                )
            )
        await s.commit()


@pytest.mark.asyncio
@pytest.mark.usefixtures("capture_on")
async def test_ingest_stores_steps_and_ending(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A child's batch is stored whole, with the server-derived ending."""
    read_id = str(uuid.uuid4())
    resp = await client.post(
        _url(seed),
        json=_batch(seed, _FINISHED, read_id),
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"recorded": True, "stored_steps": 5}
    async with sessions() as s:
        row = await s.get(ReadingTrail, uuid.UUID(read_id))
    assert row is not None
    assert row.family_id == seed.family_id
    assert row.child_profile_id == seed.child_profile_id
    assert row.started_on == datetime.now(UTC).date()
    assert row.ending_id == "e_treasure_found"
    assert row.step_count == 5
    assert [step["kind"] for step in row.steps] == [
        "start",
        "auto",
        "choice",
        "choice",
        "end",
    ]
    # Exactly the minimal shape: no wall clock, no device, no free text.
    assert all(
        set(step) == {"seq", "kind", "node_id", "choice_id", "elapsed_s"}
        for step in row.steps
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("capture_on")
async def test_replaying_the_opening_batch_is_a_no_op(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """The same batch twice stores one read with the same steps."""
    body = _batch(seed, _FINISHED)
    first = await client.post(_url(seed), json=body, headers=auth(seed.child_token))
    second = await client.post(_url(seed), json=body, headers=auth(seed.child_token))
    assert first.json() == second.json() == {"recorded": True, "stored_steps": 5}
    async with sessions() as s:
        rows = (await s.scalars(select(ReadingTrail))).all()
    assert len(rows) == 1
    assert rows[0].step_count == 5


@pytest.mark.asyncio
@pytest.mark.usefixtures("capture_on")
async def test_overlapping_batches_merge_without_loss(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """Overlapping and concurrent batches for one read union by seq."""
    read_id = str(uuid.uuid4())
    opening = await client.post(
        _url(seed),
        json=_batch(seed, _FINISHED[:2], read_id),
        headers=auth(seed.child_token),
    )
    assert opening.status_code == 200, opening.text
    # Two batches racing on the same row: the row lock serializes them.
    results = await asyncio.gather(
        client.post(
            _url(seed),
            json=_batch(seed, _FINISHED[1:4], read_id),
            headers=auth(seed.child_token),
        ),
        client.post(
            _url(seed),
            json=_batch(seed, _FINISHED[3:], read_id),
            headers=auth(seed.child_token),
        ),
    )
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    async with sessions() as s:
        row = await s.get(ReadingTrail, uuid.UUID(read_id))
    assert row is not None
    assert [step["seq"] for step in row.steps] == [0, 1, 2, 3, 4]
    assert row.ending_id == "e_treasure_found"


@pytest.mark.asyncio
async def test_disabled_flag_stores_nothing(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With capture off (the default) a valid batch stores no row at all."""
    monkeypatch.setattr(settings, "reading_trail_enabled", False)
    resp = await client.post(
        _url(seed), json=_batch(seed, _FINISHED), headers=auth(seed.child_token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"recorded": False, "stored_steps": 0}
    assert await _trail_count(sessions) == 0


@pytest.mark.asyncio
async def test_disabled_flag_still_authorizes(client: AsyncClient, seed: Seed) -> None:
    """The flag is read after authorization, so it is not a profile oracle."""
    resp = await client.post(
        _url(seed), json=_batch(seed, _FINISHED), headers=auth(seed.other_child_token)
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
@pytest.mark.usefixtures("capture_on")
async def test_other_family_child_cannot_write_trail(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """Another family's child can neither write A's trail nor trail A's book."""
    as_other_for_a = await client.post(
        _url(seed), json=_batch(seed, _FINISHED), headers=auth(seed.other_child_token)
    )
    assert as_other_for_a.status_code == 403, as_other_for_a.text
    own_profile_foreign_book = await client.post(
        _url(seed, profile=seed.other_child_profile_id),
        json=_batch(seed, _FINISHED),
        headers=auth(seed.other_child_token),
    )
    assert own_profile_foreign_book.status_code == 403, own_profile_foreign_book.text
    assert await _trail_count(sessions) == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("capture_on")
async def test_unauthenticated_request_rejected(
    client: AsyncClient, seed: Seed
) -> None:
    """No bearer, no write."""
    resp = await client.post(_url(seed), json=_batch(seed, _FINISHED))
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
@pytest.mark.usefixtures("capture_on")
async def test_unassigned_story_trail_rejected(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """An own-family story the child was not assigned is 404, like reading state."""
    await _add_story(sessions, seed, "s_unassigned", assign=False)
    resp = await client.post(
        _url(seed, book="s_unassigned"),
        json=_batch(seed, _FINISHED),
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404, resp.text
    assert await _trail_count(sessions) == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("capture_on")
async def test_unapproved_version_rejected(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A version that was never approved, or does not exist, is 404."""
    async with sessions() as s:
        base = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert base is not None
        s.add(
            StorybookVersion(
                storybook_id=seed.storybook_id, version=2, blob=dict(base.blob)
            )
        )
        await s.commit()
    for version in (2, 9):
        body = _batch(seed, _FINISHED)
        body["version"] = version
        resp = await client.post(_url(seed), json=body, headers=auth(seed.child_token))
        assert resp.status_code == 404, resp.text
    assert await _trail_count(sessions) == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("capture_on")
@pytest.mark.parametrize(
    "bad_step",
    [
        _s(1, "back", "n_not_in_this_book"),
        _s(1, "choice", "n_entrance", "c_not_in_this_book"),
        _s(1, "choice", "n_cave_fork", "c_take_lantern"),
        _s(1, "auto", "n_entrance", "c_take_lantern"),
        _s(1, "end", "n_entrance"),
    ],
)
async def test_unknown_node_rejected(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    bad_step: dict[str, object],
) -> None:
    """One step inconsistent with the version rejects the whole batch, unstored."""
    resp = await client.post(
        _url(seed),
        json=_batch(seed, [_s(0, "start", "n_open"), bad_step]),
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 422, resp.text
    # The response never echoes the submitted identifier back.
    assert "not_in_this_book" not in resp.text
    assert await _trail_count(sessions) == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("capture_on")
async def test_read_id_bound_to_another_profile_rejected(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A read id already bound to one read cannot be extended for another book."""
    await _add_story(sessions, seed, "s_second", assign=True)
    read_id = str(uuid.uuid4())
    first = await client.post(
        _url(seed),
        json=_batch(seed, _FINISHED[:2], read_id),
        headers=auth(seed.child_token),
    )
    assert first.status_code == 200, first.text
    reused = await client.post(
        _url(seed, book="s_second"),
        json=_batch(seed, _FINISHED[:2], read_id),
        headers=auth(seed.child_token),
    )
    assert reused.status_code == 422, reused.text
    async with sessions() as s:
        row = await s.get(ReadingTrail, uuid.UUID(read_id))
    assert row is not None
    assert row.storybook_id == seed.storybook_id


@pytest.mark.asyncio
@pytest.mark.usefixtures("capture_on")
async def test_daily_read_cap_enforced(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A profile cannot open more than the daily cap of new reads."""
    monkeypatch.setattr(reading_api, "READING_TRAIL_MAX_READS_PER_DAY", 2)
    statuses = [
        (
            await client.post(
                _url(seed),
                json=_batch(seed, _FINISHED[:1]),
                headers=auth(seed.child_token),
            )
        ).status_code
        for _ in range(3)
    ]
    assert statuses == [200, 200, 422]
    assert await _trail_count(sessions) == 2


@pytest.mark.asyncio
@pytest.mark.usefixtures("capture_on")
async def test_there_is_no_read_back_route(client: AsyncClient, seed: Seed) -> None:
    """Nobody, a child included, can read a trail back over the API."""
    resp = await client.get(_url(seed), headers=auth(seed.child_token))
    assert resp.status_code == 405, resp.text


@pytest.mark.asyncio
@pytest.mark.usefixtures("capture_on")
async def test_family_export_includes_reading_trails(
    client: AsyncClient, seed: Seed
) -> None:
    """The guardian's access-right export carries each read, steps included."""
    read_id = str(uuid.uuid4())
    await client.post(
        _url(seed),
        json=_batch(seed, _FINISHED, read_id),
        headers=auth(seed.child_token),
    )
    resp = await client.get("/api/v1/me/export", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    profile = next(
        p for p in resp.json()["profiles"] if p["id"] == str(seed.child_profile_id)
    )
    (trail,) = profile["reading_trails"]
    assert trail["read_id"] == read_id
    assert trail["ending_id"] == "e_treasure_found"
    assert len(trail["steps"]) == 5


@pytest.mark.asyncio
@pytest.mark.usefixtures("capture_on")
async def test_report_script_prints_aggregates_without_identifiers(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    pg_url: str,
) -> None:
    """The owner script reads seeded trails and names nobody unless asked."""
    await client.post(
        _url(seed), json=_batch(seed, _FINISHED), headers=auth(seed.child_token)
    )
    abandoned = [
        _s(0, "start", "n_open"),
        _s(1, "auto", "n_open", "c_n_open", 4),
        _s(2, "choice", "n_entrance", "c_take_lantern", 12),
        _s(3, "back", "n_entrance", None, 30),
        _s(4, "choice", "n_entrance", "c_ignore_lantern", 33),
        _s(5, "leave", "n_cave_fork", None, 153),
    ]
    await client.post(
        _url(seed), json=_batch(seed, abandoned), headers=auth(seed.child_token)
    )
    script = _ROOT / "scripts" / "report_reading_trail.py"
    env = {**os.environ, "READING_TRAIL_REPORT_DATABASE_URL": pg_url}

    def _run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *args],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

    plain = await asyncio.to_thread(_run)
    assert plain.returncode == 0, plain.stderr
    out = plain.stdout
    assert "Reads started: 2   resumed sessions: 0   finished: 1" in out
    assert "e_treasure_found" in out
    assert "n_cave_fork  (left 1, restarted 0, median time on node 2.0 min)" in out
    assert "n_entrance  (rewinds back to here: 1)" in out
    assert "Reader A" not in out
    assert str(seed.child_profile_id) not in out
    assert str(seed.family_id) not in out
    assert pg_url not in out
    assert pg_url not in plain.stderr
    by_profile = await asyncio.to_thread(_run, "--by-profile")
    assert by_profile.returncode == 0, by_profile.stderr
    assert "Reader A: 2 / 1" in by_profile.stdout


# --- Migrated-database tests: RLS as cyo_api, and the retention purge ---


async def _seed_two_families(admin_url: str) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Seed two families, each with a profile and a trail on a shared version.

    Returns:
        tuple: ``(family_a, family_b, profile_b_id)``.
    """
    engine = create_async_engine(admin_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    family_a, family_b = uuid.uuid4(), uuid.uuid4()
    try:
        async with sessions() as s:
            s.add_all([Family(id=family_a, name="A"), Family(id=family_b, name="B")])
            await s.flush()
            admin = User(
                family_id=family_a,
                role="admin",
                is_admin=True,
                authn_subject="rt-admin",
            )
            s.add(admin)
            profile_a = ChildProfile(
                family_id=family_a, display_name="RA", age_band="10-13"
            )
            profile_b = ChildProfile(
                family_id=family_b, display_name="RB", age_band="10-13"
            )
            s.add_all([profile_a, profile_b])
            await s.flush()
            s.add(
                Storybook(
                    id="s_rt",
                    family_id=family_a,
                    status="published",
                    current_published_version=1,
                )
            )
            await s.flush()
            s.add(
                StorybookVersion(
                    storybook_id="s_rt",
                    version=1,
                    blob={"nodes": []},
                    approved_by=admin.id,
                )
            )
            await s.flush()
            today = datetime.now(UTC).date()
            for profile, family, started in (
                (profile_a, family_a, today),
                (profile_b, family_b, today),
                (profile_a, family_a, today - timedelta(days=31)),
                (profile_a, family_a, today - timedelta(days=30)),
            ):
                s.add(
                    ReadingTrail(
                        id=uuid.uuid4(),
                        child_profile_id=profile.id,
                        family_id=family,
                        storybook_id="s_rt",
                        version=1,
                        started_on=started,
                        steps=[],
                        step_count=0,
                    )
                )
            await s.commit()
            profile_b_id = profile_b.id
    finally:
        await engine.dispose()
    return family_a, family_b, profile_b_id


@pytest.mark.asyncio
async def test_rls_scopes_reading_trail_to_caller_family(pg_url: str) -> None:
    """As cyo_api: no context sees nothing; family A sees only A's trails."""
    admin_url, role_url = await migrate_and_connect_as(
        pg_url, "rls_reading_trail", "cyo_api"
    )
    family_a, family_b, profile_b = await _seed_two_families(admin_url)
    engine = create_async_engine(role_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as s:
            unset = (
                await s.execute(text("SELECT count(*) FROM reading_trail"))
            ).scalar_one()
        assert unset == 0
        async with sessions() as s:
            await apply_family_rls_context(s, family_id=family_a, is_admin=False)
            visible = (
                (await s.execute(text("SELECT family_id FROM reading_trail")))
                .scalars()
                .all()
            )
            assert visible
            assert {str(fid) for fid in visible} == {str(family_a)}
            # USING: family B's row is invisible to an UPDATE as well as a SELECT.
            updated = (
                await s.execute(
                    text(
                        "UPDATE reading_trail SET step_count = 1 WHERE family_id = :fb"
                    ).bindparams(fb=family_b)
                )
            ).rowcount
            assert updated == 0
        async with sessions() as s:
            await apply_family_rls_context(s, family_id=family_a, is_admin=False)
            # WITH CHECK: family A's context cannot insert a family B row.
            with pytest.raises(DBAPIError, match="row-level security"):
                await s.execute(
                    text(
                        "INSERT INTO reading_trail (id, child_profile_id, family_id, "
                        "storybook_id, version, started_on, steps) VALUES (:id, "
                        ":pid, :fb, 's_rt', 1, CURRENT_DATE, '[]'::jsonb)"
                    ).bindparams(id=uuid.uuid4(), pid=profile_b, fb=family_b)
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_purge_function_deletes_only_expired_trails(pg_url: str) -> None:
    """The migrated purge removes rows older than 30 days, no exemptions."""
    admin_url, role_url = await migrate_and_connect_as(
        pg_url, "purge_reading_trail", "cyo_api"
    )
    await _seed_two_families(admin_url)
    engine = create_async_engine(admin_url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            removed = (
                await conn.execute(
                    text('SELECT "public"."purge_expired_reading_trails"(30)')
                )
            ).scalar_one()
            remaining = (
                await conn.execute(text("SELECT min(started_on) FROM reading_trail"))
            ).scalar_one()
        # Only the 31-day-old row goes; the 30-day-old row is inside the window.
        assert removed == 1
        assert remaining == datetime.now(UTC).date() - timedelta(days=30)
    finally:
        await engine.dispose()
    # The application role may not invoke the purge itself.
    api_engine = create_async_engine(role_url, poolclass=NullPool)
    try:
        async with api_engine.connect() as conn:
            with pytest.raises(DBAPIError, match="permission denied"):
                await conn.execute(
                    text('SELECT "public"."purge_expired_reading_trails"(1)')
                )
    finally:
        await api_engine.dispose()


def test_purge_job_schedules_the_documented_window() -> None:
    """Guard the documented 30-day constant in the migration against drift."""
    migration = (
        _ROOT / "supabase" / "migrations" / "20261120120000_add_reading_trail.sql"
    ).read_text(encoding="utf-8")
    assert '"public"."purge_expired_reading_trails"(30)' in migration
