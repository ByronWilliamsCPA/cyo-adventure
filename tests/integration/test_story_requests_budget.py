"""Integration tests for the ADR-015 budget-consent delta.

Covers the guardian cost gate (G7: family monthly quota), per-child
pre-authorization envelopes (G3: auto-approval at request creation), and the
GET /families/me/budget balance-exposure endpoint. Quota/envelope/spend
scenarios need real counting queries (grouped by family/profile and filtered
on ``approved_at``), which the hand-rolled ``_FakeSession`` in
tests/unit/test_story_requests.py cannot express; this module mirrors
test_story_requests_service.py's pattern (seed rows directly via the
``sessions`` fixture, call the service layer or the HTTP API) for exactly
that reason.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from cyo_adventure.api.deps import Principal
from cyo_adventure.core.config import settings
from cyo_adventure.core.exceptions import StateTransitionError
from cyo_adventure.db.models import ChildProfile, Concept, Family, StoryRequest, User
from cyo_adventure.story_requests import service
from cyo_adventure.story_requests.service import ApprovalConfirmation
from cyo_adventure.storybook.models import AgeBand, Length, NarrativeStyle
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_CREATE = "/api/v1/story-requests"
_AUTHORED = "/api/v1/story-requests/authored"
_BUDGET = "/api/v1/families/me/budget"
_CONFIRMATION = {"age_band": "10-13", "length": "medium", "narrative_style": "prose"}


def _guardian_principal(user_id: uuid.UUID, family_id: uuid.UUID) -> Principal:
    return Principal(
        subject="g",
        user_id=user_id,
        role="guardian",  # pyright: ignore[reportArgumentType]
        family_id=family_id,
        profile_ids=frozenset(),
    )


def _admin_principal(user_id: uuid.UUID, family_id: uuid.UUID) -> Principal:
    return Principal(
        subject="a",
        user_id=user_id,
        role="admin",  # pyright: ignore[reportArgumentType]
        family_id=family_id,
        profile_ids=frozenset(),
        is_admin=True,
    )


async def _seed_approved_request(
    session: AsyncSession,
    *,
    family_id: uuid.UUID,
    profile_id: uuid.UUID | None,
    approved_at: datetime,
) -> StoryRequest:
    """Insert an already-``approved`` StoryRequest with a specific approved_at.

    Bypasses the service layer entirely: these rows exist only to be COUNTED
    by the budget queries under test, so they are built directly rather than
    run through the real approve flow (which would itself be gated by the
    quota this fixture is trying to pre-populate).
    """
    row = StoryRequest(
        family_id=family_id,
        profile_id=profile_id,
        request_text="a seeded approved request",
        status="approved",
        age_band="10-13",
        length="short",
        narrative_style="prose",
        approved_at=approved_at,
    )
    session.add(row)
    await session.flush()
    return row


async def test_family_monthly_spend_excludes_prior_month_at_the_boundary(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """The last instant of June does not count toward a spend query pinned to July.

    Both timestamps are deliberately adjacent to the UTC month boundary
    (23:59:59 June 30 vs 00:00:00 July 1) so the test would fail if the
    derivation used a wrong boundary (e.g. off-by-one-day, or a naive/local
    time zone rather than UTC).
    """
    async with sessions() as session:
        fam = Family(name="Boundary Family")
        session.add(fam)
        await session.flush()
        await _seed_approved_request(
            session,
            family_id=fam.id,
            profile_id=None,
            approved_at=datetime(2026, 6, 30, 23, 59, 59, tzinfo=UTC),
        )
        await _seed_approved_request(
            session,
            family_id=fam.id,
            profile_id=None,
            approved_at=datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC),
        )
        await session.commit()

    async with sessions() as session:
        spend = await service.family_monthly_spend(
            session, fam.id, now=datetime(2026, 7, 15, 12, 0, 0, tzinfo=UTC)
        )
        assert spend == 1


async def test_enforce_family_quota_blocks_and_creates_nothing(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A family at its quota is blocked with 409; no Concept is created."""
    async with sessions() as session:
        fam = Family(name="At Quota", monthly_story_quota=1)
        session.add(fam)
        await session.flush()
        guardian = User(family_id=fam.id, role="guardian", authn_subject="g")
        session.add(guardian)
        await session.flush()
        await _seed_approved_request(
            session,
            family_id=fam.id,
            profile_id=None,
            approved_at=datetime(2026, 7, 10, tzinfo=UTC),
        )
        request = StoryRequest(
            family_id=fam.id,
            request_text="one story too many",
            status="pending",
            age_band="10-13",
        )
        session.add(request)
        await session.flush()
        await session.commit()

    principal = _guardian_principal(guardian.id, fam.id)
    async with sessions() as session:
        pending = await session.get(StoryRequest, request.id)
        assert pending is not None
        with pytest.raises(StateTransitionError, match="monthly story budget reached"):
            await service.approve_story_request(
                session,
                principal,
                pending,
                confirmation=ApprovalConfirmation(
                    age_band=AgeBand.BAND_10_13,
                    length=Length.MEDIUM,
                    narrative_style=NarrativeStyle.PROSE,
                ),
                now=datetime(2026, 7, 15, tzinfo=UTC),
            )
        await session.rollback()

    async with sessions() as session:
        concepts = (await session.scalars(select(Concept))).all()
        assert len(concepts) == 0
        reloaded = await session.get(StoryRequest, request.id)
        assert reloaded is not None
        assert reloaded.status == "pending"


