"""Integration tests for the guardian storage/download view (G15 remainder).

Real Postgres, real HTTP client (mirrors test_device_grants.py's convention
for this sibling feature): proves the report/remove/list endpoints end to
end, including cross-family scoping and the title/profile-name projection.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cyo_adventure.db.models import ChildProfile, DeviceDownload, User
from tests.integration.conftest import Seed, auth, mint_device_token

if TYPE_CHECKING:
    import uuid

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_report_creates_a_row(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    resp = await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "device-1",
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 204, resp.text

    async with sessions() as s:
        row = await s.scalar(
            select(DeviceDownload).where(
                DeviceDownload.device_id == "device-1",
                DeviceDownload.child_profile_id == seed.child_profile_id,
                DeviceDownload.storybook_id == seed.storybook_id,
            )
        )
        assert row is not None
        assert row.family_id == seed.family_id


async def test_repeat_report_advances_last_confirmed_at_without_duplicating(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    body = {
        "device_id": "device-1",
        "profile_id": str(seed.child_profile_id),
        "storybook_id": seed.storybook_id,
    }
    first = await client.put(
        "/api/v1/device-downloads", json=body, headers=auth(seed.guardian_token)
    )
    assert first.status_code == 204, first.text
    second = await client.put(
        "/api/v1/device-downloads", json=body, headers=auth(seed.guardian_token)
    )
    assert second.status_code == 204, second.text

    async with sessions() as s:
        rows = (
            await s.scalars(
                select(DeviceDownload).where(
                    DeviceDownload.device_id == "device-1",
                    DeviceDownload.child_profile_id == seed.child_profile_id,
                    DeviceDownload.storybook_id == seed.storybook_id,
                )
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].updated_at >= rows[0].created_at


async def test_concurrent_reports_do_not_conflict(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """Two overlapping reports for the same key must not race an INSERT.

    A plain read-then-insert (check for an existing row, else insert) lets
    two concurrent requests both observe "no row yet" and both attempt the
    INSERT, raising a UNIQUE violation on
    ``uq_device_download_device_profile_book``. The endpoint upserts
    atomically instead, so both requests succeed and exactly one row exists.
    """
    body = {
        "device_id": "device-1",
        "profile_id": str(seed.child_profile_id),
        "storybook_id": seed.storybook_id,
    }
    responses = await asyncio.gather(
        client.put(
            "/api/v1/device-downloads", json=body, headers=auth(seed.child_token)
        ),
        client.put(
            "/api/v1/device-downloads", json=body, headers=auth(seed.child_token)
        ),
    )
    assert all(r.status_code == 204 for r in responses), [r.text for r in responses]

    async with sessions() as s:
        rows = (
            await s.scalars(
                select(DeviceDownload).where(
                    DeviceDownload.device_id == "device-1",
                    DeviceDownload.child_profile_id == seed.child_profile_id,
                    DeviceDownload.storybook_id == seed.storybook_id,
                )
            )
        ).all()
        assert len(rows) == 1


async def test_report_wrong_profile_is_403(client: AsyncClient, seed: Seed) -> None:
    resp = await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "device-1",
            "profile_id": str(seed.other_child_profile_id),
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403, resp.text


async def test_report_nonexistent_profile_is_403_via_ownership_check(
    client: AsyncClient, seed: Seed
) -> None:
    """A fabricated profile id is never in any real principal's accessible set.

    ``authorize_profile`` runs before the ``ChildProfile`` existence check
    (mirrors ``flags.py::create_flag``'s identical ordering), so a
    nonexistent id 403s rather than 404s: a guardian's/child's accessible
    profile set is always derived from real rows, so a made-up id can never
    be "theirs" in the first place. The 404 branch exists for a genuine race
    (the profile is deleted between token mint and this request) that a
    fabricated id cannot exercise at the HTTP level.
    """
    resp = await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "device-1",
            "profile_id": "00000000-0000-4000-8000-000000000000",
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.dual_token),
    )
    assert resp.status_code == 403, resp.text


async def test_remove_deletes_the_row(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "device-1",
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.child_token),
    )

    resp = await client.request(
        "DELETE",
        "/api/v1/device-downloads",
        params={"device_id": "device-1", "storybook_id": seed.storybook_id},
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 204, resp.text

    async with sessions() as s:
        row = await s.scalar(
            select(DeviceDownload).where(
                DeviceDownload.device_id == "device-1",
                DeviceDownload.storybook_id == seed.storybook_id,
            )
        )
        assert row is None


async def test_remove_rejects_device_principal(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A bare device-grant principal (paired, no profile picked) may not remove.

    Unlike the PUT/GET siblings, DELETE takes no profile_id, so
    authorize_profile cannot gate it; this pins the explicit Role.DEVICE
    check that closes the gap a bare device token would otherwise walk
    through to delete any download row in the family.
    """
    await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "device-1",
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.child_token),
    )
    device_token = await mint_device_token(client, seed.guardian_token)

    resp = await client.request(
        "DELETE",
        "/api/v1/device-downloads",
        params={"device_id": "device-1", "storybook_id": seed.storybook_id},
        headers=auth(device_token),
    )
    assert resp.status_code == 403, resp.text

    async with sessions() as s:
        row = await s.scalar(
            select(DeviceDownload).where(
                DeviceDownload.device_id == "device-1",
                DeviceDownload.storybook_id == seed.storybook_id,
            )
        )
        assert row is not None


