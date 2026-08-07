-- ADR-023/ADR-028: add the ring-1-only `character_name` personalization slot
-- (persistent-characters runtime plan, Task 3).
--
-- character_name is the only PERSONALIZATION_FIELDS member whose value lives
-- outside this table entirely: it is synthesized at resolve time from the
-- profile's active `character.name` row (added by
-- 20260806120000_add_persistent_characters.sql), not from
-- value_text/value_enum/value_profile_id. A guardian's consent row for this
-- slot therefore carries `ring1_enabled` and nothing else.
--
-- That broke the previous ck_cpp_exactly_one_value CHECK, which required
-- exactly one of value_text/value_enum/value_profile_id for every row with
-- no exception. Relaxing it for all twelve slots would let any slot silently
-- carry a value AND a redundant value_text copy of it, so instead this
-- migration TIGHTENS it into a per-slot_type CASE: character_name must carry
-- NONE of the three value columns; the other eleven slot types keep the
-- original exactly-one rule, unchanged. The CHECK is renamed
-- ck_cpp_value_cardinality because its body is no longer "exactly one" for
-- every row, matching db.models.ChildProfilePersonalization's parallel,
-- hand-maintained Python metadata (see that class's docstring).
-- tests/integration/test_schema_parity.py compares CHECK constraints by
-- deparsed sqltext only, never by name, so the migration and the ORM's
-- CheckConstraint.name are kept in sync here by hand, not by that gate; see
-- tests/unit/test_personalization_vocab_drift.py::
-- test_orm_value_cardinality_constraint_present for the name-level guard.
--
-- character_name never enters ck_cpp_ring2_ceiling: it is a permanent
-- ring-1-only ceiling (ADR-018's three-ring boundary keeps unreviewed child
-- free text inside ring 1 only), so that CHECK's value list is unchanged.
-- It is still dropped and recreated below, matching
-- tests/unit/test_personalization_vocab_drift.py's dynamic-resolution
-- design (`_newest_slot_type_check_migration`): only the newest migration
-- that defines a `slot_type IN (...)` CHECK is trusted to describe the
-- vocabulary, so a migration that touched only ck_cpp_slot_type would leave
-- this file unable to answer "what is the current ring-2 ceiling?" on its
-- own.
--
-- #VERIFY: tests/unit/test_character_name_slot.py,
-- tests/unit/test_personalization_vocab_drift.py,
-- tests/integration/test_personalization_purge.py.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_cpp_slot_type'
          AND conrelid = '"public"."child_profile_personalization"'::regclass
    ) THEN
        ALTER TABLE "public"."child_profile_personalization"
            DROP CONSTRAINT "ck_cpp_slot_type";
    END IF;

    ALTER TABLE "public"."child_profile_personalization"
        ADD CONSTRAINT "ck_cpp_slot_type" CHECK (slot_type IN (
            'protagonist_first_name', 'pronoun_set', 'sibling_name', 'pet_species',
            'pet_name', 'kinship_label', 'favorite_color', 'favorite_food',
            'favorite_hobby', 'home_type', 'dedication', 'character_name'));

    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_cpp_exactly_one_value'
          AND conrelid = '"public"."child_profile_personalization"'::regclass
    ) THEN
        ALTER TABLE "public"."child_profile_personalization"
            DROP CONSTRAINT "ck_cpp_exactly_one_value";
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_cpp_value_cardinality'
          AND conrelid = '"public"."child_profile_personalization"'::regclass
    ) THEN
        ALTER TABLE "public"."child_profile_personalization"
            DROP CONSTRAINT "ck_cpp_value_cardinality";
    END IF;

    ALTER TABLE "public"."child_profile_personalization"
        ADD CONSTRAINT "ck_cpp_value_cardinality" CHECK (
            CASE WHEN slot_type = 'character_name'
                 THEN (value_text IS NULL AND value_enum IS NULL
                       AND value_profile_id IS NULL)
                 ELSE ((value_text IS NOT NULL)::int + (value_enum IS NOT NULL)::int
                       + (value_profile_id IS NOT NULL)::int = 1)
            END);

    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_cpp_ring2_ceiling'
          AND conrelid = '"public"."child_profile_personalization"'::regclass
    ) THEN
        ALTER TABLE "public"."child_profile_personalization"
            DROP CONSTRAINT "ck_cpp_ring2_ceiling";
    END IF;

    ALTER TABLE "public"."child_profile_personalization"
        ADD CONSTRAINT "ck_cpp_ring2_ceiling" CHECK (
            NOT ring2_enabled OR slot_type IN (
            'protagonist_first_name', 'sibling_name', 'pet_species', 'pet_name',
            'kinship_label', 'favorite_color', 'favorite_food', 'favorite_hobby',
            'home_type'));
END
$$;

-- Forward-only migration per this project's Supabase CLI convention
-- (ADR-012); no down script.
