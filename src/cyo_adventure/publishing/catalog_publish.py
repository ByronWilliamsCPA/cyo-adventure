"""Promote an in-review catalog story to published/catalog visibility.

A distinct, explicitly-invoked command, deliberately kept separate from
``generation/import_catalog.py`` (which never publishes; see that module's
own docstring and ADR-005's mandatory human approval requirement). This runs
outside any HTTP request, so it never passes through ``api/deps.py``'s
per-request auth layer; it enforces its own, narrower scope instead:

- Only a ``Storybook`` owned by ``CATALOG_FAMILY_ID`` may be promoted (a
  catalog-import artifact, never an arbitrary family's story).
- The operator must supply a real, existing admin ``User`` id
  (``--approved-by``); this command loads that row and refuses to proceed
  unless it resolves to an admin :class:`~cyo_adventure.api.deps.Principal`,
  mirroring ``api/approval.py::_load_admin_story``'s own admin-role check.

The actual state transition and provenance stamping is delegated entirely to
``publishing/service.py::approve``, the codebase's sole publish path; this
module only assembles the inputs (a locked ``Storybook`` row, an admin
``Principal``, the latest version) that function requires.

Usage:
    uv run python -m cyo_adventure.publishing.catalog_publish <storybook-id> --approved-by <admin-user-uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from cyo_adventure.api.deps import Principal, Role
from cyo_adventure.core.database import get_session
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ProjectBaseError,
    ResourceNotFoundError,
)
from cyo_adventure.db.models import (
    CATALOG_FAMILY_ID,
    Storybook,
    StorybookVersion,
    User,
)
from cyo_adventure.publishing import service as approval_service
from cyo_adventure.publishing.state_machine import Visibility

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def _load_catalog_story_for_update(
    session: AsyncSession, storybook_id: str
) -> Storybook:
    """Load and row-lock a ``CATALOG_FAMILY_ID``-owned storybook, or raise.

    Args:
        session: Open async session; caller owns the transaction.
        storybook_id: The story id to load.

    Returns:
        The locked Storybook row.

    Raises:
        ResourceNotFoundError: If no storybook with this id is owned by
            ``CATALOG_FAMILY_ID``. This includes the case where the id
            exists but belongs to a real family: this command refuses to
            touch non-catalog content, and deliberately raises the same
            "not found" (rather than a distinguishing "wrong family") error
            so it never confirms the existence of an out-of-scope story.
    """
    # #CRITICAL: security: scoping to CATALOG_FAMILY_ID here (not "any
    # storybook") is this command's entire safety boundary, since it bypasses
    # api/deps.py's per-request admin/family authorization entirely. Locking
    # with FOR UPDATE mirrors api/approval.py::_load_admin_story so a
    # concurrent promotion of the same story (this CLI run twice, or racing
    # the admin console's own approve endpoint) cannot both pass approve()'s
    # in-memory status check before either commits.
    # #VERIFY: test_promote_catalog_story_refuses_a_non_catalog_story asserts
    # a real-family story id raises ResourceNotFoundError.
    stmt = (
        select(Storybook)
        .where(Storybook.id == storybook_id, Storybook.family_id == CATALOG_FAMILY_ID)
        .with_for_update()
    )
    book = (await session.execute(stmt)).scalar_one_or_none()
    if book is None:
        msg = f"catalog storybook '{storybook_id}' not found"
        raise ResourceNotFoundError(
            msg, resource_type="Storybook", resource_id=storybook_id
        )
    return book


async def _load_admin_principal(
    session: AsyncSession, approved_by: uuid.UUID
) -> Principal:
    """Load a User and build an admin Principal from it, or raise.

    Args:
        session: Open async session.
        approved_by: The operator-supplied admin user id.

    Returns:
        A Principal with ``is_admin=True``.

    Raises:
        ResourceNotFoundError: If no User with this id exists.
        AuthorizationError: If the User exists but does not hold the admin
            capability (mirrors ``api/approval.py::_load_admin_story``'s
            own check), or if its stored ``role`` is outside the closed
            :class:`Role` set.
    """
    # #CRITICAL: security: this is the ONLY authorization check in this CLI
    # path (there is no HTTP request, so api/deps.py's admin gate never
    # runs); a caller supplying a non-admin or nonexistent --approved-by
    # must be rejected here, before approval_service.approve ever runs, so
    # this command cannot be used to publish a story under a fabricated
    # approver identity.
    # #VERIFY: test_load_admin_principal_rejects_non_admin_user asserts
    # AuthorizationError for a real but non-admin User row;
    # test_load_admin_principal_rejects_unknown_user asserts
    # ResourceNotFoundError.
    user = await session.get(User, approved_by)
    if user is None:
        msg = f"user '{approved_by}' not found"
        raise ResourceNotFoundError(
            msg, resource_type="User", resource_id=str(approved_by)
        )
    # #CRITICAL: security: unlike api/deps.py::require_principal (which lets
    # an unmodeled ``role`` raise a bare ValueError, relying on FastAPI's
    # ASGI-level exception handling to turn it into a 500), this command runs
    # outside any request cycle: main()'s only handler is
    # ``except ProjectBaseError``, so an unguarded Role(...) coercion failure
    # here would print a raw traceback instead of a clean "promotion failed"
    # message. Guarding it and raising AuthorizationError keeps this CLI's
    # error surface consistent for every rejection path.
    # #VERIFY: see test_load_admin_principal_rejects_a_row_with_an_unmodeled_role,
    # which asserts AuthorizationError (never a bare ValueError) for a role
    # outside the closed Role set.
    try:
        role = Role(user.role)
    except ValueError as exc:
        msg = f"user '{approved_by}' has an unrecognized role: {user.role!r}"
        raise AuthorizationError(msg, required_permission="admin") from exc
    principal = Principal(
        subject=str(user.id),
        user_id=user.id,
        role=role,
        family_id=user.family_id,
        profile_ids=frozenset(),
        is_admin=user.is_admin,
    )
    if not principal.is_admin:
        msg = "admin role required to approve a catalog story"
        raise AuthorizationError(msg, required_permission="admin")
    return principal


async def _latest_version(session: AsyncSession, storybook_id: str) -> int:
    """Return the highest version number for a storybook.

    Mirrors ``api/approval.py::_latest_version`` (slice-1 stories are
    single-version, so "approve the storybook" means approve its latest/only
    version); duplicated rather than imported to keep this module
    independent of the FastAPI router layer.

    Args:
        session: Open async session.
        storybook_id: The story id.

    Returns:
        The latest version number.

    Raises:
        ResourceNotFoundError: If the story has no versions.
    """
    latest = await session.scalar(
        select(func.max(StorybookVersion.version)).where(
            StorybookVersion.storybook_id == storybook_id
        )
    )
    if latest is None:
        msg = f"storybook '{storybook_id}' has no versions"
        raise ResourceNotFoundError(
            msg, resource_type="StorybookVersion", resource_id=storybook_id
        )
    return latest


async def promote_catalog_story(
    session: AsyncSession, storybook_id: str, approved_by: uuid.UUID
) -> StorybookVersion:
    """Approve and publish a ``CATALOG_FAMILY_ID`` story with catalog visibility.

    Args:
        session: Open async session; caller owns the transaction (commits on
            success, matching the codebase's request-session convention;
            see ``publishing/service.py``'s module docstring).
        storybook_id: The story to promote (must be owned by
            ``CATALOG_FAMILY_ID``).
        approved_by: A real, existing admin User id.

    Returns:
        The stamped StorybookVersion row.

    Raises:
        ResourceNotFoundError: If the story is not a catalog story, if
            ``approved_by`` does not resolve to a User, or if the story has
            no versions.
        AuthorizationError: If ``approved_by`` resolves to a non-admin User.
        StateTransitionError: If the story is not currently ``in_review``
            (propagated from ``publishing.service.approve``; a story import
            left at ``needs_revision`` cannot be promoted directly).
        BusinessLogicError: If the latest version has no moderation report,
            or (series books only) series-chain validation fails
            (propagated from ``publishing.service.approve``).
    """
    book = await _load_catalog_story_for_update(session, storybook_id)
    principal = await _load_admin_principal(session, approved_by)
    version = await _latest_version(session, storybook_id)
    return await approval_service.approve(
        session, principal, book, version, visibility=Visibility.CATALOG
    )


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the catalog-publish CLI argument parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Promote an in-review catalog story (family_id=CATALOG_FAMILY_ID) "
            "to published, visibility=catalog."
        )
    )
    parser.add_argument("storybook_id", help="The story id to promote.")
    parser.add_argument(
        "--approved-by",
        required=True,
        help="An existing admin User UUID to stamp as the approver.",
    )
    return parser


async def _run(storybook_id: str, approved_by: uuid.UUID) -> StorybookVersion:
    """Open a session, promote the story, and commit.

    Args:
        storybook_id: The story to promote.
        approved_by: A real, existing admin User id.

    Returns:
        The stamped StorybookVersion row.
    """
    async with get_session() as session:
        version_row = await promote_catalog_story(session, storybook_id, approved_by)
        await session.commit()
        return version_row


def main(argv: list[str] | None = None) -> int:
    """Parse args, promote the story, and print the result.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Exit code: 0 on success, 1 on any handled failure.
    """
    args = build_arg_parser().parse_args(argv)
    storybook_id: str = args.storybook_id
    raw_approved_by: str = args.approved_by
    try:
        approved_by = uuid.UUID(raw_approved_by)
    except ValueError:
        sys.stderr.write(f"error: invalid --approved-by UUID: {raw_approved_by}\n")
        return 1
    try:
        version_row = asyncio.run(_run(storybook_id, approved_by))
    except ProjectBaseError as exc:
        sys.stderr.write(f"promotion failed: {exc}\n")
        return 1
    sys.stdout.write(
        f"published {storybook_id} v{version_row.version} (visibility=catalog)\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
