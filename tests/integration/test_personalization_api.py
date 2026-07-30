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

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.api import personalization as personalization_api
from cyo_adventure.db.models import (
    ChildProfile,
    ChildProfilePersonalization,
    Family,
    FamilyConnection,
    PersonalizationDisclosureConsent,
    Storybook,
    User,
)
from cyo_adventure.storybook.sentinels import SENTINEL_RE
from tests.integration._event_assertions import assert_single_event
from tests.integration.conftest import Seed, Stranger, auth, mint_device_token

if TYPE_CHECKING:
    from collections.abc import Sequence

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
    """A second PUT with fewer slots drops the ones it omits (wholesale replace).

    The second slot in ``first`` used to be a ``dedication`` row carrying
    ``value_text``; ADR-023 Stage C Task C0e closed that as a free-text hole
    (``dedication`` is a closed kinship enum, like ``kinship_label``, not
    guardian-authored prose), so that value now correctly 422s and no longer
    exercises this test's actual concern (multi-slot wholesale replacement).
    Swapped for ``pronoun_set``, the one slot type
    ``storybook/personalization_values.py`` documents as deliberately
    shape-unconstrained, to keep two slots in the first PUT without relying on
    a closed vocabulary that ships empty by design.
    """
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
                "slot_type": "pronoun_set",
                "value_text": "she/her",
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


