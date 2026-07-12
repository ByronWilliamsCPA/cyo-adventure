"""Unit tests for the child-user provisioning conflict discriminator (G1 / P6-04).

Covers ``db.integrity.is_authn_subject_conflict``: the pure predicate that
decides whether an ``IntegrityError`` from the JIT child-user insert is the
benign double-mint race (a unique violation on ``ix_user_authn_subject``,
which the caller recovers from) or a real error (FK/CHECK, which must
propagate). The endpoint's DB-backed
race recovery is covered in tests/integration/test_child_sessions.py; these
cases pin the driver-aware SQLSTATE + constraint-name logic without a database.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from cyo_adventure.db.integrity import is_authn_subject_conflict

pytestmark = [pytest.mark.security]


class _FakeOrigError(Exception):
    """Stand-in for a DBAPI error with driver-reported diagnostic fields.

    asyncpg exposes ``sqlstate`` and ``constraint_name``; psycopg exposes
    ``pgcode``. Each attribute is optional so tests can model a driver that
    surfaces none of them and force the message-text fallback.
    """

    def __init__(
        self,
        message: str,
        *,
        sqlstate: str | None = None,
        pgcode: str | None = None,
        constraint_name: str | None = None,
    ) -> None:
        super().__init__(message)
        if sqlstate is not None:
            self.sqlstate = sqlstate
        if pgcode is not None:
            self.pgcode = pgcode
        if constraint_name is not None:
            self.constraint_name = constraint_name


def _integrity_error(orig: _FakeOrigError) -> IntegrityError:
    return IntegrityError("INSERT INTO ...", None, orig)


@pytest.mark.unit
def test_unique_violation_on_authn_subject_index_is_conflict() -> None:
    """23505 on the authn_subject index is the benign double-mint race."""
    orig = _FakeOrigError(
        'duplicate key value violates unique constraint "ix_user_authn_subject"',
        sqlstate="23505",
        constraint_name="ix_user_authn_subject",
    )
    assert is_authn_subject_conflict(_integrity_error(orig)) is True


@pytest.mark.unit
def test_unique_violation_on_other_index_is_not_conflict() -> None:
    """A unique violation on a different index must propagate, not recover."""
    orig = _FakeOrigError(
        'duplicate key value violates unique constraint "ix_user_email"',
        sqlstate="23505",
        constraint_name="ix_user_email",
    )
    assert is_authn_subject_conflict(_integrity_error(orig)) is False


@pytest.mark.unit
def test_foreign_key_violation_is_not_conflict() -> None:
    """A 23503 FK violation is a real error even if it mentions authn_subject."""
    orig = _FakeOrigError(
        "insert or update on table violates foreign key; see authn_subject",
        sqlstate="23503",
        constraint_name="fk_user_family",
    )
    assert is_authn_subject_conflict(_integrity_error(orig)) is False


@pytest.mark.unit
def test_message_text_fallback_when_constraint_name_absent() -> None:
    """When the driver omits the constraint, fall back to the message text."""
    orig = _FakeOrigError(
        'duplicate key value violates unique constraint "ix_user_authn_subject"',
        sqlstate="23505",
    )
    assert is_authn_subject_conflict(_integrity_error(orig)) is True


@pytest.mark.unit
def test_psycopg_pgcode_is_honored() -> None:
    """psycopg-style pgcode is used when sqlstate is not present."""
    orig = _FakeOrigError(
        'duplicate key value violates unique constraint "ix_user_authn_subject"',
        pgcode="23505",
        constraint_name="ix_user_authn_subject",
    )
    assert is_authn_subject_conflict(_integrity_error(orig)) is True


@pytest.mark.unit
def test_no_sqlstate_uses_message_text_superset() -> None:
    """With no SQLSTATE at all, behavior stays a superset of the old text match."""
    orig = _FakeOrigError(
        'duplicate key value violates unique constraint "ix_user_authn_subject"'
    )
    assert is_authn_subject_conflict(_integrity_error(orig)) is True
