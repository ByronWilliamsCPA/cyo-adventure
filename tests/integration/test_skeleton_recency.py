"""Integration tests for recent_skeleton_usage (WS-C PR2)."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.api.schemas import AuthoringPlanRequest
from cyo_adventure.db.models import (
    ChildProfile,
    Concept,
    Family,
    Storybook,
    StorybookVersion,
    StoryRequest,
    User,
)
from cyo_adventure.events import Actor
from cyo_adventure.generation.skeleton_match import recent_skeleton_usage
from cyo_adventure.story_requests import authoring_plan as authoring_plan_module
from cyo_adventure.story_requests.authoring_plan import build_authoring_plan

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.asyncio


async def _seed_version(
    session: AsyncSession,
    family_id: uuid.UUID,
    *,
    storybook_id: str,
    skeleton_slug: str | None,
) -> None:
    session.add(Storybook(id=storybook_id, family_id=family_id, status="draft"))
    await session.flush()
    session.add(
        StorybookVersion(
            storybook_id=storybook_id,
            version=1,
            blob={"id": storybook_id, "title": "T", "nodes": []},
            skeleton_slug=skeleton_slug,
        )
    )
    await session.flush()


async def test_recent_skeleton_usage_counts_within_family(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        family = Family(name="Recency Fam")
        session.add(family)
        await session.flush()
        await _seed_version(
            session, family.id, storybook_id="s_r1", skeleton_slug="the-cave-of-echoes"
        )
        await _seed_version(
            session, family.id, storybook_id="s_r2", skeleton_slug="the-cave-of-echoes"
        )
        await _seed_version(
            session,
            family.id,
            storybook_id="s_r3",
            skeleton_slug="the-sky-ship-stowaway",
        )
        await _seed_version(session, family.id, storybook_id="s_r4", skeleton_slug=None)
        await session.commit()

        usage = await recent_skeleton_usage(session, family.id)
        assert usage == {"the-cave-of-echoes": 2, "the-sky-ship-stowaway": 1}


async def test_recent_skeleton_usage_returns_empty_for_none_family_id(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        assert await recent_skeleton_usage(session, None) == {}


async def test_recent_skeleton_usage_returns_empty_for_family_with_no_history(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        family = Family(name="Empty Fam")
        session.add(family)
        await session.flush()
        await session.commit()

        assert await recent_skeleton_usage(session, family.id) == {}


async def test_recent_skeleton_usage_ignores_other_families(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        family_a = Family(name="Fam A")
        family_b = Family(name="Fam B")
        session.add_all([family_a, family_b])
        await session.flush()
        await _seed_version(
            session,
            family_a.id,
            storybook_id="s_a1",
            skeleton_slug="the-cave-of-echoes",
        )
        await _seed_version(
            session,
            family_b.id,
            storybook_id="s_b1",
            skeleton_slug="the-sky-ship-stowaway",
        )
        await session.commit()

        usage = await recent_skeleton_usage(session, family_a.id)
        assert usage == {"the-cave-of-echoes": 1}


async def test_build_authoring_plan_deweights_recent_skeleton(
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gap 2: recency weighting is wired end to end through build_authoring_plan.

    This test pins an exact two-candidate cell by monkeypatching the candidate
    source, so the weighted pick is exercised deterministically regardless of
    how many skeletons the real catalog holds. It binds the three halves that
    are otherwise only tested
    independently: build_authoring_plan consults ``recent_skeleton_usage``
    against real seeded family history, feeds that usage into
    ``select_skeleton_for_cell``'s inverse-frequency weighting, and draws a
    pick from ``random.SystemRandom`` (patched here to a seeded Random for
    determinism).

    With a recency window heavily dominated by ``recent`` (10 uses vs 0 for
    ``fresh``), the de-weighted candidate ``recent`` carries weight 1/11 while
    ``fresh`` carries 1.0; under the fixed seed the pick is ``fresh``, proving
    the recency counts actually steered the draw rather than being computed and
    ignored.
    """
    recent = "the-cave-of-echoes"
    fresh = "the-sky-ship-stowaway"

    seen_usage: dict[str, dict[str, int]] = {}
    real_recent_usage = authoring_plan_module.recent_skeleton_usage

    async def _spy_recent_usage(
        session_: AsyncSession, family_id: uuid.UUID | None
    ) -> dict[str, int]:
        usage = await real_recent_usage(session_, family_id)
        seen_usage["value"] = usage
        return usage

    monkeypatch.setattr(
        authoring_plan_module, "candidates_for_cell", lambda *_a: [recent, fresh]
    )
    monkeypatch.setattr(
        authoring_plan_module, "recent_skeleton_usage", _spy_recent_usage
    )
    # Seed 0 deterministically draws `fresh` under the [1/11, 1.0] weights.
    monkeypatch.setattr(
        authoring_plan_module.random, "SystemRandom", lambda: random.Random(0)
    )

    async with sessions() as session:
        family = Family(name="Weighted Fam")
        session.add(family)
        await session.flush()
        admin = User(
            family_id=family.id,
            role="admin",
            authn_subject="admin-weighted",
            is_admin=True,
        )
        profile = ChildProfile(family_id=family.id, display_name="Kid", age_band="8-11")
        session.add_all([admin, profile])
        await session.flush()

        # A recency window heavily dominated by `recent`.
        for i in range(10):
            await _seed_version(
                session, family.id, storybook_id=f"s_w{i}", skeleton_slug=recent
            )

        concept = Concept(
            family_id=family.id,
            created_by=admin.id,
            brief={"age_band": "8-11", "premise": "a fox finds a lantern"},
        )
        session.add(concept)
        await session.flush()

        # request is read only for family_id; it need not be persisted.
        request = StoryRequest(
            family_id=family.id,
            profile_id=profile.id,
            request_text="a fox",
            status="approved",
        )
        plan = AuthoringPlanRequest(
            method="skeleton_fill", mechanism="skill", prep_model="sonnet"
        )
        result = await build_authoring_plan(
            session,
            request,
            concept,
            plan,
            actor=Actor(actor_id=admin.id, actor_role="admin"),
        )
        await session.commit()

    # recent_skeleton_usage was consulted and saw the dominant history.
    assert seen_usage["value"] == {recent: 10}
    # The heavily-recent (de-weighted) slug is NOT the pick under this seed.
    assert result.skeleton_slug == fresh
    assert result.skeleton_slug != recent
    assert sorted(result.skeleton_alternatives) == sorted([recent, fresh])
