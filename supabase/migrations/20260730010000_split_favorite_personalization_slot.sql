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

-- #CRITICAL: data integrity: `child_profile_personalization.slot_type` is NOT
-- the only store of this vocabulary. `personalization_consent.covered_slot_types`
-- is an unconstrained JSONB string array holding the same slot-type names, and
-- unlike the CHECK-guarded column above it COULD legitimately hold 'favorite'
-- today: its only gate is api/personalization.py's `slot_type not in
-- PERSONALIZATION_FIELDS or slot_type in _RING2_EXCLUDED_SLOT_TYPES`, and
-- 'favorite' satisfied both before this migration. So the DELETE above is
-- defensive, but the UPDATE below is a real data migration.
--
-- The element is REMOVED rather than expanded into the three new keys. That
-- direction is deliberate and is the COPPA-safe one: a guardian consented to
-- share "favorite", which under Option A was a single undifferentiated value.
-- Rewriting that grant into favorite_color + favorite_food + favorite_hobby
-- would widen a ring-2 sharing scope to three distinct facts the guardian was
-- never shown, which is exactly the consent-inflation ADR-023's ring model
-- exists to prevent. Removing it means the new slots start unshared until the
-- guardian re-consents, so the failure direction is under-share.
--
-- `jsonb - text` removes every matching string element from a JSONB array and
-- is a no-op on an array that does not contain it; the `?` guard keeps the
-- UPDATE from rewriting untouched rows. NULL rows are skipped by `?` returning
-- NULL, which is correct: a NULL scope covers nothing.
-- #VERIFY: tests/unit/test_personalization_vocab_drift.py::
-- test_consent_covered_slot_types_vocabulary_matches_personalization_fields
-- pins this column's admissible vocabulary to PERSONALIZATION_FIELDS, so the
-- next vocabulary change fails there rather than silently stranding a consent
-- record that names a slot type the system no longer has.
UPDATE "public"."personalization_consent"
   SET covered_slot_types = covered_slot_types - 'favorite'
 WHERE covered_slot_types ? 'favorite';

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
