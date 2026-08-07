-- ADR-028: persistent reader characters. A child creates one character (name,
-- archetype, look) that carries across books rather than starting fresh each
-- time; three new tables plus a binding on reading_state.
--
-- Table and REFERENCES targets are schema-qualified ("public".*): see
-- 20260729000000_add_child_profile_personalization.sql's header comment for
-- why (the baseline migration empties search_path for the rest of the
-- session, so every later migration that creates or alters a table must
-- schema-qualify or fail with "no schema has been selected to create in").
-- Column names and CHECK bodies stay unquoted, matching every other migration
-- in this repository (see the same personalization migration's slot_type IN
-- (...) CHECK); this also keeps this migration's CHECK literal text bytewise
-- identical to the equivalent SQLAlchemy CheckConstraint text in db/models.py,
-- which is what tests/unit/test_character_vocab_drift.py and
-- tests/integration/test_schema_parity.py both rely on.
--
-- Tier classification (ADR-022): "character" carries a direct family_id
-- column (denormalized from its owning profile) so it gets the Tier 1
-- family_scoped policy, matching child_profile/story_request/device_grant in
-- 20260724120000_scoped_rls_tier1_family_scoping.sql. "character_attribute"
-- and "character_book_completion" are keyed by character_id (and, for the
-- latter, reading_state's own composite key) with no direct family_id column,
-- so per ADR-022's Technical Debt clause they are Tier 2 (blanket), matching
-- reading_state itself.
--
-- The Tier 2 shape below is a single "service_rw" policy granted to BOTH
-- cyo_api and cyo_worker, matching every Tier 2 table added since
-- 20260720170200_add_service_role_policies.sql (most recently
-- reading_activity_day and security_event). An earlier draft of this
-- migration split Tier 2 into a "worker_rw" + "api_rw" pair; that shape does
-- not match any table in this repository and has been replaced with the real
-- convention.

-- 1. child_profile needs a composite unique on (family_id, id): this is what
-- makes character's fk_character_profile_family below a real database
-- constraint rather than an application convention. Column order
-- (family_id, id) is arbitrary; Postgres matches a foreign key's referenced
-- columns against a unique constraint by set, not by declared order (see
-- character's own FK below, which references child_profile in (id,
-- family_id) order).
ALTER TABLE "public"."child_profile"
    ADD CONSTRAINT uq_child_profile_family_id_id UNIQUE (family_id, id);

-- 2. character: one row per persistent character, owned by one profile.
CREATE TABLE IF NOT EXISTS "public"."character" (
    id UUID NOT NULL,
    child_profile_id UUID NOT NULL,
    family_id UUID NOT NULL,
    name VARCHAR(32) NOT NULL,
    archetype VARCHAR(16) NOT NULL,
    look VARCHAR(16) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    books_completed INTEGER NOT NULL DEFAULT 0,
    retired_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT character_pkey PRIMARY KEY (id),
    CONSTRAINT fk_character_profile_family FOREIGN KEY (child_profile_id, family_id)
        REFERENCES "public"."child_profile" (id, family_id) ON DELETE CASCADE,
    CONSTRAINT ck_character_active_xor_retired CHECK (
        NOT (is_active AND retired_at IS NOT NULL)),
    CONSTRAINT ck_character_archetype CHECK (archetype IN (
        'scout', 'guardian', 'trickster', 'scholar', 'healer', 'wildheart')),
    CONSTRAINT ck_character_look CHECK (look IN (
        'avatar_01', 'avatar_02', 'avatar_03', 'avatar_04',
        'avatar_05', 'avatar_06', 'avatar_07', 'avatar_08',
        'avatar_09', 'avatar_10', 'avatar_11', 'avatar_12')),
    CONSTRAINT ck_character_books_completed_non_negative CHECK (books_completed >= 0)
);

-- A partial unique index, not a table constraint: at most one ACTIVE
-- character per profile, but any number of retired ones (a retired
-- character is not deleted, so books_completed history survives).
CREATE UNIQUE INDEX IF NOT EXISTS uq_character_one_active
    ON "public"."character" (child_profile_id) WHERE (is_active);

-- Postgres indexes the referenced side of a foreign key automatically but
-- never the referencing side; a profile deletion (CASCADE above) would
-- otherwise sequentially scan this table.
CREATE INDEX IF NOT EXISTS ix_character_child_profile_id
    ON "public"."character" (child_profile_id);

