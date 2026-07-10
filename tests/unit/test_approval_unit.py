"""Docker-independent unit tests for cyo_adventure.api.approval.

These call the handler functions and private helpers directly, with the
publishing service replaced by AsyncMock via monkeypatch. No DB, no ASGI
stack, no Docker.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.dialects import postgresql

from cyo_adventure.api import approval
from cyo_adventure.api.deps import Principal, RequestContext
from cyo_adventure.api.schemas import ReviewQueueView, SendBackRequest
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import Storybook, StorybookVersion

pytestmark = pytest.mark.asyncio


def _principal(role: str) -> Principal:
    """Return a minimal Principal with the given role."""
    return Principal(
        subject=f"{role}-x",
        user_id=uuid.uuid4(),
        role=role,
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
    )


def _story(status: str, *, current: int | None = None) -> Storybook:
    """Construct a Storybook ORM instance without a session."""
    return Storybook(
        id="s1",
        family_id=uuid.uuid4(),
        status=status,
        current_published_version=current,
    )


def _ctx(role: str, session: AsyncMock) -> RequestContext:
    """Build a RequestContext from a role name and a mock session."""
    return RequestContext(principal=_principal(role), session=session)


def _execute_result(value: object) -> MagicMock:
    """Build a fake `Result` whose `scalar_one_or_none()` returns ``value``.

    Mirrors production ``(await session.execute(stmt)).scalar_one_or_none()``:
    ``execute()`` is awaited, but the `Result` it returns exposes a plain
    (synchronous) `scalar_one_or_none` method.
    """
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


# ---------------------------------------------------------------------------
# _load_admin_story
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_load_admin_story_non_admin_raises_before_load() -> None:
    """A non-admin caller raises AuthorizationError without touching the session."""
    session = AsyncMock()
    ctx = RequestContext(principal=_principal("child"), session=session)

    with pytest.raises(AuthorizationError):
        await approval._load_admin_story(ctx, "s1")

    session.execute.assert_not_awaited()


@pytest.mark.unit
async def test_load_admin_story_missing_raises_404() -> None:
    """An admin caller with an unknown story id raises ResourceNotFoundError."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_execute_result(None))
    ctx = _ctx("admin", session)

    with pytest.raises(ResourceNotFoundError):
        await approval._load_admin_story(ctx, "missing-id")


@pytest.mark.unit
async def test_load_admin_story_returns_book() -> None:
    """An admin caller with a known story id returns the Storybook."""
    book = _story("draft")
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_execute_result(book))
    ctx = _ctx("admin", session)

    result = await approval._load_admin_story(ctx, "s1")

    assert result is book


@pytest.mark.unit
async def test_load_admin_story_locks_row_for_update() -> None:
    """The admin-story load must carry SELECT ... FOR UPDATE.

    Mirrors how tests/unit/test_reading_api_unit.py pins the lock on
    api/reading.py's read-modify-write load. Every admin transition
    (submit/approve/send_back/archive) loads through this one helper, so
    losing the lock here reopens the concurrent-approve race that lets two
    admins both pass the in-memory status check and the last writer silently
    overwrite `approved_by` (#129 / audit Finding 3).
    """
    book = _story("in_review")
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_execute_result(book))
    ctx = _ctx("admin", session)

    result = await approval._load_admin_story(ctx, "s1")

    assert result is book
    session.execute.assert_awaited_once()
    stmt = session.execute.await_args.args[0]
    where = str(stmt.whereclause)
    assert "storybook" in where.lower()

    # Render with the Postgres dialect (the deployment target): the generic
    # compiler omits skip_locked/nowait clauses, so a weakening would be
    # invisible under str(stmt). skip_locked would let a concurrent admin
    # slip past the lock instead of serializing behind it.
    rendered = str(stmt.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in rendered
    assert "SKIP LOCKED" not in rendered
    assert "NOWAIT" not in rendered


# ---------------------------------------------------------------------------
# _latest_version
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_latest_version_returns_max() -> None:
    """_latest_version returns the integer max version when versions exist."""
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=3)

    result = await approval._latest_version(session, "s1")

    assert result == 3


@pytest.mark.unit
async def test_latest_version_none_raises_404() -> None:
    """_latest_version raises ResourceNotFoundError when no versions exist."""
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=None)

    with pytest.raises(ResourceNotFoundError):
        await approval._latest_version(session, "s1")


