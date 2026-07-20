-- WS-7 D2 (K19): persist the request interpretation, plus its declined/blocked
-- retention purge. Adds "public"."story_request"."interpretation" (nullable
-- JSONB), the read model for the per-request reflection object that WS-7's
-- general layer (submission-time) and refined layer (fill-time) write. The
-- column is added nullable with NO backfill: pre-WS-7 requests simply stay
-- NULL. The column carries Phase-3 (GDPR/COPPA remediation) obligations
-- enumerated in the ORM docstring (db/models.py::StoryRequest.interpretation):
-- deletion rides the parent story_request row, the guardian export must include
-- it, and this migration adds the retention half of that scope.
--
-- Retention (design section 8.4): the remediation plan purges a declined or
-- blocked request's raw request_text 30 days after decision, keeping only the
-- redacted category/verdict. Interpretation `element` phrases are the only
-- premise-derived free text in the object, so the same rule applies: a daily
-- pg_cron job nulls every element's `element` key on declined/blocked rows past
-- the 30-day mark, keeping the dispositions, reasons, and template-rendered
-- kid/guardian texts (catalog prose, not premise content, matching the
-- "redacted category/verdict" retention posture) plus the top-level
-- kid_summary/guardian_summary/etc. In practice this is mostly
-- defense-in-depth: the general layer (design section 4) stores no
-- premise-derived `element` text (a blocked row never carries one at all, CR-1;
-- an advisory/band element is element=None; only a guardian-banned-theme echo
-- is a non-null `element`, and that is guardian vocabulary, not premise text).
-- The refined layer (fill-time) can carry premise-derived element phrases, so
-- the rule is honored literally per 8.4 regardless.

ALTER TABLE "public"."story_request"
    ADD COLUMN IF NOT EXISTS "interpretation" jsonb;

-- #CRITICAL: external resources: pg_cron ships as a Supabase-managed extension
-- in every deployed environment, but local/test Postgres (and any non-Supabase
-- CI database) typically does not have it installed. This migration must never
-- hard-fail on such an environment, or every other migration after it in the
-- same `supabase db reset`/CI run would be blocked by an unrelated scheduling
-- feature. Mirrors 20260718000000_add_report_retention_purge.sql exactly.
-- #VERIFY: CREATE EXTENSION is wrapped in a nested DO block that catches any
-- exception and falls back to RAISE NOTICE; the schedule/unschedule block only
-- runs when "pg_extension" shows pg_cron actually installed, and is itself
-- read-only with respect to "public"."story_request" (it only registers a
-- cron.job row; the nulling UPDATE runs later, on the cron worker's own
-- schedule, never inside this migration transaction).
DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS pg_cron;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'pg_cron extension unavailable in this environment (%); skipping story_request.interpretation element-retention purge scheduling. Supabase-deployed environments have pg_cron and are unaffected.', SQLERRM;
    END;
END
$$;

-- Idempotent by job name: unschedule any existing registration for
-- 'purge_story_request_interpretation_elements' before scheduling it fresh, so
-- re-running this migration (or a future migration that needs to change the
-- schedule) never leaves duplicate cron.job rows. Guarded by the same
-- pg_extension check so this block is a no-op wherever pg_cron did not install
-- above. The purge UPDATE only touches declined/blocked rows whose decision (or
-- creation, when never reviewed) is older than 30 days AND that still have at
-- least one element with a non-null `element` phrase, so the job is a no-op
-- once a row is purged (it never rewrites an already-purged row).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        IF EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'purge_story_request_interpretation_elements') THEN
            PERFORM cron.unschedule('purge_story_request_interpretation_elements');
        END IF;

        PERFORM cron.schedule(
            'purge_story_request_interpretation_elements',
            '0 4 * * *',
            $job$
            UPDATE "public"."story_request"
            SET "interpretation" = jsonb_set(
                "interpretation",
                '{elements}',
                (
                    SELECT coalesce(
                        jsonb_agg(elem || '{"element": null}'::jsonb),
                        '[]'::jsonb
                    )
                    FROM jsonb_array_elements("interpretation" -> 'elements') AS elem
                )
            )
            WHERE "interpretation" IS NOT NULL
              AND "status" IN ('blocked', 'declined')
              AND coalesce("reviewed_at", "created_at") < (now() - interval '30 days')
              AND EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements("interpretation" -> 'elements') AS e
                  WHERE (e ->> 'element') IS NOT NULL
              );
            $job$
        );
    ELSE
        RAISE NOTICE 'pg_cron extension not installed; skipping schedule of purge_story_request_interpretation_elements (expected on local/test Postgres without the extension; Supabase environments have pg_cron and schedule normally).';
    END IF;
END
$$;
