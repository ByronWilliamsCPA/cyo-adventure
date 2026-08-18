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
Task D6's split migration replaces both CHECKs wholesale to split the flat
``favorite`` slot into ``favorite_color``/``favorite_food``/
``favorite_hobby``, so only the newest migration describes the vocabulary the
database actually ends up with. Deliberately named here by role rather than
by filename: a timestamp prefix in prose goes stale the moment the file is
renamed (this one already was, to resolve a version collision), which is the
exact failure mode this module exists to prevent.

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

from cyo_adventure.api.personalization import (
    _RING2_EXCLUDED_SLOT_TYPES,
)
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
# outward, dedication names the book's giver, not its reader, and
# character_name (ADR-028) is a permanent ceiling, not a default: it is
# unreviewed child free text, and the three-ring boundary (ADR-018) keeps
# unreviewed child free text inside ring 1 only.
_RING1_ONLY_FIELDS = frozenset({"pronoun_set", "dedication", "character_name"})

# AL-068/UW-C20: every `PERSONALIZATION_FIELDS` member must resolve to
# EITHER a `CLOSED_VOCABULARIES` entry OR a name in this set, which records
# WHY each one is deliberately free-text/reference-shaped rather than an
# enum: `protagonist_first_name`/`pet_name` are guardian-authored free text
# (a real name), and `SIBLING_SLOT_TYPE` (`sibling_name`) is a
# `value_profile_id` reference, not text or an enum, so it was never eligible
# for `CLOSED_VOCABULARIES` at all.
#
# `pronoun_set` LEFT this set on 2026-08-18: it was exempted on the reasoning
# that no design document stated its shape, which was false (ADR-023 row 2 and
# OD-2 both scope it), and the exemption was the last free-text channel into
# child-facing prose. It is now a `CLOSED_VOCABULARIES` entry, so this guard
# covers it by the normal route (AL-459, UW-C285).
_FREE_TEXT_OR_REFERENCE_EXEMPT_FIELDS = frozenset(
    {"protagonist_first_name", "pet_name", SIBLING_SLOT_TYPE}
)

# ADR-028: character_name carries NO value in this table at all (its value
# is synthesized from the active Character's name), so it is neither a
# CLOSED_VOCABULARIES candidate nor a free-text/reference slot in the sense
# `_FREE_TEXT_OR_REFERENCE_EXEMPT_FIELDS` records; it is exempt from having
# a vocabulary for a different reason (there is no value to constrain the
# shape of) and gets its own, separately documented set rather than being
# folded into that one, so a reader of either set sees a single reason, not
# two unrelated reasons sharing one name.
_NO_VALUE_EXEMPT_FIELDS = frozenset({"character_name"})


def _executable_ddl(path: Path) -> str:
    """Return a migration's text with its ``--`` comment lines removed.

    #EDGE: data-integrity: this project's SQL migration header comments are
    prose and routinely quote the very DDL they describe (the D6 split
    migration's own header explains the ``slot_type IN (...)`` CHECK it
    replaces). Both the migration SELECTOR and the list PARSER below must
    therefore agree that only executable DDL counts; a selector that matched
    on raw text would happily nominate a comment-only or policy-only
    migration as "the newest one defining the CHECK", and the parser would
    then fail with "found 0 occurrences", pointing the next engineer at a
    nonexistent DDL defect instead of at the selector.

    Args:
        path: The migration file to read.

    Returns:
        str: The file's lines with every ``--`` comment line dropped.
    """
    raw = path.read_text(encoding="utf-8")
    return "\n".join(
        line for line in raw.splitlines() if not line.strip().startswith("--")
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
        if "slot_type IN (" in _executable_ddl(path)
    )
    if not candidates:
        message = (
            f"no migration under {_MIGRATIONS_DIR} defines a 'slot_type IN (...)' CHECK"
        )
        raise AssertionError(message)
    return candidates[-1]


