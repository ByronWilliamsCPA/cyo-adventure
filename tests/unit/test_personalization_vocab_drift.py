"""Guard against ADR-023 P4 personalization CHECK-constraint vocabulary drift.

``supabase/migrations/<...>_add_child_profile_personalization.sql`` and
``db/models.py`` (``ChildProfilePersonalization``) both hand-maintain the
``child_profile_personalization.slot_type`` CHECK vocabulary, plus the
narrower ring-2 subset (the "real name only shareable at ring 1" ceiling:
``pronoun_set`` and ``dedication`` are ring-1-only), as plain SQL literal
fragments rather than deriving them from
``storybook.theme_contract.PERSONALIZATION_FIELDS`` (the closed ADR-023
vocabulary for personalizable slots). This mirrors the established pattern in
``tests/unit/test_pipeline_event_check_vocab.py``: parse each literal SQL
fragment and assert it still matches its source of truth, so an enum addition
that forgets to update a hand-maintained CHECK list fails loudly here instead
of silently letting the database reject (or wrongly accept) a value the
application layer considers valid.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import CheckConstraint

from cyo_adventure.db.models import ChildProfilePersonalization
from cyo_adventure.storybook.theme_contract import PERSONALIZATION_FIELDS

_MIGRATIONS_DIR = Path(__file__).parents[2] / "supabase" / "migrations"

# The ring-1-only fields (real-name-adjacent but not itself a real name, or
# structurally incapable of a ring-2 "shared with connected families" grant):
# pronoun_set is a grammatical choice, not an identity a family shares
# outward, and dedication names the book's giver, not its reader.
_RING1_ONLY_FIELDS = frozenset({"pronoun_set", "dedication"})


def _find_migration() -> Path:
    """Locate the ADR-023 P4 personalization migration file.

    Returns:
        Path: The single migration file matching the expected suffix.
    """
    matches = sorted(_MIGRATIONS_DIR.glob("*_add_child_profile_personalization.sql"))
    assert len(matches) == 1, (
        f"expected exactly one add_child_profile_personalization migration, "
        f"found {matches}"
    )
    return matches[0]


def _parse_sql_string_list(fragment: str) -> set[str]:
    """Parse a `'a', 'b', 'c'` SQL literal fragment into a set of strings."""
    return set(re.findall(r"'([^']*)'", fragment))


def _migration_slot_type_lists() -> tuple[set[str], set[str]]:
    """Extract the migration's two `slot_type IN (...)` literal lists.

    Returns:
        tuple[set[str], set[str]]: ``(full_check, ring2_ceiling_check)`` --
        the table's column-level ``slot_type`` CHECK vocabulary, and the
        narrower list guarded by ``ck_cpp_ring2_ceiling``, in the order they
        appear in the file.
    """
    text = _find_migration().read_text(encoding="utf-8")
    occurrences = re.findall(r"slot_type IN \(([^)]*)\)", text)
    assert len(occurrences) == 2, (
        f"expected exactly 2 'slot_type IN (...)' occurrences "
        f"(the column CHECK and ck_cpp_ring2_ceiling), found {len(occurrences)}"
    )
    full_check, ring2_ceiling = occurrences
    return _parse_sql_string_list(full_check), _parse_sql_string_list(ring2_ceiling)


def _orm_check_sqltext(name: str) -> str:
    """Return the literal SQL text of a named CheckConstraint in __table_args__.

    Args:
        name: The constraint's ``name`` as declared in ``__table_args__``.

    Returns:
        str: The constraint's ``sqltext``, stringified.

    Raises:
        AssertionError: If no CheckConstraint with that name is found.
    """
    for constraint in ChildProfilePersonalization.__table_args__:
        if isinstance(constraint, CheckConstraint) and constraint.name == name:
            return str(constraint.sqltext)
    msg = f"no CheckConstraint named {name!r} in ChildProfilePersonalization"
    raise AssertionError(msg)


def test_migration_slot_type_check_matches_personalization_fields() -> None:
    """The migration's full slot_type CHECK vocabulary equals PERSONALIZATION_FIELDS."""
    full_check, _ = _migration_slot_type_lists()
    assert full_check == set(PERSONALIZATION_FIELDS)


def test_migration_ring2_ceiling_check_matches_personalization_fields_minus_ring1_only() -> (
    None
):
    """The ring2 ceiling CHECK equals PERSONALIZATION_FIELDS minus the ring-1-only fields."""
    _, ring2_ceiling = _migration_slot_type_lists()
    assert ring2_ceiling == set(PERSONALIZATION_FIELDS) - _RING1_ONLY_FIELDS


def test_orm_slot_type_check_matches_personalization_fields() -> None:
    """The ORM's ck_cpp_slot_type CHECK equals PERSONALIZATION_FIELDS exactly."""
    sqltext = _orm_check_sqltext("ck_cpp_slot_type")
    assert _parse_sql_string_list(sqltext) == set(PERSONALIZATION_FIELDS)


def test_orm_ring2_ceiling_check_matches_personalization_fields_minus_ring1_only() -> (
    None
):
    """The ORM's ck_cpp_ring2_ceiling CHECK equals PERSONALIZATION_FIELDS minus ring-1-only."""
    sqltext = _orm_check_sqltext("ck_cpp_ring2_ceiling")
    assert _parse_sql_string_list(sqltext) == set(PERSONALIZATION_FIELDS) - (
        _RING1_ONLY_FIELDS
    )


def test_orm_exactly_one_value_constraint_present() -> None:
    """ck_cpp_exactly_one_value exists, mirroring the migration's named CHECK."""
    sqltext = _orm_check_sqltext("ck_cpp_exactly_one_value")
    assert "value_text" in sqltext
    assert "value_enum" in sqltext
    assert "value_profile_id" in sqltext
