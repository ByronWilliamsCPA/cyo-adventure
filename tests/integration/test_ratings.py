"""Integration tests for the rating endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rating_recorded(client: AsyncClient, seed: Seed) -> None:
    """A valid rating is stored and echoed back."""
    resp = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 4,
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["value"] == 4
    assert body["storybook_id"] == seed.storybook_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rating_is_upserted(client: AsyncClient, seed: Seed) -> None:
    """Re-rating the same book overwrites the prior value (no 409)."""
    first = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 2,
        },
        headers=auth(seed.child_token),
    )
    assert first.status_code == 200, first.text
    second = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 5,
        },
        headers=auth(seed.child_token),
    )
    assert second.status_code == 200, second.text
    assert second.json()["value"] == 5


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rating_out_of_range_rejected(client: AsyncClient, seed: Seed) -> None:
    """A value above 5 is rejected at the schema boundary (422)."""
    resp = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 6,
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rating_wrong_profile_forbidden(client: AsyncClient, seed: Seed) -> None:
    """A child cannot rate using a profile that is not theirs (403)."""
    resp = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.other_child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 3,
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rating_foreign_storybook_forbidden(
    client: AsyncClient, seed: Seed
) -> None:
    """A child in family B cannot rate a storybook owned by family A (403)."""
    # child-b owns this profile (authorize_profile passes); the storybook is
    # family A's, so authorize_family is what fires here.
    resp = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.other_child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 3,
        },
        headers=auth(seed.other_child_token),
    )
    assert resp.status_code == 403, resp.text
