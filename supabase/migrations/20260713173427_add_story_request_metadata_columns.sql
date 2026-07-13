-- Add story_request columns that are present in the baseline schema
-- (supabase/migrations/20260710000000_baseline.sql) but were never applied
-- to production: the baseline migration is recorded as applied in
-- supabase_migrations.schema_migrations, yet these columns do not exist on
-- the live database. Root-caused via GET /v1/story-requests and
-- GET /v1/admin/story-requests both returning 500
-- (asyncpg.exceptions.UndefinedColumnError: story_request.initiator_role
-- does not exist).
--
-- This migration is a no-op on production's next `supabase db push` (the
-- columns and constraints below already exist there once this migration has
-- run once). On any environment that applies the full migration chain fresh
-- against an empty database (CI, a new dev clone, staging, DR restore), the
-- baseline migration already creates these same columns and constraints, so
-- every statement below is written to skip cleanly when its target already
-- exists rather than error.

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
--
-- #CRITICAL: data integrity: this UPDATE cannot resolve every row. It joins
-- on child_profile, so a profile-less request (guardian/admin-initiated,
-- story_request.profile_id IS NULL, a live path per api/story_requests.py)
-- is never matched, and a row whose linked profile's own age_band is itself
-- NULL is matched but not changed. Guessing a value for either case would
-- silently misrepresent what the request was actually scoped to.
-- #VERIFY: the guard below fails the migration loudly if any row is still
-- unresolved after this UPDATE, rather than letting SET NOT NULL fail with
-- an opaque SQLSTATE 23502 or silently accepting a guessed value.
UPDATE "public"."story_request" sr
SET "age_band" = cp."age_band"
FROM "public"."child_profile" cp
WHERE sr."profile_id" = cp."id"
  AND sr."age_band" IS NULL;

DO $$
DECLARE
    unresolved_count integer;
BEGIN
    SELECT count(*) INTO unresolved_count
    FROM "public"."story_request"
    WHERE "age_band" IS NULL;

    IF unresolved_count > 0 THEN
        RAISE EXCEPTION
            'story_request has % row(s) with unresolved age_band after backfill (profile-less requests or a profile with its own NULL age_band); resolve manually before this migration can proceed',
            unresolved_count;
    END IF;
END $$;

ALTER TABLE "public"."story_request"
    ALTER COLUMN "age_band" SET NOT NULL;

DO $$
BEGIN
    ALTER TABLE "public"."story_request"
        ADD CONSTRAINT "ck_story_request_age_band" CHECK ((("age_band")::"text" = ANY ((ARRAY['3-5'::character varying, '5-8'::character varying, '8-11'::character varying, '10-13'::character varying, '13-16'::character varying, '16+'::character varying])::"text"[])));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE "public"."story_request"
        ADD CONSTRAINT "ck_story_request_anchor_requires_series" CHECK ((("anchor_storybook_id" IS NULL) OR ("series_id" IS NOT NULL)));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE "public"."story_request"
        ADD CONSTRAINT "ck_story_request_initiator_role" CHECK ((("initiator_role")::"text" = ANY ((ARRAY['child'::character varying, 'guardian'::character varying, 'admin'::character varying])::"text"[])));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE "public"."story_request"
        ADD CONSTRAINT "ck_story_request_length" CHECK ((("length" IS NULL) OR (("length")::"text" = ANY ((ARRAY['short'::character varying, 'medium'::character varying, 'long'::character varying])::"text"[]))));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE "public"."story_request"
        ADD CONSTRAINT "ck_story_request_narrative_style" CHECK ((("narrative_style")::"text" = ANY ((ARRAY['prose'::character varying, 'gamebook'::character varying])::"text"[])));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE "public"."story_request"
        ADD CONSTRAINT "ck_story_request_style_band" CHECK (((("narrative_style")::"text" = 'prose'::"text") OR (("age_band")::"text" = ANY ((ARRAY['13-16'::character varying, '16+'::character varying])::"text"[]))));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE "public"."story_request"
        ADD CONSTRAINT "ck_story_request_title_anchor_mutex" CHECK ((NOT (("proposed_series_title" IS NOT NULL) AND ("anchor_storybook_id" IS NOT NULL))));
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- The baseline also declares these two FK constraints for the columns added
-- above; add them here too so production ends up with the same referential
-- integrity the baseline defines everywhere else.
DO $$
BEGIN
    ALTER TABLE ONLY "public"."story_request"
        ADD CONSTRAINT "fk_story_request_anchor_storybook_id_storybook" FOREIGN KEY ("anchor_storybook_id") REFERENCES "public"."storybook"("id");
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE ONLY "public"."story_request"
        ADD CONSTRAINT "fk_story_request_series_id_series" FOREIGN KEY ("series_id") REFERENCES "public"."series"("id");
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
