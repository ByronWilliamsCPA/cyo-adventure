"""At-rest guarantees for ``kws_verification`` (ADR-018).

Two kinds of drift are guarded here, both of which would be invisible until a
row was already wrong in production: a CHECK vocabulary that stops matching the
application's own, and the reappearance of a parent email column.

Mirrors tests/unit/test_security_event_check_vocab.py's approach of parsing the
creating migration's text as well as the ORM's constraints, so the two halves
of the schema are pinned independently rather than one being trusted because
the other passed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

import pytest
from sqlalchemy import CheckConstraint

from cyo_adventure.core.config import Settings
from cyo_adventure.db.models import (
    _KWS_ENVIRONMENT_VALUES,
    _KWS_VERIFICATION_STATUS_VALUES,
    KWS_VERIFICATION_STATUS_FAILED,
    KWS_VERIFICATION_STATUS_SEND_FAILED,
    KWS_VERIFICATION_STATUS_SENT,
    KWS_VERIFICATION_STATUS_VERIFIED,
    KwsVerification,
)

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
_TABLE = "kws_verification"


def _parse_sql_string_list(fragment: str) -> set[str]:
    """Parse a ``'a', 'b', 'c'`` SQL literal fragment into a set of strings."""
    return set(re.findall(r"'([^']*)'", fragment))


def _creating_migration() -> str:
    """Return the DDL of the migration that creates the table, comments stripped.

    Comment lines are dropped before any parsing: this project's migration
    headers are prose and routinely contain apostrophes, which would otherwise
    be read as string-literal delimiters (the same guard
    test_security_event_check_vocab.py documents).
    """
    candidates = sorted(
        path
        for path in _MIGRATIONS_DIR.glob("*.sql")
        if f'CREATE TABLE IF NOT EXISTS "public"."{_TABLE}"' in path.read_text("utf-8")
    )
    assert candidates, f"no migration under {_MIGRATIONS_DIR} creates {_TABLE}"
    sql = candidates[-1].read_text("utf-8")
    return "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )


def _latest_status_check_migration() -> str:
    """Return the DDL of the migration that most recently (re)defines the status CHECK.

    The creating migration is no longer the whole story: the vocabulary was
    widened later, and comparing the ORM against the CREATE TABLE alone would
    have this test insist on the OLD set forever. Comment lines are stripped
    first, for the reason ``_creating_migration`` documents.
    """
    needle = re.compile(r'CONSTRAINT "?ck_kws_verification_status"?\s*\n?\s*CHECK')
    candidates = sorted(
        path
        for path in _MIGRATIONS_DIR.glob("*.sql")
        if needle.search(path.read_text("utf-8"))
    )
    assert candidates, f"no migration under {_MIGRATIONS_DIR} defines the status CHECK"
    sql = candidates[-1].read_text("utf-8")
    return "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )


def _orm_check(name: str) -> str:
    """Return the SQL text of one of the table's named CHECK constraints.

    Args:
        name: The constraint name.

    Returns:
        str: Its SQL expression.
    """
    for constraint in KwsVerification.__table__.constraints:
        if isinstance(constraint, CheckConstraint) and constraint.name == name:
            return str(constraint.sqltext)
    message = f"{_TABLE} has no CHECK constraint named {name}"
    raise AssertionError(message)


@pytest.mark.unit
def test_at_rest_environment_vocabulary_matches_the_setting() -> None:
    """The CHECK and ``Settings.kws_environment`` name the same two environments.

    Hand-maintained in parallel rather than derived, so this is the only thing
    stopping the two from drifting. Drift here is not cosmetic: the column is
    the sole distinction between sandbox noise and evidence about a real
    parent, and a value the CHECK rejects would surface as a failed INSERT on
    the very attempt it was meant to record.
    """
    declared = get_args(Settings.model_fields["kws_environment"].annotation)

    assert _parse_sql_string_list(_KWS_ENVIRONMENT_VALUES) == set(declared)


@pytest.mark.unit
def test_status_and_environment_are_constrained_at_rest() -> None:
    """Both vocabularies are CHECK-constrained in the ORM and the migration.

    A writer-side check alone would leave any other write path (a fixture, a
    manual repair, a future job) free to persist an unreadable record.
    """
    statuses = {
        KWS_VERIFICATION_STATUS_SENT,
        KWS_VERIFICATION_STATUS_VERIFIED,
        KWS_VERIFICATION_STATUS_FAILED,
        KWS_VERIFICATION_STATUS_SEND_FAILED,
    }
    ddl = _creating_migration()

    assert _parse_sql_string_list(_KWS_VERIFICATION_STATUS_VALUES) == statuses
    assert _parse_sql_string_list(_orm_check("ck_kws_verification_status")) == statuses
    assert _parse_sql_string_list(
        _orm_check("ck_kws_verification_environment")
    ) == _parse_sql_string_list(_KWS_ENVIRONMENT_VALUES)
    assert "CONSTRAINT ck_kws_verification_status" in ddl
    assert "CONSTRAINT ck_kws_verification_environment" in ddl
    # The SQL side is checked against whichever migration last defined the
    # constraint, not against CREATE TABLE: a widening that never shipped as a
    # migration would leave the deployed database rejecting a status the
    # application writes, on the one attempt it was recording.
    latest = _latest_status_check_migration()
    status_clause = re.search(
        r"CONSTRAINT \"?ck_kws_verification_status\"?\s*\n?\s*CHECK \(status IN \(([^)]*)\)",
        latest,
    )
    assert status_clause is not None, "the status CHECK's value list was not parseable"
    assert _parse_sql_string_list(status_clause.group(1)) == statuses


@pytest.mark.unit
def test_resolution_pairing_is_constrained_at_rest() -> None:
    """``status = 'sent'`` and ``resolved_at IS NULL`` can never disagree.

    Without it, a "still waiting" filter and a "never resolved" filter would be
    two different questions with two different answers.
    """
    pairing = _orm_check("ck_kws_verification_resolution_pairing")

    assert pairing == "(status = 'sent') = (resolved_at IS NULL)"
    assert "CONSTRAINT ck_kws_verification_resolution_pairing" in _creating_migration()


@pytest.mark.unit
def test_the_table_has_no_email_column() -> None:
    """The parent's address is not a column here, under any spelling.

    Keeping it out of the join is the entire reason the opaque per-attempt
    correlation exists. This is a name-shaped test on purpose: the failure it
    guards against is somebody adding ``parent_email`` (or ``contact``, or
    ``recipient``) as an obvious convenience, and a name check is what catches
    that at review time rather than at a privacy review years later.
    """
    names = {column.name for column in KwsVerification.__table__.columns}

    assert not {name for name in names if "mail" in name or "recipient" in name}
    assert names == {
        "id",
        "user_id",
        "kws_environment",
        "status",
        "requested_at",
        "resolved_at",
        "transaction_id",
        "enabled_methods",
        "location",
    }
