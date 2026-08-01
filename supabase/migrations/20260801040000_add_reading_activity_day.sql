-- W3.3 (kid-appeal-implementation-plan.md; gamification-recommendation-2026-08-01.md
-- section 2.4/5): day-grain active reading time substrate. Powers the future
-- weekly ring (W3.4) and the lifetime "Forty Days of Stories" badge (W3.5);
-- this migration creates only the table, RLS, and cascade tax -- the ring and
-- badge themselves are out of scope here (plan v1 cut line, recommendation
-- section 7 Q5). The guardian-facing minutes/day and days/week extension to
-- GET /families/me/reading-summary reads this table but adds no columns of
-- its own.
--
-- Column set: child_profile_id, activity_date, active_seconds, updated_at
-- match the recommendation's section 5 data-model sketch verbatim; last_flush_id
-- is an addition the kid-appeal-implementation-plan.md W3.3 task explicitly
-- authorizes ("a simple per-(profile, date) last_flush_id column on the row is
-- acceptable" for idempotency), mirroring reading_state.last_event_id.
--
-- Retention: the plan's "Plan defaults" item 2 adopts a 12-month retention
-- default for these day-grain rows (detail rolls into a running total after
-- that window; lifetime days-read survives), to be entered into the ADR-018
-- counsel bundle and the privacy model's data classification. Enforcing that
-- rollover (a scheduled purge/aggregate job, mirroring
-- 20260720150000_add_retention_purge_jobs.sql's pattern for other retained
-- data) is explicitly OUT OF SCOPE for this migration; only the table and its
-- cascade/RLS exist here.
--
-- Table and REFERENCES targets are schema-qualified ("public".*): see
-- 20260729000000_add_child_profile_personalization.sql's header comment for
-- why (the baseline migration empties search_path for the rest of the
-- session, so every later migration that creates or alters a table must
-- schema-qualify or fail with "no schema has been selected to create in").

CREATE TABLE IF NOT EXISTS "public"."reading_activity_day" (
    child_profile_id UUID NOT NULL REFERENCES "public"."child_profile"(id) ON DELETE CASCADE,
    activity_date DATE NOT NULL,
    active_seconds INTEGER NOT NULL DEFAULT 0,
    last_flush_id VARCHAR(64),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (child_profile_id, activity_date),
    CONSTRAINT ck_reading_activity_day_active_seconds CHECK (active_seconds >= 0)
);

-- #CRITICAL: security: RLS is the ONLY gate on the PostgREST path (see
-- 20260729000000_add_child_profile_personalization.sql's identical note); a
-- new table that skips ENABLE ROW LEVEL SECURITY is a silent hole in the
-- "every public table has RLS" invariant established by
-- 20260711200745_enable_rls_all_tables.sql.
-- #VERIFY: tests/integration/test_rls_service_roles.py::
-- test_no_public_table_ships_without_row_level_security asserts that no
-- table in `public` has rowsecurity = false.
ALTER TABLE "public"."reading_activity_day" ENABLE ROW LEVEL SECURITY;

-- Tier 2 (blanket), not Tier 1 family-scoped: this table is keyed by
-- child_profile_id, not a direct family_id column, so a flat per-family
-- predicate would need a join. Per ADR-022's Technical Debt clause (see
-- 20260724120000_scoped_rls_tier1_family_scoping.sql's header comment) it is
-- demoted to Tier 2 alongside reading_state/completion/rating, which the app
-- layer (api/deps.py::authorize_profile, POST /me/reading-time's own-profile
-- gate) already scopes.
-- DROP POLICY IF EXISTS + CREATE POLICY keeps re-application idempotent with
-- no down-migration (ADR-012 forward-only).
DROP POLICY IF EXISTS service_rw ON "public"."reading_activity_day";
CREATE POLICY service_rw ON "public"."reading_activity_day"
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

-- RLS policies gate rows only once the GRANT layer admits the role at all;
-- both service roles need the table-level grants too (the omission fails
-- tests/integration/test_rls_service_roles.py::
-- test_every_rls_table_grants_both_service_roles).
GRANT SELECT, INSERT, UPDATE, DELETE ON
  "public"."reading_activity_day" TO cyo_api, cyo_worker;

-- Forward-only migration per this project's Supabase CLI convention
-- (ADR-012); no down script.
