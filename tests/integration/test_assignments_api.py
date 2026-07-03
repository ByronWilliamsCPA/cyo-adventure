"""Integration tests for storybook assignment: ORM, API, and read-gate invariants."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cyo_adventure.db.models import (
    ChildProfile,
    Family,
    Storybook,
    StorybookAssignment,
    User,
)

from .conftest import Seed, auth

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_storybook_assignment_roundtrip(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """An assignment row inserts and reads back with its composite key."""
    async with sessions() as session:
        fam = Family(name="Fam")
        session.add(fam)
        await session.flush()
        profile = ChildProfile(family_id=fam.id, display_name="Kid", age_band="8-11")
        session.add(profile)
        book = Storybook(id="s-assign-1", family_id=fam.id, status="published")
        session.add(book)
        await session.flush()
        session.add(
            StorybookAssignment(child_profile_id=profile.id, storybook_id="s-assign-1")
        )
        await session.commit()
        profile_id = profile.id

    async with sessions() as session:
        row = await session.get(StorybookAssignment, (profile_id, "s-assign-1"))
        assert row is not None
        assert row.assigned_by is None


# ---------------------------------------------------------------------------
# End-to-end assignment read-gate invariants (Task 8)
#
# These pin the assignment security model across the assign router, the library
# listing gate, and the direct version-fetch gate. Each denial targets data that
# clears every OTHER predicate (family, published, approved, current, profile
# scope) so the denial is attributable to the single missing condition, and each
# is paired with a positive control on the SAME data.
# ---------------------------------------------------------------------------


async def _add_sibling(
    sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> tuple[str, str]:
    """Add a second Family A child profile and child user.

    Returns the sibling's bearer token and its profile id. Created locally here
    rather than in the shared seed so the family-wide count assertions in
    ``test_profiles.py`` and ``test_me.py`` stay valid.

    Args:
        sessions: The session factory bound to the test engine.
        seed: The seeded fixture data (supplies the Family A id).

    Returns:
        tuple[str, str]: The sibling's bearer token and its profile id.
    """
    async with sessions() as session:
        sibling = ChildProfile(
            family_id=seed.family_id, display_name="Reader A2", age_band="8-11"
        )
        session.add(sibling)
        await session.flush()
        session.add(
            User(
                family_id=seed.family_id,
                role="child",
                authn_subject="child-a2",
                child_profile_id=sibling.id,
            )
        )
        await session.commit()
        return "child-a2", str(sibling.id)


async def test_child_cannot_call_assign_endpoints(
    client: AsyncClient, seed: Seed
) -> None:
    """A child token is 403 on both POST and GET assignment endpoints.

    The child's own profile and the family's own book clear every other check, so
    the guardian-only role gate is the sole cause of the denial. The guardian
    positive control on the same book and body is ``test_assign_is_idempotent``.
    """
    post = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/assignments",
        headers=auth(seed.child_token),
        json={"profile_ids": [str(seed.child_profile_id)]},
    )
    assert post.status_code == 403, post.text
    get = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/assignments",
        headers=auth(seed.child_token),
    )
    assert get.status_code == 403, get.text


async def test_cross_family_guardian_gets_403(client: AsyncClient, seed: Seed) -> None:
    """Family B's guardian probing Family A's existing book gets 403, not 404.

    Repo convention: 404-if-missing precedes ``authorize_family``
    (ratings.py:60-68, library.py:346-356), so an existing cross-family book is
    403. The owning guardian's 200 on the same book is the positive control that
    isolates the cross-family check as the sole cause of the denial.
    """
    resp = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/assignments",
        headers=auth(seed.other_guardian_token),
    )
    assert resp.status_code == 403, resp.text
    owner = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/assignments",
        headers=auth(seed.guardian_token),
    )
    assert owner.status_code == 200, owner.text


async def test_unknown_storybook_404(client: AsyncClient, seed: Seed) -> None:
    """An unknown storybook id is 404 for the guardian on POST.

    The same guardian assigning the real seed book at 200
    (``test_assign_is_idempotent``) is the positive control isolating the
    missing-book 404 from the role and profile checks.
    """
    resp = await client.post(
        "/api/v1/storybooks/no-such-story/assignments",
        headers=auth(seed.guardian_token),
        json={"profile_ids": [str(seed.child_profile_id)]},
    )
    assert resp.status_code == 404, resp.text


async def test_sibling_blocked_then_assigned(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """Sibling cannot see or fetch the seed story until the guardian assigns it.

    The seed story is approved, published, current, and in the sibling's own
    family, so it clears every predicate except the per-profile assignment. The
    before/after pair around a single guardian assign isolates the assignment
    row as the only thing that changed across both read paths.
    """
    token, sibling_id = await _add_sibling(sessions, seed)

    # 1. Not in the sibling's library, and the direct version fetch is 404.
    before = await client.get(
        "/api/v1/library", params={"profile_id": sibling_id}, headers=auth(token)
    )
    assert before.status_code == 200, before.text
    assert seed.storybook_id not in {s["id"] for s in before.json()["stories"]}
    blocked = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}",
        headers=auth(token),
    )
    assert blocked.status_code == 404, blocked.text

    # 2. Guardian assigns the seed story to the sibling.
    assigned = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/assignments",
        headers=auth(seed.guardian_token),
        json={"profile_ids": [sibling_id]},
    )
    assert assigned.status_code == 200, assigned.text
    assert sibling_id in assigned.json()["profile_ids"]

    # 3. Now the sibling sees it in the library and can fetch the blob.
    after = await client.get(
        "/api/v1/library", params={"profile_id": sibling_id}, headers=auth(token)
    )
    assert seed.storybook_id in {s["id"] for s in after.json()["stories"]}
    ok = await client.get(
        f"/api/v1/storybooks/{seed.storybook_id}/versions/{seed.version}",
        headers=auth(token),
    )
    assert ok.status_code == 200, ok.text


async def test_assign_is_idempotent(client: AsyncClient, seed: Seed) -> None:
    """Assigning an already-assigned profile is a no-op that still returns 200."""
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/assignments",
        headers=auth(seed.guardian_token),
        json={"profile_ids": [str(seed.child_profile_id)]},
    )
    assert resp.status_code == 200, resp.text
    assert str(seed.child_profile_id) in resp.json()["profile_ids"]


async def test_profile_outside_family_403(client: AsyncClient, seed: Seed) -> None:
    """Assigning a Family B profile from Family A's guardian is 403.

    The book is Family A's and published, so the guardian clears the role,
    family, and published checks; only the foreign profile fails. The idempotent
    assign of a same-family profile on the same book is the positive control.
    """
    resp = await client.post(
        f"/api/v1/storybooks/{seed.storybook_id}/assignments",
        headers=auth(seed.guardian_token),
        json={"profile_ids": [str(seed.other_child_profile_id)]},
    )
    assert resp.status_code == 403, resp.text


async def test_non_published_story_400(
    client: AsyncClient, sessions: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    """Assigning a draft (non-published) story is 400.

    The draft is Family A's, so the guardian clears the role and family checks;
    the non-published status is the sole cause. The idempotent assign of the
    published seed story is the positive control on the published branch.
    """
    async with sessions() as session:
        session.add(Storybook(id="draft-1", family_id=seed.family_id, status="draft"))
        await session.commit()
    resp = await client.post(
        "/api/v1/storybooks/draft-1/assignments",
        headers=auth(seed.guardian_token),
        json={"profile_ids": [str(seed.child_profile_id)]},
    )
    assert resp.status_code == 400, resp.text
