"""Story personalization API tests (ADR-023 Task B6).

Covers ring-1 CRUD (GET/PUT .../personalization), ring-2 disclosure consent
(POST/DELETE .../ring2-consent), and the values-resolution route
(GET .../personalization-values). The values route implements the 8-condition
(plus condition 0) predicate from
``docs/planning/story-personalization-implementation-plan.md`` section 8.4/
8.6; each predicate-failure test below exercises exactly one condition,
mirroring the enumerated test list in section 8.8. Fixtures build custom
families/profiles/connections directly via the ``sessions`` fixture (the
shared ``seed`` fixture's fam_a has no sibling profile and no
``FamilyConnection``), following ``test_personalization_consent_tombstone.py``'s
own ORM-construction style.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import (
    ChildProfile,
    ChildProfilePersonalization,
    Family,
    FamilyConnection,
    PersonalizationDisclosureConsent,
    Storybook,
    User,
)
from tests.integration._event_assertions import assert_single_event
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    import uuid

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _guardian(
    session: AsyncSession, family_id: uuid.UUID, authn_subject: str
) -> User:
    """Create a consented guardian User for a family; returns the ORM row.

    The dev-stub auth accepts a seeded opaque ``authn_subject`` directly as
    the bearer token (``auth(subject)``), so this row's ``authn_subject`` IS
    the token a test uses to act as this guardian.
    """
    row = User(
        family_id=family_id,
        role="guardian",
        authn_subject=authn_subject,
        consent_accepted_at=datetime.now(UTC),
        consent_policy_version="test-fixture",
        consent_signer_name=authn_subject,
        consent_ip="127.0.0.1",
    )
    session.add(row)
    await session.flush()
    return row


def _connection(
    viewer_family_id: uuid.UUID,
    sharer_family_id: uuid.UUID,
    viewer_user_id: uuid.UUID,
    sharer_user_id: uuid.UUID,
    *,
    dual_consented: bool = True,
) -> FamilyConnection:
    """Build a FamilyConnection; dual-consented by default (ADR-016 active)."""
    row = FamilyConnection(
        family_id=viewer_family_id, connected_family_id=sharer_family_id
    )
    if dual_consented:
        row.consented_by_viewer_user_id = viewer_user_id
        row.consented_by_viewer_at = datetime.now(UTC)
        row.consented_by_sharer_user_id = sharer_user_id
        row.consented_by_sharer_at = datetime.now(UTC)
    return row


async def _storybook(
    session: AsyncSession,
    family_id: uuid.UUID,
    subject_profile_id: uuid.UUID | None,
    *,
    visibility: str = "family",
) -> Storybook:
    """Create a minimal Storybook row with a personalization subject.

    ``visibility`` defaults to the column default. Every CROSS-family case
    must pass ``visibility="catalog"``: a cross-family book only ever reaches
    another family's profile through the catalog + assignment path (see
    ``api/recommendations.py::_visible_books`` and
    ``api/reading.py::_authorized_storybook``), so a fixture that leaves a
    ring-2 book at ``"family"`` is asserting against a book the viewer family
    could never actually open.
    """
    row = Storybook(
        id=f"book-{family_id}-{subject_profile_id}",
        family_id=family_id,
        personalization_subject_profile_id=subject_profile_id,
        visibility=visibility,
    )
    session.add(row)
    await session.flush()
    return row


# ---------------------------------------------------------------------------
# Ring-1 CRUD (GET/PUT /profiles/{profile_id}/personalization)
# ---------------------------------------------------------------------------


async def test_get_personalization_empty_for_new_profile(
    client: AsyncClient, seed: Seed
) -> None:
    resp = await client.get(
        f"/api/v1/profiles/{seed.child_profile_id}/personalization",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["real_name_ring1_enabled"] is False
    assert body["real_name_ring2_enabled"] is False
    assert body["slots"] == []


async def test_put_personalization_round_trip(client: AsyncClient, seed: Seed) -> None:
    payload = {
        "real_name_ring1_enabled": True,
        "real_name_ring2_enabled": False,
        "slots": [
            {
                "slot_type": "pet_name",
                "value_text": "Biscuit",
                "ring1_enabled": True,
                "ring2_enabled": False,
            }
        ],
    }
    put_resp = await client.put(
        f"/api/v1/profiles/{seed.child_profile_id}/personalization",
        json=payload,
        headers=auth(seed.guardian_token),
    )
    assert put_resp.status_code == 200, put_resp.text
    body = put_resp.json()
    assert body["real_name_ring1_enabled"] is True
    assert len(body["slots"]) == 1
    slot = body["slots"][0]
    assert slot["slot_type"] == "pet_name"
    assert slot["value_text"] == "Biscuit"
    assert slot["ring2_eligible"] is True

    get_resp = await client.get(
        f"/api/v1/profiles/{seed.child_profile_id}/personalization",
        headers=auth(seed.guardian_token),
    )
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["slots"][0]["value_text"] == "Biscuit"


async def test_put_personalization_replaces_wholesale(
    client: AsyncClient, seed: Seed
) -> None:
    first = {
        "real_name_ring1_enabled": False,
        "real_name_ring2_enabled": False,
        "slots": [
            {
                "slot_type": "pet_name",
                "value_text": "Biscuit",
                "ring1_enabled": True,
                "ring2_enabled": False,
            },
            {
                "slot_type": "dedication",
                "value_text": "For Grandma",
                "ring1_enabled": True,
                "ring2_enabled": False,
            },
        ],
    }
    resp1 = await client.put(
        f"/api/v1/profiles/{seed.child_profile_id}/personalization",
        json=first,
        headers=auth(seed.guardian_token),
    )
    assert resp1.status_code == 200, resp1.text
    assert len(resp1.json()["slots"]) == 2

    second = {
        "real_name_ring1_enabled": False,
        "real_name_ring2_enabled": False,
        "slots": [
            {
                "slot_type": "pet_name",
                "value_text": "Biscuit",
                "ring1_enabled": True,
                "ring2_enabled": False,
            }
        ],
    }
    resp2 = await client.put(
        f"/api/v1/profiles/{seed.child_profile_id}/personalization",
        json=second,
        headers=auth(seed.guardian_token),
    )
    assert resp2.status_code == 200, resp2.text
    slots = resp2.json()["slots"]
    assert len(slots) == 1
    assert slots[0]["slot_type"] == "pet_name"


async def test_put_personalization_rejects_ring2_on_excluded_slot_type(
    client: AsyncClient, seed: Seed
) -> None:
    payload = {
        "real_name_ring1_enabled": False,
        "real_name_ring2_enabled": False,
        "slots": [
            {
                "slot_type": "dedication",
                "value_text": "For Grandma",
                "ring1_enabled": True,
                "ring2_enabled": True,
            }
        ],
    }
    resp = await client.put(
        f"/api/v1/profiles/{seed.child_profile_id}/personalization",
        json=payload,
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text


async def test_put_personalization_rejects_denylisted_value(
    client: AsyncClient, seed: Seed
) -> None:
    # seed.child_profile_id's age_band is "10-13", whose only band-mandatory
    # bundle is "graphic" (validator/slots.py._BAND_MANDATORY); "blood" is
    # one of that bundle's own denylist terms, so a personalization value
    # must clear the same floor a slot's LLM-proposed value does.
    payload = {
        "real_name_ring1_enabled": False,
        "real_name_ring2_enabled": False,
        "slots": [
            {
                "slot_type": "pet_name",
                "value_text": "blood",
                "ring1_enabled": True,
                "ring2_enabled": False,
            }
        ],
    }
    resp = await client.put(
        f"/api/v1/profiles/{seed.child_profile_id}/personalization",
        json=payload,
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text


async def test_put_personalization_emits_toggled_event(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    payload = {
        "real_name_ring1_enabled": False,
        "real_name_ring2_enabled": False,
        "slots": [
            {
                "slot_type": "pet_name",
                "value_text": "Biscuit",
                "ring1_enabled": True,
                "ring2_enabled": False,
            }
        ],
    }
    resp = await client.put(
        f"/api/v1/profiles/{seed.child_profile_id}/personalization",
        json=payload,
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 200, resp.text
    event = await assert_single_event(
        sessions,
        event_type="personalization_toggled",
        entity_type="child_profile_personalization",
    )
    assert event.payload == {"slot_type": "pet_name", "ring": 1, "action": "enabled"}


async def test_child_cannot_read_or_write_personalization(
    client: AsyncClient, seed: Seed
) -> None:
    get_resp = await client.get(
        f"/api/v1/profiles/{seed.child_profile_id}/personalization",
        headers=auth(seed.child_token),
    )
    assert get_resp.status_code == 403
    put_resp = await client.put(
        f"/api/v1/profiles/{seed.child_profile_id}/personalization",
        json={
            "real_name_ring1_enabled": False,
            "real_name_ring2_enabled": False,
            "slots": [],
        },
        headers=auth(seed.child_token),
    )
    assert put_resp.status_code == 403


# ---------------------------------------------------------------------------
# Ring-2 disclosure consent (POST/DELETE /profiles/{id}/ring2-consent)
# ---------------------------------------------------------------------------


async def test_grant_ring2_consent_success(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        sharer = Family(name="Sharer")
        viewer = Family(name="Viewer")
        session.add_all([sharer, viewer])
        await session.flush()
        subject = ChildProfile(
            family_id=sharer.id, display_name="Alex", age_band="10-13"
        )
        session.add(subject)
        await session.flush()
        sharer_guardian = await _guardian(session, sharer.id, "sharer-guardian")
        viewer_guardian = await _guardian(session, viewer.id, "viewer-guardian")
        connection = _connection(
            viewer.id, sharer.id, viewer_guardian.id, sharer_guardian.id
        )
        session.add(connection)
        await session.commit()
        subject_id = subject.id
        connection_id = connection.id

    resp = await client.post(
        f"/api/v1/profiles/{subject_id}/ring2-consent",
        json={
            "family_connection_id": str(connection_id),
            "covered_slot_types": ["pet_name"],
            "policy_version": "v1",
            "signer_name": "Sharer Guardian",
            "accepted": True,
        },
        headers=auth("sharer-guardian"),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["covered_slot_types"] == ["pet_name"]
    assert body["consent_accepted_at"] is not None
    assert body["consent_policy_version"] == "v1"
    assert body["revoked_at"] is None


async def test_grant_ring2_consent_ignores_client_supplied_server_stamped_fields(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """extra=forbid rejects a client attempt to set consent_ip/consent_accepted_at."""
    async with sessions() as session:
        sharer = Family(name="Sharer2")
        viewer = Family(name="Viewer2")
        session.add_all([sharer, viewer])
        await session.flush()
        subject = ChildProfile(
            family_id=sharer.id, display_name="Mira", age_band="10-13"
        )
        session.add(subject)
        await session.flush()
        sharer_guardian = await _guardian(session, sharer.id, "sharer-guardian-2")
        viewer_guardian = await _guardian(session, viewer.id, "viewer-guardian-2")
        connection = _connection(
            viewer.id, sharer.id, viewer_guardian.id, sharer_guardian.id
        )
        session.add(connection)
        await session.commit()
        subject_id = subject.id
        connection_id = connection.id

    resp = await client.post(
        f"/api/v1/profiles/{subject_id}/ring2-consent",
        json={
            "family_connection_id": str(connection_id),
            "covered_slot_types": ["pet_name"],
            "policy_version": "v1",
            "signer_name": "Sharer Guardian",
            "accepted": True,
            "consent_ip": "1.2.3.4",
            "consent_accepted_at": "2020-01-01T00:00:00Z",
        },
        headers=auth("sharer-guardian-2"),
    )
    assert resp.status_code == 422, resp.text


async def test_viewer_side_guardian_cannot_grant_ring2_consent(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """FamilyConnection.family_id is the VIEWER; only the sharer side may grant."""
    async with sessions() as session:
        fam_a = Family(name="Family A (viewer of the connection)")
        fam_b = Family(name="Family B (sharer of the connection)")
        session.add_all([fam_a, fam_b])
        await session.flush()
        # The subject profile lives in fam_a (the VIEWER side); fam_a's own
        # guardian owns the profile via authorize_profile, but fam_a is the
        # viewer, not the sharer, on this connection.
        subject = ChildProfile(family_id=fam_a.id, display_name="Sam", age_band="10-13")
        session.add(subject)
        await session.flush()
        guardian_a = await _guardian(session, fam_a.id, "family-a-guardian")
        guardian_b = await _guardian(session, fam_b.id, "family-b-guardian")
        # family_id=fam_a (viewer), connected_family_id=fam_b (sharer): fam_a
        # is NOT the sharer, so its guardian must be rejected.
        connection = _connection(fam_a.id, fam_b.id, guardian_a.id, guardian_b.id)
        session.add(connection)
        await session.commit()
        subject_id = subject.id
        connection_id = connection.id

    resp = await client.post(
        f"/api/v1/profiles/{subject_id}/ring2-consent",
        json={
            "family_connection_id": str(connection_id),
            "covered_slot_types": ["pet_name"],
            "policy_version": "v1",
            "signer_name": "Family A Guardian",
            "accepted": True,
        },
        headers=auth("family-a-guardian"),
    )
    assert resp.status_code == 403, resp.text


async def test_sibling_authority_attested_required_when_sibling_slot_covered(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        sharer = Family(name="Sharer3")
        viewer = Family(name="Viewer3")
        session.add_all([sharer, viewer])
        await session.flush()
        subject = ChildProfile(
            family_id=sharer.id, display_name="Nora", age_band="10-13"
        )
        session.add(subject)
        await session.flush()
        sharer_guardian = await _guardian(session, sharer.id, "sharer-guardian-3")
        viewer_guardian = await _guardian(session, viewer.id, "viewer-guardian-3")
        connection = _connection(
            viewer.id, sharer.id, viewer_guardian.id, sharer_guardian.id
        )
        session.add(connection)
        await session.commit()
        subject_id = subject.id
        connection_id = connection.id

    resp = await client.post(
        f"/api/v1/profiles/{subject_id}/ring2-consent",
        json={
            "family_connection_id": str(connection_id),
            "covered_slot_types": ["sibling_name"],
            "policy_version": "v1",
            "signer_name": "Sharer Guardian",
            "accepted": True,
        },
        headers=auth("sharer-guardian-3"),
    )
    assert resp.status_code == 422, resp.text


async def test_revoke_ring2_consent(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        sharer = Family(name="Sharer4")
        viewer = Family(name="Viewer4")
        session.add_all([sharer, viewer])
        await session.flush()
        subject = ChildProfile(
            family_id=sharer.id, display_name="Theo", age_band="10-13"
        )
        session.add(subject)
        await session.flush()
        sharer_guardian = await _guardian(session, sharer.id, "sharer-guardian-4")
        viewer_guardian = await _guardian(session, viewer.id, "viewer-guardian-4")
        connection = _connection(
            viewer.id, sharer.id, viewer_guardian.id, sharer_guardian.id
        )
        session.add(connection)
        # connection.id is a client-side uuid4 default assigned at flush; it
        # must be flushed before being read into the consent row's FK below,
        # or the consent row would embed None instead of the real id.
        await session.flush()
        consent = PersonalizationDisclosureConsent(
            child_profile_id=subject.id,
            family_connection_id=connection.id,
            covered_slot_types=["pet_name"],
            consent_accepted_at=datetime.now(UTC),
            consent_policy_version="v1",
            consent_signer_name="Sharer Guardian",
            consent_ip="127.0.0.1",
        )
        session.add(consent)
        await session.commit()
        subject_id = subject.id
        connection_id = connection.id

    resp = await client.delete(
        f"/api/v1/profiles/{subject_id}/ring2-consent/{connection_id}",
        headers=auth("sharer-guardian-4"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["revoked_at"] is not None


# ---------------------------------------------------------------------------
# Values resolution (GET /storybooks/{storybook_id}/personalization-values)
# ---------------------------------------------------------------------------


async def test_values_missing_storybook_returns_the_empty_payload(
    client: AsyncClient, seed: Seed
) -> None:
    """A nonexistent book is indistinguishable from every other predicate failure.

    This route previously 404'd here, which made it an existence oracle over
    the whole storybook table: any authenticated caller could enumerate ids
    and learn which exist globally, before any family check had run. The
    route has no 403 branch either, so uniform disclosure is the only way it
    can honor its own "leak nothing about another family" contract.
    """
    resp = await client.get(
        "/api/v1/storybooks/does-not-exist/personalization-values",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subject_profile_id"] is None
    assert body["ring"] is None
    assert body["values"] == {}


async def test_values_cross_family_private_book_returns_the_empty_payload(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Another family's non-catalog book is not addressable, consent aside.

    Without the reachability check the route resolved values from ANY book
    id, leaving the cross-family private case governed only by the
    downstream ring-2 consent predicate rather than by the visibility rule
    every other read path enforces.
    """
    async with sessions() as session:
        sharer = Family(name="Private Sharer")
        viewer = Family(name="Unrelated Viewer")
        session.add_all([sharer, viewer])
        await session.flush()
        subject = ChildProfile(
            family_id=sharer.id,
            display_name="Private Reader",
            age_band="10-13",
            real_name_ring1_enabled=True,
        )
        session.add(subject)
        await session.flush()
        session.add(
            ChildProfilePersonalization(
                child_profile_id=subject.id,
                slot_type="pet_name",
                value_text="Waffles",
                ring1_enabled=True,
            )
        )
        await _guardian(session, viewer.id, "unrelated-viewer-guardian")
        await session.flush()
        # Cross-family AND non-catalog: the one combination no read path in
        # the app allows, whatever the consent state says.
        book = await _storybook(session, sharer.id, subject.id, visibility="family")
        await session.commit()
        book_id = book.id

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth("unrelated-viewer-guardian"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["values"] == {}


async def test_values_no_subject_returns_empty(client: AsyncClient, seed: Seed) -> None:
    """seed.storybook_id has no personalization_subject_profile_id set."""
    resp = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/personalization-values",
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subject_profile_id"] is None
    assert body["ring"] is None
    assert body["values"] == {}


async def test_values_ring1_happy_path(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        fam = Family(name="Ring1 Family")
        session.add(fam)
        await session.flush()
        subject = ChildProfile(
            family_id=fam.id,
            display_name="Ring1 Reader",
            age_band="10-13",
            real_name_ring1_enabled=True,
        )
        session.add(subject)
        await session.flush()
        session.add(
            ChildProfilePersonalization(
                child_profile_id=subject.id,
                slot_type="pet_name",
                value_text="Waffles",
                ring1_enabled=True,
            )
        )
        await _guardian(session, fam.id, "ring1-guardian")
        await session.flush()
        book = await _storybook(session, fam.id, subject.id)
        await session.commit()
        book_id = book.id

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth("ring1-guardian"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ring"] == 1
    assert body["values"]["protagonist_first_name"] == "Ring1 Reader"
    assert body["values"]["pet_name"] == "Waffles"


async def test_values_unconnected_family_empty(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        sharer = Family(name="Sharer5")
        viewer = Family(name="Viewer5")
        session.add_all([sharer, viewer])
        await session.flush()
        subject = ChildProfile(
            family_id=sharer.id,
            display_name="Unconnected Subject",
            age_band="10-13",
            real_name_ring2_enabled=True,
        )
        session.add(subject)
        await session.flush()
        await _guardian(session, viewer.id, "unconnected-viewer-guardian")
        book = await _storybook(session, sharer.id, subject.id, visibility="catalog")
        # Deliberately no FamilyConnection at all between viewer and sharer.
        await session.commit()
        book_id = book.id

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth("unconnected-viewer-guardian"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ring"] is None
    assert body["values"] == {}


async def _build_ring2_scenario(
    session: AsyncSession,
    *,
    dual_consented: bool = True,
    consent_covers: list[str] | None = ("pet_name",),
    consent_revoked: bool = False,
    subject_deactivated: bool = False,
    subject_restricted: bool = False,
    viewer_receive_enabled: bool = True,
    ring2_enabled_on_slot: bool = True,
) -> tuple[str, str]:
    """Build a full ring-2 scenario; returns (storybook_id, viewer_guardian_token)."""
    sharer = Family(name=f"Sharer-{id(session)}")
    viewer = Family(
        name=f"Viewer-{id(session)}",
        personalization_receive_enabled=viewer_receive_enabled,
    )
    session.add_all([sharer, viewer])
    await session.flush()
    subject = ChildProfile(
        family_id=sharer.id,
        display_name="Ring2 Subject",
        age_band="10-13",
        deactivated_at=datetime.now(UTC) if subject_deactivated else None,
        processing_restricted_at=datetime.now(UTC) if subject_restricted else None,
    )
    session.add(subject)
    await session.flush()
    if ring2_enabled_on_slot:
        session.add(
            ChildProfilePersonalization(
                child_profile_id=subject.id,
                slot_type="pet_name",
                value_text="Ring2Pet",
                ring2_enabled=True,
            )
        )
    sharer_guardian = await _guardian(
        session, sharer.id, f"sharer-guardian-{id(session)}"
    )
    viewer_guardian = await _guardian(
        session, viewer.id, f"viewer-guardian-{id(session)}"
    )
    connection = _connection(
        viewer.id,
        sharer.id,
        viewer_guardian.id,
        sharer_guardian.id,
        dual_consented=dual_consented,
    )
    session.add(connection)
    await session.flush()
    if consent_covers is not None:
        session.add(
            PersonalizationDisclosureConsent(
                child_profile_id=subject.id,
                family_connection_id=connection.id,
                covered_slot_types=list(consent_covers),
                consent_accepted_at=datetime.now(UTC),
                consent_policy_version="v1",
                consent_signer_name="Sharer Guardian",
                consent_ip="127.0.0.1",
                revoked_at=datetime.now(UTC) if consent_revoked else None,
            )
        )
    book = await _storybook(session, sharer.id, subject.id, visibility="catalog")
    await session.commit()
    return book.id, viewer_guardian.authn_subject


async def test_values_ring2_happy_path(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        book_id, viewer_token = await _build_ring2_scenario(session)

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth(viewer_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ring"] == 2
    assert body["values"] == {"pet_name": "Ring2Pet"}


async def test_values_ring2_not_dual_consented_empty(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        book_id, viewer_token = await _build_ring2_scenario(
            session, dual_consented=False
        )

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth(viewer_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["values"] == {}


async def test_values_ring2_revoked_consent_empty(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        book_id, viewer_token = await _build_ring2_scenario(
            session, consent_revoked=True
        )

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth(viewer_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["values"] == {}


async def test_values_ring2_missing_consent_row_empty(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        book_id, viewer_token = await _build_ring2_scenario(
            session, consent_covers=None
        )

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth(viewer_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["values"] == {}


async def test_values_ring2_flag_off_empty(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        book_id, viewer_token = await _build_ring2_scenario(
            session, ring2_enabled_on_slot=False
        )

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth(viewer_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["values"] == {}


async def test_values_ring2_deactivated_subject_empty(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        book_id, viewer_token = await _build_ring2_scenario(
            session, subject_deactivated=True
        )

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth(viewer_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["values"] == {}


async def test_values_ring2_processing_restricted_subject_empty(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        book_id, viewer_token = await _build_ring2_scenario(
            session, subject_restricted=True
        )

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth(viewer_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["values"] == {}


async def test_values_ring2_receive_toggle_off_empty(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        book_id, viewer_token = await _build_ring2_scenario(
            session, viewer_receive_enabled=False
        )

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth(viewer_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["values"] == {}


async def test_values_child_session_in_viewer_family_succeeds(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    async with sessions() as session:
        sharer = Family(name="Sharer-Child")
        viewer = Family(name="Viewer-Child")
        session.add_all([sharer, viewer])
        await session.flush()
        subject = ChildProfile(
            family_id=sharer.id, display_name="ChildCase Subject", age_band="10-13"
        )
        viewer_profile = ChildProfile(
            family_id=viewer.id, display_name="Viewer Kid", age_band="10-13"
        )
        session.add_all([subject, viewer_profile])
        await session.flush()
        session.add(
            ChildProfilePersonalization(
                child_profile_id=subject.id,
                slot_type="pet_name",
                value_text="ChildCasePet",
                ring2_enabled=True,
            )
        )
        sharer_guardian = await _guardian(session, sharer.id, "sharer-guardian-child")
        viewer_guardian = await _guardian(session, viewer.id, "viewer-guardian-child")
        session.add(
            User(
                family_id=viewer.id,
                role="child",
                authn_subject="viewer-child-token",
                child_profile_id=viewer_profile.id,
            )
        )
        connection = _connection(
            viewer.id, sharer.id, viewer_guardian.id, sharer_guardian.id
        )
        session.add(connection)
        await session.flush()
        session.add(
            PersonalizationDisclosureConsent(
                child_profile_id=subject.id,
                family_connection_id=connection.id,
                covered_slot_types=["pet_name"],
                consent_accepted_at=datetime.now(UTC),
                consent_policy_version="v1",
                consent_signer_name="Sharer Guardian",
                consent_ip="127.0.0.1",
            )
        )
        book = await _storybook(session, sharer.id, subject.id, visibility="catalog")
        await session.commit()
        book_id = book.id

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth("viewer-child-token"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ring"] == 2
    assert body["values"] == {"pet_name": "ChildCasePet"}


async def test_values_pronoun_and_dedication_never_disclosed_ring2(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """pronoun_set/dedication carry no ring2_enabled=True row: the DB CHECK
    (ck_cpp_ring2_ceiling) makes such a row unconstructible, and the write
    route (PUT .../personalization) rejects it at the API layer too (see
    test_put_personalization_rejects_ring2_on_excluded_slot_type). This test
    pins the values route's own belt-and-braces filter: a ring1-only
    dedication row must never leak into a ring-2 payload even though the
    slot exists on the subject.
    """
    async with sessions() as session:
        sharer = Family(name="Sharer-Dedication")
        viewer = Family(name="Viewer-Dedication")
        session.add_all([sharer, viewer])
        await session.flush()
        subject = ChildProfile(
            family_id=sharer.id, display_name="Dedication Subject", age_band="10-13"
        )
        session.add(subject)
        await session.flush()
        session.add(
            ChildProfilePersonalization(
                child_profile_id=subject.id,
                slot_type="dedication",
                value_text="For Grandma",
                ring1_enabled=True,
                ring2_enabled=False,
            )
        )
        sharer_guardian = await _guardian(
            session, sharer.id, "sharer-guardian-dedication"
        )
        viewer_guardian = await _guardian(
            session, viewer.id, "viewer-guardian-dedication"
        )
        connection = _connection(
            viewer.id, sharer.id, viewer_guardian.id, sharer_guardian.id
        )
        session.add(connection)
        await session.flush()
        session.add(
            PersonalizationDisclosureConsent(
                child_profile_id=subject.id,
                family_connection_id=connection.id,
                covered_slot_types=["dedication"],
                consent_accepted_at=datetime.now(UTC),
                consent_policy_version="v1",
                consent_signer_name="Sharer Guardian",
                consent_ip="127.0.0.1",
            )
        )
        book = await _storybook(session, sharer.id, subject.id, visibility="catalog")
        await session.commit()
        book_id = book.id

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth("viewer-guardian-dedication"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["values"] == {}


async def test_values_sibling_disclosed_under_own_consent(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Sibling B's name is disclosed under B's OWN ring-2 settings/consent."""
    async with sessions() as session:
        sharer = Family(name="Sharer-Sibling")
        viewer = Family(name="Viewer-Sibling")
        session.add_all([sharer, viewer])
        await session.flush()
        subject_a = ChildProfile(
            family_id=sharer.id, display_name="Sibling A", age_band="10-13"
        )
        sibling_b = ChildProfile(
            family_id=sharer.id,
            display_name="Sibling B",
            age_band="10-13",
            real_name_ring2_enabled=True,
        )
        session.add_all([subject_a, sibling_b])
        await session.flush()
        session.add(
            ChildProfilePersonalization(
                child_profile_id=subject_a.id,
                slot_type="sibling_name",
                value_profile_id=sibling_b.id,
                ring2_enabled=True,
            )
        )
        sharer_guardian = await _guardian(session, sharer.id, "sharer-guardian-sibling")
        viewer_guardian = await _guardian(session, viewer.id, "viewer-guardian-sibling")
        connection = _connection(
            viewer.id, sharer.id, viewer_guardian.id, sharer_guardian.id
        )
        session.add(connection)
        await session.flush()
        # A's own consent covers the sibling slot.
        session.add(
            PersonalizationDisclosureConsent(
                child_profile_id=subject_a.id,
                family_connection_id=connection.id,
                covered_slot_types=["sibling_name"],
                sibling_authority_attested=True,
                consent_accepted_at=datetime.now(UTC),
                consent_policy_version="v1",
                consent_signer_name="Sharer Guardian",
                consent_ip="127.0.0.1",
            )
        )
        # B's OWN consent covers B's own protagonist_first_name slot.
        session.add(
            PersonalizationDisclosureConsent(
                child_profile_id=sibling_b.id,
                family_connection_id=connection.id,
                covered_slot_types=["protagonist_first_name"],
                consent_accepted_at=datetime.now(UTC),
                consent_policy_version="v1",
                consent_signer_name="Sharer Guardian",
                consent_ip="127.0.0.1",
            )
        )
        book = await _storybook(session, sharer.id, subject_a.id, visibility="catalog")
        await session.commit()
        book_id = book.id

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth("viewer-guardian-sibling"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["values"]["sibling_name"] == "Sibling B"


async def test_values_sibling_omitted_when_sibling_lacks_own_consent(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """B's OWN consent missing: the sibling slot is omitted, not the whole payload."""
    async with sessions() as session:
        sharer = Family(name="Sharer-Sibling2")
        viewer = Family(name="Viewer-Sibling2")
        session.add_all([sharer, viewer])
        await session.flush()
        subject_a = ChildProfile(
            family_id=sharer.id, display_name="Sibling A2", age_band="10-13"
        )
        sibling_b = ChildProfile(
            family_id=sharer.id,
            display_name="Sibling B2",
            age_band="10-13",
            real_name_ring2_enabled=True,
        )
        session.add_all([subject_a, sibling_b])
        await session.flush()
        session.add_all(
            [
                ChildProfilePersonalization(
                    child_profile_id=subject_a.id,
                    slot_type="sibling_name",
                    value_profile_id=sibling_b.id,
                    ring2_enabled=True,
                ),
                ChildProfilePersonalization(
                    child_profile_id=subject_a.id,
                    slot_type="pet_name",
                    value_text="A2Pet",
                    ring2_enabled=True,
                ),
            ]
        )
        sharer_guardian = await _guardian(
            session, sharer.id, "sharer-guardian-sibling2"
        )
        viewer_guardian = await _guardian(
            session, viewer.id, "viewer-guardian-sibling2"
        )
        connection = _connection(
            viewer.id, sharer.id, viewer_guardian.id, sharer_guardian.id
        )
        session.add(connection)
        await session.flush()
        # A's consent covers both slots; B has NO consent row of its own.
        session.add(
            PersonalizationDisclosureConsent(
                child_profile_id=subject_a.id,
                family_connection_id=connection.id,
                covered_slot_types=["sibling_name", "pet_name"],
                sibling_authority_attested=True,
                consent_accepted_at=datetime.now(UTC),
                consent_policy_version="v1",
                consent_signer_name="Sharer Guardian",
                consent_ip="127.0.0.1",
            )
        )
        book = await _storybook(session, sharer.id, subject_a.id, visibility="catalog")
        await session.commit()
        book_id = book.id

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth("viewer-guardian-sibling2"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "sibling_name" not in body["values"]
    assert body["values"]["pet_name"] == "A2Pet"


# ---------------------------------------------------------------------------
# B5 resolution: display_name structural/denylist checks at both write points
# ---------------------------------------------------------------------------


async def test_create_profile_rejects_denylisted_display_name(
    client: AsyncClient, seed: Seed
) -> None:
    resp = await client.post(
        "/api/v1/profiles",
        json={
            "display_name": "blood",
            "age_band": "10-13",
        },
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text


async def test_update_profile_rejects_denylisted_display_name(
    client: AsyncClient, seed: Seed
) -> None:
    resp = await client.patch(
        f"/api/v1/profiles/{seed.child_profile_id}",
        json={"display_name": "blood"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text
