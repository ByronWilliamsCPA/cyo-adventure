-- UW-M07 defense-in-depth stopgap. The R2 cover object key
-- (covers/storage.py::cover_object_key) was fully determined by
-- storybook_id and version, both visible or guessable to a client, so the
-- object's privacy depended entirely on the bucket's own access control.
-- The root cause -- the bucket's public custom domain -- was closed at the
-- Cloudflare level on 2026-07-30 (outside this repository); this column
-- adds a second, independent layer: a per-cover random token that
-- covers/service.py::generate_cover now folds into the R2 key, so knowing
-- storybook_id and version alone is no longer sufficient to reach the
-- object even if the public binding is ever mistakenly restored.
--
-- Purely additive: a nullable column with no backfill. Every row created
-- before this migration keeps cover_object_salt = NULL, and
-- cover_object_key() falls back to the legacy unsalted key for those, so
-- already-uploaded R2 objects (which were never renamed) keep resolving
-- with no R2-side migration required. Only newly generated covers receive
-- a salt going forward.
--
-- Written to be idempotent ("add column if not exists"), mirroring
-- 20260728000000_add_cover_approval_gate.sql and
-- 20260718010000_add_device_grant_expires_at.sql, so it is a no-op if
-- applied a second time.
--
-- #CRITICAL: timing: apply this migration BEFORE deploying the image that
-- writes cover_object_salt (covers/service.py::generate_cover). Against a
-- database without this column, that write would fail (UndefinedColumn),
-- mirroring the migrate-before-deploy note on
-- 20260718010000_add_device_grant_expires_at.sql.
--
-- Forward-only migration per this project's Supabase CLI convention
-- (ADR-012); no down script.

ALTER TABLE "public"."storybook_version"
    ADD COLUMN IF NOT EXISTS "cover_object_salt" character varying(32);

COMMENT ON COLUMN "public"."storybook_version"."cover_object_salt" IS
    'Per-cover random token folded into the R2 object key (UW-M07 defense in depth). NULL for rows predating this column, which resolve at the legacy unsalted key; set once by covers.service.generate_cover and never rotated.';
