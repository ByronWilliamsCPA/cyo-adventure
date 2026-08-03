-- W0.4 (kid-appeal-implementation-plan.md, design review section 4.1): give
-- a story request a real link to the storybook it produced, so the kid
-- request card can flip from "being written" to "it's on your shelf"
-- honestly instead of RequestStory.tsx's retired isLikelyPublished substring
-- guess against shelf titles.
--
-- Adds "public"."story_request"."resulting_storybook_id" (nullable
-- character varying(120), matching anchor_storybook_id's column type since
-- both reference "public"."storybook"."id", itself character varying(120))
-- plus its FK to "public"."storybook"("id") ON DELETE SET NULL. Mirrors
-- anchor_storybook_id's own FK (added in 20260713173427_add_story_request_
-- metadata_columns.sql, later given its ON DELETE SET NULL action in
-- 20260720170000_add_erasure_cascades.sql) and cover_approved_by's two-step
-- "ADD COLUMN IF NOT EXISTS" + "DROP CONSTRAINT IF EXISTS / ADD CONSTRAINT"
-- shape (20260728000000_add_cover_approval_gate.sql), so this migration is a
-- no-op if applied a second time.
--
-- Application layer: publishing/service.py::approve() is the SOLE path that
-- sets storybook.status = "published" (see that function's own #CRITICAL
-- note), and it stamps this column in the same operation by resolving
-- GenerationJob WHERE (storybook_id, version) == the approved (id, version)
-- to a concept_id, then StoryRequest WHERE concept_id == that concept_id --
-- reusing the exact two-hop resolution generation/worker.py's
-- _stamp_request_interpretation already established for the K19
-- interpretation write, rather than adding a third way to walk
-- request -> concept -> job -> storybook. A guardian-authored or catalog job
-- has no originating request row, so that resolution is a silent no-op, same
-- as _stamp_request_interpretation's.
--
-- Column-level, not row-level: unlike the three RLS-guarded remediation
-- tables (child_profile, story_request, device_grant) touched by
-- 20260724120000_scoped_rls_tier1_family_scoping.sql, this migration adds a
-- new NULLABLE column to a table whose family_scoped RLS policy
-- (WITH CHECK / USING) already filters by "family_id", a row-level
-- predicate blind to which columns exist on the row. No RLS policy
-- references specific story_request columns by name, so a plain
-- "ADD COLUMN" here requires no matching RLS change; the existing
-- family_scoped and worker_rw policies apply to the widened row unchanged.
--
-- No CASCADE-tax entry beyond the FK below: a storybook row is never deleted
-- by any live application code path today (no admin "delete storybook"
-- endpoint exists, and family deletion CASCADEs both the storybook and the
-- story_request together via family_id, so the SET NULL branch below never
-- fires via any current product flow). ON DELETE SET NULL is still the
-- correct action, matching every other nullable non-owning reference on this
-- row (profile_id, reviewed_by, concept_id, anchor_storybook_id): the
-- request is family-owned content that must survive a storybook row
-- vanishing by any other means (a manual admin fixup, a future hard-delete
-- tool, direct SQL) rather than silently fail to delete or be dragged down
-- with it.
--
-- Forward-only migration per this project's Supabase CLI convention
-- (ADR-012); no down script.

ALTER TABLE "public"."story_request"
    ADD COLUMN IF NOT EXISTS "resulting_storybook_id" character varying(120);

ALTER TABLE ONLY "public"."story_request"
    DROP CONSTRAINT IF EXISTS "story_request_resulting_storybook_id_fkey";
ALTER TABLE ONLY "public"."story_request"
    ADD CONSTRAINT "story_request_resulting_storybook_id_fkey" FOREIGN KEY ("resulting_storybook_id")
    REFERENCES "public"."storybook"("id") ON DELETE SET NULL;

COMMENT ON COLUMN "public"."story_request"."resulting_storybook_id" IS
    'The storybook this request produced, stamped once at publish by publishing.service.approve(); NULL before publish (W0.4).';
