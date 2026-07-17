"""Unit tests for the guardian notification kind registry (S9/G10).

Pure, DB-free tests: every composer is exercised by constructing a real
``PipelineEvent`` ORM instance (no session, no flush -- SQLAlchemy mapped
classes are plain Python objects until added to a session) plus a hand-built
``EntityContext``, mirroring the "no DB, no ASGI" convention used across this
test suite (see tests/unit/test_assignments_api_unit.py).
"""

from __future__ import annotations

import uuid

import pytest

from cyo_adventure.db.models import PipelineEvent
from cyo_adventure.events.models import EventType
from cyo_adventure.notifications import registry
from cyo_adventure.notifications.models import EntityContext

_FAMILY = uuid.uuid4()
_PROFILE = uuid.uuid4()


def _event(
    event_type: EventType,
    *,
    to_state: str | None = None,
    from_state: str | None = None,
    payload: dict[str, object] | None = None,
) -> PipelineEvent:
    return PipelineEvent(
        id=uuid.uuid4(),
        actor_id=None,
        actor_role="system",
        entity_type="irrelevant-for-these-tests",
        entity_id="irrelevant-for-these-tests",
        event_type=str(event_type),
        from_state=from_state,
        to_state=to_state,
        payload=payload or {},
    )


def _ctx(
    *,
    profile_name: str | None = "Maya",
    storybook_title: str | None = "The Lighthouse Mystery",
) -> EntityContext:
    return EntityContext(
        family_id=_FAMILY,
        profile_id=_PROFILE,
        profile_name=profile_name,
        storybook_id="the-lighthouse-mystery",
        storybook_title=storybook_title,
    )


@pytest.mark.unit
class TestComposeRequestCreated:
    def test_child_initiated_pending_is_awaiting_consent_info(self) -> None:
        event = _event(
            EventType.REQUEST_CREATED,
            to_state="pending",
            payload={"initiator_role": "child"},
        )
        raw = registry.compose(event, _ctx())
        assert raw is not None
        assert raw.kind == "awaiting_consent"
        assert raw.severity == "info"
        assert raw.title == "Maya's story request is waiting for you"

    def test_guardian_initiated_pending_is_dropped(self) -> None:
        event = _event(
            EventType.REQUEST_CREATED,
            to_state="pending",
            payload={"initiator_role": "guardian"},
        )
        assert registry.compose(event, _ctx()) is None

    def test_admin_initiated_pending_is_dropped(self) -> None:
        event = _event(
            EventType.REQUEST_CREATED,
            to_state="pending",
            payload={"initiator_role": "admin"},
        )
        assert registry.compose(event, _ctx()) is None

    def test_blocked_is_an_alert_regardless_of_initiator(self) -> None:
        event = _event(
            EventType.REQUEST_CREATED,
            to_state="blocked",
            payload={"initiator_role": "child"},
        )
        raw = registry.compose(event, _ctx())
        assert raw is not None
        assert raw.kind == "request_blocked"
        assert raw.severity == "alert"

    def test_missing_profile_name_falls_back_to_generic_label(self) -> None:
        event = _event(
            EventType.REQUEST_CREATED,
            to_state="pending",
            payload={"initiator_role": "child"},
        )
        raw = registry.compose(event, _ctx(profile_name=None))
        assert raw is not None
        assert raw.title == "Your child's story request is waiting for you"


@pytest.mark.unit
class TestComposeRequestDecisions:
    def test_request_approved_is_info(self) -> None:
        event = _event(
            EventType.REQUEST_APPROVED, from_state="pending", to_state="approved"
        )
        raw = registry.compose(event, _ctx())
        assert raw is not None
        assert raw.kind == "request_approved"
        assert raw.severity == "info"
        assert "Maya" in raw.title

    def test_request_declined_is_info(self) -> None:
        event = _event(
            EventType.REQUEST_DECLINED, from_state="pending", to_state="declined"
        )
        raw = registry.compose(event, _ctx())
        assert raw is not None
        assert raw.kind == "request_declined"
        assert raw.severity == "info"


@pytest.mark.unit
class TestComposeGenerationFinished:
    def test_failed_outcome_is_an_alert(self) -> None:
        event = _event(EventType.GENERATION_FINISHED, payload={"outcome": "failed"})
        raw = registry.compose(event, _ctx())
        assert raw is not None
        assert raw.kind == "generation_failed"
        assert raw.severity == "alert"
        assert "could not be generated" in raw.title

    @pytest.mark.parametrize("outcome", ["passed", "needs_review"])
    def test_reviewable_outcomes_are_info(self, outcome: str) -> None:
        event = _event(EventType.GENERATION_FINISHED, payload={"outcome": outcome})
        raw = registry.compose(event, _ctx())
        assert raw is not None
        assert raw.kind == "generation_finished"
        assert raw.severity == "info"

    def test_unknown_outcome_is_dropped(self) -> None:
        event = _event(
            EventType.GENERATION_FINISHED, payload={"outcome": "awaiting_manual_fill"}
        )
        assert registry.compose(event, _ctx()) is None

    def test_missing_outcome_is_dropped(self) -> None:
        event = _event(EventType.GENERATION_FINISHED, payload={})
        assert registry.compose(event, _ctx()) is None


