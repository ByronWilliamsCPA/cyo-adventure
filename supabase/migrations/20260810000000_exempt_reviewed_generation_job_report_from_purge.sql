-- ADR-007 amendment (2026-08-10): exempt a human-reviewed generation job's
-- raw output from the 30-day sweep registered by
-- 20260718000000_add_report_retention_purge.sql. This migration amends that
-- job's predicate in place (same "purge_generation_job_report" job name,
-- unschedule-then-reschedule); it does not touch the 20260718000000 file or
-- publishing/service.py::approve's separate on-publish purge, both of which
-- are left exactly as they are.
--
-- Why: a review-scorecard calibration corpus needs a generation job's raw
-- output paired with the human decision made about the storybook it
-- produced (approved/published, or sent back with a reason). The unqualified
-- 30-day sweep destroys that pairing for any job whose storybook took longer
-- than 30 days to reach a decision, one day at a time.
--
-- New predicate: a "public"."generation_job" row is exempt from the sweep
-- (its "report" is left alone, however old) when its "public"."storybook"
-- row's status shows a human review decision was reached at some point:
-- "published" or "archived" (both mean an approve happened; archived is a
-- published book pulled later) or "needs_revision" (a send-back happened).
-- "draft" and "in_review" are NOT exempt: neither has had a decision yet, so
-- the default 30-day retention in ADR-007 still applies to them, same as a
-- job whose storybook_id never resolves to a row at all (a job that failed
-- before any storybook existed -- see GenerationJob's class docstring).
--
-- #ASSUME: data-integrity: exemption is keyed on the STORYBOOK's status, not
-- the individual job/version. A storybook can accumulate several
-- generation_job rows across a submit -> send-back -> resubmit -> approve
-- cycle; once any decision is reached, every job tied to that storybook_id
-- is preserved, including an earlier sent-back version's report -- exactly
-- the "what did the reviewer see when they said no" record the calibration
-- corpus needs. This is deliberately coarser than per-version and is the
-- documented scope of this exemption.
-- #VERIFY: tests/unit/test_report_retention.py::
-- test_amendment_migration_exempts_reviewed_storybook_statuses and
-- test_amendment_migration_keeps_default_window_for_undecided_storybooks.
--
-- #CRITICAL: external resources: same pg_cron caveat as
-- 20260718000000_add_report_retention_purge.sql -- pg_cron is a
-- Supabase-managed extension present in every deployed environment, but
-- typically absent on local/test/CI Postgres. This migration must never
-- hard-fail there, or every migration after it in the same
-- `supabase db reset`/CI run would be blocked.
-- #VERIFY: CREATE EXTENSION is wrapped in the same exception-catching DO
-- block as the original migration, falling back to RAISE NOTICE; the
-- unschedule/reschedule block only runs when pg_extension shows pg_cron
-- actually installed.

-- No new index is required for the added NOT EXISTS lookup: it probes
-- "public"."storybook" by "id", which is that table's primary key and
-- therefore already backed by a unique btree index. The existing
-- "ix_generation_job_status_updated_at" (status, updated_at) from
-- 20260718000000_add_report_retention_purge.sql still backs this job's main
-- predicate unchanged; re-declared here with IF NOT EXISTS purely so this
-- migration is self-contained and safe to re-run on its own.
create index if not exists "ix_generation_job_status_updated_at"
    on "public"."generation_job" using "btree" ("status", "updated_at");

DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS pg_cron;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'pg_cron extension unavailable in this environment (%); skipping generation_job.report retention purge rescheduling. Supabase-deployed environments have pg_cron and are unaffected.', SQLERRM;
    END;
END
$$;

-- Idempotent by job name: unschedule the existing 'purge_generation_job_report'
-- registration (from 20260718000000, or from a prior run of this same
-- migration) before scheduling the amended query, so re-applying this
-- migration never leaves duplicate cron.job rows and never runs both the old
-- and new predicate.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'purge_generation_job_report') THEN
            PERFORM cron.unschedule('purge_generation_job_report');
        END IF;

        PERFORM cron.schedule(
            'purge_generation_job_report',
            '0 3 * * *',
            $job$
            UPDATE "public"."generation_job" AS "gj"
            SET "report" = NULL
            WHERE "gj"."report" IS NOT NULL
              AND "gj"."status" IN ('passed', 'needs_review', 'failed')
              AND "gj"."updated_at" < (now() - interval '30 days')
              AND NOT EXISTS (
                  SELECT 1
                  FROM "public"."storybook" AS "sb"
                  WHERE "sb"."id" = "gj"."storybook_id"
                    AND "sb"."status" IN ('published', 'archived', 'needs_revision')
              );
            $job$
        );
    ELSE
        RAISE NOTICE 'pg_cron extension not installed; skipping reschedule of purge_generation_job_report (expected on local/test Postgres without the extension; Supabase environments have pg_cron and schedule normally).';
    END IF;
END
$$;
