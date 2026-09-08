-- docs/superpowers/specs/2026-09-08-cover-ai-review-design.md Design
-- section 4: three columns recording the outcome of the AI-assisted cover
-- review loop (covers/review.py::review_cover, called from
-- covers/service.py::generate_cover).
--
-- Purely additive: all three columns are nullable with no backfill. NULL on
-- cover_review_verdict means one of several things, deliberately unified
-- rather than distinguished by an extra state: this cover predates the
-- feature; the review provider could not be built for this generation (a
-- ConfigurationError degrade-to-off -- see
-- covers/service.py::_resolve_review_provider); or the reviewer ran but its
-- final attempt returned no usable verdict (a ProviderError, an empty or
-- unparseable response, or a value outside pass/flag -- see
-- covers/review.py's docstring). All of these mean the same thing to a
-- reviewing admin: "this cover was not actually judged by the AI reviewer,"
-- so one NULL value serves all of them.
--
-- cover_review_attempts is NOT NULL DEFAULT 0 (not nullable like the other
-- two): every row, including one that predates this migration, has a
-- well-defined attempt count of zero reviews run, so a default is correct
-- rather than a third "unknown" state.
--
-- Written to be idempotent: the ADD COLUMN clauses use IF NOT EXISTS
-- (mirroring 20260730000000_add_cover_object_salt.sql), and the CHECK
-- constraint below uses this project's DROP CONSTRAINT IF EXISTS + ADD
-- CONSTRAINT pattern (20260801050000_add_child_profile_gamification_settings.sql,
-- 20260802000000_add_user_residence_country_and_adulthood_attestation.sql,
-- 20260823120000_add_submitted_to_pipeline_event.sql,
-- 20260809100000_add_notification_digest_ready_to_pipeline_event.sql), so
-- the whole file is a no-op if applied a second time.
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
    'AI cover reviewer''s verdict for the surviving generation attempt: pass, flag, or NULL (predates this feature, review provider could not be built for this generation, or the reviewer ran but its final attempt returned no usable verdict). Set once by covers.service.generate_cover.';

COMMENT ON COLUMN "public"."storybook_version"."cover_review_notes" IS
    'AI cover reviewer''s short explanation, present only when cover_review_verdict is not NULL. Set once by covers.service.generate_cover.';

COMMENT ON COLUMN "public"."storybook_version"."cover_review_attempts" IS
    'How many generate+review cycles covers.service.generate_cover ran for the current cover (0 when the cover predates this feature or the review provider could not be built for this generation, up to MAX_COVER_REVIEW_ATTEMPTS when the reviewer ran).';

-- DROP-then-ADD keeps re-application idempotent, matching this project's
-- house pattern for idempotent CHECK-constraint migrations (see the header
-- comment above); an explicit "IS NULL OR" clause rather than relying on
-- implicit SQL NULL semantics for the IN() comparison.
ALTER TABLE "public"."storybook_version"
    DROP CONSTRAINT IF EXISTS "ck_storybook_version_cover_review_verdict";
ALTER TABLE "public"."storybook_version"
    ADD CONSTRAINT "ck_storybook_version_cover_review_verdict"
    CHECK ("cover_review_verdict" IS NULL OR "cover_review_verdict" IN ('pass', 'flag'));
