-- ADR-023 Task D6: split the flat `favorite` personalization slot into
-- `favorite_color` / `favorite_food` / `favorite_hobby` (Option B), per the
-- owner's 2026-07-29 decision recorded in
-- docs/planning/personalization-closed-vocabularies-proposal.md ("favorite
-- (Option B, split into three): ACCEPTED 2026-07-29, migration accepted
-- knowingly"). The flat single-vocabulary shape (Option A) could not encode
-- which sub-category (color/food/hobby) a candidate value belonged to,
-- because `CLOSED_VOCABULARIES["favorite"]` is exactly one closed set.
--
-- `child_profile_personalization` was created by
-- 20260729000000_add_child_profile_personalization.sql with a column-level,
-- UNNAMED `slot_type ... CHECK (slot_type IN (...))`. Postgres auto-names an
-- unnamed single-column CHECK "<table>_<column>_check", verified empirically
-- against a local scratch table: "child_profile_personalization_slot_type_check".
-- This migration both widens the vocabulary and gives the constraint the
-- explicit name `ck_cpp_slot_type`, matching
-- `db.models.ChildProfilePersonalization.__table_args__` (which already
-- declared that name for its parallel, hand-maintained Python metadata; see
-- that class's docstring) so the DB and the ORM mirror agree going forward.
--
-- #CRITICAL: security: no `favorite` row could ever have passed write-time
-- validation before this migration: `CLOSED_VOCABULARIES["favorite"]`
-- shipped as `frozenset()` (fail-closed) since ADR-023 P4 first landed, and
-- `_shape_violations` rejects `value_text` outright for any slot_type that
-- is a `CLOSED_VOCABULARIES` key. The DELETE below is therefore defensive
-- (a row written by hand, outside the API, would otherwise violate the
-- narrowed CHECK below and abort this migration), not a real data migration.
-- #VERIFY: tests/unit/test_personalization_vocab_drift.py pins both CHECK
-- lists (and the CLOSED_VOCABULARIES/PERSONALIZATION_FIELDS drift guard)
-- against `storybook.theme_contract.PERSONALIZATION_FIELDS`.
DELETE FROM "public"."child_profile_personalization" WHERE slot_type = 'favorite';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'child_profile_personalization_slot_type_check'
          AND conrelid = '"public"."child_profile_personalization"'::regclass
    ) THEN
        ALTER TABLE "public"."child_profile_personalization"
            DROP CONSTRAINT "child_profile_personalization_slot_type_check";
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_constraint
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
            'favorite_hobby', 'home_type', 'dedication'));

    IF EXISTS (
        SELECT 1
        FROM pg_constraint
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
