"""Integration tests for the child-session mint endpoint (G1 / P6-04).

Exercises minting authorization (guardian own-family, admin, cross-family,
child, unauthenticated, missing child account), the end-to-end round-trip
(a minted token authenticates as a CHILD principal scoped to one profile),
and the P6-09 negative cases (a child token is rejected on a guardian
endpoint and on another profile's library).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import ChildProfile
from tests.integration.conftest import Seed, Stranger, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.security]


# ---------------------------------------------------------------------------
# mint authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_guardian_mints_own_family_profile_returns_201(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian mints a session for a profile in its own family."""
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(seed.child_profile_id)},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["profile_id"] == str(seed.child_profile_id)
    assert body["token"]
    assert body["expires_at"]


@pytest.mark.asyncio
async def test_admin_mints_any_profile_returns_201(
    client: AsyncClient, seed: Seed
) -> None:
    """An admin is global and may mint for any profile."""
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(seed.child_profile_id)},
        headers=auth(seed.admin_token),
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_guardian_cannot_mint_other_family_profile(
    client: AsyncClient, seed: Seed
) -> None:
    """A guardian naming another family's profile is rejected with 403."""
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(seed.other_child_profile_id)},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_child_cannot_mint(client: AsyncClient, seed: Seed) -> None:
    """A child dev-stub token cannot mint a session (403 at the role gate)."""
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(seed.child_profile_id)},
        headers=auth(seed.child_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_unauthenticated_mint_returns_401(
    client: AsyncClient, seed: Seed
) -> None:
    """Minting without a bearer token is rejected with 401."""
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(seed.child_profile_id)},
    )
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_mint_requires_child_account(
    client: AsyncClient,
    seed: Seed,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """A profile with no child User cannot start a session (404)."""
    async with sessions() as session:
        bare = ChildProfile(
            family_id=seed.family_id, display_name="No Account", age_band="10-13"
        )
        session.add(bare)
        await session.commit()
        bare_id = bare.id

    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(bare_id)},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_mint_rejects_malformed_profile_id(
    client: AsyncClient, seed: Seed
) -> None:
    """A non-UUID profile id is rejected with 422 before any lookup."""
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": "not-a-uuid"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_mint_forbids_unknown_body_field(client: AsyncClient, seed: Seed) -> None:
    """An unexpected body field is rejected (extra='forbid')."""
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(seed.child_profile_id), "role": "admin"},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# end-to-end round-trip
# ---------------------------------------------------------------------------


async def _mint_child_token(client: AsyncClient, seed: Seed) -> str:
    """Mint a child token for the seeded profile and return the raw JWT."""
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(seed.child_profile_id)},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["token"]
    assert isinstance(token, str)
    return token


