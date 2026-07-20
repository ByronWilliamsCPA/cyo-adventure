-- Phase 4c: two more scheduled purge jobs against the retention table
-- accepted 2026-07-20 (coppa-gdpr-remediation-plan.md Section 5), mirroring
-- 20260718000000_add_report_retention_purge.sql's pattern (idempotent
-- pg_cron scheduling that degrades gracefully to a RAISE NOTICE on any
-- Postgres without the extension, e.g. local/test/CI).
--
-- 1. purge_blocked_declined_story_request_text: blocked or declined
--    "public"."story_request" rows keep their raw "request_text" for 30
--    days from the decision (COALESCE("reviewed_at", "created_at") --
--    a bright-line-blocked row is never guardian-reviewed, so it has no
--    "reviewed_at"; a guardian-declined row does), then the raw text is
--    overwritten with a fixed placeholder. NOT a NULL: "request_text" is
--    NOT NULL by design (every row has a request), so purging replaces the
--    value rather than requiring a nullability change to the column.
--    api/story_requests.py's existing read-layer redaction of blocked rows
--    is unaffected; this is the underlying data, not the view.
--
-- 2. purge_stale_deactivated_profile_activity: per the accepted retention
--    table's "life of the active profile, plus 30-90 days after
--    deactivation" window for reading_state/completion/rating, DELETEs
--    those three tables' rows for any "public"."child_profile" deactivated
--    more than 90 days ago (the upper end of the accepted range, favoring
--    data availability). The profile row itself is untouched: a guardian
--    who wants the profile gone entirely already has
--    DELETE /api/v1/profiles/{id} (Phase 3b); this job only prunes stale
--    activity data for a profile that was deactivated, not deleted.

-- Back both purge queries with the indexes their WHERE clauses need,
-- unconditional and independent of pg_cron availability (mirrors
-- 20260718000000_add_report_retention_purge.sql's ix_generation_job_status_updated_at).
create index if not exists "ix_story_request_status_reviewed_at"
    on "public"."story_request" using "btree" ("status", "reviewed_at");

create index if not exists "ix_child_profile_deactivated_at"
    on "public"."child_profile" using "btree" ("deactivated_at")
    where ("deactivated_at" is not null);

DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS pg_cron;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'pg_cron extension unavailable in this environment (%); skipping Phase 4c retention purge scheduling. Supabase-deployed environments have pg_cron and are unaffected.', SQLERRM;
    END;
END
$$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'purge_blocked_declined_story_request_text') THEN
            PERFORM cron.unschedule('purge_blocked_declined_story_request_text');
        END IF;

        PERFORM cron.schedule(
            'purge_blocked_declined_story_request_text',
            '0 3 * * *',
            $job$
            UPDATE "public"."story_request"
            SET "request_text" = '[purged: 30-day retention policy, remediation plan Section 5]'
            WHERE "status" IN ('blocked', 'declined')
              AND "request_text" <> '[purged: 30-day retention policy, remediation plan Section 5]'
              AND COALESCE("reviewed_at", "created_at") < (now() - interval '30 days');
            $job$
        );

        IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'purge_stale_deactivated_profile_activity') THEN
            PERFORM cron.unschedule('purge_stale_deactivated_profile_activity');
        END IF;

        PERFORM cron.schedule(
            'purge_stale_deactivated_profile_activity',
            '15 3 * * *',
            $job$
            WITH "stale_profiles" AS (
                SELECT "id" FROM "public"."child_profile"
                WHERE "deactivated_at" IS NOT NULL
                  AND "deactivated_at" < (now() - interval '90 days')
            )
            DELETE FROM "public"."reading_state"
            WHERE "child_profile_id" IN (SELECT "id" FROM "stale_profiles");
            $job$
        );

        -- Two further DELETEs (completion, rating) scheduled as their own
        -- cron.job rows rather than crammed into one multi-statement job:
        -- cron.schedule's $job$ body is a single SQL statement, and separate
        -- jobs also let one table's purge be paused/inspected independently.
        IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'purge_stale_deactivated_profile_completions') THEN
            PERFORM cron.unschedule('purge_stale_deactivated_profile_completions');
        END IF;

        PERFORM cron.schedule(
            'purge_stale_deactivated_profile_completions',
            '20 3 * * *',
            $job$
            DELETE FROM "public"."completion"
            WHERE "child_profile_id" IN (
                SELECT "id" FROM "public"."child_profile"
                WHERE "deactivated_at" IS NOT NULL
                  AND "deactivated_at" < (now() - interval '90 days')
            );
            $job$
        );

        IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'purge_stale_deactivated_profile_ratings') THEN
            PERFORM cron.unschedule('purge_stale_deactivated_profile_ratings');
        END IF;

        PERFORM cron.schedule(
            'purge_stale_deactivated_profile_ratings',
            '25 3 * * *',
            $job$
            DELETE FROM "public"."rating"
            WHERE "child_profile_id" IN (
                SELECT "id" FROM "public"."child_profile"
                WHERE "deactivated_at" IS NOT NULL
                  AND "deactivated_at" < (now() - interval '90 days')
            );
            $job$
        );
    ELSE
        RAISE NOTICE 'pg_cron extension not installed; skipping Phase 4c retention purge job scheduling (expected on local/test Postgres without the extension; Supabase environments have pg_cron and schedule normally).';
    END IF;
END
$$;