def _split_favorite_migration() -> Path:
    """Locate the migration that split the flat `favorite` slot (Task D6).

    Resolved by content, not filename, for the same reason
    `_newest_slot_type_check_migration` above is resolved dynamically: a
    hardcoded name would go stale the moment the file is renamed. But this
    helper deliberately does NOT reuse that one. Two tests below assert
    facts specific to the D6 event (that it swept
    `personalization_disclosure_consent` and removed the literal
    `'favorite'` element), and pointing them at "whichever migration is
    newest" was a latent bug that this migration exposed: it happened to
    return the D6 migration only because, at the time those tests were
    written, D6 was ALSO the newest migration touching the `slot_type`
    CHECK. The persistent-characters migration (ADR-028) is newer still and
    touches that same CHECK to add `character_name`, a purely additive
    change with nothing to sweep in the consent table: the added slot type
    was never grantable before this migration, so no existing consent
    record could already reference it. There never was a general "the
    newest slot_type migration always touches the consent table" rule;
    only this one historical event was ever being pinned.

    Returns:
        Path: The migration file that removed `'favorite'` from
        `personalization_disclosure_consent.covered_slot_types`.

    Raises:
        AssertionError: If no migration matches, or more than one does.
    """
    candidates = [
        path
        for path in _MIGRATIONS_DIR.glob("*.sql")
        if "- 'favorite'" in _executable_ddl(path)
    ]
    assert len(candidates) == 1, (
        "expected exactly one migration containing the `covered_slot_types "
        f"- 'favorite'` consent-scope removal (Task D6), found {len(candidates)}: "
        f"{candidates}"
    )
    return candidates[0]


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
    # Comment lines are stripped by `_executable_ddl` (see its docstring for
    # why the selector above must use the same view of the file), so a header
    # comment's mention of "slot_type IN (...)" is never mistaken for one of
    # the two executable DDL occurrences. Mirrors
    # test_pipeline_event_check_vocab.py's identical guard for apostrophes.
    ddl = _executable_ddl(_newest_slot_type_check_migration())
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


def test_orm_value_cardinality_constraint_present() -> None:
    """ck_cpp_value_cardinality exists, mirroring the migration's named CHECK.

    Renamed from ck_cpp_exactly_one_value (ADR-028): character_name is the
    one slot_type whose row must carry NONE of the three value columns, so
    the constraint is no longer "exactly one" for every row and the old name
    would misdescribe it.
    """
    sqltext = _orm_check_sqltext("ck_cpp_value_cardinality")
    assert "value_text" in sqltext
    assert "value_enum" in sqltext
    assert "value_profile_id" in sqltext
    assert "character_name" in sqltext