@pytest.mark.asyncio
async def test_minted_token_authenticates_as_scoped_child(
    client: AsyncClient, seed: Seed
) -> None:
    """A minted token yields a CHILD principal scoped to exactly one profile."""
    token = await _mint_child_token(client, seed)
    resp = await client.get("/api/v1/me", headers=auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "child"
    assert body["profile_ids"] == [str(seed.child_profile_id)]
    assert body["family_id"] == str(seed.family_id)


@pytest.mark.asyncio
async def test_minted_token_reads_own_library(client: AsyncClient, seed: Seed) -> None:
    """A child token may list its own profile's library."""
    token = await _mint_child_token(client, seed)
    resp = await client.get(
        "/api/v1/library",
        params={"profile_id": str(seed.child_profile_id)},
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# P6-09 negative cases: a child token on out-of-scope surfaces
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_child_token_rejected_on_guardian_endpoint(
    client: AsyncClient, seed: Seed
) -> None:
    """A minted child token cannot reach a guardian-only endpoint (403)."""
    token = await _mint_child_token(client, seed)
    resp = await client.post(
        "/api/v1/profiles",
        json={"display_name": "New Kid", "age_band": "10-13"},
        headers=auth(token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_child_token_rejected_on_other_profile_library(
    client: AsyncClient, seed: Seed
) -> None:
    """A child token scoped to profile A cannot read profile B's library."""
    token = await _mint_child_token(client, seed)
    resp = await client.get(
        "/api/v1/library",
        params={"profile_id": str(seed.other_child_profile_id)},
        headers=auth(token),
    )
    assert resp.status_code in (403, 404), resp.text
    assert not (200 <= resp.status_code < 300)


# ---------------------------------------------------------------------------
# P6-10: third, stranger-family IDOR extension
# ---------------------------------------------------------------------------
#
# Everything above proves the mint-authorization gate and the minted-token
# round-trip against family B (the seed fixture's second family). Neither
# proves the SAME real, backend-signed JWT mechanism holds against a third
# family with zero relationship to A or B: a bug that happens to key off
# "family B's id" specifically (e.g. an id comparison against the wrong
# constant, or a filter that special-cases the one other family the tests
# know about) would still pass every test above. The ``stranger`` fixture
# (family C: no shared storybook, assignment, or profile with A or B) closes
# that gap for both mint-time authorization and the minted token's own
# family/profile scoping.


async def _mint_token_for(
    client: AsyncClient, profile_id: object, guardian_token: str
) -> str:
    """Mint a child token for an arbitrary profile/guardian pair.

    Generalizes ``_mint_child_token`` so the stranger-family tests below can
    mint against ``stranger.child_profile_id``/``stranger.guardian_token``
    without duplicating the request/assert boilerplate.
    """
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(profile_id)},
        headers=auth(guardian_token),
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["token"]
    assert isinstance(token, str)
    return token


@pytest.mark.asyncio
async def test_guardian_cannot_mint_stranger_family_profile(
    client: AsyncClient, seed: Seed, stranger: Stranger
) -> None:
    """Family A's guardian naming family C's profile is rejected with 403.

    Mirrors ``test_guardian_cannot_mint_other_family_profile`` (family B)
    with a third, unrelated family, so a mint-time check that happens to
    reject only the specific family B id cannot slip through.
    """
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(stranger.child_profile_id)},
        headers=auth(seed.guardian_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_stranger_guardian_cannot_mint_family_a_profile(
    client: AsyncClient, seed: Seed, stranger: Stranger
) -> None:
    """Family C's guardian naming family A's profile is rejected with 403.

    The reverse direction of the check above: an unrelated family's guardian
    must not be able to mint a session for family A's child either.
    """
    resp = await client.post(
        "/api/v1/child-sessions",
        json={"profile_id": str(seed.child_profile_id)},
        headers=auth(stranger.guardian_token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_stranger_family_minted_token_rejected_on_family_a_library(
    client: AsyncClient, seed: Seed, stranger: Stranger
) -> None:
    """A real, minted family-C child JWT cannot read family A's library.

    Unlike the dev-stub role tokens used elsewhere in this module, this
    exercises the actual backend-signed HS256 JWT
    (``core/child_session.py::mint_child_session_token`` /
    ``verify_child_session_token``): the token is self-contained (family_id
    and profile_id are signed claims, verified with no database round-trip),
    so this proves the real mint/verify mechanism enforces family isolation,
    not just the dev-stub token-to-subject lookup the rest of the suite uses.
    """
    token = await _mint_token_for(
        client, stranger.child_profile_id, stranger.guardian_token
    )
    resp = await client.get(
        "/api/v1/library",
        params={"profile_id": str(seed.child_profile_id)},
        headers=auth(token),
    )
    assert resp.status_code in (403, 404), resp.text
    assert not (200 <= resp.status_code < 300)


@pytest.mark.asyncio
async def test_stranger_family_minted_token_rejected_on_family_a_guardian_endpoint(
    client: AsyncClient, stranger: Stranger
) -> None:
    """A real, minted family-C child JWT cannot reach a guardian-only route.

    The role gate (``ctx.principal.is_guardian``) must reject a CHILD
    principal built from a verified third-family token exactly as it rejects
    the dev-stub child token in ``test_child_token_rejected_on_guardian_endpoint``.
    """
    token = await _mint_token_for(
        client, stranger.child_profile_id, stranger.guardian_token
    )
    resp = await client.post(
        "/api/v1/profiles",
        json={"display_name": "New Kid", "age_band": "10-13"},
        headers=auth(token),
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_family_a_minted_token_rejected_on_stranger_family_library(
    client: AsyncClient, seed: Seed, stranger: Stranger
) -> None:
    """A real, minted family-A child JWT cannot read family C's library.

    The reverse direction of
    ``test_stranger_family_minted_token_rejected_on_family_a_library``: the
    isolation the signed claims provide must hold symmetrically.
    """
    token = await _mint_child_token(client, seed)
    resp = await client.get(
        "/api/v1/library",
        params={"profile_id": str(stranger.child_profile_id)},
        headers=auth(token),
    )
    assert resp.status_code in (403, 404), resp.text
    assert not (200 <= resp.status_code < 300)
