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


def test_validate_payload_rejects_unknown_key() -> None:
    with pytest.raises(ValidationError, match="disallowed keys"):
        _validate_payload(EventType.RATED, {"value": 5, "child_name": "Ada"})


def test_validate_payload_accepts_allowlisted_keys() -> None:
    _validate_payload(EventType.RATED, {"value": 5, "is_update": True})


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
