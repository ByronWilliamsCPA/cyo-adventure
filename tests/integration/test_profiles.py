"""Integration tests for the profiles API (C4a-2).

List scoping follows the authorization matrix: a guardian sees every profile
in their own family, a child sees only their own, and nobody sees another
family's rows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import Family, User
from tests.integration.conftest import Seed, auth, mint_device_token

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


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
    assert row["reading_level_cap"] == pytest.approx(99.0)
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
async def test_device_grant_lists_own_family_profiles(
    client: AsyncClient, seed: Seed
) -> None:
    """A device grant lists its own family's profiles, shaped like the guardian view.

    ADR-014 phase 2: the kid picker needs name/avatar/has_pin for every
    profile in the authorized device's family, without a live guardian
    bearer. Another family's profile must never appear.
    """
    device_token = await mint_device_token(client, seed.guardian_token)
    resp = await client.get("/api/v1/profiles", headers=auth(device_token))
    assert resp.status_code == 200, resp.text
    profiles = resp.json()["profiles"]
    ids = {p["id"] for p in profiles}
    assert str(seed.child_profile_id) in ids
    assert str(seed.other_child_profile_id) not in ids

    row = next(p for p in profiles if p["id"] == str(seed.child_profile_id))
    assert row["display_name"] == "Reader A"
    assert "avatar" in row
    assert "has_pin" in row


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
    assert body["reading_level_cap"] == pytest.approx(99.0)
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
async def test_create_profile_requires_recorded_consent(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A guardian with no recorded VPC consent cannot create a profile (400).

    Phase 2 / ADR-018 D1: seed's own guardians are pre-consented (see
    conftest.py::_consented) so this test seeds its own, deliberately
    unconsented, guardian instead.
    """
    _ = seed
    async with sessions() as session:
        family = Family(name="Unconsented Family")
        session.add(family)
        await session.flush()
        session.add(
            User(
                family_id=family.id,
                role="guardian",
                authn_subject="unconsented-guardian",
            )
        )
        await session.commit()

    resp = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "5-8"},
        headers=auth("unconsented-guardian"),
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_profile_toggles_processing_restricted(
    client: AsyncClient, seed: Seed
) -> None:
    """PATCH .../profiles/{id} sets and clears the Article 18/21 restrict flag."""
    restrict = await client.patch(
        f"/api/v1/profiles/{seed.child_profile_id}",
        json={"processing_restricted": True},
        headers=auth(seed.guardian_token),
    )
    assert restrict.status_code == 200, restrict.text
    assert restrict.json()["processing_restricted"] is True

    unrestrict = await client.patch(
        f"/api/v1/profiles/{seed.child_profile_id}",
        json={"processing_restricted": False},
        headers=auth(seed.guardian_token),
    )
    assert unrestrict.status_code == 200, unrestrict.text
    assert unrestrict.json()["processing_restricted"] is False


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
    assert body["reading_level_cap"] == pytest.approx(4.5)
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
    assert at_zero.json()["reading_level_cap"] == pytest.approx(0.0)
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


