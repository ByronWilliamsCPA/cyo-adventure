"""Unit tests for the notification projection's DB-touching half (S9/G10).

No real database and no ASGI stack (mirrors tests/unit/test_ratings_api_unit.py
and test_assignments_api_unit.py): every test builds real ORM instances
in-memory (never added to a session) and a small scripted async session
double that returns them in the fixed call order each function under test is
known to make. The orchestration tests (``TestListGuardianNotifications``)
patch ``service._ENTITY_RESOLVERS`` with fakes so they exercise the
family-scoping gate in isolation from any particular resolver's query shape;
each resolver is also tested directly and separately below.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from cyo_adventure.api.deps import Principal
from cyo_adventure.db.models import (
    ChildProfile,
    GenerationJob,
    KidFlag,
    PipelineEvent,
    Storybook,
    StorybookVersion,
    StoryRequest,
)
from cyo_adventure.events.models import EventType
from cyo_adventure.notifications import service
from cyo_adventure.notifications.models import EntityContext

_T0 = datetime(2026, 7, 1, tzinfo=UTC)
_T1 = datetime(2026, 7, 2, tzinfo=UTC)
_T2 = datetime(2026, 7, 3, tzinfo=UTC)


class _Result:
    """Stand-in for whatever ``session.scalars``/``session.execute`` returns."""

    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _SeqSession:
    """Async session double returning pre-scripted rows in call order.

    ``scalars()`` and ``execute()`` draw from independent FIFO queues, since
    every resolver under test makes a fixed, known sequence of each.
    """

    def __init__(
        self,
        *,
        scalars: list[list[object]] | None = None,
        execute: list[list[object]] | None = None,
    ) -> None:
        self._scalars = list(scalars or [])
        self._execute = list(execute or [])
        self.scalars_calls: list[object] = []
        self.execute_calls: list[object] = []

    async def scalars(self, stmt: object) -> _Result:
        self.scalars_calls.append(stmt)
        return _Result(self._scalars.pop(0))

    async def execute(self, stmt: object) -> _Result:
        self.execute_calls.append(stmt)
        return _Result(self._execute.pop(0))


def _principal(family_id: uuid.UUID, *, role: str = "guardian") -> Principal:
    return Principal(
        subject="sub",
        user_id=uuid.uuid4(),
        role=role,
        family_id=family_id,
        profile_ids=frozenset(),
    )


def _story_request(
    *, id_: uuid.UUID, family_id: uuid.UUID, profile_id: uuid.UUID | None
) -> StoryRequest:
    return StoryRequest(
        id=id_,
        family_id=family_id,
        profile_id=profile_id,
        request_text="a fox explores a forest",
        status="pending",
        initiator_role="child",
        age_band="8-11",
    )


def _storybook(
    *, id_: str, family_id: uuid.UUID, current_published_version: int | None
) -> Storybook:
    return Storybook(
        id=id_,
        family_id=family_id,
        current_published_version=current_published_version,
        status="published" if current_published_version else "draft",
    )


def _version(*, storybook_id: str, version: int, title: str | None) -> StorybookVersion:
    blob: dict[str, object] = {"title": title} if title is not None else {}
    return StorybookVersion(storybook_id=storybook_id, version=version, blob=blob)


def _child_profile(
    *, id_: uuid.UUID, family_id: uuid.UUID, display_name: str
) -> ChildProfile:
    return ChildProfile(
        id=id_, family_id=family_id, display_name=display_name, age_band="8-11"
    )


@pytest.mark.unit
class TestResolveStoryRequest:
    @pytest.mark.asyncio
    async def test_resolves_family_and_profile_name(self) -> None:
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        req = _story_request(
            id_=uuid.uuid4(), family_id=family_id, profile_id=profile_id
        )
        session = _SeqSession(scalars=[[req]], execute=[[(profile_id, "Maya")]])

        result = await service._resolve_story_request(
            session, [str(req.id), "not-a-uuid"]
        )

        assert set(result) == {str(req.id)}
        ctx = result[str(req.id)]
        assert ctx.family_id == family_id
        assert ctx.profile_id == profile_id
        assert ctx.profile_name == "Maya"
        assert ctx.request_id == str(req.id)

    @pytest.mark.asyncio
    async def test_profileless_request_skips_the_name_lookup(self) -> None:
        family_id = uuid.uuid4()
        req = _story_request(id_=uuid.uuid4(), family_id=family_id, profile_id=None)
        session = _SeqSession(
            scalars=[[req]]
        )  # no execute() queued: must not be called

        result = await service._resolve_story_request(session, [str(req.id)])

        assert result[str(req.id)].profile_id is None
        assert result[str(req.id)].profile_name is None
        assert session.execute_calls == []

    @pytest.mark.asyncio
    async def test_no_valid_uuids_short_circuits_without_querying(self) -> None:
        session = _SeqSession()
        result = await service._resolve_story_request(session, ["not-a-uuid"])
        assert result == {}
        assert session.scalars_calls == []


@pytest.mark.unit
class TestResolveGenerationJob:
    @pytest.mark.asyncio
    async def test_resolves_family_via_concept(self) -> None:
        family_id = uuid.uuid4()
        concept_id = uuid.uuid4()
        job = GenerationJob(
            id=uuid.uuid4(), concept_id=concept_id, status="failed", storybook_id=None
        )
        session = _SeqSession(execute=[[(job, family_id)]])

        result = await service._resolve_generation_job(session, [str(job.id)])

        ctx = result[str(job.id)]
        assert ctx.family_id == family_id
        assert ctx.storybook_id is None


@pytest.mark.unit
class TestResolveStorybook:
    @pytest.mark.asyncio
    async def test_resolves_family_and_current_title(self) -> None:
        family_id = uuid.uuid4()
        book = _storybook(
            id_="the-lighthouse-mystery",
            family_id=family_id,
            current_published_version=2,
        )
        version = _version(
            storybook_id=book.id, version=2, title="The Lighthouse Mystery"
        )
        session = _SeqSession(scalars=[[book], [version]])

        result = await service._resolve_storybook(session, [book.id])

        ctx = result[book.id]
        assert ctx.family_id == family_id
        assert ctx.storybook_title == "The Lighthouse Mystery"

    @pytest.mark.asyncio
    async def test_unpublished_book_has_no_title_lookup(self) -> None:
        family_id = uuid.uuid4()
        book = _storybook(
            id_="draft-book", family_id=family_id, current_published_version=None
        )
        session = _SeqSession(scalars=[[book]])  # no second scalars() call queued

        result = await service._resolve_storybook(session, [book.id])

        assert result[book.id].storybook_title is None
        assert len(session.scalars_calls) == 1


@pytest.mark.unit
class TestResolveStorybookVersion:
    @pytest.mark.asyncio
    async def test_splits_on_the_last_colon_and_resolves_family(self) -> None:
        family_id = uuid.uuid4()
        version = _version(storybook_id="a:tricky:id", version=3, title="Tricky Title")
        session = _SeqSession(execute=[[(version, family_id)]])

        result = await service._resolve_storybook_version(
            session, ["a:tricky:id:3", "malformed-no-colon"]
        )

        assert set(result) == {"a:tricky:id:3"}
        ctx = result["a:tricky:id:3"]
        assert ctx.family_id == family_id
        assert ctx.storybook_id == "a:tricky:id"
        assert ctx.storybook_title == "Tricky Title"


@pytest.mark.unit
class TestResolveStorybookAssignment:
    @pytest.mark.asyncio
    async def test_resolves_family_from_the_child_not_the_book(self) -> None:
        child_family = uuid.uuid4()
        book_family = (
            uuid.uuid4()
        )  # deliberately different: catalog cross-family assign
        profile_id = uuid.uuid4()
        profile = _child_profile(
            id_=profile_id, family_id=child_family, display_name="Briella"
        )
        book = _storybook(
            id_="the-lighthouse-mystery",
            family_id=book_family,
            current_published_version=1,
        )
        version = _version(
            storybook_id=book.id, version=1, title="The Lighthouse Mystery"
        )
        session = _SeqSession(scalars=[[profile], [book], [version]])

        entity_id = f"{profile_id}:{book.id}"
        result = await service._resolve_storybook_assignment(session, [entity_id])

        ctx = result[entity_id]
        assert ctx.family_id == child_family
        assert ctx.profile_name == "Briella"
        assert ctx.storybook_title == "The Lighthouse Mystery"

    @pytest.mark.asyncio
    async def test_unknown_profile_is_dropped(self) -> None:
        # ChildProfile lookup returns nothing, so the storybook_ids set is
        # still built (storybook_id parses out fine) and a Storybook lookup
        # still runs; with no books found either, _titles_for_pairs
        # short-circuits on an empty pairs list without a third query.
        session = _SeqSession(scalars=[[], []])
        entity_id = f"{uuid.uuid4()}:some-book"
        result = await service._resolve_storybook_assignment(session, [entity_id])
        assert result == {}


@pytest.mark.unit
class TestResolveKidFlag:
    @pytest.mark.asyncio
    async def test_resolves_family_profile_and_the_version_actually_read(self) -> None:
        family_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        flag = KidFlag(
            id=uuid.uuid4(),
            family_id=family_id,
            profile_id=profile_id,
            storybook_id="the-lighthouse-mystery",
            version=1,
            reason="scared_me",
        )
        session = _SeqSession(
            scalars=[
                [flag],
                [
                    _version(
                        storybook_id=flag.storybook_id,
                        version=1,
                        title="The Lighthouse Mystery",
                    )
                ],
            ],
            execute=[[(profile_id, "Maya")]],
        )

        result = await service._resolve_kid_flag(session, [str(flag.id)])

        ctx = result[str(flag.id)]
        assert ctx.family_id == family_id
        assert ctx.profile_id == profile_id
        assert ctx.profile_name == "Maya"
        assert ctx.storybook_title == "The Lighthouse Mystery"


@pytest.mark.unit
class TestCandidateCap:
    def test_small_limit_uses_the_floor(self) -> None:
        assert service._candidate_cap(1) == service._CANDIDATE_FLOOR

    def test_large_limit_is_capped_at_the_ceiling(self) -> None:
        assert service._candidate_cap(1000) == service._CANDIDATE_CEILING

    def test_mid_range_limit_scales_by_the_multiplier(self) -> None:
        limit = 30
        expected = limit * service._CANDIDATE_MULTIPLIER
        assert service._candidate_cap(limit) == expected


def _pipeline_event(
    *,
    event_type: EventType,
    entity_type: str,
    entity_id: str,
    occurred_at: datetime,
    to_state: str | None = None,
    payload: dict[str, object] | None = None,
) -> PipelineEvent:
    return PipelineEvent(
        id=uuid.uuid4(),
        occurred_at=occurred_at,
        actor_id=None,
        actor_role="system",
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=str(event_type),
        to_state=to_state,
        payload=payload or {},
    )


@pytest.mark.unit
class TestListGuardianNotifications:
    @pytest.mark.asyncio
    async def test_family_scoping_negative_other_family_events_never_appear(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        family_a = uuid.uuid4()
        family_b = uuid.uuid4()
        event_a = _pipeline_event(
            event_type=EventType.RELEASED,
            entity_type="storybook",
            entity_id="book-a",
            occurred_at=_T1,
            to_state="published",
        )
        event_b = _pipeline_event(
            event_type=EventType.RELEASED,
            entity_type="storybook",
            entity_id="book-b",
            occurred_at=_T2,
            to_state="published",
        )
        session = _SeqSession(scalars=[[event_a, event_b]])

        async def fake_resolver(
            _session: object, ids: list[str]
        ) -> dict[str, EntityContext]:
            contexts = {
                "book-a": EntityContext(
                    family_id=family_a, storybook_id="book-a", storybook_title="Book A"
                ),
                "book-b": EntityContext(
                    family_id=family_b, storybook_id="book-b", storybook_title="Book B"
                ),
            }
            return {i: contexts[i] for i in ids if i in contexts}

        monkeypatch.setattr(service, "_ENTITY_RESOLVERS", {"storybook": fake_resolver})

        items = await service.list_guardian_notifications(
            session, _principal(family_a), since=None, limit=30
        )

        assert len(items) == 1
        assert items[0].storybook_id == "book-a"
        assert "Book B" not in items[0].title
        assert "Book B" not in items[0].body

    @pytest.mark.asyncio
    async def test_unknown_entity_type_is_dropped_not_raised(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        family_id = uuid.uuid4()
        event = _pipeline_event(
            event_type=EventType.RELEASED,
            entity_type="a-brand-new-entity-type-nobody-resolves-yet",
            entity_id="whatever",
            occurred_at=_T1,
            to_state="published",
        )
        session = _SeqSession(scalars=[[event]])
        monkeypatch.setattr(service, "_ENTITY_RESOLVERS", {})

        items = await service.list_guardian_notifications(
            session, _principal(family_id), since=None, limit=30
        )

        assert items == []

    @pytest.mark.asyncio
    async def test_composer_none_result_is_excluded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        family_id = uuid.uuid4()
        # A guardian-initiated REQUEST_CREATED: registry.compose drops this
        # (see test_notifications_registry.py), so it must never reach the
        # output even though its entity resolves fine to the caller's family.
        event = _pipeline_event(
            event_type=EventType.REQUEST_CREATED,
            entity_type="story_request",
            entity_id="req-1",
            occurred_at=_T1,
            to_state="pending",
            payload={"initiator_role": "guardian"},
        )
        session = _SeqSession(scalars=[[event]])

        async def fake_resolver(
            _session: object, _ids: list[str]
        ) -> dict[str, EntityContext]:
            return {"req-1": EntityContext(family_id=family_id, request_id="req-1")}

        monkeypatch.setattr(
            service, "_ENTITY_RESOLVERS", {"story_request": fake_resolver}
        )

        items = await service.list_guardian_notifications(
            session, _principal(family_id), since=None, limit=30
        )

        assert items == []

    @pytest.mark.asyncio
    async def test_limit_truncates_and_preserves_newest_first_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        family_id = uuid.uuid4()
        events = [
            _pipeline_event(
                event_type=EventType.RELEASED,
                entity_type="storybook",
                entity_id=f"book-{i}",
                occurred_at=ts,
                to_state="published",
            )
            for i, ts in enumerate([_T2, _T1, _T0])
        ]
        session = _SeqSession(scalars=[events])

        async def fake_resolver(
            _session: object, ids: list[str]
        ) -> dict[str, EntityContext]:
            return {i: EntityContext(family_id=family_id, storybook_id=i) for i in ids}

        monkeypatch.setattr(service, "_ENTITY_RESOLVERS", {"storybook": fake_resolver})

        items = await service.list_guardian_notifications(
            session, _principal(family_id), since=None, limit=2
        )

        assert len(items) == 2
        assert items[0].storybook_id == "book-0"  # occurred_at = _T2, newest
        assert items[1].storybook_id == "book-1"  # occurred_at = _T1

    @pytest.mark.asyncio
    async def test_since_is_pushed_into_the_where_clause(self) -> None:
        session = _SeqSession(scalars=[[]])

        await service.list_guardian_notifications(
            session, _principal(uuid.uuid4()), since=_T1, limit=30
        )

        stmt = session.scalars_calls[0]
        where = str(stmt.whereclause)
        assert "occurred_at" in where
        # event_type is bound as an expanding IN-list (unhashable), so check
        # membership directly on the params view rather than via set().
        assert _T1 in stmt.compile().params.values()

    @pytest.mark.asyncio
    async def test_no_since_omits_the_occurred_at_predicate(self) -> None:
        session = _SeqSession(scalars=[[]])

        await service.list_guardian_notifications(
            session, _principal(uuid.uuid4()), since=None, limit=30
        )

        stmt = session.scalars_calls[0]
        where = str(stmt.whereclause)
        assert "occurred_at" not in where
        assert "event_type" in where

    @pytest.mark.asyncio
    async def test_non_positive_limit_returns_empty_without_querying(self) -> None:
        session = _SeqSession()
        items = await service.list_guardian_notifications(
            session, _principal(uuid.uuid4()), since=None, limit=0
        )
        assert items == []
        assert session.scalars_calls == []
