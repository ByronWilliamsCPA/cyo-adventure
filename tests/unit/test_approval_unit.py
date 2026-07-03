"""Docker-independent unit tests for cyo_adventure.api.approval.

These call the handler functions and private helpers directly, with the
publishing service replaced by AsyncMock via monkeypatch. No DB, no ASGI
stack, no Docker.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError as PydanticValidationError

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

    session.get.assert_not_awaited()


@pytest.mark.unit
async def test_load_admin_story_missing_raises_404() -> None:
    """An admin caller with an unknown story id raises ResourceNotFoundError."""
    session = AsyncMock()
    session.get = AsyncMock(return_value=None)
    ctx = _ctx("admin", session)

    with pytest.raises(ResourceNotFoundError):
        await approval._load_admin_story(ctx, "missing-id")


@pytest.mark.unit
async def test_load_admin_story_returns_book() -> None:
    """An admin caller with a known story id returns the Storybook."""
    book = _story("draft")
    session = AsyncMock()
    session.get = AsyncMock(return_value=book)
    ctx = _ctx("admin", session)

    result = await approval._load_admin_story(ctx, "s1")

    assert result is book


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
    session.get = AsyncMock(return_value=book)
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
    session.get = AsyncMock(return_value=book)
    session.scalar = AsyncMock(return_value=1)
    ctx = _ctx("admin", session)

    async def _approve(*_args: object, **_kwargs: object) -> StorybookVersion:
        book.status = "published"
        return version_row

    approve_mock = AsyncMock(side_effect=_approve)
    monkeypatch.setattr("cyo_adventure.publishing.service.approve", approve_mock)

    view = await approval.approve_storybook("s1", ctx)

    assert view.approved_by == str(approver_id)
    assert view.published_at == published


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
    session.get = AsyncMock(return_value=book)
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
    session.get = AsyncMock(return_value=book)
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
    session.get.side_effect = [book, version]  # _load_admin_story, then version row
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
    session.get.assert_not_awaited()


@pytest.mark.unit
async def test_review_surface_missing_version_raises_404() -> None:
    """get_review_surface raises 404 when the requested version row is missing."""
    session = AsyncMock()
    book = _story("in_review", current=None)
    session.get.side_effect = [book, None]  # admin story ok, version row missing
    ctx = _ctx("admin", session)
    with pytest.raises(ResourceNotFoundError):
        await approval.get_review_surface(book.id, ctx, version=9)


@pytest.mark.unit
async def test_review_surface_rejects_non_positive_version() -> None:
    """A non-positive version query param is rejected before the version-row
    lookup: only _load_admin_story's session.get call happens.
    """
    session = AsyncMock()
    book = _story("in_review", current=None)
    session.get = AsyncMock(return_value=book)
    ctx = _ctx("admin", session)

    with pytest.raises(ValidationError):
        await approval.get_review_surface(book.id, ctx, version=0)

    session.get.assert_awaited_once()


@pytest.mark.unit
async def test_review_surface_rejects_negative_version() -> None:
    """A negative version query param is rejected the same as zero."""
    session = AsyncMock()
    book = _story("in_review", current=None)
    session.get = AsyncMock(return_value=book)
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

    The handler makes two scalars() calls (storybooks, then version rows) and
    one execute() call (the grouped max-version query). This double returns the
    seeded rows in that order and records call counts so a test can prove the
    handler is O(1) queries, not O(stories).
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
    """Two in_review stories still cost exactly three DB round trips."""
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