async def test_remove_never_touches_another_familys_row(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "shared-device-id",
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.child_token),
    )

    # Family B removes the same device_id/storybook_id pair; family A's own
    # row (different family_id, enforced by the WHERE clause, not by the
    # device_id happening to differ) must survive.
    await client.request(
        "DELETE",
        "/api/v1/device-downloads",
        params={"device_id": "shared-device-id", "storybook_id": seed.storybook_id},
        headers=auth(seed.other_child_token),
    )

    async with sessions() as s:
        row = await s.scalar(
            select(DeviceDownload).where(
                DeviceDownload.device_id == "shared-device-id",
                DeviceDownload.child_profile_id == seed.child_profile_id,
                DeviceDownload.storybook_id == seed.storybook_id,
            )
        )
        assert row is not None


async def _seed_sibling_with_download(
    sessions: async_sessionmaker[AsyncSession], seed: Seed, device_id: str
) -> uuid.UUID:
    """Add a second Family A profile that has the seed book on ``device_id``.

    Both children share one physical device (the common tablet case), so
    their rows differ only by ``child_profile_id``. The download row is
    inserted directly rather than reported over HTTP because no principal in
    this test may report for a sibling; that is the very rule under test.

    Args:
        sessions: The integration session factory.
        seed: The seeded fixture data (supplies Family A and the book).
        device_id: The shared device both profiles cached the book on.

    Returns:
        uuid.UUID: The sibling profile's id.
    """
    async with sessions() as session:
        sibling = ChildProfile(
            family_id=seed.family_id, display_name="Reader A2", age_band="10-13"
        )
        session.add(sibling)
        await session.flush()
        session.add(
            User(
                family_id=seed.family_id,
                role="child",
                authn_subject="child-a2",
                child_profile_id=sibling.id,
            )
        )
        session.add(
            DeviceDownload(
                family_id=seed.family_id,
                child_profile_id=sibling.id,
                device_id=device_id,
                storybook_id=seed.storybook_id,
            )
        )
        await session.commit()
        return sibling.id


