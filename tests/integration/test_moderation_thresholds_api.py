"""Admin CRUD for moderation thresholds: auth, upsert, delete, audit."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.db.models import ModerationThresholdAudit
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_URL = "/api/v1/admin/moderation-thresholds"


async def test_guardian_gets_403(client: AsyncClient, seed: Seed) -> None:
    """Non-admin callers are rejected before any read."""
    res = await client.get(_URL, headers=auth(seed.guardian_token))
    assert res.status_code == 403


async def test_list_returns_defaults_and_rows(client: AsyncClient, seed: Seed) -> None:
    """The list view exposes the code default and known categories."""
    res = await client.get(_URL, headers=auth(seed.admin_token))
    assert res.status_code == 200
    body = res.json()
    assert body["default_min_verdict"] == "flag"
    assert body["default_min_score"] is None
    assert "toxicity" in body["known_categories"]
    assert body["rows"] == []


async def test_upsert_creates_then_updates_with_audit(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """PUT creates a row, a second PUT updates it, both write audit rows."""
    res = await client.put(
        f"{_URL}/3-5/violence",
        json={"min_verdict": "advisory", "min_score": 0.3},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200
    res = await client.put(
        f"{_URL}/3-5/violence",
        json={"min_verdict": "advisory", "min_score": 0.5},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200
    listed = await client.get(_URL, headers=auth(seed.admin_token))
    rows = listed.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["min_score"] == 0.5
    async with AsyncSession(engine) as session:
        audits = (await session.scalars(select(ModerationThresholdAudit))).all()
    assert [a.action for a in audits] == ["upsert", "upsert"]
    assert audits[1].old_min_score == 0.3
    assert audits[1].new_min_score == 0.5


async def test_delete_removes_row_with_audit(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """DELETE removes the override (falling back to default) and audits it."""
    await client.put(
        f"{_URL}/3-5/violence",
        json={"min_verdict": "advisory", "min_score": None},
        headers=auth(seed.admin_token),
    )
    res = await client.delete(f"{_URL}/3-5/violence", headers=auth(seed.admin_token))
    assert res.status_code == 200
    assert (await client.get(_URL, headers=auth(seed.admin_token))).json()["rows"] == []
    async with AsyncSession(engine) as session:
        audits = (await session.scalars(select(ModerationThresholdAudit))).all()
    assert audits[-1].action == "delete"


async def test_delete_missing_row_404(client: AsyncClient, seed: Seed) -> None:
    """Deleting a non-existent override is a 404, not a silent no-op."""
    res = await client.delete(f"{_URL}/3-5/never-set", headers=auth(seed.admin_token))
    assert res.status_code == 404


async def test_invalid_band_and_verdict_rejected(
    client: AsyncClient, seed: Seed
) -> None:
    """Unknown age band -> 422; 'pass'/'block-typo' min_verdict -> 422."""
    res = await client.put(
        f"{_URL}/4-6/violence",
        json={"min_verdict": "advisory", "min_score": None},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422
    res = await client.put(
        f"{_URL}/3-5/violence",
        json={"min_verdict": "pass", "min_score": None},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422