def test_orm_has_no_stale_exactly_one_value_constraint_name() -> None:
    """The ORM's __table_args__ never carries the pre-rename constraint name.

    Complementary to the presence test above, and the reason it exists at
    all: `test_schema_parity.py` compares CHECK constraints by deparsed
    `sqltext` only, never by `conname` (see this module's docstring), so a
    stray second CheckConstraint left behind under the old name would be
    invisible to that gate and to the presence test, which only proves the
    NEW name exists, not that the OLD one is gone.
    """
    names = {
        constraint.name
        for constraint in ChildProfilePersonalization.__table_args__
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_cpp_exactly_one_value" not in names
    assert "ck_cpp_value_cardinality" in names


def test_migration_renames_value_cardinality_constraint() -> None:
    """The migration adds the new constraint name and never re-adds the old one.

    The other migration-side tests in this module compare CHECK bodies only
    (`_migration_slot_type_lists` parses `slot_type IN (...)` fragments, not
    constraint names), so the ck_cpp_exactly_one_value -> ck_cpp_value_cardinality
    rename (ADR-028) is invisible to them, and to
    `tests/integration/test_schema_parity.py`, which is also sqltext-only.
    This is the one place that rename is checked directly.
    """
    ddl = _executable_ddl(_newest_slot_type_check_migration())
    assert 'ADD CONSTRAINT "ck_cpp_value_cardinality"' in ddl
    assert 'ADD CONSTRAINT "ck_cpp_exactly_one_value"' not in ddl


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
        - _NO_VALUE_EXEMPT_FIELDS
    )
    assert uncovered == set(), (
        f"slot type(s) {sorted(uncovered)} are in PERSONALIZATION_FIELDS with "
        "neither a CLOSED_VOCABULARIES entry nor a "
        "_FREE_TEXT_OR_REFERENCE_EXEMPT_FIELDS or _NO_VALUE_EXEMPT_FIELDS exemption"
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
    assert _NO_VALUE_EXEMPT_FIELDS.isdisjoint(CLOSED_VOCABULARIES)
    assert _NO_VALUE_EXEMPT_FIELDS.isdisjoint(_FREE_TEXT_OR_REFERENCE_EXEMPT_FIELDS)


# ---------------------------------------------------------------------------
# The SECOND store of this vocabulary:
# personalization_disclosure_consent.covered_slot_types.
# ---------------------------------------------------------------------------


def test_consent_covered_slot_types_vocabulary_matches_personalization_fields() -> None:
    """The consent scope's admissible vocabulary is exactly the ring-2 eligible set.

    `personalization_disclosure_consent.covered_slot_types` is an UNCONSTRAINED JSONB
    string array holding the same slot-type names the CHECK-guarded
    `child_profile_personalization.slot_type` column holds. Unlike that
    column, nothing at the database level bounds it: the only gate is
    `api/personalization.py`'s write-time
    ``slot_type not in PERSONALIZATION_FIELDS or slot_type in
    _RING2_EXCLUDED_SLOT_TYPES`` check.

    That asymmetry is exactly how Task D6 nearly shipped a half-done data
    migration. The split migration reasoned carefully about why a
    `slot_type = 'favorite'` ROW was unwritable (empty frozenset plus
    `_shape_violations`) and wrote a defensive DELETE anyway, while the store
    where `'favorite'` genuinely WAS writable went untouched. A stale entry
    there fails closed (`_ring2_values` excludes any row whose slot_type is
    not in `covered`, so the family under-shares rather than over-shares) but
    leaves a consent record naming a slot type the system no longer has, and
    `GET /v1/me` echoes that dead string back verbatim.

    This test binds the Python-side gate to the same source of truth the DB
    CHECKs are bound to above, so the next vocabulary change fails here rather
    than silently stranding consent records.
    """
    admissible = set(PERSONALIZATION_FIELDS) - _RING2_EXCLUDED_SLOT_TYPES
    assert admissible == set(PERSONALIZATION_FIELDS) - _RING1_ONLY_FIELDS, (
        "api/personalization.py's consent-scope gate and this module's "
        "ring-1-only set disagree about which slot types a ring-2 consent may "
        "cover; they must name the same ceiling as ck_cpp_ring2_ceiling"
    )
    _, ring2_ceiling = _migration_slot_type_lists()
    assert admissible == ring2_ceiling, (
        "the consent scope's admissible vocabulary drifted from the DB's own "
        "ring-2 ceiling; a consent could then name a slot type the "
        "child_profile_personalization CHECK rejects, or vice versa"
    )


def test_split_migration_sweeps_the_consent_scope_too() -> None:
    """The D6 split migration clears 'favorite' from the consent scope column.

    The companion to the guard above, pinned as a regression test rather than
    a vocabulary assertion: the split migration must touch BOTH stores. The
    element is removed rather than expanded into the three new keys because
    rewriting a single 'favorite' grant into favorite_color + favorite_food +
    favorite_hobby would widen a ring-2 sharing scope to three distinct facts
    the guardian was never shown.

    Resolved via `_split_favorite_migration`, not `_newest_slot_type_check_
    migration`: this is a fact about one historical migration, not about
    whichever migration is newest today. See that helper's docstring.
    """
    ddl = _executable_ddl(_split_favorite_migration())
    assert "personalization_disclosure_consent" in ddl, (
        "the D6 split migration does not touch "
        "personalization_disclosure_consent.covered_slot_types, the second "
        "(unconstrained) store of this same vocabulary"
    )
    assert "- 'favorite'" in ddl, (
        "expected a `covered_slot_types - 'favorite'` removal; an expansion "
        "into the three new keys would widen consent beyond what was granted"
    )


def test_split_migration_only_names_tables_that_a_migration_creates() -> None:
    """Every `"public"."<table>"` the split migration touches actually exists.

    The guard above asserts the migration NAMES the second store, which is
    necessary but, on its own, vacuous: it reads the migration's own text, so a
    misspelled table name satisfies it as happily as a correct one. That is not
    hypothetical. The consent sweep first shipped against
    ``"public"."personalization_consent"``, and the real table is
    ``personalization_disclosure_consent``; the string assertion passed locally
    because the test and the typo agreed, and the defect surfaced only in CI as
    ``relation "public.personalization_consent" does not exist (SQLSTATE
    42P01)`` after every unit test had gone green.

    This test closes that gap without needing a database: it resolves each
    schema-qualified name in the migration against the set of tables the
    migration directory as a whole creates. A name no `CREATE TABLE` ever
    introduced cannot be a table this migration can touch.

    #EDGE: data-integrity: this checks table names only, not columns; a typo in
    `covered_slot_types` would still reach CI. Columns would need the ORM
    metadata or a live schema to resolve, and the table name is where the whole
    statement fails, so this is the cheap 90%.
    #VERIFY: a real schema check runs in the `Validate migration chain` and
    `Playwright (real-backend PR smoke)` CI jobs, which apply every migration
    against a live Postgres.

    Resolved via `_split_favorite_migration`, not `_newest_slot_type_check_
    migration`, for the same reason as the guard above: this test is about
    the D6 event by name, not about whichever migration is newest today.
    """
    migrations = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    created: set[str] = set()
    for path in migrations:
        created.update(
            re.findall(
                r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"public"\."(\w+)"',
                _executable_ddl(path),
                flags=re.IGNORECASE,
            )
        )
    assert created, "no CREATE TABLE statements found; the parser is broken"

    ddl = _executable_ddl(_split_favorite_migration())
    referenced = set(re.findall(r'"public"\."(\w+)"', ddl))
    unknown = referenced - created
    assert not unknown, (
        f"the split migration references {sorted(unknown)}, which no migration "
        f"in {_MIGRATIONS_DIR.name}/ creates; check for a misspelled table name"
    )
