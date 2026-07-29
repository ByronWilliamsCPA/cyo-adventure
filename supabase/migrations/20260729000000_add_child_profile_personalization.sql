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

-- #CRITICAL: security: RLS is the ONLY gate on the PostgREST path. Supabase's
-- platform-level `ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public`
-- (applied by the platform, not present in this repo) grants `anon` and
-- `authenticated` full arwdDxtm on every table `postgres` creates in `public`,
-- and the anon key ships in the frontend bundle. Without this statement,
-- `GET /rest/v1/child_profile_personalization?select=*` returns every child's
-- real first name, sibling name, pet name, kinship label, and dedication
-- across every family, unauthenticated, with writes included. This mirrors
-- 20260711200745_enable_rls_all_tables.sql, which established the invariant
-- that EVERY public table has RLS enabled; a new table that skips it is a
-- silent hole in that invariant.
-- ENABLE (not FORCE) is deliberate and matches 20260711200745: the app
-- currently connects as `postgres`, the table owner, which Postgres always
-- exempts from RLS. FORCE would lock the application out of its own table.
-- Service-role access for the ADR-021 `cyo_api` / `cyo_worker` cutover is
-- granted separately in 20260729040000_add_personalization_service_role_access.sql.
-- #VERIFY: tests/integration/test_rls_service_roles.py
-- ::test_no_public_table_ships_without_row_level_security asserts that no
-- table in `public` has rowsecurity = false, so the next table that forgets
-- this fails a test instead of shipping.
ALTER TABLE "public"."child_profile_personalization" ENABLE ROW LEVEL SECURITY;

-- Postgres indexes the referenced side of a foreign key automatically but
-- never the referencing side. value_profile_id is ON DELETE CASCADE, so a
-- sibling profile deletion sequentially scans this table without it. The
-- (child_profile_id, slot_type) primary key already covers the other FK.
CREATE INDEX IF NOT EXISTS ix_cpp_value_profile_id
    ON "public"."child_profile_personalization" (value_profile_id);
