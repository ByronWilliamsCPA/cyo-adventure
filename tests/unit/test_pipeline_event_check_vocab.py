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

from cyo_adventure.api.deps import Role
from cyo_adventure.db.models import (
    _PIPELINE_ACTOR_ROLE_VALUES,
    _PIPELINE_EVENT_TYPE_VALUES,
)
from cyo_adventure.events.models import SYSTEM_ACTOR_ROLE, EventType


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
