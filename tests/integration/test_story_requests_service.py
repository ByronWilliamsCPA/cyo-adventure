"""Integration tests for the story-request service's series/anchor handling.

WS-B PR 3 (Task 4): ``resolve_anchor`` and ``load_anchor_context`` run real
queries against a published, series-linked anchor storybook, which the
unit-level ``_FakeSession`` double in tests/unit/test_story_requests.py
cannot provide, so the band-mismatch and anchor-context cases run here
against a real Postgres session instead. Mirrors the
``tests/integration/test_publishing_service.py`` pattern: seed a family,
guardian, and story rows directly via the ``sessions`` fixture, then call the
service layer, bypassing the HTTP API and its endpoint-level authorization.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.api.deps import Principal
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import Concept, Family, StoryRequest, User
from cyo_adventure.story_requests import service
from cyo_adventure.story_requests.service import ApprovalConfirmation
from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle

from ._series_utils import seed_published_anchor

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _principal(user_id: uuid.UUID, family_id: uuid.UUID) -> Principal:
    """Build a guardian Principal for service-layer tests."""
    return Principal(
        subject="g",
        user_id=user_id,
        role="guardian",  # pyright: ignore[reportArgumentType]
        family_id=family_id,
        profile_ids=frozenset(),
    )


async def test_approve_anchored_request_band_mismatch_raises(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A confirmed band that differs from the anchor's series band is a 422
    (``resolve_anchor``'s band check), not a silent series fork."""
    async with sessions() as session:
        fam = Family(name="Fam")
        session.add(fam)
        await session.flush()
        guardian = User(family_id=fam.id, role="guardian", authn_subject="g")
        session.add(guardian)
        await session.flush()
        _series, storybook = await seed_published_anchor(
            session, family_id=fam.id, approved_by=guardian.id, age_band="8-11"
        )
        principal = _principal(guardian.id, fam.id)
        request = StoryRequest(
            family_id=fam.id,
            request_text="book two of the fox saga",
            status="pending",
            age_band="8-11",
            anchor_storybook_id=storybook.id,
        )

        with pytest.raises(ValidationError, match="age band"):
            await service.approve_story_request(
                session,
                principal,
                request,
                confirmation=ApprovalConfirmation(
                    age_band=AgeBand.BAND_13_16,
                    length=Length.MEDIUM,
                    narrative_style=NarrativeStyle.PROSE,
                ),
            )


async def test_build_concept_anchored_request_includes_anchor_context(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """``_build_concept`` on an anchored request loads the anchor's title
    into the persisted concept's brief: the shared soft-continuation tail
    both approval and authored creation run through."""
    async with sessions() as session:
        fam = Family(name="Fam")
        session.add(fam)
        await session.flush()
        guardian = User(family_id=fam.id, role="guardian", authn_subject="g")
        session.add(guardian)
        await session.flush()
        _series, storybook = await seed_published_anchor(
            session,
            family_id=fam.id,
            approved_by=guardian.id,
            age_band="8-11",
            title="The First Chapter",
        )
        principal = _principal(guardian.id, fam.id)
        request = StoryRequest(
            family_id=fam.id,
            request_text="book two of the fox saga",
            status="pending",
            age_band="8-11",
            anchor_storybook_id=storybook.id,
        )
        session.add(request)
        await session.flush()

        # Whitebox: exercises the shared concept-building tail directly, the
        # same seam approve_story_request and create_authored_request share.
        concept_id = await service._build_concept(session, principal, request, None)

        assert request.status == "approved"
        assert str(request.concept_id) == concept_id
        concept = await session.get(Concept, request.concept_id)
        assert concept is not None
        assert concept.brief["anchor_context"]["title"] == "The First Chapter"