async def test_values_payload_carries_the_sentinel_pattern(
    client: AsyncClient, seed: Seed
) -> None:
    """The client never re-derives the sentinel pattern (risk R9).

    A missing book is one of the universal-empty-payload predicate failures
    (``get_personalization_values``'s own #CRITICAL note); it is used here
    because it needs no fixture beyond an authenticated caller, and the field
    is present on EVERY response, including this one.
    """
    resp = await client.get(
        "/api/v1/storybooks/does-not-exist/personalization-values",
        headers=auth(seed.guardian_token),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["sentinel_pattern"] == SENTINEL_RE.pattern


async def test_empty_values_payload_carries_no_slot_bindings(
    client: AsyncClient, seed: Seed
) -> None:
    """An empty payload stays uniform: an empty map, never a null or a partial one."""
    resp = await client.get(
        "/api/v1/storybooks/does-not-exist/personalization-values",
        headers=auth(seed.guardian_token),
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["slot_bindings"] == {}


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
    # slot_bindings is the slot-id to slot-type join the resolver needs (C0);
    # it is a property of the book's contract, identical at both rings.
    # `_storybook` seeds no GenerationJob, so the contract is unresolvable and
    # the map is legitimately empty here (the empty-vs-populated case is
    # covered directly by tests/unit/test_personalizable_slots.py).
    expected_slot_bindings: dict[str, str] = {}
    assert body["slot_bindings"] == expected_slot_bindings


@pytest.mark.parametrize(
    ("deactivated", "restricted"),
    [(True, False), (False, True)],
    ids=["deactivated", "processing_restricted"],
)
async def test_ring1_sibling_name_is_dropped_when_the_sibling_is_not_live(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    deactivated: bool,
    restricted: bool,
) -> None:
    """A deactivated or Article-18-restricted sibling's name must not render.

    `_is_live` documents its contract as "in either ring", but ring 1 resolved
    the sibling through `_family_profile_ids`, which constrains the referenced
    profile to the same family and says nothing about liveness. Ring 2 already
    gated on it, so the subject's own family was the weaker boundary: exactly
    backwards. Both non-live states are exercised because they are separate
    columns and a fix that reads only one of them looks correct.
    """
    async with sessions() as session:
        fam = Family(name="Ring1 Sibling Liveness Family")
        session.add(fam)
        await session.flush()
        subject = ChildProfile(
            family_id=fam.id, display_name="Ring1 Subject", age_band="10-13"
        )
        sibling = ChildProfile(
            family_id=fam.id,
            display_name="Not Live Sibling",
            age_band="10-13",
            deactivated_at=datetime.now(UTC) if deactivated else None,
            processing_restricted_at=datetime.now(UTC) if restricted else None,
        )
        session.add_all([subject, sibling])
        await session.flush()
        session.add_all(
            [
                ChildProfilePersonalization(
                    child_profile_id=subject.id,
                    slot_type="sibling_name",
                    value_profile_id=sibling.id,
                    ring1_enabled=True,
                ),
                # A second, unaffected slot. Without it the payload would be
                # empty and `_resolve_ring1_view` would return the universal
                # empty view (ring None), so the test would pass even if the
                # whole request had collapsed. This pins that exactly one
                # slot is dropped.
                ChildProfilePersonalization(
                    child_profile_id=subject.id,
                    slot_type="pet_name",
                    value_text="Waffles",
                    ring1_enabled=True,
                ),
            ]
        )
        await _guardian(session, fam.id, "ring1-liveness-guardian")
        await session.flush()
        book = await _storybook(session, fam.id, subject.id)
        await session.commit()
        book_id = book.id

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth("ring1-liveness-guardian"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ring"] == 1
    assert body["values"]["pet_name"] == "Waffles"
    assert "sibling_name" not in body["values"], (
        "a non-live sibling's real name reached a ring-1 payload"
    )


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
    # Full 8.3 indistinguishability, not just an empty values map: an
    # unconnected family's response must be byte-identical in shape to every
    # other predicate-failure empty payload, so nothing here leaks that a
    # subject or connection exists.
    assert body["subject_profile_id"] is None
    assert body["ring"] is None
    assert body["policy_version"] is None
    assert body["values"] == {}


async def _build_ring2_scenario(
    session: AsyncSession,
    *,
    dual_consented: bool = True,
    consent_covers: Sequence[str] | None = ("pet_name",),
    consent_revoked: bool = False,
    subject_deactivated: bool = False,
    subject_restricted: bool = False,
    viewer_receive_enabled: bool = True,
    ring2_enabled_on_slot: bool = True,
) -> tuple[str, str]:
    """Build a full ring-2 scenario; returns (storybook_id, viewer_guardian_token)."""
    # Names and authn_subjects only need to be unique, not meaningful, but they
    # DO need to be unique per call rather than per session object. `id(session)`
    # was the memory address of the session, which CPython reuses once a closed
    # session is collected: two sequential `async with sessions()` blocks in one
    # test (the ordering test below does exactly that) can land on the same
    # address and collide on `authn_subject`, and separate xdist workers never
    # had any reason to differ at all.
    tag = uuid.uuid4().hex[:12]
    sharer = Family(name=f"Sharer-{tag}")
    viewer = Family(
        name=f"Viewer-{tag}",
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
    sharer_guardian = await _guardian(session, sharer.id, f"sharer-guardian-{tag}")
    viewer_guardian = await _guardian(session, viewer.id, f"viewer-guardian-{tag}")
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
    # slot_bindings is a property of the book's contract, identical at both
    # rings; `_build_ring2_scenario` seeds its book through `_storybook`,
    # which adds no GenerationJob, so the contract is unresolvable and the
    # map is legitimately empty here (see test_values_ring1_happy_path above
    # for the same reasoning).
    expected_slot_bindings: dict[str, str] = {}
    assert body["slot_bindings"] == expected_slot_bindings


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


async def test_values_ring2_restricted_subject_is_refused_before_any_value_read(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A restricted subject's values are never read, not merely never returned.

    The two cases above already pin the OUTCOME (an empty payload). This pins
    the ORDER, which is the part a refactor can quietly break: the liveness
    guard runs before ``_ring2_values``, so an Article-18 processing-restricted
    child's personalization rows are not touched at all. Reading them in order
    to discard them would be the exact processing that restriction exists to
    stop, and it is the shape a "make the empty paths take constant time"
    change would naturally take.

    The stub raises rather than records, so a hoist fails loudly. The second
    half proves the patch target is live: on the happy path the same stub
    fires, so a green first half can never be green because the monkeypatch
    missed.
    """

    def _must_not_run(*_args: object, **_kwargs: object) -> None:
        msg = "_ring2_values was reached for a processing-restricted subject"
        raise AssertionError(msg)

    monkeypatch.setattr(personalization_api, "_ring2_values", _must_not_run)

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

    async with sessions() as session:
        live_book_id, live_token = await _build_ring2_scenario(session)
    with pytest.raises(AssertionError, match="processing-restricted subject"):
        await client.get(
            f"/api/v1/storybooks/{live_book_id}/personalization-values",
            headers=auth(live_token),
        )


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


_RECEIVE = "/api/v1/families/me/personalization-receive"


async def test_receive_toggle_off_empties_the_ring2_payload(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The guardian-facing switch actually reaches the resolution path.

    ``test_values_ring2_receive_toggle_off_empty`` above proves the COLUMN
    gates the payload, but it sets the column directly in the fixture. This
    proves a guardian can get there from the API: the column defaults TRUE
    and had no write surface at all until this route existed, so the
    documented opt-out was unreachable in practice.
    """
    async with sessions() as session:
        book_id, viewer_token = await _build_ring2_scenario(session)

    before = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth(viewer_token),
    )
    assert before.status_code == 200, before.text
    assert before.json()["values"] == {"pet_name": "Ring2Pet"}

    read = await client.get(_RECEIVE, headers=auth(viewer_token))
    assert read.status_code == 200, read.text
    assert read.json() == {"enabled": True}

    off = await client.put(
        _RECEIVE, headers=auth(viewer_token), json={"enabled": False}
    )
    assert off.status_code == 200, off.text
    assert off.json() == {"enabled": False}

    after = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth(viewer_token),
    )
    assert after.status_code == 200, after.text
    assert after.json()["values"] == {}

    # And it is reversible: an opt-out is a preference, not a burned bridge.
    back_on = await client.put(
        _RECEIVE, headers=auth(viewer_token), json={"enabled": True}
    )
    assert back_on.status_code == 200, back_on.text
    restored = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth(viewer_token),
    )
    assert restored.json()["values"] == {"pet_name": "Ring2Pet"}


async def test_receive_toggle_rejects_a_child_session(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Only a guardian may throw their family's switch, never a kid.

    The kid reads the RESULT of this switch on every personalized book, so
    a kid-writable toggle would let a child re-enable disclosures their
    guardian had turned off.
    """
    async with sessions() as session:
        family = Family(name="Receive-Toggle-Kid")
        session.add(family)
        await session.flush()
        kid_profile = ChildProfile(
            family_id=family.id, display_name="Toggle Kid", age_band="10-13"
        )
        session.add(kid_profile)
        await session.flush()
        session.add(
            User(
                family_id=family.id,
                role="child",
                authn_subject="receive-toggle-child-token",
                child_profile_id=kid_profile.id,
            )
        )
        await session.commit()

    read = await client.get(_RECEIVE, headers=auth("receive-toggle-child-token"))
    assert read.status_code == 403, read.text

    write = await client.put(
        _RECEIVE,
        headers=auth("receive-toggle-child-token"),
        json={"enabled": False},
    )
    assert write.status_code == 403, write.text


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


async def test_values_sibling_outside_the_sharer_family_is_omitted(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A stored sibling reference pointing out of the sharer family is dropped.

    Everything the happy path needs is present here except one thing: the
    referenced sibling lives in a third family. ``validator/slots.py``'s
    ``sibling_outside_family`` rule rejects that combination at write time, so
    a row like this at rest predates the rule or names a profile that has since
    moved households. The render path drops only the sibling slot, and now also
    says so in the log rather than failing the same row silently on every read.
    """
    async with sessions() as session:
        sharer = Family(name="Sharer-Outsider")
        viewer = Family(name="Viewer-Outsider")
        third = Family(name="Third-Outsider")
        session.add_all([sharer, viewer, third])
        await session.flush()
        subject_a = ChildProfile(
            family_id=sharer.id, display_name="Subject A", age_band="10-13"
        )
        outsider = ChildProfile(
            family_id=third.id,
            display_name="Outsider B",
            age_band="10-13",
            real_name_ring2_enabled=True,
        )
        session.add_all([subject_a, outsider])
        await session.flush()
        session.add(
            ChildProfilePersonalization(
                child_profile_id=subject_a.id,
                slot_type="sibling_name",
                value_profile_id=outsider.id,
                ring2_enabled=True,
            )
        )
        sharer_guardian = await _guardian(session, sharer.id, "sharer-guardian-outside")
        viewer_guardian = await _guardian(session, viewer.id, "viewer-guardian-outside")
        connection = _connection(
            viewer.id, sharer.id, viewer_guardian.id, sharer_guardian.id
        )
        session.add(connection)
        await session.flush()
        for profile_id, covers in (
            (subject_a.id, ["sibling_name"]),
            (outsider.id, ["protagonist_first_name"]),
        ):
            session.add(
                PersonalizationDisclosureConsent(
                    child_profile_id=profile_id,
                    family_connection_id=connection.id,
                    covered_slot_types=covers,
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
        headers=auth("viewer-guardian-outside"),
    )
    assert resp.status_code == 200, resp.text
    assert "sibling_name" not in resp.json()["values"]


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


async def test_values_sibling_ring2_empty_when_the_subject_did_not_opt_in(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Design plan 8.8: B opted in and A not returns nothing.

    B's own consent authorizes B's NAME being disclosed; it does not authorize a
    payload about A. With A's ring-2 flags off and no consent row for A, the whole
    payload is empty, not "empty except the sibling slot".
    """
    async with sessions() as session:
        sharer = Family(name="Sharer-SubjectOptOut")
        viewer = Family(name="Viewer-SubjectOptOut")
        session.add_all([sharer, viewer])
        await session.flush()
        subject_a = ChildProfile(
            family_id=sharer.id, display_name="Subject A OptOut", age_band="10-13"
        )
        sibling_b = ChildProfile(
            family_id=sharer.id,
            display_name="Sibling B OptOut",
            age_band="10-13",
            real_name_ring2_enabled=True,
        )
        session.add_all([subject_a, sibling_b])
        await session.flush()
        # A's own sibling_name row exists but is NOT ring2-enabled: A never
        # opted its own household into disclosing this slot.
        session.add(
            ChildProfilePersonalization(
                child_profile_id=subject_a.id,
                slot_type="sibling_name",
                value_profile_id=sibling_b.id,
                ring2_enabled=False,
            )
        )
        sharer_guardian = await _guardian(session, sharer.id, "sharer-guardian-optout")
        viewer_guardian = await _guardian(session, viewer.id, "viewer-guardian-optout")
        connection = _connection(
            viewer.id, sharer.id, viewer_guardian.id, sharer_guardian.id
        )
        session.add(connection)
        await session.flush()
        # No consent row for A at all. B's own consent covers B's own name;
        # it has no bearing on anything read from A's side.
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
        headers=auth("viewer-guardian-optout"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subject_profile_id"] is None
    assert body["ring"] is None
    assert body["policy_version"] is None
    assert body["values"] == {}
    assert body["sentinel_pattern"] == SENTINEL_RE.pattern
    assert body["slot_bindings"] == {}


async def test_values_sibling_ring2_empty_when_neither_opted_in(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Design plan 8.8: neither A nor B opted in returns nothing.

    Confirms the shape above does not depend on B's participation: with A
    holding no sibling_name row at all and B never ring-2 enabled, the
    payload is the same universal empty shape.
    """
    async with sessions() as session:
        sharer = Family(name="Sharer-NeitherOptIn")
        viewer = Family(name="Viewer-NeitherOptIn")
        session.add_all([sharer, viewer])
        await session.flush()
        subject_a = ChildProfile(
            family_id=sharer.id, display_name="Subject A Neither", age_band="10-13"
        )
        sibling_b = ChildProfile(
            family_id=sharer.id, display_name="Sibling B Neither", age_band="10-13"
        )
        session.add_all([subject_a, sibling_b])
        await session.flush()
        # A has no personalization rows of any kind: no sibling_name slot, no
        # real-name opt-in. B's real_name_ring2_enabled is left False too.
        sharer_guardian = await _guardian(session, sharer.id, "sharer-guardian-neither")
        viewer_guardian = await _guardian(session, viewer.id, "viewer-guardian-neither")
        connection = _connection(
            viewer.id, sharer.id, viewer_guardian.id, sharer_guardian.id
        )
        session.add(connection)
        await session.flush()
        book = await _storybook(session, sharer.id, subject_a.id, visibility="catalog")
        await session.commit()
        book_id = book.id

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth("viewer-guardian-neither"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subject_profile_id"] is None
    assert body["ring"] is None
    assert body["policy_version"] is None
    assert body["values"] == {}
    assert body["sentinel_pattern"] == SENTINEL_RE.pattern
    assert body["slot_bindings"] == {}


@pytest.mark.parametrize(
    ("deactivated", "restricted"),
    [(True, False), (False, True)],
    ids=["deactivated", "processing_restricted"],
)
async def test_values_sibling_ring2_omitted_when_the_sibling_is_not_live(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    deactivated: bool,
    restricted: bool,
) -> None:
    """A deactivated or Article-18-restricted sibling's ring-2 name must not render.

    Mirrors ``test_ring1_sibling_name_is_dropped_when_the_sibling_is_not_live``
    for ring 2: ``_ring2_sibling_value`` already gates on ``_is_live``, but
    nothing pinned it directly. A's own protagonist_first_name slot stays
    present so a fix that collapsed the whole payload to empty, rather than
    omitting only the sibling slot, would still fail here.
    """
    async with sessions() as session:
        sharer = Family(name="Sharer-Ring2SiblingLiveness")
        viewer = Family(name="Viewer-Ring2SiblingLiveness")
        session.add_all([sharer, viewer])
        await session.flush()
        subject_a = ChildProfile(
            family_id=sharer.id,
            display_name="Ring2 Liveness Subject",
            age_band="10-13",
            real_name_ring2_enabled=True,
        )
        sibling_b = ChildProfile(
            family_id=sharer.id,
            display_name="Ring2 Liveness Sibling",
            age_band="10-13",
            real_name_ring2_enabled=True,
            deactivated_at=datetime.now(UTC) if deactivated else None,
            processing_restricted_at=datetime.now(UTC) if restricted else None,
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
        sharer_guardian = await _guardian(
            session, sharer.id, "sharer-guardian-ring2liveness"
        )
        viewer_guardian = await _guardian(
            session, viewer.id, "viewer-guardian-ring2liveness"
        )
        connection = _connection(
            viewer.id, sharer.id, viewer_guardian.id, sharer_guardian.id
        )
        session.add(connection)
        await session.flush()
        # A's own consent covers both A's own name and the sibling slot.
        session.add(
            PersonalizationDisclosureConsent(
                child_profile_id=subject_a.id,
                family_connection_id=connection.id,
                covered_slot_types=["protagonist_first_name", "sibling_name"],
                sibling_authority_attested=True,
                consent_accepted_at=datetime.now(UTC),
                consent_policy_version="v1",
                consent_signer_name="Sharer Guardian",
                consent_ip="127.0.0.1",
            )
        )
        # B's own consent covers B's own name; irrelevant here since B fails
        # the liveness check before its own settings are ever consulted.
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
        headers=auth("viewer-guardian-ring2liveness"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["values"]["protagonist_first_name"] == "Ring2 Liveness Subject"
    assert "sibling_name" not in body["values"], (
        "a non-live sibling's real name reached a ring-2 payload"
    )


async def test_values_device_principal_in_unrelated_family_empty(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    stranger: Stranger,
) -> None:
    """A DEVICE principal gets the empty payload, never a 403.

    This route has no guardian gate (its own docstring's rationale: a kid's
    tablet must be able to render a personalized book), so a DEVICE-role
    token minted for a family with no connection to the sharer must land on
    the same unconnected-family empty payload as any other principal type,
    not on an authorization error.
    """
    async with sessions() as session:
        book_id, _viewer_token = await _build_ring2_scenario(session)

    device_token = await mint_device_token(client, stranger.guardian_token)
    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth(device_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ring"] is None
    assert body["values"] == {}


async def test_values_child_session_in_unrelated_family_empty(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    stranger: Stranger,
) -> None:
    """A child session in a family with no connection gets the empty payload.

    ``test_values_child_session_in_viewer_family_succeeds`` above proves a
    child IN the viewer family can read a full ring-2 payload; this proves
    the flip side, a child session outside any connection to the sharer,
    lands on the same empty payload a guardian would, never a 403.
    """
    async with sessions() as session:
        book_id, _viewer_token = await _build_ring2_scenario(session)

    resp = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth(stranger.child_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ring"] is None
    assert body["values"] == {}


async def test_values_empty_after_the_subject_profile_is_deleted(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Deleting the subject profile is the erasure mechanism (plan 8.2/8.7).

    ``Storybook.personalization_subject_profile_id`` is ON DELETE SET NULL:
    severing the link, not cascading the book away, is how the subject's
    erasure request reaches every book that named them.
    """
    async with sessions() as session:
        book_id, viewer_token = await _build_ring2_scenario(session)

    before = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth(viewer_token),
    )
    assert before.status_code == 200, before.text
    assert before.json()["values"] == {"pet_name": "Ring2Pet"}

    async with sessions() as session:
        book = await session.get(Storybook, book_id)
        assert book is not None
        subject_id = book.personalization_subject_profile_id
        assert subject_id is not None
        subject = await session.get(ChildProfile, subject_id)
        assert subject is not None
        await session.delete(subject)
        await session.commit()

    after = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth(viewer_token),
    )
    assert after.status_code == 200, after.text
    body = after.json()
    assert body["subject_profile_id"] is None
    assert body["ring"] is None
    assert body["values"] == {}


async def test_values_sibling_slot_gone_after_the_sibling_profile_is_deleted(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """B's own profile deletion removes only the sibling slot, not A's payload.

    ``ChildProfilePersonalization.value_profile_id`` is ON DELETE CASCADE:
    deleting sibling B's profile deletes A's sibling_name row that pointed at
    B outright, rather than leaving a dangling reference for
    ``_ring2_sibling_value`` to discover and log at read time. A's own name
    must still render.
    """
    async with sessions() as session:
        sharer = Family(name="Sharer-SiblingDeletion")
        viewer = Family(name="Viewer-SiblingDeletion")
        session.add_all([sharer, viewer])
        await session.flush()
        subject_a = ChildProfile(
            family_id=sharer.id,
            display_name="Deletion Subject A",
            age_band="10-13",
            real_name_ring2_enabled=True,
        )
        sibling_b = ChildProfile(
            family_id=sharer.id,
            display_name="Deletion Sibling B",
            age_band="10-13",
            real_name_ring2_enabled=True,
        )
        session.add_all([subject_a, sibling_b])
        await session.flush()
        sibling_b_id = sibling_b.id
        session.add(
            ChildProfilePersonalization(
                child_profile_id=subject_a.id,
                slot_type="sibling_name",
                value_profile_id=sibling_b.id,
                ring2_enabled=True,
            )
        )
        sharer_guardian = await _guardian(
            session, sharer.id, "sharer-guardian-sibdeletion"
        )
        viewer_guardian = await _guardian(
            session, viewer.id, "viewer-guardian-sibdeletion"
        )
        connection = _connection(
            viewer.id, sharer.id, viewer_guardian.id, sharer_guardian.id
        )
        session.add(connection)
        await session.flush()
        session.add(
            PersonalizationDisclosureConsent(
                child_profile_id=subject_a.id,
                family_connection_id=connection.id,
                covered_slot_types=["protagonist_first_name", "sibling_name"],
                sibling_authority_attested=True,
                consent_accepted_at=datetime.now(UTC),
                consent_policy_version="v1",
                consent_signer_name="Sharer Guardian",
                consent_ip="127.0.0.1",
            )
        )
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

    before = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth("viewer-guardian-sibdeletion"),
    )
    assert before.status_code == 200, before.text
    assert before.json()["values"]["sibling_name"] == "Deletion Sibling B"

    async with sessions() as session:
        sibling = await session.get(ChildProfile, sibling_b_id)
        assert sibling is not None
        await session.delete(sibling)
        await session.commit()

    after = await client.get(
        f"/api/v1/storybooks/{book_id}/personalization-values",
        headers=auth("viewer-guardian-sibdeletion"),
    )
    assert after.status_code == 200, after.text
    body = after.json()
    assert body["values"]["protagonist_first_name"] == "Deletion Subject A"
    assert "sibling_name" not in body["values"]


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