# ---------------------------------------------------------------------------
# submit_storybook
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_submit_handler_calls_service_and_returns_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """submit_storybook delegates to service.submit and echoes a state view."""
    book = _story("draft")
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_execute_result(book))
    ctx = _ctx("admin", session)

    async def _submit(*_args: object, **_kwargs: object) -> None:
        book.status = "in_review"

    submit_mock = AsyncMock(side_effect=_submit)
    monkeypatch.setattr("cyo_adventure.publishing.service.submit", submit_mock)

    view = await approval.submit_storybook("s1", ctx)

    assert view.id == "s1"
    submit_mock.assert_awaited_once_with(ctx.session, book)


# ---------------------------------------------------------------------------
# approve_storybook
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_approve_handler_stamps_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """approve_storybook returns a view with approved_by and published_at set."""
    book = _story("in_review")
    approver_id = uuid.uuid4()
    published = datetime.now(UTC)
    version_row = StorybookVersion(
        storybook_id="s1",
        version=1,
        blob={},
        approved_by=approver_id,
        published_at=published,
    )

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_execute_result(book))
    session.scalar = AsyncMock(return_value=1)
    ctx = _ctx("admin", session)

    async def _approve(*_args: object, **_kwargs: object) -> StorybookVersion:
        # Mirror the real service's stamps (publishing/service.py): approve is
        # the sole publish path and sets status AND visibility together. The
        # ORM instance here has no session, so the column default never fires;
        # a fake that skips the visibility stamp fails ApprovedView validation.
        book.status = "published"
        book.visibility = "family"
        return version_row

    approve_mock = AsyncMock(side_effect=_approve)
    monkeypatch.setattr("cyo_adventure.publishing.service.approve", approve_mock)

    view = await approval.approve_storybook("s1", ctx)

    assert view.approved_by == str(approver_id)
    assert view.published_at == published


@pytest.mark.unit
@pytest.mark.parametrize(
    ("approved_by", "published_at"),
    [
        pytest.param(None, datetime.now(UTC), id="missing_approver"),
        pytest.param(uuid.uuid4(), None, id="missing_published_at"),
        pytest.param(None, None, id="missing_both"),
    ],
)
async def test_approve_handler_missing_stamp_raises_business_logic_error(
    monkeypatch: pytest.MonkeyPatch,
    approved_by: uuid.UUID | None,
    published_at: datetime | None,
) -> None:
    """approve_storybook rejects a service response missing its approval stamp.

    This is the defensive #CRITICAL invariant guard in approve_storybook: the
    publishing service is contracted to always set both approved_by and
    published_at together, so a version_row missing either must never reach
    the response layer as if it were a valid ApprovedView.
    """
    from cyo_adventure.core.exceptions import BusinessLogicError

    book = _story("in_review")
    version_row = StorybookVersion(
        storybook_id="s1",
        version=1,
        blob={},
        approved_by=approved_by,
        published_at=published_at,
    )

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_execute_result(book))
    session.scalar = AsyncMock(return_value=1)
    ctx = _ctx("admin", session)

    async def _approve(*_args: object, **_kwargs: object) -> StorybookVersion:
        book.status = "published"
        return version_row

    approve_mock = AsyncMock(side_effect=_approve)
    monkeypatch.setattr("cyo_adventure.publishing.service.approve", approve_mock)

    with pytest.raises(
        BusinessLogicError, match="approved version is missing its approval stamp"
    ):
        await approval.approve_storybook("s1", ctx)


# ---------------------------------------------------------------------------
# send_back_storybook
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_send_back_handler_echoes_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """send_back_storybook echoes the reason in the returned view."""
    book = _story("in_review")
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_execute_result(book))
    ctx = _ctx("admin", session)
    body = SendBackRequest(reason="too scary")

    async def _send_back(*_args: object, **_kwargs: object) -> None:
        book.status = "needs_revision"

    send_back_mock = AsyncMock(side_effect=_send_back)
    monkeypatch.setattr("cyo_adventure.publishing.service.send_back", send_back_mock)

    view = await approval.send_back_storybook("s1", body, ctx)

    assert view.reason == "too scary"
    send_back_mock.assert_awaited_once_with(
        ctx.session, ctx.principal, book, "too scary"
    )


# ---------------------------------------------------------------------------
# archive_storybook
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_archive_handler_calls_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """archive_storybook delegates to service.archive and returns a state view."""
    book = _story("published", current=1)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_execute_result(book))
    ctx = _ctx("admin", session)

    async def _archive(*_args: object, **_kwargs: object) -> None:
        book.status = "archived"

    archive_mock = AsyncMock(side_effect=_archive)
    monkeypatch.setattr("cyo_adventure.publishing.service.archive", archive_mock)

    view = await approval.archive_storybook("s1", ctx)

    archive_mock.assert_awaited_once_with(ctx.session, ctx.principal, book)
    assert view.id == "s1"


