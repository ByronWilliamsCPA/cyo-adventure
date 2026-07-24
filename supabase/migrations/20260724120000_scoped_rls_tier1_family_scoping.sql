-- ADR-022: Tier 1 scoped RLS. Replace the blanket service_rw policy on the
-- highest-sensitivity, never-cross-family children's-PII tables with a
-- role-split pair: cyo_worker keeps blanket access; cyo_api gets a flat,
-- fail-closed per-family predicate. This narrows ADR-021's blanket-USING(true)
-- posture (add_service_role_policies.sql) for exactly these tables, and amends
-- ADR-009 point 7 for them only ("never the primary model" still holds; RLS is
-- a dumb second backstop behind the FastAPI Principal layer, not a
-- re-implementation of the sharing/admin rules).
--
-- Tier 1 tables here are ONLY those that carry a direct, NOT NULL family_id
-- column, so the predicate stays a flat comparison with no join:
--   child_profile, story_request, device_grant.
-- The other ADR-022 candidates (reading_state, completion, rating) are scoped
-- in the schema by child_profile_id, not family_id, so a flat predicate is
-- impossible without a subquery/join. Per ADR-022's Technical Debt clause they
-- are DEMOTED to Tier 2 (left blanket) pending a denormalized family_id, rather
-- than carrying a per-row join predicate. They keep their existing service_rw
-- policy untouched.
--
-- Predicate semantics:
--   USING/WITH CHECK ( family_id::text = current_setting('app.family_id', true)
--                      OR current_setting('app.is_admin', true) = 'true' )
--   * current_setting(name, true) returns NULL when the GUC is unset, and
--     "family_id = NULL" is never true, so a request that never set context
--     matches zero rows: FAIL-CLOSED (a zero-row outage, never a cross-family
--     leak). The request path sets the GUC via set_config(..., is_local => true)
--     in api/deps.py::require_principal (see core/database.py::
--     apply_family_rls_context).
--   * The app.is_admin escape hatch is the ONLY cross-family reach in the
--     predicate: an admin/moderation principal (ADR-016) reads across families.
--     All other cross-family logic (the three-ring sharing graph) stays in the
--     app layer and never touches these Tier 1 tables, so no graph traversal is
--     encoded in SQL here.
--
-- #CRITICAL: security: this migration is a NO-OP for the running app until the
-- ADR-021 least-privilege cutover. RLS never applies to a table's owner and
-- FORCE ROW LEVEL SECURITY is deliberately not set (see
-- 20260711200745_enable_rls_all_tables.sql), so while the app still connects as
-- the postgres owner these policies do not affect it. Enforcement activates the
-- moment the app connects as the non-owner cyo_api role. Applying this ahead of
-- the cutover is therefore safe and changes no live behavior.
-- #VERIFY: tests/integration/test_rls_tier1_enforcement.py runs the suite as
-- cyo_api and asserts fail-closed (unset context = zero rows) and per-family
-- scoping on these tables; it self-activates once this migration is applied to
-- the test schema.
--
-- DROP POLICY IF EXISTS + CREATE POLICY keeps re-application idempotent with no
-- down-migration (ADR-012 forward-only). Must run after
-- 20260720170200_add_service_role_policies.sql (it supersedes service_rw on
-- these three tables); the timestamps enforce that ordering. The roles already
-- exist (20260720170100_create_service_roles.sql) and the GRANTs are unchanged.

-- child_profile: a per-child reading profile (display name, age band, caps).
DROP POLICY IF EXISTS service_rw ON public.child_profile;
DROP POLICY IF EXISTS worker_rw ON public.child_profile;
DROP POLICY IF EXISTS family_scoped ON public.child_profile;
CREATE POLICY worker_rw ON public.child_profile
  FOR ALL TO cyo_worker USING (true) WITH CHECK (true);
CREATE POLICY family_scoped ON public.child_profile
  FOR ALL TO cyo_api
  USING (
    family_id::text = current_setting('app.family_id', true)
    OR current_setting('app.is_admin', true) = 'true'
  )
  WITH CHECK (
    family_id::text = current_setting('app.family_id', true)
    OR current_setting('app.is_admin', true) = 'true'
  );

-- story_request: a guardian/child story request (brief, screening, plan).
DROP POLICY IF EXISTS service_rw ON public.story_request;
DROP POLICY IF EXISTS worker_rw ON public.story_request;
DROP POLICY IF EXISTS family_scoped ON public.story_request;
CREATE POLICY worker_rw ON public.story_request
  FOR ALL TO cyo_worker USING (true) WITH CHECK (true);
CREATE POLICY family_scoped ON public.story_request
  FOR ALL TO cyo_api
  USING (
    family_id::text = current_setting('app.family_id', true)
    OR current_setting('app.is_admin', true) = 'true'
  )
  WITH CHECK (
    family_id::text = current_setting('app.family_id', true)
    OR current_setting('app.is_admin', true) = 'true'
  );

-- device_grant: a revocable, family-scoped device authorization (ADR-014).
DROP POLICY IF EXISTS service_rw ON public.device_grant;
DROP POLICY IF EXISTS worker_rw ON public.device_grant;
DROP POLICY IF EXISTS family_scoped ON public.device_grant;
CREATE POLICY worker_rw ON public.device_grant
  FOR ALL TO cyo_worker USING (true) WITH CHECK (true);
CREATE POLICY family_scoped ON public.device_grant
  FOR ALL TO cyo_api
  USING (
    family_id::text = current_setting('app.family_id', true)
    OR current_setting('app.is_admin', true) = 'true'
  )
  WITH CHECK (
    family_id::text = current_setting('app.family_id', true)
    OR current_setting('app.is_admin', true) = 'true'
  );
