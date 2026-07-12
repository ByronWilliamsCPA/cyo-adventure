"""Integration tests for the child story-request endpoints."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import func, select

from cyo_adventure.db.models import ChildProfile, Concept, GenerationJob, StoryRequest
from tests.integration.conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio

_CREATE = "/api/v1/story-requests"

# WS-B: approve requires a confirmation body. This mirrors the seeded
# profile's own age band (see conftest.Seed's profile_a, age_band="10-13")
# so existing behavioral tests that were not exercising the confirmation
# contract keep passing unchanged.
_CONFIRMATION = {"age_band": "10-13", "length": "medium", "narrative_style": "prose"}


async def _create_pending_request(
    client: AsyncClient, seed: Seed, *, request_text: str = "a fox"
) -> str:
    """Submit a pending request for the seeded child profile; return its id."""
    res = await client.post(
        _CREATE,
        json={"profile_id": str(seed.child_profile_id), "request_text": request_text},
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 201, res.text
    return str(res.json()["id"])


async def test_guardian_creates_pending_request(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian submits a request for a family profile; it is pending."""
    res = await client.post(
        _CREATE,
        json={"profile_id": str(seed.child_profile_id), "request_text": "a brave fox"},
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "pending"


async def test_child_creates_own_profile_request(
    client: AsyncClient, seed: Seed
) -> None:
    """A child token may submit a request for its own profile (own-profile-only)."""
    res = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a curious cat",
        },
        headers=auth(seed.child_token),
    )
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "pending"


async def test_create_rejects_cross_family_profile(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian cannot submit for another family's profile (403)."""
    res = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.other_child_profile_id),
            "request_text": "a brave fox",
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 403


async def test_admin_cannot_create_request(client: AsyncClient, seed: Seed) -> None:
    """An admin has no profiles of its own, so it cannot submit a request (403)."""
    res = await client.post(
        _CREATE,
        json={"profile_id": str(seed.child_profile_id), "request_text": "a brave fox"},
        headers=auth(seed.admin_token),
    )
    assert res.status_code == 403


async def test_create_blocks_pii(client: AsyncClient, seed: Seed) -> None:
    """A request naming the real child (Reader A) is blocked, not pending."""
    res = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a story about Reader A",
        },
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 201
    assert res.json()["status"] == "blocked"


async def test_pending_cap_returns_409(client: AsyncClient, seed: Seed) -> None:
    """The sixth pending request for a profile is refused with 409."""
    for _ in range(5):
        ok = await client.post(
            _CREATE,
            json={"profile_id": str(seed.child_profile_id), "request_text": "idea"},
            headers=auth(seed.guardian_token),
        )
        assert ok.status_code == 201
    over = await client.post(
        _CREATE,
        json={"profile_id": str(seed.child_profile_id), "request_text": "one more"},
        headers=auth(seed.guardian_token),
    )
    assert over.status_code == 409


async def test_guardian_lists_family_requests(client: AsyncClient, seed: Seed) -> None:
    """The guardian sees its family's pending requests, filterable by profile."""
    await client.post(
        _CREATE,
        json={"profile_id": str(seed.child_profile_id), "request_text": "a fox"},
        headers=auth(seed.guardian_token),
    )
    res = await client.get(
        f"{_CREATE}?status=pending&profile_id={seed.child_profile_id}",
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 200
    assert len(res.json()["requests"]) == 1


async def test_list_is_family_scoped_for_every_caller(
    client: AsyncClient, seed: Seed
) -> None:
    """GET /story-requests never widens past the caller's family.

    The surface selects the scope: a family-B request must be invisible to
    family A's guardian, to the dual-role adult (guardian + admin
    capability), and to the admin-only user on THIS surface, even though
    the latter two can read it on the admin surface. Before the dual-role
    change an admin token was global here, which would have silently turned
    a dual-role guardian's everyday request list into a cross-family view.
    """
    request_id = await _create_pending_request(client, seed)
    other = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.other_child_profile_id),
            "request_text": "an otter",
        },
        headers=auth(seed.other_guardian_token),
    )
    assert other.status_code == 201, other.text
    other_id = str(other.json()["id"])

    for token in (seed.guardian_token, seed.dual_token, seed.admin_token):
        res = await client.get(_CREATE, headers=auth(token))
        assert res.status_code == 200, res.text
        ids = {r["id"] for r in res.json()["requests"]}
        assert other_id not in ids, f"family-B row leaked to {token}"
        assert request_id in ids, f"own-family row missing for {token}"


