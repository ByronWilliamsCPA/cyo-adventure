"""Unit tests for the admin audit route handler (no DB, no ASGI stack).

Calls ``list_audit_events`` directly with a constructed ``Principal`` / fake
session, following the ``_FakeSession``/``_FakeScalars`` pattern established
in ``test_reading_history_api_unit.py`` (session.scalars() drains an ordered
queue of rows) plus the role-gate testing style from
``test_notifications_api_unit.py``. Covers: admin-only enforcement, every
filter (kind, actor_id, storybook_id, profile_id, since, until), pagination
(limit/offset/has_more), newest-first ordering, and empty results.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cyo_adventure.api import audit
from cyo_adventure.api.deps import Principal, RequestContext
from cyo_adventure.core.exceptions import AuthorizationError, ValidationError
from cyo_adventure.db.models import PipelineEvent

_T1 = datetime(2026, 1, 1, tzinfo=UTC)
_T2 = datetime(2026, 1, 2, tzinfo=UTC)
_T3 = datetime(2026, 1, 3, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fake session
# ---------------------------------------------------------------------------


class _FakeScalars:
    """Returned by session.scalars() -- wraps a list of ORM rows."""

    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        """Return the seeded rows."""
        return self._rows


class _FakeSession:
    """Minimal async session double: session.scalars() drains an ordered queue."""

    def __init__(self, queue: list[list[object]]) -> None:
        self._queue: list[list[object]] = [list(rows) for rows in queue]
        self.scalars_calls: list[object] = []

    async def scalars(self, stmt: object) -> _FakeScalars:
        """Return the next queued row list, in call order."""
        self.scalars_calls.append(stmt)
        rows = self._queue.pop(0) if self._queue else []
        return _FakeScalars(rows)


# ---------------------------------------------------------------------------
# Principal / context builders
# ---------------------------------------------------------------------------


def _admin_principal() -> Principal:
    return Principal(
        subject="admin-sub",
        user_id=uuid.uuid4(),
        role="admin",
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
    )


def _guardian_principal() -> Principal:
    return Principal(
        subject="guardian-sub",
        user_id=uuid.uuid4(),
        role="guardian",
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
    )


def _child_principal() -> Principal:
    return Principal(
        subject="child-sub",
        user_id=uuid.uuid4(),
        role="child",
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
    )


def _dual_role_principal() -> Principal:
    """A guardian who also holds the admin capability."""
    return Principal(
        subject="dual-sub",
        user_id=uuid.uuid4(),
        role="guardian",
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
        is_admin=True,
    )


def _ctx(
    principal: Principal, rows: list[list[object]] | None = None
) -> RequestContext:
    session = _FakeSession(rows if rows is not None else [[]])
    return RequestContext(principal=principal, session=session)


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------


def _event(
    *,
    event_type: str = "book_assigned",
    entity_type: str = "storybook_assignment",
    entity_id: str = "some-entity",
    actor_id: uuid.UUID | None = None,
    actor_role: str = "admin",
    occurred_at: datetime = _T1,
    from_state: str | None = None,
    to_state: str | None = None,
    payload: dict[str, object] | None = None,
) -> PipelineEvent:
    row = PipelineEvent(
        actor_id=actor_id,
        actor_role=actor_role,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        from_state=from_state,
        to_state=to_state,
        payload=payload or {},
    )
    row.id = uuid.uuid4()
    row.occurred_at = occurred_at
    return row


# ---------------------------------------------------------------------------
# Role gate
# ---------------------------------------------------------------------------


class TestListAuditEventsRoleGate:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_admin_token_is_accepted(self) -> None:
        ctx = _ctx(_admin_principal(), [[]])
        view = await audit.list_audit_events(ctx, audit.AuditFilters())
        assert view.events == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_dual_role_token_is_accepted(self) -> None:
        ctx = _ctx(_dual_role_principal(), [[]])
        view = await audit.list_audit_events(ctx, audit.AuditFilters())
        assert view.events == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_guardian_token_gets_403(self) -> None:
        ctx = _ctx(_guardian_principal())
        with pytest.raises(AuthorizationError):
            await audit.list_audit_events(ctx, audit.AuditFilters())

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_child_token_gets_403(self) -> None:
        ctx = _ctx(_child_principal())
        with pytest.raises(AuthorizationError):
            await audit.list_audit_events(ctx, audit.AuditFilters())

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_rejected_role_never_reaches_the_query(self) -> None:
        session = _FakeSession([[]])
        ctx = RequestContext(principal=_guardian_principal(), session=session)
        with pytest.raises(AuthorizationError):
            await audit.list_audit_events(ctx, audit.AuditFilters())
        assert session.scalars_calls == []


# ---------------------------------------------------------------------------
# _validate_kind
# ---------------------------------------------------------------------------


class TestValidateKind:
    @pytest.mark.unit
    def test_none_is_accepted(self) -> None:
        audit._validate_kind(None)  # no raise

    @pytest.mark.unit
    def test_known_kind_is_accepted(self) -> None:
        audit._validate_kind("book_assigned")  # no raise

    @pytest.mark.unit
    def test_unknown_kind_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match="kind"):
            audit._validate_kind("not_a_real_event_type")


# ---------------------------------------------------------------------------
# _parse_timestamp
# ---------------------------------------------------------------------------


class TestParseTimestamp:
    @pytest.mark.unit
    def test_none_returns_none(self) -> None:
        assert audit._parse_timestamp(None, "since") is None

    @pytest.mark.unit
    def test_offset_aware_timestamp_round_trips(self) -> None:
        parsed = audit._parse_timestamp("2026-07-01T12:00:00+00:00", "since")
        assert parsed == datetime(2026, 7, 1, 12, 0, tzinfo=UTC)

    @pytest.mark.unit
    def test_naive_timestamp_is_treated_as_utc(self) -> None:
        parsed = audit._parse_timestamp("2026-07-01T12:00:00", "until")
        assert parsed is not None
        assert parsed.tzinfo == UTC

    @pytest.mark.unit
    def test_malformed_timestamp_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match="since"):
            audit._parse_timestamp("not-a-timestamp", "since")


# ---------------------------------------------------------------------------
# _bound_limit / _bound_offset
# ---------------------------------------------------------------------------


class TestBoundLimit:
    @pytest.mark.unit
    def test_within_range_is_unchanged(self) -> None:
        assert audit._bound_limit(10) == 10

    @pytest.mark.unit
    def test_zero_or_negative_clamps_to_one(self) -> None:
        assert audit._bound_limit(0) == 1
        assert audit._bound_limit(-5) == 1

    @pytest.mark.unit
    def test_above_ceiling_clamps_to_max(self) -> None:
        assert audit._bound_limit(10_000) == audit._MAX_LIMIT


class TestBoundOffset:
    @pytest.mark.unit
    def test_within_range_is_unchanged(self) -> None:
        assert audit._bound_offset(25) == 25

    @pytest.mark.unit
    def test_negative_clamps_to_zero(self) -> None:
        assert audit._bound_offset(-5) == 0


# ---------------------------------------------------------------------------
# Filters, forwarded through to the query (asserted via returned view + the
# fact that the fake session only ever returns the rows it was seeded with;
# the WHERE clauses themselves are exercised end to end in
# tests/integration/test_audit_api.py).
# ---------------------------------------------------------------------------


class TestFilterParsingAndValidation:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_kind_raises_before_any_query(self) -> None:
        session = _FakeSession([[]])
        ctx = RequestContext(principal=_admin_principal(), session=session)
        with pytest.raises(ValidationError, match="kind"):
            await audit.list_audit_events(
                ctx, audit.AuditFilters(kind="not_a_real_event_type")
            )
        assert session.scalars_calls == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_actor_id_raises_before_any_query(self) -> None:
        session = _FakeSession([[]])
        ctx = RequestContext(principal=_admin_principal(), session=session)
        with pytest.raises(ValidationError, match="actor_id"):
            await audit.list_audit_events(
                ctx, audit.AuditFilters(actor_id="not-a-uuid")
            )
        assert session.scalars_calls == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_profile_id_raises_before_any_query(self) -> None:
        session = _FakeSession([[]])
        ctx = RequestContext(principal=_admin_principal(), session=session)
        with pytest.raises(ValidationError, match="profile_id"):
            await audit.list_audit_events(
                ctx, audit.AuditFilters(profile_id="not-a-uuid")
            )
        assert session.scalars_calls == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_since_raises_before_any_query(self) -> None:
        session = _FakeSession([[]])
        ctx = RequestContext(principal=_admin_principal(), session=session)
        with pytest.raises(ValidationError, match="since"):
            await audit.list_audit_events(ctx, audit.AuditFilters(since="garbage"))
        assert session.scalars_calls == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_until_raises_before_any_query(self) -> None:
        session = _FakeSession([[]])
        ctx = RequestContext(principal=_admin_principal(), session=session)
        with pytest.raises(ValidationError, match="until"):
            await audit.list_audit_events(ctx, audit.AuditFilters(until="garbage"))
        assert session.scalars_calls == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_valid_kind_actor_storybook_profile_since_until_are_accepted(
        self,
    ) -> None:
        actor_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        session = _FakeSession([[]])
        ctx = RequestContext(principal=_admin_principal(), session=session)
        view = await audit.list_audit_events(
            ctx,
            audit.AuditFilters(
                kind="book_assigned",
                actor_id=str(actor_id),
                storybook_id="the-lighthouse-mystery",
                profile_id=str(profile_id),
                since="2026-01-01T00:00:00Z",
                until="2026-12-31T00:00:00Z",
            ),
        )
        assert view.events == []
        assert len(session.scalars_calls) == 1

    @pytest.mark.unit
    def test_extra_query_key_is_rejected(self) -> None:
        with pytest.raises(Exception, match="extra"):
            audit.AuditFilters.model_validate({"bogus_field": "x"})


# ---------------------------------------------------------------------------
# _storybook_match / _profile_match predicate shape (compiled SQL, no DB)
# ---------------------------------------------------------------------------


class TestStorybookMatch:
    @pytest.mark.unit
    def test_matches_bare_storybook_entity_id(self) -> None:
        clause = audit._storybook_match("the-lighthouse-mystery")
        compiled = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "the-lighthouse-mystery" in compiled

    @pytest.mark.unit
    def test_covers_prefix_and_suffix_shapes(self) -> None:
        # entity_id shapes this must match: bare id (storybook), "id:version"
        # (storybook_version), and "profile:id" (storybook_assignment/rating).
        clause = audit._storybook_match("book-1")
        compiled = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert "'book-1:'" in compiled
        assert "':book-1'" in compiled
        assert "LIKE" in compiled.upper()


class TestProfileMatch:
    @pytest.mark.unit
    def test_matches_leading_profile_id_segment(self) -> None:
        profile_id = uuid.uuid4()
        clause = audit._profile_match(profile_id)
        compiled = str(clause.compile(compile_kwargs={"literal_binds": True}))
        assert f"'{profile_id}:'" in compiled
        assert "LIKE" in compiled.upper()


# ---------------------------------------------------------------------------
# Pagination and ordering
# ---------------------------------------------------------------------------


class TestPagination:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_empty_results(self) -> None:
        session = _FakeSession([[]])
        ctx = RequestContext(principal=_admin_principal(), session=session)
        view = await audit.list_audit_events(ctx, audit.AuditFilters())
        assert view.events == []
        assert view.has_more is False
        assert view.limit == audit._DEFAULT_LIMIT
        assert view.offset == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_has_more_true_when_extra_row_exists(self) -> None:
        rows = [_event(occurred_at=_T1) for _ in range(3)]
        session = _FakeSession([rows])
        ctx = RequestContext(principal=_admin_principal(), session=session)
        view = await audit.list_audit_events(ctx, audit.AuditFilters(limit=2))
        assert len(view.events) == 2
        assert view.has_more is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_has_more_false_when_exactly_limit_rows_exist(self) -> None:
        rows = [_event(occurred_at=_T1) for _ in range(2)]
        session = _FakeSession([rows])
        ctx = RequestContext(principal=_admin_principal(), session=session)
        view = await audit.list_audit_events(ctx, audit.AuditFilters(limit=2))
        assert len(view.events) == 2
        assert view.has_more is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_limit_and_offset_are_bounded_and_returned(self) -> None:
        session = _FakeSession([[]])
        ctx = RequestContext(principal=_admin_principal(), session=session)
        view = await audit.list_audit_events(
            ctx, audit.AuditFilters(limit=10_000, offset=-5)
        )
        assert view.limit == audit._MAX_LIMIT
        assert view.offset == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_offset_round_trips_into_the_view(self) -> None:
        session = _FakeSession([[]])
        ctx = RequestContext(principal=_admin_principal(), session=session)
        view = await audit.list_audit_events(ctx, audit.AuditFilters(offset=40))
        assert view.offset == 40


class TestOrdering:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_query_orders_by_occurred_at_descending(self) -> None:
        # The fake session cannot itself sort (that is Postgres's job); this
        # asserts the compiled statement carries the ORDER BY the handler
        # builds, so a regression that drops/reverses it is caught here even
        # though the fake session always returns rows in seeded order.
        session = _FakeSession([[]])
        ctx = RequestContext(principal=_admin_principal(), session=session)
        await audit.list_audit_events(ctx, audit.AuditFilters())
        [stmt] = session.scalars_calls
        compiled = str(stmt)
        order_by_idx = compiled.upper().index("ORDER BY")
        occurred_at_idx = compiled.upper().index("OCCURRED_AT", order_by_idx)
        assert occurred_at_idx > order_by_idx
        assert "DESC" in compiled.upper()


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


class TestResponseShape:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_row_fields_round_trip_into_the_view(self) -> None:
        actor_id = uuid.uuid4()
        row = _event(
            event_type="threshold_changed",
            entity_type="moderation_threshold",
            entity_id="8-11",
            actor_id=actor_id,
            actor_role="admin",
            occurred_at=_T2,
            from_state=None,
            to_state=None,
            payload={"action": "upsert", "min_verdict": "review"},
        )
        session = _FakeSession([[row]])
        ctx = RequestContext(principal=_admin_principal(), session=session)
        view = await audit.list_audit_events(ctx, audit.AuditFilters())
        assert len(view.events) == 1
        out = view.events[0]
        assert out.id == str(row.id)
        assert out.occurred_at == _T2
        assert out.actor_id == str(actor_id)
        assert out.actor_role == "admin"
        assert out.entity_type == "moderation_threshold"
        assert out.entity_id == "8-11"
        assert out.event_type == "threshold_changed"
        assert out.from_state is None
        assert out.to_state is None
        assert out.payload == {"action": "upsert", "min_verdict": "review"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_system_actor_serializes_actor_id_as_none(self) -> None:
        row = _event(
            event_type="generation_started",
            entity_type="generation_job",
            entity_id=str(uuid.uuid4()),
            actor_id=None,
            actor_role="system",
            occurred_at=_T3,
        )
        session = _FakeSession([[row]])
        ctx = RequestContext(principal=_admin_principal(), session=session)
        view = await audit.list_audit_events(ctx, audit.AuditFilters())
        assert view.events[0].actor_id is None
        assert view.events[0].actor_role == "system"
