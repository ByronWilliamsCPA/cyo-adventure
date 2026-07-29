-- ADR-023 P4: per-(profile, slot) personalization values and ring flags.
-- #CRITICAL: security: ring ceilings are DB CHECKs, not API validation, so the
-- taxonomy's ring-1-only rows (pronoun_set, dedication) are structurally
-- incapable of carrying ring2_enabled = true.
-- #VERIFY: tests/unit/test_personalization_vocab_drift.py pins both lists
-- against storybook.theme_contract.PERSONALIZATION_FIELDS.
--
-- Table and REFERENCES targets are schema-qualified ("public".*): the
-- baseline migration (20260710000000_baseline.sql, a pg_dump) runs
-- `SELECT pg_catalog.set_config('search_path', '', false)` with
-- is_local=false, which empties search_path for the rest of the session, not
-- just the baseline's own statements; every migration applied afterward
-- through the same connection (see tests/integration/_migration_utils.py,
-- which reuses one asyncpg connection across the whole migrations/ chain)
-- inherits that empty search_path and an unqualified `CREATE TABLE foo`
-- fails with "no schema has been selected to create in". Every other
-- post-baseline migration that creates or alters a table already
-- schema-qualifies for this reason (see 20260717120000_add_kid_flag.sql,
-- 20260724000000_add_child_profile_reduce_motion.sql).

CREATE TABLE IF NOT EXISTS "public"."child_profile_personalization" (
    child_profile_id UUID NOT NULL REFERENCES "public"."child_profile"(id) ON DELETE CASCADE,
    slot_type VARCHAR(32) NOT NULL CHECK (slot_type IN (
        'protagonist_first_name', 'pronoun_set', 'sibling_name', 'pet_species',
        'pet_name', 'kinship_label', 'favorite', 'home_type', 'dedication')),
    value_text TEXT,
    value_enum VARCHAR(64),
    value_profile_id UUID REFERENCES "public"."child_profile"(id) ON DELETE CASCADE,
    ring1_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ring2_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (child_profile_id, slot_type),
    CONSTRAINT ck_cpp_exactly_one_value CHECK (
        (value_text IS NOT NULL)::int + (value_enum IS NOT NULL)::int
        + (value_profile_id IS NOT NULL)::int = 1),
    CONSTRAINT ck_cpp_ring2_ceiling CHECK (
        NOT ring2_enabled OR slot_type IN (
        'protagonist_first_name', 'sibling_name', 'pet_species', 'pet_name',
        'kinship_label', 'favorite', 'home_type'))
);

ALTER TABLE "public"."child_profile"
    ADD COLUMN IF NOT EXISTS real_name_ring1_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS real_name_ring2_enabled BOOLEAN NOT NULL DEFAULT FALSE;
