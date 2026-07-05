"""Seed the development database with a family, a child profile, and stories.

Run against a local Postgres so the reader app has content to serve::

    uv run python scripts/seed_dev_data.py

It creates the schema (if missing), one family with a guardian, an admin, and
a child profile; publishes the two hand-authored Phase 1 stories; and leaves a
third story in review with a flagged moderation report so the admin review
queue has work to approve. It is idempotent: re-running skips rows that
already exist. This is a development convenience, not a migration; production
data comes through the generation pipeline.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

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
_REVIEW_STORY = "08_tier2_bridge_builder.json"

_GUARDIAN_SUBJECT = "dev-guardian"
_CHILD_SUBJECT = "dev-child"
_ADMIN_SUBJECT = "dev-admin"


def _flagged_moderation_report(node_id: str) -> dict[str, object]:
    """A minimal soft-flag report so the review surface shows a flagged passage."""
    # #ASSUME: data-integrity: this dict must match ModerationReport.to_dict()
    # (src/cyo_adventure/moderation/report.py); approve() only checks non-null,
    # but the review surface reads findings[].node_id/verdict/message.
    # #VERIFY: test_seed_dev_data_seeds_admin_and_review_story.
    return {
        "findings": [
            {
                "stage": 1,
                "source": "llm_safety",
                "category": "safety",
                "verdict": "flag",
                "message": "Dev seed: sample flag so the review queue has work.",
                "node_id": node_id,
                "score": 0.4,
            }
        ],
        "summary": {
            "count": 1,
            "hard_block": False,
            "soft_flag": True,
            "repaired": False,
            "reviewer_independent": True,
        },
    }


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
        session_factory: Callable returning a new ``AsyncSession``. When
            omitted it is derived from ``engine`` so schema creation and row
            inserts always target the same database; if ``engine`` is omitted
            too, it defaults to the app's ``get_session``.
    """
    active_engine = engine if engine is not None else get_engine()
    async with active_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # #ASSUME: data integrity: schema creation and row inserts must hit the same
    # database. When only ``engine`` is injected, bind the session factory to it
    # so a caller cannot create the schema on one engine while inserting through
    # the app's default ``get_session`` (a silent split-database footgun).
    # #VERIFY: seed_dev_data(engine=X) with no session_factory writes to X.
    if session_factory is not None:
        new_session = session_factory
    elif engine is not None:
        new_session = async_sessionmaker(active_engine, expire_on_commit=False)
    else:
        new_session = get_session

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
        session.add(
            User(family_id=family.id, role="admin", authn_subject=_ADMIN_SUBJECT)
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

        # #ASSUME: concurrency: the review-story Storybook/Version/Assignment
        # inserts share the composite-PK / no-rerun assumption tagged on the
        # published-story loop above; the function-level early return is the
        # sole guard against a second run duplicating these rows.
        # #VERIFY: test_seed_dev_data_seeds_admin_and_review_story.
        review_blob = json.loads((_VALID / _REVIEW_STORY).read_text(encoding="utf-8"))
        review_id = str(review_blob["id"])
        review_version = int(review_blob["version"])
        first_node_id = str(review_blob["nodes"][0]["id"])
        session.add(
            Storybook(
                id=review_id,
                family_id=family.id,
                current_published_version=None,
                status="in_review",
            )
        )
        session.add(
            StorybookVersion(
                storybook_id=review_id,
                version=review_version,
                blob=review_blob,
                moderation_report=_flagged_moderation_report(first_node_id),
            )
        )
        session.add(
            StorybookAssignment(
                child_profile_id=profile.id,
                storybook_id=review_id,
                assigned_by=guardian.id,
            )
        )

        # #ASSUME: security: a second, wholly unrelated family exists solely so
        # naive-kid-misuse-real.spec.ts can prove authorize_profile rejects a
        # cross-family profile id, not just a cross-profile-same-family id.
        # No guardian/admin User rows are seeded for this family: the test only
        # needs the child profile to exist, not a full principal set.
        # #VERIFY: test_seed_dev_data_seeds_unrelated_family_profile.
        unrelated_family = Family(name="Unrelated Family")
        session.add(unrelated_family)
        await session.flush()
        session.add(
            ChildProfile(
                id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
                family_id=unrelated_family.id,
                display_name="Unrelated Reader",
                age_band="8-11",
            )
        )

        await session.commit()
        print(
            f"Seeded family {family.id}, profile {profile.id}, admin user, "
            f"{len(_STORIES)} published stories, and 1 in-review story "
            f"({review_id}) awaiting approval."
        )


def main() -> None:
    """Entry point for the dev seed script."""
    asyncio.run(seed_dev_data())


if __name__ == "__main__":
    main()
