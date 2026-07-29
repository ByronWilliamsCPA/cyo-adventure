"""Ring-2 disclosure consent tombstone behaviour (ADR-023 P4, design plan 5.3).

``personalization_disclosure_consent.family_connection_id`` is ``ON DELETE
SET NULL``, never CASCADE: deleting the ``family_connection`` a consent was
granted on must not destroy the evidence that consent was given, but
deleting the CHILD PROFILE (the data subject) must remove the whole row,
because the data subject is gone. This is the one FK on this table that
deviates from the project's usual CASCADE-everything-child-linked pattern
(see ``PersonalizationDisclosureConsent``'s docstring in ``db/models.py``),
so it gets its own focused round-trip test rather than folding into
``test_deletion_drill.py`` (whose extension for the CASCADE half, and the
export surface, is Task B3's).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import (
    ChildProfile,
    Family,
    FamilyConnection,
    PersonalizationDisclosureConsent,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_connection_delete_tombstones_then_profile_delete_removes(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """Connection deletion nulls the FK and keeps the row; profile deletion
    removes it entirely.
    """
    async with sessions() as session:
        sharer = Family(name="Sharer Family")
        viewer = Family(name="Viewer Family")
        session.add_all([sharer, viewer])
        await session.flush()

        subject = ChildProfile(
            family_id=sharer.id, display_name="Alex", age_band="10-13"
        )
        session.add(subject)
        await session.flush()
        subject_id = subject.id

        connection = FamilyConnection(
            family_id=viewer.id, connected_family_id=sharer.id
        )
        session.add(connection)
        await session.flush()

        consent = PersonalizationDisclosureConsent(
            child_profile_id=subject.id,
            family_connection_id=connection.id,
            connected_family_label="Viewer Family",
            covered_slot_types=["protagonist_first_name"],
            consent_accepted_at=datetime.now(UTC),
            consent_policy_version="v1",
            consent_signer_name="Alex's Guardian",
            consent_ip="127.0.0.1",
        )
        session.add(consent)
        await session.commit()
        consent_id = consent.id

    # Delete the connection: the consent row must survive, tombstoned.
    async with sessions() as session:
        connection = await session.get(FamilyConnection, connection.id)
        assert connection is not None
        await session.delete(connection)
        await session.commit()

    async with sessions() as session:
        row = await session.get(PersonalizationDisclosureConsent, consent_id)
        assert row is not None, "tombstone row must survive connection deletion"
        assert row.family_connection_id is None
        assert row.child_profile_id == subject_id
        assert row.connected_family_label == "Viewer Family"
        assert row.consent_signer_name == "Alex's Guardian"
        assert row.consent_accepted_at is not None

    # Now delete the subject profile (the data subject): the tombstoned row
    # must be gone, since there is nothing left to evidence.
    async with sessions() as session:
        profile = await session.get(ChildProfile, subject_id)
        assert profile is not None
        await session.delete(profile)
        await session.commit()

    async with sessions() as session:
        row = await session.get(PersonalizationDisclosureConsent, consent_id)
        assert row is None, "profile deletion must remove the consent row entirely"


async def test_profile_delete_removes_live_untombstoned_consent(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A still-live (non-tombstoned) consent also CASCADEs on profile deletion."""
    async with sessions() as session:
        sharer = Family(name="Sharer Family 2")
        viewer = Family(name="Viewer Family 2")
        session.add_all([sharer, viewer])
        await session.flush()

        subject = ChildProfile(
            family_id=sharer.id, display_name="Mateo", age_band="10-13"
        )
        session.add(subject)
        await session.flush()
        subject_id = subject.id

        connection = FamilyConnection(
            family_id=viewer.id, connected_family_id=sharer.id
        )
        session.add(connection)
        await session.flush()

        consent = PersonalizationDisclosureConsent(
            child_profile_id=subject.id,
            family_connection_id=connection.id,
            covered_slot_types=["pet_name"],
        )
        session.add(consent)
        await session.commit()
        consent_id = consent.id

    async with sessions() as session:
        profile = await session.get(ChildProfile, subject_id)
        assert profile is not None
        await session.delete(profile)
        await session.commit()

    async with sessions() as session:
        row = await session.get(PersonalizationDisclosureConsent, consent_id)
        assert row is None
