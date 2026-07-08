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


async def test_guardian_put_and_delete_get_403(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """Non-admin callers are rejected before any write (PUT and DELETE); no
    row or audit entry is created.
    """
    put_res = await client.put(
        f"{_URL}/3-5",
        params={"category": "violence"},
        json={"min_verdict": "advisory", "min_score": None},
        headers=auth(seed.guardian_token),
    )
    assert put_res.status_code == 403
    delete_res = await client.delete(
        f"{_URL}/3-5",
        params={"category": "violence"},
        headers=auth(seed.guardian_token),
    )
    assert delete_res.status_code == 403
    async with AsyncSession(engine) as session:
        rows = (await session.scalars(select(ModerationThresholdAudit))).all()
    assert rows == []


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
        f"{_URL}/3-5",
        params={"category": "violence"},
        json={"min_verdict": "advisory", "min_score": 0.3},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200
    res = await client.put(
        f"{_URL}/3-5",
        params={"category": "violence"},
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
        f"{_URL}/3-5",
        params={"category": "violence"},
        json={"min_verdict": "advisory", "min_score": None},
        headers=auth(seed.admin_token),
    )
    res = await client.delete(
        f"{_URL}/3-5",
        params={"category": "violence"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200
    assert (await client.get(_URL, headers=auth(seed.admin_token))).json()["rows"] == []
    async with AsyncSession(engine) as session:
        audits = (await session.scalars(select(ModerationThresholdAudit))).all()
    assert audits[-1].action == "delete"


async def test_audit_rows_capture_changed_by_and_old_new_values(
    client: AsyncClient, seed: Seed, engine: AsyncEngine
) -> None:
    """Audit rows for both upsert and delete record changed_by plus the old/new
    verdict and score, not just the action.
    """
    res = await client.put(
        f"{_URL}/3-5",
        params={"category": "self-harm/intent"},
        json={"min_verdict": "flag", "min_score": 0.4},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200
    async with AsyncSession(engine) as session:
        audits = (await session.scalars(select(ModerationThresholdAudit))).all()
    assert len(audits) == 1
    upsert_audit = audits[0]
    assert upsert_audit.action == "upsert"
    assert upsert_audit.old_min_verdict is None
    assert upsert_audit.old_min_score is None
    assert upsert_audit.new_min_verdict == "flag"
    assert upsert_audit.new_min_score == 0.4
    assert upsert_audit.changed_by == seed.admin_user_id

    res = await client.delete(
        f"{_URL}/3-5",
        params={"category": "self-harm/intent"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200
    async with AsyncSession(engine) as session:
        audits = (await session.scalars(select(ModerationThresholdAudit))).all()
    assert len(audits) == 2
    delete_audit = next(a for a in audits if a.action == "delete")
    assert delete_audit.old_min_verdict == "flag"
    assert delete_audit.old_min_score == 0.4
    assert delete_audit.new_min_verdict is None
    assert delete_audit.new_min_score is None
    assert delete_audit.changed_by == seed.admin_user_id


async def test_delete_missing_row_404(client: AsyncClient, seed: Seed) -> None:
    """Deleting a non-existent override is a 404, not a silent no-op."""
    res = await client.delete(
        f"{_URL}/3-5",
        params={"category": "never-set"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 404


async def test_invalid_band_and_verdict_rejected(
    client: AsyncClient, seed: Seed
) -> None:
    """Unknown age band -> 422; 'pass'/'block-typo' min_verdict -> 422."""
    res = await client.put(
        f"{_URL}/4-6",
        params={"category": "violence"},
        json={"min_verdict": "advisory", "min_score": None},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422
    res = await client.put(
        f"{_URL}/3-5",
        params={"category": "violence"},
        json={"min_verdict": "pass", "min_score": None},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 422


async def test_slash_category_roundtrips(client: AsyncClient, seed: Seed) -> None:
    """Categories containing '/' (e.g. self-harm/instructions) round-trip.

    ``category`` travels as a QUERY parameter precisely because five known
    categories contain '/', which a path segment cannot carry (the decoded
    slash breaks route matching and 404s).
    """
    res = await client.put(
        f"{_URL}/3-5",
        params={"category": "self-harm/instructions"},
        json={"min_verdict": "advisory", "min_score": None},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 200
    rows = (await client.get(_URL, headers=auth(seed.admin_token))).json()["rows"]
    assert rows[0]["category"] == "self-harm/instructions"
