-- docs/superpowers/specs/2026-09-08-cover-ai-review-design.md Design
-- section 4: three columns recording the outcome of the AI-assisted cover
-- review loop (covers/review.py::review_cover, called from
-- covers/service.py::generate_cover).
--
-- Purely additive: all three columns are nullable with no backfill. NULL on
-- cover_review_verdict means one of two things, deliberately unified rather
-- than distinguished by a fourth state: either this cover predates the
-- feature, or every review attempt in its run failed open (a ProviderError
-- or an unparseable response -- see covers/review.py's docstring). Both
-- cases mean the same thing to a reviewing admin: "this cover was not
-- actually judged by the AI reviewer," so one NULL value serves both.
--
-- cover_review_attempts is NOT NULL DEFAULT 0 (not nullable like the other
-- two): every row, including one that predates this migration, has a
-- well-defined attempt count of zero reviews run, so a default is correct
-- rather than a third "unknown" state.
--
-- Written to be idempotent ("add column if not exists"), mirroring
-- 20260730000000_add_cover_object_salt.sql, so it is a no-op if applied a
-- second time.
--
-- #CRITICAL: timing: apply this migration BEFORE deploying the image that
-- writes these columns (covers/service.py::generate_cover). Against a
-- database without them, that write would fail (UndefinedColumn), mirroring
-- the migrate-before-deploy note on 20260730000000_add_cover_object_salt.sql.
--
-- Forward-only migration per this project's Supabase CLI convention
-- (ADR-012); no down script.

ALTER TABLE "public"."storybook_version"
    ADD COLUMN IF NOT EXISTS "cover_review_verdict" text,
    ADD COLUMN IF NOT EXISTS "cover_review_notes" text,
    ADD COLUMN IF NOT EXISTS "cover_review_attempts" integer NOT NULL DEFAULT 0;

COMMENT ON COLUMN "public"."storybook_version"."cover_review_verdict" IS
    'AI cover reviewer''s verdict for the surviving generation attempt: pass, flag, or NULL (predates this feature, or every attempt in the run failed open). Set once by covers.service.generate_cover.';

COMMENT ON COLUMN "public"."storybook_version"."cover_review_notes" IS
    'AI cover reviewer''s short explanation, present only when cover_review_verdict is not NULL. Set once by covers.service.generate_cover.';

COMMENT ON COLUMN "public"."storybook_version"."cover_review_attempts" IS
    'How many generate+review cycles covers.service.generate_cover ran for the current cover (0 for a row predating this feature, up to MAX_COVER_REVIEW_ATTEMPTS otherwise).';

ALTER TABLE "public"."storybook_version"
    ADD CONSTRAINT "ck_storybook_version_cover_review_verdict"
    CHECK ("cover_review_verdict" IN ('pass', 'flag'));
