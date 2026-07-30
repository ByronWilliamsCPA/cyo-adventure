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
--      cover is withheld from a child's library card by every API read
--      path with no change needed on the read side. Note the scope: this
--      gates the API responses that carry a cover URL, not the bytes in
--      object storage, whose exposure is a separate control (see the
--      module note in covers/storage.py).
--
--   2. Add cover_approved_by / cover_approved_at, the cover-art analogue of
--      approved_by / published_at above: stamped only by the new
--      covers.service.approve_cover, the sole path that may move a cover
--      from 'pending_review' to 'ready'.
--
--   3. Backfill: demote pre-existing 'ready' rows that carry no approver
--      back to 'pending_review'. Without this, every cover generated
--      before the gate existed stays 'ready' with a NULL
--      cover_approved_by, which is precisely the population the gate was
--      written to catch: images that reached child library cards with no
--      human ever having looked at them. Verified against production on
--      2026-07-28: exactly one row matches (sk_ashfall_expedition v1), so
--      the blast radius is one cover reverting to the admin approval
--      queue, not a library-wide blackout. Stating the number here rather
--      than leaving the demotion silent is deliberate.
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

-- #CRITICAL: data integrity: a row at cover_status = 'ready' with
-- cover_approved_by IS NULL is not an approved cover; it is a cover that
-- predates the approval gate, generated when 'ready' was written directly by
-- covers/service.py::generate_cover. Leaving those rows alone would
-- grandfather them as approved-by-nobody, so the very covers that never had a
-- human review would be the only ones exempt from requiring one. Demote them
-- to 'pending_review' so an admin has to approve them through
-- covers.service.approve_cover like any newly generated cover.
--
-- Naturally idempotent and safe to re-run: after this statement no row
-- satisfies the predicate, and every row that reaches 'ready' from here on
-- does so only via approve_cover, which stamps cover_approved_by in the same
-- operation, so a re-application matches zero rows. It cannot demote a
-- legitimately approved cover, because 'ready' plus a NULL approver is a state
-- approve_cover can never produce.
--
-- #VERIFY: after applying, expect zero rows from
--   SELECT count(*) FROM public.storybook_version
--    WHERE cover_status = 'ready' AND cover_approved_by IS NULL;
-- and confirm the demoted covers appear in the admin approval surface. On
-- production as of 2026-07-28 this affects exactly one row
-- (sk_ashfall_expedition v1), whose cover reverts to pending_review until an
-- admin approves it.
UPDATE "public"."storybook_version"
   SET "cover_status" = 'pending_review'
 WHERE "cover_status" = 'ready'
   AND "cover_approved_by" IS NULL;
