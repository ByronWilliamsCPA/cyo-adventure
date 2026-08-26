"""Seed the three catalog lifecycle states for workflow validation.

Given a catalog whose authored drafts are already imported under the
well-known ``CATALOG_FAMILY_ID`` family (by
``generation/import_catalog.py``), this script arranges a deliberate mix of
lifecycle states so the admin-review, guardian-review, and child-read
workflows can each be validated end to end in staging AND production:

- **child-readable**: promoted to ``published``/``visibility=catalog`` and
  assigned to the single resolved test child profile (the reader path).
- **pending guardian review**: promoted to ``published``/``visibility=catalog``
  but left unassigned (a guardian must browse and assign it).
- **pending admin review**: left at ``in_review`` (the admin approval queue).

Promotion goes through ``publishing/catalog_publish.py::promote_catalog_story``,
the same ADR-005 human-approval path the ``catalog-publish`` CLI uses, so each
promotion is a per-story admin decision, never a bulk auto-approve. Assignments
are attributed to the resolved admin, mirroring ``seed_series_catalog.py``.

Dry-run by default (reads and prints the plan, writes nothing). Pass
``--apply`` to write. Writing to production additionally requires
``SEED_CONFIRM=1``.

This script never calls the real moderation pipeline (promote_catalog_story
only transitions already-validated rows), but Settings still boots with
review_provider defaulting to "mock", and core/config.py now refuses to boot
the mock reviewer outside environment="local" unless
``CYO_ADVENTURE_ALLOW_MOCK_REVIEW=1`` is set (design doc section 2.4 / gap
G1). Set it alongside ENVIRONMENT below, or export REVIEW_PROVIDER to
whatever real backend the target environment already runs.

Inspect staging (dry run)::

    ENVIRONMENT=staging CYO_ADVENTURE_ALLOW_MOCK_REVIEW=1 \\
        CYO_ADVENTURE_DATABASE_URL=... \\
        uv run python scripts/seed_catalog_validation_states.py

Apply to staging::

    ENVIRONMENT=staging CYO_ADVENTURE_ALLOW_MOCK_REVIEW=1 \\
        CYO_ADVENTURE_DATABASE_URL=... \\
        uv run python scripts/seed_catalog_validation_states.py --apply

Apply to production (requires explicit confirmation)::

    ENVIRONMENT=production SEED_CONFIRM=1 CYO_ADVENTURE_ALLOW_MOCK_REVIEW=1 \\
        CYO_ADVENTURE_DATABASE_URL=... \\
        uv run python scripts/seed_catalog_validation_states.py --apply

The child profile the readable books are assigned to is resolved exactly as in
``seed_series_catalog.py``: the single ``ChildProfile`` whose family name is in
an allowlist (default "E2E Test Family" or "Test Family"; override with
``SEED_ASSIGN_FAMILY``). If zero or more than one profile matches, the script
refuses to run rather than risk assigning fixture content to a real family.

Idempotent by design: books already in the target state are left untouched and
reported as "already", so re-running is safe.

Catalog drafts go through the same moderation pipeline as any other story at
import time (see ``generation/import_catalog.py``) and can legitimately carry
a block or high-severity finding; ``publishing/service.py::approve`` then
refuses the promotion unless a non-blank override reason is supplied
(``approve_requires_override_reason``). Set ``SEED_OVERRIDE_REASON`` to
override the default justification text used for every promotion in this
run; the default is broad enough for the fixture catalog this script targets
and is not intended as a per-book audit trail.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from cyo_adventure.core.database import get_engine
from cyo_adventure.core.exceptions import ProjectBaseError
from cyo_adventure.db.models import (
    CATALOG_FAMILY_ID,
    ChildProfile,
    Family,
    Storybook,
    StorybookAssignment,
    User,
)
from cyo_adventure.publishing.catalog_publish import promote_catalog_story

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

REQUIRED_ENV: tuple[str, ...] = ("CYO_ADVENTURE_DATABASE_URL",)
_ALLOWED_ENVIRONMENTS = frozenset({"staging", "production"})
_DEFAULT_ASSIGN_FAMILIES = frozenset({"E2E Test Family", "Test Family"})

# The recommended validation mix across the authored catalog drafts. The three
# child-readable titles are the 8-11 band books, age-matched to the E2E test
# child so the reader path validates cleanly. The pending-guardian set spans
# other bands so the guardian browse queue has representative coverage. Every
# other imported draft stays at in_review (the admin review queue).
_CHILD_READABLE: tuple[str, ...] = (
    "sk_cave_of_echoes",
    "sk_clockwork_menagerie",
    "sk_sky_ship_stowaway",
)
_PENDING_GUARDIAN: tuple[str, ...] = (
    "sk_ashfall_expedition",
    "sk_lost_mitten",
    "sk_lantern_festival",
    "sk_midnight_museum",
    "sk_vanishing_orchard",
)
_PUBLISHED = "published"
_IN_REVIEW = "in_review"
_DEFAULT_OVERRIDE_REASON = (
    "seed_catalog_validation_states: fixture catalog promotion for workflow "
    "validation; see script docstring for scope (SEED_OVERRIDE_REASON to "
    "override)."
)


def require_env() -> None:
    """Exit with a clear message naming every required env var that is missing."""
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        sys.exit(
            "seed_catalog_validation_states: missing required environment "
            "variable(s): " + ", ".join(missing)
        )


async def _resolve_test_child_profile(session: AsyncSession) -> ChildProfile:
    """Resolve the single test child profile the readable books are assigned to.

    #CRITICAL: security: this script writes to staging AND production. Assigning
    a fixture book to the wrong profile would put it in front of a real family's
    child. To fail safe it NEVER guesses: it proceeds only when exactly one
    child profile matches the allowlisted test-family name(s), and exits
    otherwise. #VERIFY: mirrors seed_series_catalog.py::_resolve_test_child_profile.
    """
    override = os.environ.get("SEED_ASSIGN_FAMILY")
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
        sys.exit(
            "seed_catalog_validation_states: expected exactly one child profile "
            f"in a test family ({allowed}); found {len(rows)}: {found}. Refusing "
            "to guess which profile to assign readable books to."
        )

    profile, _name = rows[0]
    return profile


async def _resolve_admin_user(session: AsyncSession, family_id: uuid.UUID) -> User:
    """Resolve the admin user to attribute promotions and assignments to.

    Prefers an admin belonging to ``family_id`` (the resolved test family);
    falls back to any ``is_admin=True`` user. #VERIFY: mirrors
    seed_series_catalog.py::_resolve_admin_user.
    """
    admins = (await session.scalars(select(User).where(User.is_admin.is_(True)))).all()
    if not admins:
        sys.exit(
            "seed_catalog_validation_states: no admin (is_admin=True) user found; "
            "cannot attribute promotions/assignments to anyone."
        )
    for admin in admins:
        if admin.family_id == family_id:
            return admin
    return admins[0]


async def _catalog_state(session: AsyncSession) -> dict[str, tuple[str, str, int]]:
    """Return {storybook_id: (status, visibility, assignment_count)} for the catalog."""
    rows = (
        await session.execute(
            select(
                Storybook.id,
                Storybook.status,
                Storybook.visibility,
                func.count(StorybookAssignment.child_profile_id),
            )
            .outerjoin(
                StorybookAssignment,
                StorybookAssignment.storybook_id == Storybook.id,
            )
            .where(Storybook.family_id == CATALOG_FAMILY_ID)
            .group_by(Storybook.id, Storybook.status, Storybook.visibility)
        )
    ).all()
    return {sid: (status, vis, int(n)) for sid, status, vis, n in rows}


def _plan(
    state: dict[str, tuple[str, str, int]],
) -> tuple[list[str], list[str], list[str]]:
    """Compute (to_promote, to_assign, missing) against the current catalog state.

    to_promote: target books currently at in_review that must be published.
    to_assign: child-readable books not yet assigned to the test child.
    missing: target ids not present in the catalog at all (import not run).
    """
    targets = _CHILD_READABLE + _PENDING_GUARDIAN
    missing = [sid for sid in targets if sid not in state]
    to_promote = [
        sid for sid in targets if sid in state and state[sid][0] == _IN_REVIEW
    ]
    to_assign = [sid for sid in _CHILD_READABLE if sid in state and state[sid][2] == 0]
    return to_promote, to_assign, missing


def _print_plan(
    state: dict[str, tuple[str, str, int]],
    to_promote: list[str],
    to_assign: list[str],
    missing: list[str],
) -> None:
    """Print the current catalog state and the intended changes."""
    print(f"catalog books present: {len(state)}")
    print("\n--- current state of target books ---")
    for sid in _CHILD_READABLE + _PENDING_GUARDIAN:
        if sid in state:
            status, vis, n = state[sid]
            print(f"  {sid:36s} {status:12s} {vis:8s} assignments={n}")
        else:
            print(f"  {sid:36s} MISSING (not imported)")
    print("\n--- planned changes ---")
    print(f"  promote to published/catalog ({len(to_promote)}): {to_promote or 'none'}")
    print(f"  assign to test child ({len(to_assign)}): {to_assign or 'none'}")
    if missing:
        print(f"  WARNING missing (run import_catalog first): {missing}")
    remaining = sum(1 for s in state.values() if s[0] == _IN_REVIEW) - len(to_promote)
    print(f"  will remain at in_review (pending admin): ~{max(remaining, 0)}")


async def run(*, apply: bool) -> int:
    """Compute the plan and, when ``apply`` is set, execute it.

    Returns a process exit code.
    """
    require_env()
    environment = os.environ.get("ENVIRONMENT", "")
    if apply:
        if environment not in _ALLOWED_ENVIRONMENTS:
            sys.exit(
                "seed_catalog_validation_states: --apply requires ENVIRONMENT to "
                f"be one of {sorted(_ALLOWED_ENVIRONMENTS)}, got {environment!r}."
            )
        # #CRITICAL: security: production is real, guardian-owned data; an
        # accidental --apply must not silently promote/assign against it.
        # SEED_CONFIRM=1 is a deliberate human opt-in; staging needs no gate.
        # #VERIFY: the production branch below refuses without SEED_CONFIRM=1.
        if environment == "production" and os.environ.get("SEED_CONFIRM") != "1":
            sys.exit(
                "seed_catalog_validation_states: refusing to --apply against "
                "PRODUCTION without SEED_CONFIRM=1."
            )

    engine = get_engine()
    new_session = async_sessionmaker(engine, expire_on_commit=False)

    async with new_session() as session:
        state = await _catalog_state(session)
        profile = await _resolve_test_child_profile(session)
        admin = await _resolve_admin_user(session, profile.family_id)
        to_promote, to_assign, missing = _plan(state)

    print(f"environment: {environment or '(unset)'}   apply: {apply}")
    print(f"resolved admin: {admin.id}   test child: {profile.id}")
    _print_plan(state, to_promote, to_assign, missing)

    if not apply:
        print("\nDRY RUN: no changes written. Re-run with --apply to execute.")
        return 0

    override_reason = os.environ.get("SEED_OVERRIDE_REASON") or _DEFAULT_OVERRIDE_REASON

    print("\n--- applying ---")
    # Promote each target in its own transaction so one failure cannot half-apply
    # the batch; promote_catalog_story enforces in_review + moderation-report +
    # is_admin, then sets visibility=catalog (ADR-005 human approval per story).
    # override_reason is passed unconditionally: approve() only requires (and
    # records) it when the version actually carries a block/high-severity
    # finding, so passing it for every book is harmless for the rest.
    for sid in to_promote:
        async with new_session() as session:
            try:
                await promote_catalog_story(
                    session, sid, admin.id, override_reason=override_reason
                )
                await session.commit()
                print(f"  promoted: {sid}")
            except (ProjectBaseError, SQLAlchemyError) as exc:
                await session.rollback()
                print(f"  FAILED to promote {sid}: {type(exc).__name__}: {exc}")

    for sid in to_assign:
        async with new_session() as session:
            book = await session.get(Storybook, sid)
            if book is None or book.status != _PUBLISHED:
                print(f"  SKIP assign {sid}: not published (promotion failed?)")
                continue
            exists = await session.scalar(
                select(StorybookAssignment).where(
                    StorybookAssignment.storybook_id == sid,
                    StorybookAssignment.child_profile_id == profile.id,
                )
            )
            if exists is not None:
                print(f"  assign {sid}: already assigned")
                continue
            session.add(
                StorybookAssignment(
                    child_profile_id=profile.id,
                    storybook_id=sid,
                    assigned_by=admin.id,
                )
            )
            await session.commit()
            print(f"  assigned: {sid} -> child {profile.id}")

    async with new_session() as session:
        final = await _catalog_state(session)
    readable = sum(
        1
        for sid in _CHILD_READABLE
        if sid in final and final[sid][0] == _PUBLISHED and final[sid][2] > 0
    )
    guardian_pending = sum(
        1
        for status, vis, n in final.values()
        if status == _PUBLISHED and vis == "catalog" and n == 0
    )
    admin_pending = sum(1 for s in final.values() if s[0] == _IN_REVIEW)
    print("\n--- final catalog state ---")
    print(f"  child-readable (published/catalog + assigned): {readable}")
    print(
        f"  pending guardian review (published/catalog, unassigned): {guardian_pending}"
    )
    print(f"  pending admin review (in_review): {admin_pending}")
    return 0


def main() -> None:
    """Entry point: parse args and run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the changes. Default is a dry run that only prints the plan.",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(apply=args.apply)))


if __name__ == "__main__":
    main()
