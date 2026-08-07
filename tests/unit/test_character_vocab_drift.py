"""Guard against ADR-028 character vocabulary drift.

``supabase/migrations/<...>_add_persistent_characters.sql`` and
``db/models.py`` (``Character``, ``CharacterAttribute``) both hand-maintain
three closed vocabularies as plain SQL literal fragments rather than
deriving them from ``storybook.character_vocabulary`` (the application-layer
source of truth): ``character.archetype``, ``character.look``, and
``character_attribute.name``. This mirrors the established pattern in
``tests/unit/test_personalization_vocab_drift.py``: parse each literal SQL
fragment and assert it still matches its source of truth, so a vocabulary
change that forgets to update a hand-maintained CHECK list fails loudly here
instead of silently letting the database reject (or wrongly accept) a value
the application layer considers valid.

The migration side is resolved dynamically (the newest migration that
defines each CHECK), not hardcoded to the introducing migration, mirroring
``test_personalization_vocab_drift.py``'s own
``_newest_slot_type_check_migration``: today only one migration defines
these three CHECKs, but a future migration that widens or splits one of
them should be the one this module reads, not this one.

``character.look`` has no Python-layer source of truth (the twelve avatar
ids are a frontend asset-naming convention, not a domain vocabulary), so its
two tests compare the migration and the ORM directly against each other
rather than against a third store.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint

from cyo_adventure.db.models import Character, CharacterAttribute
from cyo_adventure.storybook.character_vocabulary import (
    ARCHETYPE_ROSTER,
    CANONICAL_CHARACTER_VARIABLES,
)

if TYPE_CHECKING:
    from cyo_adventure.core.database import Base

_MIGRATIONS_DIR = Path(__file__).parents[2] / "supabase" / "migrations"

# The twelve selectable avatar look ids, mirrored from the same hand-authored
# list in db/models.py::_CHARACTER_LOOK_IDS. There is no application-layer
# source of truth to derive this from (unlike archetype and attribute names,
# which come from storybook.character_vocabulary): avatar ids are a frontend
# asset-naming convention. Kept here so the look CHECK still has a drift
# guard between the migration and the ORM, even without a third store.
_AVATAR_LOOK_IDS = frozenset(f"avatar_{i:02d}" for i in range(1, 13))


def _executable_ddl(path: Path) -> str:
    """Return a migration's text with its ``--`` comment lines removed.

    #EDGE: data-integrity: this project's SQL migration header comments are
    prose and can quote the very DDL they describe. Both the migration
    SELECTOR and the list PARSER below must therefore agree that only
    executable DDL counts; a selector that matched on raw text could
    nominate a comment-only migration as "the newest one defining the
    CHECK", and the parser would then fail with "found 0 occurrences",
    pointing at a nonexistent DDL defect instead of at the selector. Mirrors
    ``test_personalization_vocab_drift.py``'s identical helper.

    Args:
        path: The migration file to read.

    Returns:
        str: The file's lines with every ``--`` comment line dropped.
    """
    raw = path.read_text(encoding="utf-8")
    return "\n".join(
        line for line in raw.splitlines() if not line.strip().startswith("--")
    )


def _newest_migration_defining(literal: str) -> Path:
    """Locate the last-sorting migration whose executable DDL contains a literal.

    Migration filenames are timestamp-prefixed, so lexicographic order is
    chronological order. Resolved dynamically rather than hardcoded, for the
    same reason as ``test_personalization_vocab_drift.py``'s twin helper: a
    hardcoded filename silently starts guarding a superseded migration the
    moment a newer one replaces the CHECK wholesale.

    Args:
        literal: A raw text fragment (e.g. ``"archetype IN ("``) expected to
            appear in the migration's executable DDL.

    Returns:
        Path: The newest migration whose executable DDL contains ``literal``.

    Raises:
        AssertionError: If no migration contains the fragment at all.
    """
    candidates = sorted(
        path
        for path in _MIGRATIONS_DIR.glob("*.sql")
        if literal in _executable_ddl(path)
    )
    if not candidates:
        message = f"no migration under {_MIGRATIONS_DIR} contains {literal!r}"
        raise AssertionError(message)
    return candidates[-1]


def _parse_sql_string_list(fragment: str) -> set[str]:
    """Parse a `'a', 'b', 'c'` SQL literal fragment into a set of strings."""
    return set(re.findall(r"'([^']*)'", fragment))


# The two clause shapes `ck_character_attribute_value_range` mixes: a single
# name compared with `=` (archetype) and several names compared with `IN`
# (the three stats). Each clause pairs its name(s) with one
# `value_int BETWEEN <low> AND <high>` bound.
_NAME_EQ_RANGE_RE = re.compile(
    r"name\s*=\s*'([^']*)'\s*AND\s*value_int\s*BETWEEN\s*(\d+)\s*AND\s*(\d+)"
)
_NAME_IN_RANGE_RE = re.compile(
    r"name\s+IN\s*\(([^)]*)\)\s*AND\s*value_int\s*BETWEEN\s*(\d+)\s*AND\s*(\d+)"
)


def _parse_value_range_clauses(fragment: str) -> dict[str, tuple[int, int]]:
    """Parse a `(name = 'x' AND value_int BETWEEN a AND b) OR (...)` fragment.

    ``ck_character_attribute_value_range`` hand-types its numeric bounds
    (I-2): a name-set drift guard alone would let a widened archetype
    roster pass the vocabulary test above while the database still rejects
    the new archetype's code at write time with a CHECK violation. This
    parses both clause shapes (a single name behind `=`, several names
    behind `IN (...)`) into one mapping so the bounds can be compared
    against ``CANONICAL_CHARACTER_VARIABLES`` directly.

    Args:
        fragment: The CHECK constraint's SQL text (ORM ``sqltext`` or a
            migration excerpt covering the full constraint body).

    Returns:
        dict[str, tuple[int, int]]: Each attribute name mapped to its
        ``(inclusive low, inclusive high)`` bound.
    """
    bounds: dict[str, tuple[int, int]] = {}
    for name, low, high in _NAME_EQ_RANGE_RE.findall(fragment):
        bounds[name] = (int(low), int(high))
    for names_fragment, low, high in _NAME_IN_RANGE_RE.findall(fragment):
        for name in _parse_sql_string_list(names_fragment):
            bounds[name] = (int(low), int(high))
    return bounds


def _expected_attribute_value_bounds() -> dict[str, tuple[int, int]]:
    """The per-name (min, max) bounds `CANONICAL_CHARACTER_VARIABLES` declares.

    archetype's max is ``len(ARCHETYPE_ROSTER)``, derived rather than
    hand-typed (see ``storybook.character_vocabulary``), so this stays
    correct if the roster ever grows.
    """
    return {
        name: (variable.min, variable.max)
        for name, variable in CANONICAL_CHARACTER_VARIABLES.items()
    }


def _migration_value_range_bounds(path: Path) -> dict[str, tuple[int, int]]:
    """Extract ``ck_character_attribute_value_range``'s bounds from a migration.

    The constraint body mixes several parenthesized clauses, so (unlike
    ``_migration_check_list``'s single ``IN (...)`` capture) this slices out
    the whole statement housing the anchor, up to the next statement
    terminator, and hands that window to ``_parse_value_range_clauses``.

    Args:
        path: The migration file to parse.

    Returns:
        dict[str, tuple[int, int]]: Each attribute name mapped to its
        ``(inclusive low, inclusive high)`` bound.

    Raises:
        AssertionError: If the anchor does not appear exactly once in the
            migration's executable DDL.
    """
    ddl = _executable_ddl(path)
    anchor = "ck_character_attribute_value_range"
    assert ddl.count(anchor) == 1, (
        f"expected exactly 1 occurrence of {anchor!r} in {path.name}, "
        f"found {ddl.count(anchor)}"
    )
    start = ddl.index(anchor)
    end = ddl.index(";", start)
    return _parse_value_range_clauses(ddl[start:end])


def _migration_check_list(anchor: str, column: str, path: Path) -> set[str]:
    """Extract a migration's ``<column> IN (...)`` literal list near an anchor.

    ``character_attribute``'s ``name`` column appears in two CHECK bodies:
    ``ck_character_attribute_name`` (the full canonical list, what this
    module verifies) and ``ck_character_attribute_value_range`` (a
    per-name-range predicate that reuses two of those same names). A bare
    ``name IN (`` selector would match both, ambiguously; anchoring on the
    enclosing constraint name (mirroring how ``_orm_check_sqltext`` already
    keys off a constraint name on the ORM side) picks the one this test
    means. ``archetype`` and ``look`` have no such second occurrence, so
    their own constraint name is redundant but still passed for uniformity.

    Args:
        anchor: A literal substring, normally the enclosing constraint's
            name, expected to immediately precede ``<column> IN (...)`` in
            the DDL.
        column: The bare column name preceding ``IN (...)`` in the DDL.
        path: The migration file to parse.

    Returns:
        set[str]: The literal values inside the matched ``IN (...)``.

    Raises:
        AssertionError: If the anchored ``IN (...)`` pattern does not appear
            exactly once in the migration's executable DDL.
    """
    ddl = _executable_ddl(path)
    pattern = rf"{re.escape(anchor)}.*?\b{re.escape(column)} IN \(([^)]*)\)"
    occurrences = re.findall(pattern, ddl, flags=re.DOTALL)
    assert len(occurrences) == 1, (
        f"expected exactly 1 {anchor!r}-anchored '{column} IN (...)' "
        f"occurrence in {path.name}, found {len(occurrences)}"
    )
    return _parse_sql_string_list(occurrences[0])


def _orm_check_sqltext(model: type[Base], name: str) -> str:
    """Return the literal SQL text of a named CheckConstraint in __table_args__.

    Args:
        model: The ORM class whose ``__table_args__`` to search.
        name: The constraint's ``name`` as declared in ``__table_args__``.

    Returns:
        str: The constraint's ``sqltext``, stringified.

    Raises:
        AssertionError: If no CheckConstraint with that name is found.
    """
    for constraint in model.__table_args__:  # type: ignore[attr-defined]
        if isinstance(constraint, CheckConstraint) and constraint.name == name:
            return str(constraint.sqltext)
    msg = f"no CheckConstraint named {name!r} in {model.__name__}"
    raise AssertionError(msg)


def test_migration_archetype_check_matches_archetype_roster() -> None:
    """The migration's character.archetype CHECK equals ARCHETYPE_ROSTER."""
    migration = _newest_migration_defining("archetype IN (")
    assert _migration_check_list(
        "ck_character_archetype", "archetype", migration
    ) == set(ARCHETYPE_ROSTER)


def test_orm_archetype_check_matches_archetype_roster() -> None:
    """The ORM's ck_character_archetype CHECK equals ARCHETYPE_ROSTER."""
    sqltext = _orm_check_sqltext(Character, "ck_character_archetype")
    assert _parse_sql_string_list(sqltext) == set(ARCHETYPE_ROSTER)


def test_migration_attribute_name_check_matches_canonical_variables() -> None:
    """The migration's character_attribute.name CHECK equals the canonical variable keys."""
    migration = _newest_migration_defining("ck_character_attribute_name")
    assert _migration_check_list(
        "ck_character_attribute_name", "name", migration
    ) == set(CANONICAL_CHARACTER_VARIABLES)


def test_orm_attribute_name_check_matches_canonical_variables() -> None:
    """The ORM's ck_character_attribute_name CHECK equals the canonical variable keys."""
    sqltext = _orm_check_sqltext(CharacterAttribute, "ck_character_attribute_name")
    assert _parse_sql_string_list(sqltext) == set(CANONICAL_CHARACTER_VARIABLES)


def test_migration_look_check_matches_avatar_ids() -> None:
    """The migration's character.look CHECK equals the twelve avatar ids."""
    migration = _newest_migration_defining("look IN (")
    assert (
        _migration_check_list("ck_character_look", "look", migration)
        == _AVATAR_LOOK_IDS
    )


def test_orm_look_check_matches_avatar_ids() -> None:
    """The ORM's ck_character_look CHECK equals the twelve avatar ids."""
    sqltext = _orm_check_sqltext(Character, "ck_character_look")
    assert _parse_sql_string_list(sqltext) == _AVATAR_LOOK_IDS


def test_migration_attribute_value_range_matches_canonical_bounds() -> None:
    """The migration's numeric CHECK bounds equal CANONICAL_CHARACTER_VARIABLES.

    I-2: the tests above only guard the attribute NAME set; a widened
    archetype roster could pass those while this hand-typed numeric range
    still rejects the new code at write time. Deriving the expected bounds
    from ``CANONICAL_CHARACTER_VARIABLES`` (whose archetype max is
    ``len(ARCHETYPE_ROSTER)``) closes that gap.
    """
    migration = _newest_migration_defining("ck_character_attribute_value_range")
    assert (
        _migration_value_range_bounds(migration) == _expected_attribute_value_bounds()
    )


def test_orm_attribute_value_range_matches_canonical_bounds() -> None:
    """The ORM's numeric CHECK bounds equal CANONICAL_CHARACTER_VARIABLES.

    The ORM-side counterpart to the migration test above; see its docstring
    for the failure this closes.
    """
    sqltext = _orm_check_sqltext(
        CharacterAttribute, "ck_character_attribute_value_range"
    )
    assert _parse_value_range_clauses(sqltext) == _expected_attribute_value_bounds()
