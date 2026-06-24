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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_ratings_returns_profile_ratings(
    client: AsyncClient, seed: Seed
) -> None:
    """A recorded rating appears in the profile's rating list."""
    await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 5,
        },
        headers=auth(seed.child_token),
    )
    resp = await client.get(
        f"/api/v1/ratings/{seed.child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 200, resp.text
    ratings = resp.json()["ratings"]
    assert any(
        r["storybook_id"] == seed.storybook_id and r["value"] == 5 for r in ratings
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_ratings_other_profile_forbidden(
    client: AsyncClient, seed: Seed
) -> None:
    """A child cannot list another profile's ratings (403)."""
    resp = await client.get(
        f"/api/v1/ratings/{seed.other_child_profile_id}",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rating_below_range_rejected(client: AsyncClient, seed: Seed) -> None:
    """A value below 1 is rejected at the schema boundary (422)."""
    resp = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": seed.storybook_id,
            "value": 0,
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rating_unknown_storybook_is_404(client: AsyncClient, seed: Seed) -> None:
    """Rating a storybook that does not exist returns 404."""
    resp = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": str(seed.child_profile_id),
            "storybook_id": "does-not-exist",
            "value": 3,
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rating_invalid_profile_uuid_rejected(
    client: AsyncClient, seed: Seed
) -> None:
    """A non-UUID profile_id on POST is rejected by _parse_uuid (422)."""
    resp = await client.post(
        "/api/v1/ratings",
        json={
            "profile_id": "not-a-uuid",
            "storybook_id": seed.storybook_id,
            "value": 3,
        },
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_ratings_invalid_profile_uuid_rejected(
    client: AsyncClient, seed: Seed
) -> None:
    """A non-UUID profile_id on GET is rejected by _parse_uuid (422)."""
    resp = await client.get(
        "/api/v1/ratings/not-a-uuid",
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 422, resp.text
