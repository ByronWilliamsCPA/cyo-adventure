"""Cover endpoints: admin gate, enqueue, config guard, status."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import StorybookVersion

from .conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_CONFIGURED = SimpleNamespace(
    gemini_api_key="g",
    supabase_service_key="svc",
    supabase_url="https://p.supabase.co",
)
_UNCONFIGURED = SimpleNamespace(
    gemini_api_key=None,
    supabase_service_key="svc",
    supabase_url="https://p.supabase.co",
)
_MISSING_URL = SimpleNamespace(
    gemini_api_key="g",
    supabase_service_key="svc",
    supabase_url=None,
)


async def test_non_admin_forbidden(
    client: AsyncClient, seed: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("cyo_adventure.api.covers.settings", _CONFIGURED)
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/cover",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 403


async def test_admin_enqueues(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("cyo_adventure.api.covers.settings", _CONFIGURED)
    monkeypatch.setattr(
        "cyo_adventure.api.covers.enqueue_cover", lambda *a, **k: "job-1"
    )
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/cover",
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["cover_status"] == "generating"

    # The response body alone is not proof the console's poll loop will see
    # "generating" on its first read: without a persisted commit, the row
    # stays at its prior status until an RQ worker eventually dequeues the
    # job (10-30s later on a busy queue), so the 2s poll breaks the loop
    # immediately. Re-fetch through a fresh session to prove the write is
    # actually durable, not just reflected in the in-request response.
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row is not None
        assert row.cover_status == "generating"


@pytest.mark.parametrize("settings_ns", [_UNCONFIGURED, _MISSING_URL])
async def test_missing_config_returns_400(
    client: AsyncClient,
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
    settings_ns: SimpleNamespace,
) -> None:
    monkeypatch.setattr("cyo_adventure.api.covers.settings", settings_ns)
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/cover",
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 400