-- 3. character_attribute: one canonical attribute value per character.
-- value_bool is deliberately absent in v1 (see db/models.py::
-- CharacterAttribute's docstring): every canonical variable is an int.
CREATE TABLE IF NOT EXISTS "public"."character_attribute" (
    character_id UUID NOT NULL REFERENCES "public"."character"(id) ON DELETE CASCADE,
    name VARCHAR(16) NOT NULL,
    value_int INTEGER NOT NULL,
    PRIMARY KEY (character_id, name),
    CONSTRAINT ck_character_attribute_name CHECK (name IN (
        'archetype', 'might', 'wits', 'nerve')),
    CONSTRAINT ck_character_attribute_value_range CHECK (
        (name = 'archetype' AND value_int BETWEEN 0 AND 6)
        OR (name IN ('might', 'wits', 'nerve') AND value_int BETWEEN 0 AND 2))
);

-- 4. character_book_completion: one row per (reading_state, character) that
-- has been written back.
-- #CRITICAL: data integrity: this composite primary key IS the writeback
-- idempotency mechanism. A child who reaches a satisfying ending, goes
-- offline, and replays the queued completion must not increment
-- books_completed twice; INSERT ... ON CONFLICT DO NOTHING against this key
-- makes the second attempt a no-op in the database rather than an
-- application-side (and racy, under concurrent sync) "have we done this
-- already?" read.
-- #VERIFY: tests/integration/test_character_progression.py::
-- test_replayed_completion_does_not_increment_twice
--
-- The spec names this key (reading_state_id, character_id), but reading_state
-- has a composite key (child_profile_id, storybook_id) and no surrogate id,
-- so the faithful translation is the three-column key below; no surrogate id
-- was added to reading_state to make the spec's wording literal.
CREATE TABLE IF NOT EXISTS "public"."character_book_completion" (
    reading_state_child_profile_id UUID NOT NULL,
    reading_state_storybook_id VARCHAR(120) NOT NULL,
    character_id UUID NOT NULL REFERENCES "public"."character"(id) ON DELETE CASCADE,
    ending_id VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (
        reading_state_child_profile_id, reading_state_storybook_id, character_id
    ),
    CONSTRAINT fk_cbc_reading_state FOREIGN KEY (
        reading_state_child_profile_id, reading_state_storybook_id
    ) REFERENCES "public"."reading_state" (child_profile_id, storybook_id)
        ON DELETE CASCADE
);

-- 5. reading_state: the character bound to this reading session, and the
-- character-attribute snapshot it was seeded from. Both nullable: an
-- unseeded reading state (no character carried into this book) is the
-- normal case, not an error. SET NULL, not CASCADE: deleting a character
-- must not delete the child's reading progress in the books that character
-- played.
ALTER TABLE "public"."reading_state"
    ADD COLUMN IF NOT EXISTS character_id UUID
        REFERENCES "public"."character"(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS seed_var_state JSONB;

-- #CRITICAL: security: RLS is the ONLY gate on the PostgREST path (see
-- 20260729000000_add_child_profile_personalization.sql's identical note); a
-- new table that skips ENABLE ROW LEVEL SECURITY is a silent hole in the
-- "every public table has RLS" invariant established by
-- 20260711200745_enable_rls_all_tables.sql.
-- #VERIFY: tests/integration/test_rls_service_roles.py::
-- test_no_public_table_ships_without_row_level_security asserts that no
-- table in `public` has rowsecurity = false.
ALTER TABLE "public"."character" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."character_attribute" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."character_book_completion" ENABLE ROW LEVEL SECURITY;

-- Tier 1: character carries a direct family_id column, so it gets the same
-- fail-closed family_scoped predicate as child_profile/story_request/
-- device_grant (20260724120000_scoped_rls_tier1_family_scoping.sql).
-- current_setting(name, true) returns NULL when the GUC is unset, and
-- "family_id = NULL" is never true, so a request that never set context
-- matches zero rows: fail-closed. app.is_admin is the only cross-family
-- reach in the predicate (an admin/moderation principal, ADR-016).
DROP POLICY IF EXISTS worker_rw ON "public"."character";
DROP POLICY IF EXISTS family_scoped ON "public"."character";
CREATE POLICY worker_rw ON "public"."character"
    FOR ALL TO cyo_worker USING (true) WITH CHECK (true);
CREATE POLICY family_scoped ON "public"."character"
    FOR ALL TO cyo_api
    USING (
        family_id::text = current_setting('app.family_id', true)
        OR current_setting('app.is_admin', true) = 'true'
    )
    WITH CHECK (
        family_id::text = current_setting('app.family_id', true)
        OR current_setting('app.is_admin', true) = 'true'
    );

-- Tier 2 (blanket): character_attribute and character_book_completion have
-- no direct family_id column (they are keyed by character_id / reading_state's
-- own key), matching reading_state's own Tier 2 classification per ADR-022's
-- Technical Debt clause. DROP POLICY IF EXISTS + CREATE POLICY keeps
-- re-application idempotent with no down-migration (ADR-012 forward-only).
DROP POLICY IF EXISTS service_rw ON "public"."character_attribute";
CREATE POLICY service_rw ON "public"."character_attribute"
    FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON "public"."character_book_completion";
CREATE POLICY service_rw ON "public"."character_book_completion"
    FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

-- RLS policies gate rows only once the GRANT layer admits the role at all;
-- both service roles need the table-level grants too (the omission fails
-- tests/integration/test_rls_service_roles.py::
-- test_every_rls_table_grants_both_service_roles).
GRANT SELECT, INSERT, UPDATE, DELETE ON
    "public"."character",
    "public"."character_attribute",
    "public"."character_book_completion"
    TO cyo_api, cyo_worker;

-- Forward-only migration per this project's Supabase CLI convention
-- (ADR-012); no down script.
