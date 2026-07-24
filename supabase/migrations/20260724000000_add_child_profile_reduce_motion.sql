-- Guardian-set per-child motion preference: when true, the reader/library
-- frontend treats this child's session as if prefers-reduced-motion were set
-- (band-tokens.css), regardless of the device's own OS-level preference.
-- Set/cleared only via src/cyo_adventure/api/profiles.py::update_profile
-- (guardian-only) or src/cyo_adventure/api/admin_profiles.py (admin-only).

-- "reduce_motion" is NOT NULL on the ORM side
-- (ChildProfile.reduce_motion: Mapped[bool] = mapped_column(default=False))
-- but carries NO server_default (mirrors "tts_enabled"/"request_auto_approve":
-- a plain "boolean NOT NULL" column, Python-side default only). Added nullable
-- first, backfilled, then constrained, rather than
-- "ADD COLUMN ... DEFAULT false NOT NULL", so the final catalog state has no
-- persisted column default, matching what Base.metadata.create_all would
-- produce and what tests/integration/test_schema_parity.py checks for.
alter table "public"."child_profile"
    add column if not exists "reduce_motion" boolean;

update "public"."child_profile"
    set "reduce_motion" = false
    where "reduce_motion" is null;

alter table "public"."child_profile"
    alter column "reduce_motion" set not null;