@pytest.mark.unit
class TestComposeStoryReady:
    def test_released_names_the_story_and_the_shelf(self) -> None:
        event = _event(EventType.RELEASED, from_state="in_review", to_state="published")
        raw = registry.compose(event, _ctx())
        assert raw is not None
        assert raw.kind == "story_ready"
        assert raw.severity == "info"
        assert raw.title == "The Lighthouse Mystery is ready on the shelf"

    def test_released_falls_back_to_generic_label_without_a_title(self) -> None:
        event = _event(EventType.RELEASED, to_state="published")
        raw = registry.compose(event, _ctx(storybook_title=None))
        assert raw is not None
        assert raw.title == "A story is ready on the shelf"

    def test_book_assigned_names_the_story_and_the_child(self) -> None:
        event = _event(
            EventType.BOOK_ASSIGNED, payload={"child_profile_id": str(_PROFILE)}
        )
        raw = registry.compose(event, _ctx())
        assert raw is not None
        assert raw.kind == "story_ready"
        assert raw.severity == "info"
        assert raw.title == "The Lighthouse Mystery is ready on Maya's shelf"


@pytest.mark.unit
class TestComposeKidFlagged:
    """Pins the KID_FLAGGED mapping directly (composer, not the registry dict).

    Direct calls exercise the mapping contract regardless of whether
    ``EventType.KID_FLAGGED`` exists at import time in this checkout (see
    ``TestKidFlaggedTolerance`` below for the getattr-based registration
    itself).
    """

    def test_scared_me_reason_is_named_in_the_body(self) -> None:
        event = _event(EventType.KID_FLAGGED, payload={"reason": "scared_me"})
        raw = registry._compose_kid_flagged(event, _ctx())
        assert raw is not None
        assert raw.kind == "kid_flagged"
        assert raw.severity == "alert"
        assert "scared them" in raw.body

    def test_confusing_reason_is_named_in_the_body(self) -> None:
        event = _event(EventType.KID_FLAGGED, payload={"reason": "confusing"})
        raw = registry._compose_kid_flagged(event, _ctx())
        assert raw is not None
        assert "confusing" in raw.body

    def test_unrecognized_reason_falls_back_to_generic_clause(self) -> None:
        event = _event(EventType.KID_FLAGGED, payload={"reason": "a-future-reason"})
        raw = registry._compose_kid_flagged(event, _ctx())
        assert raw is not None
        assert "flagged this story" in raw.body

    def test_title_names_the_child(self) -> None:
        event = _event(EventType.KID_FLAGGED, payload={"reason": "did_not_like"})
        raw = registry._compose_kid_flagged(event, _ctx())
        assert raw is not None
        assert raw.title == "Maya flagged a story"


@pytest.mark.unit
class TestKidFlaggedTolerance:
    """Pins the tolerant getattr-based registration described in the module docstring.

    ``registry.py`` builds ``_KID_FLAGGED`` via
    ``getattr(EventType, "KID_FLAGGED", None)`` at import time specifically so
    that importing this module never raises whether or not that enum member
    exists yet. This checkout already has the member (the sibling K15
    workstream landed it), so the "absent" branch cannot be exercised against
    the real ``EventType`` without monkeypatching the enum itself (StrEnum
    members are not removable at runtime); the getattr-with-default call is
    the actual safety mechanism and is a one-line, self-evidently total
    Python builtin (it never raises for a missing attribute when a default is
    given), so the meaningful, non-tautological assertion left to pin is that
    the present-day registration this mechanism was built for actually
    happened.
    """

    def test_reload_succeeds_regardless_of_kid_flagged_presence(self) -> None:
        # A smoke check that the getattr guard keeps module import total: if a
        # future refactor replaced it with a bare ``EventType.KID_FLAGGED``
        # access, THIS reload would start raising the moment that member is
        # ever removed or renamed, even though nothing else in this file
        # would catch it.
        import importlib

        reloaded = importlib.reload(registry)
        assert reloaded is registry

    def test_kid_flagged_registers_when_the_enum_member_exists_at_runtime(self) -> None:
        # As of this slice, the sibling K15 workstream has already landed
        # EventType.KID_FLAGGED, so the tolerant getattr lookup should have
        # picked it up; this pins that the registration actually happened,
        # not just that it didn't crash.
        kid_flagged = getattr(EventType, "KID_FLAGGED", None)
        if kid_flagged is None:
            pytest.skip("EventType.KID_FLAGGED not present in this checkout")
        assert kid_flagged in registry._COMPOSERS
        assert kid_flagged.value in registry.relevant_event_type_values()


@pytest.mark.unit
def test_relevant_event_type_values_matches_composer_keys() -> None:
    values = registry.relevant_event_type_values()
    assert set(values) == {et.value for et in registry._COMPOSERS}
    # Every mapped kind must be a real EventType member (round-trips cleanly).
    for value in values:
        assert EventType(value).value == value


@pytest.mark.unit
def test_compose_returns_none_for_an_unmapped_event_type() -> None:
    event = _event(EventType.RATED, payload={"value": 5, "is_update": False})
    assert registry.compose(event, _ctx()) is None


@pytest.mark.unit
def test_compose_returns_none_for_a_corrupt_event_type_string() -> None:
    event = PipelineEvent(
        id=uuid.uuid4(),
        actor_id=None,
        actor_role="system",
        entity_type="storybook",
        entity_id="some-id",
        event_type="not-a-real-event-type",
        payload={},
    )
    assert registry.compose(event, _ctx()) is None
