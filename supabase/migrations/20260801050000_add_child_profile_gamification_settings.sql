-- W3.4 (kid-appeal-implementation-plan.md; gamification-recommendation-
-- 2026-08-01.md section 4/P-A): per-profile gamification settings.
--
-- ring_enabled / ring_goal_days are nullable-means-band-default (mirrors
-- child_profile.banned_themes' "NULL = no override" contract): a profile a
-- guardian has never touched resolves to the P-A band table
-- (src/cyo_adventure/api/progress.py::_resolve_ring_settings), never to
-- "off"/"0" by column absence. ring_goal_days is capped at 6 by CHECK
-- (gamification recommendation "Plan defaults" item 4: one guaranteed free
-- day at every band); the API layer enforces the same bound so a request
-- never reaches the CHECK in the first place, but the CHECK is the
-- structural backstop (mirrors ck_cpp_ring2_ceiling's reasoning: a DB
-- constraint holds even if a future write path bypasses application
-- validation).
--
-- badges_enabled / time_capture_paused carry real (non-band-dependent)
-- defaults, so they use the ADD COLUMN ... DEFAULT ... NOT NULL form
-- directly (mirrors real_name_ring1_enabled/real_name_ring2_enabled in
-- 20260729000000_add_child_profile_personalization.sql) rather than the
-- nullable-then-backfill dance reduce_motion used, since these two DO carry
-- a persisted server_default on the ORM side
-- (db/models.py::ChildProfile.badges_enabled/time_capture_paused).
--
-- Table is schema-qualified ("public".*): see
-- 20260729000000_add_child_profile_personalization.sql's header comment for
-- why (the baseline migration empties search_path for the rest of the
-- session).

ALTER TABLE "public"."child_profile"
    ADD COLUMN IF NOT EXISTS ring_enabled BOOLEAN,
    ADD COLUMN IF NOT EXISTS ring_goal_days INTEGER,
    ADD COLUMN IF NOT EXISTS badges_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS time_capture_paused BOOLEAN NOT NULL DEFAULT FALSE;

-- DROP-then-ADD keeps re-application idempotent, matching the FK migration
-- pattern in 20260801000000_add_story_request_resulting_storybook_id.sql
-- (the ADD COLUMN lines above are already IF NOT EXISTS-guarded).
ALTER TABLE "public"."child_profile"
    DROP CONSTRAINT IF EXISTS ck_child_profile_ring_goal_days_range;
ALTER TABLE "public"."child_profile"
    ADD CONSTRAINT ck_child_profile_ring_goal_days_range
        CHECK (ring_goal_days IS NULL OR ring_goal_days BETWEEN 1 AND 6);

-- Forward-only migration per this project's Supabase CLI convention
-- (ADR-012); no down script.
