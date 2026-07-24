"""Integration tests for admin child-profile management across families (WS-J).

Exercises ``/api/v1/admin/profiles``: the 403 gate, cross-family create, the
PIN write-only contract, and the deactivation effects on the guardian-scoped
listing and the child-session mint.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from .conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_PROFILES = "/api/v1/admin/profiles"


async def test_guardian_gets_403(client: AsyncClient, seed: Seed) -> None:
    """A non-admin guardian is refused list/create/update (403)."""
    list_resp = await client.get(_PROFILES, headers=auth(seed.guardian_token))
    assert list_resp.status_code == 403

    create_resp = await client.post(
        _PROFILES,
        headers=auth(seed.guardian_token),
        json={
            "family_id": str(seed.family_id),
            "display_name": "New Kid",
            "age_band": "5-8",
        },
    )
    assert create_resp.status_code == 403


async def test_create_and_list_profile_in_any_family(
    client: AsyncClient, seed: Seed
) -> None:
    """An admin can create a profile in any family, PIN never serialized."""
    resp = await client.post(
        _PROFILES,
        headers=auth(seed.admin_token),
        json={
            "family_id": str(seed.family_id),
            "display_name": "Admin-Made Kid",
            "age_band": "5-8",
            "reading_level_cap": 10,
        },
    )
    assert resp.status_code == 201, resp.text
    body = cast("dict[str, object]", resp.json())
    assert body["status"] == "active"
    assert body["has_pin"] is False
    assert "pin_hash" not in resp.text

    list_resp = await client.get(
        _PROFILES,
        params={"family_id": str(seed.family_id)},
        headers=auth(seed.admin_token),
    )
    assert list_resp.status_code == 200
    names = [row["display_name"] for row in list_resp.json()["profiles"]]
    assert "Admin-Made Kid" in names


async def test_admin_sets_and_clears_reduce_motion(
    client: AsyncClient, seed: Seed
) -> None:
    """An admin can set reduce_motion on create and flip it via PATCH."""
    resp = await client.post(
        _PROFILES,
        headers=auth(seed.admin_token),
        json={
            "family_id": str(seed.family_id),
            "display_name": "Admin-Made Kid",
            "age_band": "5-8",
            "reduce_motion": True,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["reduce_motion"] is True
    pid = resp.json()["id"]

    patched = await client.patch(
        f"{_PROFILES}/{pid}",
        headers=auth(seed.admin_token),
        json={"reduce_motion": False},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["reduce_motion"] is False


async def test_pin_hash_never_serialized_on_update(
    client: AsyncClient, seed: Seed
) -> None:
    """Setting a PIN via PATCH never echoes the hash; has_pin flips true."""
    resp = await client.patch(
        f"{_PROFILES}/{seed.child_profile_id}",
        headers=auth(seed.admin_token),
        json={"pin": "1234"},
    )
    assert resp.status_code == 200
    assert "pin_hash" not in resp.text
    assert resp.json()["has_pin"] is True


async def test_deactivated_profile_excluded_from_guardian_listing(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian's own profile list omits a profile an admin deactivated."""
    deactivate = await client.patch(
        f"{_PROFILES}/{seed.child_profile_id}",
        headers=auth(seed.admin_token),
        json={"status": "deactivated"},
    )
    assert deactivate.status_code == 200
    assert deactivate.json()["status"] == "deactivated"

    listing = await client.get("/api/v1/profiles", headers=auth(seed.guardian_token))
    assert listing.status_code == 200
    ids = [row["id"] for row in listing.json()["profiles"]]
    assert str(seed.child_profile_id) not in ids


async def test_deactivated_profile_cannot_mint_child_session(
    client: AsyncClient, seed: Seed
) -> None:
    """A deactivated profile refuses a new child-session mint (404).

    Minted via the admin token: a guardian's OWN mint would already 403
    earlier, at ``authorize_profile`` (deactivation also drops the profile
    from ``_resolve_profiles``'s scoped set); the admin path skips that
    per-family ownership check and is what actually reaches the
    deactivated-profile check this test targets.
    """
    deactivate = await client.patch(
        f"{_PROFILES}/{seed.child_profile_id}",
        headers=auth(seed.admin_token),
        json={"status": "deactivated"},
    )
    assert deactivate.status_code == 200

    mint = await client.post(
        "/api/v1/child-sessions",
        headers=auth(seed.admin_token),
        json={"profile_id": str(seed.child_profile_id)},
    )
    assert mint.status_code == 404


async def test_list_admin_profiles_records_profile_viewed_event(
    client: AsyncClient, seed: Seed
) -> None:
    """Listing profiles cross-family logs one profile_viewed audit event.

    GDPR Article 30 accountability (remediation plan Phase 8a): this is the
    only cross-family read of child-linked data anywhere in the admin
    console, so it is audited like a write. One event per call, not one per
    row returned.
    """
    list_resp = await client.get(
        _PROFILES,
        params={"family_id": str(seed.family_id)},
        headers=auth(seed.admin_token),
    )
    assert list_resp.status_code == 200
    returned_count = len(list_resp.json()["profiles"])

    audit_resp = await client.get(
        "/api/v1/admin/audit",
        params={"kind": "profile_viewed"},
        headers=auth(seed.admin_token),
    )
    assert audit_resp.status_code == 200
    events = audit_resp.json()["events"]
    assert len(events) == 1
    event = events[0]
    assert event["entity_type"] == "child_profile"
    assert event["entity_id"] == str(seed.family_id)
    assert event["payload"] == {
        "family_id": str(seed.family_id),
        "count": returned_count,
    }


async def test_list_admin_profiles_without_filter_records_all_sentinel(
    client: AsyncClient, seed: Seed
) -> None:
    """An unfiltered admin listing audits with entity_id/family_id 'all'/None."""
    list_resp = await client.get(_PROFILES, headers=auth(seed.admin_token))
    assert list_resp.status_code == 200

    audit_resp = await client.get(
        "/api/v1/admin/audit",
        params={"kind": "profile_viewed"},
        headers=auth(seed.admin_token),
    )
    assert audit_resp.status_code == 200
    event = audit_resp.json()["events"][0]
    assert event["entity_id"] == "all"
    assert event["payload"]["family_id"] is None


async def test_reactivated_profile_reappears_in_listing(
    client: AsyncClient, seed: Seed
) -> None:
    """Reactivating a profile restores it to the guardian's own listing."""
    await client.patch(
        f"{_PROFILES}/{seed.child_profile_id}",
        headers=auth(seed.admin_token),
        json={"status": "deactivated"},
    )
    reactivate = await client.patch(
        f"{_PROFILES}/{seed.child_profile_id}",
        headers=auth(seed.admin_token),
        json={"status": "active"},
    )
    assert reactivate.status_code == 200
    assert reactivate.json()["status"] == "active"

    listing = await client.get("/api/v1/profiles", headers=auth(seed.guardian_token))
    ids = [row["id"] for row in listing.json()["profiles"]]
    assert str(seed.child_profile_id) in ids
