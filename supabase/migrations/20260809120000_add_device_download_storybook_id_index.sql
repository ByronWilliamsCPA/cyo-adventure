-- G15 follow-up: device_download.storybook_id is a foreign key (REFERENCES
-- storybook(id) ON DELETE CASCADE, 20260809110000_add_device_download.sql) but that
-- migration only indexed the family_id side (ix_device_download_family_id), following
-- the same "Postgres indexes the referenced side of a foreign key automatically but
-- never the referencing side" reasoning it documents -- an omission on the exact
-- column that reasoning also applies to. A storybook deletion (CASCADE) would
-- otherwise sequentially scan this table, and the 3-column unique constraint
-- (device_id, child_profile_id, storybook_id) does not help: storybook_id is not
-- its leading column, so Postgres cannot use it for a storybook_id-only lookup.

CREATE INDEX IF NOT EXISTS ix_device_download_storybook_id
    ON "public"."device_download" (storybook_id);

-- Forward-only migration per this project's Supabase CLI convention (ADR-012); no down
-- script.
