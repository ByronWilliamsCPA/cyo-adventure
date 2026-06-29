"""Unit tests for the reading-state and completion API handlers (no DB, no ASGI).

Calls route functions directly with a fake session and constructed principals.
Covers: get_reading_state (happy path, missing state, bad UUID, profile IDOR,
storybook not found, family IDOR), put_reading_state (create first state,
revision increment, idempotent replay via event_id, revision mismatch 409,
version mismatch 409, nonzero first-revision 422, bad UUID), record_completion
(new, idempotent existing, bad ending_id, version not found, storybook not
found, family IDOR), and the _parse_uuid, _view, _conflict, _version_ending_ids
helper functions directly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import pytest

from cyo_adventure.api.deps import Principal, RequestContext
from cyo_adventure.api.reading import (
    _conflict,
    _parse_uuid,
    _version_ending_ids,
    _view,
    get_reading_state,
    put_reading_state,
    record_completion,
)
from cyo_adventure.api.schemas import CompletionBody, ReadingStateBody
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import (
    Completion,
    ReadingState,
    Storybook,
    StorybookVersion,
)

if TYPE_CHECKING:
    from sqlalchemy import Select

_FIXED_TS = datetime(2026, 1, 1, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeSession:
    """Minimal async session double for reading/completion API handlers.

    ``get_map`` maps (model_type, key) -> row-or-None.
    ``scalar_result`` is returned from the single scalar() call in put_reading_state.
    """

    def __init__(
        self,
        *,
        get_map: dict[tuple[type[object], object], object] | None = None,
        scalar_result: object | None = None,
    ) -> None:
        self._get_map: dict[tuple[type[object], object], object] = get_map or {}
        self._scalar_result = scalar_result
        self.added: list[object] = []
        self.flush_count = 0
        self.refresh_calls: list[tuple[object, list[str] | None]] = []
        self.get_calls: list[tuple[type[object], object]] = []
        self.scalar_calls: list[object] = []

    async def get(self, model: type[object], key: object) -> object | None:
        """Look up by (model, key)."""
        self.get_calls.append((model, key))
        return self._get_map.get((model, key))

    def add(self, obj: object) -> None:
        """Record added ORM instances."""
        self.added.append(obj)

    async def flush(self) -> None:
        """Count flushes (no-op)."""
        self.flush_count += 1

    async def refresh(self, obj: object, attrs: list[str] | None = None) -> None:
        """Populate server-default columns the handler reads back after flush."""
        self.refresh_calls.append((obj, attrs))
        # Populate found_at for Completion rows
        if isinstance(obj, Completion):
            obj.found_at = _FIXED_TS

    async def scalar(self, stmt: object) -> object | None:
        """Capture the statement, then return the seeded SELECT...FOR UPDATE result."""
        self.scalar_calls.append(stmt)
        return self._scalar_result


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _child_principal(family_id: uuid.UUID, profile_id: uuid.UUID) -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="child",
        family_id=family_id,
        profile_ids=frozenset({profile_id}),
    )


def _guardian_principal(family_id: uuid.UUID) -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role="guardian",
        family_id=family_id,
        profile_ids=frozenset(),
    )


def _ctx(principal: Principal, session: _FakeSession) -> RequestContext:
    return RequestContext(principal=principal, session=session)


def _published_book(storybook_id: str, family_id: uuid.UUID) -> Storybook:
    book = Storybook(id=storybook_id, family_id=family_id)
    book.status = "published"
    book.current_published_version = 1
    return book


def _state_row(
    profile_id: uuid.UUID,
    storybook_id: str,
    *,
    version: int = 1,
    current_node: str = "start",
    state_revision: int = 3,
    event_id: str | None = None,
) -> ReadingState:
    row = ReadingState(
        child_profile_id=profile_id,
        storybook_id=storybook_id,
        version=version,
        current_node=current_node,
    )
    row.state_revision = state_revision
    row.var_state = {}
    row.path = []
    row.visit_set = []
    row.save_slots = {}
    row.last_event_id = event_id
    row.updated_by_device_id = None
    row.last_synced_at = None
    return row


def _body(
    *,
    version: int = 1,
    current_node: str = "node-a",
    state_revision: int = 3,
    event_id: str | None = None,
    device_id: str | None = None,
) -> ReadingStateBody:
    return ReadingStateBody(
        version=version,
        current_node=current_node,
        state_revision=state_revision,
        event_id=event_id,
        device_id=device_id,
    )


def _completion_blob(*ending_ids: str) -> dict[str, object]:
    """Build a minimal Storybook blob with the given ending ids."""
    nodes: list[object] = [
        {
            "id": eid,
            "is_ending": True,
            "ending": {"id": eid},
        }
        for eid in ending_ids
    ]
    return {"nodes": nodes}


# ---------------------------------------------------------------------------
# _parse_uuid
# ---------------------------------------------------------------------------


class TestParseUuid:
    @pytest.mark.unit
    def test_valid_uuid_is_parsed(self) -> None:
        raw = str(uuid.uuid4())
        result = _parse_uuid(raw, "profile_id")
        assert str(result) == raw

    @pytest.mark.unit
    def test_invalid_string_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            _parse_uuid("bad", "profile_id")
        assert "profile_id" in str(exc_info.value)


# ---------------------------------------------------------------------------
# _view
# ---------------------------------------------------------------------------


class TestView:
    @pytest.mark.unit
    def test_view_maps_all_fields(self) -> None:
        """_view() maps every ReadingState attribute to ReadingStateView."""
        profile_id = uuid.uuid4()
        row = _state_row(
            profile_id, "s", version=2, current_node="ch3", state_revision=7
        )
        v = _view(row)
        assert v.child_profile_id == str(profile_id)
        assert v.storybook_id == "s"
        assert v.version == 2
        assert v.current_node == "ch3"
        assert v.state_revision == 7


# ---------------------------------------------------------------------------
# _conflict
# ---------------------------------------------------------------------------


class TestConflict:
    @pytest.mark.unit
    def test_conflict_response_has_409_status(self) -> None:
        """_conflict() produces a JSONResponse with status 409."""
        profile_id = uuid.uuid4()
        row = _state_row(profile_id, "s")
        response = _conflict(row, "revision mismatch")
        assert response.status_code == 409

    @pytest.mark.unit
    def test_conflict_response_body_contains_detail(self) -> None:
        """The 409 response body includes the provided detail string."""
        import json

        profile_id = uuid.uuid4()
        row = _state_row(profile_id, "s")
        response = _conflict(row, "version mismatch")
        body = json.loads(response.body)
        assert body["detail"] == "version mismatch"
        assert "current_row" in body


# ---------------------------------------------------------------------------
# _version_ending_ids
# ---------------------------------------------------------------------------


class TestVersionEndingIds:
    @pytest.mark.unit
    def test_returns_all_ending_ids(self) -> None:
        blob = _completion_blob("end-a", "end-b")
        assert _version_ending_ids(blob) == {"end-a", "end-b"}

    @pytest.mark.unit
    def test_empty_nodes_returns_empty_set(self) -> None:
        assert _version_ending_ids({"nodes": []}) == set()

    @pytest.mark.unit
    def test_non_list_nodes_returns_empty_set(self) -> None:
        assert _version_ending_ids({"nodes": "bad"}) == set()

    @pytest.mark.unit
    def test_non_ending_nodes_excluded(self) -> None:
        """Nodes without is_ending=True are not included."""
        blob: dict[str, object] = {
            "nodes": [
                {"id": "n1", "is_ending": False},
                {"id": "n2"},
                {"id": "n3", "is_ending": True, "ending": {"id": "end-1"}},
            ]
        }
        assert _version_ending_ids(blob) == {"end-1"}

    @pytest.mark.unit
    def test_ending_with_non_string_id_excluded(self) -> None:
        """An ending node whose ending.id is not a string is excluded."""
        blob: dict[str, object] = {
            "nodes": [
                {"is_ending": True, "ending": {"id": 42}},
            ]
        }
        assert _version_ending_ids(blob) == set()

    @pytest.mark.unit
    def test_ending_with_no_ending_dict_excluded(self) -> None:
        """An is_ending node without an 'ending' dict is excluded."""
        blob: dict[str, object] = {
            "nodes": [
                {"is_ending": True, "ending": "not-a-dict"},
            ]
        }
        assert _version_ending_ids(blob) == set()

    @pytest.mark.unit
    def test_non_dict_node_skipped(self) -> None:
        """Non-dict items in the nodes list are silently skipped."""
        blob: dict[str, object] = {"nodes": ["not-a-node", None, 42]}
        assert _version_ending_ids(blob) == set()

    @pytest.mark.unit
    def test_missing_nodes_key_returns_empty_set(self) -> None:
        assert _version_ending_ids({}) == set()


# ---------------------------------------------------------------------------
# get_reading_state
# ---------------------------------------------------------------------------


class TestGetReadingState:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_happy_path_returns_reading_state_view(self) -> None:
        """A valid profile/story pair with an existing state row returns the view."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        row = _state_row(profile_id, "story-1")
        session = _FakeSession(
            get_map={
                (Storybook, "story-1"): book,
                (ReadingState, (profile_id, "story-1")): row,
            }
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)

        result = await get_reading_state(str(profile_id), "story-1", ctx)

        assert result.storybook_id == "story-1"
        assert result.child_profile_id == str(profile_id)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_reading_state_row_raises_not_found(self) -> None:
        """A profile with no saved state for the story raises ResourceNotFoundError."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        session = _FakeSession(
            get_map={
                (Storybook, "story-1"): book,
                # No ReadingState entry
            }
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)

        with pytest.raises(ResourceNotFoundError):
            await get_reading_state(str(profile_id), "story-1", ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_uuid_raises_validation_error(self) -> None:
        """A non-UUID profile_id string raises ValidationError."""
        family_id = uuid.uuid4()
        session = _FakeSession()
        ctx = _ctx(_guardian_principal(family_id), session)

        with pytest.raises(ValidationError):
            await get_reading_state("bad-uuid", "story-1", ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_child_profile_idor_raises_authorization(self) -> None:
        """A child trying to read another profile's state gets 403."""
        family_id = uuid.uuid4()
        my_profile = uuid.uuid4()
        other_profile = uuid.uuid4()
        session = _FakeSession()
        ctx = _ctx(_child_principal(family_id, my_profile), session)

        with pytest.raises(AuthorizationError):
            await get_reading_state(str(other_profile), "story-1", ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_storybook_not_found_raises_not_found(self) -> None:
        """A storybook that does not exist raises ResourceNotFoundError."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        session = _FakeSession(get_map={})
        ctx = _ctx(_child_principal(family_id, profile_id), session)

        with pytest.raises(ResourceNotFoundError):
            await get_reading_state(str(profile_id), "no-book", ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cross_family_storybook_raises_authorization(self) -> None:
        """A storybook owned by another family raises AuthorizationError."""
        my_family = uuid.uuid4()
        other_family = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", other_family)
        session = _FakeSession(get_map={(Storybook, "story-1"): book})
        ctx = _ctx(_child_principal(my_family, profile_id), session)

        with pytest.raises(AuthorizationError):
            await get_reading_state(str(profile_id), "story-1", ctx)


# ---------------------------------------------------------------------------
# put_reading_state
# ---------------------------------------------------------------------------


class TestPutReadingState:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_locked_read_is_profile_story_scoped_and_for_update(self) -> None:
        """The read-modify-write read must be row-scoped and locked.

        Inspects the SQL captured by the fake session so a regression that drops
        the (child_profile_id, storybook_id) predicate (cross-profile write) or
        the SELECT ... FOR UPDATE lock (concurrent-writer race on the revision
        check) fails here rather than passing on the seeded scalar result alone.
        """
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        session = _FakeSession(
            get_map={(Storybook, "story-1"): book},
            scalar_result=None,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)

        await put_reading_state(
            str(profile_id), "story-1", _body(state_revision=0), ctx
        )

        assert len(session.scalar_calls) == 1
        stmt = cast("Select[Any]", session.scalar_calls[0])
        # The row scope lives in the WHERE clause; the SELECT column list names
        # every column, so checking the full statement would not catch a dropped
        # predicate. FOR UPDATE is a statement-level modifier, checked on str().
        where = str(stmt.whereclause)
        assert "child_profile_id" in where  # cross-profile IDOR scope
        assert "storybook_id" in where
        assert "FOR UPDATE" in str(stmt)  # serializes concurrent writers

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_first_state_returns_view(self) -> None:
        """When no existing state row exists a new row is inserted and returned."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        session = _FakeSession(
            get_map={(Storybook, "story-1"): book},
            scalar_result=None,  # No existing row
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = _body(state_revision=0, current_node="start")

        result = await put_reading_state(str(profile_id), "story-1", body, ctx)

        from cyo_adventure.api.schemas import ReadingStateView

        assert isinstance(result, ReadingStateView)
        assert result.current_node == "start"
        assert result.state_revision == 1  # server bumped from 0
        assert len(session.added) == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_nonzero_revision_raises_validation(self) -> None:
        """A first save that doesn't start at revision 0 raises ValidationError."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        session = _FakeSession(
            get_map={(Storybook, "story-1"): book},
            scalar_result=None,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = _body(state_revision=5)  # Should be 0 for first save

        with pytest.raises(ValidationError):
            await put_reading_state(str(profile_id), "story-1", body, ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_matching_revision_applies_body(self) -> None:
        """A save with matching version and state_revision applies and bumps revision."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        existing = _state_row(profile_id, "story-1", state_revision=3)
        session = _FakeSession(
            get_map={(Storybook, "story-1"): book},
            scalar_result=existing,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = _body(version=1, state_revision=3, current_node="chapter-2")

        result = await put_reading_state(str(profile_id), "story-1", body, ctx)

        from cyo_adventure.api.schemas import ReadingStateView

        assert isinstance(result, ReadingStateView)
        assert result.current_node == "chapter-2"
        assert result.state_revision == 4  # server bumped

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_revision_mismatch_returns_409(self) -> None:
        """A save with a stale state_revision returns a 409 JSONResponse."""
        from fastapi.responses import JSONResponse

        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        existing = _state_row(profile_id, "story-1", state_revision=5)
        session = _FakeSession(
            get_map={(Storybook, "story-1"): book},
            scalar_result=existing,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = _body(version=1, state_revision=3)  # stale: server is at 5

        result = await put_reading_state(str(profile_id), "story-1", body, ctx)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 409

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_version_mismatch_returns_409(self) -> None:
        """A save targeting a different version than the stored row returns 409."""
        from fastapi.responses import JSONResponse

        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        existing = _state_row(profile_id, "story-1", version=1, state_revision=3)
        session = _FakeSession(
            get_map={(Storybook, "story-1"): book},
            scalar_result=existing,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = _body(version=2, state_revision=3)  # version 2 but stored is 1

        result = await put_reading_state(str(profile_id), "story-1", body, ctx)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 409

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_idempotent_replay_returns_current_row(self) -> None:
        """A save with an already-applied event_id returns the stored row unchanged."""
        from cyo_adventure.api.schemas import ReadingStateView

        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        existing = _state_row(
            profile_id, "story-1", state_revision=3, event_id="evt-xyz"
        )
        session = _FakeSession(
            get_map={(Storybook, "story-1"): book},
            scalar_result=existing,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = _body(version=1, state_revision=3, event_id="evt-xyz")

        result = await put_reading_state(str(profile_id), "story-1", body, ctx)

        # Should return the unchanged row, not 409
        assert isinstance(result, ReadingStateView)
        assert result.state_revision == 3  # not bumped

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_uuid_raises_validation(self) -> None:
        """A non-UUID profile_id raises ValidationError."""
        family_id = uuid.uuid4()
        session = _FakeSession()
        ctx = _ctx(_guardian_principal(family_id), session)

        with pytest.raises(ValidationError):
            await put_reading_state("not-uuid", "story-1", _body(), ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_profile_idor_raises_authorization(self) -> None:
        """A child trying to write another profile's state raises AuthorizationError."""
        family_id = uuid.uuid4()
        my_profile = uuid.uuid4()
        other_profile = uuid.uuid4()
        session = _FakeSession()
        ctx = _ctx(_child_principal(family_id, my_profile), session)

        with pytest.raises(AuthorizationError):
            await put_reading_state(str(other_profile), "story-1", _body(), ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_device_id_stored_on_row(self) -> None:
        """A device_id in the body is persisted to the updated row."""
        from cyo_adventure.api.schemas import ReadingStateView

        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        existing = _state_row(profile_id, "story-1", state_revision=0)
        session = _FakeSession(
            get_map={(Storybook, "story-1"): book},
            scalar_result=existing,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = _body(version=1, state_revision=0, device_id="my-device-abc")

        result = await put_reading_state(str(profile_id), "story-1", body, ctx)

        assert isinstance(result, ReadingStateView)
        assert result.updated_by_device_id == "my-device-abc"


# ---------------------------------------------------------------------------
# record_completion
# ---------------------------------------------------------------------------


class TestRecordCompletion:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_new_completion_inserted_and_returned(self) -> None:
        """A first completion for an ending is inserted and returned."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        blob = _completion_blob("end-happy")
        sv = StorybookVersion(storybook_id="story-1", version=1, blob=blob)
        key = (profile_id, "story-1", 1, "end-happy")
        session = _FakeSession(
            get_map={
                (Storybook, "story-1"): book,
                (StorybookVersion, ("story-1", 1)): sv,
                (Completion, key): None,
            }
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = CompletionBody(
            profile_id=str(profile_id),
            storybook_id="story-1",
            version=1,
            ending_id="end-happy",
        )

        result = await record_completion(body, ctx)

        assert result.ending_id == "end-happy"
        assert result.found_at == _FIXED_TS
        assert len(session.added) == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_existing_completion_returned_without_insert(self) -> None:
        """A duplicate completion request returns the existing row idempotently."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        blob = _completion_blob("end-sad")
        sv = StorybookVersion(storybook_id="story-1", version=1, blob=blob)
        existing = Completion(
            child_profile_id=profile_id,
            storybook_id="story-1",
            version=1,
            ending_id="end-sad",
        )
        existing.found_at = _FIXED_TS
        key = (profile_id, "story-1", 1, "end-sad")
        session = _FakeSession(
            get_map={
                (Storybook, "story-1"): book,
                (StorybookVersion, ("story-1", 1)): sv,
                (Completion, key): existing,
            }
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = CompletionBody(
            profile_id=str(profile_id),
            storybook_id="story-1",
            version=1,
            ending_id="end-sad",
        )

        result = await record_completion(body, ctx)

        assert result.found_at == _FIXED_TS
        assert session.added == []  # no new row inserted

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_ending_id_raises_validation(self) -> None:
        """An ending_id not in the version blob raises ValidationError."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        blob = _completion_blob("real-end")
        sv = StorybookVersion(storybook_id="story-1", version=1, blob=blob)
        session = _FakeSession(
            get_map={
                (Storybook, "story-1"): book,
                (StorybookVersion, ("story-1", 1)): sv,
            }
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = CompletionBody(
            profile_id=str(profile_id),
            storybook_id="story-1",
            version=1,
            ending_id="fake-end",
        )

        with pytest.raises(ValidationError):
            await record_completion(body, ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_version_not_found_raises_not_found(self) -> None:
        """A missing StorybookVersion raises ResourceNotFoundError."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        session = _FakeSession(
            get_map={
                (Storybook, "story-1"): book,
                # No StorybookVersion entry
            }
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = CompletionBody(
            profile_id=str(profile_id),
            storybook_id="story-1",
            version=99,
            ending_id="end-x",
        )

        with pytest.raises(ResourceNotFoundError):
            await record_completion(body, ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_storybook_not_found_raises_not_found(self) -> None:
        """A missing Storybook raises ResourceNotFoundError before version lookup."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        session = _FakeSession(get_map={})
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = CompletionBody(
            profile_id=str(profile_id),
            storybook_id="no-book",
            version=1,
            ending_id="end-x",
        )

        with pytest.raises(ResourceNotFoundError):
            await record_completion(body, ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cross_family_storybook_raises_authorization(self) -> None:
        """A story owned by another family raises AuthorizationError."""
        my_family = uuid.uuid4()
        other_family = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", other_family)
        session = _FakeSession(get_map={(Storybook, "story-1"): book})
        ctx = _ctx(_child_principal(my_family, profile_id), session)
        body = CompletionBody(
            profile_id=str(profile_id),
            storybook_id="story-1",
            version=1,
            ending_id="end-x",
        )

        with pytest.raises(AuthorizationError):
            await record_completion(body, ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_profile_uuid_raises_validation(self) -> None:
        """A non-UUID profile_id in the body raises ValidationError."""
        family_id = uuid.uuid4()
        session = _FakeSession()
        ctx = _ctx(_guardian_principal(family_id), session)
        body = CompletionBody(
            profile_id="not-a-uuid",
            storybook_id="story-1",
            version=1,
            ending_id="end-x",
        )

        with pytest.raises(ValidationError):
            await record_completion(body, ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_child_profile_idor_raises_authorization(self) -> None:
        """A child requesting a completion for another profile gets 403."""
        family_id = uuid.uuid4()
        my_profile = uuid.uuid4()
        other_profile = uuid.uuid4()
        session = _FakeSession()
        ctx = _ctx(_child_principal(family_id, my_profile), session)
        body = CompletionBody(
            profile_id=str(other_profile),
            storybook_id="story-1",
            version=1,
            ending_id="end-x",
        )

        with pytest.raises(AuthorizationError):
            await record_completion(body, ctx)
