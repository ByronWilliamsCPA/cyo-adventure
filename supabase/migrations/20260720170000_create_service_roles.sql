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
-- tables from 20260711200745_enable_rls_all_tables.sql.
GRANT SELECT, INSERT, UPDATE, DELETE ON
  public.child_profile,
  public.completion,
  public.concept,
  public.family,
  public.generation_job,
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
