"""Shared classification of database integrity errors.

Home for predicates that decide whether an ``IntegrityError`` is a specific,
recoverable conflict (a lost provisioning race on a unique index) rather than
a real fault that must propagate. Used by the child-account double-mint
recovery (``api/child_sessions.py``) and the guardian first-login race
recovery (``api/onboarding.py``); keep the classification here so the two
paths can never drift apart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.exc import IntegrityError


def is_authn_subject_conflict(exc: IntegrityError) -> bool:
    """Return True only for a unique violation on the ``authn_subject`` index.

    A provisioning race (child double-mint, guardian first login) is benign
    only when the failure is a duplicate-key conflict on
    ``ix_user_authn_subject``; an FK or CHECK violation is a real error a
    retry cannot fix and must propagate. A bare ``"authn_subject" in
    str(exc.orig)`` match is brittle: it silently reclassifies an unrelated
    error whose text happens to mention the column, and it breaks if the
    message format changes. Prefer the driver-reported SQLSTATE 23505
    (``unique_violation``) plus the constraint/index name, and fall back to
    the message text only when the driver does not surface either, so
    behaviour stays a strict superset of the old check.

    Args:
        exc: The ``IntegrityError`` raised by the savepoint flush.

    Returns:
        bool: True when the error is the ``authn_subject`` unique conflict.
    """
    orig = exc.orig
    # asyncpg exposes ``sqlstate``; psycopg exposes ``pgcode``. 23505 is
    # unique_violation. Anything else is not a benign provisioning race.
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate is not None and sqlstate != "23505":
        return False
    constraint = getattr(orig, "constraint_name", None)
    if constraint:
        return "authn_subject" in constraint
    # Driver did not surface the constraint name; fall back to message text.
    return "authn_subject" in str(orig)
