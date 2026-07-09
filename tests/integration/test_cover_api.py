"""Cover endpoints: admin gate, enqueue, config guard, status."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from .conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient

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
    client: AsyncClient, seed: Seed, monkeypatch: pytest.MonkeyPatch
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


async def test_missing_config_returns_400(
    client: AsyncClient, seed: Seed, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("cyo_adventure.api.covers.settings", _UNCONFIGURED)
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}/cover",
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 400
