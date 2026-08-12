-- Rebuild ix_pipeline_event_entity_event_type without an exclusive lock, part 2 of 2.
--
-- Recreates, with CONCURRENTLY, the index that 20260811170000 dropped. Column list and
-- name are identical to the one 20260810000000 created, so the end state of the schema is
-- unchanged; only the way it is built differs. See part 1 for why this is split across
-- two single-statement files and for the measured production scale behind the change.
--
-- What the index is for: the send-back half of ADR-007's reviewed-storybook exemption
-- probes "pipeline_event" by (entity_type, entity_id, event_type) once per row per
-- nightly sweep. Without support that is a sequential scan of an append-only log that
-- only ever grows.
--
-- #CRITICAL: external resources: a CONCURRENTLY build that fails partway leaves an
-- INVALID index behind. Postgres does not use an invalid index for reads, but it is still
-- maintained on write, so the failure mode is a silent loss of the index's benefit rather
-- than an error anyone sees. `if not exists` will then match that invalid index by name
-- and skip the rebuild, so a re-run does not repair it on its own.
-- #VERIFY: after deploying this pair, confirm
--   select indisvalid from pg_index x join pg_class i on i.oid = x.indexrelid
--   where i.relname = 'ix_pipeline_event_entity_event_type';
-- returns true. If it returns false, drop the invalid index concurrently and re-run this
-- statement; do not leave it in place.
--
-- Forward-only migration per this project's Supabase CLI convention (ADR-012); no down
-- script.

create index concurrently if not exists "ix_pipeline_event_entity_event_type"
    on "public"."pipeline_event" using "btree"
    ("entity_type", "entity_id", "event_type");
