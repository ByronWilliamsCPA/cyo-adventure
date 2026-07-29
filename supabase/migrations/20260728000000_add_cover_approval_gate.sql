-- H2 (security-hardening-plan-2026-07.md): AI cover images must not reach a
-- child's library card without a human review, mirroring the existing
-- approved_by/published_at gate that already protects story TEXT
-- (storybook_version.approved_by, set only by the sole publish path in
-- publishing/service.py::approve). Two changes:
--
--   1. Widen the cover_status CHECK to add 'pending_review', inserted
--      between 'generating' and 'ready'. covers/service.py::generate_cover
--      now stops at 'pending_review' on a successful generation instead of
--      writing 'ready' directly; api/library.py's cover_status == "ready"
--      read gate already excludes any other status, so a pending_review
--      cover is structurally invisible to a child's library card with no
--      change needed on the read side.
--
--   2. Add cover_approved_by / cover_approved_at, the cover-art analogue of
--      approved_by / published_at above: stamped only by the new
--      covers.service.approve_cover, the sole path that may move a cover
--      from 'pending_review' to 'ready'.
--
-- Written to be idempotent (checks the current constraint definition before
-- acting, "add column if not exists"), mirroring
-- 20260727000000_add_book_unassigned_to_pipeline_event.sql and
-- 20260718010000_add_device_grant_expires_at.sql, so it is a no-op if
-- applied a second time.
--
-- #CRITICAL: timing: apply this migration BEFORE deploying the image that
-- reads/writes cover_approved_by, cover_approved_at, or the
-- 'pending_review' status. Against a database without these, the new admin
-- approve endpoint and the changed generate_cover transition would fail
-- (UndefinedColumn / CHECK violation), mirroring the migrate-before-deploy
-- note on 20260718010000_add_device_grant_expires_at.sql.
--
-- Forward-only migration per this project's Supabase CLI convention
-- (ADR-012); no down script.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_storybook_version_cover_status'
          AND conrelid = '"public"."storybook_version"'::regclass
          AND pg_get_constraintdef(oid) NOT LIKE '%''pending_review''%'
    ) THEN
        ALTER TABLE "public"."storybook_version"
            DROP CONSTRAINT "ck_storybook_version_cover_status";
        ALTER TABLE "public"."storybook_version"
            ADD CONSTRAINT "ck_storybook_version_cover_status"
            CHECK ((("cover_status")::"text" = ANY ((ARRAY['none'::character varying, 'generating'::character varying, 'pending_review'::character varying, 'ready'::character varying, 'failed'::character varying])::"text"[])));
    END IF;
END
$$;

ALTER TABLE "public"."storybook_version"
    ADD COLUMN IF NOT EXISTS "cover_approved_by" uuid,
    ADD COLUMN IF NOT EXISTS "cover_approved_at" timestamp with time zone;

ALTER TABLE ONLY "public"."storybook_version"
    DROP CONSTRAINT IF EXISTS "storybook_version_cover_approved_by_fkey";
ALTER TABLE ONLY "public"."storybook_version"
    ADD CONSTRAINT "storybook_version_cover_approved_by_fkey" FOREIGN KEY ("cover_approved_by")
    REFERENCES "public"."user"("id") ON DELETE SET NULL;

COMMENT ON COLUMN "public"."storybook_version"."cover_approved_by" IS
    'Admin who approved this version''s generated cover for child delivery (H2). NULL until approve_cover runs; set only by covers.service.approve_cover.';
COMMENT ON COLUMN "public"."storybook_version"."cover_approved_at" IS
    'Timestamp of the cover approval recorded in cover_approved_by (H2).';
