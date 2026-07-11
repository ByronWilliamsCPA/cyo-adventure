"""Seed the STAGING Supabase project with disposable test fixtures.

Creates (idempotently): a guardian and an admin user in Supabase Auth via the
GoTrue admin API (email_confirm=true), a "Test Family", matching User rows
whose authn_subject is each Auth user's UUID, a "Test Reader" child profile
(age band 5-8), and the two hand-authored published stories assigned to the
profile. Run with:

    SEED_GUARDIAN_PASSWORD=... SEED_ADMIN_PASSWORD=... \\
        uv run --env-file .env.staging python scripts/seed_staging.py

Never run against production: the script refuses to run unless
ENVIRONMENT=staging. Passwords are intentionally absent from
.env.staging.example (see that file's Seed script inputs section); export
them in the shell at seed time only, never commit or log them.

Idempotent by design: re-running against an already-seeded staging project
is a no-op (it detects the guardian's Auth-subject User row and returns
early) rather than raising or duplicating rows. The GoTrue Auth users are
looked up by email before any create call, so a second run reuses the same
Auth user ids instead of erroring on "already registered".
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from cyo_adventure.core.database import Base, get_engine
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

# Every env var this script needs. ENVIRONMENT is included so a wholesale-unset
# shell reports it alongside the rest rather than tripping the separate
# staging-only guard first with a less informative message. The two
# SEED_*_PASSWORD vars are deliberately absent from .env.staging.example (see
# that file); they must come from the process environment only.
REQUIRED_ENV: tuple[str, ...] = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SEED_GUARDIAN_EMAIL",
    "SEED_ADMIN_EMAIL",
    "SEED_GUARDIAN_PASSWORD",
    "SEED_ADMIN_PASSWORD",
    "CYO_ADVENTURE_DATABASE_URL",
    "ENVIRONMENT",
)

# The same two hand-authored, already-validated fixture blobs seed_dev_data.py
# uses, reused here for the identical reason: they are guaranteed
# schema-valid and require no LLM generation to produce.
_VALID = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "storybook" / "valid"
)
_STORIES = ("06_tier1_tide_pools.json", "07_tier2_clockwork_garden.json")

_FAMILY_NAME = "Test Family"
_CHILD_DISPLAY_NAME = "Test Reader"
_CHILD_AGE_BAND = "5-8"


def require_env() -> None:
    """Exit with a clear message naming every required env var that is missing.

    Called before any network or database I/O so a misconfigured shell fails
    fast instead of partway through seeding (e.g. after creating one Auth
    user but not the other).
    """
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        sys.exit(
            "seed_staging: missing required environment variable(s): "
            + ", ".join(missing)
        )


def build_auth_user_payload(email: str, password: str) -> dict[str, object]:
    """Build the GoTrue admin create-user request body.

    ``email_confirm`` is always True: a staging fixture account has no real
    inbox to receive a confirmation email, so it must be created pre-confirmed
    to be usable for login.

    Args:
        email: The account's email address.
        password: The account's password.

    Returns:
        The JSON body for ``POST {SUPABASE_URL}/auth/v1/admin/users``.
    """
    return {"email": email, "password": password, "email_confirm": True}


def _as_dict(value: object) -> dict[str, object] | None:
    """Narrow an untrusted decoded-JSON value to a string-keyed mapping.

    Args:
        value: A value from a decoded GoTrue admin API JSON response.

    Returns:
        The value cast to ``dict[str, object]`` when it is a dict, else None.
    """
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


async def _find_auth_user_by_email(client: httpx.AsyncClient, email: str) -> str | None:
    """Look up an existing GoTrue Auth user by exact email match.

    # #CRITICAL: external-resources: GoTrue's admin list-users endpoint has no
    # guaranteed exact-email server-side filter across Supabase versions, so
    # this fetches the user list and matches client-side.
    # #VERIFY: acceptable at staging fixture scale (two accounts); would need
    # pagination to scale past GoTrue's default page size.

    Args:
        client: httpx client whose base_url is the Supabase project and whose
            headers already carry the service-key credentials.
        email: The address to match.

    Returns:
        The matching Auth user's UUID as a string, or None if not found.
    """
    response = await client.get("/auth/v1/admin/users")
    response.raise_for_status()
    body = _as_dict(response.json())
    users = body.get("users") if body is not None else None
    if not isinstance(users, list):
        return None
    for entry in users:
        record = _as_dict(entry)
        if record is not None and record.get("email") == email:
            user_id = record.get("id")
            return str(user_id) if user_id is not None else None
    return None


async def ensure_auth_user(client: httpx.AsyncClient, email: str, password: str) -> str:
    """Create or find a Supabase Auth user by email, returning its UUID.

    Idempotent: looks up the user by email first and only calls the create
    endpoint on a miss. If the create call loses a race to a concurrent seed
    run (GoTrue reports the email already registered via a 400/422), falls
    back to a second lookup instead of treating it as a fatal error.

    # #CRITICAL: security: the service key lives only in ``client``'s
    # preconfigured headers (apikey / Authorization), built from
    # SUPABASE_SERVICE_KEY by the caller; it grants full Auth-admin access to
    # the project. This function never logs the key or the ``password``
    # argument.
    # #VERIFY: no logger/print call in this module references ``password`` or
    # any request/response header.

    Args:
        client: Shared httpx.AsyncClient configured for the GoTrue admin API.
        email: The Auth user's email address.
        password: The Auth user's password (never logged).

    Returns:
        The Supabase Auth user's UUID as a string.

    Raises:
        httpx.HTTPStatusError: On any non-recoverable non-2xx response.
        RuntimeError: If a successful create response has no usable id.
    """
    existing = await _find_auth_user_by_email(client, email)
    if existing is not None:
        return existing

    response = await client.post(
        "/auth/v1/admin/users", json=build_auth_user_payload(email, password)
    )
    if response.status_code in (400, 422):
        # #ASSUME: concurrency: a 400/422 here most plausibly means "email
        # already registered" (a concurrent seed run won the lookup/create
        # race); re-check before treating this as fatal.
        # #VERIFY: test_ensure_auth_user_recovers_from_conflicting_create.
        existing = await _find_auth_user_by_email(client, email)
        if existing is not None:
            return existing
    response.raise_for_status()
    created = _as_dict(response.json())
    if created is None or created.get("id") is None:
        msg = f"GoTrue admin create-user returned an unexpected body for {email!r}"
        raise RuntimeError(msg)
    return str(created["id"])


async def _publish_fixture_stories(
    session: AsyncSession,
    family: Family,
    profile: ChildProfile,
    guardian: User,
) -> None:
    """Publish the two hand-authored fixture stories and assign them.

    Copies the Storybook/StorybookVersion/StorybookAssignment construction
    pattern verbatim from ``scripts/seed_dev_data.py`` (its published-story
    loop); duplicated rather than imported because scripts/ are standalone
    entry points, not an importable package.

    # #ASSUME: concurrency: StorybookAssignment has a composite primary key on
    # (child_profile_id, storybook_id); this relies on the caller (seed())
    # never reaching this function on a second run against an already-seeded
    # database, since the guardian-existence guard in seed() returns early
    # before this call.
    # #VERIFY: test_seed_skips_when_guardian_already_exists.

    Args:
        session: The active seed session.
        family: The just-flushed Test Family row.
        profile: The just-flushed Test Reader child profile row.
        guardian: The just-flushed guardian User row (used as approved_by /
            assigned_by).
    """
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
        session.add(
            StorybookAssignment(
                child_profile_id=profile.id,
                storybook_id=story_id,
                assigned_by=guardian.id,
            )
        )


async def seed(
    *,
    engine: AsyncEngine | None = None,
    session_factory: Callable[[], AsyncSession] | None = None,
) -> None:
    """Idempotently seed the staging Supabase project with test fixtures.

    Refuses to run unless ENVIRONMENT=staging (the hard guard against an
    accidental run against production). Creates two Supabase Auth users
    (guardian, admin), a Test Family, matching User rows, a Test Reader child
    profile, and publishes the two fixture stories to it. Skips all of it
    (Auth-user creation included) when the guardian's User row already
    exists, so re-running against an already-seeded staging project is a
    no-op.

    Args:
        engine: Async engine to create the schema on. Defaults to the app's
            shared engine (``get_engine()``); tests inject a mock engine here.
        session_factory: Callable returning a new AsyncSession. Defaults to a
            sessionmaker bound to ``engine``; tests inject a mocked session
            factory here so no real database connection is required.
    """
    require_env()
    environment = os.environ["ENVIRONMENT"]
    if environment != "staging":
        sys.exit(
            "seed_staging: refusing to run because ENVIRONMENT="
            f"{environment!r}, not 'staging'. This script creates Auth users "
            "and writes test data; it must never run against production."
        )

    guardian_email = os.environ["SEED_GUARDIAN_EMAIL"]
    admin_email = os.environ["SEED_ADMIN_EMAIL"]
    guardian_password = os.environ["SEED_GUARDIAN_PASSWORD"]
    admin_password = os.environ["SEED_ADMIN_PASSWORD"]
    supabase_url = os.environ["SUPABASE_URL"]
    service_key = os.environ["SUPABASE_SERVICE_KEY"]

    async with httpx.AsyncClient(
        base_url=supabase_url,
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
        timeout=30.0,
    ) as client:
        guardian_subject = await ensure_auth_user(
            client, guardian_email, guardian_password
        )
        admin_subject = await ensure_auth_user(client, admin_email, admin_password)

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
            select(User).where(User.authn_subject == guardian_subject)
        )
        if existing is not None:
            print("Staging fixtures already seeded; nothing to do.")
            return

        family = Family(name=_FAMILY_NAME)
        session.add(family)
        await session.flush()

        profile = ChildProfile(
            family_id=family.id,
            display_name=_CHILD_DISPLAY_NAME,
            age_band=_CHILD_AGE_BAND,
        )
        session.add(profile)

        guardian = User(
            family_id=family.id, role="guardian", authn_subject=guardian_subject
        )
        session.add(guardian)
        session.add(
            User(family_id=family.id, role="admin", authn_subject=admin_subject)
        )
        await session.flush()

        await _publish_fixture_stories(session, family, profile, guardian)

        await session.commit()
        print(
            f"Seeded staging family {family.id}, profile {profile.id}, "
            f"guardian+admin Auth users, and {len(_STORIES)} published "
            "stories."
        )


def main() -> None:
    """Entry point for the staging seed script."""
    asyncio.run(seed())


if __name__ == "__main__":
    main()
