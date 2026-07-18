-- #173: seed the single, well-known "system catalog" family that owns
-- admin-initiated catalog-origin story requests, concepts, and storybooks.
--
-- Design decision (owner-ratified 2026-07-18): rather than make family_id
-- nullable across story_request / concept / storybook (which would reopen the
-- descoped WS-E catalog-origin cascade and force every family-scoped authz
-- check to handle a null owner), a catalog-origin request is OWNED by this
-- fixed sentinel family. family_id stays a hard NOT NULL invariant everywhere;
-- the resulting book becomes globally visible only when an admin publishes it
-- with visibility='catalog' (ADR-005 human approval unchanged). This mirrors
-- the "generic family used whenever an admin requests a book" model.
--
-- The id MUST match cyo_adventure.db.models.CATALOG_FAMILY_ID. It is a stable,
-- permanent sentinel and must never be reused for a real family.
--
-- Idempotent: ON CONFLICT DO NOTHING so re-applying the migration (or applying
-- it after a manual seed) is a no-op. created_at falls to its now() default and
-- deactivated_at stays NULL (the catalog family is always active).

INSERT INTO "public"."family" ("id", "name")
VALUES ('0ca7a109-0000-4000-8000-000000000000', 'Catalog (system)')
ON CONFLICT ("id") DO NOTHING;
