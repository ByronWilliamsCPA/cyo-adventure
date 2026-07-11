-- Enable Row Level Security (RLS) on every public table as defense-in-depth
-- against the Supabase PostgREST anon/authenticated data path (issue #125).
--
-- Context: the FastAPI backend connects to Postgres via the session pooler
-- as the "postgres" role. Postgres exempts table owners (and superusers)
-- from RLS regardless of policies, so enabling RLS here does not change any
-- backend query behavior; it only closes the PostgREST anon/authenticated
-- path, which currently has zero client usage (verified below).
--
-- #CRITICAL: security: this migration assumes the application database role
-- is "postgres" (the table owner), which Postgres always exempts from RLS.
-- If the app's DB connection role is ever changed to a non-owner role (for
-- example a scoped "app_user"), RLS enabled here WILL start restricting
-- backend queries, since a non-owner role with RLS enabled and no policies
-- denies all rows by default.
-- #VERIFY: before changing the app's DB connection role away from
-- "postgres", confirm the new role in src/cyo_adventure/core/config.py /
-- core/database.py and add explicit policies for it first.
--
-- Deliberately NOT using FORCE ROW LEVEL SECURITY: FORCE would also apply
-- RLS restrictions to the table owner ("postgres"), and with zero policies
-- defined that would lock the application itself out of every table. Plain
-- ENABLE ROW LEVEL SECURITY leaves owner/superuser access intact while
-- still gating the anon/authenticated PostgREST roles, which is the point
-- of this migration.
--
-- No anon/authenticated policies are added, on purpose: this is a
-- deny-by-default posture for PostgREST. No client in this codebase uses
-- PostgREST; the only supabase-js usage
-- (frontend/src/auth/supabaseClient.ts, frontend/src/auth/AuthContext.tsx)
-- is Auth (GoTrue) only: auth.getSession, auth.onAuthStateChange,
-- auth.signInWithOAuth, auth.signInWithPassword, auth.signOut. A
-- repo-wide grep for ".from(" against the supabase client found no
-- PostgREST table access anywhere in frontend/src/ (verified 2026-07-11:
-- frontend uses the anon key for Auth only). The child-session design
-- (P6-04, built in parallel) mints backend JWTs rather than issuing
-- Supabase client sessions to kid readers, so this deny-by-default posture
-- holds for R2.
--
-- Table list: every table created by the Supabase baseline migration
-- (20260710000000_baseline.sql), 19 total. This is a superset of the 13
-- tables named in issue #125's original advisory: 6 additional tables
-- (moderation_setting, moderation_threshold, moderation_threshold_audit,
-- pipeline_event, provider_model_allowlist, provider_model_allowlist_audit)
-- plus "series" (7 total beyond the advisor's 13) were added by migrations
-- that landed after the advisory was written. "alembic_version" from the
-- advisor's list is intentionally excluded here: it was dropped in
-- 20260711031627_drop_alembic_version.sql, which always applies before this
-- migration (earlier timestamp), so the table no longer exists by the time
-- this one runs.

ALTER TABLE IF EXISTS public.child_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.completion ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.concept ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.family ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.generation_job ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.moderation_setting ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.moderation_threshold ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.moderation_threshold_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.pipeline_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.provider_model_allowlist ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.provider_model_allowlist_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.rating ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.reading_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.series ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.story_request ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.storybook ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.storybook_assignment ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public.storybook_version ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS public."user" ENABLE ROW LEVEL SECURITY;
