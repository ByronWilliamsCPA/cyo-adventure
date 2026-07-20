-- ADR-021: dedicated least-privilege service roles for the API (cyo_api) and
-- the RQ workers (cyo_worker). Created NOLOGIN; a login password is set
-- out-of-band per environment (Supabase dashboard SQL editor), never in this
-- file or anywhere in git.
--
-- Idempotent on purpose: Postgres has no CREATE ROLE IF NOT EXISTS, roles are
-- cluster-wide (not per-database), and the integration harness applies this
-- chain to sibling databases on one cluster, so a bare CREATE ROLE would fail
-- on the second application. Forward-only safe (ADR-012): purely additive,
-- grants only, no DDL privileges, no role-management privileges, and the
-- postgres owner role is untouched.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cyo_api') THEN
    CREATE ROLE cyo_api NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cyo_worker') THEN
    CREATE ROLE cyo_worker NOLOGIN;
  END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO cyo_api, cyo_worker;

-- Identical DML grant set for both roles initially (ADR-021 decision 1;
-- per-role tightening is explicitly deferred). Table list is verbatim the 19
-- tables from 20260711200745_enable_rls_all_tables.sql, plus three tables
-- that later migrations independently enabled RLS on with the same
-- deny-by-default posture: device_grant (20260713180000_add_device_grants.sql),
-- family_connection (20260716120000_admin_user_management.sql), and
-- kid_flag (20260717120000_add_kid_flag.sql). Without these grants the
-- non-owner cyo_api/cyo_worker roles get permission-denied on all three at
-- the WU-10 cutover, breaking device-authorized kid login and family/flag
-- access.
GRANT SELECT, INSERT, UPDATE, DELETE ON
  public.child_profile,
  public.completion,
  public.concept,
  public.device_grant,
  public.family,
  public.family_connection,
  public.generation_job,
  public.kid_flag,
  public.moderation_setting,
  public.moderation_threshold,
  public.moderation_threshold_audit,
  public.pipeline_event,
  public.provider_model_allowlist,
  public.provider_model_allowlist_audit,
  public.rating,
  public.reading_state,
  public.series,
  public.story_request,
  public.storybook,
  public.storybook_assignment,
  public.storybook_version,
  public."user"
TO cyo_api, cyo_worker;

-- Defensive: no sequences exist today (every PK is a UUID or an
-- application-supplied composite; verified against 20260710000000_baseline.sql
-- and db/models.py), so this is a no-op now, but a future identity column
-- failing with a permission error at runtime is worse than a harmless grant.
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cyo_api, cyo_worker;