# ---------------------------------------------------------------------------
# P6-07: optional picker PIN (guardian set/clear; write-only hash)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_set_pin_marks_profile_has_pin(client: AsyncClient, seed: Seed) -> None:
    """A guardian sets a PIN; has_pin flips to true in the echo and the list."""
    guardian = auth(seed.guardian_token)
    created = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "5-8"},
        headers=guardian,
    )
    assert created.status_code == 201, created.text
    assert created.json()["has_pin"] is False  # no PIN by default
    pid = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/profiles/{pid}", json={"pin": "4321"}, headers=guardian
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["has_pin"] is True

    listed = await client.get("/api/v1/profiles", headers=guardian)
    by_id = {p["id"]: p for p in listed.json()["profiles"]}
    assert by_id[pid]["has_pin"] is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_clear_pin_via_explicit_null(client: AsyncClient, seed: Seed) -> None:
    """An explicit ``"pin": null`` removes the PIN; omitting it keeps it."""
    guardian = auth(seed.guardian_token)
    pid = str(seed.child_profile_id)
    await client.patch(
        f"/api/v1/profiles/{pid}", json={"pin": "4321"}, headers=guardian
    )

    untouched = await client.patch(
        f"/api/v1/profiles/{pid}", json={"tts_enabled": True}, headers=guardian
    )
    assert untouched.status_code == 200, untouched.text
    assert untouched.json()["has_pin"] is True  # omitted pin left unchanged

    cleared = await client.patch(
        f"/api/v1/profiles/{pid}", json={"pin": None}, headers=guardian
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["has_pin"] is False


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_pin",
    ["123", "123456789", "12a4", "    ", "", "12 34"],
)
async def test_update_rejects_malformed_pin(
    client: AsyncClient, seed: Seed, bad_pin: str
) -> None:
    """Anything but 4-8 ASCII digits is a 422 (PinCode boundary)."""
    resp = await client.patch(
        f"/api/v1/profiles/{seed.child_profile_id}",
        json={"pin": bad_pin},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.integration
@pytest.mark.security
@pytest.mark.asyncio
async def test_malformed_pin_422_never_echoes_submitted_value(
    client: AsyncClient, seed: Seed
) -> None:
    """The 422 body must not repeat the submitted PIN candidate (CWE-209).

    FastAPI's default RequestValidationError handler echoes the raw submitted
    value in each error's ``input`` field; the app-wide handler in ``app.py``
    strips it (keeping ``type``/``loc``/``msg``) so a near-miss PIN, which is
    credential material, can never leak through a validation error.
    """
    candidate = "998877665"  # 9 digits: fails PinCode's max_length, near-miss
    resp = await client.patch(
        f"/api/v1/profiles/{seed.child_profile_id}",
        json={"pin": candidate},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text
    assert candidate not in resp.text
    detail = resp.json()["detail"]
    assert detail, "expected at least one validation error entry"
    for entry in detail:
        assert "input" not in entry
        assert "ctx" not in entry
        assert set(entry) == {"type", "loc", "msg"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guardian_cannot_set_pin_on_other_familys_profile(
    client: AsyncClient, seed: Seed
) -> None:
    """Cross-family PIN set is a 403 like any other cross-family PATCH."""
    resp = await client.patch(
        f"/api/v1/profiles/{seed.other_child_profile_id}",
        json={"pin": "4321"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_child_cannot_set_own_pin(client: AsyncClient, seed: Seed) -> None:
    """A child token may not set or clear a picker PIN (guardian-only write)."""
    resp = await client.patch(
        f"/api/v1/profiles/{seed.child_profile_id}",
        json={"pin": "4321"},
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pin_hash_never_serialized(client: AsyncClient, seed: Seed) -> None:
    """No profile response ever contains the stored hash, only has_pin.

    Asserts on the RAW response body text, not parsed keys, so an accidental
    rename or nesting of the credential field cannot slip past the check.
    """
    guardian = auth(seed.guardian_token)
    pid = str(seed.child_profile_id)

    patched = await client.patch(
        f"/api/v1/profiles/{pid}", json={"pin": "4321"}, headers=guardian
    )
    assert patched.status_code == 200, patched.text
    assert "pin_hash" not in patched.text
    assert "pbkdf2" not in patched.text

    listed = await client.get("/api/v1/profiles", headers=guardian)
    assert listed.status_code == 200, listed.text
    assert "pin_hash" not in listed.text
    assert "pbkdf2" not in listed.text

    as_child = await client.get("/api/v1/profiles", headers=auth(seed.child_token))
    assert as_child.status_code == 200, as_child.text
    assert "pin_hash" not in as_child.text
    assert "pbkdf2" not in as_child.text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_with_content_flag_caps_and_banned_themes(
    client: AsyncClient, seed: Seed
) -> None:
    """G2: a guardian sets per-child flag caps and banned themes on create."""
    resp = await client.post(
        "/api/v1/profiles",
        json={
            "display_name": "Nova",
            "age_band": "8-11",
            "content_flag_caps": {"violence": "none", "scariness": "mild"},
            "banned_themes": ["Spiders", "  Magic  "],
        },
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["content_flag_caps"] == {
        "violence": "none",
        "scariness": "mild",
        "peril": None,
    }
    # whitespace-trimmed and lowercased at the API boundary.
    assert body["banned_themes"] == ["spiders", "magic"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_defaults_g2_fields_to_empty(
    client: AsyncClient, seed: Seed
) -> None:
    """A create body with no G2 fields yields no caps and no banned themes."""
    resp = await client.post(
        "/api/v1/profiles",
        json={"display_name": "Nova", "age_band": "8-11"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["content_flag_caps"] == {
        "violence": None,
        "scariness": None,
        "peril": None,
    }
    assert body["banned_themes"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_rejects_unknown_content_flag_level(
    client: AsyncClient, seed: Seed
) -> None:
    """A content_flag_caps value outside the closed vocabulary is a 422."""
    resp = await client.post(
        "/api/v1/profiles",
        json={
            "display_name": "Nova",
            "age_band": "8-11",
            "content_flag_caps": {"violence": "extreme"},
        },
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_rejects_banned_theme_with_control_characters(
    client: AsyncClient, seed: Seed
) -> None:
    """A banned theme carrying disallowed characters is a 422, not silently kept."""
    resp = await client.post(
        "/api/v1/profiles",
        json={
            "display_name": "Nova",
            "age_band": "8-11",
            "banned_themes": ["spiders\x07;drop table"],
        },
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_rejects_more_than_twenty_banned_themes(
    client: AsyncClient, seed: Seed
) -> None:
    """More than 20 banned themes is a 422 (mirrors ConceptBrief.content_nogo's cap)."""
    resp = await client.post(
        "/api/v1/profiles",
        json={
            "display_name": "Nova",
            "age_band": "8-11",
            "banned_themes": [f"theme{i}" for i in range(21)],
        },
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_content_flag_caps_replaces_wholesale(
    client: AsyncClient, seed: Seed
) -> None:
    """PATCH content_flag_caps replaces the stored caps, it does not merge."""
    guardian = auth(seed.guardian_token)
    created = await client.post(
        "/api/v1/profiles",
        json={
            "display_name": "Nova",
            "age_band": "8-11",
            "content_flag_caps": {"violence": "none", "scariness": "mild"},
        },
        headers=guardian,
    )
    pid = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/profiles/{pid}",
        json={"content_flag_caps": {"peril": "mild"}},
        headers=guardian,
    )
    assert resp.status_code == 200, resp.text
    # violence/scariness are gone, not carried over: a wholesale replace.
    assert resp.json()["content_flag_caps"] == {
        "violence": None,
        "scariness": None,
        "peril": "mild",
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_content_flag_caps_clears_via_explicit_null(
    client: AsyncClient, seed: Seed
) -> None:
    """PATCH with an explicit null clears every content-flag cap."""
    guardian = auth(seed.guardian_token)
    created = await client.post(
        "/api/v1/profiles",
        json={
            "display_name": "Nova",
            "age_band": "8-11",
            "content_flag_caps": {"violence": "none"},
        },
        headers=guardian,
    )
    pid = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/profiles/{pid}", json={"content_flag_caps": None}, headers=guardian
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["content_flag_caps"] == {
        "violence": None,
        "scariness": None,
        "peril": None,
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_banned_themes_clears_via_explicit_null(
    client: AsyncClient, seed: Seed
) -> None:
    """PATCH with an explicit null clears the banned-themes list."""
    guardian = auth(seed.guardian_token)
    created = await client.post(
        "/api/v1/profiles",
        json={
            "display_name": "Nova",
            "age_band": "8-11",
            "banned_themes": ["spiders"],
        },
        headers=guardian,
    )
    pid = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/profiles/{pid}", json={"banned_themes": None}, headers=guardian
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["banned_themes"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_omitting_g2_fields_keeps_them_unchanged(
    client: AsyncClient, seed: Seed
) -> None:
    """A PATCH that omits the G2 fields entirely leaves them untouched."""
    guardian = auth(seed.guardian_token)
    created = await client.post(
        "/api/v1/profiles",
        json={
            "display_name": "Nova",
            "age_band": "8-11",
            "content_flag_caps": {"violence": "none"},
            "banned_themes": ["spiders"],
        },
        headers=guardian,
    )
    pid = created.json()["id"]

    resp = await client.patch(
        f"/api/v1/profiles/{pid}", json={"display_name": "Nova II"}, headers=guardian
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["content_flag_caps"]["violence"] == "none"
    assert body["banned_themes"] == ["spiders"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_and_update_envelope_fields(
    client: AsyncClient, seed: Seed
) -> None:
    """G3 envelope fields round-trip on create, apply on PATCH, null clears."""
    guardian = auth(seed.guardian_token)
    created = await client.post(
        "/api/v1/profiles",
        json={
            "display_name": "Vega",
            "age_band": "8-11",
            "request_auto_approve": True,
            "monthly_request_envelope": 3,
        },
        headers=guardian,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["request_auto_approve"] is True
    assert body["monthly_request_envelope"] == 3
    pid = body["id"]

    toggled = await client.patch(
        f"/api/v1/profiles/{pid}",
        json={"request_auto_approve": False},
        headers=guardian,
    )
    assert toggled.status_code == 200, toggled.text
    assert toggled.json()["request_auto_approve"] is False
    assert toggled.json()["monthly_request_envelope"] == 3

    cleared = await client.patch(
        f"/api/v1/profiles/{pid}",
        json={"monthly_request_envelope": None},
        headers=guardian,
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["monthly_request_envelope"] is None
