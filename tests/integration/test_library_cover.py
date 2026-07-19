"""list_library surfaces a fresh presigned cover URL, never the stored column.

Covers are private-by-default in R2 (Phase 1d): the API never returns the
stored ``cover_image_url`` audit value directly, only a short-lived signed
GET URL generated on read from ``(storybook_id, version)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from cyo_adventure.core.config import settings
from cyo_adventure.db.models import StorybookVersion
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_cover_url_present_when_ready(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ready cover surfaces a freshly presigned URL, not the stored column."""
    monkeypatch.setattr(settings, "r2_account_id", "acct123")
    monkeypatch.setattr(settings, "r2_access_key_id", "AKIDEXAMPLE")
    monkeypatch.setattr(settings, "r2_secret_access_key", "secret")
    monkeypatch.setattr(settings, "r2_bucket", "covers")
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row is not None
        # Deliberately NOT the URL the API should return, to prove the read
        # path never trusts this stored column.
        row.cover_image_url = "https://stale.example/should-not-be-served.webp"
        row.cover_status = "ready"
        await s.commit()

    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = "https://r2.example/signed.webp"
    with patch("cyo_adventure.covers.storage.boto3.client", return_value=mock_client):
        resp = await client.get(
            f"/api/v1/library?profile_id={seed.child_profile_id}",
            headers=auth(seed.child_token),
        )
    assert resp.status_code == 200
    story = next(
        item for item in resp.json()["stories"] if item["id"] == seed.storybook_id
    )
    assert story["cover_url"] == "https://r2.example/signed.webp"
    mock_client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={
            "Bucket": "covers",
            "Key": f"{seed.storybook_id}/{seed.version}.webp",
        },
        ExpiresIn=3600,
    )


async def test_cover_url_null_by_default(
    client: AsyncClient,
    seed: Seed,
) -> None:
    """A story with no cover generated yet shows a null cover_url."""
    resp = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200
    story = next(
        item for item in resp.json()["stories"] if item["id"] == seed.storybook_id
    )
    assert story["cover_url"] is None


async def test_cover_url_null_when_ready_but_r2_unconfigured(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A ready cover degrades to a null cover_url, not a 500, when R2 is unconfigured."""
    async with sessions() as s:
        row = await s.get(StorybookVersion, (seed.storybook_id, seed.version))
        assert row is not None
        row.cover_status = "ready"
        await s.commit()

    resp = await client.get(
        f"/api/v1/library?profile_id={seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200
    story = next(
        item for item in resp.json()["stories"] if item["id"] == seed.storybook_id
    )
    assert story["cover_url"] is None
