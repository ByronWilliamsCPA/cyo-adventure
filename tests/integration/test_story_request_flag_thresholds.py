"""Threshold filtering on guardian story-request flag projections."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import StoryRequest
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _seed_request(
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    *,
    status: str,
    flags: dict[str, object],
) -> str:
    """Insert a story-request row with pre-set moderation flags; return its id."""
    async with sessions() as session:
        row = StoryRequest(
            family_id=seed.family_id,
            profile_id=seed.child_profile_id,
            request_text="a story about a brave turtle",
            status=status,
            age_band="10-13",
            moderation_flags=flags,
        )
        session.add(row)
        await session.commit()
        return str(row.id)


async def test_guardian_request_list_hides_advisory_flags(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """The 0.01-floor classifier advisories no longer reach the guardian list."""
    request_id = await _seed_request(
        sessions,
        seed,
        status="pending",
        flags={
            "blocked": False,
            "flags": [
                {
                    "category": "toxicity",
                    "verdict": "advisory",
                    "message": "graded advisory",
                },
                {"category": "safety", "verdict": "flag", "message": "needs review"},
            ],
        },
    )
    res = await client.get("/api/v1/story-requests", headers=auth(seed.guardian_token))
    assert res.status_code == 200
    target = next(r for r in res.json()["requests"] if r["id"] == request_id)
    categories = [f["category"] for f in target["moderation_flags"]]
    assert categories == ["safety"]


async def test_blocked_request_flags_still_surface(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """Bright-line BLOCK flags always surface (block >= flag >= default)."""
    request_id = await _seed_request(
        sessions,
        seed,
        status="blocked",
        flags={
            "blocked": True,
            "flags": [
                {
                    "category": "personal_information",
                    "verdict": "block",
                    "message": "names a real child",
                }
            ],
        },
    )
    res = await client.get("/api/v1/story-requests", headers=auth(seed.guardian_token))
    target = next(r for r in res.json()["requests"] if r["id"] == request_id)
    assert target["request_text"] is None  # existing hiding rule unchanged
    assert [f["verdict"] for f in target["moderation_flags"]] == ["block"]


async def test_admin_sees_all_flags_guardian_sees_filtered(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """Admins see every flag regardless of threshold; guardians stay filtered."""
    request_id = await _seed_request(
        sessions,
        seed,
        status="pending",
        flags={
            "blocked": False,
            "flags": [
                {
                    "category": "toxicity",
                    "verdict": "advisory",
                    "message": "graded advisory",
                },
                {"category": "safety", "verdict": "flag", "message": "needs review"},
            ],
        },
    )

    guardian_res = await client.get(
        "/api/v1/story-requests", headers=auth(seed.guardian_token)
    )
    assert guardian_res.status_code == 200
    guardian_target = next(
        r for r in guardian_res.json()["requests"] if r["id"] == request_id
    )
    guardian_categories = [f["category"] for f in guardian_target["moderation_flags"]]
    assert guardian_categories == ["safety"]

    admin_res = await client.get(
        "/api/v1/story-requests", headers=auth(seed.admin_token)
    )
    assert admin_res.status_code == 200
    admin_target = next(
        r for r in admin_res.json()["requests"] if r["id"] == request_id
    )
    admin_categories = {f["category"] for f in admin_target["moderation_flags"]}
    assert admin_categories == {"toxicity", "safety"}


def _all_keys(obj: object) -> set[str]:
    """Collect every dict key (lowercased) in a nested JSON structure."""
    keys: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            keys.add(str(key).lower())
            keys |= _all_keys(value)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _all_keys(item)
    return keys


async def test_kid_library_exposes_no_moderation_fields(
    client: AsyncClient, seed: Seed
) -> None:
    """Kid-facing library payloads carry no findings/flags/moderation keys.

    Assert on JSON keys, not raw response text: story titles or prose can
    legitimately contain words like "verdict", so a substring scan of the
    whole body would false-positive on clean content.
    """
    res = await client.get(
        "/api/v1/library",
        params={"profile_id": str(seed.child_profile_id)},
        headers=auth(seed.child_token),
    )
    assert res.status_code == 200
    keys = _all_keys(res.json())
    for needle in ("moderation", "finding", "verdict", "flag"):
        leaked = {key for key in keys if needle in key}
        assert not leaked, f"kid library leaked moderation keys: {leaked}"
