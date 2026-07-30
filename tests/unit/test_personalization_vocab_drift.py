"""Guard against ADR-023 P4 personalization vocabulary drift.

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

The migration side is resolved dynamically (the newest migration that
defines a ``slot_type IN (...)`` CHECK), not hardcoded to the original
creation migration, mirroring
``test_pipeline_event_check_vocab.py::_newest_event_type_check_migration``:
Task D6 (``20260730000000_split_favorite_personalization_slot.sql``)
replaces both CHECKs wholesale to split the flat ``favorite`` slot into
``favorite_color``/``favorite_food``/``favorite_hobby``, so only the newest
migration describes the vocabulary the database actually ends up with.

This module also carries the ``CLOSED_VOCABULARIES``-vs-``PERSONALIZATION_
FIELDS`` drift guard from AL-068/UW-C20
(``docs/planning/authoring-lessons-log.md``,
``docs/planning/unscheduled-work-register.md``): AL-068 found that
``dedication`` existed in ``PERSONALIZATION_FIELDS`` with no entry in
``storybook.personalization_values.CLOSED_VOCABULARIES``, which meant
``_shape_violations`` treated it as a free-text slot and let it accept
guardian-authored prose on a kid-facing screen. The tests below fail the same
way the next slot type would fail if it repeated that mistake: added to
``PERSONALIZATION_FIELDS`` with neither a vocabulary entry nor a name in the
explicit free-text/reference exemption set.
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import CheckConstraint

from cyo_adventure.db.models import ChildProfilePersonalization
from cyo_adventure.storybook.personalization_values import (
    CLOSED_VOCABULARIES,
    SIBLING_SLOT_TYPE,
)
from cyo_adventure.storybook.theme_contract import PERSONALIZATION_FIELDS

_MIGRATIONS_DIR = Path(__file__).parents[2] / "supabase" / "migrations"

# The ring-1-only fields (real-name-adjacent but not itself a real name, or
# structurally incapable of a ring-2 "shared with connected families" grant):
# pronoun_set is a grammatical choice, not an identity a family shares
# outward, and dedication names the book's giver, not its reader.
_RING1_ONLY_FIELDS = frozenset({"pronoun_set", "dedication"})

# AL-068/UW-C20: every `PERSONALIZATION_FIELDS` member must resolve to
# EITHER a `CLOSED_VOCABULARIES` entry OR a name in this set, which records
# WHY each one is deliberately free-text/reference-shaped rather than an
# enum: `protagonist_first_name`/`pet_name` are guardian-authored free text
# (a real name), `pronoun_set` is free text with no design-stated shape
# (`personalization_values.py`'s own
# `test_pronoun_set_shape_is_deliberately_unconstrained` pins that), and
# `SIBLING_SLOT_TYPE` (`sibling_name`) is a `value_profile_id` reference, not
# text or an enum, so it was never eligible for `CLOSED_VOCABULARIES` at all.
_FREE_TEXT_OR_REFERENCE_EXEMPT_FIELDS = frozenset(
    {"protagonist_first_name", "pet_name", "pronoun_set", SIBLING_SLOT_TYPE}
)


def _newest_slot_type_check_migration() -> Path:
    """Locate the last-sorting migration that defines a slot_type CHECK.

    Every migration touching the ``child_profile_personalization.slot_type``
    CHECK (the column-level check and ``ck_cpp_ring2_ceiling``) replaces both
    wholesale with an absolute value list, so only the newest one describes
    the vocabulary the database actually ends up with. Migration filenames
    are timestamp-prefixed, so lexicographic order is chronological order.
    Resolved dynamically rather than hardcoded, for the same reason as
    ``test_pipeline_event_check_vocab.py``'s twin helper: a hardcoded
    filename silently starts guarding a superseded migration the moment a
    newer one lands.

    Returns:
        Path: The newest migration defining a ``slot_type IN (...)`` CHECK.

    Raises:
        AssertionError: If no migration defines the constraint at all.
    """
    candidates = sorted(
        path
        for path in _MIGRATIONS_DIR.glob("*.sql")
        if "slot_type IN (" in path.read_text(encoding="utf-8")
    )
    if not candidates:
        message = (
            f"no migration under {_MIGRATIONS_DIR} defines a 'slot_type IN (...)' CHECK"
        )
        raise AssertionError(message)
    return candidates[-1]


def _parse_sql_string_list(fragment: str) -> set[str]:
    """Parse a `'a', 'b', 'c'` SQL literal fragment into a set of strings."""
    return set(re.findall(r"'([^']*)'", fragment))


def _migration_slot_type_lists() -> tuple[set[str], set[str]]:
    """Extract the newest migration's two `slot_type IN (...)` literal lists.

    Returns:
        tuple[set[str], set[str]]: ``(full_check, ring2_ceiling_check)`` --
        the table's column-level ``slot_type`` CHECK vocabulary, and the
        narrower list guarded by ``ck_cpp_ring2_ceiling``, in the order they
        appear in the file.
    """
    # #EDGE: data-integrity: this project's SQL migration header comments are
    # prose and may themselves mention the literal text "slot_type IN (...)"
    # (e.g. explaining why a later migration replaces it); `--`-comment lines
    # are stripped before parsing so a comment's mention is never mistaken
    # for one of the two executable DDL occurrences. Mirrors
    # test_pipeline_event_check_vocab.py's identical guard for apostrophes.
    raw = _newest_slot_type_check_migration().read_text(encoding="utf-8")
    ddl = "\n".join(
        line for line in raw.splitlines() if not line.strip().startswith("--")
    )
    occurrences = re.findall(r"slot_type IN \(([^)]*)\)", ddl)
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


# ---------------------------------------------------------------------------
# AL-068/UW-C20: CLOSED_VOCABULARIES vs PERSONALIZATION_FIELDS drift guard.
# ---------------------------------------------------------------------------


def test_every_personalization_field_has_a_vocabulary_or_an_exemption() -> None:
    """Every PERSONALIZATION_FIELDS member is a vocabulary key or an exemption.

    This is the AL-068/UW-C20 guard itself: `dedication` shipped in
    `PERSONALIZATION_FIELDS` with no `CLOSED_VOCABULARIES` entry, and
    `_shape_violations` (which gates on CLOSED_VOCABULARIES membership, not
    PERSONALIZATION_FIELDS membership) silently treated it as free-text. A
    slot type that repeats that mistake, added to PERSONALIZATION_FIELDS with
    neither a vocabulary entry nor a name in
    `_FREE_TEXT_OR_REFERENCE_EXEMPT_FIELDS`, fails here instead of shipping a
    kid-facing free-text hole a second time.
    """
    uncovered = (
        set(PERSONALIZATION_FIELDS)
        - set(CLOSED_VOCABULARIES)
        - _FREE_TEXT_OR_REFERENCE_EXEMPT_FIELDS
    )
    assert uncovered == set(), (
        f"slot type(s) {sorted(uncovered)} are in PERSONALIZATION_FIELDS with "
        "neither a CLOSED_VOCABULARIES entry nor a "
        "_FREE_TEXT_OR_REFERENCE_EXEMPT_FIELDS exemption"
    )


def test_closed_vocabularies_keys_are_a_subset_of_personalization_fields() -> None:
    """CLOSED_VOCABULARIES never carries a stale key PERSONALIZATION_FIELDS dropped.

    The complementary direction of the guard above: a key left behind after a
    field is renamed or removed (as `favorite` was by Task D6) would be dead
    weight at best and a silently-unreachable vocabulary at worst.
    """
    assert set(CLOSED_VOCABULARIES) <= set(PERSONALIZATION_FIELDS)


def test_every_closed_vocabulary_is_non_empty() -> None:
    """No CLOSED_VOCABULARIES entry ships fail-closed-empty after Task D6.

    Before Task D6, every entry was `frozenset()` by design (ADR-023 never
    itself enumerated a shippable list); the owner's 2026-07-29 acceptance in
    `personalization-closed-vocabularies-proposal.md` closed that gap for
    every entry that exists at all, so an empty entry from here on is a
    regression, not the documented starting state.
    """
    empty = {
        slot_type
        for slot_type, vocabulary in CLOSED_VOCABULARIES.items()
        if not vocabulary
    }
    assert empty == set()


def test_exempt_fields_carry_no_vocabulary_entry() -> None:
    """An exempt field never also carries a stray CLOSED_VOCABULARIES entry.

    Guards the exemption set itself against going stale in the other
    direction: a field added to `CLOSED_VOCABULARIES` should be removed from
    the exemption list, not left in both places where the two could quietly
    disagree about which check governs it.
    """
    assert _FREE_TEXT_OR_REFERENCE_EXEMPT_FIELDS.isdisjoint(CLOSED_VOCABULARIES)
