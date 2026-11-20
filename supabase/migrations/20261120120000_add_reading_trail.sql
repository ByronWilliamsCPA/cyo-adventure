-- Reading trail: one row per read-through of one storybook version by one
-- child, holding the ordered (node, choice) steps of that read so the owner
-- can see which books and which choices work (privacy-model.md "Reading
-- trail"; reader-path-engagement-design.md section 3.1, phase-2 client-minted
-- read id; story-quality-technique-review-2026-08-15.md T5).
--
-- What a row holds, and nothing else: the profile, its family (denormalized
-- for Tier 1 RLS, below), the storybook version, a client-minted read id (the
-- primary key), the server's calendar DATE of first receipt, the steps as a
-- JSONB array of {seq, kind, node_id, choice_id, elapsed_s}, a step count, and
-- the ending id when one was reached. No per-step wall-clock time, no device
-- id, no IP, no user agent, no free text.
--
-- Capture is gated by Settings.reading_trail_enabled (READING_TRAIL_ENABLED,
-- default off): with the flag off the API stores nothing, so this table exists
-- but stays empty until the owner turns capture on for an environment.
--
-- Table and REFERENCES targets are schema-qualified ("public".*): see
-- 20260729000000_add_child_profile_personalization.sql's header comment for
-- why (the baseline migration empties search_path for the rest of the
-- session). Written to be idempotent (IF NOT EXISTS, DROP POLICY IF EXISTS,
-- unschedule-then-schedule), forward-only per ADR-012, no down script.

