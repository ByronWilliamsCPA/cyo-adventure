"""Seed the development database with a family, a child profile, and stories.

Run against a local Postgres so the reader app has content to serve::

    uv run python scripts/seed_dev_data.py

It creates the schema (if missing), one family with a guardian and a child
profile, and publishes the two hand-authored Phase 1 stories. It is idempotent:
re-running skips rows that already exist. This is a development convenience, not a
migration; production data comes through the generation pipeline.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from cyo_adventure.core.database import Base, get_engine, get_session
from cyo_adventure.db.models import (
    ChildProfile,
    Family,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
    User,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

_VALID = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "storybook" / "valid"
)
_STORIES = ["06_tier1_tide_pools.json", "07_tier2_clockwork_garden.json"]

_GUARDIAN_SUBJECT = "dev-guardian"
_CHILD_SUBJECT = "dev-child"


async def seed_dev_data(
    *,
    engine: AsyncEngine | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> None:
    """Create the schema and insert the demo family, profile, and stories.

    Args:
        engine: Async engine to create the schema on. Defaults to the app's
            shared engine (``get_engine()``); tests inject a testcontainers
            engine here.
        session_factory: Callable returning a new ``AsyncSession``. Defaults
            to ``get_session``; tests inject a factory bound to the same
            engine passed above.
    """
    active_engine = engine if engine is not None else get_engine()
    async with active_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    new_session = session_factory if session_factory is not None else get_session

    async with new_session() as session:
        existing = await session.scalar(
            select(User).where(User.authn_subject == _GUARDIAN_SUBJECT)
        )
        if existing is not None:
            print("Dev data already seeded; nothing to do.")
            return

        family = Family(name="Dev Family")
        session.add(family)
        await session.flush()

        profile = ChildProfile(
            family_id=family.id, display_name="Dev Reader", age_band="10-13"
        )
        session.add(profile)
        await session.flush()

        guardian = User(
            family_id=family.id,
            role="guardian",
            authn_subject=_GUARDIAN_SUBJECT,
        )
        session.add(guardian)
        await session.flush()

        session.add(
            User(
                family_id=family.id,
                role="child",
                authn_subject=_CHILD_SUBJECT,
                child_profile_id=profile.id,
            )
        )

        # #ASSUME: data integrity: published_at must be timezone-aware to match
        # StorybookVersion.published_at, a TIMESTAMP WITH TIME ZONE column
        # (_TS = DateTime(timezone=True) in db/models.py). A naive datetime
        # would be ambiguous about which zone it represents.
        # #VERIFY: datetime.now(UTC) always returns a tz-aware value.
        published_at = datetime.now(UTC)

        for filename in _STORIES:
            blob = json.loads((_VALID / filename).read_text(encoding="utf-8"))
            story_id = str(blob["id"])
            version = int(blob["version"])
            session.add(
                Storybook(
                    id=story_id,
                    family_id=family.id,
                    current_published_version=version,
                    status="published",
                )
            )
            session.add(
                StorybookVersion(
                    storybook_id=story_id,
                    version=version,
                    blob=blob,
                    approved_by=guardian.id,
                    published_at=published_at,
                )
            )
            # #ASSUME: concurrency: StorybookAssignment has a composite primary
            # key on (child_profile_id, storybook_id), so inserting one row per
            # seeded story here relies on this function never re-running for an
            # already-seeded family (the guardian-existence guard above returns
            # early before reaching this loop on a re-run).
            # #VERIFY: the early return at the top of this function is the only
            # idempotency guard; a caller that seeds without it would violate
            # the composite primary key on a second run.
            session.add(
                StorybookAssignment(
                    child_profile_id=profile.id,
                    storybook_id=story_id,
                    assigned_by=guardian.id,
                )
            )

        await session.commit()
        print(
            f"Seeded family {family.id}, profile {profile.id}, "
            f"and {len(_STORIES)} stories."
        )


def main() -> None:
    """Entry point for the dev seed script."""
    asyncio.run(seed_dev_data())


if __name__ == "__main__":
    main()
