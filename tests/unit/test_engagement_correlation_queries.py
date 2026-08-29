"""ADR-030 Decision 4: the read allowlist, checked against the compiled SQL.

The oracle here is the SQL each statement compiles to, not the Python that
builds it. A test that asserted over the ORM expression tree would keep passing
if a statement acquired a denied column through a relationship load or a
``selectinload``, because the column never appears as a written attribute in
that case. It does appear in the SQL.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

import pytest
from sqlalchemy.dialects import postgresql

from cyo_adventure.analysis.queries import (
    ALL_STATEMENTS,
    DENIED_COLUMNS,
    READ_ALLOWLIST,
    completion_families_statement,
    flag_families_statement,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy import Select

pytestmark = pytest.mark.unit

# ``table.column`` as SQLAlchemy renders it for PostgreSQL, unquoted.
_QUALIFIED: Final = re.compile(r"\b([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b")


def _compiled(statement: Select[tuple[object, ...]]) -> str:
    """Return the PostgreSQL text one statement compiles to.

    Args:
        statement: The statement to compile.

    Returns:
        str: The SQL, with literals bound so no column hides in a parameter.
    """
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def _referenced_pairs(sql: str) -> set[tuple[str, str]]:
    """Return every ``(table, column)`` pair the SQL text names.

    Args:
        sql: Compiled SQL.

    Returns:
        set[tuple[str, str]]: The qualified references.
    """
    return {(match.group(1), match.group(2)) for match in _QUALIFIED.finditer(sql)}


def _all_pairs() -> set[tuple[str, str]]:
    """Return every qualified reference across every statement the job issues.

    Returns:
        set[tuple[str, str]]: The union over all statements.
    """
    pairs: set[tuple[str, str]] = set()
    for builder in ALL_STATEMENTS:
        pairs |= _referenced_pairs(_compiled(builder()))
    return pairs


class TestReadAllowlist:
    """The job may read these columns and no others."""

    def test_the_statement_set_is_not_empty(self) -> None:
        """A vacuous suite is the failure mode every check below shares.

        Every other test in this class quantifies over ``ALL_STATEMENTS``, so
        an empty tuple would make all of them pass while the job read whatever
        it liked.
        """
        assert len(ALL_STATEMENTS) == 6
        for builder in ALL_STATEMENTS:
            assert _referenced_pairs(_compiled(builder()))

    @pytest.mark.parametrize("builder", ALL_STATEMENTS)
    def test_every_statement_selects_only_allowlisted_columns(
        self, builder: Callable[[], Select[tuple[object, ...]]]
    ) -> None:
        """Closed by default: a column absent from the ADR's table is a failure.

        Asserted as a subset relation against the allowlist rather than as a
        disjointness relation against a denied list, so a column added to one of
        these tables tomorrow is denied without anyone remembering to deny it.
        """
        sql = _compiled(builder())
        for table, column in _referenced_pairs(sql):
            assert table in READ_ALLOWLIST, f"{table} is not a readable table"
            assert column in READ_ALLOWLIST[table], f"{table}.{column} is not allowed"

    def test_no_denied_column_appears_in_any_compiled_statement(self) -> None:
        """The named denials, checked by name as well as by the subset rule.

        Redundant with the test above by construction, and kept because the two
        fail differently: this one names the column in its failure message, and
        it still fires if a column is added to the allowlist by mistake.
        """
        offenders = {
            f"{table}.{column}"
            for table, column in _all_pairs()
            if column in DENIED_COLUMNS
        }
        assert offenders == set()

    def test_node_id_is_denied_and_is_absent_from_the_sql_text(self) -> None:
        """ADR-030 Decision 5's hard rule, at the earliest point it can be broken.

        Checked as a substring of the SQL, not as a parsed pair, so an unqualified
        or aliased reference cannot slip past the pair extractor.
        """
        assert "node_id" in DENIED_COLUMNS
        for builder in ALL_STATEMENTS:
            assert "node_id" not in _compiled(builder())

    def test_the_allowlist_matches_the_adr_decision_four_table(self) -> None:
        """Pins the seven tables and their columns to the ADR's own wording.

        The allowlist is what every other test in this class is measured
        against, so a widened allowlist would silently widen them all.
        """
        expected = {
            "storybook": frozenset(
                {
                    "id",
                    "visibility",
                    "status",
                    "current_published_version",
                    "personalization_subject_profile_id",
                }
            ),
            "storybook_version": frozenset(
                {"storybook_id", "version", "moderation_report"}
            ),
            "child_profile": frozenset({"id", "family_id"}),
            "reading_state": frozenset({"child_profile_id", "storybook_id", "version"}),
            "completion": frozenset(
                {"child_profile_id", "storybook_id", "version", "ending_id", "found_at"}
            ),
            "rating": frozenset({"child_profile_id", "storybook_id", "value"}),
            "kid_flag": frozenset({"storybook_id", "version", "profile_id", "reason"}),
        }
        assert expected == READ_ALLOWLIST

    def test_no_statement_reads_a_table_the_adr_does_not_name(self) -> None:
        """``reading_activity_day``, ``device_download``, ``storybook_assignment``."""
        tables = {table for table, _ in _all_pairs()}
        assert tables <= set(READ_ALLOWLIST)
        assert "reading_activity_day" not in tables
        assert "device_download" not in tables
        assert "storybook_assignment" not in tables

    def test_the_completion_timestamp_is_truncated_inside_the_database(self) -> None:
        """The raw timestamp must never cross the connection.

        Decision 4 admits ``completion.found_at`` "truncated to calendar date".
        Truncating in Python would satisfy the emit rules and still fetch the
        untruncated value, which is the thing the wording forbids.
        """
        sql = _compiled(completion_families_statement())
        assert "CAST(completion.found_at AS DATE)" in sql

    def test_family_grain_comes_from_a_join_and_not_a_denormalised_column(
        self,
    ) -> None:
        """``kid_flag.family_id`` exists; reading it would bypass ``child_profile``.

        Both routes reach the same value today. Only one of them is the route
        Decision 4 allowlisted, and the denormalised column is the one that
        drifts.
        """
        sql = _compiled(flag_families_statement())
        assert "kid_flag.family_id" not in sql
        assert "child_profile.family_id" in sql


class TestStatementsAreReadOnly:
    """A job that cannot write cannot corrupt what it reads."""

    @pytest.mark.parametrize("builder", ALL_STATEMENTS)
    def test_every_statement_is_a_select(
        self, builder: Callable[[], Select[tuple[object, ...]]]
    ) -> None:
        """No INSERT, UPDATE, DELETE, or locking clause anywhere."""
        sql = _compiled(builder()).upper()
        assert sql.startswith("SELECT")
        for verb in ("INSERT", "UPDATE ", "DELETE", "FOR UPDATE", "FOR SHARE"):
            assert verb not in sql
