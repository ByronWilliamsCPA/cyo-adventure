"""Unit tests for the catalog-publish CLI's authorization boundary and entrypoint.

``_load_admin_principal`` is documented as "the ONLY authorization check in
this CLI path" (there is no HTTP request, so ``api/deps.py``'s admin gate
never runs). It touches the database only through a single
``session.get(User, approved_by)`` call, so a minimal fake session double
(mirroring ``tests/unit/test_resume_manual_fill.py``'s own ``_FakeSession``
pattern) is enough to exercise every branch without a real Postgres
connection. DB-backed coverage for ``_load_catalog_story_for_update`` (which
runs a real ``SELECT ... FOR UPDATE``) lives in
``tests/integration/test_catalog_publish.py``.

``main()`` is exercised here too (mocking ``_run`` rather than opening a real
session), since it is pure CLI plumbing (argv parsing, exit codes, stdout/
stderr messages) with no DB or moderation-pipeline behavior of its own to
verify at the integration layer.

Async tests are marked individually with ``@pytest.mark.asyncio`` (not a
module-level ``pytestmark``) because this module mixes them with the sync
``main()`` tests below; see ``tests/CLAUDE.md``'s pytest-conventions note.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.core.exceptions import AuthorizationError, ResourceNotFoundError
from cyo_adventure.db.models import StorybookVersion, User
from cyo_adventure.publishing.catalog_publish import (
    _latest_version,
    _load_admin_principal,
    main,
)

_MODULE = "cyo_adventure.publishing.catalog_publish"


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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_load_admin_principal_rejects_unknown_user() -> None:
    """No User row for ``approved_by`` raises ResourceNotFoundError."""
    session = _FakeSession(user=None)
    approved_by = uuid.uuid4()

    with pytest.raises(ResourceNotFoundError, match=str(approved_by)):
        await _load_admin_principal(session, approved_by)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_load_admin_principal_rejects_non_admin_user() -> None:
    """A real but non-admin User (a plain guardian) raises AuthorizationError.

    Asserts requirement (b): a ``--approved-by`` user with ``is_admin=False``
    must be rejected, so this command cannot be used to publish a catalog
    story under a non-admin's identity.
    """
    session = _FakeSession(user=_user(role="guardian", is_admin=False))

    with pytest.raises(AuthorizationError, match="admin role required"):
        await _load_admin_principal(session, uuid.uuid4())  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.asyncio
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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_latest_version_raises_when_no_versions_exist() -> None:
    """A storybook with zero StorybookVersion rows raises ResourceNotFoundError.

    Covers the partial-import state this command must refuse rather than
    crash on: import_catalog.py's own creation path always inserts version 1
    in the same flush as the Storybook row, so this should not happen in
    practice, but a hand-seeded or corrupted row with no version rows must
    still fail cleanly (a ResourceNotFoundError, caught by main()'s handler)
    rather than let ``max(...)`` returning ``None`` propagate as a bare
    ``TypeError`` from an unguarded arithmetic/format use downstream.
    """
    session = AsyncMock(spec=AsyncSession)
    session.scalar = AsyncMock(return_value=None)

    with pytest.raises(ResourceNotFoundError, match="no versions"):
        await _latest_version(session, "some-story-id")


@pytest.mark.unit
class TestMain:
    """Sync tests for the ``main()`` entrypoint (argv parsing, exit codes).

    ``main()`` itself is a sync function (it drives its own ``asyncio.run``
    internally), so these tests call it directly rather than going through
    pytest-asyncio; ``_run`` is patched so no real session or DB is touched.
    """

    def test_rejects_invalid_approved_by_uuid(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A malformed --approved-by value is rejected before any async work runs."""
        exit_code = main(["storybook-1", "--approved-by", "not-a-uuid"])

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "invalid --approved-by UUID: not-a-uuid" in captured.err

    def test_reports_a_project_base_error_as_a_clean_failure(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A ProjectBaseError from the publish path exits 1 with a clean message.

        Regression for main()'s only exception handler: a
        ProjectBaseError subclass (here AuthorizationError, e.g. a
        non-admin --approved-by, or any other domain rejection from
        promote_catalog_story) must produce an operator-facing
        "promotion failed: ..." message and exit code 1, never an uncaught
        traceback escaping to the shell.
        """

        async def _raise_authorization_error(
            storybook_id: str, approved_by: uuid.UUID
        ) -> StorybookVersion:
            _ = (storybook_id, approved_by)
            msg = "admin role required to approve a catalog story"
            raise AuthorizationError(msg, required_permission="admin")

        monkeypatch.setattr(f"{_MODULE}._run", _raise_authorization_error)

        exit_code = main(["storybook-1", "--approved-by", str(uuid.uuid4())])

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "promotion failed: admin role required" in captured.err

    def test_success_prints_the_published_summary(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A clean run prints the published-summary line and exits 0."""

        async def _fake_run(
            storybook_id: str, approved_by: uuid.UUID
        ) -> StorybookVersion:
            _ = approved_by
            return StorybookVersion(storybook_id=storybook_id, version=3, blob={})

        monkeypatch.setattr(f"{_MODULE}._run", _fake_run)

        exit_code = main(["storybook-1", "--approved-by", str(uuid.uuid4())])

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "published storybook-1 v3 (visibility=catalog)" in captured.out