# ---------------------------------------------------------------------------
# Guardian (non-admin) role is blocked on all handlers
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_submit_handler_blocks_guardian() -> None:
    """submit_storybook blocks a guardian principal with AuthorizationError."""
    session = AsyncMock()
    ctx = _ctx("guardian", session)

    with pytest.raises(AuthorizationError):
        await approval.submit_storybook("s1", ctx)


@pytest.mark.unit
async def test_approve_handler_blocks_guardian() -> None:
    """approve_storybook blocks a guardian principal with AuthorizationError."""
    session = AsyncMock()
    ctx = _ctx("guardian", session)

    with pytest.raises(AuthorizationError):
        await approval.approve_storybook("s1", ctx)


@pytest.mark.unit
async def test_send_back_handler_blocks_guardian() -> None:
    """send_back_storybook blocks a guardian principal with AuthorizationError."""
    session = AsyncMock()
    ctx = _ctx("guardian", session)
    body = SendBackRequest(reason="nope")

    with pytest.raises(AuthorizationError):
        await approval.send_back_storybook("s1", body, ctx)


@pytest.mark.unit
async def test_archive_handler_blocks_guardian() -> None:
    """archive_storybook blocks a guardian principal with AuthorizationError."""
    session = AsyncMock()
    ctx = _ctx("guardian", session)

    with pytest.raises(AuthorizationError):
        await approval.archive_storybook("s1", ctx)


# ---------------------------------------------------------------------------
# get_review_surface
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_review_surface_returns_view_for_admin() -> None:
    """get_review_surface returns a projected view for an admin caller."""
    session = AsyncMock()
    book = _story("in_review", current=None)
    version = StorybookVersion(
        storybook_id=book.id,
        version=1,
        blob={"nodes": [{"id": "n1", "body": "Hi."}]},
        moderation_report={
            "findings": [
                {
                    "stage": 1,
                    "source": "llm_safety",
                    "category": "safety",
                    "node_id": "n1",
                    "verdict": "flag",
                    "score": None,
                    "message": "m",
                }
            ],
            "summary": {
                "count": 1,
                "hard_block": False,
                "soft_flag": True,
                "repaired": False,
                "reviewer_independent": True,
            },
        },
    )

    # _load_admin_story loads via execute() (locked); the version row loads
    # via session.get(StorybookVersion, ...), and load_admin_noise_floor loads
    # via session.get(ModerationSetting, ...); disambiguate by model class
    # since a single AsyncMock return_value cannot serve both call shapes.
    async def _fake_get(model: object, _key: object) -> object | None:
        return version if model is StorybookVersion else None

    session.execute = AsyncMock(return_value=_execute_result(book))
    session.get = AsyncMock(side_effect=_fake_get)
    ctx = _ctx("admin", session)
    view = await approval.get_review_surface(book.id, ctx, version=1)
    assert view.version == 1
    assert view.flagged_passages[0].prose == "Hi."


@pytest.mark.unit
async def test_review_surface_blocks_child() -> None:
    """get_review_surface blocks a child principal with AuthorizationError, and
    never reads a row (role is checked before any load).
    """
    session = AsyncMock()
    ctx = _ctx("child", session)
    with pytest.raises(AuthorizationError):
        await approval.get_review_surface("s1", ctx, version=1)
    session.execute.assert_not_awaited()
    session.get.assert_not_awaited()


@pytest.mark.unit
async def test_review_surface_missing_version_raises_404() -> None:
    """get_review_surface raises 404 when the requested version row is missing."""
    session = AsyncMock()
    book = _story("in_review", current=None)
    session.execute = AsyncMock(return_value=_execute_result(book))
    session.get = AsyncMock(return_value=None)  # version row missing
    ctx = _ctx("admin", session)
    with pytest.raises(ResourceNotFoundError):
        await approval.get_review_surface(book.id, ctx, version=9)


@pytest.mark.unit
async def test_review_surface_rejects_non_positive_version() -> None:
    """A non-positive version query param is rejected before the version-row
    lookup: only _load_admin_story's (locked) session.execute call happens.
    """
    session = AsyncMock()
    book = _story("in_review", current=None)
    session.execute = AsyncMock(return_value=_execute_result(book))
    ctx = _ctx("admin", session)

    with pytest.raises(ValidationError):
        await approval.get_review_surface(book.id, ctx, version=0)

    session.execute.assert_awaited_once()
    session.get.assert_not_awaited()


@pytest.mark.unit
async def test_review_surface_rejects_negative_version() -> None:
    """A negative version query param is rejected the same as zero."""
    session = AsyncMock()
    book = _story("in_review", current=None)
    session.execute = AsyncMock(return_value=_execute_result(book))
    ctx = _ctx("admin", session)

    with pytest.raises(ValidationError):
        await approval.get_review_surface(book.id, ctx, version=-1)


