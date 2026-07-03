"""Integration tests for the profiles API (C4a-2).

List scoping follows the authorization matrix: a guardian sees every profile
in their own family, a child sees only their own, and nobody sees another
family's rows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_requires_authentication(client: AsyncClient) -> None:
    """GET /profiles without a bearer is a 401."""
    resp = await client.get("/api/v1/profiles")
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardian_lists_own_family_profiles(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian sees all of their family's profiles and nothing else."""
    resp = await client.get("/api/v1/profiles", headers=auth(seed.guardian_token))
    assert resp.status_code == 200, resp.text
    profiles = resp.json()["profiles"]
    assert [p["display_name"] for p in profiles] == ["Reader A"]
    row = profiles[0]
    assert row["id"] == str(seed.child_profile_id)
    assert row["age_band"] == "10-13"
    assert row["reading_level_cap"] == 99.0
    assert row["avatar"] is None
    assert row["tts_enabled"] is False
    assert "created_at" in row


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_lists_only_own_profile(client: AsyncClient, seed: Seed) -> None:
    """A child token resolves to exactly its own profile."""
    resp = await client.get("/api/v1/profiles", headers=auth(seed.child_token))
    assert resp.status_code == 200, resp.text
    profiles = resp.json()["profiles"]
    assert [p["id"] for p in profiles] == [str(seed.child_profile_id)]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_profileless_child_gets_empty_list(
    client: AsyncClient, seed: Seed
) -> None:
    """A child with no assigned profile gets an empty list, not an error."""
    del seed  # fixture seeds the child-noprofile user
    resp = await client.get("/api/v1/profiles", headers=auth("child-noprofile"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["profiles"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardian_creates_profile(client: AsyncClient, seed: Seed) -> None:
    """A guardian creates a profile; it is echoed back and then listed."""
    resp = await client.post(
        "/api/v1/profiles",
        json={"display_name": "  Nova  ", "age_band": "5-8", "avatar": "fox"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["display_name"] == "Nova"  # whitespace stripped
    assert body["age_band"] == "5-8"
    assert body["reading_level_cap"] == 99.0
    assert body["avatar"] == "fox"
    assert body["tts_enabled"] is False

    listed = await client.get("/api/v1/profiles", headers=auth(seed.guardian_token))
    names = [p["display_name"] for p in listed.json()["profiles"]]
    assert names == ["Reader A", "Nova"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_cannot_create_profile(client: AsyncClient, seed: Seed) -> None:
    """A child token is rejected with 403 before any write."""
    resp = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "5-8"},
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_rejects_unknown_age_band(client: AsyncClient, seed: Seed) -> None:
    """An age band outside the six-band vocabulary is a 422."""
    resp = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "4-6"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_rejects_unknown_fields(client: AsyncClient, seed: Seed) -> None:
    """extra=forbid rejects unmodeled body fields."""
    resp = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "5-8", "family_id": "x"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardian_updates_caps_and_clears_avatar(
    client: AsyncClient, seed: Seed
) -> None:
    """PATCH updates provided fields; explicit null clears the avatar."""
    guardian = auth(seed.guardian_token)
    created = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "5-8", "avatar": "fox"},
        headers=guardian,
    )
    pid = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/profiles/{pid}",
        json={"reading_level_cap": 4.5, "age_band": "8-11", "avatar": None},
        headers=guardian,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reading_level_cap"] == 4.5
    assert body["age_band"] == "8-11"
    assert body["avatar"] is None
    assert body["display_name"] == "Nova"  # untouched field survives


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_omitting_avatar_keeps_it(client: AsyncClient, seed: Seed) -> None:
    """A PATCH that omits avatar leaves the stored avatar unchanged."""
    guardian = auth(seed.guardian_token)
    created = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "5-8", "avatar": "owl"},
        headers=guardian,
    )
    pid = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/profiles/{pid}", json={"tts_enabled": True}, headers=guardian
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["avatar"] == "owl"
    assert resp.json()["tts_enabled"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardian_cannot_update_other_familys_profile(
    client: AsyncClient, seed: Seed
) -> None:
    """Cross-family PATCH is a 403 (authorize_profile), leaking nothing."""
    resp = await client.patch(
        f"/api/v1/profiles/{seed.other_child_profile_id}",
        json={"reading_level_cap": 1.0},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_cannot_update_profile(client: AsyncClient, seed: Seed) -> None:
    """A child may not change their own caps."""
    resp = await client.patch(
        f"/api/v1/profiles/{seed.child_profile_id}",
        json={"reading_level_cap": 99.0},
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_rejects_malformed_uuid(client: AsyncClient, seed: Seed) -> None:
    """A non-UUID path id is a 422 from parse_uuid."""
    resp = await client.patch(
        "/api/v1/profiles/not-a-uuid",
        json={"tts_enabled": True},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_ignores_explicit_null_on_non_avatar_fields(
    client: AsyncClient, seed: Seed
) -> None:
    """Explicit null on a non-avatar field is silently ignored (is not None gate)."""
    guardian = auth(seed.guardian_token)
    created = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "5-8"},
        headers=guardian,
    )
    pid = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/profiles/{pid}",
        json={"age_band": None},
        headers=guardian,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["age_band"] == "5-8"  # unchanged, null was ignored


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_rejects_unknown_fields(client: AsyncClient, seed: Seed) -> None:
    """extra=forbid rejects unmodeled body fields on PATCH too."""
    resp = await client.patch(
        f"/api/v1/profiles/{seed.child_profile_id}",
        json={"family_id": "x"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_requires_authentication(client: AsyncClient) -> None:
    """POST /profiles without a bearer is a 401."""
    resp = await client.post(
        "/api/v1/profiles", json={"display_name": "Nova", "age_band": "5-8"}
    )
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_requires_authentication(client: AsyncClient, seed: Seed) -> None:
    """PATCH /profiles/{id} without a bearer is a 401."""
    resp = await client.patch(
        f"/api/v1/profiles/{seed.child_profile_id}", json={"tts_enabled": True}
    )
    assert resp.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_cannot_create_profile(client: AsyncClient, seed: Seed) -> None:
    """An admin token is rejected with 403; profile writes are guardian-only."""
    resp = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "5-8"},
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_cannot_update_profile(client: AsyncClient, seed: Seed) -> None:
    """An admin token may not change caps either (guardian-only writes)."""
    resp = await client.patch(
        f"/api/v1/profiles/{seed.child_profile_id}",
        json={"reading_level_cap": 1.0},
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_admin_list_is_empty(client: AsyncClient, seed: Seed) -> None:
    """An admin resolves no profile set, so the list is empty, not an error."""
    del seed  # fixture seeds the admin-a user
    resp = await client.get("/api/v1/profiles", headers=auth("admin-a"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["profiles"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_rejects_unknown_avatar(client: AsyncClient, seed: Seed) -> None:
    """An avatar id outside the illustrated catalog is a 422 (closed vocabulary)."""
    resp = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "5-8", "avatar": "not-a-glyph"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_display_name_length_boundaries(
    client: AsyncClient, seed: Seed
) -> None:
    """Names of 1 and 120 chars pass; 121 chars and whitespace-only are 422."""
    guardian = auth(seed.guardian_token)
    ok_short = await client.post(
        "/api/v1/profiles",
        json={"display_name": "N", "age_band": "5-8"},
        headers=guardian,
    )
    assert ok_short.status_code == 201, ok_short.text
    ok_long = await client.post(
        "/api/v1/profiles",
        json={"display_name": "x" * 120, "age_band": "5-8"},
        headers=guardian,
    )
    assert ok_long.status_code == 201, ok_long.text
    too_long = await client.post(
        "/api/v1/profiles",
        json={"display_name": "x" * 121, "age_band": "5-8"},
        headers=guardian,
    )
    assert too_long.status_code == 422
    whitespace_only = await client.post(
        "/api/v1/profiles",
        json={"display_name": "   ", "age_band": "5-8"},
        headers=guardian,
    )
    assert whitespace_only.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_reading_cap_boundaries(client: AsyncClient, seed: Seed) -> None:
    """Caps of 0.0 and 99.0 pass; below 0 and above 99 are 422."""
    guardian = auth(seed.guardian_token)
    at_zero = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "5-8", "reading_level_cap": 0.0},
        headers=guardian,
    )
    assert at_zero.status_code == 201, at_zero.text
    assert at_zero.json()["reading_level_cap"] == 0.0
    at_max = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova2", "age_band": "5-8", "reading_level_cap": 99.0},
        headers=guardian,
    )
    assert at_max.status_code == 201, at_max.text
    below_zero = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova3", "age_band": "5-8", "reading_level_cap": -0.5},
        headers=guardian,
    )
    assert below_zero.status_code == 422
    above_max = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova4", "age_band": "5-8", "reading_level_cap": 99.5},
        headers=guardian,
    )
    assert above_max.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_rejects_unknown_age_band(client: AsyncClient, seed: Seed) -> None:
    """PATCH with an age band outside the vocabulary is a 422, like POST."""
    resp = await client.patch(
        f"/api/v1/profiles/{seed.child_profile_id}",
        json={"age_band": "4-6"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_display_name(client: AsyncClient, seed: Seed) -> None:
    """PATCH can rename a profile; whitespace is stripped like on create."""
    resp = await client.patch(
        f"/api/v1/profiles/{seed.child_profile_id}",
        json={"display_name": "  Reader A Prime  "},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["display_name"] == "Reader A Prime"
