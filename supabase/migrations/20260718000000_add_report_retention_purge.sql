-- ADR-007 / Phase 5 (M5 register item S10): scheduled purge of
-- "public"."generation_job"."report", the raw multi-stage LLM output
-- retained for debugging. ADR-007 decided a 30-calendar-day retention
-- window from "updated_at" (the final status transition); the on-publish
-- half of the purge is enforced separately, in the same transaction as the
-- publish write, by src/cyo_adventure/publishing/service.py::approve. This
-- migration covers the time-based half: a daily pg_cron job nulls "report"
-- for jobs that reached a terminal status ('passed', 'needs_review',
-- 'failed') more than 30 days ago. 'queued', 'running', and
-- 'awaiting_manual_fill' are excluded: they are not "completed" states (see
-- db/models.py's _GENERATION_JOB_STATUS_VALUES comment), so their "report"
-- is either not yet written or intentionally parked pending a human fill.
--
-- #CRITICAL: external resources: pg_cron ships as a Supabase-managed
-- extension in every deployed environment, but local/test Postgres (and any
-- non-Supabase CI database) typically does not have it installed. This
-- migration must never hard-fail on such an environment, or every other
-- migration after it in the same `supabase db reset`/CI run would be
-- blocked by an unrelated scheduling feature.
-- #VERIFY: CREATE EXTENSION is wrapped in a nested DO block that catches any
-- exception and falls back to RAISE NOTICE; the schedule/unschedule block
-- only runs when "pg_extension" shows pg_cron actually installed, and is
-- itself read-only with respect to "public"."generation_job" (it only
-- registers a cron.job row; the nulling UPDATE runs later, on the cron
-- worker's own schedule, never inside this migration transaction).

-- ADR-007's Implementation Notes require the purge query to use an index on
-- (updated_at, status) to avoid a full-table scan on large deployments;
-- (status, updated_at) here serves the same predicate (equality on status,
-- range on updated_at) and also backs the plain "WHERE status = ..." lookups
-- generation.py already does elsewhere. Unconditional and independent of
-- pg_cron availability, since it is useful with or without the scheduled job.
create index if not exists "ix_generation_job_status_updated_at"
    on "public"."generation_job" using "btree" ("status", "updated_at");

DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS pg_cron;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'pg_cron extension unavailable in this environment (%); skipping generation_job.report retention purge scheduling. Supabase-deployed environments have pg_cron and are unaffected.', SQLERRM;
    END;
END
$$;

-- Idempotent by job name: unschedule any existing registration for
-- 'purge_generation_job_report' before scheduling it fresh, so re-running
-- this migration (or a future migration that needs to change the schedule)
-- never leaves duplicate cron.job rows. Guarded by the same pg_extension
-- check so this block is a no-op wherever pg_cron did not install above.
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
            UPDATE "public"."generation_job"
            SET "report" = NULL
            WHERE "report" IS NOT NULL
              AND "status" IN ('passed', 'needs_review', 'failed')
              AND "updated_at" < (now() - interval '30 days');
            $job$
        );
    ELSE
        RAISE NOTICE 'pg_cron extension not installed; skipping schedule of purge_generation_job_report (expected on local/test Postgres without the extension; Supabase environments have pg_cron and schedule normally).';
    END IF;
END
$$;
