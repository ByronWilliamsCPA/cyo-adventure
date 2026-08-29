"""Unit tests for the reading-state and completion API handlers (no DB, no ASGI).

Calls route functions directly with a fake session and constructed principals.
Covers: get_reading_state (happy path, absent state returns null, bad UUID,
profile IDOR, storybook not found, family IDOR), put_reading_state (create
first state,
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
from unittest.mock import patch

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.dialects import postgresql

from cyo_adventure.api import reading as reading_module
from cyo_adventure.api.deps import Principal, RequestContext
from cyo_adventure.api.reading import (
    _completion_recorded_view,
    _conflict,
    _parse_uuid,
    _version_ending_ids,
    _view,
    get_reading_state,
    get_series_next,
    put_reading_state,
    record_completion,
)
from cyo_adventure.api.schemas import (
    CompletionBody,
    CompletionRecordedView,
    ReadingStateBody,
)
from cyo_adventure.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from cyo_adventure.db.models import (
    Completion,
    ReadingState,
    Storybook,
    StorybookAssignment,
    StorybookVersion,
)
from cyo_adventure.storybook.sentinels import wrap

if TYPE_CHECKING:
    from sqlalchemy import Select

_FIXED_TS = datetime(2026, 1, 1, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


_ASSIGNED = "assigned"


def _is_assignment_query(stmt: object) -> bool:
    """Return whether a SELECT reads ``StorybookAssignment`` (the M1 read gate).

    ``_require_assignment`` adds a second ``scalar()`` call ahead of
    ``put_reading_state``'s SELECT ... FOR UPDATE, so the fake dispatches on
    the selected entity rather than returning one seeded result to both.
    """
    descriptions = getattr(stmt, "column_descriptions", None)
    if not descriptions:
        return False
    first = descriptions[0]
    return isinstance(first, dict) and first.get("entity") is StorybookAssignment


class _FakeSession:
    """Minimal async session double for reading/completion API handlers.

    ``get_map`` maps (model_type, key) -> row-or-None.
    ``scalar_result`` is returned from the SELECT ... FOR UPDATE scalar() call
    in put_reading_state. ``assignment`` is returned from the M1 assignment
    lookup and defaults to a present row, so only the tests that specifically
    exercise the unassigned-story 404 have to say so.
    """

    def __init__(
        self,
        *,
        get_map: dict[tuple[type[object], object], object] | None = None,
        scalar_result: object | None = None,
        assignment: object | None = _ASSIGNED,
    ) -> None:
        self._get_map: dict[tuple[type[object], object], object] = get_map or {}
        self._scalar_result = scalar_result
        self._assignment = assignment
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
        """Capture the statement, then return the seeded result for its entity."""
        self.scalar_calls.append(stmt)
        if _is_assignment_query(stmt):
            return self._assignment
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


def _approved_version(
    storybook_id: str, version: int, blob: dict[str, Any]
) -> StorybookVersion:
    """Build an APPROVED version row.

    M1 gates a first reading-state save and every completion on the book's
    current, published, APPROVED version, so a fixture that leaves
    ``approved_by`` unset now 404s on those paths (which is the point of the
    gate, not a defect in it).
    """
    return StorybookVersion(
        storybook_id=storybook_id,
        version=version,
        blob=blob,
        approved_by=uuid.uuid4(),
    )


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


def _completion_blob(
    *ending_ids: str, ending_count: int | None = None
) -> dict[str, object]:
    """Build a minimal Storybook blob with the given ending ids.

    Args:
        *ending_ids: Ending node ids to declare.
        ending_count: When given, adds ``metadata.ending_count`` so callers
            exercising the W0.3 ``total`` field can control it independently
            of the actual node count (mirrors a real blob, where the two are
            enforced equal at validation time but the read path here trusts
            the metadata field rather than recounting nodes).
    """
    nodes: list[object] = [
        {
            "id": eid,
            "is_ending": True,
            "ending": {"id": eid},
        }
        for eid in ending_ids
    ]
    blob: dict[str, object] = {"nodes": nodes}
    if ending_count is not None:
        blob["metadata"] = {"ending_count": ending_count}
    return blob


def _valid_blob() -> dict[str, object]:
    """A schema-valid linear story whose node ids match the existing test bodies.

    Nodes start -> node-a -> chapter-2 -> ch3(ending); no variables (bodies carry
    empty var_state). Structural floor passes for any current_node in this set.
    """
    return {
        "schema_version": "2.0",
        "id": "story-1",
        "version": 1,
        "title": "Fixture",
        "metadata": {
            "age_band": "10-13",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 4.0,
                "tolerance": 1.0,
            },
            "tier": 2,
            "themes": [],
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": "branch_and_bottleneck",
            "content_flags": {
                "violence": "none",
                "scariness": "none",
                "peril": "none",
            },
        },
        "variables": [],
        "start_node": "start",
        "nodes": [
            {
                "id": "start",
                "body": "S.",
                "choices": [{"id": "c1", "label": "x", "target": "node-a"}],
            },
            {
                "id": "node-a",
                "body": "A.",
                "choices": [{"id": "c2", "label": "x", "target": "chapter-2"}],
            },
            {
                "id": "chapter-2",
                "body": "C.",
                "choices": [{"id": "c3", "label": "x", "target": "ch3"}],
            },
            {
                "id": "ch3",
                "body": "E.",
                "is_ending": True,
                "ending": {
                    "id": "e_end",
                    "valence": "positive",
                    "kind": "success",
                    "title": "End",
                },
                "choices": [],
            },
        ],
    }


def _story_blob() -> dict[str, object]:
    """A two-node story: n_start -> (choice c_go) -> n_end, int var courage 0..5."""
    return {
        "schema_version": "2.0",
        "id": "s_syn",
        "version": 1,
        "title": "Synthetic",
        "metadata": {
            "age_band": "10-13",
            "reading_level": {
                "scheme": "flesch_kincaid",
                "target": 4.0,
                "tolerance": 1.0,
            },
            "tier": 2,
            "themes": [],
            "estimated_minutes": 5,
            "ending_count": 1,
            "topology": "branch_and_bottleneck",
            "content_flags": {
                "violence": "none",
                "scariness": "none",
                "peril": "none",
            },
        },
        "variables": [
            {"name": "courage", "type": "int", "initial": 0, "min": 0, "max": 5}
        ],
        "start_node": "n_start",
        "nodes": [
            {
                "id": "n_start",
                "body": "Start here.",
                "on_enter": [],
                "choices": [
                    {
                        "id": "c_go",
                        "label": "Go",
                        "target": "n_end",
                        "effects": [{"op": "inc", "var": "courage", "value": 2}],
                    }
                ],
            },
            {
                "id": "n_end",
                "body": "Done.",
                "is_ending": True,
                "ending": {
                    "id": "e_end",
                    "valence": "positive",
                    "kind": "success",
                    "title": "End",
                },
                "choices": [],
            },
        ],
    }


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
        with pytest.raises(
            ValidationError, match=r"profile_id must be a UUID"
        ) as exc_info:
            _parse_uuid("bad", "profile_id")
        assert "profile_id" in str(exc_info.value)


# ---------------------------------------------------------------------------
# _view
# ---------------------------------------------------------------------------


class TestView:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_view_maps_all_fields(self) -> None:
        """_view() maps every ReadingState attribute to ReadingStateView."""
        profile_id = uuid.uuid4()
        row = _state_row(
            profile_id, "s", version=2, current_node="ch3", state_revision=7
        )
        session = _FakeSession()
        v = await _view(session, row)
        assert v.child_profile_id == str(profile_id)
        assert v.storybook_id == "s"
        assert v.version == 2
        assert v.current_node == "ch3"
        assert v.state_revision == 7
        assert v.character_id is None
        assert v.character_name is None
        assert v.seed_var_state is None


# ---------------------------------------------------------------------------
# _conflict
# ---------------------------------------------------------------------------


class TestConflict:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_conflict_response_has_409_status(self) -> None:
        """_conflict() produces a JSONResponse with status 409."""
        profile_id = uuid.uuid4()
        row = _state_row(profile_id, "s")
        session = _FakeSession()
        response = await _conflict(session, row, "revision mismatch")
        assert response.status_code == 409

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_conflict_response_body_contains_detail(self) -> None:
        """The 409 response body includes the provided detail string."""
        import json

        profile_id = uuid.uuid4()
        row = _state_row(profile_id, "s")
        session = _FakeSession()
        response = await _conflict(session, row, "version mismatch")
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

        assert result.state is not None
        assert result.state.storybook_id == "story-1"
        assert result.state.child_profile_id == str(profile_id)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_reading_state_row_returns_null_state(self) -> None:
        """A profile with no saved state for the story gets a 200 with state: null.

        A first-time reader is a normal condition, not an error (see
        ReadingStateResultView's docstring); a 404 here would surface as an
        uncatchable browser console error before application code can
        handle it.
        """
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
        profile_id_str = str(profile_id)

        result = await get_reading_state(profile_id_str, "story-1", ctx)

        assert result.state is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_uuid_raises_validation_error(self) -> None:
        """A non-UUID profile_id string raises ValidationError."""
        family_id = uuid.uuid4()
        session = _FakeSession()
        ctx = _ctx(_guardian_principal(family_id), session)

        with pytest.raises(ValidationError, match=r"profile_id must be a UUID"):
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
        other_profile_str = str(other_profile)

        with pytest.raises(
            AuthorizationError, match=r"profile is not accessible to this principal"
        ):
            await get_reading_state(other_profile_str, "story-1", ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_storybook_not_found_raises_not_found(self) -> None:
        """A storybook that does not exist raises ResourceNotFoundError."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        session = _FakeSession(get_map={})
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        profile_id_str = str(profile_id)

        with pytest.raises(
            ResourceNotFoundError, match=r"storybook 'no-book' not found"
        ):
            await get_reading_state(profile_id_str, "no-book", ctx)

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
        profile_id_str = str(profile_id)

        with pytest.raises(
            AuthorizationError, match=r"resource belongs to another family"
        ):
            await get_reading_state(profile_id_str, "story-1", ctx)


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
        version = _approved_version("story-1", 1, _valid_blob())
        session = _FakeSession(
            get_map={
                (Storybook, "story-1"): book,
                (StorybookVersion, ("story-1", 1)): version,
            },
            scalar_result=None,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)

        await put_reading_state(
            str(profile_id), "story-1", _body(state_revision=0), ctx
        )

        # Three scalar() calls now: the M1 assignment lookup, the locked
        # read-modify-write read this test is about, then the create path's
        # active-character binding lookup (Task 6; the fake session's seeded
        # scalar_result of None means "no character" for that third call).
        assert len(session.scalar_calls) == 3
        stmt = cast("Select[Any]", session.scalar_calls[1])
        # The row scope lives in the WHERE clause; the SELECT column list names
        # every column, so checking the full statement would not catch a dropped
        # predicate.
        where = str(stmt.whereclause)
        assert "child_profile_id" in where  # cross-profile IDOR scope
        assert "storybook_id" in where

        # Pin the predicate VALUES, not just the column names: a constant or
        # wrong-attribute binding would still render the column here.
        params = set(stmt.compile().params.values())
        assert profile_id in params  # bound to the authorized profile
        assert "story-1" in params  # bound to the path storybook

        # The lock must be a plain row lock that serializes writers. Render with
        # the Postgres dialect (the deployment target): the generic compiler
        # omits skip_locked/nowait clauses, so a weakening would be invisible
        # under str(stmt). skip_locked lets a concurrent writer slip past; nowait
        # changes the failure mode. Both still contain "FOR UPDATE".
        rendered = str(stmt.compile(dialect=postgresql.dialect()))
        assert "FOR UPDATE" in rendered  # serializes concurrent writers
        assert "SKIP LOCKED" not in rendered
        assert "NOWAIT" not in rendered

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_first_state_returns_view(self) -> None:
        """When no existing state row exists a new row is inserted and returned."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        version = _approved_version("story-1", 1, _valid_blob())
        session = _FakeSession(
            get_map={
                (Storybook, "story-1"): book,
                (StorybookVersion, ("story-1", 1)): version,
            },
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
        version = _approved_version("story-1", 1, _valid_blob())
        session = _FakeSession(
            get_map={
                (Storybook, "story-1"): book,
                (StorybookVersion, ("story-1", 1)): version,
            },
            scalar_result=None,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = _body(state_revision=5)  # Should be 0 for first save
        profile_id_str = str(profile_id)

        with pytest.raises(
            ValidationError,
            match=r"first reading-state save must start at state_revision 0",
        ):
            await put_reading_state(profile_id_str, "story-1", body, ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_matching_revision_applies_body(self) -> None:
        """A save with matching version and state_revision applies and bumps revision."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        version = _approved_version("story-1", 1, _valid_blob())
        existing = _state_row(profile_id, "story-1", state_revision=3)
        session = _FakeSession(
            get_map={
                (Storybook, "story-1"): book,
                (StorybookVersion, ("story-1", 1)): version,
            },
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
        version = _approved_version("story-1", 1, _valid_blob())
        existing = _state_row(profile_id, "story-1", state_revision=5)
        session = _FakeSession(
            get_map={
                (Storybook, "story-1"): book,
                (StorybookVersion, ("story-1", 1)): version,
            },
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
        # body targets version 2, so validation loads the version-2 pin.
        version = _approved_version("story-1", 2, _valid_blob())
        existing = _state_row(profile_id, "story-1", version=1, state_revision=3)
        session = _FakeSession(
            get_map={
                (Storybook, "story-1"): book,
                (StorybookVersion, ("story-1", 2)): version,
            },
            scalar_result=existing,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = _body(version=2, state_revision=3)  # version 2 but stored is 1

        result = await put_reading_state(str(profile_id), "story-1", body, ctx)

        assert isinstance(result, JSONResponse)
        assert result.status_code == 409

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_version_mismatch_with_absent_version_returns_409(self) -> None:
        """A version mismatch still 409s even when the mismatched version has no

        persisted ``StorybookVersion`` row: the concurrency conflict must win over
        the version-existence check, since a stale-session client is out of date,
        not malformed (see reading.py's version-mismatch-before-validation note).
        """
        from fastapi.responses import JSONResponse

        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        # stored row is on version 1; body targets version 2, which has NO
        # StorybookVersion row seeded in get_map.
        existing = _state_row(profile_id, "story-1", version=1, state_revision=3)
        session = _FakeSession(
            get_map={
                (Storybook, "story-1"): book,
                # (StorybookVersion, ("story-1", 2)) intentionally absent.
            },
            scalar_result=existing,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = _body(version=2, state_revision=3)  # version 2 absent, stored is 1

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
        version = _approved_version("story-1", 1, _valid_blob())
        existing = _state_row(
            profile_id, "story-1", state_revision=3, event_id="evt-xyz"
        )
        session = _FakeSession(
            get_map={
                (Storybook, "story-1"): book,
                (StorybookVersion, ("story-1", 1)): version,
            },
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

        body = _body()
        with pytest.raises(ValidationError, match=r"profile_id must be a UUID"):
            await put_reading_state("not-uuid", "story-1", body, ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_profile_idor_raises_authorization(self) -> None:
        """A child trying to write another profile's state raises AuthorizationError."""
        family_id = uuid.uuid4()
        my_profile = uuid.uuid4()
        other_profile = uuid.uuid4()
        session = _FakeSession()
        ctx = _ctx(_child_principal(family_id, my_profile), session)

        other_profile_str = str(other_profile)
        body = _body()
        with pytest.raises(
            AuthorizationError, match=r"profile is not accessible to this principal"
        ):
            await put_reading_state(other_profile_str, "story-1", body, ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_device_id_stored_on_row(self) -> None:
        """A device_id in the body is persisted to the updated row."""
        from cyo_adventure.api.schemas import ReadingStateView

        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        version = _approved_version("story-1", 1, _valid_blob())
        existing = _state_row(profile_id, "story-1", state_revision=0)
        session = _FakeSession(
            get_map={
                (Storybook, "story-1"): book,
                (StorybookVersion, ("story-1", 1)): version,
            },
            scalar_result=existing,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = _body(version=1, state_revision=0, device_id="my-device-abc")

        result = await put_reading_state(str(profile_id), "story-1", body, ctx)

        assert isinstance(result, ReadingStateView)
        assert result.updated_by_device_id == "my-device-abc"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_put_rejects_forged_current_node(self) -> None:
        """A current_node not in the pinned version's node set raises ValidationError."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("s_syn", family_id)
        version = _approved_version("s_syn", 1, _story_blob())
        session = _FakeSession(
            get_map={
                (Storybook, "s_syn"): book,
                (StorybookVersion, ("s_syn", 1)): version,
            },
            scalar_result=None,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = ReadingStateBody(
            version=1,
            current_node="n_ghost",
            var_state={"courage": 0},
            path=["n_start"],
            visit_set=["n_start"],
            state_revision=0,
        )
        profile_id_str = str(profile_id)
        with pytest.raises(
            ValidationError, match=r"current_node is not a node in this story version"
        ):
            await put_reading_state(profile_id_str, "s_syn", body, ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_put_missing_version_raises_404(self) -> None:
        """A save citing a StorybookVersion that does not exist raises 404."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("s_syn", family_id)
        session = _FakeSession(
            get_map={(Storybook, "s_syn"): book},  # no version row seeded
            scalar_result=None,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = ReadingStateBody(
            version=7,
            current_node="n_start",
            var_state={},
            path=["n_start"],
            visit_set=["n_start"],
            state_revision=0,
        )
        profile_id_str = str(profile_id)
        with pytest.raises(
            ResourceNotFoundError, match=r"version 7 of 's_syn' not found"
        ):
            await put_reading_state(profile_id_str, "s_syn", body, ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_put_accepts_valid_first_save(self) -> None:
        """A structurally-valid first save against the pinned version succeeds."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("s_syn", family_id)
        version = _approved_version("s_syn", 1, _story_blob())
        session = _FakeSession(
            get_map={
                (Storybook, "s_syn"): book,
                (StorybookVersion, ("s_syn", 1)): version,
            },
            scalar_result=None,  # no existing ReadingState -> create path
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = ReadingStateBody(
            version=1,
            current_node="n_start",
            var_state={"courage": 0},
            path=["n_start"],
            visit_set=["n_start"],
            state_revision=0,
        )
        result = await put_reading_state(str(profile_id), "s_syn", body, ctx)
        assert result.current_node == "n_start"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_put_forwards_choice_path_and_accepts_genuine_replay(self) -> None:
        """A body.choice_path is forwarded to validate_reading_state and a
        genuinely-replayed state is accepted.
        """
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("s_syn", family_id)
        version = _approved_version("s_syn", 1, _story_blob())
        session = _FakeSession(
            get_map={
                (Storybook, "s_syn"): book,
                (StorybookVersion, ("s_syn", 1)): version,
            },
            scalar_result=None,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = ReadingStateBody(
            version=1,
            current_node="n_end",
            var_state={"courage": 2},
            path=["n_start", "n_end"],
            visit_set=["n_start", "n_end"],
            choice_path=["c_go"],
            state_revision=0,
        )
        result = await put_reading_state(str(profile_id), "s_syn", body, ctx)
        assert result.current_node == "n_end"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_put_forwards_save_slots_and_rejects_a_forged_slot(self) -> None:
        """A non-empty body.save_slots must reach the gate and be refused (B1).

        save_slots was the one persisted reading-state field
        ``validate_reading_state`` did not receive, so a forged slot went straight
        onto the JSONB column unchecked. This proves the field now reaches the
        gate rather than being silently dropped, which is the same property the
        choice_path tests above establish for replay.
        """
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("s_syn", family_id)
        version = _approved_version("s_syn", 1, _story_blob())
        session = _FakeSession(
            get_map={
                (Storybook, "s_syn"): book,
                (StorybookVersion, ("s_syn", 1)): version,
            },
            scalar_result=None,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = ReadingStateBody(
            version=1,
            current_node="n_start",
            var_state={"courage": 0},
            path=["n_start"],
            visit_set=["n_start"],
            state_revision=0,
            save_slots={
                "forged": {"current_node": "n_end", "var_state": {"courage": 9}}
            },
        )
        with pytest.raises(ValidationError, match="save_slots must be empty"):
            await put_reading_state(str(profile_id), "s_syn", body, ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_put_forwards_choice_path_and_rejects_forged_replay(self) -> None:
        """A forged var_state that is in-bounds (so the structural floor alone
        would accept it) must still be rejected once body.choice_path is
        present, proving choice_path actually reaches validate_reading_state's
        full-replay tier rather than being silently dropped.
        """
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("s_syn", family_id)
        version = _approved_version("s_syn", 1, _story_blob())
        session = _FakeSession(
            get_map={
                (Storybook, "s_syn"): book,
                (StorybookVersion, ("s_syn", 1)): version,
            },
            scalar_result=None,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = ReadingStateBody(
            version=1,
            current_node="n_end",
            var_state={"courage": 5},  # in-bounds (0..5) but replay yields 2
            path=["n_start", "n_end"],
            visit_set=["n_start", "n_end"],
            choice_path=["c_go"],
            state_revision=0,
        )
        profile_id_str = str(profile_id)
        with pytest.raises(
            ValidationError,
            match=r"submitted reading state does not match a replay of choice_path",
        ):
            await put_reading_state(profile_id_str, "s_syn", body, ctx)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_path_forwards_the_row_seed_not_none(self) -> None:
        """The update path must pass row.seed_var_state, not None, to replay.

        Every other put_reading_state test in this class takes the create
        path (scalar_result=None), so none of them observes this call site's
        seed_var_state=row.seed_var_state argument (api/reading.py). The body
        below is constructed to be asymmetric: it replays correctly (and
        would be ACCEPTED) if the seed were None, but the existing row
        carries seed_var_state={"courage": 3}, so the same body must be
        REJECTED once c_go's +2 effect is applied on top of the real seed
        (3 + 2 = 5, not the submitted 2). A test that passed either way
        (i.e. that would also pass if reading.py forwarded None) would prove
        nothing about which value was threaded through; this one only
        passes if the row's seed reaches validate_reading_state.
        """
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("s_syn", family_id)
        version = _approved_version("s_syn", 1, _story_blob())
        existing = _state_row(profile_id, "s_syn", current_node="n_start")
        existing.seed_var_state = {"courage": 3}
        session = _FakeSession(
            get_map={
                (Storybook, "s_syn"): book,
                (StorybookVersion, ("s_syn", 1)): version,
            },
            scalar_result=existing,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)
        body = ReadingStateBody(
            version=1,
            current_node="n_end",
            var_state={"courage": 2},  # correct only if seed_var_state=None
            path=["n_start", "n_end"],
            visit_set=["n_start", "n_end"],
            choice_path=["c_go"],
            state_revision=3,  # matches _state_row's default
        )
        profile_id_str = str(profile_id)
        with pytest.raises(
            ValidationError,
            match=r"submitted reading state does not match a replay of choice_path",
        ):
            await put_reading_state(profile_id_str, "s_syn", body, ctx)


# ---------------------------------------------------------------------------
# record_completion
# ---------------------------------------------------------------------------


class TestRecordCompletion:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_new_completion_inserted_and_returned(self) -> None:
        """A first completion for an ending is inserted, with is_new/found/total (W0.3)."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        blob = _completion_blob("end-happy", "end-other", ending_count=2)
        sv = _approved_version("story-1", 1, blob)
        key = (profile_id, "story-1", 1, "end-happy")
        session = _FakeSession(
            get_map={
                (Storybook, "story-1"): book,
                (StorybookVersion, ("story-1", 1)): sv,
                (Completion, key): None,
            },
            # Stands in for the post-flush distinct-ending count query: this
            # profile has found 1 distinct ending (the one just inserted).
            scalar_result=1,
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
        assert result.is_new is True
        assert result.found == 1
        assert result.total == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_existing_completion_returned_without_insert(self) -> None:
        """A duplicate completion request returns the existing row, is_new=False (W0.3)."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        blob = _completion_blob("end-sad", ending_count=1)
        sv = _approved_version("story-1", 1, blob)
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
            },
            # The repeat completion does not change the distinct-ending count.
            scalar_result=1,
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
        assert result.is_new is False
        assert result.found == 1
        assert result.total == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_ending_id_raises_validation(self) -> None:
        """An ending_id not in the version blob raises ValidationError."""
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        blob = _completion_blob("real-end")
        sv = _approved_version("story-1", 1, blob)
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

        with pytest.raises(
            ValidationError, match=r"ending_id does not belong to the cited version"
        ):
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

        with pytest.raises(
            ResourceNotFoundError, match=r"version 99 of 'story-1' not found"
        ):
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

        with pytest.raises(
            ResourceNotFoundError, match=r"storybook 'no-book' not found"
        ):
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

        with pytest.raises(
            AuthorizationError, match=r"resource belongs to another family"
        ):
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

        with pytest.raises(ValidationError, match=r"profile_id must be a UUID"):
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

        with pytest.raises(
            AuthorizationError, match=r"profile is not accessible to this principal"
        ):
            await record_completion(body, ctx)


# ---------------------------------------------------------------------------
# CompletionBody contract
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCompletionBodyContract:
    """The request body a client may send when claiming an ending.

    ``api/reading.py::_ending_is_satisfying``'s ``#CRITICAL`` marker rests on
    this: character progression is decided from the SERVER's pinned version
    blob because the request body has no field that could say otherwise. That
    holds only while ``CompletionBody`` both lacks such a field and refuses
    unknown ones, so both halves are pinned here rather than left to the
    model definition being read carefully.
    """

    def test_a_completion_body_carrying_an_extra_field_is_rejected(self) -> None:
        """extra="forbid": an invented field is a 422, not a silently dropped one."""
        payload = {
            "profile_id": str(uuid.uuid4()),
            "storybook_id": "story-1",
            "version": 1,
            "ending_id": "end-happy",
            # A client asserting its own ending kind. If this were merely
            # ignored instead of rejected, the field could later be wired up
            # by accident without any test noticing.
            "kind": "success",
        }
        # Validated from a dict, not constructed with a keyword, so the
        # deliberately-invalid field needs no type-checker suppression.
        with pytest.raises(PydanticValidationError, match="Extra inputs are not"):
            CompletionBody.model_validate(payload)
        del payload["kind"]
        assert CompletionBody.model_validate(payload).ending_id == "end-happy"

    def test_the_body_declares_no_ending_kind_or_var_state_field(self) -> None:
        """The rejection above only matters while no such field is declared."""
        declared = set(CompletionBody.model_fields)
        assert declared == {
            "profile_id",
            "storybook_id",
            "version",
            "ending_id",
            "event_id",
        }


# ---------------------------------------------------------------------------
# get_series_next
# ---------------------------------------------------------------------------


class TestGetSeriesNext:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_next_book_title_strips_sentinels(self) -> None:
        """SeriesNextBook.title must not leak a raw personalization sentinel.

        ADR-023 P3 (registry: tests/unit/test_title_strip_registry.py). The
        series-next feed is kid-facing, structurally identical to the
        already-fixed LibraryItem/ReadingHistoryItem/RecommendationItem
        sites: the sibling's published blob title is read verbatim from
        `blob.get("title")` and must be stripped before it reaches the
        response model.
        """
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        book = _published_book("story-1", family_id)
        book.series_id = uuid.uuid4()
        book.book_index = 1
        sibling = _published_book("story-2", family_id)
        sibling.series_id = book.series_id
        sibling.book_index = 2
        token = wrap("HERO", "Explorer")
        blob = _valid_blob()
        blob["title"] = f"{token} and the Map"
        version = _approved_version("story-2", 1, blob)
        session = _FakeSession(
            get_map={
                (Storybook, "story-1"): book,
                (Storybook, "story-2"): sibling,
                (StorybookVersion, ("story-2", 1)): version,
            },
            scalar_result=sibling,
        )
        ctx = _ctx(_child_principal(family_id, profile_id), session)

        result = await get_series_next(str(profile_id), "story-1", ctx)

        assert result.next is not None
        assert "{~" not in result.next.title
        assert "~}" not in result.next.title
        assert "Explorer" in result.next.title


@pytest.mark.unit
class TestCompletionRecordedViewInvariants:
    """``CompletionRecordedView`` rejects a tally the ending screen cannot render.

    The response carries "you found N of M endings" and a "this one was NEW!"
    flag straight to a child's ending screen, so an incoherent pair is not a
    cosmetic problem: "you found 9 of 3!" is nonsense, and a celebration over
    a zero tally contradicts itself. Both were representable before this
    change, and the type is the only place either can be ruled out once and
    for every construction site.
    """

    @staticmethod
    def _kwargs(**overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "child_profile_id": str(uuid.uuid4()),
            "storybook_id": "story-a",
            "version": 1,
            "ending_id": "e1",
            "found_at": datetime(2026, 1, 1, tzinfo=UTC),
            "is_new": True,
            "found": 1,
            "total": 3,
        }
        base.update(overrides)
        return base

    def test_a_coherent_tally_is_accepted(self) -> None:
        # The guard rail: a validator that rejected everything would satisfy
        # both negative cases below while breaking every real completion.
        view = CompletionRecordedView(**self._kwargs())  # pyright: ignore[reportAny]
        assert view.found == 1
        assert view.total == 3

    def test_found_may_equal_total(self) -> None:
        # The boundary is inclusive: finding the last ending is the single
        # most important response this endpoint returns (it is what unlocks
        # the "found them all" celebration), so an off-by-one in the
        # comparison must fail a test rather than a child's last ending.
        view = CompletionRecordedView(**self._kwargs(found=3, total=3))  # pyright: ignore[reportAny]
        assert view.found == view.total

    def test_found_above_total_is_rejected(self) -> None:
        kwargs = self._kwargs(found=9, total=3)
        with pytest.raises(PydanticValidationError, match="cannot exceed"):
            CompletionRecordedView(**kwargs)  # pyright: ignore[reportAny]

    def test_a_new_find_with_a_zero_tally_is_rejected(self) -> None:
        # Structurally unreachable through the route: record_completion
        # flushes the insert before counting, precisely so the new row is
        # visible to the count query. That flush is what this invariant
        # protects; drop it and the count runs blind, which this catches at
        # the type rather than in a child-facing "0 endings found" celebration.
        kwargs = self._kwargs(is_new=True, found=0, total=3)
        with pytest.raises(PydanticValidationError, match="a new find must be counted"):
            CompletionRecordedView(**kwargs)  # pyright: ignore[reportAny]

    def test_a_repeat_visit_with_a_zero_tally_is_still_rejected_only_by_found(
        self,
    ) -> None:
        # is_new=False with found=0 is merely impossible-in-practice, not
        # self-contradictory (nothing claims a find happened), so the
        # validator deliberately does NOT reject it. Pinned so a later
        # "tighten it further" change is a considered decision, not a silent
        # 500 on a shape the route could theoretically produce.
        view = CompletionRecordedView(**self._kwargs(is_new=False, found=0, total=3))  # pyright: ignore[reportAny]
        assert view.is_new is False


@pytest.mark.unit
class TestCompletionRecordedViewBoundary:
    """``_completion_recorded_view`` degrades rather than 500s on a bad total."""

    @staticmethod
    def _row() -> Completion:
        row = Completion(
            child_profile_id=uuid.uuid4(),
            storybook_id="story-a",
            version=1,
            ending_id="e1",
        )
        row.found_at = datetime(2026, 1, 1, tzinfo=UTC)
        return row

    def test_recorded_view_widens_an_understated_ending_total(self) -> None:
        """The row is already committed when this view is built.

        Letting the model's own invariant raise here would hand a child an
        error screen for an ending the server DID record. The only cause is a
        pinned version whose ``metadata.ending_count`` understates its real
        endings, so widening the total to what was actually counted is both
        the truthful number and the one that keeps the screen readable.
        """
        with patch.object(reading_module, "_logger") as logger:
            view = _completion_recorded_view(self._row(), is_new=True, found=4, total=2)
        assert view.found == 4
        assert view.total == 4
        logger.warning.assert_called_once_with(
            "completion_ending_total_understated",
            storybook_id="story-a",
            version=1,
            declared_total=2,
            distinct_found=4,
        )

    def test_a_correct_total_is_left_alone_and_logs_nothing(self) -> None:
        with patch.object(reading_module, "_logger") as logger:
            view = _completion_recorded_view(self._row(), is_new=True, found=2, total=5)
        assert view.total == 5
        logger.warning.assert_not_called()