-- The composite (family_id, id) unique on child_profile that the foreign key
-- below references already exists: 20260806120000_add_persistent_characters.sql
-- created uq_child_profile_family_id_id for character's identical FK.
CREATE TABLE IF NOT EXISTS "public"."reading_trail" (
    id UUID NOT NULL,
    child_profile_id UUID NOT NULL,
    family_id UUID NOT NULL,
    storybook_id VARCHAR(120) NOT NULL,
    version INTEGER NOT NULL,
    started_on DATE NOT NULL,
    steps JSONB NOT NULL,
    step_count INTEGER NOT NULL DEFAULT 0,
    ending_id VARCHAR(120),
    CONSTRAINT reading_trail_pkey PRIMARY KEY (id),
    -- #CRITICAL: data-integrity: both FKs CASCADE. The trail is child-linked
    -- behavioural data and is purged with its profile (and so with its
    -- family, via child_profile's own family cascade) and with the storybook
    -- version it is pinned to.
    -- #VERIFY: tests/integration/test_deletion_drill.py seeds a trail and
    -- asserts profile deletion and family deletion both remove it.
    CONSTRAINT fk_reading_trail_profile_family FOREIGN KEY (child_profile_id, family_id)
        REFERENCES "public"."child_profile" (id, family_id) ON DELETE CASCADE,
    CONSTRAINT fk_reading_trail_storybook_version FOREIGN KEY (storybook_id, version)
        REFERENCES "public"."storybook_version" (storybook_id, version) ON DELETE CASCADE,
    CONSTRAINT ck_reading_trail_step_count CHECK (step_count >= 0 AND step_count <= 2000)
);

-- Postgres never indexes the referencing side of a foreign key; each index
-- below backs one cascade or one query.
CREATE INDEX IF NOT EXISTS ix_reading_trail_child_profile_id_started_on
    ON "public"."reading_trail" (child_profile_id, started_on);
CREATE INDEX IF NOT EXISTS ix_reading_trail_storybook_id_version
    ON "public"."reading_trail" (storybook_id, version);
CREATE INDEX IF NOT EXISTS ix_reading_trail_started_on
    ON "public"."reading_trail" (started_on);

-- #CRITICAL: security: RLS is the ONLY gate on the PostgREST path; a new table
-- that skips ENABLE ROW LEVEL SECURITY is world-readable through the anon key.
-- #VERIFY: tests/integration/test_rls_service_roles.py::
-- test_no_public_table_ships_without_row_level_security and
-- ::test_unprivileged_roles_denied_on_sensitive_tables both discover this
-- table from the live catalog.
ALTER TABLE "public"."reading_trail" ENABLE ROW LEVEL SECURITY;

-- Tier 1 (ADR-022), not Tier 2: reading_trail carries a direct family_id, so
-- it gets the same fail-closed family_scoped predicate as child_profile,
-- story_request, device_grant, and character. This is deliberately STRONGER
-- than reading_state/completion/rating, which are Tier 2 (blanket) only
-- because they lack a family_id column. current_setting(name, true) returns
-- NULL when the GUC is unset and "family_id = NULL" is never true, so a
-- request that never set context matches zero rows. app.is_admin is the only
-- cross-family reach in the predicate.
-- #CRITICAL: security: like every Tier 1 policy this is a no-op while the app
-- connects as the table owner, and binds the moment it connects as cyo_api
-- (ADR-021 cutover); the app layer (authorize_profile plus the reading gate in
-- api/reading.py) is the primary control in both states.
-- #VERIFY: tests/integration/test_reading_trail.py::
-- test_rls_scopes_reading_trail_to_caller_family runs as cyo_api on a
-- migrated database.
DROP POLICY IF EXISTS service_rw ON "public"."reading_trail";
DROP POLICY IF EXISTS worker_rw ON "public"."reading_trail";
DROP POLICY IF EXISTS family_scoped ON "public"."reading_trail";
CREATE POLICY worker_rw ON "public"."reading_trail"
    FOR ALL TO cyo_worker USING (true) WITH CHECK (true);
CREATE POLICY family_scoped ON "public"."reading_trail"
    FOR ALL TO cyo_api
    USING (
        family_id::text = current_setting('app.family_id', true)
        OR current_setting('app.is_admin', true) = 'true'
    )
    WITH CHECK (
        family_id::text = current_setting('app.family_id', true)
        OR current_setting('app.is_admin', true) = 'true'
    );

-- RLS policies gate rows only once the GRANT layer admits the role at all
-- (tests/integration/test_rls_service_roles.py::
-- test_every_rls_table_grants_both_service_roles requires full CRUD for both).
GRANT SELECT, INSERT, UPDATE, DELETE ON "public"."reading_trail" TO cyo_api, cyo_worker;

-- Retention: 30 days from started_on, no exemption set.
--
-- The window follows reader-path-engagement-design.md section 7 item 2 (30
-- days, on ADR-007's raw-output precedent) and the clock follows ADR-031
-- Decision 7: it starts at the server-stamped DATE, so "30 days" means every
-- row whose started_on is earlier than current_date - 30 is deleted, which is
-- 30 to 31 calendar days depending on the hour of arrival. There is no
-- exemption predicate at all, which is the cheapest immunity to UW-C227's
-- sweep-time-versus-decision-time inversion.
--
-- The window is a SQL constant rather than a Settings field because pg_cron
-- runs inside Postgres and cannot read the API process's environment; every
-- other retention window in this repository is a migration constant for the
-- same reason (20260718000000, 20260720150000). Changing it is a new
-- migration that reschedules this job.
--
-- The delete lives in a function so the integration suite can exercise the
-- exact predicate the job runs (pg_cron itself is absent from test Postgres).
-- SECURITY INVOKER (the default): the job executes as the role that scheduled
-- it, the migration owner. EXECUTE is revoked from PUBLIC so neither the
-- PostgREST roles nor the application roles can invoke it.
CREATE OR REPLACE FUNCTION "public"."purge_expired_reading_trails"(retention_days integer DEFAULT 30)
RETURNS integer
LANGUAGE plpgsql
SET search_path = ''
AS $fn$
DECLARE
    removed integer;
BEGIN
    IF retention_days IS NULL OR retention_days < 1 THEN
        RAISE EXCEPTION 'retention_days must be a positive integer';
    END IF;
    DELETE FROM "public"."reading_trail"
    WHERE "started_on" < (CURRENT_DATE - retention_days);
    GET DIAGNOSTICS removed = ROW_COUNT;
    RETURN removed;
END
$fn$;

REVOKE ALL ON FUNCTION "public"."purge_expired_reading_trails"(integer) FROM PUBLIC;

DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS pg_cron;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'pg_cron extension unavailable in this environment (%); skipping reading_trail retention purge scheduling. Supabase-deployed environments have pg_cron and are unaffected.', SQLERRM;
    END;
END
$$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'purge_expired_reading_trails') THEN
            PERFORM cron.unschedule('purge_expired_reading_trails');
        END IF;

        PERFORM cron.schedule(
            'purge_expired_reading_trails',
            '35 3 * * *',
            $job$ SELECT "public"."purge_expired_reading_trails"(30); $job$
        );
    ELSE
        RAISE NOTICE 'pg_cron extension not installed; skipping reading_trail retention purge scheduling (expected on local/test Postgres without the extension; Supabase environments have pg_cron and schedule normally).';
    END IF;
END
$$;
