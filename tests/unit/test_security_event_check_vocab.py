"""Guard against security_event CHECK-constraint vocabulary drift (OPS-005).

Mirrors tests/unit/test_pipeline_event_check_vocab.py's approach for
pipeline_event's event_type CHECK, adapted for security_event: there is no
Python enum source of truth here (only three fixed literal event names, used
directly at both call sites -- app.py::_handle_project_error and
middleware/security.py::RateLimitMiddleware -- and in
db/models.py::_SECURITY_EVENT_TYPE_VALUES), so this test pins the literal set
itself rather than deriving it from an enum, then confirms the creating
migration's CHECK constraint carries the same vocabulary.
"""

from __future__ import annotations

import re
from pathlib import Path

from cyo_adventure.db.models import _SECURITY_EVENT_TYPE_VALUES

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
_EVENT_TYPE_CHECK_CONSTRAINT = "ck_security_event_event_type"

_EXPECTED_EVENT_TYPES = {
    "security_auth_failed",
    "security_authz_denied",
    "security_rate_limit_exceeded",
}


def _parse_sql_string_list(fragment: str) -> set[str]:
    """Parse a `'a', 'b', 'c'` SQL literal fragment into a set of strings."""
    return set(re.findall(r"'([^']*)'", fragment))


def _newest_event_type_check_migration() -> Path:
    """Locate the last-sorting migration that defines the event_type CHECK.

    Only one migration defines this constraint today (the table's creation);
    resolved dynamically anyway, matching test_pipeline_event_check_vocab.py's
    rationale, so a future migration that replaces the constraint wholesale
    is picked up automatically rather than silently guarding a stale file.
    """
    candidates = sorted(
        path
        for path in _MIGRATIONS_DIR.glob("*.sql")
        if _EVENT_TYPE_CHECK_CONSTRAINT in path.read_text(encoding="utf-8")
    )
    if not candidates:
        message = (
            f"no migration under {_MIGRATIONS_DIR} defines "
            f"{_EVENT_TYPE_CHECK_CONSTRAINT}"
        )
        raise AssertionError(message)
    return candidates[-1]


def test_security_event_type_values_matches_expected_vocabulary() -> None:
    """db/models.py's hand-maintained CHECK fragment carries exactly the three
    structlog event names this feature emits, no more and no less.
    """
    assert _parse_sql_string_list(_SECURITY_EVENT_TYPE_VALUES) == _EXPECTED_EVENT_TYPES


def test_newest_event_type_check_migration_carries_exactly_the_expected_vocab() -> None:
    """The migration's CHECK constraint carries exactly the expected event types.

    Parsed from the migration text rather than from
    db/models.py::_SECURITY_EVENT_TYPE_VALUES (the separate hand-maintained
    mirror asserted above), so this proves the migration itself, not just
    the ORM's parallel constant, carries the vocabulary the application
    layer considers valid.

    Scoped to the CHECK constraint's own ``ARRAY[...]`` fragment, not the
    whole file: unlike pipeline_event's migrations (which touch nothing but
    the CHECK constraint), this one also defines the append-only trigger
    function, whose ``RAISE EXCEPTION 'security_event is append-only: ...'``
    message is itself a single-quoted string literal. Parsing the whole file
    would fold that message into the parsed set and make an exact-equality
    assertion permanently fail on a string that was never part of the
    vocabulary; pipeline_event's sibling test can compare its parse against
    the whole file with ``<=`` (subset, since its own vocabulary only grows
    over time via new migrations) precisely because it never has this
    collision. This table's vocabulary is fixed at three values, so an exact
    match here is both correct and achievable.

    # #EDGE: data-integrity: this project's SQL migration header comments are
    # prose and routinely contain apostrophes; --comment lines are stripped
    # before parsing so an apostrophe in a comment is never mistaken for a
    # string-literal delimiter in the executable DDL below it (mirrors
    # test_pipeline_event_check_vocab.py's identical guard).
    """
    sql = _newest_event_type_check_migration().read_text(encoding="utf-8")
    ddl = "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )
    array_match = re.search(r"ARRAY\[(.*?)\]", ddl, re.DOTALL)
    assert array_match is not None, "no ARRAY[...] literal found in the migration"
    parsed = _parse_sql_string_list(array_match.group(1))
    assert parsed == _EXPECTED_EVENT_TYPES
