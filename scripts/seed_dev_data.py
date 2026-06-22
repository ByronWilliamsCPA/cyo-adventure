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
from pathlib import Path

from sqlalchemy import select

from cyo_adventure.core.database import Base, get_engine, get_session
from cyo_adventure.db.models import (
    ChildProfile,
    Family,
    Storybook,
    StorybookVersion,
    User,
)

_VALID = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "storybook" / "valid"
)
_STORIES = ["06_tier1_tide_pools.json", "07_tier2_clockwork_garden.json"]

_GUARDIAN_SUBJECT = "dev-guardian"
_CHILD_SUBJECT = "dev-child"


async def _seed() -> None:
    """Create the schema and insert the demo family, profile, and stories."""
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with get_session() as session:
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

        session.add_all(
            [
                User(
                    family_id=family.id,
                    role="guardian",
                    authn_subject=_GUARDIAN_SUBJECT,
                ),
                User(
                    family_id=family.id,
                    role="child",
                    authn_subject=_CHILD_SUBJECT,
                    child_profile_id=profile.id,
                ),
            ]
        )

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
                StorybookVersion(storybook_id=story_id, version=version, blob=blob)
            )

        await session.commit()
        print(
            f"Seeded family {family.id}, profile {profile.id}, "
            f"and {len(_STORIES)} stories."
        )


def main() -> None:
    """Entry point for the dev seed script."""
    asyncio.run(_seed())


if __name__ == "__main__":
    main()
