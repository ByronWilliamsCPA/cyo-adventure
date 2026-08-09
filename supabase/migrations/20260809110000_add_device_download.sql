-- G15 remainder (docs/planning/roadmap.md Phase 4b; capability register G15): a guardian
-- storage/download view -- which books are downloaded on which device. Device list/revoke
-- (the other G15 half) shipped earlier via device_grant; this table is the missing piece,
-- reporting client-side IndexedDB cache state (frontend/src/offline/db.ts's `storybooks`
-- store) so the guardian console has something to show.
--
-- device_id is a NEW, separate identity from device_grant.jti (the kid-mode device
-- authorization token id): a plain client-generated UUID persisted in localStorage
-- (frontend/src/offline/deviceId.ts), not an auth token. A guardian's own browser
-- previewing the kid shelf downloads books too and has no device_grant of its own, so
-- keying this table on the auth token id would silently miss it.
--
-- Table and REFERENCES targets are schema-qualified ("public".*): see
-- 20260729000000_add_child_profile_personalization.sql's header comment for why.
--
-- Tier classification (ADR-022): device_download carries a direct family_id column
-- (denormalized from the owning profile, same reasoning as "character" in
-- 20260806120000_add_persistent_characters.sql), so it gets the Tier 1 family_scoped
-- policy. The composite FK to child_profile (id, family_id) below is what keeps the
-- denormalized value honest, reusing the uq_child_profile_family_id_id constraint that
-- migration already added.

CREATE TABLE IF NOT EXISTS "public"."device_download" (
    id UUID NOT NULL,
    family_id UUID NOT NULL,
    child_profile_id UUID NOT NULL,
    device_id VARCHAR(64) NOT NULL,
    storybook_id VARCHAR(120) NOT NULL REFERENCES "public"."storybook"(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT device_download_pkey PRIMARY KEY (id),
    CONSTRAINT fk_device_download_profile_family FOREIGN KEY (child_profile_id, family_id)
        REFERENCES "public"."child_profile" (id, family_id) ON DELETE CASCADE,
    CONSTRAINT uq_device_download_device_profile_book
        UNIQUE (device_id, child_profile_id, storybook_id)
);

-- Postgres indexes the referenced side of a foreign key automatically but never the
-- referencing side; a family deletion (CASCADE above) would otherwise sequentially scan
-- this table (same reasoning as ix_character_child_profile_id).
CREATE INDEX IF NOT EXISTS ix_device_download_family_id
    ON "public"."device_download" (family_id);

-- Same rule, second referencing FK: storybook_id REFERENCES storybook(id) ON DELETE
-- CASCADE above. Unpublishing or deleting a book is a routine operation here (it is how
-- a withdrawn story leaves every shelf), so leaving this side unindexed puts a
-- sequential scan of the whole download inventory on that path. The composite unique
-- constraint below does not help: its leading column is device_id, and Postgres cannot
-- use a composite index for a predicate that names only a trailing column.
CREATE INDEX IF NOT EXISTS ix_device_download_storybook_id
    ON "public"."device_download" (storybook_id);

-- #CRITICAL: security: RLS is the ONLY gate on the PostgREST path (see
-- 20260729000000_add_child_profile_personalization.sql's identical note); a new table
-- that skips ENABLE ROW LEVEL SECURITY is a silent hole in the "every public table has
-- RLS" invariant established by 20260711200745_enable_rls_all_tables.sql.
-- #VERIFY: tests/integration/test_rls_service_roles.py::
-- test_no_public_table_ships_without_row_level_security asserts that no table in
-- `public` has rowsecurity = false.
ALTER TABLE "public"."device_download" ENABLE ROW LEVEL SECURITY;

-- Tier 1: family_scoped, identical shape to "character"'s policy in
-- 20260806120000_add_persistent_characters.sql. current_setting(name, true) returns NULL
-- when the GUC is unset, and "family_id = NULL" is never true, so a request that never
-- set context matches zero rows: fail-closed. app.is_admin is the only cross-family reach
-- in the predicate.
DROP POLICY IF EXISTS worker_rw ON "public"."device_download";
DROP POLICY IF EXISTS family_scoped ON "public"."device_download";
CREATE POLICY worker_rw ON "public"."device_download"
    FOR ALL TO cyo_worker USING (true) WITH CHECK (true);
CREATE POLICY family_scoped ON "public"."device_download"
    FOR ALL TO cyo_api
    USING (
        family_id::text = current_setting('app.family_id', true)
        OR current_setting('app.is_admin', true) = 'true'
    )
    WITH CHECK (
        family_id::text = current_setting('app.family_id', true)
        OR current_setting('app.is_admin', true) = 'true'
    );

-- RLS policies gate rows only once the GRANT layer admits the role at all; both service
-- roles need the table-level grants too (the omission fails
-- tests/integration/test_rls_service_roles.py::test_every_rls_table_grants_both_service_roles).
GRANT SELECT, INSERT, UPDATE, DELETE ON "public"."device_download" TO cyo_api, cyo_worker;

-- Forward-only migration per this project's Supabase CLI convention (ADR-012); no down
-- script.
