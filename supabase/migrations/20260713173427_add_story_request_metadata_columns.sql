-- Add story_request columns that are present in the baseline schema
-- (supabase/migrations/20260710000000_baseline.sql) but were never applied
-- to production: the baseline migration is recorded as applied in
-- supabase_migrations.schema_migrations, yet these columns do not exist on
-- the live database. Root-caused via GET /v1/story-requests and
-- GET /v1/admin/story-requests both returning 500
-- (asyncpg.exceptions.UndefinedColumnError: story_request.initiator_role
-- does not exist).

ALTER TABLE "public"."story_request"
    ADD COLUMN IF NOT EXISTS "initiator_role" character varying(16) DEFAULT 'child'::character varying NOT NULL,
    ADD COLUMN IF NOT EXISTS "age_band" character varying(16),
    ADD COLUMN IF NOT EXISTS "length" character varying(16),
    ADD COLUMN IF NOT EXISTS "narrative_style" character varying(16) DEFAULT 'prose'::character varying NOT NULL,
    ADD COLUMN IF NOT EXISTS "series_id" "uuid",
    ADD COLUMN IF NOT EXISTS "anchor_storybook_id" character varying(120),
    ADD COLUMN IF NOT EXISTS "proposed_series_title" character varying(120);

-- age_band is NOT NULL in the baseline with no default. Backfill any row
-- written before this migration from its requesting profile's age_band
-- (the closest available source of truth for what the request was actually
-- scoped to) before enforcing NOT NULL.
UPDATE "public"."story_request" sr
SET "age_band" = cp."age_band"
FROM "public"."child_profile" cp
WHERE sr."profile_id" = cp."id"
  AND sr."age_band" IS NULL;

ALTER TABLE "public"."story_request"
    ALTER COLUMN "age_band" SET NOT NULL;

ALTER TABLE "public"."story_request"
    ADD CONSTRAINT "ck_story_request_age_band" CHECK ((("age_band")::"text" = ANY ((ARRAY['3-5'::character varying, '5-8'::character varying, '8-11'::character varying, '10-13'::character varying, '13-16'::character varying, '16+'::character varying])::"text"[]))),
    ADD CONSTRAINT "ck_story_request_anchor_requires_series" CHECK ((("anchor_storybook_id" IS NULL) OR ("series_id" IS NOT NULL))),
    ADD CONSTRAINT "ck_story_request_initiator_role" CHECK ((("initiator_role")::"text" = ANY ((ARRAY['child'::character varying, 'guardian'::character varying, 'admin'::character varying])::"text"[]))),
    ADD CONSTRAINT "ck_story_request_length" CHECK ((("length" IS NULL) OR (("length")::"text" = ANY ((ARRAY['short'::character varying, 'medium'::character varying, 'long'::character varying])::"text"[])))),
    ADD CONSTRAINT "ck_story_request_narrative_style" CHECK ((("narrative_style")::"text" = ANY ((ARRAY['prose'::character varying, 'gamebook'::character varying])::"text"[]))),
    ADD CONSTRAINT "ck_story_request_style_band" CHECK (((("narrative_style")::"text" = 'prose'::"text") OR (("age_band")::"text" = ANY ((ARRAY['13-16'::character varying, '16+'::character varying])::"text"[])))),
    ADD CONSTRAINT "ck_story_request_title_anchor_mutex" CHECK ((NOT (("proposed_series_title" IS NOT NULL) AND ("anchor_storybook_id" IS NOT NULL))));
