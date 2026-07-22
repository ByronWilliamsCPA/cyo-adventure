"""Idempotently seed the "Ember Trail" series into the shared CATALOG.

Publishes a two-book, state-carrying series ("Ember Trail" 1/2) as
catalog-visible, published books under the well-known `CATALOG_FAMILY_ID`
family, then assigns both books to a resolved test child profile, so the
series-continuation ("Continue the series") flow is walkable end to end in
staging AND production. Unlike `scripts/seed_staging.py`, this script does
NOT hard-refuse a non-staging environment: it is meant to run against either
staging or production (with an explicit confirmation gate for production).

Run against staging:

    ENVIRONMENT=staging CYO_ADVENTURE_DATABASE_URL=... \\
        uv run python scripts/seed_series_catalog.py

Run against production (requires explicit confirmation):

    ENVIRONMENT=production SEED_CONFIRM=1 CYO_ADVENTURE_DATABASE_URL=... \\
        uv run python scripts/seed_series_catalog.py

The child profile the books are assigned to is resolved by looking for
exactly one `ChildProfile` whose family name is in an allowlist (default:
"E2E Test Family" or "Test Family"; override with `SEED_SERIES_ASSIGN_FAMILY`
to target a single, differently-named family instead). If zero or more than
one profile matches, the script refuses to run rather than guess and risk
assigning the series to a real family's profile.

Idempotent by design: re-running is a no-op (detected via the first book's
fixed storybook id) rather than raising or duplicating rows.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from cyo_adventure.core.database import Base, get_engine
from cyo_adventure.db.models import (
    CATALOG_FAMILY_ID,
    ChildProfile,
    Family,
    Series,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
    User,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

# Every env var this script needs before it will do anything.
REQUIRED_ENV: tuple[str, ...] = ("ENVIRONMENT", "CYO_ADVENTURE_DATABASE_URL")

_ALLOWED_ENVIRONMENTS = frozenset({"staging", "production"})

# Default set of family names this script is willing to assign the series to.
# Overridable (as a single name) via SEED_SERIES_ASSIGN_FAMILY for a
# differently-named QA/test family in a given environment.
_DEFAULT_ASSIGN_FAMILIES = frozenset({"E2E Test Family", "Test Family"})

# Fixed title/age-band/book ids so this script (and any spec that reads the
# library afterward) can identify the series deterministically.
_SERIES_TITLE = "Ember Trail"
_SERIES_AGE_BAND = "10-13"
_SERIES_BOOKS: tuple[tuple[str, str, int], ...] = (
    ("s_dev_ember_1", "Ember Trail 1", 1),
    ("s_dev_ember_2", "Ember Trail 2", 2),
)


def require_env() -> None:
    """Exit with a clear message naming every required env var that is missing.

    Called before any database I/O so a misconfigured shell fails fast rather
    than partway through seeding.
    """
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        sys.exit(
            "seed_series_catalog: missing required environment variable(s): "
            + ", ".join(missing)
        )


def _series_blob(
    story_id: str, title: str, book_index: int, series_id: str
) -> dict[str, object]:
    """Build a three-node story blob for a series book.

    Copied verbatim from `scripts/seed_dev_data.py::_series_blob` (that copy
    is the canonical one); duplicated rather than imported because scripts/
    are standalone entry points, not an importable package (no `__init__.py`,
    by design -- see the `INP` per-file-ignore for `scripts/**/*.py` in
    `pyproject.toml`), which is the same reason `seed_staging.py` duplicates
    its own fixture-construction logic instead of importing it.

    Mirrors the two-node `_blob` helper in
    `tests/integration/test_series_next.py` but adds a middle node so the
    start node offers a real choice (one branch sets `courage` via an effect,
    the other is plain) before the reader reaches the ending; both branches
    converge on the middle node so the book resolves in at most two clicks.
    The metadata carries every field `StoryMetadata` requires (reading_level,
    tier, estimated_minutes, ending_count, topology): the reading-state PUT
    path re-runs `Storybook.model_validate` on the pinned blob
    (api/reading.py -> player/replay.py), so a blob missing any of them would
    422 every progress save.

    Args:
        story_id: Fixed storybook id embedded in the blob (`blob["id"]`).
        title: Story title, also used as the passage-body prefix.
        book_index: 1-based position within the series.
        series_id: The just-flushed `Series.id` (as a string), embedded in
            `metadata.series.series_id` so the book links to a real row.

    Returns:
        A `Storybook.model_validate`-clean blob whose `metadata.series` block
        declares the start node as the series entry node and marks the book
        as state-carrying.
    """
    prefix = f"n_e{book_index}"
    start = f"{prefix}_start"
    middle = f"{prefix}_middle"
    end = f"{prefix}_end"
    return {
        "schema_version": "2.0",
        "id": story_id,
        "version": 1,
        "title": title,
        "metadata": {
            "age_band": _SERIES_AGE_BAND,
            "reading_level": {"scheme": "flesch_kincaid", "target": 4.0},
            # Tier 2, not 1: the model forbids variables on tier 1 stories
            # (_check_tier_variables), and this blob declares "courage".
            "tier": 2,
            "estimated_minutes": 2,
            "ending_count": 1,
            "topology": "branch_and_bottleneck",
            "series": {
                "series_id": series_id,
                "book_index": book_index,
                "series_entry_node": start,
                "is_final": False,
                "carries_state": True,
            },
        },
        "variables": [
            {"name": "courage", "type": "int", "initial": 0, "min": 0, "max": 5}
        ],
        "start_node": start,
        "nodes": [
            {
                "id": start,
                "body": f"{title}: the trail begins.",
                "is_ending": False,
                "choices": [
                    {
                        "id": f"c_{prefix}_brave",
                        "label": "Face it with courage",
                        "target": middle,
                        "effects": [{"op": "set", "var": "courage", "value": 3}],
                    },
                    {
                        "id": f"c_{prefix}_plain",
                        "label": "Walk on carefully",
                        "target": middle,
                    },
                ],
            },
            {
                "id": middle,
                "body": f"{title}: onward through the woods.",
                "is_ending": False,
                "choices": [
                    {
                        "id": f"c_{prefix}_onward",
                        "label": "Keep going",
                        "target": end,
                    }
                ],
            },
            {
                "id": end,
                "body": f"{title}: journey's end.",
                "is_ending": True,
                "ending": {
                    "id": f"e_{prefix}_done",
                    "valence": "positive",
                    "kind": "success",
                    "title": "The End",
                },
                "choices": [],
            },
        ],
    }


async def _resolve_test_child_profile(session: AsyncSession) -> ChildProfile:
    """Resolve the single test child profile the series will be assigned to.

    # #CRITICAL: security: this script writes to staging AND production
    # (unlike seed_staging.py, which hard-refuses non-staging). Assigning the
    # series to the wrong profile would put fixture content in front of a
    # real family's child. To fail safe, this NEVER guesses: it only proceeds
    # when exactly one child profile matches the allowlisted test-family
    # name(s), and exits otherwise (zero matches or more than one).
    # #VERIFY: test_seed_series_catalog_fails_when_no_test_family_profile,
    # test_seed_series_catalog_fails_when_multiple_test_family_profiles.

    Args:
        session: The active seed session.

    Returns:
        The single matching `ChildProfile` row.
    """
    override = os.environ.get("SEED_SERIES_ASSIGN_FAMILY")
    allowed_names = {override} if override else set(_DEFAULT_ASSIGN_FAMILIES)

    rows = (
        await session.execute(
            select(ChildProfile, Family.name)
            .join(Family, Family.id == ChildProfile.family_id)
            .where(Family.name.in_(allowed_names))
        )
    ).all()

    if len(rows) != 1:
        found = (
            ", ".join(f"{name!r}/{profile.display_name!r}" for profile, name in rows)
            or "none"
        )
        allowed = ", ".join(sorted(allowed_names))
        message = (
            "seed_series_catalog: expected exactly one child profile in a "
            f"test family ({allowed}); found {len(rows)}: {found}. Refusing "
            "to guess which profile to assign the series to."
        )
        sys.exit(message)

    profile, _name = rows[0]
    return profile


async def _resolve_admin_user(session: AsyncSession, family_id: uuid.UUID) -> User:
    """Resolve the admin user to attribute the seeded rows to.

    Prefers an admin belonging to `family_id` (the resolved test family), so
    the series/books read back attributed to the same test fixture family
    where possible; falls back to any `is_admin=True` user otherwise.

    Args:
        session: The active seed session.
        family_id: The resolved test child profile's family id.

    Returns:
        The chosen admin `User` row.
    """
    admins = (await session.scalars(select(User).where(User.is_admin.is_(True)))).all()
    if not admins:
        message = (
            "seed_series_catalog: no admin (is_admin=True) user found; cannot "
            "attribute the seeded series/books to anyone."
        )
        sys.exit(message)

    for admin in admins:
        if admin.family_id == family_id:
            return admin
    return admins[0]


async def seed(
    *,
    engine: AsyncEngine | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> None:
    """Idempotently seed the "Ember Trail" series into the shared CATALOG.

    Refuses to run unless `ENVIRONMENT` is `staging` or `production`, and
    additionally requires `SEED_CONFIRM=1` for production. On a re-run
    against an already-seeded database it detects the first book's fixed
    storybook id and returns before touching the database further, so no
    duplicate rows are ever created.

    Args:
        engine: Async engine to create the schema on. Defaults to the app's
            shared engine (`get_engine()`); tests inject a testcontainers
            engine here.
        session_factory: Callable returning a new `AsyncSession`. Defaults to
            a sessionmaker bound to `engine`; tests inject a mocked/test
            session factory here so no real database connection is required
            outside of tests.
    """
    require_env()
    environment = os.environ["ENVIRONMENT"]
    if environment not in _ALLOWED_ENVIRONMENTS:
        sys.exit(
            "seed_series_catalog: ENVIRONMENT must be one of "
            f"{sorted(_ALLOWED_ENVIRONMENTS)}, got {environment!r}."
        )

    # #CRITICAL: security: production is real, guardian-owned data; an
    # accidental run must not silently write a fixture series/books to it.
    # SEED_CONFIRM=1 is a deliberate, explicit opt-in a human (or an
    # intentional automation) must set; staging needs no such gate.
    # #VERIFY: test_seed_series_catalog_requires_confirm_for_production,
    # test_seed_series_catalog_production_with_confirm_reaches_db.
    if environment == "production" and os.environ.get("SEED_CONFIRM") != "1":
        sys.exit(
            "seed_series_catalog: refusing to run against PRODUCTION without "
            "SEED_CONFIRM=1. This writes the 'Ember Trail' series to the live "
            "production catalog and assigns it to a test child profile; set "
            "SEED_CONFIRM=1 to confirm you intend this."
        )

    active_engine = engine if engine is not None else get_engine()
    async with active_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    new_session = (
        session_factory
        if session_factory is not None
        else async_sessionmaker(active_engine, expire_on_commit=False)
    )

    async with new_session() as session:
        existing = await session.scalar(
            select(Storybook.id).where(Storybook.id == _SERIES_BOOKS[0][0])
        )
        if existing is not None:
            print("Series catalog fixtures already seeded; nothing to do.")
            return

        profile = await _resolve_test_child_profile(session)
        admin = await _resolve_admin_user(session, profile.family_id)

        series = Series(
            family_id=CATALOG_FAMILY_ID,
            title=_SERIES_TITLE,
            age_band=_SERIES_AGE_BAND,
            carries_state=True,
            created_by=admin.id,
        )
        session.add(series)
        await session.flush()

        published_at = datetime.now(UTC)
        for story_id, title, book_index in _SERIES_BOOKS:
            session.add(
                Storybook(
                    id=story_id,
                    family_id=CATALOG_FAMILY_ID,
                    current_published_version=1,
                    status="published",
                    visibility="catalog",
                    series_id=series.id,
                    book_index=book_index,
                    created_by=admin.id,
                )
            )
            # #CRITICAL: security, data-integrity: approved_by must never be
            # left null. The library read gate (api/library.py) requires it
            # to be set on the published version; a null value here would
            # make the book published-but-invisible to any child.
            # #VERIFY: the "inserts series books and assignment" integration
            # test asserts approved_by equals the resolved admin's id for
            # both seeded versions.
            session.add(
                StorybookVersion(
                    storybook_id=story_id,
                    version=1,
                    blob=_series_blob(story_id, title, book_index, str(series.id)),
                    approved_by=admin.id,
                    published_at=published_at,
                )
            )
            session.add(
                StorybookAssignment(
                    child_profile_id=profile.id,
                    storybook_id=story_id,
                    assigned_by=admin.id,
                )
            )

        await session.commit()
        print(
            f"Seeded series {series.id} ('{_SERIES_TITLE}') with "
            f"{len(_SERIES_BOOKS)} books, assigned to profile {profile.id}."
        )


def main() -> None:
    """Entry point for the series-catalog seed script."""
    asyncio.run(seed())


if __name__ == "__main__":
    main()