async def test_remove_does_not_touch_another_profiles_row_for_a_child_principal(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A child's eviction clears its own row only, not a sibling's.

    Family scoping alone would not be authorization here: every principal
    carries a ``family_id``, and the endpoint's only inputs are a
    ``device_id`` and a ``storybook_id``, neither secret within a family. A
    family-only WHERE clause would let any child delete a sibling's rows by
    naming them, so the DELETE additionally constrains to the principal's own
    profile set.
    """
    sibling_id = await _seed_sibling_with_download(sessions, seed, "shared-tablet")
    await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "shared-tablet",
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.child_token),
    )

    resp = await client.request(
        "DELETE",
        "/api/v1/device-downloads",
        params={"device_id": "shared-tablet", "storybook_id": seed.storybook_id},
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 204, resp.text

    async with sessions() as s:
        rows = (
            await s.scalars(
                select(DeviceDownload).where(
                    DeviceDownload.device_id == "shared-tablet",
                    DeviceDownload.storybook_id == seed.storybook_id,
                )
            )
        ).all()
        assert [row.child_profile_id for row in rows] == [sibling_id]


async def test_remove_by_a_guardian_clears_every_profile_on_the_device(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """The profile-set filter must not narrow the adult eviction path.

    ``downloadBudget.ts`` and ``revocation.ts`` evict by book id for the whole
    device at once, so an adult removal has to clear every profile's row. A
    guardian's accessible profile set is its whole family, which is what
    makes one WHERE clause serve both callers.
    """
    await _seed_sibling_with_download(sessions, seed, "shared-tablet")
    await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "shared-tablet",
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.child_token),
    )

    resp = await client.request(
        "DELETE",
        "/api/v1/device-downloads",
        params={"device_id": "shared-tablet", "storybook_id": seed.storybook_id},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 204, resp.text

    async with sessions() as s:
        rows = (
            await s.scalars(
                select(DeviceDownload).where(
                    DeviceDownload.device_id == "shared-tablet",
                    DeviceDownload.storybook_id == seed.storybook_id,
                )
            )
        ).all()
        assert list(rows) == []


async def test_report_unknown_book_is_404(client: AsyncClient, seed: Seed) -> None:
    """A bad storybook_id is a 404, not an unhandled FK violation.

    ``storybook_id`` is a client-supplied string carrying a real foreign key.
    Without an explicit existence check the INSERT raises a
    ``ForeignKeyViolation`` that no exception handler maps, so the caller
    gets a bare 500 where the sibling profile branch correctly gives a 404.
    """
    resp = await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "device-1",
            "profile_id": str(seed.child_profile_id),
            "storybook_id": "no-such-book",
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404, resp.text


async def test_list_returns_profile_name_and_book_title(
    client: AsyncClient, seed: Seed
) -> None:
    await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "device-1",
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.child_token),
    )

    resp = await client.get(
        "/api/v1/device-downloads", headers=auth(seed.guardian_token)
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1
    item = items[0]
    assert item["device_id"] == "device-1"
    assert item["profile_id"] == str(seed.child_profile_id)
    assert item["storybook_id"] == seed.storybook_id
    # Exact values, not truthiness: the projection's whole job is joining the
    # right profile row and the right published version's blob title. A
    # truthy check passes on the "Unknown" fallback the endpoint substitutes
    # when the profile join misses, which is precisely the bug this test
    # exists to catch.
    assert item["profile_name"] == "Reader A"
    assert item["storybook_title"] == "The Lantern Cave"
    assert item["downloaded_at"] is not None
    assert item["last_confirmed_at"] is not None


async def test_list_never_leaks_another_familys_rows(
    client: AsyncClient, seed: Seed
) -> None:
    await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "device-b",
            "profile_id": str(seed.other_child_profile_id),
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.other_child_token),
    )

    resp = await client.get(
        "/api/v1/device-downloads", headers=auth(seed.guardian_token)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test_list_rejects_child_principal(client: AsyncClient, seed: Seed) -> None:
    resp = await client.get("/api/v1/device-downloads", headers=auth(seed.child_token))
    assert resp.status_code == 403, resp.text


async def test_list_allows_admin(client: AsyncClient, seed: Seed) -> None:
    await client.put(
        "/api/v1/device-downloads",
        json={
            "device_id": "device-1",
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
        },
        headers=auth(seed.child_token),
    )
    resp = await client.get("/api/v1/device-downloads", headers=auth(seed.admin_token))
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1
