-- ADR-021 + ADR-023 P4: extend the cyo_api / cyo_worker service-role grant
-- and policy set to the two tables added by
-- 20260729000000_add_child_profile_personalization.sql and
-- 20260729010000_add_personalization_consent_and_eligibility.sql.
--
-- Why this is a NEW migration rather than an edit to 20260720170100 and
-- 20260720170200: those two are already applied to staging and production,
-- and ADR-012 migrations are forward-only. Editing an applied file changes
-- nothing in a deployed database and desynchronizes the repo from reality.
--
-- #CRITICAL: security: RLS ENABLE with zero policies is deny-all for every
-- non-owner role. Today the app connects as `postgres` (the table owner,
-- which Postgres exempts from RLS), so this migration is a no-op in behavior.
-- At the ADR-021 / WU-10 cutover the app connects as cyo_api, a non-owner:
-- without BOTH the GRANT below and the service_rw policy below, every
-- personalization route fails with permission denied. Two separate axes are
-- required because a GRANT alone still loses to RLS, and a policy alone still
-- loses to the missing GRANT.
-- #VERIFY: tests/integration/test_rls_service_roles.py exercises the
-- cyo_api role against these tables;
-- test_every_rls_table_grants_both_service_roles in that same file asserts
-- that every RLS-enabled table carries a service_rw policy and the matching
-- GRANT, so the next table that gets RLS without either fails a test instead
-- of failing at cutover.

GRANT SELECT, INSERT, UPDATE, DELETE ON
  public.child_profile_personalization,
  public.personalization_disclosure_consent
TO cyo_api, cyo_worker;

-- Same shape as 20260720170200_add_service_role_policies.sql: a permissive
-- FOR ALL policy scoped to the two service roles. USING (true) is correct
-- here because tenant scoping lives in the application query layer
-- (authorize_profile / family_id filtering), not in the policy; the policy
-- exists to restore access that RLS removes, not to add authorization.
-- anon and authenticated deliberately get no policy at all, which leaves the
-- PostgREST path deny-by-default.
DROP POLICY IF EXISTS service_rw ON public.child_profile_personalization;
CREATE POLICY service_rw ON public.child_profile_personalization
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS service_rw ON public.personalization_disclosure_consent;
CREATE POLICY service_rw ON public.personalization_disclosure_consent
  FOR ALL TO cyo_api, cyo_worker USING (true) WITH CHECK (true);