# ---------------------------------------------------------------------------
# SendBackRequest reason validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_send_back_rejects_whitespace_only_reason() -> None:
    """A whitespace-only reason is rejected server-side: strip_whitespace
    collapses "   " to "" which fails min_length=1. Closes the direct-API
    bypass of the frontend's non-blank guard. Deletion-sensitive: without
    strip_whitespace, "   " has length 3 and would pass min_length=1.
    """
    with pytest.raises(PydanticValidationError):
        SendBackRequest(reason="   ")


@pytest.mark.unit
def test_send_back_trims_surrounding_whitespace_in_reason() -> None:
    """A valid reason with surrounding whitespace is accepted and stored
    trimmed. Same-data positive control for the whitespace rejection above.
    """
    body = SendBackRequest(reason="  too scary for 6yo  ")
    assert body.reason == "too scary for 6yo"


# ---------------------------------------------------------------------------
# get_review_queue
# ---------------------------------------------------------------------------


class _Rows:
    """A minimal Result/ScalarResult double exposing .all()."""

    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        """Return the seeded rows."""
        return list(self._rows)


class _QueueSession:
    """Session double for get_review_queue that counts DB round trips.

    The handler makes two scalars() calls (storybooks, then version rows), one
    execute() call (the grouped max-version query), and one get() call (the
    admin noise-floor setting, loaded once for the whole listing). This double
    returns the seeded rows in that order and records call counts so a test
    can prove the handler is O(1) queries, not O(stories).
    """

    def __init__(
        self,
        *,
        storybooks: list[object],
        latest: list[object],
        versions: list[object],
    ) -> None:
        self._storybooks = storybooks
        self._latest = latest
        self._versions = versions
        self.scalars_calls = 0
        self.execute_calls = 0
        self.get_calls = 0

    async def scalars(self, _stmt: object) -> _Rows:
        """Return storybooks on the first call, version rows on the second."""
        self.scalars_calls += 1
        if self.scalars_calls == 1:
            return _Rows(self._storybooks)
        return _Rows(self._versions)

    async def execute(self, _stmt: object) -> _Rows:
        """Return the seeded (storybook_id, max_version) tuples."""
        self.execute_calls += 1
        return _Rows(self._latest)

    async def get(self, _entity: object, _key: object) -> None:
        """Return None (no moderation_setting row; code default floor applies)."""
        self.get_calls += 1


@pytest.mark.unit
async def test_review_queue_blocks_non_admin() -> None:
    """A non-admin caller raises AuthorizationError without any DB round trip."""
    session = _QueueSession(storybooks=[], latest=[], versions=[])
    ctx = RequestContext(principal=_principal("guardian"), session=session)  # type: ignore[arg-type]

    with pytest.raises(AuthorizationError):
        await approval.get_review_queue(ctx)

    assert session.scalars_calls == 0
    assert session.execute_calls == 0


@pytest.mark.unit
async def test_review_queue_empty_returns_no_items() -> None:
    """No in_review stories yields an empty queue after a single scalars call."""
    session = _QueueSession(storybooks=[], latest=[], versions=[])
    ctx = RequestContext(principal=_principal("admin"), session=session)  # type: ignore[arg-type]

    view = await approval.get_review_queue(ctx)

    assert isinstance(view, ReviewQueueView)
    assert view.items == []
    assert session.scalars_calls == 1  # short-circuits before the version query
    assert session.execute_calls == 0


@pytest.mark.unit
async def test_review_queue_is_bulk_not_n_plus_one() -> None:
    """Two in_review stories still cost exactly four DB round trips."""
    book_a = _story("in_review")
    book_a.id = "a"
    book_b = _story("in_review")
    book_b.id = "b"
    ver_a = StorybookVersion(
        storybook_id="a", version=1, blob={"title": "A", "nodes": []}
    )
    ver_b = StorybookVersion(
        storybook_id="b", version=3, blob={"title": "B", "nodes": []}
    )
    session = _QueueSession(
        storybooks=[book_a, book_b],
        latest=[("a", 1), ("b", 3)],
        versions=[ver_a, ver_b],
    )
    ctx = RequestContext(principal=_principal("admin"), session=session)  # type: ignore[arg-type]

    view = await approval.get_review_queue(ctx)

    assert {item.storybook_id for item in view.items} == {"a", "b"}
    assert {item.version for item in view.items} == {1, 3}
    assert session.scalars_calls == 2
    assert session.execute_calls == 1
    # The admin noise floor is loaded once for the listing, never per story.
    assert session.get_calls == 1
