-- Catalog-first inventory: seed the reserved "Library" family that owns the
-- admin-authored base story inventory.
--
-- Stories no longer require a real family's UUID to enter the database. An
-- admin imports the base inventory under this single reserved family
-- (src/cyo_adventure/core/catalog.py::LIBRARY_FAMILY_ID) via
-- `import_cli --library`, and each story becomes browsable and assignable by
-- every family's guardians once an admin publishes it at
-- visibility='catalog' (WS-E) and a guardian assigns it (StorybookAssignment).
--
-- The insert is idempotent (ON CONFLICT DO NOTHING) so re-running the
-- migration, or seeding a dev/staging database on top of it, is safe. The
-- Library family holds no users or child profiles; admins act on its stories
-- through the global is_admin capability. Ownership alone grants no child
-- access: visibility stays 'family' until admin release-approval, and the
-- StorybookAssignment read-gate is unchanged, so this row widens nothing on
-- its own.

INSERT INTO "public"."family" ("id", "name")
VALUES ('00000000-0000-0000-0000-000000000001', 'Library')
ON CONFLICT ("id") DO NOTHING;