async def test_admin_surface_lists_all_families(
    client: AsyncClient, seed: Seed
) -> None:
    """GET /admin/story-requests is the global queue, admin capability only."""
    request_id = await _create_pending_request(client, seed)
    other = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.other_child_profile_id),
            "request_text": "an otter",
        },
        headers=auth(seed.other_guardian_token),
    )
    assert other.status_code == 201, other.text
    other_id = str(other.json()["id"])

    for token in (seed.admin_token, seed.dual_token):
        res = await client.get("/api/v1/admin/story-requests", headers=auth(token))
        assert res.status_code == 200, res.text
        ids = {r["id"] for r in res.json()["requests"]}
        assert {request_id, other_id} <= ids

    denied = await client.get(
        "/api/v1/admin/story-requests", headers=auth(seed.guardian_token)
    )
    assert denied.status_code == 403


async def test_child_lists_only_own_profile_requests(
    client: AsyncClient,
    sessions: async_sessionmaker[AsyncSession],
    seed: Seed,
) -> None:
    """A child token listing with no profile_id sees only its own requests.

    A child session is scoped to its own profile: it must never read a
    sibling's request text just by omitting the profile_id filter. This pins
    the family filter alone is insufficient for a child; the own-profile
    constraint is what confines the list.
    """
    own_id = await _create_pending_request(client, seed)
    # A sibling profile in the SAME family, with its own request inserted
    # directly (the child cannot create for a profile it does not own).
    async with sessions() as session:
        sibling = ChildProfile(
            family_id=seed.family_id, display_name="Reader A2", age_band="8-11"
        )
        session.add(sibling)
        await session.flush()
        sibling_request = StoryRequest(
            family_id=seed.family_id,
            profile_id=sibling.id,
            request_text="a sibling's secret idea",
            status="pending",
            moderation_flags={"blocked": False, "flags": []},
            age_band="8-11",
            initiator_role="child",
        )
        session.add(sibling_request)
        await session.commit()
        sibling_request_id = str(sibling_request.id)

    res = await client.get(_CREATE, headers=auth(seed.child_token))
    assert res.status_code == 200, res.text
    ids = {r["id"] for r in res.json()["requests"]}
    assert own_id in ids
    assert sibling_request_id not in ids, "child leaked a sibling's request"


