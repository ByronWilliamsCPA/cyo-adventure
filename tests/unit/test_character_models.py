"""Character ORM shape: the constraints the migration must mirror.

The migration and these models are compared structurally by
tests/integration/test_schema_parity.py; this module pins the intent so a
reviewer can see WHICH constraint each name enforces without reading SQL.
"""

from __future__ import annotations

import pytest

from cyo_adventure.db.models import (
    Character,
    CharacterAttribute,
    CharacterBookCompletion,
    ChildProfile,
    ReadingState,
)


@pytest.mark.unit
def test_character_carries_a_family_id_for_tier1_rls() -> None:
    """Tier 1 scoping needs the column on the row, not via a join."""
    assert "family_id" in Character.__table__.columns


@pytest.mark.unit
def test_character_family_id_is_backed_by_a_composite_fk() -> None:
    """A denormalized family_id with no FK is a claim nothing checks.

    The composite FK to child_profile (family_id, id) is what makes
    "this character's family matches its profile's family" a database
    constraint rather than an application convention, which is the whole
    justification for denormalizing it in the first place.
    """
    targets = {
        tuple(sorted(col.name for col in fk.columns))
        for fk in Character.__table__.foreign_key_constraints
    }
    assert ("child_profile_id", "family_id") in targets


@pytest.mark.unit
def test_child_profile_exposes_the_composite_unique_the_fk_needs() -> None:
    """The FK above is unsatisfiable without this; assert it, do not assume it."""
    uniques = {
        tuple(sorted(col.name for col in c.columns))
        for c in ChildProfile.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    }
    assert ("family_id", "id") in uniques


@pytest.mark.unit
def test_only_one_character_per_profile_may_be_active() -> None:
    """A partial unique index, so retired characters do not collide."""
    index = next(
        i for i in Character.__table__.indexes if i.name == "uq_character_one_active"
    )
    assert index.unique
    assert index.dialect_options["postgresql"]["where"] is not None


@pytest.mark.unit
def test_active_and_retired_cannot_both_hold() -> None:
    """is_active and retired_at are two spellings of one fact; keep them agreeing."""
    names = {c.name for c in Character.__table__.constraints if c.name}
    assert "ck_character_not_active_and_retired" in names


@pytest.mark.unit
def test_attribute_names_are_restricted_to_the_canonical_vocabulary() -> None:
    """The DB is the last line: an out-of-vocabulary attribute must not persist."""
    names = {c.name for c in CharacterAttribute.__table__.constraints if c.name}
    assert "ck_character_attribute_name" in names
    assert "ck_character_attribute_value_range" in names


@pytest.mark.unit
def test_completion_pk_is_what_makes_writeback_idempotent() -> None:
    """Idempotency is a constraint, not an application-side check."""
    pk = tuple(sorted(c.name for c in CharacterBookCompletion.__table__.primary_key))
    # The spec writes this key as (reading_state_id, character_id), but
    # reading_state has a composite key and no surrogate id, so the
    # faithful translation is three columns. Do NOT add a surrogate key to
    # reading_state to make the spec's wording literal.
    assert pk == (
        "character_id",
        "reading_state_child_profile_id",
        "reading_state_storybook_id",
    )


@pytest.mark.unit
def test_reading_state_carries_the_binding_and_the_seed() -> None:
    """Both nullable: an unseeded read is the normal case, not an error."""
    assert ReadingState.__table__.columns["character_id"].nullable
    assert ReadingState.__table__.columns["seed_var_state"].nullable