async def test_enforce_family_quota_passes_under_quota(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A family under its quota approves normally and a Concept is created."""
    async with sessions() as session:
        fam = Family(name="Under Quota", monthly_story_quota=5)
        session.add(fam)
        await session.flush()
        guardian = User(family_id=fam.id, role="guardian", authn_subject="g2")
        session.add(guardian)
        await session.flush()
        await _seed_approved_request(
            session,
            family_id=fam.id,
            profile_id=None,
            approved_at=datetime(2026, 7, 10, tzinfo=UTC),
        )
        request = StoryRequest(
            family_id=fam.id,
            request_text="well within budget",
            status="pending",
            age_band="10-13",
        )
        session.add(request)
        await session.flush()
        await session.commit()

    principal = _guardian_principal(guardian.id, fam.id)
    async with sessions() as session:
        pending = await session.get(StoryRequest, request.id)
        assert pending is not None
        concept_id = await service.approve_story_request(
            session,
            principal,
            pending,
            confirmation=ApprovalConfirmation(
                age_band=AgeBand.BAND_10_13,
                length=Length.MEDIUM,
                narrative_style=NarrativeStyle.PROSE,
            ),
            now=datetime(2026, 7, 15, tzinfo=UTC),
        )
        assert concept_id
        await session.commit()


async def test_enforce_family_quota_admin_bypasses(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """An admin principal approves past a family already at its quota."""
    async with sessions() as session:
        fam = Family(name="Admin Bypass", monthly_story_quota=1)
        session.add(fam)
        await session.flush()
        admin_user = User(
            family_id=fam.id, role="admin", is_admin=True, authn_subject="a1"
        )
        session.add(admin_user)
        await session.flush()
        await _seed_approved_request(
            session,
            family_id=fam.id,
            profile_id=None,
            approved_at=datetime(2026, 7, 10, tzinfo=UTC),
        )
        request = StoryRequest(
            family_id=fam.id,
            request_text="platform-funded catalog request",
            status="pending",
            age_band="10-13",
        )
        session.add(request)
        await session.flush()
        await session.commit()

    principal = _admin_principal(admin_user.id, fam.id)
    async with sessions() as session:
        pending = await session.get(StoryRequest, request.id)
        assert pending is not None
        concept_id = await service.approve_story_request(
            session,
            principal,
            pending,
            confirmation=ApprovalConfirmation(
                age_band=AgeBand.BAND_10_13,
                length=Length.MEDIUM,
                narrative_style=NarrativeStyle.PROSE,
            ),
            now=datetime(2026, 7, 15, tzinfo=UTC),
        )
        assert concept_id


async def test_authored_guardian_blocked_by_quota_via_http(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """POST /story-requests/authored by a guardian is also gated by quota."""
    async with sessions() as session:
        fam = await session.get(Family, seed.family_id)
        assert fam is not None
        fam.monthly_story_quota = 0
        await session.commit()

    res = await client.post(
        _AUTHORED,
        json={
            "request_text": "an authored request over quota",
            "age_band": "8-11",
            "length": "short",
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 409, res.text

    async with sessions() as session:
        concepts = (
            await session.scalars(select(Concept).where(Concept.family_id == fam.id))
        ).all()
        assert len(concepts) == 0


async def test_authored_admin_bypasses_quota_via_http(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """An admin's authored request bypasses even a zeroed-out family quota."""
    async with sessions() as session:
        fam = await session.get(Family, seed.family_id)
        assert fam is not None
        fam.monthly_story_quota = 0
        await session.commit()

    res = await client.post(
        _AUTHORED,
        json={
            "request_text": "a platform-funded catalog request",
            "age_band": "8-11",
            "length": "short",
            "family_id": str(seed.family_id),
        },
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "approved"
    assert res.json()["concept_id"]


async def test_auto_approve_within_envelope(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A child's request auto-approves when the profile's envelope allows it."""
    async with sessions() as session:
        profile = await session.get(ChildProfile, seed.child_profile_id)
        assert profile is not None
        profile.request_auto_approve = True
        profile.monthly_request_envelope = 5
        await session.commit()

    res = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a story auto-approved by pre-authorization",
        },
        headers=auth(seed.child_token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "approved"

    async with sessions() as session:
        row = await session.get(StoryRequest, uuid.UUID(body["id"]))
        assert row is not None
        assert row.status == "approved"
        assert row.concept_id is not None
        assert row.approved_at is not None
        # The initiator stays the child: pre-authorization delegates the
        # click, never the liability (ADR-015).
        assert row.initiator_role == "child"
        assert row.length == "short"
        assert row.narrative_style == "prose"


async def test_auto_approve_refused_when_envelope_exhausted_falls_back_to_pending(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """An exhausted per-child envelope leaves the row pending, not an error."""
    async with sessions() as session:
        profile = await session.get(ChildProfile, seed.child_profile_id)
        assert profile is not None
        profile.request_auto_approve = True
        profile.monthly_request_envelope = 1
        await session.flush()
        # Pre-fill the one-request envelope for THIS profile this month.
        await _seed_approved_request(
            session,
            family_id=seed.family_id,
            profile_id=seed.child_profile_id,
            approved_at=datetime.now(UTC),
        )
        await session.commit()

    res = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a request beyond this child's own envelope",
        },
        headers=auth(seed.child_token),
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "pending"


async def test_auto_approve_refused_when_family_quota_exhausted_falls_back_to_pending(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A family at its own quota still leaves the row pending, not an error,
    even though the child's own envelope has room."""
    async with sessions() as session:
        fam = await session.get(Family, seed.family_id)
        assert fam is not None
        fam.monthly_story_quota = 0
        profile = await session.get(ChildProfile, seed.child_profile_id)
        assert profile is not None
        profile.request_auto_approve = True
        profile.monthly_request_envelope = 10
        await session.commit()

    res = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a request the family budget cannot cover",
        },
        headers=auth(seed.child_token),
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "pending"


async def test_blocked_screening_never_auto_approves(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """A bright-line-blocked wish never auto-approves, even with a wide-open
    envelope and quota (PII guard fires ahead of the auto-approve check)."""
    async with sessions() as session:
        profile = await session.get(ChildProfile, seed.child_profile_id)
        assert profile is not None
        profile.request_auto_approve = True
        profile.monthly_request_envelope = 99
        child_name = profile.display_name
        await session.commit()

    res = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": f"a story starring {child_name} the brave",
        },
        headers=auth(seed.child_token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "blocked"

    async with sessions() as session:
        row = await session.get(StoryRequest, uuid.UUID(body["id"]))
        assert row is not None
        assert row.status == "blocked"
        assert row.concept_id is None
        assert row.approved_at is None


async def test_budget_endpoint_math(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """GET /families/me/budget reports quota/spent/remaining and per-child usage."""
    async with sessions() as session:
        fam = await session.get(Family, seed.family_id)
        assert fam is not None
        fam.monthly_story_quota = 3
        profile = await session.get(ChildProfile, seed.child_profile_id)
        assert profile is not None
        profile.request_auto_approve = True
        profile.monthly_request_envelope = 2
        now = datetime.now(UTC)
        await _seed_approved_request(
            session,
            family_id=seed.family_id,
            profile_id=seed.child_profile_id,
            approved_at=now,
        )
        await session.commit()

    res = await client.get(_BUDGET, headers=auth(seed.guardian_token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["quota"] == 3
    assert body["spent_this_month"] == 1
    assert body["remaining"] == 2
    child = next(
        c for c in body["children"] if c["profile_id"] == str(seed.child_profile_id)
    )
    assert child["request_auto_approve"] is True
    assert child["monthly_request_envelope"] == 2
    assert child["used_this_month"] == 1


async def test_budget_endpoint_uses_platform_default_when_quota_unset(
    client: AsyncClient, seed: Seed
) -> None:
    """An un-customized family reports the platform default quota."""
    res = await client.get(_BUDGET, headers=auth(seed.guardian_token))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["quota"] == settings.default_monthly_story_quota
    assert body["spent_this_month"] == 0
    assert body["remaining"] == settings.default_monthly_story_quota


async def test_budget_endpoint_child_is_403(client: AsyncClient, seed: Seed) -> None:
    """A child token cannot read the family budget (adults-only surface)."""
    res = await client.get(_BUDGET, headers=auth(seed.child_token))
    assert res.status_code == 403, res.text


async def test_budget_endpoint_device_is_403(client: AsyncClient, seed: Seed) -> None:
    """A device grant token cannot read the family budget (adults-only surface)."""
    from tests.integration.conftest import mint_device_token

    device_token = await mint_device_token(client, seed.guardian_token)
    res = await client.get(_BUDGET, headers=auth(device_token))
    assert res.status_code == 403, res.text


async def test_budget_endpoint_admin_own_family(
    client: AsyncClient, seed: Seed
) -> None:
    """An admin token also reads the (admin's own) family budget."""
    res = await client.get(_BUDGET, headers=auth(seed.admin_token))
    assert res.status_code == 200, res.text