async def test_list_rejects_inaccessible_profile_filter(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian filtering by another family's profile id gets 403."""
    res = await client.get(
        f"{_CREATE}?profile_id={seed.other_child_profile_id}",
        headers=auth(seed.guardian_token),
    )
    assert res.status_code == 403


async def test_list_rejects_invalid_status(client: AsyncClient, seed: Seed) -> None:
    """An unrecognized status filter value is a 422, not a silent empty list."""
    res = await client.get(f"{_CREATE}?status=nope", headers=auth(seed.guardian_token))
    assert res.status_code == 422


async def test_admin_approve_creates_concept_but_no_job(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """An admin approves a pending request; a concept is created but no
    GenerationJob yet (that requires POST .../authoring-plan)."""
    created = await client.post(
        _CREATE,
        json={"profile_id": str(seed.child_profile_id), "request_text": "a fox"},
        headers=auth(seed.guardian_token),
    )
    req_id = created.json()["id"]
    res = await client.post(
        f"{_CREATE}/{req_id}/approve",
        headers=auth(seed.admin_token),
        json=_CONFIRMATION,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "approved"
    assert body["concept_id"]
    assert "job_id" not in body

    async with sessions() as session:
        job = await session.scalar(
            select(GenerationJob).where(
                GenerationJob.concept_id == uuid.UUID(body["concept_id"])
            )
        )
        assert job is None


async def test_admin_approve_is_global_across_families(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """An admin (family A) can approve a request from family B (global scope).

    The created Concept (and its GenerationJob) must be stamped with the
    REQUEST's own family (family B), not the approving admin's family
    (family A). Stamping from the principal instead of the request would
    silently misfile family B's story into family A.
    """
    request_text = "a kind whale"
    created = await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.other_child_profile_id),
            "request_text": request_text,
        },
        headers=auth(seed.other_guardian_token),
    )
    assert created.status_code == 201, created.text
    req_id = created.json()["id"]
    res = await client.post(
        f"{_CREATE}/{req_id}/approve",
        headers=auth(seed.admin_token),
        json=_CONFIRMATION,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "approved"
    concept_id = body["concept_id"]

    async with sessions() as session:
        profile_b = await session.get(ChildProfile, seed.other_child_profile_id)
        assert profile_b is not None
        request_family_id = profile_b.family_id
        # The admin's own family must differ from the request's family, or
        # this test cannot distinguish "stamped from request" from "stamped
        # from principal".
        assert request_family_id != seed.family_id

        concept = await session.get(Concept, uuid.UUID(concept_id))
        assert concept is not None
        assert concept.family_id == request_family_id
        assert concept.family_id != seed.family_id
        assert concept.brief["premise"] == request_text


async def test_approve_stamps_reviewer_and_builds_brief_from_stored_text(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """Approval stamps status/reviewed_by/reviewed_at and the brief premise is
    the request's own stored text (not some other source)."""
    request_text = "a story about a lighthouse keeper and a curious seal"
    created = await client.post(
        _CREATE,
        json={"profile_id": str(seed.child_profile_id), "request_text": request_text},
        headers=auth(seed.guardian_token),
    )
    req_id = created.json()["id"]
    res = await client.post(
        f"{_CREATE}/{req_id}/approve",
        headers=auth(seed.admin_token),
        json=_CONFIRMATION,
    )
    assert res.status_code == 200, res.text
    concept_id = res.json()["concept_id"]

    async with sessions() as session:
        row = await session.get(StoryRequest, uuid.UUID(req_id))
        assert row is not None
        assert row.status == "approved"
        assert row.reviewed_by == seed.admin_user_id
        assert row.reviewed_at is not None
        assert str(row.concept_id) == concept_id

        concept = await session.get(Concept, uuid.UUID(concept_id))
        assert concept is not None
        assert concept.brief["premise"] == request_text


async def test_approve_cross_family_is_404(client: AsyncClient, seed: Seed) -> None:
    """A guardian approving another family's request gets 404 (existence hiding)."""
    created = await client.post(
        _CREATE,
        json={"profile_id": str(seed.child_profile_id), "request_text": "a fox"},
        headers=auth(seed.guardian_token),
    )
    req_id = created.json()["id"]
    res = await client.post(
        f"{_CREATE}/{req_id}/approve",
        headers=auth(seed.other_guardian_token),
        json=_CONFIRMATION,
    )
    assert res.status_code == 404


async def test_child_cannot_approve(client: AsyncClient, seed: Seed) -> None:
    """A child token is denied at the approve endpoint (403), never a 404."""
    created = await client.post(
        _CREATE,
        json={"profile_id": str(seed.child_profile_id), "request_text": "a fox"},
        headers=auth(seed.guardian_token),
    )
    req_id = created.json()["id"]
    res = await client.post(
        f"{_CREATE}/{req_id}/approve",
        headers=auth(seed.child_token),
        json=_CONFIRMATION,
    )
    assert res.status_code == 403


async def test_child_cannot_decline(client: AsyncClient, seed: Seed) -> None:
    """A child token is denied at the decline endpoint (403)."""
    created = await client.post(
        _CREATE,
        json={"profile_id": str(seed.child_profile_id), "request_text": "a fox"},
        headers=auth(seed.guardian_token),
    )
    req_id = created.json()["id"]
    res = await client.post(
        f"{_CREATE}/{req_id}/decline", headers=auth(seed.child_token)
    )
    assert res.status_code == 403


async def test_decline_then_reapprove_conflicts(
    client: AsyncClient, seed: Seed
) -> None:
    """A declined request cannot then be approved (409)."""
    created = await client.post(
        _CREATE,
        json={"profile_id": str(seed.child_profile_id), "request_text": "a fox"},
        headers=auth(seed.guardian_token),
    )
    req_id = created.json()["id"]
    dec = await client.post(
        f"{_CREATE}/{req_id}/decline", headers=auth(seed.guardian_token)
    )
    assert dec.status_code == 200
    again = await client.post(
        f"{_CREATE}/{req_id}/approve",
        headers=auth(seed.guardian_token),
        json=_CONFIRMATION,
    )
    assert again.status_code == 409


async def test_approve_twice_conflicts(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """A second approval of an already-approved request is a 409, not a second
    Concept (locks the sequential double-approval path). No GenerationJob is
    created by approve at all anymore; that happens via POST .../authoring-plan."""
    created = await client.post(
        _CREATE,
        json={"profile_id": str(seed.child_profile_id), "request_text": "a fox"},
        headers=auth(seed.guardian_token),
    )
    req_id = created.json()["id"]
    first = await client.post(
        f"{_CREATE}/{req_id}/approve",
        headers=auth(seed.guardian_token),
        json=_CONFIRMATION,
    )
    assert first.status_code == 200
    concept_id = first.json()["concept_id"]
    second = await client.post(
        f"{_CREATE}/{req_id}/approve",
        headers=auth(seed.guardian_token),
        json=_CONFIRMATION,
    )
    assert second.status_code == 409

    async with sessions() as session:
        concept_count = await session.scalar(
            select(func.count())
            .select_from(Concept)
            .where(Concept.id == uuid.UUID(concept_id))
        )
        assert concept_count == 1

        job_count = await session.scalar(
            select(func.count())
            .select_from(GenerationJob)
            .where(GenerationJob.concept_id == uuid.UUID(concept_id))
        )
        assert job_count == 0


async def test_blocked_request_hides_raw_text(client: AsyncClient, seed: Seed) -> None:
    """A blocked request never returns its raw text to the guardian list."""
    await client.post(
        _CREATE,
        json={
            "profile_id": str(seed.child_profile_id),
            "request_text": "a story about Reader A",
        },
        headers=auth(seed.guardian_token),
    )
    res = await client.get(
        f"{_CREATE}?status=blocked", headers=auth(seed.guardian_token)
    )
    assert res.status_code == 200
    row = res.json()["requests"][0]
    assert row["request_text"] is None
    assert row["moderation_flags"][0]["category"] == "personal_information"


async def test_approve_without_body_returns_422(
    client: AsyncClient, seed: Seed
) -> None:
    """WS-B strict contract: approval requires band and length."""
    request_id = await _create_pending_request(client, seed)
    res = await client.post(
        f"{_CREATE}/{request_id}/approve",
        headers=auth(seed.guardian_token),
        json={},
    )
    assert res.status_code == 422


async def test_approve_with_confirmation_stamps_request(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The approval confirmation becomes the request's stored band/length,
    overriding whatever band the create endpoint stamped from the profile
    (the request is the source of truth for band/length from approval on)."""
    request_id = await _create_pending_request(client, seed)
    resp = await client.post(
        f"{_CREATE}/{request_id}/approve",
        headers=auth(seed.guardian_token),
        json={"age_band": "8-11", "length": "medium", "narrative_style": "prose"},
    )
    assert resp.status_code == 200, resp.text
    async with sessions() as session:
        row = await session.get(StoryRequest, uuid.UUID(request_id))
        assert row is not None
        assert row.age_band == "8-11"
        assert row.length == "medium"


async def test_gamebook_below_teen_band_rejected_at_approve(
    client: AsyncClient, seed: Seed
) -> None:
    """A gamebook style is rejected for a band below 13-16/16+ (422)."""
    request_id = await _create_pending_request(client, seed)
    resp = await client.post(
        f"{_CREATE}/{request_id}/approve",
        headers=auth(seed.guardian_token),
        json={"age_band": "8-11", "length": "short", "narrative_style": "gamebook"},
    )
    assert resp.status_code == 422


async def test_create_stamps_band_from_profile_and_child_role(
    client: AsyncClient, seed: Seed, sessions: async_sessionmaker[AsyncSession]
) -> None:
    """The create endpoint stamps age_band from the profile and
    initiator_role='child' (the kid surface runs under the guardian token in
    R1, but the request always records 'child' as the initiating role)."""
    request_id = await _create_pending_request(client, seed)
    async with sessions() as session:
        row = await session.get(StoryRequest, uuid.UUID(request_id))
        assert row is not None
        profile = await session.get(ChildProfile, seed.child_profile_id)
        assert profile is not None
        assert row.age_band == profile.age_band
        assert row.initiator_role == "child"
