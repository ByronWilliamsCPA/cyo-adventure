"""Unit tests for the pipeline-event writer and payload allowlist."""

from __future__ import annotations

import uuid

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.events import Actor, EventType
from cyo_adventure.events.models import SYSTEM_ACTOR_ROLE
from cyo_adventure.events.writer import _PAYLOAD_ALLOWLIST, _validate_payload


def test_every_event_type_has_an_allowlist_entry() -> None:
    assert set(_PAYLOAD_ALLOWLIST) == set(EventType)


@pytest.mark.parametrize("event_type", list(EventType))
def test_validate_payload_rejects_unknown_key_for_every_event_type(
    event_type: EventType,
) -> None:
    # A key absent from every allowlist must be rejected regardless of event type;
    # the allowlist is per-event-type, so a single-type test would miss a regression
    # that loosened one other type's frozenset.
    with pytest.raises(ValidationError, match="disallowed keys"):
        _validate_payload(event_type, {"child_name": "Ada"})


def test_validate_payload_accepts_allowlisted_keys() -> None:
    _validate_payload(EventType.RATED, {"value": 5, "is_update": True})


def test_validate_payload_accepts_moderation_counts_dict() -> None:
    _validate_payload(
        EventType.MODERATION_COMPLETED,
        {"overall_verdict": "block", "repaired": False, "counts": {"block": 1}},
    )


def test_validate_payload_rejects_free_text_value() -> None:
    # An allowlisted key carrying a long free-text value (e.g. story prose routed
    # under threshold_changed.category) must be rejected: D3 enforcement is on the
    # value, not just the key.
    with pytest.raises(ValidationError, match="free text is not permitted"):
        _validate_payload(EventType.THRESHOLD_CHANGED, {"category": "x" * 201})


def test_validate_payload_rejects_non_scalar_value() -> None:
    with pytest.raises(ValidationError, match="not a PII-safe scalar"):
        _validate_payload(EventType.THRESHOLD_CHANGED, {"category": ["a", "b"]})


def test_actor_system_has_no_user_id() -> None:
    actor = Actor.system()
    assert actor.actor_id is None
    assert actor.actor_role == SYSTEM_ACTOR_ROLE


def test_actor_from_principal_copies_id_and_role() -> None:
    uid = uuid.uuid4()

    class _P:
        user_id = uid
        role = "admin"

    actor = Actor.from_principal(_P())
    assert actor.actor_id == uid
    assert actor.actor_role == "admin"


def test_actor_rejects_system_role_with_user_id() -> None:
    # Spec D2: a system actor must not carry a user id (enforced in __post_init__,
    # backstopped by the ck_pipeline_event_system_actor_null DB CHECK).
    with pytest.raises(ValidationError):
        Actor(actor_id=uuid.uuid4(), actor_role=SYSTEM_ACTOR_ROLE)


def test_actor_rejects_user_role_with_null_id() -> None:
    with pytest.raises(ValidationError):
        Actor(actor_id=None, actor_role="guardian")
