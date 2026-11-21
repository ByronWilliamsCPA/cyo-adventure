-- WP-2.3 (docs/planning/story-plan-implementation-plan.md), ADR-033 Decision 1:
-- "For on-demand books, a JSON column on StorybookVersion, added by a Supabase
-- migration, written by the worker and never returned by any kid-surface
-- route."
--
-- story_plan holds the Story Plan a version was written from, as
-- StoryPlan.model_dump(mode="json") (src/cyo_adventure/storyplan/models.py).
-- It is an authoring-side record: request-derived text, the fact ledger, the
-- threads. No kid-surface response model selects it (api/library.py,
-- api/reading.py), and tests/unit/test_story_plan_not_on_kid_routes.py pins
-- that no kid route's OpenAPI schema can carry it.
--
-- Purely additive: one nullable column, no default, no backfill. NULL means
-- the version was not built from a plan, which is every version until the
-- WP-2.6 plan fill exists; WP-2.3 plan jobs stop at a checked plan recorded on
-- generation_job.report and create no version.
--
-- Written to be idempotent (ADD COLUMN IF NOT EXISTS, mirroring
-- 20260908000000_add_cover_review_columns.sql), so re-application is a no-op.
--
-- #CRITICAL: timing: apply this migration BEFORE deploying the image that
-- maps the column (db/models.py StorybookVersion.story_plan). The ORM selects
-- every mapped column when it loads a version, so an image against a database
-- without it fails every version read (UndefinedColumn), not only plan jobs.
--
-- Forward-only migration per this project's Supabase CLI convention
-- (ADR-012); no down script.

ALTER TABLE "public"."storybook_version"
    ADD COLUMN IF NOT EXISTS "story_plan" jsonb;

COMMENT ON COLUMN "public"."storybook_version"."story_plan" IS
    'Story Plan (ADR-033) this version was written from, as StoryPlan JSON; NULL when the version was not built from a plan. Authoring-side only: never returned by a kid-surface route. Written by generation.persistence.persist_storybook.';
