"""Guard against pipeline_event CHECK-constraint vocabulary drift.

``db/models.py`` hand-maintains the ``event_type``/``actor_role`` CHECK
constraint literals as plain SQL fragments (``_PIPELINE_EVENT_TYPE_VALUES``,
``_PIPELINE_ACTOR_ROLE_VALUES``) instead of deriving them from
``events.models.EventType``/``api.deps.Role``, because importing either
enum's module from ``db/models.py`` would create a circular import (see the
comment above ``_PIPELINE_EVENT_TYPE_VALUES``). These tests close the gap
from the other side: parse the literal SQL fragment and assert it still
matches its enum source of truth, so an enum addition that forgets to update
the hand-maintained CHECK list fails loudly here instead of silently letting
the database reject a value the application layer considers valid.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cyo_adventure.api.deps import Role
from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.db.models import (
    _PIPELINE_ACTOR_ROLE_VALUES,
    _PIPELINE_EVENT_TYPE_VALUES,
)
from cyo_adventure.events.models import SYSTEM_ACTOR_ROLE, EventType
from cyo_adventure.events.writer import _validate_payload

# ADR-023 P3/P4 (Task B4): the CHECK-vocab migration that adds
# personalization_toggled/ring2_consent_granted/ring2_consent_revoked to
# pipeline_event.event_type, following the wholesale-replace pattern (see
# 20260727000000_add_book_unassigned_to_pipeline_event.sql's header). Parsed
# directly from the migration text rather than via
# cyo_adventure.db.models._PIPELINE_EVENT_TYPE_VALUES (a separate
# hand-maintained mirror asserted against above), so this test proves the
# migration itself, not just the ORM's parallel constant, carries the new
# vocabulary.
_PERSONALIZATION_EVENT_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260729020000_add_personalization_event_types.sql"
)


def _parse_sql_string_list(fragment: str) -> set[str]:
    """Parse a `'a', 'b', 'c'` SQL literal fragment into a set of strings."""
    return set(re.findall(r"'([^']*)'", fragment))


def test_pipeline_event_type_check_matches_event_type_enum() -> None:
    """The event_type CHECK vocabulary equals EventType's value set exactly."""
    assert _parse_sql_string_list(_PIPELINE_EVENT_TYPE_VALUES) == {
        e.value for e in EventType
    }


def test_pipeline_actor_role_check_matches_role_sources() -> None:
    """The actor_role CHECK vocabulary equals system + every api.deps.Role value.

    ``SYSTEM_ACTOR_ROLE`` (events/models.py) covers the worker/moderation
    system actor; ``Role`` (api/deps.py) covers every authenticated principal
    role. Together they are the CHECK constraint's full source of truth.
    """
    assert _parse_sql_string_list(_PIPELINE_ACTOR_ROLE_VALUES) == {
        SYSTEM_ACTOR_ROLE,
        *(r.value for r in Role),
    }


# entity_type is intentionally NOT guarded here: the pipeline_event
# entity_type vocabulary (story_request, generation_job, storybook,
# storybook_version, series, storybook_assignment, rating,
# moderation_threshold, moderation_setting) has no single enum source of
# truth anywhere in the codebase; every call site in events/writer.py's
# callers passes its own ad hoc literal string for the entity it just wrote.
# Asserting drift-freedom would mean inventing a parallel enum solely to
# satisfy this test, which is more machinery than the hand-maintained list it
# would guard, so this gap is accepted rather than worked around.


def test_personalization_event_types_migration_carries_full_vocab() -> None:
    """The Task B4 migration's event_type CHECK carries every current EventType value.

    Reads the migration file directly (see the module comment on
    ``_PERSONALIZATION_EVENT_MIGRATION``): before the migration exists this
    fails on the missing file, and once it lands with the wholesale-replace
    pattern, the parsed CHECK vocabulary is a superset of (in practice,
    given the wholesale-replace pattern, exactly) every EventType value,
    including the three ADR-023 additions.

    # #EDGE: data-integrity: this project's SQL migration header comments are
    # prose and routinely contain apostrophes (e.g. "file's"); ``--``-comment
    # lines are stripped before parsing so an apostrophe in a comment is never
    # mistaken for a string-literal delimiter in the executable DDL below it.
    # #VERIFY: this test would fail loudly (extra/missing entries) if a
    # comment apostrophe ever leaked into the parsed vocabulary.
    """
    sql = _PERSONALIZATION_EVENT_MIGRATION.read_text(encoding="utf-8")
    ddl = "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )
    parsed = _parse_sql_string_list(ddl)
    assert {e.value for e in EventType} <= parsed


def test_personalization_toggled_rejects_value_bearing_key() -> None:
    """The allowlist carries keys only, never values (writer.py:14-16).

    A key that would carry an actual personalization value (e.g. a child's
    pet name) must be rejected outright as a disallowed key for
    PERSONALIZATION_TOGGLED, not merely have its value bounded: the house
    contract is enforced at the key layer, before any value-level check runs.
    """
    with pytest.raises(ValidationError, match="disallowed keys"):
        _validate_payload(EventType.PERSONALIZATION_TOGGLED, {"pet_name": "Rex"})
