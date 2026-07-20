"""Unit tests for the catalog-publish CLI's authorization boundary.

``_load_admin_principal`` is documented as "the ONLY authorization check in
this CLI path" (there is no HTTP request, so ``api/deps.py``'s admin gate
never runs). It touches the database only through a single
``session.get(User, approved_by)`` call, so a minimal fake session double
(mirroring ``tests/unit/test_resume_manual_fill.py``'s own ``_FakeSession``
pattern) is enough to exercise every branch without a real Postgres
connection. DB-backed coverage for ``_load_catalog_story_for_update`` (which
runs a real ``SELECT ... FOR UPDATE``) lives in
``tests/integration/test_catalog_publish.py``.
"""

from __future__ import annotations

import uuid

import pytest

from cyo_adventure.core.exceptions import AuthorizationError, ResourceNotFoundError
from cyo_adventure.db.models import User
from cyo_adventure.publishing.catalog_publish import _load_admin_principal

pytestmark = pytest.mark.asyncio


class _FakeSession:
    """Minimal async session double for ``_load_admin_principal``.

    Only implements what this function's code path touches: ``session.get``
    for the User lookup, seeded with a single row (or None) regardless of
    the id passed in, matching ``test_resume_manual_fill.py``'s own
    ``_FakeSession`` convention.
    """

    def __init__(self, *, user: User | None) -> None:
        self._user = user

    async def get(self, model: type[object], key: object) -> object | None:
        """Return the seeded user, ignoring the requested model/key."""
        _ = (model, key)
        return self._user


def _user(*, role: str, is_admin: bool) -> User:
    """Build an in-memory (never persisted) User row.

    Never added to a session, so the ``ck_user_role`` DB CHECK constraint
    (which restricts ``role`` to 'guardian'/'child'/'admin') never fires;
    this is what lets ``test_rejects_a_row_with_an_unmodeled_role`` below
    construct a role value that could never actually reach the database.
    """
    return User(
        id=uuid.uuid4(),
        family_id=uuid.uuid4(),
        role=role,
        is_admin=is_admin,
        authn_subject=f"subject-{uuid.uuid4()}",
    )


async def test_load_admin_principal_rejects_unknown_user() -> None:
    """No User row for ``approved_by`` raises ResourceNotFoundError."""
    session = _FakeSession(user=None)
    approved_by = uuid.uuid4()

    with pytest.raises(ResourceNotFoundError, match=str(approved_by)):
        await _load_admin_principal(session, approved_by)  # type: ignore[arg-type]


async def test_load_admin_principal_rejects_non_admin_user() -> None:
    """A real but non-admin User (a plain guardian) raises AuthorizationError.

    Asserts requirement (b): a ``--approved-by`` user with ``is_admin=False``
    must be rejected, so this command cannot be used to publish a catalog
    story under a non-admin's identity.
    """
    session = _FakeSession(user=_user(role="guardian", is_admin=False))

    with pytest.raises(AuthorizationError, match="admin role required"):
        await _load_admin_principal(session, uuid.uuid4())  # type: ignore[arg-type]


async def test_load_admin_principal_rejects_a_row_with_an_unmodeled_role() -> None:
    """A User row whose ``role`` is outside the closed Role set is rejected cleanly.

    Regression for the Medium finding: ``Role(user.role)`` used to be
    unguarded, so a corrupted/hand-edited row would raise a bare ValueError
    that escapes main()'s ``except ProjectBaseError`` handler and prints a
    raw traceback instead of a clean "promotion failed: ..." message. This
    asserts the guarded coercion now raises AuthorizationError (a
    ProjectBaseError subclass) instead.
    """
    session = _FakeSession(user=_user(role="rogue-role", is_admin=True))

    with pytest.raises(AuthorizationError, match="unrecognized role"):
        await _load_admin_principal(session, uuid.uuid4())  # type: ignore[arg-type]
